"""Tests for degradation models."""

import time
from datetime import datetime, timezone

import pytest
from src.degradation.models import (
    MODE_PRIORITY,
    MUST_DELIVER_EVENTS,
    ActionType,
    ComponentSource,
    ComponentStatus,
    EventType,
    ModeTransition,
    ReasonCode,
    RecoveryStage,
    RecoveryTrigger,
    Severity,
    SystemEvent,
    SystemLevel,
    SystemMode,
    create_event,
)


class TestSystemMode:
    """Tests for SystemMode enum."""

    def test_all_modes_defined(self):
        """All 6 modes should be defined."""
        assert len(SystemMode) == 6
        assert SystemMode.NORMAL.value == "normal"
        assert SystemMode.DEGRADED.value == "degraded"
        assert SystemMode.SAFE_MODE.value == "safe_mode"
        assert SystemMode.SAFE_MODE_DISCONNECTED.value == "safe_mode_disconnected"
        assert SystemMode.HALT.value == "halt"
        assert SystemMode.RECOVERING.value == "recovering"


class TestModePriority:
    """Tests for MODE_PRIORITY conflict resolution."""

    def test_priority_order(self):
        """HALT should be highest priority, NORMAL lowest."""
        assert MODE_PRIORITY[SystemMode.NORMAL] == 0
        assert MODE_PRIORITY[SystemMode.RECOVERING] == 1
        assert MODE_PRIORITY[SystemMode.DEGRADED] == 2
        assert MODE_PRIORITY[SystemMode.SAFE_MODE] == 3
        assert MODE_PRIORITY[SystemMode.SAFE_MODE_DISCONNECTED] == 4
        assert MODE_PRIORITY[SystemMode.HALT] == 5

    def test_conflict_resolution_takes_max(self):
        """Conflict resolution should take most severe mode."""
        modes = [SystemMode.DEGRADED, SystemMode.SAFE_MODE, SystemMode.NORMAL]
        result = max(modes, key=lambda m: MODE_PRIORITY[m])
        assert result == SystemMode.SAFE_MODE

    def test_all_modes_have_priority(self):
        """Every SystemMode should have a priority defined."""
        for mode in SystemMode:
            assert mode in MODE_PRIORITY, f"Missing priority for {mode}"


class TestSystemLevel:
    """Tests for SystemLevel enum."""

    def test_all_levels_defined(self):
        """All 3 levels should be defined."""
        assert len(SystemLevel) == 3
        assert SystemLevel.HEALTHY.value == "healthy"
        assert SystemLevel.UNSTABLE.value == "unstable"
        assert SystemLevel.TRIPPED.value == "tripped"


class TestRecoveryStage:
    """Tests for RecoveryStage enum."""

    def test_all_stages_defined(self):
        """All 4 stages should be defined."""
        assert len(RecoveryStage) == 4
        assert RecoveryStage.CONNECT_BROKER.value == "connect_broker"
        assert RecoveryStage.CATCHUP_MARKETDATA.value == "catchup_marketdata"
        assert RecoveryStage.VERIFY_RISK.value == "verify_risk"
        assert RecoveryStage.READY.value == "ready"


class TestRecoveryTrigger:
    """Tests for RecoveryTrigger enum."""

    def test_all_triggers_defined(self):
        """All recovery triggers should be defined."""
        assert RecoveryTrigger.AUTO.value == "auto"
        assert RecoveryTrigger.MANUAL.value == "manual"
        assert RecoveryTrigger.COLD_START.value == "cold_start"


class TestEventType:
    """Tests for EventType enum."""

    def test_all_event_types_defined(self):
        """All event types should be defined."""
        assert EventType.FAIL_CRIT.value == "fail_crit"
        assert EventType.FAIL_SUPP.value == "fail_supp"
        assert EventType.RECOVERED.value == "recovered"
        assert EventType.HEARTBEAT.value == "heartbeat"
        assert EventType.QUALITY_DEGRADED.value == "quality_degraded"


