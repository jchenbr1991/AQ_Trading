"""Tests for Greeks Alert Engine.

Tests cover:
- Task 8: AlertState dataclass
- Task 9: GreeksAlert dataclass
- Task 10: Threshold detection with hysteresis
- Task 11: Rate of change detection
- Task 12: AlertEngine class with state management
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


def _make_aggregated_greeks(
    scope: str = "ACCOUNT",
    scope_id: str = "acc_001",
    dollar_delta: Decimal = Decimal("0"),
    gamma_dollar: Decimal = Decimal("0"),
    vega_per_1pct: Decimal = Decimal("0"),
    theta_per_day: Decimal = Decimal("0"),
    as_of_ts: datetime | None = None,
):
    """Factory function to create AggregatedGreeks for testing."""
    from src.greeks.models import AggregatedGreeks

    return AggregatedGreeks(
        scope=scope,
        scope_id=scope_id,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
    )


class TestFormatMetricValue:
    """Tests for _format_metric_value helper - V1.5."""

    def test_format_delta_no_suffix(self):
        """Delta values have no unit suffix."""
        from src.greeks.alerts import _format_metric_value
        from src.greeks.models import RiskMetric

        result = _format_metric_value(RiskMetric.DELTA, Decimal("5000"))
        assert result == "$5000"

    def test_format_theta_trading_day_suffix(self):
        """Theta values include /trading day suffix to clarify time unit."""
        from src.greeks.alerts import _format_metric_value
        from src.greeks.models import RiskMetric

        result = _format_metric_value(RiskMetric.THETA, Decimal("-150"))
        assert result == "$-150/trading day"

    def test_format_vega_iv_suffix(self):
        """Vega values include /1% IV suffix."""
        from src.greeks.alerts import _format_metric_value
        from src.greeks.models import RiskMetric

        result = _format_metric_value(RiskMetric.VEGA, Decimal("200"))
        assert result == "$200/1% IV"

    def test_format_gamma_no_suffix(self):
        """Gamma values have no unit suffix."""
        from src.greeks.alerts import _format_metric_value
        from src.greeks.models import RiskMetric

        result = _format_metric_value(RiskMetric.GAMMA, Decimal("100"))
        assert result == "$100"


class TestAlertState:
    """Tests for AlertState dataclass - Task 8."""

    def test_alert_state_creation_with_required_fields(self):
        """AlertState can be created with required fields."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        now = datetime.now(timezone.utc)
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=now,
        )

        assert state.scope == "ACCOUNT"
        assert state.scope_id == "acc_001"
        assert state.metric == RiskMetric.DELTA
        assert state.current_level == GreeksLevel.WARN
        assert state.current_value == Decimal("42000")
        assert state.threshold_config == config
        assert state.entered_at == now

    def test_alert_state_default_ttl_seconds(self):
        """AlertState has default ttl_seconds of 86400 (24 hours)."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.NORMAL,
            current_value=Decimal("10000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc),
        )

        assert state.ttl_seconds == 86400

    def test_alert_state_last_alert_at_default_none(self):
        """AlertState has default last_alert_at of None."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.NORMAL,
            current_value=Decimal("10000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc),
        )

        assert state.last_alert_at is None

    def test_alert_state_is_expired_false_when_within_ttl(self):
        """AlertState.is_expired() returns False when within TTL."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Created 1 hour ago, TTL is 24 hours
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ttl_seconds=86400,
        )

        assert state.is_expired() is False

    def test_alert_state_is_expired_true_when_past_ttl(self):
        """AlertState.is_expired() returns True when past TTL."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Created 25 hours ago, TTL is 24 hours
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(hours=25),
            ttl_seconds=86400,
        )

        assert state.is_expired() is True

    def test_alert_state_can_send_alert_true_when_no_prior_alert(self):
        """AlertState.can_send_alert() returns True when last_alert_at is None."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc),
            last_alert_at=None,
        )

        assert state.can_send_alert(dedupe_window=900) is True

    def test_alert_state_can_send_alert_false_within_dedupe_window(self):
        """AlertState.can_send_alert() returns False within dedupe window."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Last alert was 5 minutes ago, dedupe window is 15 minutes
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(hours=1),
            last_alert_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        assert state.can_send_alert(dedupe_window=900) is False

    def test_alert_state_can_send_alert_true_past_dedupe_window(self):
        """AlertState.can_send_alert() returns True past dedupe window."""
        from src.greeks.alerts import AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Last alert was 20 minutes ago, dedupe window is 15 minutes
        state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(hours=1),
            last_alert_at=datetime.now(timezone.utc) - timedelta(minutes=20),
        )

        assert state.can_send_alert(dedupe_window=900) is True


