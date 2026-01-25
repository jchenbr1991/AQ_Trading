"""Backtest portfolio tracking."""

from decimal import Decimal

from src.backtest.models import Trade


class BacktestPortfolio:
    """Tracks cash, position, and equity during backtest.

    Constraints (long-only, no leverage):
    - position_qty >= 0 (no shorting)
    - cash >= 0 (no leverage)
    - sell quantity <= position_qty
    """

    def __init__(self, initial_capital: Decimal) -> None:
        """Initialize portfolio with starting capital.

        Args:
            initial_capital: Starting cash amount for the portfolio.
        """
        self._cash: Decimal = initial_capital
        self._position_qty: int = 0
        self._position_avg_cost: Decimal = Decimal("0")

    @property
    def cash(self) -> Decimal:
        """Current cash balance."""
        return self._cash

    @property
    def position_qty(self) -> int:
        """Number of shares currently held."""
        return self._position_qty

    @property
    def position_avg_cost(self) -> Decimal:
        """Volume-weighted average cost per share of current position."""
        return self._position_avg_cost

    def equity(self, current_price: Decimal) -> Decimal:
        """Total portfolio value: cash + position * current_price.

        Args:
            current_price: Current market price per share.

        Returns:
            Total portfolio value at the given price.
        """
        return self._cash + Decimal(self._position_qty) * current_price

    def can_buy(self, price: Decimal, quantity: int, commission: Decimal) -> bool:
        """Check if sufficient cash for purchase.

        Args:
            price: Price per share.
            quantity: Number of shares to buy.
            commission: Total commission for the trade.

        Returns:
            True if cash covers (price * quantity + commission), False otherwise.
        """
        total_cost = price * Decimal(quantity) + commission
        return self._cash >= total_cost

    def can_sell(self, quantity: int) -> bool:
        """Check if sufficient position to sell.

        Args:
            quantity: Number of shares to sell.

        Returns:
            True if position_qty >= quantity, False otherwise.
        """
        return self._position_qty >= quantity

    def apply_trade(self, trade: Trade) -> None:
        """Update cash and position based on trade.

        Buy: cash -= (fill_price * qty + commission), position += qty
        Sell: cash += (fill_price * qty - commission), position -= qty

        Updates average cost on buys using volume-weighted average.

        Args:
            trade: The executed trade to apply.
        """
        if trade.side == "buy":
            self._apply_buy(trade)
        else:
            self._apply_sell(trade)

    def _apply_buy(self, trade: Trade) -> None:
        """Apply a buy trade to the portfolio.

        Updates cash, position quantity, and average cost.
        """
        trade_value = trade.fill_price * Decimal(trade.quantity)
        total_cost = trade_value + trade.commission

        # Update average cost using volume-weighted average
        if self._position_qty == 0:
            self._position_avg_cost = trade.fill_price
        else:
            total_value = (
                Decimal(self._position_qty) * self._position_avg_cost
                + Decimal(trade.quantity) * trade.fill_price
            )
            new_qty = self._position_qty + trade.quantity
            self._position_avg_cost = total_value / Decimal(new_qty)

        self._cash -= total_cost
        self._position_qty += trade.quantity

    def _apply_sell(self, trade: Trade) -> None:
        """Apply a sell trade to the portfolio.

        Updates cash and position quantity. Average cost is unchanged.
        """
        trade_value = trade.fill_price * Decimal(trade.quantity)
        net_proceeds = trade_value - trade.commission

        self._cash += net_proceeds
        self._position_qty -= trade.quantity
