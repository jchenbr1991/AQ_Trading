"""Tests for Greeks monitoring models.

Tests cover:
- RiskMetricCategory enum
- RiskMetric enum with category property and is_greek method
- GreeksDataSource, GreeksModel, GreeksLevel, ThresholdDirection enums
"""


class TestRiskMetricCategory:
    """Tests for RiskMetricCategory enum."""

    def test_greek_category_exists(self):
        """GREEK category exists."""
        from src.greeks.models import RiskMetricCategory

        assert RiskMetricCategory.GREEK.value == "greek"

    def test_volatility_category_exists(self):
        """VOLATILITY category exists."""
        from src.greeks.models import RiskMetricCategory

        assert RiskMetricCategory.VOLATILITY.value == "volatility"

    def test_data_quality_category_exists(self):
        """DATA_QUALITY category exists."""
        from src.greeks.models import RiskMetricCategory

        assert RiskMetricCategory.DATA_QUALITY.value == "data_quality"


class TestRiskMetric:
    """Tests for RiskMetric enum."""

    def test_delta_metric_exists(self):
        """DELTA metric exists with correct value."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.DELTA.value == "delta"

    def test_gamma_metric_exists(self):
        """GAMMA metric exists with correct value."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.GAMMA.value == "gamma"

    def test_vega_metric_exists(self):
        """VEGA metric exists with correct value."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.VEGA.value == "vega"

    def test_theta_metric_exists(self):
        """THETA metric exists with correct value."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.THETA.value == "theta"

    def test_implied_volatility_metric_exists(self):
        """IMPLIED_VOLATILITY metric exists with correct value."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.IMPLIED_VOLATILITY.value == "iv"

    def test_coverage_metric_exists(self):
        """COVERAGE metric exists with correct value."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.COVERAGE.value == "coverage"

    def test_delta_category_is_greek(self):
        """DELTA belongs to GREEK category."""
        from src.greeks.models import RiskMetric, RiskMetricCategory

        assert RiskMetric.DELTA.category == RiskMetricCategory.GREEK

    def test_gamma_category_is_greek(self):
        """GAMMA belongs to GREEK category."""
        from src.greeks.models import RiskMetric, RiskMetricCategory

        assert RiskMetric.GAMMA.category == RiskMetricCategory.GREEK

    def test_vega_category_is_greek(self):
        """VEGA belongs to GREEK category."""
        from src.greeks.models import RiskMetric, RiskMetricCategory

        assert RiskMetric.VEGA.category == RiskMetricCategory.GREEK

    def test_theta_category_is_greek(self):
        """THETA belongs to GREEK category."""
        from src.greeks.models import RiskMetric, RiskMetricCategory

        assert RiskMetric.THETA.category == RiskMetricCategory.GREEK

    def test_implied_volatility_category_is_volatility(self):
        """IMPLIED_VOLATILITY belongs to VOLATILITY category."""
        from src.greeks.models import RiskMetric, RiskMetricCategory

        assert RiskMetric.IMPLIED_VOLATILITY.category == RiskMetricCategory.VOLATILITY

    def test_coverage_category_is_data_quality(self):
        """COVERAGE belongs to DATA_QUALITY category."""
        from src.greeks.models import RiskMetric, RiskMetricCategory

        assert RiskMetric.COVERAGE.category == RiskMetricCategory.DATA_QUALITY

    def test_delta_is_greek_returns_true(self):
        """DELTA.is_greek returns True."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.DELTA.is_greek is True

    def test_gamma_is_greek_returns_true(self):
        """GAMMA.is_greek returns True."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.GAMMA.is_greek is True

    def test_vega_is_greek_returns_true(self):
        """VEGA.is_greek returns True."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.VEGA.is_greek is True

    def test_theta_is_greek_returns_true(self):
        """THETA.is_greek returns True."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.THETA.is_greek is True

    def test_implied_volatility_is_greek_returns_false(self):
        """IMPLIED_VOLATILITY.is_greek returns False."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.IMPLIED_VOLATILITY.is_greek is False

    def test_coverage_is_greek_returns_false(self):
        """COVERAGE.is_greek returns False."""
        from src.greeks.models import RiskMetric

        assert RiskMetric.COVERAGE.is_greek is False


class TestGreeksDataSource:
    """Tests for GreeksDataSource enum."""

    def test_futu_source_exists(self):
        """FUTU source exists with correct value."""
        from src.greeks.models import GreeksDataSource

        assert GreeksDataSource.FUTU.value == "futu"

    def test_model_source_exists(self):
        """MODEL source exists with correct value."""
        from src.greeks.models import GreeksDataSource

        assert GreeksDataSource.MODEL.value == "model"

    def test_cached_source_exists(self):
        """CACHED source exists with correct value."""
        from src.greeks.models import GreeksDataSource

        assert GreeksDataSource.CACHED.value == "cached"


class TestGreeksModel:
    """Tests for GreeksModel enum."""

    def test_futu_model_exists(self):
        """FUTU model exists with correct value."""
        from src.greeks.models import GreeksModel

        assert GreeksModel.FUTU.value == "futu"

    def test_bs_model_exists(self):
        """BS (Black-Scholes) model exists with correct value."""
        from src.greeks.models import GreeksModel

        assert GreeksModel.BS.value == "bs"

    def test_bjerksund_model_exists(self):
        """BJERKSUND (Bjerksund-Stensland) model exists with correct value."""
        from src.greeks.models import GreeksModel

        assert GreeksModel.BJERKSUND.value == "bjerksund"


class TestGreeksLevel:
    """Tests for GreeksLevel enum."""

    def test_normal_level_exists(self):
        """NORMAL level exists with correct value."""
        from src.greeks.models import GreeksLevel

        assert GreeksLevel.NORMAL.value == "normal"

    def test_warn_level_exists(self):
        """WARN level exists with correct value."""
        from src.greeks.models import GreeksLevel

        assert GreeksLevel.WARN.value == "warn"

    def test_crit_level_exists(self):
        """CRIT level exists with correct value."""
        from src.greeks.models import GreeksLevel

        assert GreeksLevel.CRIT.value == "crit"

    def test_hard_level_exists(self):
        """HARD level exists with correct value."""
        from src.greeks.models import GreeksLevel

        assert GreeksLevel.HARD.value == "hard"


class TestThresholdDirection:
    """Tests for ThresholdDirection enum."""

    def test_abs_direction_exists(self):
        """ABS direction exists with correct value."""
        from src.greeks.models import ThresholdDirection

        assert ThresholdDirection.ABS.value == "abs"

    def test_max_direction_exists(self):
        """MAX direction exists with correct value."""
        from src.greeks.models import ThresholdDirection

        assert ThresholdDirection.MAX.value == "max"

    def test_min_direction_exists(self):
        """MIN direction exists with correct value."""
        from src.greeks.models import ThresholdDirection

        assert ThresholdDirection.MIN.value == "min"


class TestGreeksMetricAlias:
    """Tests for GreeksMetric backward compatibility alias."""

    def test_greeks_metric_alias_exists(self):
        """GreeksMetric alias points to RiskMetric."""
        from src.greeks.models import GreeksMetric, RiskMetric

        assert GreeksMetric is RiskMetric
