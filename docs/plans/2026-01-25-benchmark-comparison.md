# Benchmark Comparison Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Compare strategy backtest performance against a benchmark (SPY) with alpha, beta, and risk-adjusted metrics.

**Architecture:** Extend backtest engine to optionally load benchmark bars, build benchmark equity curve (buy&hold), compute comparison metrics via OLS regression. BenchmarkComparison dataclass nested in BacktestResult.

**Tech Stack:** Python dataclasses, Decimal math utilities (no numpy/pandas for MVP)

---

## Design Decisions

### Data Flow

```
BacktestConfig
  ├── symbol: "AAPL"
  └── benchmark_symbol: "SPY" (optional, default None)

CSVBarLoader.load("AAPL", start, end) → strategy_bars
CSVBarLoader.load("SPY", start, end)  → benchmark_bars

BacktestEngine.run(strategy_bars) → strategy_equity_curve

BenchmarkBuilder.buy_and_hold(benchmark_bars, initial_capital)
  → benchmark_equity_curve
  (normalized: benchmark_equity[t] = (SPY[t]/SPY[0]) * initial_capital)

BenchmarkMetrics.compute(
  strategy_equity_curve,
  benchmark_equity_curve
)
  → BenchmarkComparison dataclass

BacktestResult.benchmark = BenchmarkComparison | None
```

### Semantic Rules (Hardcoded)

| Rule | Decision |
|------|----------|
| Benchmark equity valuation | `bar.close` (EOD, same as strategy) |
| Returns formula | `r_t = (V_t - V_{t-1}) / V_{t-1}` |
| Alignment | Inner join on timestamp (timezone-aware) |
| Min data points | `len(aligned) >= 2`, else return None |
| Risk-free rate | `rf = 0` (hardcoded constant) |
| Alpha | OLS regression intercept: `r_s = alpha + beta * r_b + ε` |
| Alpha annualization | `alpha_annual = alpha_daily * 252` |
| Tracking error | `std(residuals) * sqrt(252)` |
| Information ratio | `alpha_annual / tracking_error` |
| Sortino downside | Based on 0: `downside_dev = std(min(r_t, 0))` |
| Sortino formula | `mean(r) / downside_dev * sqrt(252)` |
| Var(benchmark) = 0 | `beta = 0`, `alpha = mean(r_s) * 252` |
| tracking_error = 0 | `information_ratio = 0` |
| downside_dev = 0 | `sortino_ratio = 0` |
| No up days or up_mean = 0 | `up_capture = 0` |
| No down days or down_mean = 0 | `down_capture = 0` |
| math_utils precision | Decimal→float for OLS, output as Decimal |

---

## Task 1: Math Utilities

**Files:**
- Create: `backend/src/backtest/math_utils.py`
- Test: `backend/tests/backtest/test_math_utils.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_math_utils.py
import pytest
from decimal import Decimal
from src.backtest.math_utils import (
    calculate_returns,
    decimal_mean,
    decimal_variance,
    decimal_covariance,
    decimal_ols,
)


class TestCalculateReturns:
    def test_returns_from_equity_curve(self):
        """Returns are (V_t - V_{t-1}) / V_{t-1}."""
        curve = [Decimal("100"), Decimal("110"), Decimal("99")]
        returns = calculate_returns(curve)
        assert len(returns) == 2
        assert returns[0] == pytest.approx(0.10, rel=1e-9)  # 110/100 - 1
        assert returns[1] == pytest.approx(-0.10, rel=1e-9)  # 99/110 - 1

    def test_returns_empty_or_single(self):
        """Empty or single value returns empty list."""
        assert calculate_returns([]) == []
        assert calculate_returns([Decimal("100")]) == []

    def test_returns_zero_prev_value(self):
        """Zero previous value returns 0 for that period."""
        curve = [Decimal("0"), Decimal("100")]
        returns = calculate_returns(curve)
        assert returns[0] == 0.0


class TestDecimalMean:
    def test_mean_basic(self):
        data = [Decimal("1"), Decimal("2"), Decimal("3")]
        assert decimal_mean(data) == pytest.approx(2.0, rel=1e-9)

    def test_mean_empty(self):
        assert decimal_mean([]) == 0.0


class TestDecimalVariance:
    def test_variance_basic(self):
        """Sample variance with n-1 denominator."""
        data = [Decimal("2"), Decimal("4"), Decimal("4"), Decimal("4"), Decimal("5"), Decimal("5"), Decimal("7"), Decimal("9")]
        # Mean = 5, variance = 4.571...
        assert decimal_variance(data) == pytest.approx(4.571428571, rel=1e-6)

    def test_variance_single_or_empty(self):
        assert decimal_variance([]) == 0.0
        assert decimal_variance([Decimal("5")]) == 0.0


class TestDecimalCovariance:
    def test_covariance_basic(self):
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("2"), Decimal("4"), Decimal("6")]
        # Perfect correlation, cov = 2.0
        assert decimal_covariance(x, y) == pytest.approx(2.0, rel=1e-9)

    def test_covariance_different_lengths(self):
        """Different length arrays raise ValueError."""
        with pytest.raises(ValueError):
            decimal_covariance([Decimal("1")], [Decimal("1"), Decimal("2")])


class TestDecimalOLS:
    def test_ols_perfect_fit(self):
        """y = 2 + 3x should give alpha=2, beta=3."""
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("5"), Decimal("8"), Decimal("11")]  # 2 + 3*x
        alpha, beta, residuals = decimal_ols(x, y)
        assert alpha == pytest.approx(2.0, rel=1e-9)
        assert beta == pytest.approx(3.0, rel=1e-9)
        assert all(r == pytest.approx(0.0, abs=1e-9) for r in residuals)

    def test_ols_zero_variance_x(self):
        """Zero variance in x returns beta=0, alpha=mean(y)."""
        x = [Decimal("5"), Decimal("5"), Decimal("5")]
        y = [Decimal("1"), Decimal("2"), Decimal("3")]
        alpha, beta, residuals = decimal_ols(x, y)
        assert beta == pytest.approx(0.0, rel=1e-9)
        assert alpha == pytest.approx(2.0, rel=1e-9)  # mean(y)

    def test_ols_empty_or_single(self):
        """Empty or single point returns zeros."""
        alpha, beta, residuals = decimal_ols([], [])
        assert alpha == 0.0
        assert beta == 0.0
        assert residuals == []
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_math_utils.py -v`
Expected: FAIL with "ModuleNotFoundError" or "ImportError"

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/math_utils.py
"""Math utilities for benchmark metrics calculation.

Uses float internally for statistics, outputs Decimal where needed.
"""

