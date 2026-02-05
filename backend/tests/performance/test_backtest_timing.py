"""Performance tests for backtest engine timing.

Implements T049: Verify backtest performance meets SC-004 requirement.

SC-004: Backtest 1 year of daily data for 3 symbols must complete in < 30 seconds.
"""

import asyncio
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig

# Path to real data
DATA_DIR = Path(__file__).parent.parent.parent / "data"
BARS_CSV = DATA_DIR / "bars.csv"


class TestBacktestPerformance:
    """Performance tests for backtest engine.

    SC-004: 1 year x 3 symbols < 30 seconds.
    """

    @pytest.fixture
    def available_symbols(self) -> list[str]:
        """Symbols available in the test data."""
        return ["AAPL", "GOOGL", "MSFT"]

    @pytest.fixture
    def one_year_date_range(self) -> tuple[date, date]:
        """One year date range for performance testing.

        Uses 2023-02-01 to 2024-01-31 to ensure we have:
        - Warmup data available (from 2023-01-01)
        - Full year of backtest data
        """
        return (date(2023, 2, 1), date(2024, 1, 31))

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Performance test data not available")
    async def test_backtest_one_year_three_symbols_under_30_seconds(
        self,
        available_symbols: list[str],
        one_year_date_range: tuple[date, date],
    ) -> None:
        """SC-004: Backtest 1 year x 3 symbols completes in < 30 seconds.

        This test benchmarks the full backtest workflow:
        1. Load data from CSV
        2. Run strategy warmup
        3. Process all bars through strategy
        4. Calculate fills, portfolio updates, and metrics
        5. Compute attribution

        The 30 second limit accounts for:
        - ~252 trading days per symbol
        - ~756 total bars to process
        - Indicator calculations per bar
        - Attribution calculations per trade
        """
        start_date, end_date = one_year_date_range

        # Warm-up run to ensure JIT compilation / module loading doesn't affect timing
        await self._run_single_backtest(
            symbol=available_symbols[0],
            start_date=start_date,
            end_date=start_date + timedelta(days=30),  # Short warmup period
        )

        # Measure total time for all 3 symbols
        total_start_time = time.perf_counter()

        results = []
        for symbol in available_symbols:
            symbol_start = time.perf_counter()

            result = await self._run_single_backtest(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            symbol_elapsed = time.perf_counter() - symbol_start
            results.append(
                {
                    "symbol": symbol,
                    "elapsed_seconds": symbol_elapsed,
                    "total_bars": len(result.equity_curve),
                    "total_trades": result.total_trades,
                }
            )

        total_elapsed = time.perf_counter() - total_start_time

        # Report timing details
        print(f"\n{'='*60}")
        print("SC-004 Performance Test Results")
        print(f"{'='*60}")
        print(f"Date range: {start_date} to {end_date}")
        print(f"Symbols: {', '.join(available_symbols)}")
        print(f"{'='*60}")

        for r in results:
            print(
                f"  {r['symbol']}: {r['elapsed_seconds']:.2f}s "
                f"({r['total_bars']} bars, {r['total_trades']} trades)"
            )

        print(f"{'='*60}")
        print(f"TOTAL TIME: {total_elapsed:.2f} seconds")
        print("REQUIREMENT: < 30 seconds")
        print(f"STATUS: {'PASS' if total_elapsed < 30 else 'FAIL'}")
        print(f"{'='*60}")

        # SC-004 ASSERTION
        assert total_elapsed < 30, (
            f"SC-004 FAILED: Backtest took {total_elapsed:.2f}s, " f"exceeds 30s limit"
        )

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Performance test data not available")
    async def test_backtest_per_symbol_timing(
        self,
        available_symbols: list[str],
        one_year_date_range: tuple[date, date],
    ) -> None:
        """Verify each symbol completes in reasonable time (< 15 seconds each).

        This provides finer-grained performance insight per symbol.
        """
        start_date, end_date = one_year_date_range

        for symbol in available_symbols:
            start_time = time.perf_counter()

            result = await self._run_single_backtest(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )

            elapsed = time.perf_counter() - start_time

            # Individual symbol should complete in < 15 seconds
            # (gives headroom for the 30s total limit)
            assert (
                elapsed < 15
            ), f"Symbol {symbol} took {elapsed:.2f}s, exceeds 15s per-symbol limit"

            # Sanity check: should have processed data
            assert len(result.equity_curve) > 0, f"No equity curve for {symbol}"

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Performance test data not available")
    async def test_backtest_parallel_execution(
        self,
        available_symbols: list[str],
        one_year_date_range: tuple[date, date],
    ) -> None:
        """Test that parallel execution of backtests is efficient.

        While not strictly required by SC-004, parallel execution could
        further improve performance.
        """
        start_date, end_date = one_year_date_range

        start_time = time.perf_counter()

        # Run all symbols in parallel
        tasks = [
            self._run_single_backtest(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            )
            for symbol in available_symbols
        ]

        results = await asyncio.gather(*tasks)

        parallel_elapsed = time.perf_counter() - start_time

        print(f"\nParallel execution time for 3 symbols: {parallel_elapsed:.2f}s")

        # Parallel should still be under 30 seconds
        assert parallel_elapsed < 30, f"Parallel backtest took {parallel_elapsed:.2f}s, exceeds 30s"

        # All results should be valid
        for result in results:
            assert len(result.equity_curve) > 0

    async def _run_single_backtest(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        initial_capital: Decimal = Decimal("100000"),
    ):
        """Run a single backtest for one symbol.

        Uses TrendBreakoutStrategy with default parameters.
        """
        loader = CSVBarLoader(BARS_CSV)
        engine = BacktestEngine(loader)

        config = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params={
                "name": f"perf-test-{symbol}",
                "symbols": [symbol],
                "entry_threshold": 0.0,
                "exit_threshold": -0.02,
                "position_sizing": "equal_weight",
                "position_size": 100,
            },
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )

        return await engine.run(config)


