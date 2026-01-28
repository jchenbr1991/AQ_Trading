# Greeks Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Greeks monitoring system for real-time portfolio risk tracking with multi-level alerts.

**Architecture:** Event-driven Greeks calculation with 30s backstop polling. Aggregates position-level Greeks to account/strategy level. Three-tier alert system (WARN/CRIT/HARD) with hysteresis recovery. Snapshots saved on critical alerts.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL/TimescaleDB, Redis, Pytest, Pydantic

**Reference Design:** `/home/tochat/aq_trading/docs/plans/2026-01-28-greeks-monitoring-design.md`

---

## Phase 1: Core Data Models (Tasks 1-4)

### Task 1: Create Greeks Module Structure

**Files:**
- Create: `backend/src/greeks/__init__.py`
- Create: `backend/src/greeks/models.py`
- Create: `backend/tests/greeks/__init__.py`
- Create: `backend/tests/greeks/test_models.py`

**Step 1: Create module directories**

```bash
mkdir -p backend/src/greeks
mkdir -p backend/tests/greeks
touch backend/src/greeks/__init__.py
touch backend/tests/greeks/__init__.py
```

**Step 2: Write the failing test for enums**

```python
# backend/tests/greeks/test_models.py
"""Tests for Greeks monitoring data models."""
import pytest
from decimal import Decimal

from src.greeks.models import (
    RiskMetricCategory,
    RiskMetric,
    GreeksDataSource,
    GreeksModel,
    GreeksLevel,
    ThresholdDirection,
)


class TestRiskMetricCategory:
    """Tests for RiskMetricCategory enum."""

    def test_greek_category_exists(self):
        assert RiskMetricCategory.GREEK == "greek"

    def test_volatility_category_exists(self):
        assert RiskMetricCategory.VOLATILITY == "volatility"

    def test_data_quality_category_exists(self):
        assert RiskMetricCategory.DATA_QUALITY == "data_quality"


class TestRiskMetric:
    """Tests for RiskMetric enum with category support."""

    def test_delta_is_greek(self):
        assert RiskMetric.DELTA.is_greek is True
        assert RiskMetric.DELTA.category == RiskMetricCategory.GREEK

    def test_gamma_is_greek(self):
        assert RiskMetric.GAMMA.is_greek is True

    def test_vega_is_greek(self):
        assert RiskMetric.VEGA.is_greek is True

    def test_theta_is_greek(self):
        assert RiskMetric.THETA.is_greek is True

    def test_iv_is_volatility(self):
        assert RiskMetric.IMPLIED_VOLATILITY.is_greek is False
        assert RiskMetric.IMPLIED_VOLATILITY.category == RiskMetricCategory.VOLATILITY

    def test_coverage_is_data_quality(self):
        assert RiskMetric.COVERAGE.is_greek is False
        assert RiskMetric.COVERAGE.category == RiskMetricCategory.DATA_QUALITY


class TestGreeksDataSource:
    """Tests for GreeksDataSource enum."""

    def test_futu_source(self):
        assert GreeksDataSource.FUTU == "futu"

    def test_model_source(self):
        assert GreeksDataSource.MODEL == "model"

    def test_cached_source(self):
        assert GreeksDataSource.CACHED == "cached"


class TestGreeksLevel:
    """Tests for GreeksLevel alert levels."""

    def test_level_ordering(self):
        # Verify levels can be compared for escalation logic
        levels = [GreeksLevel.NORMAL, GreeksLevel.WARN, GreeksLevel.CRIT, GreeksLevel.HARD]
        assert levels == sorted(levels, key=lambda x: x.severity)

    def test_severity_values(self):
        assert GreeksLevel.NORMAL.severity == 0
        assert GreeksLevel.WARN.severity == 1
        assert GreeksLevel.CRIT.severity == 2
        assert GreeksLevel.HARD.severity == 3


class TestThresholdDirection:
    """Tests for ThresholdDirection enum."""

    def test_abs_direction(self):
        assert ThresholdDirection.ABS == "abs"

    def test_max_direction(self):
        assert ThresholdDirection.MAX == "max"

    def test_min_direction(self):
        assert ThresholdDirection.MIN == "min"
```

**Step 3: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_models.py -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'src.greeks.models'"

**Step 4: Write minimal implementation for enums**

```python
# backend/src/greeks/models.py
"""Greeks monitoring data models.

This module defines all data structures for the Greeks monitoring system:
- Enums for metrics, sources, levels, directions
- Dataclasses for position/aggregated Greeks
- Configuration models for thresholds and limits

Reference: docs/plans/2026-01-28-greeks-monitoring-design.md
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal


class RiskMetricCategory(str, Enum):
    """Risk metric classification.

    Separates Greeks from non-Greeks for:
    - AlertEngine branch processing
    - Future extensibility (Skew, Term Structure)
    """
    GREEK = "greek"
    VOLATILITY = "volatility"
    DATA_QUALITY = "data_quality"


class RiskMetric(str, Enum):
    """Risk metric types with category support.

    V1 Design:
    - IV is not a Greek but needs monitoring
    - Each metric belongs to a category for differentiated processing
    - Extensible: SKEW, TERM_STRUCTURE can be added later
    """
    # Greeks (category=GREEK)
    DELTA = "delta"
    GAMMA = "gamma"
    VEGA = "vega"
    THETA = "theta"

    # Volatility (category=VOLATILITY)
    IMPLIED_VOLATILITY = "iv"

    # Data Quality (category=DATA_QUALITY)
    COVERAGE = "coverage"

    @property
    def category(self) -> RiskMetricCategory:
        """Get metric category."""
        if self in (RiskMetric.DELTA, RiskMetric.GAMMA,
                    RiskMetric.VEGA, RiskMetric.THETA):
            return RiskMetricCategory.GREEK
        elif self in (RiskMetric.IMPLIED_VOLATILITY,):
            return RiskMetricCategory.VOLATILITY
        else:
            return RiskMetricCategory.DATA_QUALITY

    @property
    def is_greek(self) -> bool:
        """Check if this is a Greek metric."""
        return self.category == RiskMetricCategory.GREEK


# Backward compatibility alias
GreeksMetric = RiskMetric


class GreeksDataSource(str, Enum):
    """Greeks data source."""
    FUTU = "futu"
    MODEL = "model"
    CACHED = "cached"


class GreeksModel(str, Enum):
    """Greeks calculation model (when source=MODEL or cached_from=MODEL)."""
    FUTU = "futu"
    BS = "bs"                  # Black-Scholes
    BJERKSUND = "bjerksund"    # Bjerksund-Stensland (American)


class GreeksLevel(str, Enum):
    """Alert level with severity ordering."""
    NORMAL = "normal"
    WARN = "warn"
    CRIT = "crit"
    HARD = "hard"

    @property
    def severity(self) -> int:
        """Numeric severity for comparison."""
        return {
            GreeksLevel.NORMAL: 0,
            GreeksLevel.WARN: 1,
            GreeksLevel.CRIT: 2,
            GreeksLevel.HARD: 3,
        }[self]


class ThresholdDirection(str, Enum):
    """Threshold evaluation direction."""
    ABS = "abs"    # abs(value) <= limit
    MAX = "max"    # value <= limit (upper bound)
    MIN = "min"    # value >= limit (lower bound)
```