from decimal import Decimal


def calculate_returns(equity_values: list[Decimal]) -> list[float]:
    """Convert equity curve to returns series.

    Args:
        equity_values: List of equity values (not timestamps).

    Returns:
        List of returns: r_t = (V_t - V_{t-1}) / V_{t-1}
        Length is len(equity_values) - 1.
    """
    if len(equity_values) < 2:
        return []

    returns: list[float] = []
    for i in range(1, len(equity_values)):
        prev = float(equity_values[i - 1])
        curr = float(equity_values[i])
        if prev == 0:
            returns.append(0.0)
        else:
            returns.append((curr - prev) / prev)
    return returns


def decimal_mean(data: list[Decimal]) -> float:
    """Compute mean of Decimal list, return as float."""
    if not data:
        return 0.0
    return sum(float(d) for d in data) / len(data)


def decimal_variance(data: list[Decimal]) -> float:
    """Compute sample variance (n-1 denominator) of Decimal list."""
    if len(data) < 2:
        return 0.0

    values = [float(d) for d in data]
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / (len(values) - 1)


def decimal_covariance(x: list[Decimal], y: list[Decimal]) -> float:
    """Compute sample covariance of two Decimal lists."""
    if len(x) != len(y):
        raise ValueError("Arrays must have same length")

    if len(x) < 2:
        return 0.0

    x_vals = [float(d) for d in x]
    y_vals = [float(d) for d in y]

    x_mean = sum(x_vals) / len(x_vals)
    y_mean = sum(y_vals) / len(y_vals)

    return sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x_vals, y_vals)) / (len(x_vals) - 1)


def decimal_ols(x: list[Decimal], y: list[Decimal]) -> tuple[float, float, list[float]]:
    """Ordinary Least Squares regression: y = alpha + beta * x + residuals.

    Args:
        x: Independent variable (benchmark returns).
        y: Dependent variable (strategy returns).

    Returns:
        Tuple of (alpha, beta, residuals).
        If variance(x) = 0: beta=0, alpha=mean(y).
    """
    if len(x) < 2 or len(x) != len(y):
        return 0.0, 0.0, []

    x_vals = [float(d) for d in x]
    y_vals = [float(d) for d in y]

    x_mean = sum(x_vals) / len(x_vals)
    y_mean = sum(y_vals) / len(y_vals)

    # Variance of x
    var_x = sum((xi - x_mean) ** 2 for xi in x_vals) / (len(x_vals) - 1)

    if var_x == 0:
        # No variance in benchmark, can't compute beta
        return y_mean, 0.0, [yi - y_mean for yi in y_vals]

    # Covariance
    cov_xy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x_vals, y_vals)) / (len(x_vals) - 1)

    beta = cov_xy / var_x
    alpha = y_mean - beta * x_mean

    residuals = [yi - (alpha + beta * xi) for xi, yi in zip(x_vals, y_vals)]

    return alpha, beta, residuals
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_math_utils.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/math_utils.py backend/tests/backtest/test_math_utils.py
git commit -m "feat(backtest): add math utilities for benchmark metrics"
```

---

## Task 2: BenchmarkComparison Dataclass

**Files:**
- Create: `backend/src/backtest/benchmark.py`
- Test: `backend/tests/backtest/test_benchmark.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_benchmark.py
from decimal import Decimal
from src.backtest.benchmark import BenchmarkComparison