class TestBacktestScalability:
    """Tests for backtest scalability characteristics."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(not BARS_CSV.exists(), reason="Performance test data not available")
    async def test_timing_scales_linearly_with_bars(self) -> None:
        """Verify that timing scales roughly linearly with number of bars.

        Compare 6 months vs 1 year - 1 year should take ~2x the time of 6 months,
        not exponentially more.
        """
        loader = CSVBarLoader(BARS_CSV)
        engine = BacktestEngine(loader)

        # 6-month backtest
        config_6mo = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params={
                "name": "scale-test-6mo",
                "symbols": ["AAPL"],
            },
            symbol="AAPL",
            start_date=date(2023, 2, 1),
            end_date=date(2023, 7, 31),
            initial_capital=Decimal("100000"),
        )

        start_6mo = time.perf_counter()
        result_6mo = await engine.run(config_6mo)
        elapsed_6mo = time.perf_counter() - start_6mo

        # Create fresh engine for second test
        engine_12mo = BacktestEngine(loader)

        # 12-month backtest
        config_12mo = BacktestConfig(
            strategy_class="src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
            strategy_params={
                "name": "scale-test-12mo",
                "symbols": ["AAPL"],
            },
            symbol="AAPL",
            start_date=date(2023, 2, 1),
            end_date=date(2024, 1, 31),
            initial_capital=Decimal("100000"),
        )

        start_12mo = time.perf_counter()
        result_12mo = await engine_12mo.run(config_12mo)
        elapsed_12mo = time.perf_counter() - start_12mo

        # Ratio should be roughly 2x (with some tolerance for startup overhead)
        # Allow up to 3x to account for fixed overhead
        bars_ratio = len(result_12mo.equity_curve) / max(len(result_6mo.equity_curve), 1)
        time_ratio = elapsed_12mo / max(elapsed_6mo, 0.001)

        print("\nScalability test:")
        print(f"  6mo: {elapsed_6mo:.3f}s ({len(result_6mo.equity_curve)} bars)")
        print(f"  12mo: {elapsed_12mo:.3f}s ({len(result_12mo.equity_curve)} bars)")
        print(f"  Bars ratio: {bars_ratio:.2f}x")
        print(f"  Time ratio: {time_ratio:.2f}x")

        # Time should not scale super-linearly (no worse than 3x for 2x bars)
        assert (
            time_ratio < bars_ratio * 1.5
        ), f"Time scaling is super-linear: {time_ratio:.2f}x for {bars_ratio:.2f}x bars"
