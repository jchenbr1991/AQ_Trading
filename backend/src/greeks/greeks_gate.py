"""Greeks Gate for pre-order limit checking.

This module provides the GreeksGate class for checking whether an order
would breach Greeks limits before execution.

V2 Feature: Pre-order Greeks Check (Section 2 of V2 Design)

Key behaviors:
- Fail-closed by default (block if data unavailable or stale)
- Uses abs() for limit comparisons
- Returns structured GreeksCheckResult for audit
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from src.greeks.models import AggregatedGreeks
from src.greeks.v2_models import (
    GreeksCheckConfig,
    GreeksCheckDetails,
    GreeksCheckResult,
    OrderIntent,
)

logger = logging.getLogger(__name__)

# V1 canonical field names for Greeks
GREEKS_FIELDS = ["dollar_delta", "gamma_dollar", "vega_per_1pct", "theta_per_day"]


class GreeksMonitorProtocol(Protocol):
    """Protocol for GreeksMonitor dependency."""

    def get_current_greeks(self) -> AggregatedGreeks | None:
        """Get the most recent calculated Greeks."""
        ...


class GreeksCalculatorProtocol(Protocol):
    """Protocol for Greeks impact calculator."""

    async def calculate_order_impact(self, order: OrderIntent) -> dict[str, Decimal]:
        """Calculate Greeks impact of an order.

        Args:
            order: The order intent with legs.

        Returns:
            Dict with Greeks field names and their impact values.
        """
        ...


class GreeksGate:
    """Pre-order Greeks limit checker.

    Checks whether a proposed order would breach Greeks limits.
    Uses fail-closed by default: blocks order if Greeks data is
    unavailable or stale.

    Attributes:
        _greeks_monitor: Monitor for current Greeks
        _greeks_calculator: Calculator for order impact
        _config: Check configuration including limits
    """

    def __init__(
        self,
        greeks_monitor: GreeksMonitorProtocol,
        greeks_calculator: GreeksCalculatorProtocol,
        config: GreeksCheckConfig | None = None,
    ):
        """Initialize the GreeksGate.

        Args:
            greeks_monitor: GreeksMonitor instance for current Greeks
            greeks_calculator: Calculator for order impact
            config: Optional configuration (uses defaults if not provided)
        """
        self._greeks_monitor = greeks_monitor
        self._greeks_calculator = greeks_calculator
        self._config = config or GreeksCheckConfig()

    async def check_order(self, order: OrderIntent) -> GreeksCheckResult:
        """Check if an order would breach Greeks limits.

        Args:
            order: The order intent to check.

        Returns:
            GreeksCheckResult with approval status and details.
        """
        # Step 1: Get current Greeks
        current_greeks = self._greeks_monitor.get_current_greeks()

        if current_greeks is None:
            return self._handle_data_unavailable()

        # Step 2: Check staleness
        now = datetime.now(timezone.utc)
        staleness = (now - current_greeks.as_of_ts).total_seconds()

        if staleness > self._config.max_staleness_seconds:
            return self._handle_data_stale(staleness)

        # Step 3: Calculate order impact
        impact = await self._greeks_calculator.calculate_order_impact(order)

        # Step 4: Calculate projected Greeks (current + impact)
        current_dict = self._greeks_to_dict(current_greeks)
        projected = {}
        for field in GREEKS_FIELDS:
            current_val = current_dict.get(field, Decimal("0"))
            impact_val = impact.get(field, Decimal("0"))
            projected[field] = current_val + impact_val

        # Step 5: Check for breaches using abs() comparison
        breach_dims = []
        for field in GREEKS_FIELDS:
            if field not in self._config.hard_limits:
                continue
            limit = self._config.hard_limits[field]
            if abs(projected[field]) > limit:
                breach_dims.append(field)

        # Build result
        details = GreeksCheckDetails(
            asof_ts=current_greeks.as_of_ts,
            staleness_seconds=int(staleness),
            current=current_dict,
            impact=impact,
            projected=projected,
            limits=self._config.hard_limits,
            breach_dims=breach_dims,
        )

        if breach_dims:
            logger.warning(f"[RISK_BLOCK] Order breaches Greeks limits: {breach_dims}")
            return GreeksCheckResult(
                ok=False,
                reason_code="HARD_BREACH",
                details=details,
            )

        return GreeksCheckResult(
            ok=True,
            reason_code="APPROVED",
            details=details,
        )

    def _greeks_to_dict(self, greeks: AggregatedGreeks) -> dict[str, Decimal]:
        """Convert AggregatedGreeks to dict with V1 field names."""
        return {
            "dollar_delta": greeks.dollar_delta,
            "gamma_dollar": greeks.gamma_dollar,
            "vega_per_1pct": greeks.vega_per_1pct,
            "theta_per_day": greeks.theta_per_day,
        }

    def _handle_data_unavailable(self) -> GreeksCheckResult:
        """Handle case when Greeks data is unavailable."""
        if self._config.fail_mode == "open":
            logger.warning("[RISK_WARN] Greeks data unavailable, fail-open allows order")
            return GreeksCheckResult(
                ok=True,
                reason_code="APPROVED",
                details=None,
            )

        logger.critical("[RISK_BLOCK] Greeks data unavailable")
        return GreeksCheckResult(
            ok=False,
            reason_code="DATA_UNAVAILABLE",
            details=None,
        )

    def _handle_data_stale(self, staleness: float) -> GreeksCheckResult:
        """Handle case when Greeks data is stale."""
        if self._config.fail_mode == "open":
            logger.warning(f"[RISK_WARN] Greeks stale ({staleness}s), fail-open allows order")
            return GreeksCheckResult(
                ok=True,
                reason_code="APPROVED",
                details=None,
            )

        logger.warning(f"[RISK_BLOCK] Greeks stale: {staleness}s")
        return GreeksCheckResult(
            ok=False,
            reason_code="DATA_STALE",
            details=None,
        )