class TestBenchmarkComparison:
    def test_create_benchmark_comparison(self):
        """Can create frozen BenchmarkComparison dataclass."""
        comparison = BenchmarkComparison(
            benchmark_symbol="SPY",
            benchmark_total_return=Decimal("0.10"),
            alpha=Decimal("0.05"),
            beta=Decimal("0.8"),
            tracking_error=Decimal("0.02"),
            information_ratio=Decimal("2.5"),
            sortino_ratio=Decimal("1.8"),
            up_capture=Decimal("1.1"),
            down_capture=Decimal("0.9"),
        )
        assert comparison.benchmark_symbol == "SPY"
        assert comparison.alpha == Decimal("0.05")
        assert comparison.beta == Decimal("0.8")

    def test_benchmark_comparison_is_frozen(self):
        """BenchmarkComparison is immutable."""
        comparison = BenchmarkComparison(
            benchmark_symbol="SPY",
            benchmark_total_return=Decimal("0.10"),
            alpha=Decimal("0.05"),
            beta=Decimal("0.8"),
            tracking_error=Decimal("0.02"),
            information_ratio=Decimal("2.5"),
            sortino_ratio=Decimal("1.8"),
            up_capture=Decimal("1.1"),
            down_capture=Decimal("0.9"),
        )
        import pytest
        with pytest.raises(Exception):  # FrozenInstanceError
            comparison.alpha = Decimal("0.10")
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_benchmark.py::TestBenchmarkComparison -v`
Expected: FAIL with "ImportError"

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/benchmark.py
"""Benchmark comparison models and builders."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class BenchmarkComparison:
    """Benchmark comparison metrics (all annualized where applicable).

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
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_benchmark.py::TestBenchmarkComparison -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/benchmark.py backend/tests/backtest/test_benchmark.py
git commit -m "feat(backtest): add BenchmarkComparison dataclass"
```

---

## Task 3: BenchmarkBuilder.buy_and_hold

**Files:**
- Modify: `backend/src/backtest/benchmark.py`
- Test: `backend/tests/backtest/test_benchmark.py`

**Step 1: Write failing tests**

```python
# Add to backend/tests/backtest/test_benchmark.py
from datetime import datetime, timezone
from decimal import Decimal
from src.backtest.models import Bar
from src.backtest.benchmark import BenchmarkBuilder


class TestBenchmarkBuilder:
    def test_buy_and_hold_basic(self):
        """Buy and hold normalizes bars to initial capital."""
        bars = [
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("102"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000000,
            ),
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("100"),
                close=Decimal("110"),
                volume=1000000,
            ),
        ]
        initial_capital = Decimal("10000")

        curve = BenchmarkBuilder.buy_and_hold(bars, initial_capital)

        assert len(curve) == 2
        assert curve[0][0] == bars[0].timestamp
        assert curve[0][1] == Decimal("10000")  # (100/100) * 10000
        assert curve[1][1] == Decimal("11000")  # (110/100) * 10000

    def test_buy_and_hold_empty_bars(self):
        """Empty bars returns empty curve."""
        curve = BenchmarkBuilder.buy_and_hold([], Decimal("10000"))
        assert curve == []

    def test_buy_and_hold_uses_close_price(self):
        """Equity is based on bar.close, not open/high/low."""
        bars = [
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
                open=Decimal("90"),
                high=Decimal("110"),
                low=Decimal("80"),
                close=Decimal("100"),  # Only close matters
                volume=1000000,
            ),
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc),
                open=Decimal("95"),
                high=Decimal("115"),
                low=Decimal("85"),
                close=Decimal("105"),  # 5% gain
                volume=1000000,
            ),
        ]
        initial_capital = Decimal("1000")

        curve = BenchmarkBuilder.buy_and_hold(bars, initial_capital)

        assert curve[1][1] == Decimal("1050")  # (105/100) * 1000
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_benchmark.py::TestBenchmarkBuilder -v`
Expected: FAIL with "ImportError" or "AttributeError"

**Step 3: Write minimal implementation**