**Step 5: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_models.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/greeks/ backend/tests/greeks/
git commit -m "feat(greeks): add core enums for Greeks monitoring

- RiskMetricCategory: GREEK, VOLATILITY, DATA_QUALITY
- RiskMetric: with category property and is_greek helper
- GreeksDataSource, GreeksModel, GreeksLevel, ThresholdDirection

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Add PositionGreeks Dataclass

**Files:**
- Modify: `backend/src/greeks/models.py`
- Modify: `backend/tests/greeks/test_models.py`

**Step 1: Write the failing test for PositionGreeks**

```python
# Add to backend/tests/greeks/test_models.py

from src.greeks.models import PositionGreeks


class TestPositionGreeks:
    """Tests for PositionGreeks dataclass."""

    def test_create_minimal(self):
        pg = PositionGreeks(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            underlying_price=Decimal("150.00"),
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("75000"),
            gamma_dollar=Decimal("5000"),
            gamma_pnl_1pct=Decimal("0.25"),  # 0.5 * 5000 * 0.0001
            vega_per_1pct=Decimal("2000"),
            theta_per_day=Decimal("-500"),
            source=GreeksDataSource.FUTU,
            model=GreeksModel.FUTU,
        )
        assert pg.position_id == 1
        assert pg.valid is True  # default
        assert pg.staleness_seconds == 0  # default

    def test_notional_calculation(self):
        pg = PositionGreeks(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            underlying_price=Decimal("150.00"),
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("75000"),
            gamma_dollar=Decimal("5000"),
            gamma_pnl_1pct=Decimal("0.25"),
            vega_per_1pct=Decimal("2000"),
            theta_per_day=Decimal("-500"),
            source=GreeksDataSource.FUTU,
            model=GreeksModel.FUTU,
            notional=Decimal("150000"),  # 10 * 150 * 100
        )
        assert pg.notional == Decimal("150000")

    def test_invalid_position(self):
        pg = PositionGreeks(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            underlying_price=Decimal("150.00"),
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            source=GreeksDataSource.MODEL,
            model=None,
            valid=False,
            quality_warnings=["IV not available"],
        )
        assert pg.valid is False
        assert "IV not available" in pg.quality_warnings

    def test_strategy_id_optional(self):
        pg = PositionGreeks(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            underlying_price=Decimal("150.00"),
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            source=GreeksDataSource.FUTU,
            model=GreeksModel.FUTU,
            strategy_id="wheel_aapl",
        )
        assert pg.strategy_id == "wheel_aapl"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_models.py::TestPositionGreeks -v
```
Expected: FAIL with "cannot import name 'PositionGreeks'"

**Step 3: Write minimal implementation**

```python
# Add to backend/src/greeks/models.py after enums

@dataclass
class PositionGreeks:
    """Single position Greeks (normalized).

    Numeric type convention:
    - Internal calculation/storage uses Decimal
    - API/WS output converts to float (4 decimal rounding)

    Sign convention (dollar_delta):
    - Long Call: positive
    - Long Put: negative
    - Short Call: negative
    - Short Put: positive

    Dollar Greeks formulas:
    - dollar_delta = Δ × S × multiplier
      Unit: $ / $1 underlying move

    - gamma_dollar = Γ × S² × multiplier
      Unit: $ / ($1 underlying move)²
      Used for threshold monitoring

    - gamma_pnl_1pct = 0.5 × gamma_dollar × (0.01)²
      Unit: $ (PnL contribution)
      Used for scenario analysis

    ⚠️ Important: gamma_dollar vs gamma_pnl_1pct
      Differ by ~5000x, do not confuse!

    - vega_per_1pct = Vega × multiplier
      Unit: $ / 1% IV change

    - theta_per_day = Θ × multiplier
      Unit: $ / trading day
    """

    position_id: int
    symbol: str                    # Option symbol (unique identifier)
    underlying_symbol: str

    # ========== Input parameters (for audit/recalculation) ==========
    quantity: int                  # Positive=long, negative=short
    multiplier: int                # Contract multiplier (US options: 100)
    underlying_price: Decimal      # Underlying spot price
    option_type: Literal["call", "put"]
    strike: Decimal
    expiry: str                    # ISO date string

    # ========== Dollar Greeks (Canonical, single type) ==========
    dollar_delta: Decimal          # $ / $1 underlying move
    gamma_dollar: Decimal          # $ / ($1 underlying move)², for threshold
    gamma_pnl_1pct: Decimal        # $ PnL for 1% move, for scenario analysis
    vega_per_1pct: Decimal         # $ / 1% IV change
    theta_per_day: Decimal         # $ / trading day

    # ========== Data source ==========
    source: GreeksDataSource
    model: GreeksModel | None      # Required when source=MODEL
    cached_from_source: GreeksDataSource | None = None  # When source=CACHED
    cached_from_model: GreeksModel | None = None

    # ========== Data quality ==========
    valid: bool = True
    quality_warnings: list[str] = field(default_factory=list)
    staleness_seconds: int = 0
    as_of_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ========== For coverage calculation ==========
    notional: Decimal = Decimal("0")  # abs(qty) × underlying_price × multiplier

    # ========== Optional strategy assignment ==========
    strategy_id: str | None = None
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_models.py::TestPositionGreeks -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/models.py backend/tests/greeks/test_models.py
git commit -m "feat(greeks): add PositionGreeks dataclass

- All Dollar Greeks fields including gamma_pnl_1pct
- Data source and quality tracking
- Strategy assignment support
- Comprehensive docstring with formulas

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Add AggregatedGreeks Dataclass

**Files:**
- Modify: `backend/src/greeks/models.py`
- Modify: `backend/tests/greeks/test_models.py`

**Step 1: Write the failing test for AggregatedGreeks**

```python
# Add to backend/tests/greeks/test_models.py

