"""Benchmark metrics computation for backtest analysis."""

import math
from datetime import datetime
from decimal import Decimal

from src.backtest.benchmark import BenchmarkComparison
from src.backtest.math_utils import calculate_returns, decimal_ols

ANNUALIZATION_FACTOR = 252
RISK_FREE_RATE = 0.0


class BenchmarkMetrics:
    """Computes benchmark comparison metrics using OLS regression."""

    @staticmethod
    def compute(
        strategy_curve: list[tuple[datetime, Decimal]],
        benchmark_curve: list[tuple[datetime, Decimal]],
        benchmark_symbol: str,
    ) -> BenchmarkComparison | None:
        """Compute all benchmark comparison metrics.

        Args:
            strategy_curve: List of (timestamp, equity) tuples for strategy.
            benchmark_curve: List of (timestamp, equity) tuples for benchmark.
            benchmark_symbol: Symbol used as benchmark (e.g., "SPY").

        Returns:
            BenchmarkComparison or None if insufficient data (< 2 aligned points).
        """
        # Align curves by timestamp (inner join)
        aligned_strategy, aligned_benchmark = BenchmarkMetrics._align_curves(
            strategy_curve, benchmark_curve
        )

        if len(aligned_strategy) < 2:
            return None

        # Calculate returns
        strategy_returns = calculate_returns(aligned_strategy)
        benchmark_returns = calculate_returns(aligned_benchmark)

        if len(strategy_returns) < 1:
            return None

        # Calculate benchmark total return
        first_benchmark = aligned_benchmark[0]
        last_benchmark = aligned_benchmark[-1]
        if first_benchmark == 0:
            benchmark_total_return = Decimal("0")
        else:
            benchmark_total_return = (last_benchmark - first_benchmark) / first_benchmark

        # Convert returns to Decimal for OLS
        strategy_returns_dec = [Decimal(str(r)) for r in strategy_returns]
        benchmark_returns_dec = [Decimal(str(r)) for r in benchmark_returns]

        # Perform OLS regression: strategy_returns = alpha + beta * benchmark_returns
        alpha_daily, beta, residuals = decimal_ols(benchmark_returns_dec, strategy_returns_dec)

        # Annualize alpha
        alpha = alpha_daily * ANNUALIZATION_FACTOR

        # Tracking error: std(residuals) * sqrt(252)
        tracking_error = BenchmarkMetrics._std(residuals) * math.sqrt(ANNUALIZATION_FACTOR)

        # Information ratio: alpha / tracking_error
        if tracking_error == 0:
            information_ratio = 0.0
        else:
            information_ratio = alpha / tracking_error

        # Sortino ratio
        sortino_ratio = BenchmarkMetrics._compute_sortino(strategy_returns)

        # Capture ratios
        up_capture, down_capture = BenchmarkMetrics._compute_capture_ratios(
            strategy_returns, benchmark_returns
        )

        return BenchmarkComparison(
            benchmark_symbol=benchmark_symbol,
            benchmark_total_return=Decimal(str(benchmark_total_return)),
            alpha=Decimal(str(alpha)),
            beta=Decimal(str(beta)),
            tracking_error=Decimal(str(tracking_error)),
            information_ratio=Decimal(str(information_ratio)),
            sortino_ratio=Decimal(str(sortino_ratio)),
            up_capture=Decimal(str(up_capture)),
            down_capture=Decimal(str(down_capture)),
        )

    @staticmethod
    def _align_curves(
        strategy_curve: list[tuple[datetime, Decimal]],
        benchmark_curve: list[tuple[datetime, Decimal]],
    ) -> tuple[list[Decimal], list[Decimal]]:
        """Inner join curves by timestamp.

        Args:
            strategy_curve: List of (timestamp, equity) tuples for strategy.
            benchmark_curve: List of (timestamp, equity) tuples for benchmark.

        Returns:
            Tuple of (aligned_strategy_values, aligned_benchmark_values).
        """
        # Create a dictionary for benchmark timestamps
        benchmark_dict = dict(benchmark_curve)

        aligned_strategy: list[Decimal] = []
        aligned_benchmark: list[Decimal] = []

        for ts, value in strategy_curve:
            if ts in benchmark_dict:
                aligned_strategy.append(value)
                aligned_benchmark.append(benchmark_dict[ts])

        return aligned_strategy, aligned_benchmark

    @staticmethod
    def _std(data: list[float]) -> float:
        """Compute sample standard deviation.

        Args:
            data: List of float values.

        Returns:
            Sample standard deviation. Returns 0.0 if len <= 1.
        """
        if len(data) < 2:
            return 0.0

        mean = sum(data) / len(data)
        squared_diffs = [(x - mean) ** 2 for x in data]
        variance = sum(squared_diffs) / (len(data) - 1)
        return math.sqrt(variance)

    @staticmethod
    def _compute_sortino(returns: list[float]) -> float:
        """Compute Sortino ratio.

        Sortino = mean(returns) / downside_dev * sqrt(252)
        Downside deviation is based on returns below 0.

        Args:
            returns: List of returns.

        Returns:
            Sortino ratio. Returns 0.0 if downside_dev is 0.
        """
        if not returns:
            return 0.0

        mean_return = sum(returns) / len(returns)

        # Downside deviation: sqrt(mean of squared negative returns)
        negative_returns = [r for r in returns if r < 0]
        if not negative_returns:
            # No downside returns - sortino is 0 by convention
            return 0.0

        squared_negatives = [r**2 for r in negative_returns]
        downside_variance = sum(squared_negatives) / len(returns)
        downside_dev = math.sqrt(downside_variance)

        if downside_dev == 0:
            return 0.0

        return (mean_return / downside_dev) * math.sqrt(ANNUALIZATION_FACTOR)

    @staticmethod
    def _compute_capture_ratios(
        strategy_returns: list[float],
        benchmark_returns: list[float],
    ) -> tuple[float, float]:
        """Compute up and down capture ratios.

        Up capture: mean(strategy_up) / mean(benchmark_up) on days benchmark > 0
        Down capture: mean(strategy_down) / mean(benchmark_down) on days benchmark < 0

        Args:
            strategy_returns: List of strategy returns.
            benchmark_returns: List of benchmark returns.

        Returns:
            Tuple of (up_capture, down_capture).
        """
        # Up capture: days where benchmark > 0
        up_strategy = []
        up_benchmark = []
        for s_ret, b_ret in zip(strategy_returns, benchmark_returns, strict=False):
            if b_ret > 0:
                up_strategy.append(s_ret)
                up_benchmark.append(b_ret)

        if not up_benchmark:
            up_capture = 0.0
        else:
            up_benchmark_mean = sum(up_benchmark) / len(up_benchmark)
            if up_benchmark_mean == 0:
                up_capture = 0.0
            else:
                up_strategy_mean = sum(up_strategy) / len(up_strategy)
                up_capture = up_strategy_mean / up_benchmark_mean

        # Down capture: days where benchmark < 0
        down_strategy = []
        down_benchmark = []
        for s_ret, b_ret in zip(strategy_returns, benchmark_returns, strict=False):
            if b_ret < 0:
                down_strategy.append(s_ret)
                down_benchmark.append(b_ret)

        if not down_benchmark:
            down_capture = 0.0
        else:
            down_benchmark_mean = sum(down_benchmark) / len(down_benchmark)
            if down_benchmark_mean == 0:
                down_capture = 0.0
            else:
                down_strategy_mean = sum(down_strategy) / len(down_strategy)
                down_capture = down_strategy_mean / down_benchmark_mean

        return up_capture, down_capture