class TestComponentSource:
    """Tests for ComponentSource enum."""

    def test_all_sources_defined(self):
        """All component sources should be defined."""
        assert ComponentSource.BROKER.value == "broker"
        assert ComponentSource.MARKET_DATA.value == "market_data"
        assert ComponentSource.RISK.value == "risk"
        assert ComponentSource.DB.value == "db"
        assert ComponentSource.ALERTS.value == "alerts"
        assert ComponentSource.SYSTEM.value == "system"


class TestSeverity:
    """Tests for Severity enum."""

    def test_all_severities_defined(self):
        """All severity levels should be defined."""
        assert Severity.INFO.value == "info"
        assert Severity.WARNING.value == "warning"
        assert Severity.CRITICAL.value == "critical"


class TestReasonCode:
    """Tests for ReasonCode enum."""

    def test_broker_reason_codes(self):
        """Broker-related reason codes should be defined."""
        assert ReasonCode.BROKER_DISCONNECT.value == "broker.disconnect"
        assert ReasonCode.BROKER_RECONNECTED.value == "broker.reconnected"
        assert ReasonCode.BROKER_REPORT_MISMATCH.value == "broker.report_mismatch"

    def test_market_data_reason_codes(self):
        """Market data reason codes should be defined."""
        assert ReasonCode.MD_STALE.value == "market_data.stale"
        assert ReasonCode.MD_QUALITY_DEGRADED.value == "market_data.quality_degraded"

    def test_risk_reason_codes(self):
        """Risk reason codes should be defined."""
        assert ReasonCode.RISK_TIMEOUT.value == "risk.timeout"
        assert ReasonCode.RISK_BREACH_HARD.value == "risk.breach_hard"

    def test_position_reason_codes(self):
        """Position reason codes should be defined."""
        assert ReasonCode.POSITION_TRUTH_UNKNOWN.value == "position.unknown"

    def test_db_reason_codes(self):
        """Database reason codes should be defined."""
        assert ReasonCode.DB_WRITE_FAIL.value == "db.write_fail"
        assert ReasonCode.DB_BUFFER_OVERFLOW.value == "db.buffer_overflow"

    def test_alert_reason_codes(self):
        """Alert reason codes should be defined."""
        assert ReasonCode.ALERTS_CHANNEL_DOWN.value == "alerts.channel_down"

    def test_recovery_reason_codes(self):
        """Recovery reason codes should be defined."""
        assert ReasonCode.COLD_START.value == "cold_start"
        assert ReasonCode.RECOVERY_FAILED.value == "recovery.failed"
        assert ReasonCode.ALL_HEALTHY.value == "all.healthy"


class TestActionType:
    """Tests for ActionType enum."""

    def test_all_action_types_defined(self):
        """All action types should be defined."""
        assert ActionType.OPEN.value == "open"
        assert ActionType.SEND.value == "send"
        assert ActionType.AMEND.value == "amend"
        assert ActionType.CANCEL.value == "cancel"
        assert ActionType.REDUCE_ONLY.value == "reduce_only"
        assert ActionType.QUERY.value == "query"