from src.greeks.models import AggregatedGreeks


class TestAggregatedGreeks:
    """Tests for AggregatedGreeks dataclass."""

    def test_create_account_scope(self):
        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("50000"),
            gamma_dollar=Decimal("8000"),
            gamma_pnl_1pct=Decimal("0.4"),
            vega_per_1pct=Decimal("15000"),
            theta_per_day=Decimal("-3000"),
            valid_legs_count=10,
            total_legs_count=12,
            valid_notional=Decimal("900000"),
            total_notional=Decimal("1000000"),
        )
        assert ag.scope == "ACCOUNT"
        assert ag.strategy_id is None

    def test_create_strategy_scope(self):
        ag = AggregatedGreeks(
            scope="STRATEGY",
            scope_id="wheel_aapl",
            strategy_id="wheel_aapl",
            dollar_delta=Decimal("25000"),
            gamma_dollar=Decimal("4000"),
            gamma_pnl_1pct=Decimal("0.2"),
            vega_per_1pct=Decimal("8000"),
            theta_per_day=Decimal("-1500"),
            valid_legs_count=5,
            total_legs_count=5,
            valid_notional=Decimal("500000"),
            total_notional=Decimal("500000"),
        )
        assert ag.scope == "STRATEGY"
        assert ag.strategy_id == "wheel_aapl"

    def test_coverage_pct_calculation(self):
        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            valid_legs_count=9,
            total_legs_count=10,
            valid_notional=Decimal("90000"),
            total_notional=Decimal("100000"),
        )
        assert ag.coverage_pct == Decimal("90.00")

    def test_coverage_pct_zero_notional(self):
        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            valid_legs_count=0,
            total_legs_count=0,
            valid_notional=Decimal("0"),
            total_notional=Decimal("0"),
        )
        assert ag.coverage_pct == Decimal("100.0")

    def test_is_coverage_sufficient(self):
        sufficient = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            valid_legs_count=95,
            total_legs_count=100,
            valid_notional=Decimal("95000"),
            total_notional=Decimal("100000"),
        )
        assert sufficient.is_coverage_sufficient is True

        insufficient = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            valid_legs_count=90,
            total_legs_count=100,
            valid_notional=Decimal("90000"),
            total_notional=Decimal("100000"),
        )
        assert insufficient.is_coverage_sufficient is False

    def test_has_high_risk_missing_legs(self):
        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            valid_legs_count=10,
            total_legs_count=10,
            valid_notional=Decimal("100000"),
            total_notional=Decimal("100000"),
            has_high_risk_missing_legs=True,
        )
        assert ag.has_high_risk_missing_legs is True

    def test_staleness_seconds(self):
        from datetime import timedelta
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=30)
        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="acc123",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            valid_legs_count=10,
            total_legs_count=10,
            valid_notional=Decimal("100000"),
            total_notional=Decimal("100000"),
            as_of_ts_min=old_ts,
        )
        assert ag.staleness_seconds >= 29  # Allow small timing variance
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_models.py::TestAggregatedGreeks -v
```
Expected: FAIL with "cannot import name 'AggregatedGreeks'"

**Step 3: Write minimal implementation**

```python
# Add to backend/src/greeks/models.py after PositionGreeks

@dataclass
class AggregatedGreeks:
    """Aggregated portfolio Greeks.

    Timestamp semantic convention:
    - as_of_ts: Main timestamp = as_of_ts_min (most conservative, oldest data)
    - as_of_ts_min: Earliest data coverage time
    - as_of_ts_max: Latest data coverage time
    - staleness_seconds: Based on as_of_ts_min (most conservative)

    UI / Alert / Snapshot all use as_of_ts (= as_of_ts_min)
    """

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    strategy_id: str | None = None  # Only for STRATEGY scope

    # Dollar Greeks totals
    dollar_delta: Decimal = Decimal("0")
    gamma_dollar: Decimal = Decimal("0")        # For threshold monitoring
    gamma_pnl_1pct: Decimal = Decimal("0")      # For scenario analysis
    vega_per_1pct: Decimal = Decimal("0")
    theta_per_day: Decimal = Decimal("0")

    # Coverage metrics
    valid_legs_count: int = 0
    total_legs_count: int = 0
    valid_notional: Decimal = Decimal("0")
    total_notional: Decimal = Decimal("0")
    missing_positions: list[int] = field(default_factory=list)
    has_high_risk_missing_legs: bool = False  # V1: high gamma/vega missing
    warning_legs_count: int = 0
    has_positions: bool = True

    # Timestamps (convention: as_of_ts = as_of_ts_min, most conservative)
    as_of_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    as_of_ts_min: datetime | None = None  # Earliest data (for staleness)
    as_of_ts_max: datetime | None = None  # Latest data (reference only)

    # Metadata
    calc_duration_ms: int = 0

    @property
    def coverage_pct(self) -> Decimal:
        """Calculate coverage percentage."""
        if not self.has_positions or self.total_notional == 0:
            return Decimal("100.0")
        return (self.valid_notional / self.total_notional * 100).quantize(Decimal("0.01"))

    @property
    def is_coverage_sufficient(self) -> bool:
        """Check if coverage meets 95% threshold."""
        return self.coverage_pct >= Decimal("95.0")

    @property
    def staleness_seconds(self) -> int:
        """Calculate staleness based on oldest data (most conservative)."""
        if self.as_of_ts_min is None:
            return 0
        delta = datetime.now(timezone.utc) - self.as_of_ts_min
        return int(delta.total_seconds())
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_models.py::TestAggregatedGreeks -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/models.py backend/tests/greeks/test_models.py
git commit -m "feat(greeks): add AggregatedGreeks dataclass

