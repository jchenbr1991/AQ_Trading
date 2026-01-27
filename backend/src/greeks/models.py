"""Greeks monitoring data models.

This module defines the core enums and data structures for the Greeks monitoring system.

Enums:
    - RiskMetricCategory: Categories of risk metrics (GREEK, VOLATILITY, DATA_QUALITY)
    - RiskMetric: Individual risk metrics with category mapping
    - GreeksDataSource: Source of Greeks data (FUTU, MODEL, CACHED)
    - GreeksModel: Calculation model used (FUTU, BS, BJERKSUND)
    - GreeksLevel: Alert levels (NORMAL, WARN, CRIT, HARD)
    - ThresholdDirection: How to evaluate against threshold (ABS, MAX, MIN)
"""

from enum import Enum


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
