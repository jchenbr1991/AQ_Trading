"""Benchmark comparison metrics for backtest analysis."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BenchmarkComparison:
    """Holds all benchmark comparison metrics.

    This dataclass stores the results of comparing a strategy's performance
    against a benchmark (e.g., SPY for US equities).

    Attributes:
        benchmark_symbol: Symbol used as benchmark (e.g., "SPY").
        benchmark_total_return: Total return of benchmark over period.
        alpha: OLS regression intercept, annualized (alpha_daily * 252).
        beta: OLS regression slope (sensitivity to benchmark).
        tracking_error: std(residuals) * sqrt(252).
        information_ratio: alpha / tracking_error.
        sortino_ratio: mean(r) / downside_dev * sqrt(252).
        up_capture: Strategy up returns / benchmark up returns.
        down_capture: Strategy down returns / benchmark down returns.
    """

    benchmark_symbol: str
    benchmark_total_return: Decimal
    alpha: Decimal
    beta: Decimal
    tracking_error: Decimal
    information_ratio: Decimal
    sortino_ratio: Decimal
    up_capture: Decimal
    down_capture: Decimal