- Account and strategy scope support
- Coverage percentage calculation with 95% threshold
- Staleness calculation from as_of_ts_min (conservative)
- High-risk missing legs flag for V1 enhancement

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Add Configuration Models

**Files:**
- Modify: `backend/src/greeks/models.py`
- Modify: `backend/tests/greeks/test_models.py`

**Step 1: Write the failing test for configuration models**

```python
# Add to backend/tests/greeks/test_models.py

from src.greeks.models import GreeksThresholdConfig, GreeksLimitsConfig


class TestGreeksThresholdConfig:
    """Tests for GreeksThresholdConfig."""

    def test_default_percentages(self):
        cfg = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )
        assert cfg.warn_pct == Decimal("0.80")
        assert cfg.crit_pct == Decimal("1.00")
        assert cfg.hard_pct == Decimal("1.20")

    def test_recovery_thresholds(self):
        cfg = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )
        assert cfg.warn_recover_pct == Decimal("0.75")
        assert cfg.crit_recover_pct == Decimal("0.90")

    def test_threshold_values(self):
        cfg = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )
        assert cfg.warn_threshold == Decimal("40000")  # 50000 * 0.80
        assert cfg.crit_threshold == Decimal("50000")  # 50000 * 1.00
        assert cfg.hard_threshold == Decimal("60000")  # 50000 * 1.20


class TestGreeksLimitsConfig:
    """Tests for GreeksLimitsConfig."""

    def test_default_account_config(self):
        cfg = GreeksLimitsConfig.default_account_config("acc123")
        assert cfg.scope == "ACCOUNT"
        assert cfg.scope_id == "acc123"
        assert RiskMetric.DELTA in cfg.thresholds
        assert RiskMetric.GAMMA in cfg.thresholds

    def test_dedupe_windows(self):
        cfg = GreeksLimitsConfig.default_account_config("acc123")
        assert cfg.dedupe_window_seconds_by_level[GreeksLevel.WARN] == 900
        assert cfg.dedupe_window_seconds_by_level[GreeksLevel.CRIT] == 300
        assert cfg.dedupe_window_seconds_by_level[GreeksLevel.HARD] == 60
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_models.py::TestGreeksThresholdConfig -v
cd backend && pytest tests/greeks/test_models.py::TestGreeksLimitsConfig -v
```
Expected: FAIL with "cannot import name 'GreeksThresholdConfig'"

**Step 3: Write minimal implementation**

```python
# Add to backend/src/greeks/models.py after AggregatedGreeks

@dataclass
class GreeksThresholdConfig:
    """Configuration for a single Greek metric threshold."""

    metric: RiskMetric

    # Threshold direction
    direction: ThresholdDirection = ThresholdDirection.ABS

    # Absolute limit (always positive)
    limit: Decimal = Decimal("0")

    # Percentage thresholds
    warn_pct: Decimal = Decimal("0.80")   # 80%
    crit_pct: Decimal = Decimal("1.00")   # 100%
    hard_pct: Decimal = Decimal("1.20")   # 120%

    # Recovery thresholds (hysteresis)
    warn_recover_pct: Decimal = Decimal("0.75")  # Recover to 75% to clear WARN
    crit_recover_pct: Decimal = Decimal("0.90")  # Recover to 90% to clear CRIT

    # Rate of change detection
    rate_window_seconds: int = 300  # 5 minutes
    rate_change_pct: Decimal = Decimal("0.20")   # 20% of limit
    rate_change_abs: Decimal = Decimal("0")      # Absolute change threshold

    @property
    def warn_threshold(self) -> Decimal:
        """Calculate WARN threshold."""
        return self.limit * self.warn_pct

    @property
    def crit_threshold(self) -> Decimal:
        """Calculate CRIT threshold."""
        return self.limit * self.crit_pct

    @property
    def hard_threshold(self) -> Decimal:
        """Calculate HARD threshold."""
        return self.limit * self.hard_pct


@dataclass
class GreeksLimitsConfig:
    """Greeks limits configuration (account or strategy level)."""

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str

    thresholds: dict[RiskMetric, GreeksThresholdConfig] = field(
        default_factory=dict
    )

    # Coverage threshold
    min_coverage_pct: Decimal = Decimal("95.0")

    # Alert cooldowns by level
    dedupe_window_seconds_by_level: dict[GreeksLevel, int] = field(
        default_factory=lambda: {
            GreeksLevel.WARN: 900,   # 15 minutes
            GreeksLevel.CRIT: 300,   # 5 minutes
            GreeksLevel.HARD: 60,    # 1 minute
        }
    )

    @classmethod
    def default_account_config(cls, account_id: str) -> "GreeksLimitsConfig":
        """Create default account-level configuration."""
        return cls(
            scope="ACCOUNT",
            scope_id=account_id,
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    direction=ThresholdDirection.ABS,
                    limit=Decimal("50000"),
                    rate_change_abs=Decimal("5000"),
                ),
                RiskMetric.GAMMA: GreeksThresholdConfig(
                    metric=RiskMetric.GAMMA,
                    direction=ThresholdDirection.ABS,
                    limit=Decimal("10000"),
                    rate_change_abs=Decimal("1000"),
                ),
                RiskMetric.VEGA: GreeksThresholdConfig(
                    metric=RiskMetric.VEGA,
                    direction=ThresholdDirection.ABS,
                    limit=Decimal("20000"),
                    rate_change_abs=Decimal("2000"),
                ),
                RiskMetric.THETA: GreeksThresholdConfig(
                    metric=RiskMetric.THETA,
                    direction=ThresholdDirection.ABS,
                    limit=Decimal("5000"),
                    rate_change_abs=Decimal("500"),
                ),
                RiskMetric.IMPLIED_VOLATILITY: GreeksThresholdConfig(
                    metric=RiskMetric.IMPLIED_VOLATILITY,
                    direction=ThresholdDirection.MAX,
                    limit=Decimal("2.0"),  # 200% IV upper limit
                    rate_change_abs=Decimal("0.3"),  # 30% IV change
                ),
            },
        )
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_models.py::TestGreeksThresholdConfig -v
cd backend && pytest tests/greeks/test_models.py::TestGreeksLimitsConfig -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/models.py backend/tests/greeks/test_models.py
git commit -m "feat(greeks): add threshold and limits configuration

- GreeksThresholdConfig with WARN/CRIT/HARD percentages
- Hysteresis recovery thresholds
- Rate of change detection config
- GreeksLimitsConfig with default account settings

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Aggregator Component (Tasks 5-7)

### Task 5: Create GreeksAggregator with Basic Tests

**Files:**
- Create: `backend/src/greeks/aggregator.py`
- Create: `backend/tests/greeks/test_aggregator.py`

**Step 1: Write the failing test**

```python
# backend/tests/greeks/test_aggregator.py
"""Tests for Greeks aggregation."""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from src.greeks.aggregator import GreeksAggregator
from src.greeks.models import (
    PositionGreeks,
    AggregatedGreeks,
    GreeksDataSource,
    GreeksModel,
    RiskMetric,
)


