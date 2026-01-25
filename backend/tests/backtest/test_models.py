"""Tests for backtest models."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from src.backtest.models import BacktestConfig, BacktestResult, Bar, Trade


class TestBar:
    """Tests for Bar dataclass."""

    def test_create_bar(self) -> None:
        """Create bar and verify all fields are set correctly."""
        timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        bar = Bar(
            symbol="AAPL",
            timestamp=timestamp,
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        assert bar.symbol == "AAPL"
        assert bar.timestamp == timestamp
        assert bar.open == Decimal("185.50")
        assert bar.high == Decimal("187.25")
        assert bar.low == Decimal("184.00")
        assert bar.close == Decimal("186.75")
        assert bar.volume == 50_000_000
        assert bar.interval == "1d"  # default value

    def test_bar_is_frozen(self) -> None:
        """Verify Bar is immutable - raises AttributeError when modifying."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        with pytest.raises(AttributeError):
            bar.symbol = "MSFT"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            bar.close = Decimal("200.00")  # type: ignore[misc]

    def test_bar_requires_timezone_aware_timestamp(self) -> None:
        """Verify timestamp has tzinfo set (not None).

        Timezone-aware timestamps are required to avoid ambiguity in
        backtesting across different market sessions and data sources.
        """
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        # Timestamp must be timezone-aware
        assert bar.timestamp.tzinfo is not None


class TestTrade:
    """Tests for Trade dataclass."""

    def test_create_buy_trade(self) -> None:
        """Create buy trade, verify fill_price = gross + slippage."""
        signal_time = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        fill_time = datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc)

        trade = Trade(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            timestamp=fill_time,
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("185.50"),
            slippage=Decimal("0.05"),
            commission=Decimal("1.00"),
            signal_bar_timestamp=signal_time,
        )

        assert trade.trade_id == "550e8400-e29b-41d4-a716-446655440000"
        assert trade.timestamp == fill_time
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 100
        assert trade.gross_price == Decimal("185.50")
        assert trade.slippage == Decimal("0.05")
        # For buy trades: fill_price = gross_price + slippage
        assert trade.fill_price == Decimal("185.55")
        assert trade.commission == Decimal("1.00")
        assert trade.signal_bar_timestamp == signal_time

    def test_create_sell_trade(self) -> None:
        """Create sell trade, verify fill_price = gross - slippage."""
        signal_time = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        fill_time = datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc)

        trade = Trade(
            trade_id="550e8400-e29b-41d4-a716-446655440001",
            timestamp=fill_time,
            symbol="MSFT",
            side="sell",
            quantity=50,
            gross_price=Decimal("400.00"),
            slippage=Decimal("0.10"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=signal_time,
        )

        assert trade.trade_id == "550e8400-e29b-41d4-a716-446655440001"
        assert trade.timestamp == fill_time
        assert trade.symbol == "MSFT"
        assert trade.side == "sell"
        assert trade.quantity == 50
        assert trade.gross_price == Decimal("400.00")
        assert trade.slippage == Decimal("0.10")
        # For sell trades: fill_price = gross_price - slippage
        assert trade.fill_price == Decimal("399.90")
        assert trade.commission == Decimal("0.50")
        assert trade.signal_bar_timestamp == signal_time


class TestBacktestConfig:
    """Tests for BacktestConfig dataclass."""

    def test_create_config_with_defaults(self) -> None:
        """Create config with minimal params, verify defaults are set."""
        config = BacktestConfig(
            strategy_class="MyStrategy",
            strategy_params={"fast_period": 10, "slow_period": 20},
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=Decimal("100000"),
        )

        assert config.strategy_class == "MyStrategy"
        assert config.strategy_params == {"fast_period": 10, "slow_period": 20}
        assert config.symbol == "AAPL"
        assert config.start_date == date(2024, 1, 1)
        assert config.end_date == date(2024, 12, 31)
        assert config.initial_capital == Decimal("100000")
        # Verify defaults
        assert config.fill_model == "next_bar_open"
        assert config.slippage_model == "fixed_bps"
        assert config.slippage_bps == 5
        assert config.commission_model == "per_share"
        assert config.commission_per_share == Decimal("0.005")

    def test_config_with_custom_values(self) -> None:
        """Create config with all custom values."""
        config = BacktestConfig(
            strategy_class="CustomStrategy",
            strategy_params={"threshold": 0.5},
            symbol="MSFT",
            start_date=date(2023, 6, 1),
            end_date=date(2023, 12, 31),
            initial_capital=Decimal("50000"),
            fill_model="next_bar_open",
            slippage_model="fixed_bps",
            slippage_bps=10,
            commission_model="per_share",
            commission_per_share=Decimal("0.01"),
        )

        assert config.strategy_class == "CustomStrategy"
        assert config.strategy_params == {"threshold": 0.5}
        assert config.symbol == "MSFT"
        assert config.start_date == date(2023, 6, 1)
        assert config.end_date == date(2023, 12, 31)
        assert config.initial_capital == Decimal("50000")
        assert config.fill_model == "next_bar_open"
        assert config.slippage_model == "fixed_bps"
        assert config.slippage_bps == 10
        assert config.commission_model == "per_share"
        assert config.commission_per_share == Decimal("0.01")

    def test_backtest_config_benchmark_symbol_optional(self) -> None:
        """BacktestConfig has optional benchmark_symbol field."""
        config = BacktestConfig(
            strategy_class="test.Strategy",
            strategy_params={},
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=Decimal("100000"),
        )
        assert config.benchmark_symbol is None

        config_with_benchmark = BacktestConfig(
            strategy_class="test.Strategy",
            strategy_params={},
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 12, 31),
            initial_capital=Decimal("100000"),
            benchmark_symbol="SPY",
        )
        assert config_with_benchmark.benchmark_symbol == "SPY"


