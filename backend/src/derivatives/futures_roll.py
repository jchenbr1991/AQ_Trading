"""FuturesRollManager service for managing futures contract rollovers.

This module provides the FuturesRollManager class for managing the rolling
of futures positions before expiry.

Acceptance Criteria:
- FR-017: System supports futures auto-roll

Usage:
    from src.derivatives.futures_roll import FuturesRollManager, RollStrategy

    manager = FuturesRollManager(session=db_session, default_days_before=5)

    # Configure per-underlying roll strategy
    manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, days_before=5)
    manager.configure_underlying("CL", RollStrategy.CLOSE_OPEN, days_before=7)

    # Get futures positions that need to be rolled
    positions = await manager.get_positions_to_roll()

    # Generate roll plan for each position
    for position in positions:
        plan = manager.generate_roll_plan(position)
        print(f"{plan.close_action}, {plan.open_action}")
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.derivative_contract import ContractType, DerivativeContract

logger = logging.getLogger(__name__)


class RollStrategy(str, Enum):
    """Strategy for rolling futures positions.

    CALENDAR_SPREAD: Sell current month and buy next month simultaneously.
        This is the most common roll strategy and minimizes market exposure.

    CLOSE_OPEN: Close the current position without opening a new one.
        Used when the trader wants to exit the position entirely.
    """

    CALENDAR_SPREAD = "calendar_spread"
    CLOSE_OPEN = "close_open"


@dataclass(frozen=True)
class RollConfig:
    """Configuration for rolling futures positions for a specific underlying.

    Attributes:
        underlying: The underlying asset symbol (e.g., ES, NQ, CL)
        strategy: The roll strategy to use (CALENDAR_SPREAD or CLOSE_OPEN)
        days_before_expiry: Number of days before expiry to initiate the roll
    """

    underlying: str
    strategy: RollStrategy
    days_before_expiry: int


@dataclass(frozen=True)
class RollPlan:
    """Plan for rolling a futures position.

    This dataclass contains the instructions for rolling a futures position
    but does NOT execute any trades.

    Attributes:
        symbol: The current position symbol (e.g., ESH24)
        strategy: The roll strategy being applied
        close_action: Description of the close action (e.g., "SELL ESH24 to close")
        open_action: Description of the open action for calendar spreads,
                    None for CLOSE_OPEN strategy
    """

    symbol: str
    strategy: RollStrategy
    close_action: str
    open_action: str | None


class FuturesRollManager:
    """Service for managing futures contract rollovers.

    This service identifies futures positions nearing expiry and generates
    roll plans based on configurable strategies. It does NOT execute trades,
    only generates plans.

    Roll Strategies:
        - CALENDAR_SPREAD: Sell current month, buy next month simultaneously
        - CLOSE_OPEN: Close position without opening new one

    Example:
        manager = FuturesRollManager(session=db_session, default_days_before=5)

        # Configure different strategies per underlying
        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)
        manager.configure_underlying("CL", RollStrategy.CLOSE_OPEN, 7)

        # Get positions to roll and generate plans
        positions = await manager.get_positions_to_roll()
        for position in positions:
            plan = manager.generate_roll_plan(position)
            logger.info(f"Roll plan: {plan.close_action}")
    """

    def __init__(
        self,
        session: AsyncSession,
        default_days_before: int = 5,
        default_strategy: RollStrategy = RollStrategy.CALENDAR_SPREAD,
    ):
        """Initialize FuturesRollManager.

        Args:
            session: SQLAlchemy async session for database access
            default_days_before: Default number of days before expiry to roll
                                (default: 5)
            default_strategy: Default roll strategy for unconfigured underlyings
                             (default: CALENDAR_SPREAD)

        Raises:
            ValueError: If default_days_before is negative
        """
        if default_days_before < 0:
            raise ValueError(f"days_before must be non-negative, got {default_days_before}")
        self._session = session
        self._default_days_before = default_days_before
        self._default_strategy = default_strategy
        self._underlying_configs: dict[str, RollConfig] = {}

    @property
    def default_days_before(self) -> int:
        """Get the default days before expiry threshold."""
        return self._default_days_before

    @property
    def default_strategy(self) -> RollStrategy:
        """Get the default roll strategy."""
        return self._default_strategy

    def configure_underlying(
        self,
        underlying: str,
        strategy: RollStrategy,
        days_before: int,
    ) -> None:
        """Configure roll strategy for a specific underlying.

        Args:
            underlying: The underlying asset symbol (e.g., ES, NQ, CL)
            strategy: The roll strategy to use
            days_before: Number of days before expiry to initiate roll

        Raises:
            ValueError: If days_before is negative
        """
        if days_before < 0:
            raise ValueError(f"days_before must be non-negative, got {days_before}")

        config = RollConfig(
            underlying=underlying,
            strategy=strategy,
            days_before_expiry=days_before,
        )
        self._underlying_configs[underlying] = config

        logger.info(
            "Configured roll strategy for %s: %s, %d days before expiry",
            underlying,
            strategy.value,
            days_before,
        )

    def get_config(self, underlying: str) -> RollConfig:
        """Get roll configuration for an underlying.

        Returns the configured settings if available, otherwise returns
        a config with default values.

        Args:
            underlying: The underlying asset symbol

        Returns:
            RollConfig with the roll settings for the underlying
        """
        if underlying in self._underlying_configs:
            return self._underlying_configs[underlying]

        # Return default config
        return RollConfig(
            underlying=underlying,
            strategy=self._default_strategy,
            days_before_expiry=self._default_days_before,
        )

    async def get_positions_to_roll(self, days: int | None = None) -> list[DerivativeContract]:
        """Query futures positions expiring within N days.

        Args:
            days: Number of days to look ahead (default: default_days_before)

        Returns:
            List of DerivativeContract objects for futures expiring within window

        Raises:
            ValueError: If days is negative
        """
        lookup_days = days if days is not None else self._default_days_before
        if lookup_days < 0:
            raise ValueError(f"days must be non-negative, got {lookup_days}")

        today = date.today()
        cutoff_date = today + timedelta(days=lookup_days)

        logger.debug(
            "Querying futures positions expiring between %s and %s (within %d days)",
            today,
            cutoff_date,
            lookup_days,
        )

        # Query only futures contracts expiring within the window
        stmt = (
            select(DerivativeContract)
            .where(
                DerivativeContract.contract_type == ContractType.FUTURE,
                DerivativeContract.expiry >= today,
                DerivativeContract.expiry <= cutoff_date,
            )
            .order_by(DerivativeContract.expiry)
        )

        result = await self._session.execute(stmt)
        positions = result.scalars().all()

        logger.info(
            "Found %d futures positions to roll within %d days",
            len(positions),
            lookup_days,
        )

        return list(positions)

    def generate_roll_plan(self, position: DerivativeContract) -> RollPlan:
        """Generate a roll plan for a futures position.

        Creates instructions for rolling the position based on the configured
        strategy for the underlying. Does NOT execute any trades.

        Args:
            position: The futures contract to roll

        Returns:
            RollPlan with close and optional open instructions

        Raises:
            ValueError: If position is not a futures contract
        """
        if position.contract_type != ContractType.FUTURE:
            raise ValueError(
                f"Only futures contracts can be rolled, got {position.contract_type.value}"
            )

        config = self.get_config(position.underlying)

        # Generate close action
        close_action = f"SELL {position.symbol} to close"

        # Generate open action based on strategy
        if config.strategy == RollStrategy.CALENDAR_SPREAD:
            # For calendar spread, generate a placeholder for next month contract
            # In a real system, this would compute the next contract month
            next_contract = self._get_next_contract_symbol(position)
            open_action = f"BUY {next_contract} to open"
        else:
            # CLOSE_OPEN strategy - no new position
            open_action = None

        plan = RollPlan(
            symbol=position.symbol,
            strategy=config.strategy,
            close_action=close_action,
            open_action=open_action,
        )

        logger.info(
            "Generated roll plan for %s: strategy=%s, close=%s, open=%s",
            position.symbol,
            config.strategy.value,
            close_action,
            open_action,
        )

        return plan

    def _get_next_contract_symbol(self, position: DerivativeContract) -> str:
        """Compute the next contract month symbol.

        This is a simplified implementation that generates a placeholder
        for the next contract. In a production system, this would need
        to handle specific futures contract naming conventions.

        Futures typically use month codes:
        - F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun
        - N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec

        Args:
            position: The current futures contract

        Returns:
            Symbol for the next contract month
        """
        # Month codes for futures contracts
        month_codes = ["F", "G", "H", "J", "K", "M", "N", "Q", "U", "V", "X", "Z"]

        symbol = position.symbol
        underlying = position.underlying

        # Try to find and increment the month code
        for i, code in enumerate(month_codes):
            if code in symbol:
                next_month_idx = (i + 1) % 12
                next_code = month_codes[next_month_idx]
                # Simple replacement - may need year rollover logic in production
                next_symbol = symbol.replace(code, next_code, 1)
                return next_symbol

        # Fallback: append "_NEXT" to symbol
        return f"{underlying}_NEXT"