def make_position_greeks(
    position_id: int,
    dollar_delta: Decimal = Decimal("10000"),
    gamma_dollar: Decimal = Decimal("1000"),
    vega_per_1pct: Decimal = Decimal("2000"),
    theta_per_day: Decimal = Decimal("-500"),
    valid: bool = True,
    notional: Decimal = Decimal("100000"),
    strategy_id: str | None = None,
    as_of_ts: datetime | None = None,
) -> PositionGreeks:
    """Factory for test PositionGreeks."""
    return PositionGreeks(
        position_id=position_id,
        symbol=f"TEST{position_id}",
        underlying_symbol="TEST",
        quantity=10,
        multiplier=100,
        underlying_price=Decimal("100"),
        option_type="call",
        strike=Decimal("100"),
        expiry="2024-01-19",
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=Decimal("0.5") * gamma_dollar * Decimal("0.0001"),
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        source=GreeksDataSource.FUTU,
        model=GreeksModel.FUTU,
        valid=valid,
        notional=notional,
        strategy_id=strategy_id,
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
    )


class TestGreeksAggregator:
    """Tests for GreeksAggregator."""

    def test_aggregate_single_position(self):
        aggregator = GreeksAggregator()
        positions = [make_position_greeks(1)]

        result = aggregator.aggregate(positions, "ACCOUNT", "acc123")

        assert result.scope == "ACCOUNT"
        assert result.scope_id == "acc123"
        assert result.dollar_delta == Decimal("10000")
        assert result.valid_legs_count == 1
        assert result.total_legs_count == 1

    def test_aggregate_multiple_positions(self):
        aggregator = GreeksAggregator()
        positions = [
            make_position_greeks(1, dollar_delta=Decimal("10000")),
            make_position_greeks(2, dollar_delta=Decimal("20000")),
            make_position_greeks(3, dollar_delta=Decimal("-5000")),
        ]

        result = aggregator.aggregate(positions, "ACCOUNT", "acc123")

        assert result.dollar_delta == Decimal("25000")  # 10000 + 20000 - 5000
        assert result.valid_legs_count == 3
        assert result.total_legs_count == 3

    def test_aggregate_with_invalid_positions(self):
        aggregator = GreeksAggregator()
        positions = [
            make_position_greeks(1, dollar_delta=Decimal("10000"), valid=True),
            make_position_greeks(2, dollar_delta=Decimal("20000"), valid=False),
        ]

        result = aggregator.aggregate(positions, "ACCOUNT", "acc123")

        # Invalid position should not contribute to Greeks
        assert result.dollar_delta == Decimal("10000")
        assert result.valid_legs_count == 1
        assert result.total_legs_count == 2
        assert 2 in result.missing_positions

    def test_aggregate_empty_positions(self):
        aggregator = GreeksAggregator()

        result = aggregator.aggregate([], "ACCOUNT", "acc123")

        assert result.dollar_delta == Decimal("0")
        assert result.has_positions is False
        assert result.coverage_pct == Decimal("100.0")

    def test_aggregate_takes_min_timestamp(self):
        aggregator = GreeksAggregator()
        now = datetime.now(timezone.utc)
        positions = [
            make_position_greeks(1, as_of_ts=now - timedelta(seconds=30)),
            make_position_greeks(2, as_of_ts=now - timedelta(seconds=10)),
        ]

        result = aggregator.aggregate(positions, "ACCOUNT", "acc123")

        # as_of_ts should be the min (oldest)
        assert result.as_of_ts_min == positions[0].as_of_ts
        assert result.as_of_ts_max == positions[1].as_of_ts
        assert result.as_of_ts == result.as_of_ts_min  # Convention
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_aggregator.py -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'src.greeks.aggregator'"

**Step 3: Write minimal implementation**

