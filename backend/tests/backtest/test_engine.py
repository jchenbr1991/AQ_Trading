"""Tests for BacktestEngine."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig, BacktestResult
from src.strategies.base import MarketData, Strategy
from src.strategies.context import StrategyContext
from src.strategies.signals import Signal

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_BARS_CSV = FIXTURES_DIR / "sample_bars.csv"


class SimpleTestStrategy(Strategy):
    """Simple strategy for testing that buys on first signal."""

    def __init__(self, name: str = "test", symbols: list[str] | None = None):
        self.name = name
        self.symbols = symbols or ["AAPL"]
        self._bar_count = 0
        self._warmup_bars = 0

    @property
    def warmup_bars(self) -> int:
        return self._warmup_bars

    async def on_market_data(self, data: MarketData, context: "StrategyContext") -> list[Signal]:
        self._bar_count += 1
        # Generate buy signal on first bar after warmup
        if self._bar_count == self._warmup_bars + 1:
            return [
                Signal(
                    strategy_id=self.name,
                    symbol=data.symbol,
                    action="buy",
                    quantity=10,
                    timestamp=data.timestamp,
                )
            ]
        return []


class WarmupTestStrategy(Strategy):
    """Strategy that requires warmup bars."""

    def __init__(
        self, name: str = "warmup_test", symbols: list[str] | None = None, warmup: int = 3
    ):
        self.name = name
        self.symbols = symbols or ["AAPL"]
        self._warmup = warmup
        self._bar_count = 0

    @property
    def warmup_bars(self) -> int:
        return self._warmup

    async def on_market_data(self, data: MarketData, context: "StrategyContext") -> list[Signal]:
        self._bar_count += 1
        # Generate buy signal after warmup
        if self._bar_count == self._warmup + 1:
            return [
                Signal(
                    strategy_id=self.name,
                    symbol=data.symbol,
                    action="buy",
                    quantity=10,
                    timestamp=data.timestamp,
                )
            ]
        return []


class TestBacktestEngine:
    """Tests for BacktestEngine."""

    @pytest.mark.asyncio
    async def test_run_returns_result(self) -> None:
        """Basic run returns BacktestResult with required fields."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="tests.backtest.test_engine.SimpleTestStrategy",
            strategy_params={"name": "test", "symbols": ["AAPL"]},
            symbol="AAPL",
            start_date=date(2025, 1, 2),
            end_date=date(2025, 1, 8),
            initial_capital=Decimal("10000"),
        )

        result = await engine.run(config)

        # Verify BacktestResult is returned with basic fields
        assert isinstance(result, BacktestResult)
        assert result.config == config
        assert len(result.equity_curve) > 0
        assert result.final_equity > 0
        assert result.started_at is not None
        assert result.completed_at is not None
        assert result.completed_at >= result.started_at

    @pytest.mark.asyncio
    async def test_warmup_phase_does_not_trade(self) -> None:
        """Trades only occur after start_date, not during warmup."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)
        engine = BacktestEngine(loader)

        # Strategy requires 2 warmup bars
        config = BacktestConfig(
            strategy_class="tests.backtest.test_engine.WarmupTestStrategy",
            strategy_params={"name": "warmup_test", "symbols": ["AAPL"], "warmup": 2},
            symbol="AAPL",
            start_date=date(2025, 1, 6),  # Start after Jan 2, 3 (warmup)
            end_date=date(2025, 1, 8),
            initial_capital=Decimal("10000"),
        )

        result = await engine.run(config)

        # Check that no trades occur before start_date
        for trade in result.trades:
            assert (
                trade.timestamp.date() >= config.start_date
            ), f"Trade at {trade.timestamp.date()} is before start_date {config.start_date}"
            # Also check signal_bar_timestamp is before trade timestamp
            assert (
                trade.signal_bar_timestamp < trade.timestamp
            ), f"Signal at {trade.signal_bar_timestamp} should be before trade at {trade.timestamp}"

    @pytest.mark.asyncio
    async def test_insufficient_warmup_raises_error(self) -> None:
        """ValueError raised when not enough bars for warmup."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)
        engine = BacktestEngine(loader)

        # Require 10 warmup bars but only have 5 bars total in CSV
        config = BacktestConfig(
            strategy_class="tests.backtest.test_engine.WarmupTestStrategy",
            strategy_params={"name": "test", "symbols": ["AAPL"], "warmup": 10},
            symbol="AAPL",
            start_date=date(2025, 1, 6),  # Only 2 bars before this
            end_date=date(2025, 1, 8),
            initial_capital=Decimal("10000"),
        )

        with pytest.raises(ValueError, match="Insufficient warmup"):
            await engine.run(config)

    @pytest.mark.asyncio
    async def test_equity_curve_starts_at_initial_capital(self) -> None:
        """First equity point equals initial_capital."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)
        engine = BacktestEngine(loader)

        initial_capital = Decimal("50000")
        config = BacktestConfig(
            strategy_class="tests.backtest.test_engine.SimpleTestStrategy",
            strategy_params={"name": "test", "symbols": ["AAPL"]},
            symbol="AAPL",
            start_date=date(2025, 1, 2),
            end_date=date(2025, 1, 8),
            initial_capital=initial_capital,
        )

        result = await engine.run(config)

        # First equity curve point should be initial capital
        assert len(result.equity_curve) > 0
        first_timestamp, first_equity = result.equity_curve[0]
        assert (
            first_equity == initial_capital
        ), f"First equity {first_equity} should equal initial capital {initial_capital}"

    @pytest.mark.asyncio
    async def test_no_lookahead_bias(self) -> None:
        """Trade timestamp is always after signal bar timestamp (no lookahead)."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="tests.backtest.test_engine.SimpleTestStrategy",
            strategy_params={"name": "test", "symbols": ["AAPL"]},
            symbol="AAPL",
            start_date=date(2025, 1, 2),
            end_date=date(2025, 1, 8),
            initial_capital=Decimal("10000"),
        )

        result = await engine.run(config)

        # Verify each trade happened after its signal
        for trade in result.trades:
            assert trade.timestamp > trade.signal_bar_timestamp, (
                f"Trade at {trade.timestamp} should be after signal at "
                f"{trade.signal_bar_timestamp} (no lookahead bias)"
            )

    @pytest.mark.asyncio
    async def test_engine_with_benchmark(self, tmp_path) -> None:
        """Engine computes benchmark comparison when benchmark_symbol provided."""
        # Include warmup bar on 2024-01-01 and backtest bars from 2024-01-02
        csv_content = """timestamp,symbol,open,high,low,close,volume
2024-01-01T21:00:00+00:00,AAPL,99.00,100.00,98.00,99.00,1000000
2024-01-02T21:00:00+00:00,AAPL,100.00,102.00,99.00,100.00,1000000
2024-01-03T21:00:00+00:00,AAPL,100.00,110.00,100.00,110.00,1000000
2024-01-04T21:00:00+00:00,AAPL,110.00,120.00,110.00,121.00,1000000
2024-01-01T21:00:00+00:00,SPY,390.00,395.00,388.00,390.00,5000000
2024-01-02T21:00:00+00:00,SPY,400.00,405.00,398.00,400.00,5000000
2024-01-03T21:00:00+00:00,SPY,400.00,410.00,400.00,420.00,5000000
2024-01-04T21:00:00+00:00,SPY,420.00,430.00,420.00,440.00,5000000
"""
        csv_file = tmp_path / "bars.csv"
        csv_file.write_text(csv_content)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={
                "name": "momentum",
                "symbols": ["AAPL"],
                "lookback_period": 1,
                "threshold": 0.5,
                "position_size": 10,
            },
            symbol="AAPL",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 5),
            initial_capital=Decimal("10000"),
            benchmark_symbol="SPY",
        )

        loader = CSVBarLoader(csv_file)
        engine = BacktestEngine(loader)
        result = await engine.run(config)

        assert result.benchmark is not None
        assert result.benchmark.benchmark_symbol == "SPY"
        assert result.benchmark.beta is not None

    @pytest.mark.asyncio
    async def test_engine_without_benchmark(self, tmp_path) -> None:
        """Engine returns benchmark=None when no benchmark_symbol."""
        # Include warmup bar on 2024-01-01 and backtest bars from 2024-01-02
        csv_content = """timestamp,symbol,open,high,low,close,volume
2024-01-01T21:00:00+00:00,AAPL,99.00,100.00,98.00,99.00,1000000
2024-01-02T21:00:00+00:00,AAPL,100.00,102.00,99.00,100.00,1000000
2024-01-03T21:00:00+00:00,AAPL,100.00,110.00,100.00,110.00,1000000
"""
        csv_file = tmp_path / "bars.csv"
        csv_file.write_text(csv_content)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={
                "name": "momentum",
                "symbols": ["AAPL"],
                "lookback_period": 1,
                "threshold": 0.5,
                "position_size": 10,
            },
            symbol="AAPL",
            start_date=date(2024, 1, 2),
            end_date=date(2024, 1, 5),
            initial_capital=Decimal("10000"),
        )

        loader = CSVBarLoader(csv_file)
        engine = BacktestEngine(loader)
        result = await engine.run(config)

        assert result.benchmark is None