class TestGreeksAlert:
    """Tests for GreeksAlert dataclass - Task 9."""

    def test_greeks_alert_threshold_type_creation(self):
        """GreeksAlert can be created with THRESHOLD alert_type."""
        from src.greeks.alerts import GreeksAlert
        from src.greeks.models import GreeksLevel, RiskMetric

        now = datetime.now(timezone.utc)

        alert = GreeksAlert(
            alert_id="550e8400-e29b-41d4-a716-446655440000",
            alert_type="THRESHOLD",
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_value=Decimal("40000"),
            message="Delta exceeded WARN threshold",
            created_at=now,
        )

        assert alert.alert_id == "550e8400-e29b-41d4-a716-446655440000"
        assert alert.alert_type == "THRESHOLD"
        assert alert.scope == "ACCOUNT"
        assert alert.scope_id == "acc_001"
        assert alert.metric == RiskMetric.DELTA
        assert alert.level == GreeksLevel.WARN
        assert alert.current_value == Decimal("42000")
        assert alert.threshold_value == Decimal("40000")
        assert alert.message == "Delta exceeded WARN threshold"
        assert alert.created_at == now

    def test_greeks_alert_roc_type_creation(self):
        """GreeksAlert can be created with ROC alert_type."""
        from src.greeks.alerts import GreeksAlert
        from src.greeks.models import GreeksLevel, RiskMetric

        now = datetime.now(timezone.utc)

        alert = GreeksAlert(
            alert_id="550e8400-e29b-41d4-a716-446655440001",
            alert_type="ROC",
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.GAMMA,
            level=GreeksLevel.WARN,
            current_value=Decimal("8000"),
            threshold_value=Decimal("1000"),
            prev_value=Decimal("5000"),
            change_pct=Decimal("60.0"),
            message="Gamma changed by 60% (threshold: 20%)",
            created_at=now,
        )

        assert alert.alert_type == "ROC"
        assert alert.prev_value == Decimal("5000")
        assert alert.change_pct == Decimal("60.0")

    def test_greeks_alert_defaults_for_optional_fields(self):
        """GreeksAlert has correct defaults for optional fields."""
        from src.greeks.alerts import GreeksAlert
        from src.greeks.models import GreeksLevel, RiskMetric

        alert = GreeksAlert(
            alert_id="test-id",
            alert_type="THRESHOLD",
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_value=Decimal("40000"),
            message="Test alert",
            created_at=datetime.now(timezone.utc),
        )

        assert alert.prev_value is None
        assert alert.change_pct is None

    def test_greeks_alert_strategy_scope(self):
        """GreeksAlert can have STRATEGY scope."""
        from src.greeks.alerts import GreeksAlert
        from src.greeks.models import GreeksLevel, RiskMetric

        alert = GreeksAlert(
            alert_id="test-id",
            alert_type="THRESHOLD",
            scope="STRATEGY",
            scope_id="momentum_v1",
            metric=RiskMetric.VEGA,
            level=GreeksLevel.CRIT,
            current_value=Decimal("25000"),
            threshold_value=Decimal("20000"),
            message="Vega exceeded CRIT threshold for momentum_v1",
            created_at=datetime.now(timezone.utc),
        )

        assert alert.scope == "STRATEGY"
        assert alert.scope_id == "momentum_v1"