```python
# Add to backend/src/backtest/benchmark.py
from datetime import datetime
from src.backtest.models import Bar


class BenchmarkBuilder:
    """Builds benchmark equity curves from bar data."""

    @staticmethod
    def buy_and_hold(
        bars: list[Bar],
        initial_capital: Decimal,
    ) -> list[tuple[datetime, Decimal]]:
        """Convert price bars to equity curve (buy & hold strategy).

        Normalizes benchmark prices to start at initial_capital.
        Uses bar.close for valuation (EOD, same as strategy equity).

        Args:
            bars: List of Bar objects sorted ascending by timestamp.
            initial_capital: Starting capital for normalization.

        Returns:
            List of (timestamp, equity) tuples sorted ascending.
            Returns empty list if bars is empty.
        """
        if not bars:
            return []

        first_close = bars[0].close

        return [
            (bar.timestamp, (bar.close / first_close) * initial_capital)
            for bar in bars
        ]
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_benchmark.py::TestBenchmarkBuilder -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/benchmark.py backend/tests/backtest/test_benchmark.py
git commit -m "feat(backtest): add BenchmarkBuilder.buy_and_hold"
```

---

## Task 4: BenchmarkMetrics.compute

**Files:**
- Create: `backend/src/backtest/benchmark_metrics.py`
- Test: `backend/tests/backtest/test_benchmark_metrics.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_benchmark_metrics.py
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from src.backtest.benchmark_metrics import BenchmarkMetrics
from src.backtest.benchmark import BenchmarkComparison


def make_curve(values: list[float], start_day: int = 1) -> list[tuple[datetime, Decimal]]:
    """Helper to create equity curve from values."""
    return [
        (datetime(2024, 1, start_day + i, 21, 0, tzinfo=timezone.utc), Decimal(str(v)))
        for i, v in enumerate(values)
    ]


class TestBenchmarkMetrics:
    def test_compute_returns_benchmark_comparison(self):
        """Compute returns a BenchmarkComparison dataclass."""
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 105, 110.25])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert isinstance(result, BenchmarkComparison)
        assert result.benchmark_symbol == "SPY"

    def test_compute_benchmark_total_return(self):
        """Benchmark total return is (final - initial) / initial."""
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 105, 110])  # 10% total return

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert result.benchmark_total_return == pytest.approx(Decimal("0.10"), rel=1e-6)

    def test_compute_beta_positive_correlation(self):
        """Beta > 0 when strategy moves with benchmark."""
        # Both go up 10% then 10%
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 110, 121])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert float(result.beta) == pytest.approx(1.0, rel=1e-6)

    def test_compute_alpha_with_outperformance(self):
        """Alpha > 0 when strategy beats benchmark."""
        # Strategy: 10% then 10% = 21% total
        # Benchmark: 5% then 5% = 10.25% total
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 105, 110.25])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        # Alpha should be positive (strategy outperformed)
        assert float(result.alpha) > 0

    def test_compute_tracking_error(self):
        """Tracking error is std(residuals) * sqrt(252)."""
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 105, 115])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        # Should be positive when returns differ
        assert float(result.tracking_error) > 0

    def test_compute_information_ratio(self):
        """Information ratio is alpha / tracking_error."""
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 105, 110.25])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        # Should match alpha / tracking_error
        if float(result.tracking_error) > 0:
            expected_ir = float(result.alpha) / float(result.tracking_error)
            assert float(result.information_ratio) == pytest.approx(expected_ir, rel=1e-6)

    def test_compute_sortino_positive_returns(self):
        """Sortino ratio is positive for positive returns."""
        strategy = make_curve([100, 110, 121])  # All positive returns
        benchmark = make_curve([100, 105, 110])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert float(result.sortino_ratio) > 0

    def test_compute_sortino_zero_downside(self):
        """Sortino is 0 when no downside deviation."""
        # No negative returns
        strategy = make_curve([100, 110, 120])
        benchmark = make_curve([100, 105, 110])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        # downside_dev = 0, so sortino = 0
        assert float(result.sortino_ratio) == 0.0

    def test_compute_up_capture(self):
        """Up capture compares strategy vs benchmark on up days."""
        # Day 1: benchmark up 10%, strategy up 15%
        # Day 2: benchmark down 5%, strategy down 3%
        strategy = make_curve([100, 115, 111.55])
        benchmark = make_curve([100, 110, 104.5])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        # Up capture = strategy_up / benchmark_up = 15% / 10% = 1.5
        assert float(result.up_capture) == pytest.approx(1.5, rel=1e-2)

    def test_compute_down_capture(self):
        """Down capture compares strategy vs benchmark on down days."""
        # Day 1: benchmark up 10%, strategy up 15%
        # Day 2: benchmark down 5%, strategy down 3%
        strategy = make_curve([100, 115, 111.55])
        benchmark = make_curve([100, 110, 104.5])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        # Down capture = strategy_down / benchmark_down = -3% / -5% = 0.6
        # (strategy lost less)
        assert float(result.down_capture) == pytest.approx(0.6, rel=1e-2)

    def test_compute_insufficient_data_returns_none(self):
        """Less than 2 aligned points returns None."""
        strategy = make_curve([100])
        benchmark = make_curve([100])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert result is None

    def test_compute_no_overlap_returns_none(self):
        """No overlapping timestamps returns None."""
        strategy = make_curve([100, 110], start_day=1)
        benchmark = make_curve([100, 110], start_day=10)  # Different dates

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert result is None

    def test_compute_zero_benchmark_variance(self):
        """Zero benchmark variance: beta=0, alpha=mean(strategy_returns)*252."""
        strategy = make_curve([100, 110, 121])
        benchmark = make_curve([100, 100, 100])  # No movement

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert float(result.beta) == 0.0
        # Alpha should be annualized mean of strategy returns
        # Strategy returns: 10%, 10% -> mean = 10% -> annualized = 10% * 252
        assert float(result.alpha) == pytest.approx(0.10 * 252, rel=1e-2)

    def test_compute_no_up_days(self):
        """No up days: up_capture = 0."""
        strategy = make_curve([100, 95, 90])
        benchmark = make_curve([100, 95, 90])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert float(result.up_capture) == 0.0

    def test_compute_no_down_days(self):
        """No down days: down_capture = 0."""
        strategy = make_curve([100, 110, 120])
        benchmark = make_curve([100, 110, 120])

        result = BenchmarkMetrics.compute(strategy, benchmark, "SPY")

        assert float(result.down_capture) == 0.0
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_benchmark_metrics.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/benchmark_metrics.py
"""Benchmark comparison metrics calculator."""

from datetime import datetime
from decimal import Decimal

from src.backtest.benchmark import BenchmarkComparison
from src.backtest.math_utils import calculate_returns, decimal_ols


ANNUALIZATION_FACTOR = 252
RISK_FREE_RATE = 0.0


class BenchmarkMetrics:
    """Computes benchmark comparison metrics from equity curves."""

    @staticmethod
    def compute(
        strategy_curve: list[tuple[datetime, Decimal]],
        benchmark_curve: list[tuple[datetime, Decimal]],
        benchmark_symbol: str,
    ) -> BenchmarkComparison | None:
        """Compute all benchmark comparison metrics.

        Args:
            strategy_curve: Strategy equity curve [(timestamp, equity), ...].
            benchmark_curve: Benchmark equity curve [(timestamp, equity), ...].
            benchmark_symbol: Symbol name for the benchmark.

        Returns:
            BenchmarkComparison dataclass or None if insufficient data.
        """
        # Align curves by timestamp (inner join)
        aligned = BenchmarkMetrics._align_curves(strategy_curve, benchmark_curve)

        if len(aligned) < 2:
            return None

        strategy_values = [eq for _, eq, _ in aligned]
        benchmark_values = [eq for _, _, eq in aligned]

        # Calculate returns
        strategy_returns = calculate_returns(strategy_values)
        benchmark_returns = calculate_returns(benchmark_values)

        if len(strategy_returns) < 1:
            return None

        # Benchmark total return
        benchmark_total_return = (
            float(benchmark_values[-1]) - float(benchmark_values[0])
        ) / float(benchmark_values[0])

        # OLS regression: r_strategy = alpha + beta * r_benchmark + residuals
        strategy_decimals = [Decimal(str(r)) for r in strategy_returns]
        benchmark_decimals = [Decimal(str(r)) for r in benchmark_returns]

        alpha_daily, beta, residuals = decimal_ols(benchmark_decimals, strategy_decimals)

        # Annualize alpha
        alpha = alpha_daily * ANNUALIZATION_FACTOR

        # Tracking error = std(residuals) * sqrt(252)
        tracking_error = BenchmarkMetrics._std(residuals) * (ANNUALIZATION_FACTOR ** 0.5)

        # Information ratio = alpha / tracking_error
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
            benchmark_total_return=Decimal(str(round(benchmark_total_return, 10))),
            alpha=Decimal(str(round(alpha, 10))),
            beta=Decimal(str(round(beta, 10))),
            tracking_error=Decimal(str(round(tracking_error, 10))),
            information_ratio=Decimal(str(round(information_ratio, 10))),
            sortino_ratio=Decimal(str(round(sortino_ratio, 10))),
            up_capture=Decimal(str(round(up_capture, 10))),
            down_capture=Decimal(str(round(down_capture, 10))),
        )

    @staticmethod
    def _align_curves(
        strategy_curve: list[tuple[datetime, Decimal]],
        benchmark_curve: list[tuple[datetime, Decimal]],
    ) -> list[tuple[datetime, Decimal, Decimal]]:
        """Align two curves by timestamp (inner join).

        Returns:
            List of (timestamp, strategy_equity, benchmark_equity) tuples.
        """
        benchmark_map = {ts: eq for ts, eq in benchmark_curve}

        aligned = []
        for ts, strategy_eq in strategy_curve:
            if ts in benchmark_map:
                aligned.append((ts, strategy_eq, benchmark_map[ts]))

        return sorted(aligned, key=lambda x: x[0])

    @staticmethod
    def _std(values: list[float]) -> float:
        """Compute sample standard deviation."""
        if len(values) < 2:
            return 0.0

        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return variance ** 0.5

    @staticmethod
    def _compute_sortino(returns: list[float]) -> float:
        """Compute Sortino ratio: mean(r) / downside_dev * sqrt(252).

        Downside deviation based on 0 (only penalize negative returns).
        """
        if len(returns) < 1:
            return 0.0

        mean_return = sum(returns) / len(returns)

        # Downside returns (only negatives)
        downside = [min(r, 0) for r in returns]

        if len(downside) < 2:
            return 0.0

        # Downside deviation
        downside_mean = sum(downside) / len(downside)
        downside_variance = sum((d - downside_mean) ** 2 for d in downside) / (len(downside) - 1)
        downside_dev = downside_variance ** 0.5

        if downside_dev == 0:
            return 0.0

        return (mean_return / downside_dev) * (ANNUALIZATION_FACTOR ** 0.5)

    @staticmethod
    def _compute_capture_ratios(
        strategy_returns: list[float],
        benchmark_returns: list[float],
    ) -> tuple[float, float]:
        """Compute up/down capture ratios.

        Up capture = mean(strategy up) / mean(benchmark up)
        Down capture = mean(strategy down) / mean(benchmark down)

        Returns (up_capture, down_capture).
        """
        up_strategy = []
        up_benchmark = []
        down_strategy = []
        down_benchmark = []

        for s, b in zip(strategy_returns, benchmark_returns):
            if b > 0:
                up_strategy.append(s)
                up_benchmark.append(b)
            elif b < 0:
                down_strategy.append(s)
                down_benchmark.append(b)

        # Up capture
        if up_benchmark and sum(up_benchmark) != 0:
            up_capture = (sum(up_strategy) / len(up_strategy)) / (sum(up_benchmark) / len(up_benchmark))
        else:
            up_capture = 0.0

        # Down capture
        if down_benchmark and sum(down_benchmark) != 0:
            down_capture = (sum(down_strategy) / len(down_strategy)) / (sum(down_benchmark) / len(down_benchmark))
        else:
            down_capture = 0.0

        return up_capture, down_capture
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_benchmark_metrics.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/benchmark_metrics.py backend/tests/backtest/test_benchmark_metrics.py
git commit -m "feat(backtest): add BenchmarkMetrics.compute with OLS alpha/beta"
```

