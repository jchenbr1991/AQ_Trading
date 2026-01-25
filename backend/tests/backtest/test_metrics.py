"""Tests for MetricsCalculator."""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.metrics import MetricsCalculator
from src.backtest.models import Trade


class TestMetricsCalculator:
    """Tests for MetricsCalculator class."""

    def test_total_return(self) -> None:
        """Total return is (final - initial) / initial.

        100k to 110k = 10% return.
        """
        initial_capital = Decimal("100000")
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc), Decimal("105000")),
            (datetime(2024, 1, 3, 16, 0, 0, tzinfo=timezone.utc), Decimal("110000")),
        ]
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        assert metrics["total_return"] == Decimal("0.10")

    def test_annualized_return(self) -> None:
        """Annualized return over 252 trading days.

        With 252 trading days (253 equity points), annualized_return should equal total_return.
        """
        from datetime import timedelta

        initial_capital = Decimal("100000")
        # Create 253 equity points (252 trading days)
        # 10% total return means each day contributes to compounding
        base_date = datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
        equity_curve = [(base_date, Decimal("100000"))]
        # Add 252 more days with final equity = 110000 (10% return)
        for i in range(1, 253):
            equity_curve.append(
                (
                    base_date + timedelta(days=i),
                    Decimal("100000") + (Decimal("10000") * i // 252),
                )
            )
        # Ensure final point is exactly 110000
        equity_curve[-1] = (
            equity_curve[-1][0],
            Decimal("110000"),
        )
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        # With exactly 252 trading days, annualized = (1 + 0.10)^(252/252) - 1 = 0.10
        assert metrics["annualized_return"] == Decimal("0.10")

    def test_sharpe_ratio_with_zero_std(self) -> None:
        """Sharpe ratio is 0 when returns have zero standard deviation (flat curve)."""
        initial_capital = Decimal("100000")
        # All equity values are the same - zero returns
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 3, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
        ]
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        assert metrics["sharpe_ratio"] == Decimal("0")

    def test_sharpe_ratio_with_single_point(self) -> None:
        """Sharpe ratio is 0 with single equity point (no returns to compute)."""
        initial_capital = Decimal("100000")
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
        ]
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        assert metrics["sharpe_ratio"] == Decimal("0")

    def test_max_drawdown(self) -> None:
        """Max drawdown is the largest peak-to-trough decline.

        Peak 110k to trough 99k = 11/110 = 10% drawdown.
        """
        initial_capital = Decimal("100000")
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc), Decimal("110000")),  # peak
            (datetime(2024, 1, 3, 16, 0, 0, tzinfo=timezone.utc), Decimal("105000")),  # drawdown
            (datetime(2024, 1, 4, 16, 0, 0, tzinfo=timezone.utc), Decimal("99000")),  # trough
            (datetime(2024, 1, 5, 16, 0, 0, tzinfo=timezone.utc), Decimal("105000")),  # recovery
        ]
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        # Max drawdown = (110000 - 99000) / 110000 = 11000 / 110000 = 0.10
        assert metrics["max_drawdown"] == Decimal("0.10")

    def test_win_rate_all_winners(self) -> None:
        """Win rate is 1.0 when all sell trades are profitable."""
        initial_capital = Decimal("100000")
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 5, 16, 0, 0, tzinfo=timezone.utc), Decimal("110000")),
        ]
        # Buy at 100, sell at 110 (profit)
        # Buy at 105, sell at 115 (profit)
        trades = [
            _create_buy_trade(quantity=100, fill_price=Decimal("100.00")),
            _create_sell_trade(quantity=100, fill_price=Decimal("110.00")),
            _create_buy_trade(quantity=100, fill_price=Decimal("105.00")),
            _create_sell_trade(quantity=100, fill_price=Decimal("115.00")),
        ]
        # Entry prices for computing PnL on sells
        entry_prices = {"TEST": Decimal("100.00")}

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
            entry_prices=entry_prices,
        )

        assert metrics["win_rate"] == Decimal("1.0")
        assert metrics["total_trades"] == 4

    def test_win_rate_no_trades(self) -> None:
        """Win rate is 0 when there are no trades."""
        initial_capital = Decimal("100000")
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
        ]
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        assert metrics["win_rate"] == Decimal("0")

    def test_avg_trade_pnl_no_trades(self) -> None:
        """Average trade PnL is 0 when there are no trades."""
        initial_capital = Decimal("100000")
        equity_curve = [
            (datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
        ]
        trades: list[Trade] = []

        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=initial_capital,
        )

        assert metrics["avg_trade_pnl"] == Decimal("0")


def _create_buy_trade(
    quantity: int,
    fill_price: Decimal,
    commission: Decimal = Decimal("0"),
) -> Trade:
    """Helper to create a buy Trade for testing."""
    return Trade(
        trade_id="test-trade-buy",
        timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
        symbol="TEST",
        side="buy",
        quantity=quantity,
        gross_price=fill_price,
        slippage=Decimal("0"),
        commission=commission,
        signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
    )


def _create_sell_trade(
    quantity: int,
    fill_price: Decimal,
    commission: Decimal = Decimal("0"),
) -> Trade:
    """Helper to create a sell Trade for testing."""
    return Trade(
        trade_id="test-trade-sell",
        timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
        symbol="TEST",
        side="sell",
        quantity=quantity,
        gross_price=fill_price,
        slippage=Decimal("0"),
        commission=commission,
        signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
    )
