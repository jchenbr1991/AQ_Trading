"""ExpirationManager service for monitoring derivative expirations.

This module provides the ExpirationManager class for monitoring derivative
contract expirations and emitting alerts when positions are nearing expiry.

Acceptance Criteria:
- SC-011: User receives expiration warning at least 5 days before expiry
- FR-016: System tracks derivative expiry dates

Usage:
    from src.derivatives.expiration_manager import ExpirationManager

    manager = ExpirationManager(session=db_session, warning_days=5)

    # Get positions expiring within the warning window
    positions = await manager.get_expiring_positions()

    # Check expirations and get alerts
    alerts = await manager.check_expirations()
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.derivative_contract import ContractType, DerivativeContract, PutCall

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpirationAlert:
    """Alert for a derivative contract nearing expiration.

    Attributes:
        symbol: The derivative contract symbol (e.g., AAPL240119C00150000)
        underlying: The underlying asset symbol (e.g., AAPL)
        expiry: The expiration date
        days_to_expiry: Number of days until expiration
        contract_type: Type of contract (option or future)
        put_call: For options, whether it's a put or call (None for futures)
        strike: For options, the strike price (None for futures)
    """

    symbol: str
    underlying: str
    expiry: date
    days_to_expiry: int
    contract_type: ContractType
    put_call: PutCall | None
    strike: Decimal | None


class ExpirationManager:
    """Service for monitoring derivative contract expirations.

    This service queries derivative positions and identifies those nearing
    expiration, generating alerts for positions within the warning window.

    Example:
        manager = ExpirationManager(session=db_session, warning_days=5)

        # Daily check for expiring positions
        alerts = await manager.check_expirations()
        for alert in alerts:
            logger.warning(
                "Position %s expires in %d days",
                alert.symbol,
                alert.days_to_expiry
            )
    """

    def __init__(self, session: AsyncSession, warning_days: int = 5):
        """Initialize ExpirationManager.

        Args:
            session: SQLAlchemy async session for database access
            warning_days: Number of days before expiry to start warning
                         (default: 5, per SC-011)

        Raises:
            ValueError: If warning_days is negative
        """
        if warning_days < 0:
            raise ValueError(f"warning_days must be non-negative, got {warning_days}")
        self._session = session
        self._warning_days = warning_days

    @property
    def warning_days(self) -> int:
        """Get the configured warning days threshold."""
        return self._warning_days

    async def get_expiring_positions(self, days: int | None = None) -> list[DerivativeContract]:
        """Query derivative positions expiring within N days.

        Args:
            days: Number of days to look ahead (default: warning_days)

        Returns:
            List of DerivativeContract objects expiring within the window

        Raises:
            ValueError: If days is negative
        """
        lookup_days = days if days is not None else self._warning_days
        if lookup_days < 0:
            raise ValueError(f"days must be non-negative, got {lookup_days}")
        today = date.today()
        cutoff_date = today + timedelta(days=lookup_days)

        logger.debug(
            "Querying positions expiring between %s and %s (within %d days)",
            today,
            cutoff_date,
            lookup_days,
        )

        # Query contracts expiring within the window (inclusive of cutoff)
        stmt = (
            select(DerivativeContract)
            .where(
                DerivativeContract.expiry >= today,
                DerivativeContract.expiry <= cutoff_date,
            )
            .order_by(DerivativeContract.expiry)
        )

        result = await self._session.execute(stmt)
        positions = result.scalars().all()

        logger.info(
            "Found %d positions expiring within %d days",
            len(positions),
            lookup_days,
        )

        return list(positions)

    async def check_expirations(self) -> list[ExpirationAlert]:
        """Run expiration check and return alerts for positions within warning window.

        This method queries all positions expiring within the configured
        warning_days and generates an ExpirationAlert for each.

        Returns:
            List of ExpirationAlert objects for positions nearing expiry
        """
        positions = await self.get_expiring_positions()
        today = date.today()

        alerts = []
        for position in positions:
            days_to_expiry = (position.expiry - today).days

            alert = ExpirationAlert(
                symbol=position.symbol,
                underlying=position.underlying,
                expiry=position.expiry,
                days_to_expiry=days_to_expiry,
                contract_type=position.contract_type,
                put_call=position.put_call,
                strike=position.strike,
            )
            alerts.append(alert)

            # Use str() for contract_type since DB may return string instead of enum
            contract_type_str = (
                position.contract_type.value
                if hasattr(position.contract_type, "value")
                else str(position.contract_type)
            )
            logger.info(
                "Expiration alert: %s (%s) expires in %d days on %s",
                position.symbol,
                contract_type_str,
                days_to_expiry,
                position.expiry,
            )

        return alerts