---

## Task 5: Update BacktestConfig with benchmark_symbol

**Files:**
- Modify: `backend/src/backtest/models.py`
- Test: `backend/tests/backtest/test_models.py`

**Step 1: Write failing test**

```python
# Add to backend/tests/backtest/test_models.py
def test_backtest_config_benchmark_symbol_optional():
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/backtest/test_models.py::test_backtest_config_benchmark_symbol_optional -v`
Expected: FAIL with "TypeError"

**Step 3: Write minimal implementation**

Add to `BacktestConfig` in `backend/src/backtest/models.py`:

```python
@dataclass
class BacktestConfig:
    # ... existing fields ...
    benchmark_symbol: str | None = None  # Add this field
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/backtest/test_models.py::test_backtest_config_benchmark_symbol_optional -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/models.py backend/tests/backtest/test_models.py
git commit -m "feat(backtest): add benchmark_symbol to BacktestConfig"
```

---

## Task 6: Update BacktestResult with benchmark field

**Files:**
- Modify: `backend/src/backtest/models.py`
- Test: `backend/tests/backtest/test_models.py`

**Step 1: Write failing test**

```python
# Add to backend/tests/backtest/test_models.py
from src.backtest.benchmark import BenchmarkComparison

def test_backtest_result_benchmark_field():
    """BacktestResult has optional benchmark field."""
    result = BacktestResult(
        config=BacktestConfig(...),
        equity_curve=[],
        trades=[],
        final_equity=Decimal("100000"),
        final_cash=Decimal("100000"),
        final_position_qty=0,
        total_return=Decimal("0"),
        annualized_return=Decimal("0"),
        sharpe_ratio=Decimal("0"),
        max_drawdown=Decimal("0"),
        win_rate=Decimal("0"),
        total_trades=0,
        avg_trade_pnl=Decimal("0"),
        warm_up_required_bars=0,
        warm_up_bars_used=0,
        first_signal_bar=None,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
    )
    assert result.benchmark is None

    comparison = BenchmarkComparison(
        benchmark_symbol="SPY",
        benchmark_total_return=Decimal("0.10"),
        alpha=Decimal("0.05"),
        beta=Decimal("0.8"),
        tracking_error=Decimal("0.02"),
        information_ratio=Decimal("2.5"),
        sortino_ratio=Decimal("1.8"),
        up_capture=Decimal("1.1"),
        down_capture=Decimal("0.9"),
    )
    result_with_benchmark = BacktestResult(
        # ... same fields ...
        benchmark=comparison,
    )
    assert result_with_benchmark.benchmark == comparison
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/backtest/test_models.py::test_backtest_result_benchmark_field -v`
Expected: FAIL with "TypeError"