class TestSystemEvent:
    """Tests for SystemEvent dataclass."""

    def test_create_event(self):
        """SystemEvent should be creatable with required fields."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
        )

        assert event.event_type == EventType.FAIL_CRIT
        assert event.source == ComponentSource.BROKER
        assert event.severity == Severity.CRITICAL
        assert event.reason_code == ReasonCode.BROKER_DISCONNECT
        assert event.event_time_wall == now_wall
        assert event.event_time_mono == now_mono
        assert event.details is None
        assert event.ttl_seconds is None

    def test_create_event_with_optional_fields(self):
        """SystemEvent should accept optional fields."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()
        details = {"error": "Connection refused", "attempt": 3}

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
            details=details,
            ttl_seconds=60,
        )

        assert event.details == details
        assert event.ttl_seconds == 60

    def test_is_critical_whitelist(self):
        """Only whitelisted events should be critical."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        # Critical event (in whitelist)
        critical_event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
        )
        assert critical_event.is_critical() is True

        # Non-critical event (not in whitelist)
        non_critical_event = SystemEvent(
            event_type=EventType.FAIL_SUPP,
            source=ComponentSource.ALERTS,
            severity=Severity.WARNING,
            reason_code=ReasonCode.ALERTS_CHANNEL_DOWN,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
        )
        assert non_critical_event.is_critical() is False

    def test_is_critical_all_whitelist_events(self):
        """All MUST_DELIVER_EVENTS should be critical."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        for reason_code in MUST_DELIVER_EVENTS:
            event = SystemEvent(
                event_type=EventType.FAIL_CRIT,
                source=ComponentSource.BROKER,
                severity=Severity.CRITICAL,
                reason_code=reason_code,
                event_time_wall=now_wall,
                event_time_mono=now_mono,
            )
            assert event.is_critical() is True, f"{reason_code} should be critical"

    def test_must_deliver_events_whitelist(self):
        """MUST_DELIVER_EVENTS should contain only critical events."""
        assert ReasonCode.BROKER_DISCONNECT in MUST_DELIVER_EVENTS
        assert ReasonCode.POSITION_TRUTH_UNKNOWN in MUST_DELIVER_EVENTS
        assert ReasonCode.BROKER_REPORT_MISMATCH in MUST_DELIVER_EVENTS
        assert ReasonCode.RISK_BREACH_HARD in MUST_DELIVER_EVENTS
        # Non-critical should not be in whitelist
        assert ReasonCode.ALERTS_CHANNEL_DOWN not in MUST_DELIVER_EVENTS
        assert ReasonCode.MD_QUALITY_DEGRADED not in MUST_DELIVER_EVENTS

    def test_must_deliver_events_is_frozen(self):
        """MUST_DELIVER_EVENTS should be immutable."""
        assert isinstance(MUST_DELIVER_EVENTS, frozenset)

    def test_event_immutable(self):
        """SystemEvent should be immutable (frozen dataclass)."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
        )

        with pytest.raises(AttributeError):
            event.severity = Severity.WARNING  # type: ignore[misc]

    def test_event_to_dict(self):
        """SystemEvent should be convertible to dict for serialization."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
            details={"error": "test"},
            ttl_seconds=60,
        )

        d = event.to_dict()

        assert d["event_type"] == "fail_crit"
        assert d["source"] == "broker"
        assert d["severity"] == "critical"
        assert d["reason_code"] == "broker.disconnect"
        assert d["event_time_wall"] == now_wall.isoformat()
        assert d["event_time_mono"] == now_mono
        assert d["details"] == {"error": "test"}
        assert d["ttl_seconds"] == 60

    def test_event_is_expired_no_ttl(self):
        """Event without TTL should never expire."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
            ttl_seconds=None,
        )

        assert event.is_expired() is False

    def test_event_is_expired_within_ttl(self):
        """Event within TTL should not be expired."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
            ttl_seconds=60,
        )

        assert event.is_expired() is False

    def test_event_is_expired_past_ttl(self):
        """Event past TTL should be expired."""
        now_wall = datetime.now(tz=timezone.utc)
        # Set event time to 2 seconds ago with 1 second TTL
        past_mono = time.monotonic() - 2.0

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=past_mono,
            ttl_seconds=1,
        )

        assert event.is_expired() is True


class TestModeTransition:
    """Tests for ModeTransition dataclass."""

    def test_create_mode_transition(self):
        """ModeTransition should be creatable with required fields."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        transition = ModeTransition(
            from_mode=SystemMode.NORMAL,
            to_mode=SystemMode.DEGRADED,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            source=ComponentSource.BROKER,
            timestamp_wall=now_wall,
            timestamp_mono=now_mono,
        )

        assert transition.from_mode == SystemMode.NORMAL
        assert transition.to_mode == SystemMode.DEGRADED
        assert transition.reason_code == ReasonCode.BROKER_DISCONNECT
        assert transition.source == ComponentSource.BROKER
        assert transition.timestamp_wall == now_wall
        assert transition.timestamp_mono == now_mono
        assert transition.operator_id is None
        assert transition.override_ttl is None

    def test_create_mode_transition_with_optional_fields(self):
        """ModeTransition should accept optional fields."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        transition = ModeTransition(
            from_mode=SystemMode.DEGRADED,
            to_mode=SystemMode.SAFE_MODE,
            reason_code=ReasonCode.RISK_BREACH_HARD,
            source=ComponentSource.SYSTEM,
            timestamp_wall=now_wall,
            timestamp_mono=now_mono,
            operator_id="ops-user-123",
            override_ttl=3600,
        )

        assert transition.operator_id == "ops-user-123"
        assert transition.override_ttl == 3600


