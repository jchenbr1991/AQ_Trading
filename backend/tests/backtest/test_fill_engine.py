"""Tests for SimulatedFillEngine."""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.models import Bar
from src.strategies.signals import Signal


class TestSimulatedFillEngine:
    """Tests for SimulatedFillEngine order execution simulation."""

    def test_execute_buy_with_slippage(self) -> None:
        """Buy at 150.00 with 5bps slippage results in fill_price 150.075."""
        engine = SimulatedFillEngine(
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )

        signal = Signal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action="buy",
            quantity=100,
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.00"),
            volume=1_000_000,
        )

        trade = engine.execute(signal, fill_bar)

        # Verify trade fields
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 100
        assert trade.gross_price == Decimal("150.00")
        # Slippage: 150.00 * 5/10000 = 0.075
        assert trade.slippage == Decimal("0.075")
        # Buy: fill_price = gross + slippage
        assert trade.fill_price == Decimal("150.075")
        # Commission: 100 shares * 0.005 = 0.50
        assert trade.commission == Decimal("0.500")
        assert trade.timestamp == fill_bar.timestamp
        assert trade.signal_bar_timestamp == signal.timestamp

    def test_execute_sell_with_slippage(self) -> None:
        """Sell at 155.00 with 5bps slippage results in fill_price 154.9225."""
        engine = SimulatedFillEngine(
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )

        signal = Signal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action="sell",
            quantity=50,
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("155.00"),
            high=Decimal("157.00"),
            low=Decimal("154.00"),
            close=Decimal("156.00"),
            volume=1_000_000,
        )

        trade = engine.execute(signal, fill_bar)

        # Verify trade fields
        assert trade.symbol == "AAPL"
        assert trade.side == "sell"
        assert trade.quantity == 50
        assert trade.gross_price == Decimal("155.00")
        # Slippage: 155.00 * 5/10000 = 0.0775
        assert trade.slippage == Decimal("0.0775")
        # Sell: fill_price = gross - slippage
        assert trade.fill_price == Decimal("154.9225")
        # Commission: 50 shares * 0.005 = 0.25
        assert trade.commission == Decimal("0.250")
        assert trade.timestamp == fill_bar.timestamp
        assert trade.signal_bar_timestamp == signal.timestamp

    def test_execute_with_zero_slippage(self) -> None:
        """With zero slippage, fill_price equals gross_price."""
        engine = SimulatedFillEngine(
            slippage_bps=0,
            commission_per_share=Decimal("0.01"),
        )

        signal = Signal(
            strategy_id="test_strategy",
            symbol="MSFT",
            action="buy",
            quantity=200,
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        fill_bar = Bar(
            symbol="MSFT",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("400.00"),
            high=Decimal("405.00"),
            low=Decimal("398.00"),
            close=Decimal("403.00"),
            volume=2_000_000,
        )

        trade = engine.execute(signal, fill_bar)

        assert trade.gross_price == Decimal("400.00")
        assert trade.slippage == Decimal("0")
        assert trade.fill_price == Decimal("400.00")
        # Commission: 200 shares * 0.01 = 2.00
        assert trade.commission == Decimal("2.00")

    def test_trade_id_is_unique(self) -> None:
        """Two executions produce trades with different trade_ids."""
        engine = SimulatedFillEngine(
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )

        signal1 = Signal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action="buy",
            quantity=100,
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        signal2 = Signal(
            strategy_id="test_strategy",
            symbol="AAPL",
            action="sell",
            quantity=100,
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
        )

        fill_bar1 = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.00"),
            volume=1_000_000,
        )

        fill_bar2 = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 17, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("151.00"),
            high=Decimal("153.00"),
            low=Decimal("150.00"),
            close=Decimal("152.00"),
            volume=1_000_000,
        )

        trade1 = engine.execute(signal1, fill_bar1)
        trade2 = engine.execute(signal2, fill_bar2)

        # Trade IDs must be unique
        assert trade1.trade_id != trade2.trade_id
        # Trade IDs should be valid UUID strings
        assert len(trade1.trade_id) == 36  # UUID format: 8-4-4-4-12
        assert len(trade2.trade_id) == 36
