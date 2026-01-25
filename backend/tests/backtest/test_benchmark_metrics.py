"""Tests for BenchmarkMetrics.compute."""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.benchmark import BenchmarkComparison
from src.backtest.benchmark_metrics import BenchmarkMetrics


def make_curve(values: list[float], start_day: int = 1) -> list[tuple[datetime, Decimal]]:
    """Create an equity curve from values.

    Args:
        values: List of equity values.
        start_day: Starting day of month (default 1).

    Returns:
        List of (timestamp, equity) tuples.
    """
    return [
        (datetime(2024, 1, start_day + i, 21, 0, tzinfo=timezone.utc), Decimal(str(v)))
        for i, v in enumerate(values)
    ]


class TestBenchmarkMetrics:
    """Tests for BenchmarkMetrics.compute."""

    def test_compute_returns_benchmark_comparison(self) -> None:
        """Compute returns a BenchmarkComparison dataclass."""
        strategy_curve = make_curve([100, 110, 121])
        benchmark_curve = make_curve([100, 105, 110])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        assert isinstance(result, BenchmarkComparison)
        assert result.benchmark_symbol == "SPY"

    def test_compute_benchmark_total_return(self) -> None:
        """Benchmark total return is (last - first) / first."""
        strategy_curve = make_curve([100, 110, 120])
        # Benchmark: 100 -> 150, total return = 0.5
        benchmark_curve = make_curve([100, 125, 150])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        assert result.benchmark_total_return == Decimal("0.5")

    def test_compute_beta_positive_correlation(self) -> None:
        """Beta = 1 when strategy returns identical to benchmark."""
        # Same returns for both: beta should be 1
        strategy_curve = make_curve([100, 110, 121, 133.1])
        benchmark_curve = make_curve([100, 110, 121, 133.1])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # Beta should be approximately 1.0
        assert abs(float(result.beta) - 1.0) < 1e-6

    def test_compute_alpha_with_outperformance(self) -> None:
        """Alpha > 0 when strategy consistently outperforms benchmark."""
        # Strategy consistently outperforms benchmark
        # Benchmark: +10% each period
        # Strategy: +15% each period (5% daily alpha)
        strategy_curve = make_curve([100, 115, 132.25, 152.0875])
        benchmark_curve = make_curve([100, 110, 121, 133.1])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # Alpha should be positive (strategy beats benchmark)
        assert float(result.alpha) > 0

    def test_compute_tracking_error(self) -> None:
        """Tracking error is positive when returns differ."""
        # Different return patterns will have tracking error > 0
        strategy_curve = make_curve([100, 120, 110, 130])
        benchmark_curve = make_curve([100, 105, 110, 115])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        assert float(result.tracking_error) > 0

    def test_compute_information_ratio(self) -> None:
        """Information ratio = alpha / tracking_error."""
        strategy_curve = make_curve([100, 115, 132.25, 152.0875, 174.90])
        benchmark_curve = make_curve([100, 110, 121, 133.1, 146.41])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # Verify information ratio calculation
        if float(result.tracking_error) > 0:
            expected_ir = float(result.alpha) / float(result.tracking_error)
            assert abs(float(result.information_ratio) - expected_ir) < 1e-6

    def test_compute_sortino_positive_returns(self) -> None:
        """Sortino is positive for positive average returns."""
        # Mix of positive and negative returns with positive mean
        strategy_curve = make_curve([100, 110, 105, 115, 120])
        benchmark_curve = make_curve([100, 105, 102, 108, 112])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # With positive mean return and some downside, sortino should be positive
        assert float(result.sortino_ratio) > 0

    def test_compute_sortino_zero_downside(self) -> None:
        """Sortino = 0 when there are no negative returns."""
        # All positive returns - no downside
        strategy_curve = make_curve([100, 110, 121, 133.1])
        benchmark_curve = make_curve([100, 105, 110, 115])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # No negative returns means sortino = 0 by convention
        assert float(result.sortino_ratio) == 0.0

    def test_compute_up_capture(self) -> None:
        """Up capture = mean(strategy_up) / mean(benchmark_up) on up days."""
        # Benchmark up 10%, strategy up 15% = up capture 1.5
        # Benchmark down 5%, strategy down 2.5%
        # Day 1: both at 100
        # Day 2: benchmark +10% (110), strategy +15% (115)
        # Day 3: benchmark -5% (104.5), strategy -2.5% (112.125)
        # Day 4: benchmark +10% (114.95), strategy +15% (128.94375)
        strategy_curve = make_curve([100, 115, 112.125, 128.94375])
        benchmark_curve = make_curve([100, 110, 104.5, 114.95])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # Up capture should be approximately 1.5 (15% / 10%)
        assert abs(float(result.up_capture) - 1.5) < 1e-6

    def test_compute_down_capture(self) -> None:
        """Down capture = mean(strategy_down) / mean(benchmark_down) on down days."""
        # Benchmark down 10%, strategy down 5% = down capture 0.5
        # Day 1: both at 100
        # Day 2: benchmark -10% (90), strategy -5% (95)
        # Day 3: benchmark -10% (81), strategy -5% (90.25)
        strategy_curve = make_curve([100, 95, 90.25])
        benchmark_curve = make_curve([100, 90, 81])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # Down capture = (-5%) / (-10%) = 0.5
        assert abs(float(result.down_capture) - 0.5) < 1e-6

    def test_compute_insufficient_data_returns_none(self) -> None:
        """< 2 aligned points returns None."""
        strategy_curve = make_curve([100])
        benchmark_curve = make_curve([100])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is None

    def test_compute_no_overlap_returns_none(self) -> None:
        """No matching timestamps returns None."""
        # Strategy on days 1-3, benchmark on days 10-12
        strategy_curve = make_curve([100, 110, 120], start_day=1)
        benchmark_curve = make_curve([100, 105, 110], start_day=10)

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is None

    def test_compute_zero_benchmark_variance(self) -> None:
        """When benchmark variance = 0, beta = 0, alpha = mean(strategy_returns) * 252."""
        # Benchmark returns are all 0 (flat line)
        strategy_curve = make_curve([100, 110, 121, 133.1])
        benchmark_curve = make_curve([100, 100, 100, 100])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        # Beta should be 0 when benchmark has no variance
        assert float(result.beta) == 0.0
        # Alpha should be mean(strategy_returns) * 252
        # Strategy returns: 0.1, 0.1, 0.1 -> mean = 0.1
        # Alpha = 0.1 * 252 = 25.2
        assert abs(float(result.alpha) - 25.2) < 1e-6

    def test_compute_no_up_days(self) -> None:
        """Up capture = 0 when benchmark has no up days."""
        # All benchmark returns are negative
        strategy_curve = make_curve([100, 95, 90, 85])
        benchmark_curve = make_curve([100, 95, 90, 85])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        assert float(result.up_capture) == 0.0

    def test_compute_no_down_days(self) -> None:
        """Down capture = 0 when benchmark has no down days."""
        # All benchmark returns are positive
        strategy_curve = make_curve([100, 110, 121, 133.1])
        benchmark_curve = make_curve([100, 105, 110, 115])

        result = BenchmarkMetrics.compute(strategy_curve, benchmark_curve, "SPY")

        assert result is not None
        assert float(result.down_capture) == 0.0