```python
# backend/src/greeks/aggregator.py
"""Greeks aggregation logic.

This module aggregates position-level Greeks to account/strategy level,
calculating coverage metrics and tracking data quality.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from src.greeks.models import (
    AggregatedGreeks,
    PositionGreeks,
    RiskMetric,
)

logger = logging.getLogger(__name__)


@dataclass
class _Accumulator:
    """Internal accumulator for single-pass O(N) aggregation."""

    # Dollar Greeks totals
    dollar_delta: Decimal = Decimal("0")
    gamma_dollar: Decimal = Decimal("0")
    gamma_pnl_1pct: Decimal = Decimal("0")
    vega_per_1pct: Decimal = Decimal("0")
    theta_per_day: Decimal = Decimal("0")

    # Coverage stats
    valid_legs_count: int = 0
    total_legs_count: int = 0
    valid_notional: Decimal = Decimal("0")
    total_notional: Decimal = Decimal("0")
    missing_positions: list[int] = field(default_factory=list)
    high_risk_missing_positions: list[int] = field(default_factory=list)
    warning_positions: list[int] = field(default_factory=list)

    # High-risk thresholds
    GAMMA_HIGH_RISK_THRESHOLD: Decimal = Decimal("1000")
    VEGA_HIGH_RISK_THRESHOLD: Decimal = Decimal("2000")

    # Timestamp tracking
    as_of_ts_min: datetime | None = None
    as_of_ts_max: datetime | None = None

    def add(self, pg: PositionGreeks) -> None:
        """Accumulate a single position."""
        self.total_legs_count += 1
        self.total_notional += pg.notional

        # Update timestamp range
        if self.as_of_ts_min is None or pg.as_of_ts < self.as_of_ts_min:
            self.as_of_ts_min = pg.as_of_ts
        if self.as_of_ts_max is None or pg.as_of_ts > self.as_of_ts_max:
            self.as_of_ts_max = pg.as_of_ts

        if pg.valid:
            self.valid_legs_count += 1
            self.valid_notional += pg.notional
            self.dollar_delta += pg.dollar_delta
            self.gamma_dollar += pg.gamma_dollar
            self.gamma_pnl_1pct += pg.gamma_pnl_1pct
            self.vega_per_1pct += pg.vega_per_1pct
            self.theta_per_day += pg.theta_per_day

            if pg.quality_warnings:
                self.warning_positions.append(pg.position_id)
        else:
            self.missing_positions.append(pg.position_id)

            # Check for high-risk missing positions
            is_high_risk = (
                abs(pg.gamma_dollar) >= self.GAMMA_HIGH_RISK_THRESHOLD or
                abs(pg.vega_per_1pct) >= self.VEGA_HIGH_RISK_THRESHOLD
            )
            if is_high_risk:
                self.high_risk_missing_positions.append(pg.position_id)


class GreeksAggregator:
    """Aggregates position Greeks to account/strategy level.

    Design principles:
    - Single-pass O(N) aggregation
    - Outputs both computed_greeks and coverage metrics
    - as_of_ts takes the minimum (most conservative)
    """

    def aggregate(
        self,
        positions: list[PositionGreeks],
        scope: Literal["ACCOUNT", "STRATEGY"],
        scope_id: str,
    ) -> AggregatedGreeks:
        """Aggregate positions into account/strategy Greeks.

        Args:
            positions: List of PositionGreeks
            scope: Aggregation scope
            scope_id: Scope identifier

        Returns:
            AggregatedGreeks with totals and coverage metrics
        """
        acc = _Accumulator()

        # Single-pass aggregation
        for pg in positions:
            acc.add(pg)

        # Handle empty positions
        has_positions = acc.total_legs_count > 0
        as_of_ts = acc.as_of_ts_min or datetime.now(timezone.utc)

        return AggregatedGreeks(
            scope=scope,
            scope_id=scope_id,
            strategy_id=scope_id if scope == "STRATEGY" else None,
            dollar_delta=acc.dollar_delta,
            gamma_dollar=acc.gamma_dollar,
            gamma_pnl_1pct=acc.gamma_pnl_1pct,
            vega_per_1pct=acc.vega_per_1pct,
            theta_per_day=acc.theta_per_day,
            valid_legs_count=acc.valid_legs_count,
            total_legs_count=acc.total_legs_count,
            valid_notional=acc.valid_notional,
            total_notional=acc.total_notional,
            missing_positions=acc.missing_positions,
            has_high_risk_missing_legs=len(acc.high_risk_missing_positions) > 0,
            warning_legs_count=len(acc.warning_positions),
            has_positions=has_positions,
            as_of_ts=as_of_ts,
            as_of_ts_min=acc.as_of_ts_min,
            as_of_ts_max=acc.as_of_ts_max,
        )
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_aggregator.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/aggregator.py backend/tests/greeks/test_aggregator.py
git commit -m "feat(greeks): add GreeksAggregator with basic aggregation

- Single-pass O(N) aggregation
- Invalid position tracking (missing_positions)
- High-risk missing legs detection
- Timestamp min/max tracking

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Add Strategy-Level Aggregation

**Files:**
- Modify: `backend/src/greeks/aggregator.py`
- Modify: `backend/tests/greeks/test_aggregator.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/greeks/test_aggregator.py

