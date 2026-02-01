"""ExpirationWorker for daily derivative expiration checks.

This module provides the ExpirationWorker class that schedules and runs
daily expiration checks using the ExpirationManager service. It integrates
with the AlertService to emit expiration warnings.

Scheduling Options:
    1. APScheduler (recommended for in-process scheduling):
       ```python
       from apscheduler.triggers.cron import CronTrigger
       from src.workers.expiration_worker import ExpirationWorker

       worker = ExpirationWorker(session_factory, alert_service)
       scheduler.add_job(
           worker.run_check,
           CronTrigger(hour=6, minute=0),  # 6 AM daily, before market open
           id="expiration_check",
       )
       ```

    2. Cron (external scheduling):
       ```bash
       # Add to crontab (6 AM daily before US market open)
       0 6 * * * /path/to/python -m src.workers.expiration_worker
       ```

    3. systemd timer (production Linux):
       Create /etc/systemd/system/expiration-check.timer and .service

Usage:
    from src.workers.expiration_worker import ExpirationWorker

    worker = ExpirationWorker(
        session_factory=async_session,
        alert_service=alert_service,  # Optional
    )
    alerts = await worker.run_check()
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity
from src.derivatives.expiration_manager import ExpirationAlert, ExpirationManager

if TYPE_CHECKING:
    from src.alerts.service import AlertService

logger = logging.getLogger(__name__)


# Default warning days per SC-011: at least 5 days before expiry
DEFAULT_WARNING_DAYS = 5


class ExpirationWorker:
    """Worker for daily derivative expiration checks.

    This worker uses ExpirationManager to identify expiring positions and
    optionally emits alerts via AlertService. If no AlertService is provided,
    it gracefully degrades to logging only.

    Attributes:
        session_factory: Callable that creates AsyncSession instances
        alert_service: Optional AlertService for emitting expiration alerts
        warning_days: Number of days before expiry to warn (default: 5)

    Example:
        worker = ExpirationWorker(
            session_factory=async_session,
            alert_service=alert_service,
        )

        # Run manually
        alerts = await worker.run_check()

        # Or schedule with APScheduler
        scheduler.add_job(worker.run_check, CronTrigger(hour=6))
    """

    def __init__(
        self,
        session_factory: Callable[[], AsyncSession],
        alert_service: "AlertService | None" = None,
        warning_days: int = DEFAULT_WARNING_DAYS,
    ):
        """Initialize ExpirationWorker.

        Args:
            session_factory: Callable that returns an AsyncSession.
                             Can be a context manager factory (recommended) or
                             a simple callable returning a session.
            alert_service: Optional AlertService for emitting alerts.
                          If None, alerts will only be logged.
            warning_days: Number of days before expiry to warn (default: 5)

        Raises:
            ValueError: If warning_days is negative
        """
        if warning_days < 0:
            raise ValueError(f"warning_days must be non-negative, got {warning_days}")

        self._session_factory = session_factory
        self._alert_service = alert_service
        self._warning_days = warning_days

    @property
    def warning_days(self) -> int:
        """Get the configured warning days threshold."""
        return self._warning_days

    async def run_check(self) -> list[ExpirationAlert]:
        """Run expiration check and emit alerts for expiring positions.

        This method:
        1. Creates a database session
        2. Uses ExpirationManager to find expiring positions
        3. Emits alerts via AlertService (if configured) or logs them

        Returns:
            List of ExpirationAlert objects for positions nearing expiry

        Note:
            This method is safe to call repeatedly. Alert deduplication is
            handled by the AlertService (PERMANENT_PER_THRESHOLD strategy).
        """
        logger.info(
            "Running expiration check (warning_days=%d)",
            self._warning_days,
        )

        try:
            # Get session - handle both context manager and direct callable
            session = self._session_factory()

            # Check if it's an async context manager
            if hasattr(session, "__aenter__"):
                async with session as sess:
                    return await self._run_check_with_session(sess)
            else:
                # Direct session (for testing)
                return await self._run_check_with_session(session)

        except Exception as e:
            logger.exception("Expiration check failed: %s", e)
            raise

    async def _run_check_with_session(self, session: AsyncSession) -> list[ExpirationAlert]:
        """Run expiration check with the provided session.

        Args:
            session: Database session for queries

        Returns:
            List of ExpirationAlert objects
        """
        manager = ExpirationManager(
            session=session,
            warning_days=self._warning_days,
        )

        alerts = await manager.check_expirations()

        logger.info(
            "Expiration check complete: %d positions expiring within %d days",
            len(alerts),
            self._warning_days,
        )

        # Process each alert
        for expiration_alert in alerts:
            await self._process_alert(expiration_alert)

        return alerts

    async def _process_alert(self, expiration_alert: ExpirationAlert) -> None:
        """Process a single expiration alert.

        If AlertService is configured, emits an OPTION_EXPIRING alert.
        Otherwise, logs the expiration warning.

        Args:
            expiration_alert: ExpirationAlert from ExpirationManager
        """
        # Determine severity based on days to expiry
        # 0-1 days: SEV1 (Critical - immediate action required)
        # 2-3 days: SEV2 (Warning - should investigate)
        # 4+ days: SEV3 (Info - awareness)
        if expiration_alert.days_to_expiry <= 1:
            severity = Severity.SEV1
        elif expiration_alert.days_to_expiry <= 3:
            severity = Severity.SEV2
        else:
            severity = Severity.SEV3

        # Build alert summary
        contract_desc = expiration_alert.contract_type.value
        if expiration_alert.put_call:
            contract_desc = f"{expiration_alert.put_call.value} option"

        summary = (
            f"{expiration_alert.symbol} ({contract_desc}) expires in "
            f"{expiration_alert.days_to_expiry} day(s) on {expiration_alert.expiry}"
        )

        if self._alert_service is not None:
            # Emit alert via AlertService
            try:
                alert_event = create_alert(
                    type=AlertType.OPTION_EXPIRING,
                    severity=severity,
                    summary=summary,
                    symbol=expiration_alert.underlying,
                    details={
                        "position_id": expiration_alert.symbol,  # Using symbol as position_id
                        "contract_symbol": expiration_alert.symbol,
                        "underlying": expiration_alert.underlying,
                        "expiry": expiration_alert.expiry.isoformat(),
                        "days_to_expiry": expiration_alert.days_to_expiry,
                        "threshold_days": self._warning_days,
                        "contract_type": expiration_alert.contract_type.value,
                        "put_call": expiration_alert.put_call.value
                        if expiration_alert.put_call
                        else None,
                        "strike": str(expiration_alert.strike) if expiration_alert.strike else None,
                    },
                )

                success = await self._alert_service.emit(alert_event)
                if success:
                    logger.debug(
                        "Emitted expiration alert for %s",
                        expiration_alert.symbol,
                    )
                else:
                    logger.warning(
                        "Failed to emit expiration alert for %s",
                        expiration_alert.symbol,
                    )

            except Exception as e:
                logger.error(
                    "Error emitting alert for %s: %s",
                    expiration_alert.symbol,
                    e,
                )
        else:
            # Graceful degradation: log the expiration warning
            log_method = {
                Severity.SEV1: logger.critical,
                Severity.SEV2: logger.warning,
                Severity.SEV3: logger.info,
            }.get(severity, logger.info)

            log_method(
                "EXPIRATION WARNING [%s]: %s",
                severity.name,
                summary,
            )