**Step 3: Write minimal implementation**

Add to `BacktestResult` in `backend/src/backtest/models.py`:

```python
from src.backtest.benchmark import BenchmarkComparison

@dataclass
class BacktestResult:
    # ... existing fields ...
    benchmark: BenchmarkComparison | None = None  # Add this field
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/backtest/test_models.py::test_backtest_result_benchmark_field -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/models.py backend/tests/backtest/test_models.py
git commit -m "feat(backtest): add benchmark field to BacktestResult"
```

---

## Task 7: Integrate Benchmark into BacktestEngine

**Files:**
- Modify: `backend/src/backtest/engine.py`
- Test: `backend/tests/backtest/test_engine.py`

**Step 1: Write failing test**

```python
# Add to backend/tests/backtest/test_engine.py
@pytest.mark.asyncio
async def test_engine_with_benchmark(tmp_path):
    """Engine computes benchmark comparison when benchmark_symbol provided."""
    # Create CSV with both AAPL and SPY bars
    csv_content = """timestamp,symbol,open,high,low,close,volume
2024-01-02T21:00:00+00:00,AAPL,100.00,102.00,99.00,100.00,1000000
2024-01-03T21:00:00+00:00,AAPL,100.00,110.00,100.00,110.00,1000000
2024-01-04T21:00:00+00:00,AAPL,110.00,120.00,110.00,121.00,1000000
2024-01-02T21:00:00+00:00,SPY,400.00,405.00,398.00,400.00,5000000
2024-01-03T21:00:00+00:00,SPY,400.00,410.00,400.00,420.00,5000000
2024-01-04T21:00:00+00:00,SPY,420.00,430.00,420.00,440.00,5000000
"""
    csv_file = tmp_path / "bars.csv"
    csv_file.write_text(csv_content)

    config = BacktestConfig(
        strategy_class="src.strategies.examples.momentum.MomentumStrategy",
        strategy_params={"lookback_period": 1, "threshold": 0.5, "position_size": 10},
        symbol="AAPL",
        start_date=date(2024, 1, 1),
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
async def test_engine_without_benchmark(tmp_path):
    """Engine returns benchmark=None when no benchmark_symbol."""
    csv_content = """timestamp,symbol,open,high,low,close,volume
2024-01-02T21:00:00+00:00,AAPL,100.00,102.00,99.00,100.00,1000000
2024-01-03T21:00:00+00:00,AAPL,100.00,110.00,100.00,110.00,1000000
"""
    csv_file = tmp_path / "bars.csv"
    csv_file.write_text(csv_content)

    config = BacktestConfig(
        strategy_class="src.strategies.examples.momentum.MomentumStrategy",
        strategy_params={"lookback_period": 1, "threshold": 0.5, "position_size": 10},
        symbol="AAPL",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 5),
        initial_capital=Decimal("10000"),
        # No benchmark_symbol
    )

    loader = CSVBarLoader(csv_file)
    engine = BacktestEngine(loader)
    result = await engine.run(config)

    assert result.benchmark is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_engine.py::test_engine_with_benchmark tests/backtest/test_engine.py::test_engine_without_benchmark -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Modify `BacktestEngine.run()` in `backend/src/backtest/engine.py`:

```python
from src.backtest.benchmark import BenchmarkBuilder
from src.backtest.benchmark_metrics import BenchmarkMetrics

