"""Benchmark comparison metrics for backtest analysis."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from src.backtest.models import Bar


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


class BenchmarkBuilder:
    """Builder for constructing benchmark equity curves."""

    @staticmethod
    def buy_and_hold(
        bars: list[Bar],
        initial_capital: Decimal,
    ) -> list[tuple[datetime, Decimal]]:
        """Convert price bars to equity curve (buy & hold strategy).

        Normalizes benchmark prices to start at initial_capital.
        Uses bar.close for valuation (EOD, same as strategy equity).

        Args:
            bars: List of Bar objects representing price data.
            initial_capital: Starting capital for normalization.

        Returns:
            List of (timestamp, equity) tuples sorted ascending.
            Returns empty list if bars is empty.
        """
        if not bars:
            return []

        first_close = bars[0].close
        return [(bar.timestamp, (bar.close / first_close) * initial_capital) for bar in bars]
