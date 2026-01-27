"""Expiration checker for option positions.

This module implements the ExpirationChecker class that:
1. Scans option positions for upcoming expirations
2. Creates alerts for each applicable threshold
3. Uses dedupe_key for idempotent alert creation
"""

import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.alerts.factory import create_alert
from src.alerts.models import AlertType
from src.alerts.repository import AlertRepository
from src.core.portfolio import PortfolioManager
from src.models.position import AssetType
from src.options.metrics import (
    alerts_created_total,
    alerts_deduped_total,
    check_duration_seconds,
    check_errors_total,
    expiration_check_runs_total,
)
from src.options.thresholds import ExpirationThreshold, get_applicable_thresholds

logger = logging.getLogger(__name__)


class ExpirationChecker:
    """Checks option positions for upcoming expirations and creates alerts.

    Responsibilities:
    1. Scan all option positions for an account
    2. Calculate days to expiry (DTE) using market timezone
    3. Create alerts for each applicable threshold
    4. Rely on dedupe_key for idempotent writes
    """

    def __init__(
        self,
        portfolio: PortfolioManager,
        alert_repo: AlertRepository,
        market_tz: ZoneInfo = ZoneInfo("America/New_York"),
    ):
        """Initialize the checker.

        Args:
            portfolio: Portfolio manager for fetching positions
            alert_repo: Alert repository for persisting alerts
            market_tz: Market timezone for DTE calculation (default: US East)
        """
        self.portfolio = portfolio
        self.alert_repo = alert_repo
        self.market_tz = market_tz

    @check_duration_seconds.time()
    async def check_expirations(self, account_id: str) -> dict:
        """Check option positions and create expiration alerts.

        Args:
            account_id: Account to check positions for

        Returns:
            Statistics dictionary with counts and errors
        """
        run_id = str(uuid4())
        logger.info(f"Starting expiration check run_id={run_id} account={account_id}")

        stats = {
            "run_id": run_id,
            "positions_checked": 0,
            "positions_skipped_missing_expiry": 0,
            "positions_already_expired": 0,
            "positions_not_expiring_soon": 0,
            "alerts_attempted": 0,
            "alerts_created": 0,
            "alerts_deduplicated": 0,
            "errors": [],
        }

        try:
            # Get all positions and filter to options
            positions = await self.portfolio.get_positions(account_id=account_id)
            option_positions = [p for p in positions if p.asset_type == AssetType.OPTION]

            # Calculate "today" in market timezone
            today = datetime.now(self.market_tz).date()
            logger.info(
                f"run_id={run_id} checking {len(option_positions)} option positions "
                f"relative to {today} ({self.market_tz})"
            )

            for pos in option_positions:
                stats["positions_checked"] += 1

                try:
                    # Validate expiry exists
                    if pos.expiry is None:
                        error_msg = f"Position {pos.id} (symbol={pos.symbol}) missing expiry date"
                        logger.warning(f"run_id={run_id} {error_msg}")
                        stats["positions_skipped_missing_expiry"] += 1
                        stats["errors"].append(error_msg)
                        check_errors_total.labels(error_type="missing_expiry").inc()
                        continue

                    # Calculate DTE
                    days_to_expiry = (pos.expiry - today).days

                    # Skip already expired
                    if days_to_expiry < 0:
                        stats["positions_already_expired"] += 1
                        logger.debug(f"run_id={run_id} position {pos.id} already expired")
                        continue

                    # Get applicable thresholds
                    thresholds = get_applicable_thresholds(days_to_expiry)

                    if not thresholds:
                        stats["positions_not_expiring_soon"] += 1
                        logger.debug(
                            f"run_id={run_id} position {pos.id} "
                            f"DTE={days_to_expiry} out of scope"
                        )
                        continue

                    # Create alert for each threshold
                    for threshold in thresholds:
                        stats["alerts_attempted"] += 1

                        try:
                            alert = self._create_expiration_alert(
                                position=pos,
                                threshold=threshold,
                                days_to_expiry=days_to_expiry,
                                account_id=account_id,
                            )

                            # Idempotent write (dedupe_key handles duplicates)
                            is_new, alert_id = await self.alert_repo.persist_alert(alert)

                            if is_new:
                                stats["alerts_created"] += 1
                                alerts_created_total.inc()
                                logger.info(
                                    f"run_id={run_id} created alert: "
                                    f"position_id={pos.id} symbol={pos.symbol} "
                                    f"DTE={days_to_expiry} threshold={threshold.days}d "
                                    f"alert_id={alert_id}"
                                )
                            else:
                                stats["alerts_deduplicated"] += 1
                                alerts_deduped_total.inc()
                                logger.debug(
                                    f"run_id={run_id} alert deduplicated: "
                                    f"position_id={pos.id} threshold={threshold.days}d"
                                )

                        except Exception as e:
                            error_msg = (
                                f"Failed to create alert for position_id={pos.id} "
                                f"threshold={threshold.days}d: {e}"
                            )
                            logger.error(f"run_id={run_id} {error_msg}", exc_info=True)
                            stats["errors"].append(error_msg)
                            check_errors_total.labels(error_type="alert_creation").inc()

                except Exception as e:
                    error_msg = f"Failed to process position_id={pos.id}: {e}"
                    logger.error(f"run_id={run_id} {error_msg}", exc_info=True)
                    stats["errors"].append(error_msg)
                    check_errors_total.labels(error_type="position_processing").inc()

            logger.info(
                f"run_id={run_id} check complete: "
                f"{stats['positions_checked']} checked, "
                f"{stats['alerts_created']} created, "
                f"{stats['alerts_deduplicated']} deduplicated, "
                f"{len(stats['errors'])} errors"
            )

            expiration_check_runs_total.labels(status="success").inc()
            return stats

        except Exception:
            logger.error(f"run_id={run_id} check failed", exc_info=True)
            expiration_check_runs_total.labels(status="failed").inc()
            raise

    def _create_expiration_alert(
        self,
        position,
        threshold: ExpirationThreshold,
        days_to_expiry: int,
        account_id: str,
    ):
        """Create an expiration alert for a position/threshold.

        Args:
            position: The option position
            threshold: The threshold being triggered
            days_to_expiry: Current DTE
            account_id: Account ID for the alert

        Returns:
            AlertEvent ready for persistence

        Raises:
            ValueError: If required position fields are missing
        """
        # Validate required fields
        if position.strike is None:
            raise ValueError(f"Position {position.id} missing strike price")
        if position.put_call is None:
            raise ValueError(f"Position {position.id} missing put_call type")

        # Build summary message
        if days_to_expiry == 0:
            summary = f"期权 {position.symbol} 今日收盘到期"
        elif days_to_expiry == 1:
            summary = f"期权 {position.symbol} 明日到期"
        else:
            summary = f"期权 {position.symbol} 将在 {days_to_expiry} 天后到期"

        # Build details (V1 minimal set)
        strike_value = (
            float(position.strike) if isinstance(position.strike, Decimal) else position.strike
        )

        details = {
            "threshold_days": threshold.days,
            "expiry_date": position.expiry.isoformat(),
            "days_to_expiry": days_to_expiry,
            "position_id": position.id,
            "strike": strike_value,
            "put_call": position.put_call.value,
            "quantity": position.quantity,
        }

        # Add contract_key if available
        if hasattr(position, "contract_key") and position.contract_key:
            details["contract_key"] = position.contract_key

        # Create alert (symbol preserved for display)
        return create_alert(
            type=AlertType.OPTION_EXPIRING,
            severity=threshold.severity,
            summary=summary,
            account_id=account_id,
            symbol=position.symbol,
            details=details,
        )
