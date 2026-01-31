"""Limits Store for dynamic Greeks limits management.

V2 Feature: PUT /limits (Section 4 of V2 Design)

Provides in-memory storage for Greeks limits with:
- Default limits if not set
- Validation before storage
- Strategy-level limits (V2: 501 Not Implemented)

Future enhancements:
- Redis persistence for hot config
- Database persistence for audit history
- AlertEngine.reload_limits() integration
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.greeks.v2_models import (
    GreeksLimitSet,
    GreeksLimitsResponse,
    ThresholdLevels,
)


class NotImplementedError(Exception):
    """Raised when a feature is not yet implemented."""

    pass


def _default_limit_set() -> GreeksLimitSet:
    """Create default limits.

    Default values from V2 design doc section 2.4.
    """
    return GreeksLimitSet(
        dollar_delta=ThresholdLevels(
            warn=Decimal("100000"),
            crit=Decimal("150000"),
            hard=Decimal("200000"),
        ),
        gamma_dollar=ThresholdLevels(
            warn=Decimal("5000"),
            crit=Decimal("7500"),
            hard=Decimal("10000"),
        ),
        vega_per_1pct=ThresholdLevels(
            warn=Decimal("20000"),
            crit=Decimal("30000"),
            hard=Decimal("40000"),
        ),
        theta_per_day=ThresholdLevels(
            warn=Decimal("3000"),
            crit=Decimal("4500"),
            hard=Decimal("6000"),
        ),
    )


class LimitsStore:
    """In-memory store for Greeks limits.

    Stores account-level limits with validation and default fallback.

    Attributes:
        _limits: Dict mapping account_id to GreeksLimitSet
        _metadata: Dict mapping account_id to (updated_at, updated_by)
    """

    def __init__(self):
        """Initialize empty store."""
        self._limits: dict[str, GreeksLimitSet] = {}
        self._metadata: dict[str, tuple[datetime, str]] = {}

    async def get_limits(self, account_id: str) -> GreeksLimitSet:
        """Get limits for an account.

        Args:
            account_id: Account identifier.

        Returns:
            GreeksLimitSet for the account, or defaults if not set.
        """
        if account_id in self._limits:
            return self._limits[account_id]
        return _default_limit_set()

    async def set_limits(
        self,
        account_id: str,
        limits: GreeksLimitSet,
        updated_by: str,
        strategy_id: str | None = None,
    ) -> GreeksLimitsResponse:
        """Set limits for an account.

        Args:
            account_id: Account identifier.
            limits: New limit set.
            updated_by: User making the update.
            strategy_id: Strategy ID (V2: raises NotImplementedError).

        Returns:
            GreeksLimitsResponse with applied limits.

        Raises:
            NotImplementedError: If strategy_id is provided.
            ValueError: If limits fail validation.
        """
        # V2: Strategy-level limits not implemented
        if strategy_id is not None:
            raise NotImplementedError("Strategy-level limits not implemented in V2")

        # Validate limits
        errors = limits.validate()
        if errors:
            raise ValueError(f"Invalid limits: {'; '.join(errors)}")

        # Store limits
        self._limits[account_id] = limits
        now = datetime.now(timezone.utc)
        self._metadata[account_id] = (now, updated_by)

        return GreeksLimitsResponse(
            account_id=account_id,
            strategy_id=None,
            limits=limits,
            updated_at=now,
            updated_by=updated_by,
            effective_scope="ACCOUNT",
        )


# Global singleton instance
_limits_store: LimitsStore | None = None


def get_limits_store() -> LimitsStore:
    """Get the global LimitsStore instance."""
    global _limits_store
    if _limits_store is None:
        _limits_store = LimitsStore()
    return _limits_store
