"""Greeks monitoring data models.

This module defines the core enums and data structures for the Greeks monitoring system.

Enums:
    - RiskMetricCategory: Categories of risk metrics (GREEK, VOLATILITY, DATA_QUALITY)
    - RiskMetric: Individual risk metrics with category mapping
    - GreeksDataSource: Source of Greeks data (FUTU, MODEL, CACHED)
    - GreeksModel: Calculation model used (FUTU, BS, BJERKSUND)
    - GreeksLevel: Alert levels (NORMAL, WARN, CRIT, HARD)
    - ThresholdDirection: How to evaluate against threshold (ABS, MAX, MIN)

Dataclasses:
    - PositionGreeks: Single position's Greeks values in normalized dollar terms
    - AggregatedGreeks: Portfolio-level or strategy-level aggregated Greeks
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Literal


class GreeksDataSource(str, Enum):
    """Greeks data source.

    Indicates where the Greeks values came from:
    - FUTU: Direct from Futu API
    - MODEL: Calculated using pricing model (BS or Bjerksund-Stensland)
    - CACHED: Retrieved from cache (with original source recorded separately)
    """

    FUTU = "futu"
    MODEL = "model"
    CACHED = "cached"


class GreeksModel(str, Enum):
    """Greeks calculation model.

    Used when source=MODEL or to track cached_from_model:
    - FUTU: Value provided by Futu (treated as a model output)
    - BS: Black-Scholes model (European options)
    - BJERKSUND: Bjerksund-Stensland model (American options)
    """

    FUTU = "futu"
    BS = "bs"
    BJERKSUND = "bjerksund"


class GreeksLevel(str, Enum):
    """Alert level for Greeks monitoring.

    Escalation hierarchy: NORMAL < WARN < CRIT < HARD
    - NORMAL: Within acceptable limits
    - WARN: Approaching limit (default: 80% of limit)
    - CRIT: At or exceeding limit (default: 100% of limit)
    - HARD: Significantly exceeding limit (default: 120% of limit)
    """

    NORMAL = "normal"
    WARN = "warn"
    CRIT = "crit"
    HARD = "hard"


class RiskMetricCategory(str, Enum):
    """Risk metric category.

    Used to classify risk metrics for differentiated processing:
    - GREEK: Delta, Gamma, Vega, Theta
    - VOLATILITY: IV and derivatives
    - DATA_QUALITY: Coverage and data freshness metrics
    """

    GREEK = "greek"
    VOLATILITY = "volatility"
    DATA_QUALITY = "data_quality"


class RiskMetric(str, Enum):
    """Risk metric type.

    Unified interface for all monitored risk metrics.

    V1 Design Notes:
    - IV is not a Greek but needs monitoring, hence abstracted as RiskMetric
    - Each metric belongs to a category for differentiated processing
    - Future extensions: SKEW, TERM_STRUCTURE, etc.

    Greeks (category=GREEK):
        - DELTA: Portfolio delta exposure
        - GAMMA: Portfolio gamma exposure
        - VEGA: Portfolio vega exposure
        - THETA: Portfolio theta exposure

    Volatility (category=VOLATILITY):
        - IMPLIED_VOLATILITY: Implied volatility monitoring

    Data Quality (category=DATA_QUALITY):
        - COVERAGE: Greeks data coverage percentage
    """

    # Greeks (category=GREEK)
    DELTA = "delta"
    GAMMA = "gamma"
    VEGA = "vega"
    THETA = "theta"

    # Volatility (category=VOLATILITY)
    IMPLIED_VOLATILITY = "iv"
    # V1.5 reserved: IV_SKEW = "iv_skew"
    # V2 reserved: IV_TERM_STRUCTURE = "iv_term"

    # Data Quality (category=DATA_QUALITY)
    COVERAGE = "coverage"

    @property
    def category(self) -> RiskMetricCategory:
        """Get the category for this metric.

        Returns:
            RiskMetricCategory for this metric.
        """
        if self in (RiskMetric.DELTA, RiskMetric.GAMMA, RiskMetric.VEGA, RiskMetric.THETA):
            return RiskMetricCategory.GREEK
        elif self in (RiskMetric.IMPLIED_VOLATILITY,):
            return RiskMetricCategory.VOLATILITY
        else:
            return RiskMetricCategory.DATA_QUALITY

    @property
    def is_greek(self) -> bool:
        """Check if this metric is a Greek.

        Returns:
            True if this metric is a Greek (Delta, Gamma, Vega, Theta).
        """
        return self.category == RiskMetricCategory.GREEK


# Backward compatibility alias (for V1 transition period)
GreeksMetric = RiskMetric


class ThresholdDirection(str, Enum):
    """Threshold evaluation direction.

    Defines how values are compared against limits:
    - ABS: abs(value) <= limit (default, for bidirectional limits)
    - MAX: value <= limit (upper bound only)
    - MIN: value >= limit (lower bound only)
    """

    ABS = "abs"
    MAX = "max"
    MIN = "min"


@dataclass
class PositionGreeks:
    """Single position's Greeks values in normalized dollar terms.

    This dataclass represents a single option position's Greeks, all normalized
    to dollar terms for aggregation and threshold monitoring.

    Numeric Type Convention:
        - Internal storage: Decimal for precision in financial calculations
        - API responses: Convert to float for JSON serialization

    Sign Convention for dollar_delta:
        - Positive: Long delta exposure (profit when underlying rises)
        - Negative: Short delta exposure (profit when underlying falls)
        - For calls: long position = positive delta, short = negative
        - For puts: long position = negative delta, short = positive

    Dollar Greeks Formulas (all in USD):
        - dollar_delta: delta × quantity × multiplier × underlying_price
          Units: $ / $1 underlying move
          Example: dollar_delta=5000 means +$5000 PnL per $1 underlying rise

        - gamma_dollar: gamma × quantity × multiplier × underlying_price
          Units: $ / ($1 underlying move)²
          Used for: Threshold monitoring (compare against limits)

        - gamma_pnl_1pct: 0.5 × gamma × quantity × multiplier × (0.01 × underlying_price)²
          Units: $ PnL for 1% underlying move
          Used for: Scenario analysis, risk reporting
          WARNING: gamma_pnl_1pct ≈ gamma_dollar × 0.00005 × underlying_price
                   For $100 stock: gamma_pnl_1pct ≈ gamma_dollar / 200
                   This is ~5000x smaller than gamma_dollar for typical stocks!

        - vega_per_1pct: vega × quantity × multiplier × 0.01
          Units: $ / 1% IV change
          Example: vega_per_1pct=200 means +$200 PnL per 1% IV increase

        - theta_per_day: theta × quantity × multiplier
          Units: $ / trading day
          Example: theta_per_day=-50 means -$50 PnL per trading day

    Attributes:
        position_id: Unique identifier for the position
        symbol: Option symbol (e.g., "AAPL240119C00150000")
        underlying_symbol: Underlying stock symbol (e.g., "AAPL")
        quantity: Position quantity (positive=long, negative=short)
        multiplier: Contract multiplier (US options: 100)
        underlying_price: Current underlying spot price
        option_type: "call" or "put"
        strike: Option strike price
        expiry: Expiration date as ISO string (e.g., "2024-01-19")
        dollar_delta: Dollar delta exposure
        gamma_dollar: Dollar gamma for threshold monitoring
        gamma_pnl_1pct: Dollar PnL for 1% underlying move (scenario analysis)
        vega_per_1pct: Dollar vega per 1% IV change
        theta_per_day: Dollar theta per trading day
        source: Where the Greeks came from (FUTU, MODEL, CACHED)
        model: Calculation model used (None if source=FUTU)
        cached_from_source: Original source if source=CACHED
        cached_from_model: Original model if source=CACHED
        valid: Whether Greeks values are valid (no NaN, no stale data)
        quality_warnings: List of data quality warnings
        staleness_seconds: How stale the data is in seconds
        as_of_ts: Timestamp when Greeks were calculated/fetched
        strategy_id: Optional strategy this position belongs to
    """

    # Position identification
    position_id: int
    symbol: str
    underlying_symbol: str
    quantity: int
    multiplier: int

    # Underlying data
    underlying_price: Decimal

    # Option characteristics
    option_type: Literal["call", "put"]
    strike: Decimal
    expiry: str

    # Dollar Greeks
    dollar_delta: Decimal
    gamma_dollar: Decimal
    gamma_pnl_1pct: Decimal
    vega_per_1pct: Decimal
    theta_per_day: Decimal

    # Data source tracking
    source: GreeksDataSource
    model: GreeksModel | None

    # Cache tracking (when source=CACHED)
    cached_from_source: GreeksDataSource | None = None
    cached_from_model: GreeksModel | None = None

    # Data quality
    valid: bool = True
    quality_warnings: list[str] = field(default_factory=list)
    staleness_seconds: int = 0
    as_of_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Strategy assignment
    strategy_id: str | None = None

    @property
    def notional(self) -> Decimal:
        """Compute notional value of the position.

        Returns:
            abs(quantity) × underlying_price × multiplier
        """
        return abs(self.quantity) * self.underlying_price * self.multiplier


@dataclass
class AggregatedGreeks:
    """Portfolio-level or strategy-level aggregated Greeks.

    This dataclass represents aggregated Greeks for either an entire account
    or a specific strategy. All values are in normalized dollar terms.

    Timestamp Semantic Convention:
        - as_of_ts = as_of_ts_min (most conservative / oldest timestamp)
        - UI, Alert, and Snapshot operations all use as_of_ts (= as_of_ts_min)
        - as_of_ts_min: Earliest data timestamp, used for staleness calculation
        - as_of_ts_max: Latest data timestamp, for reference only

    Scope Types:
        - ACCOUNT: Entire portfolio aggregation (scope_id = account identifier)
        - STRATEGY: Single strategy aggregation (scope_id = strategy_id)

    Coverage Calculation:
        - coverage_pct = valid_notional / total_notional * 100
        - Returns 100.0% if no positions or total_notional == 0
        - is_coverage_sufficient: coverage_pct >= 95.0%

    High Risk Missing Legs (V1):
        - has_high_risk_missing_legs: True if missing positions have high gamma/vega
        - Used for enhanced alerting when data quality issues affect risk metrics

    Attributes:
        scope: "ACCOUNT" or "STRATEGY"
        scope_id: Identifier for the scope (account ID or strategy ID)
        strategy_id: Strategy ID (only for STRATEGY scope)
        dollar_delta: Aggregated dollar delta exposure
        gamma_dollar: Aggregated dollar gamma for threshold monitoring
        gamma_pnl_1pct: Aggregated dollar PnL for 1% underlying move
        vega_per_1pct: Aggregated dollar vega per 1% IV change
        theta_per_day: Aggregated dollar theta per trading day
        valid_legs_count: Number of positions with valid Greeks
        total_legs_count: Total number of positions
        valid_notional: Notional value of positions with valid Greeks
        total_notional: Total notional value of all positions
        missing_positions: List of position IDs with missing/invalid Greeks
        has_high_risk_missing_legs: V1 flag for high gamma/vega missing positions
        warning_legs_count: Number of positions with quality warnings
        has_positions: Whether any positions exist in scope
        as_of_ts: Reference timestamp (= as_of_ts_min, conservative)
        as_of_ts_min: Earliest data timestamp (for staleness)
        as_of_ts_max: Latest data timestamp (reference only)
        calc_duration_ms: Calculation time in milliseconds
    """

    # Scope identification
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str

    # Strategy association (only for STRATEGY scope)
    strategy_id: str | None = None

    # Aggregated Dollar Greeks
    dollar_delta: Decimal = Decimal("0")
    gamma_dollar: Decimal = Decimal("0")
    gamma_pnl_1pct: Decimal = Decimal("0")
    vega_per_1pct: Decimal = Decimal("0")
    theta_per_day: Decimal = Decimal("0")

    # Coverage tracking
    valid_legs_count: int = 0
    total_legs_count: int = 0
    valid_notional: Decimal = Decimal("0")
    total_notional: Decimal = Decimal("0")
    missing_positions: list[int] = field(default_factory=list)

    # Data quality flags
    has_high_risk_missing_legs: bool = False  # V1: high gamma/vega missing
    warning_legs_count: int = 0
    has_positions: bool = True

    # Timestamps
    as_of_ts: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    as_of_ts_min: datetime | None = None  # Earliest data, for staleness
    as_of_ts_max: datetime | None = None  # Latest data, reference only

    # Performance metrics
    calc_duration_ms: int = 0

    @property
    def coverage_pct(self) -> Decimal:
        """Calculate coverage percentage.

        Returns:
            (valid_notional / total_notional) * 100, or 100.0 if no positions
            or total_notional == 0.
        """
        if not self.has_positions or self.total_notional == Decimal("0"):
            return Decimal("100.0")
        return (self.valid_notional / self.total_notional) * Decimal("100")

    @property
    def is_coverage_sufficient(self) -> bool:
        """Check if coverage meets the 95% threshold.

        Returns:
            True if coverage_pct >= 95.0%.
        """
        return self.coverage_pct >= Decimal("95.0")

    @property
    def staleness_seconds(self) -> int:
        """Calculate staleness from as_of_ts_min.

        Returns:
            Seconds since as_of_ts_min, or 0 if as_of_ts_min is not set.
        """
        if self.as_of_ts_min is None:
            return 0
        now = datetime.now(timezone.utc)
        delta = now - self.as_of_ts_min
        return int(delta.total_seconds())