class TestThresholdDetection:
    """Tests for threshold detection with hysteresis - Task 10."""

    def test_check_threshold_normal_below_warn(self):
        """_check_threshold returns NORMAL when value below warn threshold."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            # warn_threshold = 50000 * 0.80 = 40000
        )

        # Value is 30000, below warn threshold of 40000
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("30000"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.NORMAL

    def test_check_threshold_warn_between_warn_and_crit(self):
        """_check_threshold returns WARN when value between warn and crit thresholds."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            # warn_threshold = 40000, crit_threshold = 50000
        )

        # Value is 45000, between warn (40000) and crit (50000)
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("45000"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.WARN

    def test_check_threshold_crit_between_crit_and_hard(self):
        """_check_threshold returns CRIT when value between crit and hard thresholds."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            # crit_threshold = 50000, hard_threshold = 60000
        )

        # Value is 55000, between crit (50000) and hard (60000)
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("55000"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.CRIT

    def test_check_threshold_hard_above_hard(self):
        """_check_threshold returns HARD when value above hard threshold."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            # hard_threshold = 50000 * 1.20 = 60000
        )

        # Value is 65000, above hard threshold of 60000
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("65000"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.HARD

    def test_check_threshold_abs_direction_uses_absolute_value(self):
        """_check_threshold with ABS direction uses abs(value)."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
            ThresholdDirection,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            direction=ThresholdDirection.ABS,
            limit=Decimal("50000"),
            # warn_threshold = 40000
        )

        # Negative value, but absolute value is 45000
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("-45000"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.WARN

    def test_check_threshold_max_direction_uses_value_directly(self):
        """_check_threshold with MAX direction uses value directly."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
            ThresholdDirection,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.IMPLIED_VOLATILITY,
            direction=ThresholdDirection.MAX,
            limit=Decimal("2.0"),  # 200% IV
            # warn_threshold = 1.6
        )

        # Value is 1.8, above warn threshold
        level = engine._check_threshold(
            metric=RiskMetric.IMPLIED_VOLATILITY,
            value=Decimal("1.8"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.WARN

    def test_check_threshold_max_direction_negative_value_normal(self):
        """_check_threshold with MAX direction: negative value is NORMAL."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
            ThresholdDirection,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.IMPLIED_VOLATILITY,
            direction=ThresholdDirection.MAX,
            limit=Decimal("2.0"),
        )

        # Negative value is always below threshold for MAX direction
        level = engine._check_threshold(
            metric=RiskMetric.IMPLIED_VOLATILITY,
            value=Decimal("-1.8"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.NORMAL

    def test_check_threshold_min_direction_uses_negated_value(self):
        """_check_threshold with MIN direction uses -value (breach if value < threshold)."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
            ThresholdDirection,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.THETA,
            direction=ThresholdDirection.MIN,
            limit=Decimal("5000"),  # Lower bound
            # warn_threshold = 5000 * 0.80 = 4000
            # crit_threshold = 5000 * 1.00 = 5000
        )

        # For MIN direction, we breach when value drops below threshold
        # Effective value = -value, so if value = -4500, effective = 4500
        # 4500 >= warn_threshold (4000) and < crit_threshold (5000) -> WARN
        level = engine._check_threshold(
            metric=RiskMetric.THETA,
            value=Decimal("-4500"),
            config=config,
            current_state=None,
        )

        assert level == GreeksLevel.WARN

    def test_check_threshold_hysteresis_remains_warn_above_recover(self):
        """Hysteresis: stays WARN if value above warn_recover threshold."""
        from src.greeks.alerts import AlertEngine, AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            warn_pct=Decimal("0.80"),
            warn_recover_pct=Decimal("0.75"),
            # warn_threshold = 40000
            # warn_recover = 50000 * 0.75 = 37500
        )

        # Currently in WARN state
        current_state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

        # Value dropped to 38000, still above warn_recover (37500)
        # Should remain WARN due to hysteresis
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("38000"),
            config=config,
            current_state=current_state,
        )

        assert level == GreeksLevel.WARN

    def test_check_threshold_hysteresis_recovers_to_normal_below_recover(self):
        """Hysteresis: recovers to NORMAL when below warn_recover threshold."""
        from src.greeks.alerts import AlertEngine, AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            warn_pct=Decimal("0.80"),
            warn_recover_pct=Decimal("0.75"),
            # warn_threshold = 40000
            # warn_recover = 37500
        )

        # Currently in WARN state
        current_state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )

        # Value dropped to 35000, below warn_recover (37500)
        # Should recover to NORMAL
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("35000"),
            config=config,
            current_state=current_state,
        )

        assert level == GreeksLevel.NORMAL

    def test_check_threshold_hysteresis_crit_to_warn_recovery(self):
        """Hysteresis: CRIT recovers to WARN when below crit_recover."""
        from src.greeks.alerts import AlertEngine, AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            crit_pct=Decimal("1.00"),
            crit_recover_pct=Decimal("0.90"),
            # crit_threshold = 50000
            # crit_recover = 45000
        )

        # Currently in CRIT state
        current_state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.CRIT,
            current_value=Decimal("52000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        # Value dropped to 42000, below crit_recover (45000)
        # Should recover to WARN (still above warn)
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("42000"),
            config=config,
            current_state=current_state,
        )

        assert level == GreeksLevel.WARN

    def test_check_threshold_escalates_from_warn_to_crit(self):
        """Threshold detection escalates from WARN to CRIT when crossing crit threshold."""
        from src.greeks.alerts import AlertEngine, AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Currently in WARN state
        current_state = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        # Value increased to 52000, above crit threshold (50000)
        level = engine._check_threshold(
            metric=RiskMetric.DELTA,
            value=Decimal("52000"),
            config=config,
            current_state=current_state,
        )

        assert level == GreeksLevel.CRIT


