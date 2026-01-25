"""Backtest engine for historical strategy testing."""

from src.backtest.bar_loader import BarLoader, CSVBarLoader
from src.backtest.benchmark import BenchmarkBuilder, BenchmarkComparison
from src.backtest.benchmark_metrics import BenchmarkMetrics
from src.backtest.engine import BacktestEngine
from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.math_utils import (
    calculate_returns,
    decimal_covariance,
    decimal_mean,
    decimal_ols,
    decimal_variance,
)
from src.backtest.metrics import MetricsCalculator
from src.backtest.models import BacktestConfig, BacktestResult, Bar, Trade
from src.backtest.portfolio import BacktestPortfolio
from src.backtest.trace import (
    BarSnapshot,
    JsonScalar,
    PortfolioSnapshot,
    SignalTrace,
    StrategySnapshot,
)
from src.backtest.trace_builder import TraceBuilder

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestPortfolio",
    "BacktestResult",
    "Bar",
    "BarLoader",
    "BenchmarkBuilder",
    "BenchmarkComparison",
    "BenchmarkMetrics",
    "CSVBarLoader",
    "MetricsCalculator",
    "SimulatedFillEngine",
    "Trade",
    "calculate_returns",
    "decimal_covariance",
    "decimal_mean",
    "decimal_ols",
    "decimal_variance",
    "BarSnapshot",
    "PortfolioSnapshot",
    "StrategySnapshot",
    "SignalTrace",
    "JsonScalar",
    "TraceBuilder",
]