class TestComponentStatus:
    """Tests for ComponentStatus dataclass."""

    def test_create_component_status(self):
        """ComponentStatus should be creatable with required fields."""
        now_mono = time.monotonic()

        status = ComponentStatus(
            source=ComponentSource.BROKER,
            level=SystemLevel.HEALTHY,
            last_event=None,
            last_update_mono=now_mono,
        )

        assert status.source == ComponentSource.BROKER
        assert status.level == SystemLevel.HEALTHY
        assert status.last_event is None
        assert status.last_update_mono == now_mono
        assert status.consecutive_failures == 0
        assert status.unstable_since_mono is None

    def test_create_component_status_with_event(self):
        """ComponentStatus should track last event."""
        now_wall = datetime.now(tz=timezone.utc)
        now_mono = time.monotonic()

        event = SystemEvent(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
            event_time_wall=now_wall,
            event_time_mono=now_mono,
        )

        status = ComponentStatus(
            source=ComponentSource.BROKER,
            level=SystemLevel.TRIPPED,
            last_event=event,
            last_update_mono=now_mono,
            consecutive_failures=3,
            unstable_since_mono=now_mono - 60.0,
        )

        assert status.last_event == event
        assert status.consecutive_failures == 3
        assert status.unstable_since_mono == now_mono - 60.0


class TestCreateEvent:
    """Tests for create_event factory function."""

    def test_create_event_basic(self):
        """create_event should produce a valid SystemEvent."""
        before_mono = time.monotonic()

        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )

        after_mono = time.monotonic()

        assert event.event_type == EventType.FAIL_CRIT
        assert event.source == ComponentSource.BROKER
        assert event.severity == Severity.CRITICAL
        assert event.reason_code == ReasonCode.BROKER_DISCONNECT
        assert event.details is None
        assert event.ttl_seconds is None
        # Check timestamps are reasonable
        assert before_mono <= event.event_time_mono <= after_mono
        assert event.event_time_wall.tzinfo == timezone.utc

    def test_create_event_with_details(self):
        """create_event should accept optional details."""
        details = {"error": "Connection refused", "retry_count": 3}

        event = create_event(
            event_type=EventType.FAIL_SUPP,
            source=ComponentSource.MARKET_DATA,
            severity=Severity.WARNING,
            reason_code=ReasonCode.MD_STALE,
            details=details,
        )

        assert event.details == details

    def test_create_event_with_ttl(self):
        """create_event should accept optional TTL."""
        event = create_event(
            event_type=EventType.RECOVERED,
            source=ComponentSource.RISK,
            severity=Severity.INFO,
            reason_code=ReasonCode.ALL_HEALTHY,
            ttl_seconds=120,
        )

        assert event.ttl_seconds == 120

    def test_create_event_with_all_optional_fields(self):
        """create_event should accept all optional fields."""
        details = {"recovery_time_ms": 500}

        event = create_event(
            event_type=EventType.RECOVERED,
            source=ComponentSource.DB,
            severity=Severity.INFO,
            reason_code=ReasonCode.ALL_HEALTHY,
            details=details,
            ttl_seconds=60,
        )

        assert event.details == details
        assert event.ttl_seconds == 60

    def test_create_event_returns_frozen_event(self):
        """create_event should return a frozen SystemEvent."""
        event = create_event(
            event_type=EventType.HEARTBEAT,
            source=ComponentSource.SYSTEM,
            severity=Severity.INFO,
            reason_code=ReasonCode.ALL_HEALTHY,
        )

        with pytest.raises(AttributeError):
            event.severity = Severity.WARNING  # type: ignore[misc]
