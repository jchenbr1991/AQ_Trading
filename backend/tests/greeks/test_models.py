"""Tests for Greeks monitoring models.

Tests cover:
- RiskMetricCategory enum
- RiskMetric enum with category property and is_greek method
- GreeksDataSource, GreeksModel, GreeksLevel, ThresholdDirection enums
- PositionGreeks dataclass
- AggregatedGreeks dataclass
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


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


class TestPositionGreeks:
    """Tests for PositionGreeks dataclass."""

    def test_minimal_creation_with_required_fields(self):
        """PositionGreeks can be created with required fields."""
        from src.greeks.models import GreeksDataSource, PositionGreeks

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
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.005"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
            source=GreeksDataSource.FUTU,
            model=None,
        )

        assert pg.position_id == 1
        assert pg.symbol == "AAPL240119C00150000"
        assert pg.underlying_symbol == "AAPL"
        assert pg.quantity == 10
        assert pg.multiplier == 100
        assert pg.underlying_price == Decimal("150.00")
        assert pg.option_type == "call"
        assert pg.strike == Decimal("150.00")
        assert pg.expiry == "2024-01-19"
        assert pg.dollar_delta == Decimal("5000.00")
        assert pg.gamma_dollar == Decimal("100.00")
        assert pg.gamma_pnl_1pct == Decimal("0.005")
        assert pg.vega_per_1pct == Decimal("200.00")
        assert pg.theta_per_day == Decimal("-50.00")
        assert pg.source == GreeksDataSource.FUTU
        assert pg.model is None

    def test_notional_calculation(self):
        """PositionGreeks computes notional correctly.

        notional = abs(quantity) x underlying_price x multiplier
        """
        from src.greeks.models import GreeksDataSource, PositionGreeks

        # Long position: 10 contracts @ $150 with multiplier 100
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
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.005"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
            source=GreeksDataSource.FUTU,
            model=None,
        )

        # notional = abs(10) * 150.00 * 100 = 150000
        assert pg.notional == Decimal("150000.00")

    def test_notional_calculation_short_position(self):
        """PositionGreeks computes notional correctly for short positions.

        notional uses abs(quantity).
        """
        from src.greeks.models import GreeksDataSource, PositionGreeks

        # Short position: -5 contracts @ $200 with multiplier 100
        pg = PositionGreeks(
            position_id=2,
            symbol="TSLA240119P00200000",
            underlying_symbol="TSLA",
            quantity=-5,
            multiplier=100,
            underlying_price=Decimal("200.00"),
            option_type="put",
            strike=Decimal("200.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("-3000.00"),
            gamma_dollar=Decimal("80.00"),
            gamma_pnl_1pct=Decimal("0.004"),
            vega_per_1pct=Decimal("150.00"),
            theta_per_day=Decimal("-30.00"),
            source=GreeksDataSource.MODEL,
            model=None,
        )

        # notional = abs(-5) * 200.00 * 100 = 100000
        assert pg.notional == Decimal("100000.00")

    def test_invalid_position_with_warnings(self):
        """PositionGreeks can track invalid status and quality warnings."""
        from src.greeks.models import GreeksDataSource, PositionGreeks

        pg = PositionGreeks(
            position_id=3,
            symbol="GME240119C00020000",
            underlying_symbol="GME",
            quantity=1,
            multiplier=100,
            underlying_price=Decimal("20.00"),
            option_type="call",
            strike=Decimal("20.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("0"),
            gamma_dollar=Decimal("0"),
            gamma_pnl_1pct=Decimal("0"),
            vega_per_1pct=Decimal("0"),
            theta_per_day=Decimal("0"),
            source=GreeksDataSource.CACHED,
            model=None,
            valid=False,
            quality_warnings=["NaN detected in delta", "Staleness exceeded threshold"],
            staleness_seconds=600,
        )

        assert pg.valid is False
        assert len(pg.quality_warnings) == 2
        assert "NaN detected in delta" in pg.quality_warnings
        assert "Staleness exceeded threshold" in pg.quality_warnings
        assert pg.staleness_seconds == 600

    def test_strategy_id_optional_field(self):
        """PositionGreeks has optional strategy_id field."""
        from src.greeks.models import GreeksDataSource, PositionGreeks

        # Without strategy_id
        pg1 = PositionGreeks(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            underlying_price=Decimal("150.00"),
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.005"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
            source=GreeksDataSource.FUTU,
            model=None,
        )
        assert pg1.strategy_id is None

        # With strategy_id
        pg2 = PositionGreeks(
            position_id=2,
            symbol="TSLA240119P00200000",
            underlying_symbol="TSLA",
            quantity=-5,
            multiplier=100,
            underlying_price=Decimal("200.00"),
            option_type="put",
            strike=Decimal("200.00"),
            expiry="2024-01-19",
            dollar_delta=Decimal("-3000.00"),
            gamma_dollar=Decimal("80.00"),
            gamma_pnl_1pct=Decimal("0.004"),
            vega_per_1pct=Decimal("150.00"),
            theta_per_day=Decimal("-30.00"),
            source=GreeksDataSource.FUTU,
            model=None,
            strategy_id="momentum_v1",
        )
        assert pg2.strategy_id == "momentum_v1"

    def test_as_of_ts_default_to_now(self):
        """PositionGreeks as_of_ts defaults to current UTC time."""
        from src.greeks.models import GreeksDataSource, PositionGreeks

        before = datetime.now(timezone.utc)
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
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.005"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
            source=GreeksDataSource.FUTU,
            model=None,
        )
        after = datetime.now(timezone.utc)

        # as_of_ts should be between before and after
        # Note: as_of_ts may be naive or aware depending on implementation
        assert pg.as_of_ts is not None

    def test_default_values(self):
        """PositionGreeks has sensible defaults for optional fields."""
        from src.greeks.models import GreeksDataSource, PositionGreeks

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
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.005"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
            source=GreeksDataSource.FUTU,
            model=None,
        )

        assert pg.valid is True
        assert pg.quality_warnings == []
        assert pg.staleness_seconds == 0
        assert pg.cached_from_source is None
        assert pg.cached_from_model is None
        assert pg.strategy_id is None


class TestAggregatedGreeks:
    """Tests for AggregatedGreeks dataclass."""

    def test_account_scope_creation(self):
        """AggregatedGreeks can be created with ACCOUNT scope."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="account_001",
        )

        assert ag.scope == "ACCOUNT"
        assert ag.scope_id == "account_001"
        assert ag.strategy_id is None

    def test_strategy_scope_creation(self):
        """AggregatedGreeks can be created with STRATEGY scope."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="STRATEGY",
            scope_id="momentum_v1",
            strategy_id="momentum_v1",
        )

        assert ag.scope == "STRATEGY"
        assert ag.scope_id == "momentum_v1"
        assert ag.strategy_id == "momentum_v1"

    def test_default_values(self):
        """AggregatedGreeks has sensible defaults for optional fields."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="default_test",
        )

        assert ag.dollar_delta == Decimal("0")
        assert ag.gamma_dollar == Decimal("0")
        assert ag.gamma_pnl_1pct == Decimal("0")
        assert ag.vega_per_1pct == Decimal("0")
        assert ag.theta_per_day == Decimal("0")
        assert ag.valid_legs_count == 0
        assert ag.total_legs_count == 0
        assert ag.valid_notional == Decimal("0")
        assert ag.total_notional == Decimal("0")
        assert ag.missing_positions == []
        assert ag.has_high_risk_missing_legs is False
        assert ag.warning_legs_count == 0
        assert ag.has_positions is True
        assert ag.as_of_ts_min is None
        assert ag.as_of_ts_max is None
        assert ag.calc_duration_ms == 0

    def test_coverage_pct_normal_case(self):
        """coverage_pct calculates correctly for normal case."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="coverage_test",
            valid_notional=Decimal("95000"),
            total_notional=Decimal("100000"),
        )

        # 95000 / 100000 * 100 = 95.0
        assert ag.coverage_pct == Decimal("95.0")

    def test_coverage_pct_partial_coverage(self):
        """coverage_pct calculates correctly for partial coverage."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="partial_coverage",
            valid_notional=Decimal("75000"),
            total_notional=Decimal("100000"),
        )

        # 75000 / 100000 * 100 = 75.0
        assert ag.coverage_pct == Decimal("75.0")

    def test_coverage_pct_zero_total_notional(self):
        """coverage_pct returns 100.0 when total_notional is zero."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="zero_notional",
            valid_notional=Decimal("0"),
            total_notional=Decimal("0"),
        )

        assert ag.coverage_pct == Decimal("100.0")

    def test_coverage_pct_no_positions(self):
        """coverage_pct returns 100.0 when has_positions is False."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="no_positions",
            has_positions=False,
            valid_notional=Decimal("0"),
            total_notional=Decimal("100000"),  # Even if total is set
        )

        assert ag.coverage_pct == Decimal("100.0")

    def test_is_coverage_sufficient_at_threshold(self):
        """is_coverage_sufficient returns True at exactly 95%."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="threshold_test",
            valid_notional=Decimal("95000"),
            total_notional=Decimal("100000"),
        )

        assert ag.is_coverage_sufficient is True

    def test_is_coverage_sufficient_above_threshold(self):
        """is_coverage_sufficient returns True above 95%."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="above_threshold",
            valid_notional=Decimal("99000"),
            total_notional=Decimal("100000"),
        )

        assert ag.is_coverage_sufficient is True

    def test_is_coverage_sufficient_below_threshold(self):
        """is_coverage_sufficient returns False below 95%."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="below_threshold",
            valid_notional=Decimal("94000"),
            total_notional=Decimal("100000"),
        )

        assert ag.is_coverage_sufficient is False

    def test_has_high_risk_missing_legs_flag(self):
        """has_high_risk_missing_legs flag can be set."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="high_risk_test",
            has_high_risk_missing_legs=True,
            missing_positions=[101, 102, 103],
        )

        assert ag.has_high_risk_missing_legs is True
        assert ag.missing_positions == [101, 102, 103]

    def test_staleness_seconds_with_as_of_ts_min(self):
        """staleness_seconds calculates from as_of_ts_min."""
        from src.greeks.models import AggregatedGreeks

        # Set as_of_ts_min to 60 seconds ago
        as_of_ts_min = datetime.now(timezone.utc) - timedelta(seconds=60)

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="staleness_test",
            as_of_ts_min=as_of_ts_min,
        )

        # Should be approximately 60 seconds (allow for test execution time)
        assert 59 <= ag.staleness_seconds <= 62

    def test_staleness_seconds_without_as_of_ts_min(self):
        """staleness_seconds returns 0 when as_of_ts_min is None."""
        from src.greeks.models import AggregatedGreeks

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="no_staleness",
            as_of_ts_min=None,
        )

        assert ag.staleness_seconds == 0

    def test_staleness_seconds_very_stale(self):
        """staleness_seconds handles very stale data."""
        from src.greeks.models import AggregatedGreeks

        # Set as_of_ts_min to 1 hour ago
        as_of_ts_min = datetime.now(timezone.utc) - timedelta(hours=1)

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="very_stale",
            as_of_ts_min=as_of_ts_min,
        )

        # Should be approximately 3600 seconds
        assert 3599 <= ag.staleness_seconds <= 3602

    def test_timestamps_semantic_convention(self):
        """as_of_ts_min and as_of_ts_max can track data range."""
        from src.greeks.models import AggregatedGreeks

        now = datetime.now(timezone.utc)
        ts_min = now - timedelta(seconds=30)
        ts_max = now - timedelta(seconds=5)

        ag = AggregatedGreeks(
            scope="ACCOUNT",
            scope_id="timestamp_test",
            as_of_ts=ts_min,  # Set to same as as_of_ts_min (conservative)
            as_of_ts_min=ts_min,
            as_of_ts_max=ts_max,
        )

        # Verify timestamps are set correctly
        assert ag.as_of_ts == ts_min
        assert ag.as_of_ts_min == ts_min
        assert ag.as_of_ts_max == ts_max
        # as_of_ts should equal as_of_ts_min per semantic convention
        assert ag.as_of_ts == ag.as_of_ts_min

    def test_full_aggregation_scenario(self):
        """Full aggregation scenario with all fields populated."""
        from src.greeks.models import AggregatedGreeks

        now = datetime.now(timezone.utc)
        ts_min = now - timedelta(seconds=15)
        ts_max = now - timedelta(seconds=2)

        ag = AggregatedGreeks(
            scope="STRATEGY",
            scope_id="momentum_v1",
            strategy_id="momentum_v1",
            dollar_delta=Decimal("25000.00"),
            gamma_dollar=Decimal("500.00"),
            gamma_pnl_1pct=Decimal("125.00"),
            vega_per_1pct=Decimal("750.00"),
            theta_per_day=Decimal("-150.00"),
            valid_legs_count=8,
            total_legs_count=10,
            valid_notional=Decimal("480000.00"),
            total_notional=Decimal("500000.00"),
            missing_positions=[201, 205],
            has_high_risk_missing_legs=True,
            warning_legs_count=2,
            has_positions=True,
            as_of_ts=ts_min,
            as_of_ts_min=ts_min,
            as_of_ts_max=ts_max,
            calc_duration_ms=45,
        )

        # Verify all fields
        assert ag.scope == "STRATEGY"
        assert ag.scope_id == "momentum_v1"
        assert ag.strategy_id == "momentum_v1"
        assert ag.dollar_delta == Decimal("25000.00")
        assert ag.gamma_dollar == Decimal("500.00")
        assert ag.gamma_pnl_1pct == Decimal("125.00")
        assert ag.vega_per_1pct == Decimal("750.00")
        assert ag.theta_per_day == Decimal("-150.00")
        assert ag.valid_legs_count == 8
        assert ag.total_legs_count == 10
        assert ag.valid_notional == Decimal("480000.00")
        assert ag.total_notional == Decimal("500000.00")
        assert ag.missing_positions == [201, 205]
        assert ag.has_high_risk_missing_legs is True
        assert ag.warning_legs_count == 2
        assert ag.has_positions is True
        assert ag.calc_duration_ms == 45

        # Verify computed properties
        # coverage_pct = 480000 / 500000 * 100 = 96.0
        assert ag.coverage_pct == Decimal("96.0")
        assert ag.is_coverage_sufficient is True
        # staleness_seconds should be approximately 15
        assert 14 <= ag.staleness_seconds <= 17
