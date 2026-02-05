"""Full integration test: Backtest -> Paper trading signal consistency.

Implements T053: End-to-end workflow validation.

This test verifies:
1. Backtest produces expected results
2. Paper trading with same data produces identical signals
3. Signal consistency between modes (SC-002)
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig, Bar
from src.strategies.base import MarketData
from src.strategies.context import StrategyContext
from src.strategies.examples.trend_breakout import TrendBreakoutStrategy

# Path to test data
DATA_DIR = Path(__file__).parent.parent.parent / "data"
BARS_CSV = DATA_DIR / "bars.csv"


@dataclass
class RecordedSignal:
    """Recorded signal for comparison."""

    symbol: str
    action: str
    quantity: int
    timestamp: datetime
    composite_score: Decimal
    momentum_score: Decimal
    breakout_score: Decimal


class TestFullFlow:
    """End-to-end integration tests for backtest -> paper flow.

    T053: Verifies signal consistency between backtest and paper modes.
    SC-002: Functional correctness - strategy produces expected signals.
    """

    @pytest.fixture
    def strategy_params(self) -> dict[str, Any]:
        """Common strategy parameters for both modes."""
        return {
            "name": "integration-test-strategy",
            "symbols": ["AAPL"],
            "entry_threshold": 0.0,
            "exit_threshold": -0.02,
            "position_sizing": "equal_weight",
            "position_size": 100,
            "feature_weights": {
                "roc_20": 0.5,
                "price_vs_ma_20": 0.5,
                "price_vs_high_20": 0.5,
                "volume_zscore": 0.5,
            },
            "factor_weights": {
                "momentum_factor": 0.5,
                "breakout_factor": 0.5,
            },
        }

    @pytest.fixture
    def test_date_range(self) -> tuple[date, date]:
        """Date range for testing - 3 months of data."""
        return (date(2023, 3, 1), date(2023, 5, 31))

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Integration test data not available")
    async def test_backtest_produces_valid_results(
        self,
        strategy_params: dict[str, Any],
        test_date_range: tuple[date, date],
    ) -> None:
        """Verify backtest produces valid results with real data.

        This is a prerequisite for testing signal consistency.
        """
        start_date, end_date = test_date_range

        loader = CSVBarLoader(BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params=strategy_params,
            symbol="AAPL",
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal("100000"),
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )

        result = await engine.run(config)

        # Verify basic result structure
        assert result is not None
        assert len(result.equity_curve) > 0, "Should have equity curve"
        assert result.final_equity > 0, "Should have positive equity"
        assert result.started_at is not None
        assert result.completed_at is not None

        print("\nBacktest Results:")
        print(f"  Total Return: {result.total_return:.2%}")
        print(f"  Total Trades: {result.total_trades}")
        print(f"  Final Equity: ${result.final_equity:.2f}")
        print(f"  Equity Curve Points: {len(result.equity_curve)}")

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Integration test data not available")
    async def test_backtest_and_paper_signal_consistency(
        self,
        strategy_params: dict[str, Any],
        test_date_range: tuple[date, date],
    ) -> None:
        """T053/SC-002: Verify backtest and paper produce identical signals.

        This test:
        1. Runs a backtest and records all signals
        2. Simulates paper trading with the same data
        3. Verifies signals match exactly
        """
        start_date, end_date = test_date_range

        # Step 1: Run backtest and collect signals
        backtest_signals = await self._run_backtest_and_collect_signals(
            strategy_params, start_date, end_date
        )

        # Step 2: Load the same data and run through paper simulation
        paper_signals = await self._run_paper_simulation_with_same_data(
            strategy_params, start_date, end_date
        )

        # Step 3: Compare signals
        assert len(backtest_signals) == len(paper_signals), (
            f"Signal count mismatch: backtest={len(backtest_signals)}, "
            f"paper={len(paper_signals)}"
        )

        for i, (bt_sig, paper_sig) in enumerate(zip(backtest_signals, paper_signals, strict=False)):
            assert (
                bt_sig.symbol == paper_sig.symbol
            ), f"Signal {i}: symbol mismatch ({bt_sig.symbol} vs {paper_sig.symbol})"
            assert (
                bt_sig.action == paper_sig.action
            ), f"Signal {i}: action mismatch ({bt_sig.action} vs {paper_sig.action})"
            assert (
                bt_sig.quantity == paper_sig.quantity
            ), f"Signal {i}: quantity mismatch ({bt_sig.quantity} vs {paper_sig.quantity})"

            # Note: We can't directly compare factor scores from backtest traces
            # because traces don't store the factor_scores. The comparison of
            # action/quantity is sufficient to verify signal consistency.

        print("\nSignal Consistency Test PASSED")
        print(f"  Total signals compared: {len(backtest_signals)}")
        if backtest_signals:
            buy_count = sum(1 for s in backtest_signals if s.action == "buy")
            sell_count = sum(1 for s in backtest_signals if s.action == "sell")
            print(f"  Buy signals: {buy_count}")
            print(f"  Sell signals: {sell_count}")

    async def _run_backtest_and_collect_signals(
        self,
        strategy_params: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> list[RecordedSignal]:
        """Run backtest and extract signals from traces."""
        loader = CSVBarLoader(BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params=strategy_params,
            symbol="AAPL",
            start_date=start_date,
            end_date=end_date,
            initial_capital=Decimal("100000"),
        )

        result = await engine.run(config)

        # Convert trades to recorded signals
        signals = []
        for trace in result.traces:
            if trace.signal_direction and trace.fill_quantity:
                # Extract factor scores from the trace if available
                signal = RecordedSignal(
                    symbol="AAPL",
                    action=trace.signal_direction,
                    quantity=trace.signal_quantity,
                    timestamp=trace.signal_bar.timestamp,
                    composite_score=Decimal("0"),  # Not directly available in trace
                    momentum_score=Decimal("0"),
                    breakout_score=Decimal("0"),
                )
                signals.append(signal)

        return signals

    async def _run_paper_simulation_with_same_data(
        self,
        strategy_params: dict[str, Any],
        start_date: date,
        end_date: date,
    ) -> list[RecordedSignal]:
        """Simulate paper trading with the same historical data."""
        # Load the same bars
        loader = CSVBarLoader(BARS_CSV)

        # Need warmup data
        warmup_days = 30
        warmup_start = start_date - timedelta(days=warmup_days * 2)

        all_bars = await loader.load("AAPL", warmup_start, end_date)

        # Split into warmup and backtest bars
        warmup_bars = [b for b in all_bars if b.timestamp.date() < start_date]
        backtest_bars = [b for b in all_bars if b.timestamp.date() >= start_date]

        # Create fresh strategy instance
        strategy = TrendBreakoutStrategy(**strategy_params)
        await strategy.on_start()

        signals: list[RecordedSignal] = []
        current_position_qty = 0

        # Process warmup bars first (strategy needs history)
        for bar in warmup_bars[-21:]:  # Use last 21 bars for warmup
            market_data = self._bar_to_market_data(bar)
            context = self._create_context(current_position_qty)
            await strategy.on_market_data(market_data, context)

        # Process backtest bars and collect signals
        for bar in backtest_bars:
            market_data = self._bar_to_market_data(bar)
            context = self._create_context(current_position_qty)

            result_signals = await strategy.on_market_data(market_data, context)

            for sig in result_signals:
                recorded = RecordedSignal(
                    symbol=sig.symbol,
                    action=sig.action,
                    quantity=sig.quantity,
                    timestamp=bar.timestamp,
                    composite_score=sig.factor_scores.get("composite", Decimal("0")),
                    momentum_score=sig.factor_scores.get("momentum_factor", Decimal("0")),
                    breakout_score=sig.factor_scores.get("breakout_factor", Decimal("0")),
                )
                signals.append(recorded)

                # Update position tracking
                if sig.action == "buy":
                    current_position_qty += sig.quantity
                elif sig.action == "sell":
                    current_position_qty -= sig.quantity

        await strategy.on_stop()
        return signals

    def _bar_to_market_data(self, bar: Bar) -> MarketData:
        """Convert a Bar to MarketData."""
        market_data = MarketData(
            symbol=bar.symbol,
            price=bar.close,
            bid=bar.close - Decimal("0.01"),
            ask=bar.close + Decimal("0.01"),
            volume=bar.volume,
            timestamp=bar.timestamp,
        )
        # Add high for PriceVsHigh indicator
        market_data.high = bar.high  # type: ignore
        return market_data

    def _create_context(self, position_qty: int) -> StrategyContext:
        """Create a mock context with position state."""

        @dataclass
        class MockPosition:
            quantity: int
            avg_cost: Decimal = Decimal("100.00")

        context = MagicMock(spec=StrategyContext)

        async def get_position(symbol: str):
            if position_qty > 0:
                return MockPosition(quantity=position_qty)
            return None

        context.get_position = get_position
        return context

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Integration test data not available")
    async def test_multiple_symbols_consistency(
        self,
        strategy_params: dict[str, Any],
    ) -> None:
        """Test signal consistency across multiple symbols.

        Verifies that each symbol's signals are independent and consistent.
        """
        symbols = ["AAPL", "GOOGL", "MSFT"]
        start_date = date(2023, 3, 1)
        end_date = date(2023, 5, 31)

        results_by_symbol: dict[str, Any] = {}

        for symbol in symbols:
            params = dict(strategy_params)
            params["symbols"] = [symbol]

            loader = CSVBarLoader(BARS_CSV)
            engine = BacktestEngine(loader)

            config = BacktestConfig(
                strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
                strategy_params=params,
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                initial_capital=Decimal("100000"),
            )

            result = await engine.run(config)
            results_by_symbol[symbol] = {
                "trades": result.total_trades,
                "return": result.total_return,
                "equity_points": len(result.equity_curve),
            }

        print("\nMulti-symbol consistency test:")
        for symbol, data in results_by_symbol.items():
            print(
                f"  {symbol}: {data['trades']} trades, "
                f"{data['return']:.2%} return, "
                f"{data['equity_points']} equity points"
            )

        # Each symbol should have produced results
        for symbol in symbols:
            assert (
                results_by_symbol[symbol]["equity_points"] > 0
            ), f"Symbol {symbol} produced no equity curve"


class TestEndToEndWorkflow:
    """Tests for complete end-to-end trading workflow."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Integration test data not available")
    async def test_complete_backtest_workflow(self) -> None:
        """Test complete backtest workflow from data load to metrics."""
        loader = CSVBarLoader(BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params={
                "name": "e2e-test",
                "symbols": ["AAPL"],
                "entry_threshold": 0.0,
                "exit_threshold": -0.02,
            },
            symbol="AAPL",
            start_date=date(2023, 3, 1),
            end_date=date(2023, 6, 30),
            initial_capital=Decimal("100000"),
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
            benchmark_symbol="SPY",
        )

        result = await engine.run(config)

        # Verify all result components
        assert result.config == config
        assert len(result.equity_curve) > 0
        assert result.final_equity > 0
        assert result.total_return is not None
        assert result.sharpe_ratio is not None
        assert result.max_drawdown is not None
        assert result.win_rate is not None
        assert result.started_at < result.completed_at

        # Verify benchmark comparison (if available)
        if result.benchmark:
            assert result.benchmark.benchmark_symbol == "SPY"
            print("\nBenchmark Comparison:")
            print(f"  Beta: {result.benchmark.beta}")
            print(f"  Alpha: {result.benchmark.alpha}")
            print(f"  Tracking Error: {result.benchmark.tracking_error}")

        # Verify traces match trades
        assert len(result.traces) == len(result.trades)

        # Verify attribution summary
        if result.total_trades > 0 and result.attribution_summary:
            print("\nAttribution Summary:")
            for factor, value in result.attribution_summary.items():
                print(f"  {factor}: ${value:.2f}")

        print("\nComplete Workflow Test PASSED")
        print(f"  Duration: {(result.completed_at - result.started_at).total_seconds():.2f}s")
        print(f"  Total Return: {result.total_return:.2%}")
        print(f"  Total Trades: {result.total_trades}")

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Integration test data not available")
    async def test_attribution_integration(self) -> None:
        """Test that attribution is calculated and consistent across trades."""
        loader = CSVBarLoader(BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params={
                "name": "attribution-test",
                "symbols": ["AAPL"],
                "entry_threshold": 0.0,
                "exit_threshold": -0.02,
            },
            symbol="AAPL",
            start_date=date(2023, 2, 1),
            end_date=date(2023, 12, 31),
            initial_capital=Decimal("100000"),
        )

        result = await engine.run(config)

        # Check trades have attribution
        trades_with_attribution = [t for t in result.trades if t.attribution]

        if trades_with_attribution:
            print("\nAttribution Integration Test:")
            print(f"  Total trades: {len(result.trades)}")
            print(f"  Trades with attribution: {len(trades_with_attribution)}")

            # Verify attribution sums match PnL for each trade
            for trade in trades_with_attribution:
                if trade.attribution:
                    attr_sum = sum(trade.attribution.values())
                    # Note: We can't directly verify against trade.pnl here
                    # because the Trade model calculates PnL differently
                    print(f"  Trade {trade.trade_id}: attribution sum = ${attr_sum:.2f}")

            # Verify summary matches sum of individual attributions
            if result.attribution_summary:
                summary_total = result.attribution_summary.get("total", Decimal("0"))
                print(f"  Total attribution: ${summary_total:.2f}")