class TestGreeksAggregatorByStrategy:
    """Tests for strategy-level aggregation."""

    def test_aggregate_by_strategy(self):
        aggregator = GreeksAggregator()
        positions = [
            make_position_greeks(1, dollar_delta=Decimal("10000"), strategy_id="wheel_aapl"),
            make_position_greeks(2, dollar_delta=Decimal("20000"), strategy_id="wheel_aapl"),
            make_position_greeks(3, dollar_delta=Decimal("5000"), strategy_id="iron_condor"),
        ]

        account, strategies = aggregator.aggregate_by_strategy(positions, "acc123")

        # Account totals
        assert account.dollar_delta == Decimal("35000")
        assert account.valid_legs_count == 3

        # Strategy breakdown
        assert len(strategies) == 2
        assert strategies["wheel_aapl"].dollar_delta == Decimal("30000")
        assert strategies["iron_condor"].dollar_delta == Decimal("5000")

    def test_aggregate_by_strategy_unassigned(self):
        aggregator = GreeksAggregator()
        positions = [
            make_position_greeks(1, dollar_delta=Decimal("10000"), strategy_id="wheel"),
            make_position_greeks(2, dollar_delta=Decimal("20000"), strategy_id=None),
        ]

        account, strategies = aggregator.aggregate_by_strategy(positions, "acc123")

        assert "_unassigned_" in strategies
        assert strategies["_unassigned_"].dollar_delta == Decimal("20000")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_aggregator.py::TestGreeksAggregatorByStrategy -v
```
Expected: FAIL with "AttributeError: 'GreeksAggregator' object has no attribute 'aggregate_by_strategy'"

**Step 3: Add implementation**

```python
# Add to backend/src/greeks/aggregator.py in GreeksAggregator class

    def aggregate_by_strategy(
        self,
        positions: list[PositionGreeks],
        account_id: str,
    ) -> tuple[AggregatedGreeks, dict[str, AggregatedGreeks]]:
        """Aggregate by strategy while also computing account total.

        Args:
            positions: List of PositionGreeks
            account_id: Account identifier

        Returns:
            (account_greeks, {strategy_id: strategy_greeks})
        """
        # Group by strategy_id
        by_strategy: dict[str, list[PositionGreeks]] = {}
        for pg in positions:
            strategy_id = pg.strategy_id or "_unassigned_"
            if strategy_id not in by_strategy:
                by_strategy[strategy_id] = []
            by_strategy[strategy_id].append(pg)

        # Strategy-level aggregation
        strategy_greeks = {
            sid: self.aggregate(pgs, "STRATEGY", sid)
            for sid, pgs in by_strategy.items()
        }

        # Account-level aggregation
        account_greeks = self.aggregate(positions, "ACCOUNT", account_id)

        return account_greeks, strategy_greeks
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_aggregator.py::TestGreeksAggregatorByStrategy -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/aggregator.py backend/tests/greeks/test_aggregator.py
git commit -m "feat(greeks): add strategy-level aggregation

- aggregate_by_strategy returns both account and strategy breakdown
- Unassigned positions grouped under _unassigned_

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Add Top Contributors Method

**Files:**
- Modify: `backend/src/greeks/aggregator.py`
- Modify: `backend/tests/greeks/test_aggregator.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/greeks/test_aggregator.py

class TestTopContributors:
    """Tests for top contributors ranking."""

    def test_get_top_contributors_delta(self):
        aggregator = GreeksAggregator()
        positions = [
            make_position_greeks(1, dollar_delta=Decimal("10000")),
            make_position_greeks(2, dollar_delta=Decimal("50000")),
            make_position_greeks(3, dollar_delta=Decimal("-30000")),
        ]

        result = aggregator.get_top_contributors(positions, RiskMetric.DELTA, top_n=2)

        assert len(result) == 2
        # Sorted by abs value descending
        assert result[0][0].position_id == 2  # 50000
        assert result[1][0].position_id == 3  # abs(-30000) = 30000

    def test_get_top_contributors_excludes_invalid(self):
        aggregator = GreeksAggregator()
        positions = [
            make_position_greeks(1, dollar_delta=Decimal("10000"), valid=True),
            make_position_greeks(2, dollar_delta=Decimal("50000"), valid=False),
        ]

        result = aggregator.get_top_contributors(positions, RiskMetric.DELTA)

        assert len(result) == 1
        assert result[0][0].position_id == 1

    def test_get_top_contributors_only_greeks(self):
        aggregator = GreeksAggregator()
        positions = [make_position_greeks(1)]

        # Non-Greek metrics should return empty
        result = aggregator.get_top_contributors(positions, RiskMetric.COVERAGE)
        assert result == []

        result = aggregator.get_top_contributors(positions, RiskMetric.IMPLIED_VOLATILITY)
        assert result == []
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_aggregator.py::TestTopContributors -v
```
Expected: FAIL with "AttributeError: 'GreeksAggregator' object has no attribute 'get_top_contributors'"

**Step 3: Add implementation**

```python
# Add to backend/src/greeks/aggregator.py in GreeksAggregator class

    def get_top_contributors(
        self,
        positions: list[PositionGreeks],
        metric: RiskMetric,
        top_n: int = 10,
    ) -> list[tuple[PositionGreeks, Decimal]]:
        """Get top N contributors for a metric.

        Args:
            positions: List of PositionGreeks
            metric: Metric to rank by (only GREEK category supported)
            top_n: Number of top contributors to return

        Returns:
            [(PositionGreeks, contribution_value)] sorted by abs contribution descending

        Note:
            Only GREEK category metrics support contribution ranking.
            VOLATILITY and DATA_QUALITY metrics return empty list.
        """
        # Only GREEK category supports position contribution ranking
        if not metric.is_greek:
            logger.warning(
                f"get_top_contributors: metric {metric} (category={metric.category}) "
                "not supported - only GREEK category metrics are applicable"
            )
            return []

        # Field mapping (Greeks only)
        field_map = {
            RiskMetric.DELTA: "dollar_delta",
            RiskMetric.GAMMA: "gamma_dollar",
            RiskMetric.VEGA: "vega_per_1pct",
            RiskMetric.THETA: "theta_per_day",
        }

        field_name = field_map.get(metric)
        if not field_name:
            return []

        # Calculate contributions and sort
        contributions = [
            (pg, abs(getattr(pg, field_name)))
            for pg in positions
            if pg.valid
        ]
        contributions.sort(key=lambda x: x[1], reverse=True)

        return contributions[:top_n]
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_aggregator.py::TestTopContributors -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/aggregator.py backend/tests/greeks/test_aggregator.py
git commit -m "feat(greeks): add top contributors ranking

- get_top_contributors for DELTA/GAMMA/VEGA/THETA
- Only GREEK category metrics supported
- Excludes invalid positions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Alert Engine (Tasks 8-12)

### Task 8: Create AlertState and AlertEngine Base

**Files:**
- Create: `backend/src/greeks/alert_engine.py`
- Create: `backend/tests/greeks/test_alert_engine.py`

**Step 1: Write the failing test**

```python
# backend/tests/greeks/test_alert_engine.py
"""Tests for Greeks alert engine."""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from src.greeks.alert_engine import AlertState, GreeksAlertEngine
from src.greeks.models import (
    AggregatedGreeks,
    GreeksLevel,
    GreeksLimitsConfig,
    RiskMetric,
)


