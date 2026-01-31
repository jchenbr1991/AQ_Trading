"""AssignmentHandler service for calculating options assignment/exercise.

This module provides the AssignmentHandler class for calculating what happens
when options expire - specifically ITM/OTM status and resulting stock positions.

Acceptance Criteria:
- FR-018: System handles options assignment/exercise

Usage:
    from src.derivatives.assignment_handler import AssignmentHandler

    handler = AssignmentHandler(session=db_session)

    # Check if option is ITM
    is_itm = handler.calculate_itm_status(option, underlying_price)

    # Estimate assignment result
    estimate = handler.estimate_assignment(option, underlying_price, quantity=1)
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.derivative_contract import DerivativeContract, PutCall

logger = logging.getLogger(__name__)


class AssignmentDirection(str, Enum):
    """Direction of stock position resulting from option exercise.

    BUY: Exercising a call results in buying the underlying stock.
    SELL: Exercising a put results in selling the underlying stock.
    """

    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class AssignmentEstimate:
    """Estimate of the result of option assignment/exercise.

    Attributes:
        option_symbol: The option contract symbol (e.g., AAPL240119C00150000)
        is_itm: Whether the option is in-the-money at the given price
        resulting_shares: Number of shares from exercise (0 if OTM)
        cash_impact: Cash required/received from exercise
                    (negative for buying, positive for selling)
        direction: Direction of the resulting stock position (BUY/SELL)
    """

    option_symbol: str
    is_itm: bool
    resulting_shares: int
    cash_impact: Decimal
    direction: AssignmentDirection


class AssignmentHandler:
    """Service for calculating options assignment and exercise results.

    This service calculates ITM/OTM status for options at expiry and
    estimates the resulting stock positions from exercise/assignment.

    Example:
        handler = AssignmentHandler(session=db_session)

        # Check if a call option is ITM
        option = DerivativeContract(...)
        is_itm = handler.calculate_itm_status(option, Decimal("155.00"))

        # Estimate assignment for 5 contracts
        estimate = handler.estimate_assignment(option, Decimal("155.00"), 5)
        print(f"Would receive {estimate.resulting_shares} shares")
        print(f"Cash impact: ${estimate.cash_impact}")

    ITM Logic:
        - Call option: ITM when underlying_price > strike
        - Put option: ITM when underlying_price < strike
        - ATM (at-the-money) is NOT considered ITM
    """

    def __init__(self, session: AsyncSession, multiplier: int = 100):
        """Initialize AssignmentHandler.

        Args:
            session: SQLAlchemy async session for database access
            multiplier: Number of shares per contract (default: 100)

        Raises:
            ValueError: If multiplier is not positive
        """
        if multiplier <= 0:
            raise ValueError(f"Multiplier must be positive, got {multiplier}")
        self._session = session
        self._multiplier = multiplier

    @property
    def multiplier(self) -> int:
        """Get the configured shares per contract multiplier."""
        return self._multiplier

    def calculate_itm_status(self, option: DerivativeContract, underlying_price: Decimal) -> bool:
        """Calculate whether an option is in-the-money (ITM).

        An option is ITM when exercising it would be profitable:
        - Call: underlying_price > strike (you can buy below market)
        - Put: underlying_price < strike (you can sell above market)

        Args:
            option: The option contract to check
            underlying_price: Current price of the underlying asset

        Returns:
            True if the option is ITM, False otherwise

        Raises:
            ValueError: If option is missing strike or put_call type
        """
        if option.strike is None:
            raise ValueError("Option must have a strike price")
        if option.put_call is None:
            raise ValueError("Option must have a put_call type")

        if option.put_call == PutCall.CALL:
            is_itm = underlying_price > option.strike
        else:  # PutCall.PUT
            is_itm = underlying_price < option.strike

        logger.debug(
            "ITM status for %s (%s @ strike %s): price=%s, ITM=%s",
            option.symbol,
            option.put_call.value,
            option.strike,
            underlying_price,
            is_itm,
        )

        return is_itm

    def estimate_assignment(
        self, option: DerivativeContract, underlying_price: Decimal, quantity: int
    ) -> AssignmentEstimate:
        """Estimate the result of option assignment/exercise.

        Calculates the resulting stock position and cash impact if
        the option is exercised or assigned at expiration.

        For ITM options:
        - Call: Results in buying shares at strike price
        - Put: Results in selling shares at strike price

        For OTM options:
        - Option expires worthless, no shares are exchanged

        Args:
            option: The option contract
            underlying_price: Current price of the underlying asset
            quantity: Number of contracts

        Returns:
            AssignmentEstimate with position and cash details

        Raises:
            ValueError: If option is invalid (missing strike or put_call)
        """
        is_itm = self.calculate_itm_status(option, underlying_price)

        # Determine direction based on option type and position sign
        # Long call or short put -> BUY shares
        # Short call or long put -> SELL shares
        is_long = quantity >= 0
        if option.put_call == PutCall.CALL:
            # Long call: BUY shares, Short call: SELL shares
            direction = AssignmentDirection.BUY if is_long else AssignmentDirection.SELL
        else:
            # Long put: SELL shares, Short put: BUY shares
            direction = AssignmentDirection.SELL if is_long else AssignmentDirection.BUY

        # Calculate resulting position using absolute quantity
        abs_quantity = abs(quantity)
        if is_itm and abs_quantity > 0:
            resulting_shares = abs_quantity * self._multiplier
            # Cash impact: negative for buying, positive for selling
            if direction == AssignmentDirection.BUY:
                cash_impact = -option.strike * resulting_shares
            else:
                cash_impact = option.strike * resulting_shares
        else:
            # OTM or zero quantity - no shares exchanged
            resulting_shares = 0
            cash_impact = Decimal("0.00")

        estimate = AssignmentEstimate(
            option_symbol=option.symbol,
            is_itm=is_itm,
            resulting_shares=resulting_shares,
            cash_impact=cash_impact,
            direction=direction,
        )

        logger.info(
            "Assignment estimate for %s: %d contracts, ITM=%s, shares=%d, cash=%s, direction=%s",
            option.symbol,
            quantity,
            is_itm,
            resulting_shares,
            cash_impact,
            direction.value,
        )

        return estimate