class TestBacktestResult:
    """Tests for BacktestResult dataclass."""

    def test_create_result(self) -> None:
        """Create result with all fields populated."""
        config = BacktestConfig(
            strategy_class="TestStrategy",
            strategy_params={},
            symbol="AAPL",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 3, 31),
            initial_capital=Decimal("100000"),
        )

        signal_time = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        fill_time = datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc)
        trade = Trade(
            trade_id="test-trade-001",
            timestamp=fill_time,
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("185.50"),
            slippage=Decimal("0.05"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=signal_time,
        )

        equity_curve = [
            (datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2024, 1, 3, 16, 0, 0, tzinfo=timezone.utc), Decimal("100500")),
            (datetime(2024, 1, 4, 16, 0, 0, tzinfo=timezone.utc), Decimal("101000")),
        ]

        started_at = datetime(2024, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
        completed_at = datetime(2024, 4, 1, 10, 0, 5, tzinfo=timezone.utc)
        first_signal = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)

        result = BacktestResult(
            config=config,
            equity_curve=equity_curve,
            trades=[trade],
            final_equity=Decimal("110000"),
            final_cash=Decimal("90000"),
            final_position_qty=100,
            total_return=Decimal("0.10"),
            annualized_return=Decimal("0.45"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("0.05"),
            win_rate=Decimal("0.60"),
            total_trades=10,
            avg_trade_pnl=Decimal("1000"),
            warm_up_required_bars=20,
            warm_up_bars_used=20,
            first_signal_bar=first_signal,
            started_at=started_at,
            completed_at=completed_at,
        )

        assert result.config == config
        assert result.equity_curve == equity_curve
        assert result.trades == [trade]
        assert result.final_equity == Decimal("110000")
        assert result.final_cash == Decimal("90000")
        assert result.final_position_qty == 100
        assert result.total_return == Decimal("0.10")
        assert result.annualized_return == Decimal("0.45")
        assert result.sharpe_ratio == Decimal("1.5")
        assert result.max_drawdown == Decimal("0.05")
        assert result.win_rate == Decimal("0.60")
        assert result.total_trades == 10
        assert result.avg_trade_pnl == Decimal("1000")
        assert result.warm_up_required_bars == 20
        assert result.warm_up_bars_used == 20
        assert result.first_signal_bar == first_signal
        assert result.started_at == started_at
        assert result.completed_at == completed_at