async def run(self, config: BacktestConfig) -> BacktestResult:
    # ... existing backtest logic ...

    # Compute benchmark comparison if benchmark_symbol provided
    benchmark = None
    if config.benchmark_symbol:
        benchmark_bars = await self._bar_loader.load(
            config.benchmark_symbol,
            config.start_date,
            config.end_date,
        )
        if benchmark_bars:
            benchmark_curve = BenchmarkBuilder.buy_and_hold(
                benchmark_bars, config.initial_capital
            )
            benchmark = BenchmarkMetrics.compute(
                equity_curve, benchmark_curve, config.benchmark_symbol
            )

    return BacktestResult(
        # ... existing fields ...
        benchmark=benchmark,
    )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_engine.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/engine.py backend/tests/backtest/test_engine.py
git commit -m "feat(backtest): integrate benchmark comparison into engine"
```

---

## Task 8: Update Backtest API Schema

**Files:**
- Modify: `backend/src/api/backtest.py`
- Test: `backend/tests/api/test_backtest.py`

**Step 1: Write failing test**

```python
# Add to backend/tests/api/test_backtest.py
def test_backtest_response_includes_benchmark():
    """Response schema includes benchmark comparison fields."""
    # Test that API response includes benchmark when provided
    ...
```

**Step 2-5: Implement and test**

Update `BacktestRequest` and `BacktestResponse` Pydantic schemas to include:
- `benchmark_symbol: str | None = None` in request
- `benchmark: BenchmarkComparisonResponse | None` in response

**Commit:**

```bash
git commit -m "feat(api): add benchmark fields to backtest API schema"
```

---

## Task 9: Update Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

Add TypeScript types:

```typescript
export interface BenchmarkComparison {
  benchmark_symbol: string;
  benchmark_total_return: string;
  alpha: string;
  beta: string;
  tracking_error: string;
  information_ratio: string;
  sortino_ratio: string;
  up_capture: string;
  down_capture: string;
}