class TestAlertState:
    """Tests for AlertState."""

    def test_create_state(self):
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc123",
            metric=RiskMetric.DELTA,
        )
        assert state.current_level == GreeksLevel.NORMAL
        assert len(state.last_alert_ts) == 0

    def test_is_expired_fresh(self):
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc123",
            metric=RiskMetric.DELTA,
        )
        assert state.is_expired is False

    def test_is_expired_old(self):
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc123",
            metric=RiskMetric.DELTA,
            last_updated_ts=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        assert state.is_expired is True


class TestGreeksAlertEngineInit:
    """Tests for GreeksAlertEngine initialization."""

    def test_create_engine(self):
        config = GreeksLimitsConfig.default_account_config("acc123")
        engine = GreeksAlertEngine(config)
        assert engine is not None
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_alert_engine.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/greeks/alert_engine.py
"""Greeks alert evaluation engine.

This module implements the alert logic for Greeks monitoring:
- Threshold breach detection (WARN/CRIT/HARD)
- Rate of change detection
- Level-scoped deduplication
- Escalation-through for upgrades
- Hysteresis recovery detection
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from src.greeks.models import (
    AggregatedGreeks,
    GreeksLevel,
    GreeksLimitsConfig,
    GreeksThresholdConfig,
    RiskMetric,
    RiskMetricCategory,
    ThresholdDirection,
)

logger = logging.getLogger(__name__)


@dataclass
class AlertState:
    """Alert state for state machine.

    Lifecycle management:
    - TTL: 24 hours without update triggers cleanup
    - Memory state needs periodic cleanup to prevent leaks

    Important: ROC detection uses prev_greeks parameter, not memory state.
    """

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    metric: RiskMetric
    current_level: GreeksLevel = GreeksLevel.NORMAL
    last_alert_ts: dict[GreeksLevel, datetime] = field(default_factory=dict)
    last_updated_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        """Check if state is expired (TTL 24h)."""
        ttl_seconds = 24 * 60 * 60  # 24 hours
        elapsed = (datetime.now(timezone.utc) - self.last_updated_ts).total_seconds()
        return elapsed > ttl_seconds


class GreeksAlertEngine:
    """Greeks alert evaluation engine.

    Responsibilities:
    1. Threshold breach detection (WARN/CRIT/HARD)
    2. Rate of change detection (ROC)
    3. Level-scoped deduplication
    4. Escalation-through for upgrades
    5. Hysteresis recovery detection

    ROC Detection Note:
    - ROC does NOT use memory state last_value_eval
    - Must pass prev_greeks from snapshot store / time series
    - Memory state unreliable across restarts / multi-instance

    State management:
    - AlertState stored in memory for dedupe and level tracking
    - _states needs periodic cleanup (TTL 24h) to prevent leaks
    - Multi-process deployment requires Redis persistence
    """

    def __init__(self, limits_config: GreeksLimitsConfig):
        self._config = limits_config
        self._states: dict[str, AlertState] = {}  # key: "{scope}:{scope_id}:{metric}"
        self._last_cleanup_ts: datetime = datetime.now(timezone.utc)
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_alert_engine.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/alert_engine.py backend/tests/greeks/test_alert_engine.py
git commit -m "feat(greeks): add AlertState and AlertEngine base

- AlertState with TTL-based expiration (24h)
- GreeksAlertEngine skeleton with state management
- Docstrings explaining ROC design decisions

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

*[Continuing with Tasks 9-12 for threshold evaluation, ROC detection, coverage checks, and state cleanup...]*

---

## Phase 4: Database Schema (Tasks 13-15)

### Task 13: Create Alembic Migration for greeks_snapshots

**Files:**
- Create: `backend/alembic/versions/XXX_greeks_snapshots.py`

*[Migration for greeks_snapshots and greeks_snapshot_details tables with TimescaleDB hypertable...]*

---

## Phase 5: Calculator Component (Tasks 16-19)

*[GreeksCalculator with Futu integration and model fallback...]*

---

## Phase 6: Monitor Service (Tasks 20-23)

*[GreeksMonitor with event-driven refresh and backstop polling...]*

---

## Phase 7: API Layer (Tasks 24-27)

*[FastAPI endpoints for /api/greeks/...]*

---

## Phase 8: Integration Testing (Tasks 28-30)

*[End-to-end tests with mock Futu client...]*

---

## Summary

| Phase | Tasks | Components |
|-------|-------|------------|
| 1 | 1-4 | Core data models (enums, dataclasses, config) |
| 2 | 5-7 | GreeksAggregator |
| 3 | 8-12 | GreeksAlertEngine |
| 4 | 13-15 | Database migrations |
| 5 | 16-19 | GreeksCalculator |
| 6 | 20-23 | GreeksMonitor service |
| 7 | 24-27 | API endpoints |
| 8 | 28-30 | Integration tests |

**Estimated total tasks:** 30 bite-sized steps

**Key testing commands:**
```bash
cd backend && pytest tests/greeks/ -v           # All Greeks tests
cd backend && pytest tests/greeks/ -v --cov=src/greeks  # With coverage
```
