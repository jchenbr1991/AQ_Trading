"""Tests for BacktestPortfolio."""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.models import Trade
from src.backtest.portfolio import BacktestPortfolio


class TestBacktestPortfolio:
    """Tests for BacktestPortfolio class."""

    def test_initial_state(self) -> None:
        """Verify portfolio initializes with correct values."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        assert portfolio.cash == Decimal("100000")
        assert portfolio.position_qty == 0
        assert portfolio.position_avg_cost == Decimal("0")

    def test_equity_no_position(self) -> None:
        """Equity equals cash when no position is held."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("50000"))

        # With no position, equity = cash regardless of price
        assert portfolio.equity(current_price=Decimal("100.00")) == Decimal("50000")
        assert portfolio.equity(current_price=Decimal("200.00")) == Decimal("50000")

    def test_equity_with_position(self) -> None:
        """Equity = cash + position_qty * current_price."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        # Apply a buy trade to establish position
        trade = _create_buy_trade(
            quantity=100,
            fill_price=Decimal("150.00"),
            commission=Decimal("1.00"),
        )
        portfolio.apply_trade(trade)

        # Cash = 100000 - (150 * 100 + 1) = 100000 - 15001 = 84999
        assert portfolio.cash == Decimal("84999")
        assert portfolio.position_qty == 100

        # Equity at different prices
        # At $150: 84999 + 100 * 150 = 84999 + 15000 = 99999
        assert portfolio.equity(current_price=Decimal("150.00")) == Decimal("99999")

        # At $160: 84999 + 100 * 160 = 84999 + 16000 = 100999
        assert portfolio.equity(current_price=Decimal("160.00")) == Decimal("100999")

        # At $140: 84999 + 100 * 140 = 84999 + 14000 = 98999
        assert portfolio.equity(current_price=Decimal("140.00")) == Decimal("98999")

    def test_can_buy_sufficient_cash(self) -> None:
        """can_buy returns True when cash covers cost + commission."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("10000"))

        # Total cost = 100 * 50 + 5 = 5005, have 10000 -> True
        assert (
            portfolio.can_buy(
                price=Decimal("50.00"),
                quantity=100,
                commission=Decimal("5.00"),
            )
            is True
        )

        # Exact amount: 100 * 100 + 0 = 10000, have 10000 -> True
        assert (
            portfolio.can_buy(
                price=Decimal("100.00"),
                quantity=100,
                commission=Decimal("0"),
            )
            is True
        )

    def test_can_buy_insufficient_cash(self) -> None:
        """can_buy returns False when cash is not enough."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("10000"))

        # Total cost = 100 * 101 + 0 = 10100, have 10000 -> False
        assert (
            portfolio.can_buy(
                price=Decimal("101.00"),
                quantity=100,
                commission=Decimal("0"),
            )
            is False
        )

        # Total cost = 100 * 100 + 1 = 10001, have 10000 -> False
        assert (
            portfolio.can_buy(
                price=Decimal("100.00"),
                quantity=100,
                commission=Decimal("1.00"),
            )
            is False
        )

    def test_can_sell_with_position(self) -> None:
        """can_sell returns True when position_qty >= quantity."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        # Apply buy to establish position of 100 shares
        trade = _create_buy_trade(
            quantity=100,
            fill_price=Decimal("100.00"),
            commission=Decimal("0"),
        )
        portfolio.apply_trade(trade)

        assert portfolio.can_sell(quantity=100) is True  # exact amount
        assert portfolio.can_sell(quantity=50) is True  # partial
        assert portfolio.can_sell(quantity=1) is True  # single share

    def test_can_sell_no_position(self) -> None:
        """can_sell returns False when no position or insufficient shares."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        # No position at all
        assert portfolio.can_sell(quantity=1) is False
        assert portfolio.can_sell(quantity=100) is False

        # Establish position of 50 shares
        trade = _create_buy_trade(
            quantity=50,
            fill_price=Decimal("100.00"),
            commission=Decimal("0"),
        )
        portfolio.apply_trade(trade)

        # Can't sell more than we have
        assert portfolio.can_sell(quantity=51) is False
        assert portfolio.can_sell(quantity=100) is False

    def test_apply_buy_trade(self) -> None:
        """Buy trade decreases cash and increases position."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        trade = _create_buy_trade(
            quantity=100,
            fill_price=Decimal("150.00"),
            commission=Decimal("10.00"),
        )
        portfolio.apply_trade(trade)

        # Cash = 100000 - (150 * 100 + 10) = 100000 - 15010 = 84990
        assert portfolio.cash == Decimal("84990")
        assert portfolio.position_qty == 100
        assert portfolio.position_avg_cost == Decimal("150.00")

    def test_apply_sell_trade(self) -> None:
        """Sell trade increases cash and decreases position."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        # First buy 100 shares at $150
        buy_trade = _create_buy_trade(
            quantity=100,
            fill_price=Decimal("150.00"),
            commission=Decimal("0"),
        )
        portfolio.apply_trade(buy_trade)

        # Cash after buy = 100000 - 15000 = 85000
        assert portfolio.cash == Decimal("85000")
        assert portfolio.position_qty == 100

        # Now sell 50 shares at $160
        sell_trade = _create_sell_trade(
            quantity=50,
            fill_price=Decimal("160.00"),
            commission=Decimal("5.00"),
        )
        portfolio.apply_trade(sell_trade)

        # Cash = 85000 + (160 * 50 - 5) = 85000 + 7995 = 92995
        assert portfolio.cash == Decimal("92995")
        assert portfolio.position_qty == 50
        # Average cost unchanged after sell
        assert portfolio.position_avg_cost == Decimal("150.00")

    def test_apply_additional_buy_updates_avg_cost(self) -> None:
        """Multiple buys update average cost using volume-weighted average."""
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))

        # Buy 100 shares at $100
        trade1 = _create_buy_trade(
            quantity=100,
            fill_price=Decimal("100.00"),
            commission=Decimal("0"),
        )
        portfolio.apply_trade(trade1)

        assert portfolio.position_qty == 100
        assert portfolio.position_avg_cost == Decimal("100.00")

        # Buy 100 more shares at $120
        trade2 = _create_buy_trade(
            quantity=100,
            fill_price=Decimal("120.00"),
            commission=Decimal("0"),
        )
        portfolio.apply_trade(trade2)

        # New avg cost = (100 * 100 + 100 * 120) / 200 = 22000 / 200 = 110
        assert portfolio.position_qty == 200
        assert portfolio.position_avg_cost == Decimal("110.00")

        # Buy 50 shares at $130
        trade3 = _create_buy_trade(
            quantity=50,
            fill_price=Decimal("130.00"),
            commission=Decimal("0"),
        )
        portfolio.apply_trade(trade3)

        # New avg cost = (200 * 110 + 50 * 130) / 250 = (22000 + 6500) / 250 = 28500 / 250 = 114
        assert portfolio.position_qty == 250
        assert portfolio.position_avg_cost == Decimal("114.00")


def _create_buy_trade(
    quantity: int,
    fill_price: Decimal,
    commission: Decimal,
) -> Trade:
    """Helper to create a buy Trade for testing."""
    # To get the desired fill_price, we need to set gross_price and slippage
    # For buy: fill_price = gross_price + slippage
    # We'll use zero slippage for simplicity in tests
    return Trade(
        trade_id="test-trade-buy",
        timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
        symbol="TEST",
        side="buy",
        quantity=quantity,
        gross_price=fill_price,  # slippage is 0, so fill_price = gross_price
        slippage=Decimal("0"),
        commission=commission,
        signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
    )


def _create_sell_trade(
    quantity: int,
    fill_price: Decimal,
    commission: Decimal,
) -> Trade:
    """Helper to create a sell Trade for testing."""
    # For sell: fill_price = gross_price - slippage
    # We'll use zero slippage for simplicity in tests
    return Trade(
        trade_id="test-trade-sell",
        timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
        symbol="TEST",
        side="sell",
        quantity=quantity,
        gross_price=fill_price,  # slippage is 0, so fill_price = gross_price
        slippage=Decimal("0"),
        commission=commission,
        signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
    )