export interface BacktestResult {
  // ... existing fields ...
  benchmark: BenchmarkComparison | null;
}

export interface BacktestRequest {
  // ... existing fields ...
  benchmark_symbol?: string;
}
```

**Commit:**

```bash
git commit -m "feat(frontend): add benchmark types"
```

---

## Task 10: Update BacktestForm with Benchmark Input

**Files:**
- Modify: `frontend/src/components/BacktestForm.tsx`
- Test: `frontend/src/components/BacktestForm.test.tsx`

Add benchmark_symbol input field (default "SPY"):

```tsx
<input
  type="text"
  id="benchmark-symbol"
  value={benchmarkSymbol}
  onChange={(e) => setBenchmarkSymbol(e.target.value.toUpperCase())}
/>
```

**Commit:**

```bash
git commit -m "feat(frontend): add benchmark symbol input to form"
```

---

## Task 11: Update BacktestResults with Benchmark Metrics

**Files:**
- Modify: `frontend/src/components/BacktestResults.tsx`
- Test: `frontend/src/components/BacktestResults.test.tsx`

Add benchmark metrics section:

```tsx
{result.benchmark && (
  <div className="benchmark-section">
    <h3>vs {result.benchmark.benchmark_symbol}</h3>
    <MetricRow label="Alpha" value={formatPercent(result.benchmark.alpha)} />
    <MetricRow label="Beta" value={result.benchmark.beta} />
    <MetricRow label="Information Ratio" value={result.benchmark.information_ratio} />
    <MetricRow label="Sortino Ratio" value={result.benchmark.sortino_ratio} />
    <MetricRow label="Up Capture" value={formatPercent(result.benchmark.up_capture)} />
    <MetricRow label="Down Capture" value={formatPercent(result.benchmark.down_capture)} />
  </div>
)}
```

**Commit:**

```bash
git commit -m "feat(frontend): display benchmark metrics in results"
```

---

## Task 12: Add Benchmark Overlay to Equity Chart

**Files:**
- Modify: `frontend/src/components/EquityChart.tsx`
- Test: `frontend/src/components/EquityChart.test.tsx`

Add second line for benchmark equity curve (normalized):

```tsx
<Line
  type="monotone"
  dataKey="benchmark_equity"
  stroke="#9ca3af"
  strokeDasharray="5 5"
  name={benchmarkSymbol}
/>
```

Note: Backend needs to return benchmark equity curve in response for this.

**Commit:**

```bash
git commit -m "feat(frontend): add benchmark overlay to equity chart"
```

---

## Task 13: Update Module Exports

**Files:**
- Modify: `backend/src/backtest/__init__.py`

Add exports:

```python
from src.backtest.benchmark import BenchmarkBuilder, BenchmarkComparison
from src.backtest.benchmark_metrics import BenchmarkMetrics
from src.backtest.math_utils import (
    calculate_returns,
    decimal_mean,
    decimal_variance,
    decimal_covariance,
    decimal_ols,
)
```

**Commit:**

```bash
git commit -m "feat(backtest): export benchmark modules"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Math utilities | math_utils.py |
| 2 | BenchmarkComparison dataclass | benchmark.py |
| 3 | BenchmarkBuilder.buy_and_hold | benchmark.py |
| 4 | BenchmarkMetrics.compute | benchmark_metrics.py |
| 5 | BacktestConfig.benchmark_symbol | models.py |
| 6 | BacktestResult.benchmark | models.py |
| 7 | Integrate into BacktestEngine | engine.py |
| 8 | Update API schema | api/backtest.py |
| 9 | Frontend types | types/index.ts |
| 10 | Form benchmark input | BacktestForm.tsx |
| 11 | Results benchmark section | BacktestResults.tsx |
| 12 | Chart benchmark overlay | EquityChart.tsx |
| 13 | Module exports | __init__.py |
