"""Tests for alert models."""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from src.alerts.models import (
    RECOVERY_TYPES,
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    Severity,
)


class TestAlertType:
    """Tests for AlertType enum."""

    # Trading alerts
    def test_order_rejected_value(self):
        assert AlertType.ORDER_REJECTED.value == "order_rejected"

    def test_order_filled_value(self):
        assert AlertType.ORDER_FILLED.value == "order_filled"

    def test_position_limit_hit_value(self):
        assert AlertType.POSITION_LIMIT_HIT.value == "position_limit_hit"

    def test_daily_loss_limit_value(self):
        assert AlertType.DAILY_LOSS_LIMIT.value == "daily_loss_limit"

    def test_kill_switch_activated_value(self):
        assert AlertType.KILL_SWITCH_ACTIVATED.value == "kill_switch_activated"

    # System alerts
    def test_component_unhealthy_value(self):
        assert AlertType.COMPONENT_UNHEALTHY.value == "component_unhealthy"

    def test_component_recovered_value(self):
        assert AlertType.COMPONENT_RECOVERED.value == "component_recovered"

    def test_db_write_fail_value(self):
        assert AlertType.DB_WRITE_FAIL.value == "db_write_fail"

    def test_storage_threshold_value(self):
        assert AlertType.STORAGE_THRESHOLD.value == "storage_threshold"

    def test_alert_delivery_failed_value(self):
        assert AlertType.ALERT_DELIVERY_FAILED.value == "alert_delivery_failed"

    def test_is_string_enum(self):
        """AlertType should be a string enum for JSON serialization."""
        assert isinstance(AlertType.ORDER_REJECTED, str)
        assert AlertType.ORDER_REJECTED == "order_rejected"


class TestSeverity:
    """Tests for Severity enum."""

    def test_sev1_value(self):
        assert Severity.SEV1.value == 1

    def test_sev2_value(self):
        assert Severity.SEV2.value == 2

    def test_sev3_value(self):
        assert Severity.SEV3.value == 3

    def test_is_int_enum(self):
        """Severity should be an int enum for comparison."""
        assert isinstance(Severity.SEV1.value, int)

    def test_severity_ordering(self):
        """Lower severity number is more critical."""
        assert Severity.SEV1.value < Severity.SEV2.value < Severity.SEV3.value


class TestRecoveryTypes:
    """Tests for RECOVERY_TYPES constant."""

    def test_contains_component_recovered(self):
        assert AlertType.COMPONENT_RECOVERED in RECOVERY_TYPES

    def test_is_frozenset(self):
        assert isinstance(RECOVERY_TYPES, frozenset)

    def test_only_contains_recovery_alerts(self):
        """Only recovery-type alerts should be in the set."""
        assert len(RECOVERY_TYPES) == 1


class TestJsonScalar:
    """Tests for JsonScalar type alias."""

    def test_type_alias_exists(self):
        """JsonScalar should be a type alias that can be used in annotations."""
        # This just verifies the import works
        value: JsonScalar = "test"
        assert value == "test"

        value = 42
        assert value == 42

        value = 3.14
        assert value == 3.14

        value = True
        assert value is True

        value = None
        assert value is None


class TestEntityRef:
    """Tests for EntityRef dataclass."""

    def test_create_with_all_fields(self):
        ref = EntityRef(
            account_id="acc123",
            symbol="AAPL",
            strategy_id="strat456",
            run_id="run789",
        )
        assert ref.account_id == "acc123"
        assert ref.symbol == "AAPL"
        assert ref.strategy_id == "strat456"
        assert ref.run_id == "run789"

    def test_create_with_defaults(self):
        """All fields should default to None."""
        ref = EntityRef()
        assert ref.account_id is None
        assert ref.symbol is None
        assert ref.strategy_id is None
        assert ref.run_id is None

    def test_partial_fields(self):
        ref = EntityRef(symbol="TSLA")
        assert ref.symbol == "TSLA"
        assert ref.account_id is None
        assert ref.strategy_id is None
        assert ref.run_id is None

    def test_is_frozen(self):
        """EntityRef should be immutable."""
        ref = EntityRef(symbol="AAPL")
        with pytest.raises(FrozenInstanceError):
            ref.symbol = "TSLA"


class TestAlertEvent:
    """Tests for AlertEvent dataclass."""

    def test_create_alert_event(self):
        alert_id = uuid4()
        timestamp = datetime.now(tz=timezone.utc)
        entity = EntityRef(symbol="AAPL", account_id="acc123")

        event = AlertEvent(
            alert_id=alert_id,
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            event_timestamp=timestamp,
            fingerprint="order_rejected:AAPL:acc123",
            entity_ref=entity,
            summary="Order rejected: insufficient buying power",
            details={"reason": "insufficient_funds", "order_id": 12345},
        )

        assert event.alert_id == alert_id
        assert event.type == AlertType.ORDER_REJECTED
        assert event.severity == Severity.SEV2
        assert event.event_timestamp == timestamp
        assert event.fingerprint == "order_rejected:AAPL:acc123"
        assert event.entity_ref == entity
        assert event.summary == "Order rejected: insufficient buying power"
        assert event.details == {"reason": "insufficient_funds", "order_id": 12345}

    def test_create_without_entity_ref(self):
        """entity_ref can be None for system-wide alerts."""
        event = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.DB_WRITE_FAIL,
            severity=Severity.SEV1,
            event_timestamp=datetime.now(tz=timezone.utc),
            fingerprint="db_write_fail:alerts_table",
            entity_ref=None,
            summary="Failed to write to alerts table",
            details={"table": "alerts", "error": "connection timeout"},
        )
        assert event.entity_ref is None

    def test_empty_details(self):
        """details can be an empty dict."""
        event = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV3,
            event_timestamp=datetime.now(tz=timezone.utc),
            fingerprint="component_recovered:redis",
            entity_ref=None,
            summary="Redis recovered",
            details={},
        )
        assert event.details == {}

    def test_is_frozen(self):
        """AlertEvent should be immutable."""
        event = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            event_timestamp=datetime.now(tz=timezone.utc),
            fingerprint="order_filled:AAPL",
            entity_ref=None,
            summary="Order filled",
            details={},
        )
        with pytest.raises(FrozenInstanceError):
            event.summary = "Modified"

    def test_alert_id_is_uuid(self):
        """alert_id should be a UUID type."""
        alert_id = uuid4()
        event = AlertEvent(
            alert_id=alert_id,
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            event_timestamp=datetime.now(tz=timezone.utc),
            fingerprint="test",
            entity_ref=None,
            summary="Test",
            details={},
        )
        assert isinstance(event.alert_id, UUID)
