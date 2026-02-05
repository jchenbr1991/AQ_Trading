"""Simulated order execution engine for backtesting."""

from decimal import Decimal
from uuid import uuid4

from src.backtest.models import Bar, Trade
from src.strategies.signals import Signal


class SimulatedFillEngine:
    """Simulates order execution with slippage and commission.

    The fill engine converts trading signals into executed trades by:
    1. Using the next bar's open price as the gross execution price
    2. Applying slippage based on a fixed basis points rate
    3. Calculating commission based on a per-share rate

    Slippage is applied directionally:
    - Buy orders pay more (price + slippage)
    - Sell orders receive less (price - slippage)

    This models the market impact and bid-ask spread costs that occur
    in real trading.

    Attributes:
        _slippage_bps: Slippage in basis points (5 = 0.05%).
        _commission_per_share: Commission charged per share traded.
    """

    def __init__(self, slippage_bps: int, commission_per_share: Decimal) -> None:
        """Initialize the fill engine with execution cost parameters.

        Args:
            slippage_bps: Slippage in basis points. 5 means 0.05% slippage.
            commission_per_share: Commission charged per share traded.
        """
        self._slippage_bps = slippage_bps
        self._commission_per_share = commission_per_share

    def execute(self, signal: Signal, fill_bar: Bar) -> Trade:
        """Create a Trade from a Signal using fill_bar.open.

        The fill price is the bar's open price adjusted for slippage:
        - Buy: fill_price = gross_price * (1 + slippage_bps/10000)
        - Sell: fill_price = gross_price * (1 - slippage_bps/10000)

        Args:
            signal: The trading signal to execute.
            fill_bar: The bar at which to execute (uses open price).

        Returns:
            Trade with unique trade_id (UUID), computed fill_price,
            and commission based on quantity.
        """
        gross_price = fill_bar.open
        slippage_rate = Decimal(self._slippage_bps) / Decimal("10000")
        slippage = gross_price * slippage_rate

        commission = self._commission_per_share * signal.quantity

        return Trade(
            trade_id=str(uuid4()),
            timestamp=fill_bar.timestamp,
            symbol=signal.symbol,
            side=signal.action,
            quantity=signal.quantity,
            gross_price=gross_price,
            slippage=slippage,
            commission=commission,
            signal_bar_timestamp=signal.timestamp,
            entry_factors=dict(signal.factor_scores),  # FR-025: Persist factor scores
        )