class TestRateOfChangeDetection:
    """Tests for rate of change detection - Task 11."""

    def test_check_roc_no_alert_below_threshold(self):
        """_check_rate_of_change returns None when change below threshold."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import GreeksThresholdConfig, RiskMetric

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            rate_change_pct=Decimal("0.20"),  # 20%
            rate_change_abs=Decimal("5000"),
        )

        # Change of 2000 is 4% of limit (50000), below 20%
        # And below absolute threshold of 5000
        result = engine._check_rate_of_change(
            metric=RiskMetric.DELTA,
            current_value=Decimal("32000"),
            prev_value=Decimal("30000"),
            config=config,
        )

        assert result is None

    def test_check_roc_triggers_on_absolute_change(self):
        """_check_rate_of_change triggers alert when abs change exceeds threshold."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import GreeksThresholdConfig, RiskMetric

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            rate_change_pct=Decimal("0.20"),  # 20%
            rate_change_abs=Decimal("5000"),
        )

        # Change of 6000 exceeds absolute threshold of 5000
        result = engine._check_rate_of_change(
            metric=RiskMetric.DELTA,
            current_value=Decimal("36000"),
            prev_value=Decimal("30000"),
            config=config,
        )

        assert result is not None
        assert result.alert_type == "ROC"
        assert result.metric == RiskMetric.DELTA
        assert result.current_value == Decimal("36000")
        assert result.prev_value == Decimal("30000")

    def test_check_roc_triggers_on_percentage_change(self):
        """_check_rate_of_change triggers alert when pct change exceeds threshold."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import GreeksThresholdConfig, RiskMetric

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.GAMMA,
            limit=Decimal("10000"),
            rate_change_pct=Decimal("0.20"),  # 20% of limit = 2000
            rate_change_abs=Decimal("0"),  # Disabled
        )

        # Change of 2500 is 25% of limit (10000), exceeds 20%
        result = engine._check_rate_of_change(
            metric=RiskMetric.GAMMA,
            current_value=Decimal("7500"),
            prev_value=Decimal("5000"),
            config=config,
        )

        assert result is not None
        assert result.alert_type == "ROC"
        assert result.change_pct is not None

    def test_check_roc_handles_negative_change(self):
        """_check_rate_of_change detects rapid decrease."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import GreeksThresholdConfig, RiskMetric

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            rate_change_pct=Decimal("0.20"),
            rate_change_abs=Decimal("5000"),
        )

        # Change of -7000 exceeds absolute threshold (uses abs)
        result = engine._check_rate_of_change(
            metric=RiskMetric.DELTA,
            current_value=Decimal("23000"),
            prev_value=Decimal("30000"),
            config=config,
        )

        assert result is not None
        assert result.alert_type == "ROC"

    def test_check_roc_no_alert_when_abs_threshold_zero(self):
        """_check_rate_of_change ignores abs threshold when zero."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import GreeksThresholdConfig, RiskMetric

        engine = AlertEngine()
        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
            rate_change_pct=Decimal("0.50"),  # 50%
            rate_change_abs=Decimal("0"),  # Disabled
        )

        # Change of 6000 is 12% of limit, below 50%
        result = engine._check_rate_of_change(
            metric=RiskMetric.DELTA,
            current_value=Decimal("36000"),
            prev_value=Decimal("30000"),
            config=config,
        )

        assert result is None


class TestAlertEngine:
    """Tests for AlertEngine class - Task 12."""

    def test_alert_engine_initialization(self):
        """AlertEngine initializes with empty state."""
        from src.greeks.alerts import AlertEngine

        engine = AlertEngine()

        assert engine._states == {}
        assert engine._state_ttl_seconds == 86400

    def test_alert_engine_custom_ttl(self):
        """AlertEngine accepts custom TTL."""
        from src.greeks.alerts import AlertEngine

        engine = AlertEngine(state_ttl_seconds=3600)

        assert engine._state_ttl_seconds == 3600

    def test_alert_engine_check_alerts_generates_threshold_alert(self):
        """AlertEngine.check_alerts generates alert when threshold breached."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
        )

        aggregated = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),  # Above warn (40000)
        )

        alerts = engine.check_alerts(aggregated, config)

        assert len(alerts) == 1
        assert alerts[0].alert_type == "THRESHOLD"
        assert alerts[0].metric == RiskMetric.DELTA
        assert alerts[0].level == GreeksLevel.WARN
        assert alerts[0].scope == "ACCOUNT"
        assert alerts[0].scope_id == "acc_001"

    def test_alert_engine_check_alerts_no_alert_below_threshold(self):
        """AlertEngine.check_alerts returns empty when below all thresholds."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
        )

        aggregated = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("30000"),  # Below warn (40000)
        )

        alerts = engine.check_alerts(aggregated, config)

        assert len(alerts) == 0

    def test_alert_engine_check_alerts_updates_state(self):
        """AlertEngine.check_alerts updates internal state."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
        )

        aggregated = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
        )

        engine.check_alerts(aggregated, config)

        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state is not None
        assert state.current_level == GreeksLevel.WARN
        assert state.current_value == Decimal("45000")

    def test_alert_engine_check_alerts_deduplicates_alerts(self):
        """AlertEngine.check_alerts respects deduplication window."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
            dedupe_window_seconds_by_level={
                GreeksLevel.WARN: 900,  # 15 minutes
                GreeksLevel.CRIT: 300,
                GreeksLevel.HARD: 60,
            },
        )

        aggregated = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
        )

        # First check generates alert
        alerts1 = engine.check_alerts(aggregated, config)
        assert len(alerts1) == 1

        # Second check within dedupe window should not generate alert
        alerts2 = engine.check_alerts(aggregated, config)
        assert len(alerts2) == 0

    def test_alert_engine_check_alerts_with_prev_greeks_generates_roc_alert(self):
        """AlertEngine.check_alerts generates ROC alert when rate of change exceeded."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    rate_change_abs=Decimal("5000"),
                ),
            },
        )

        prev_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("30000"),
        )

        current_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("38000"),  # Change of 8000, exceeds 5000 threshold
        )

        alerts = engine.check_alerts(current_greeks, config, prev_greeks=prev_greeks)

        # Should have ROC alert (may also have threshold alert depending on level)
        roc_alerts = [a for a in alerts if a.alert_type == "ROC"]
        assert len(roc_alerts) == 1
        assert roc_alerts[0].metric == RiskMetric.DELTA
        assert roc_alerts[0].prev_value == Decimal("30000")

    def test_alert_engine_check_alerts_multiple_metrics(self):
        """AlertEngine.check_alerts handles multiple metrics."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
                RiskMetric.GAMMA: GreeksThresholdConfig(
                    metric=RiskMetric.GAMMA,
                    limit=Decimal("10000"),
                ),
            },
        )

        aggregated = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),  # WARN for delta
            gamma_dollar=Decimal("11000"),  # CRIT for gamma
        )

        alerts = engine.check_alerts(aggregated, config)

        # Should have alerts for both metrics
        assert len(alerts) == 2
        metrics = {a.metric for a in alerts}
        assert RiskMetric.DELTA in metrics
        assert RiskMetric.GAMMA in metrics

        # Check correct levels
        delta_alert = next(a for a in alerts if a.metric == RiskMetric.DELTA)
        gamma_alert = next(a for a in alerts if a.metric == RiskMetric.GAMMA)
        assert delta_alert.level == GreeksLevel.WARN
        assert gamma_alert.level == GreeksLevel.CRIT

    def test_alert_engine_get_state_returns_none_when_not_exists(self):
        """AlertEngine.get_state returns None when state doesn't exist."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import RiskMetric

        engine = AlertEngine()

        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)

        assert state is None

    def test_alert_engine_cleanup_expired_states_removes_old_states(self):
        """AlertEngine.cleanup_expired_states removes expired states."""
        from src.greeks.alerts import AlertEngine, AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine(state_ttl_seconds=3600)  # 1 hour TTL

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Manually add an expired state
        key = ("ACCOUNT", "acc_001", RiskMetric.DELTA)
        engine._states[key] = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(hours=2),  # Expired
            ttl_seconds=3600,
        )

        # Add a non-expired state
        key2 = ("ACCOUNT", "acc_002", RiskMetric.DELTA)
        engine._states[key2] = AlertState(
            scope="ACCOUNT",
            scope_id="acc_002",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(minutes=30),  # Not expired
            ttl_seconds=3600,
        )

        removed_count = engine.cleanup_expired_states()

        assert removed_count == 1
        assert key not in engine._states
        assert key2 in engine._states

    def test_alert_engine_cleanup_expired_states_returns_zero_when_none_expired(self):
        """AlertEngine.cleanup_expired_states returns 0 when no states expired."""
        from src.greeks.alerts import AlertEngine, AlertState
        from src.greeks.models import (
            GreeksLevel,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine(state_ttl_seconds=86400)

        config = GreeksThresholdConfig(
            metric=RiskMetric.DELTA,
            limit=Decimal("50000"),
        )

        # Add a non-expired state
        key = ("ACCOUNT", "acc_001", RiskMetric.DELTA)
        engine._states[key] = AlertState(
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            current_level=GreeksLevel.WARN,
            current_value=Decimal("42000"),
            threshold_config=config,
            entered_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ttl_seconds=86400,
        )

        removed_count = engine.cleanup_expired_states()

        assert removed_count == 0
        assert key in engine._states

    def test_alert_engine_escalation_generates_new_alert(self):
        """AlertEngine generates alert when escalating from WARN to CRIT."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                ),
            },
        )

        # First trigger WARN
        aggregated_warn = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
        )
        alerts1 = engine.check_alerts(aggregated_warn, config)
        assert len(alerts1) == 1
        assert alerts1[0].level == GreeksLevel.WARN

        # Now escalate to CRIT - should generate new alert
        aggregated_crit = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("55000"),
        )
        alerts2 = engine.check_alerts(aggregated_crit, config)
        assert len(alerts2) == 1
        assert alerts2[0].level == GreeksLevel.CRIT

    def test_alert_engine_recovery_clears_state_level(self):
        """AlertEngine updates state when recovering to NORMAL."""
        from src.greeks.alerts import AlertEngine
        from src.greeks.models import (
            GreeksLevel,
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )

        engine = AlertEngine()
        config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("50000"),
                    warn_recover_pct=Decimal("0.75"),  # 37500
                ),
            },
        )

        # First trigger WARN
        aggregated_warn = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
        )
        engine.check_alerts(aggregated_warn, config)

        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state is not None
        assert state.current_level == GreeksLevel.WARN

        # Now recover below threshold
        aggregated_normal = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("35000"),  # Below warn_recover (37500)
        )
        engine.check_alerts(aggregated_normal, config)

        state = engine.get_state("ACCOUNT", "acc_001", RiskMetric.DELTA)
        assert state is not None
        assert state.current_level == GreeksLevel.NORMAL
