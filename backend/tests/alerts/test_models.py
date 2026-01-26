"""Tests for alert models."""

import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from src.alerts.models import (
    MAX_DETAILS_BYTES,
    MAX_KEYS,
    MAX_STRING_VALUE_LENGTH,
    RECOVERY_TYPES,
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    Severity,
    sanitize_details,
    to_json_safe,
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


class TestConstants:
    """Tests for serialization constants."""

    def test_max_details_bytes(self):
        assert MAX_DETAILS_BYTES == 8192

    def test_max_string_value_length(self):
        assert MAX_STRING_VALUE_LENGTH == 512

    def test_max_keys(self):
        assert MAX_KEYS == 20


class TestToJsonSafe:
    """Tests for to_json_safe function."""

    def test_string_passthrough(self):
        """Strings should pass through unchanged."""
        assert to_json_safe("hello") == "hello"
        assert to_json_safe("") == ""

    def test_int_passthrough(self):
        """Integers should pass through unchanged."""
        assert to_json_safe(42) == 42
        assert to_json_safe(0) == 0
        assert to_json_safe(-100) == -100

    def test_float_passthrough(self):
        """Floats should pass through unchanged."""
        assert to_json_safe(3.14) == 3.14
        assert to_json_safe(0.0) == 0.0
        assert to_json_safe(-2.5) == -2.5

    def test_bool_passthrough(self):
        """Booleans should pass through unchanged."""
        assert to_json_safe(True) is True
        assert to_json_safe(False) is False

    def test_none_passthrough(self):
        """None should pass through unchanged."""
        assert to_json_safe(None) is None

    def test_decimal_to_string(self):
        """Decimal should be converted to string."""
        result = to_json_safe(Decimal("123.45"))
        assert result == "123.45"
        assert isinstance(result, str)

    def test_decimal_preserves_precision(self):
        """Decimal conversion should preserve precision."""
        assert to_json_safe(Decimal("0.00001")) == "0.00001"
        assert to_json_safe(Decimal("1000000.99")) == "1000000.99"

    def test_datetime_to_iso8601(self):
        """Datetime should be converted to ISO 8601 string."""
        dt = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        result = to_json_safe(dt)
        assert result == "2026-01-25T12:00:00+00:00"
        assert isinstance(result, str)

    def test_datetime_with_microseconds(self):
        """Datetime with microseconds should preserve them."""
        dt = datetime(2026, 1, 25, 12, 30, 45, 123456, tzinfo=timezone.utc)
        result = to_json_safe(dt)
        assert "2026-01-25T12:30:45.123456" in result

    def test_uuid_to_string(self):
        """UUID should be converted to string."""
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        result = to_json_safe(test_uuid)
        assert result == "12345678-1234-5678-1234-567812345678"
        assert isinstance(result, str)

    def test_exception_to_string(self):
        """Exception should be converted to 'TypeName: message' format."""
        exc = ValueError("test error")
        result = to_json_safe(exc)
        assert result == "ValueError: test error"
        assert isinstance(result, str)

    def test_exception_with_empty_message(self):
        """Exception with empty message should still format correctly."""
        exc = ValueError()
        result = to_json_safe(exc)
        assert result == "ValueError: "

    def test_custom_exception(self):
        """Custom exceptions should use their class name."""

        class CustomError(Exception):
            pass

        exc = CustomError("custom message")
        result = to_json_safe(exc)
        assert result == "CustomError: custom message"

    def test_unknown_type_uses_str(self):
        """Unknown types should be converted using str()."""

        class CustomObject:
            def __str__(self):
                return "custom_repr"

        result = to_json_safe(CustomObject())
        assert result == "custom_repr"
        assert isinstance(result, str)

    def test_list_uses_str(self):
        """Lists should be converted to string representation."""
        result = to_json_safe([1, 2, 3])
        assert result == "[1, 2, 3]"

    def test_dict_uses_str(self):
        """Dicts should be converted to string representation."""
        result = to_json_safe({"a": 1})
        assert isinstance(result, str)


class TestSanitizeDetails:
    """Tests for sanitize_details function."""

    def test_small_dict_passthrough(self):
        """Small dict with valid values should pass through with conversion."""
        details = {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }
        result = sanitize_details(details)
        assert result == {
            "string": "hello",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
        }

    def test_converts_decimal(self):
        """Decimal values should be converted to strings."""
        details = {"price": Decimal("123.45")}
        result = sanitize_details(details)
        assert result == {"price": "123.45"}

    def test_converts_datetime(self):
        """Datetime values should be converted to ISO strings."""
        dt = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        details = {"timestamp": dt}
        result = sanitize_details(details)
        assert result == {"timestamp": "2026-01-25T12:00:00+00:00"}

    def test_converts_uuid(self):
        """UUID values should be converted to strings."""
        test_uuid = UUID("12345678-1234-5678-1234-567812345678")
        details = {"id": test_uuid}
        result = sanitize_details(details)
        assert result == {"id": "12345678-1234-5678-1234-567812345678"}

    def test_converts_exception(self):
        """Exception values should be converted to strings."""
        details = {"error": ValueError("test error")}
        result = sanitize_details(details)
        assert result == {"error": "ValueError: test error"}

    def test_truncates_large_dict_by_keys(self):
        """Dict with many keys should be truncated to MAX_KEYS when exceeding size."""
        # Create a dict with 100 keys and longer values to exceed 8192 bytes
        details = {f"key_{i:04d}": f"value_{i}" * 20 for i in range(100)}
        result = sanitize_details(details)

        # Should have MAX_KEYS + 1 (for _truncated)
        assert len(result) == MAX_KEYS + 1
        assert result["_truncated"] is True

    def test_truncates_long_string_values(self):
        """Long string values should be truncated."""
        # Create a dict with very long string values that exceeds size
        long_value = "x" * 2000
        details = {f"key_{i}": long_value for i in range(10)}
        result = sanitize_details(details)

        # Values should be truncated
        for key, value in result.items():
            if key.startswith("key_") and isinstance(value, str):
                assert len(value) <= MAX_STRING_VALUE_LENGTH + len("...[truncated]")
                if len(long_value) > MAX_STRING_VALUE_LENGTH:
                    assert value.endswith("...[truncated]")

    def test_string_truncation_format(self):
        """Truncated strings should end with ...[truncated]."""
        # Create content that exceeds max size but won't trigger fallback
        # After key truncation, string truncation should kick in
        long_value = "a" * 1000
        details = {f"key_{i}": long_value for i in range(5)}
        # Use a max_size that's small enough to trigger string truncation
        # but large enough to not hit the final fallback
        result = sanitize_details(details, max_size=4000)

        # Check at least some values were truncated
        truncated_values = [
            v for v in result.values() if isinstance(v, str) and v.endswith("...[truncated]")
        ]
        assert len(truncated_values) > 0

    def test_fallback_for_extremely_large(self):
        """Extremely large dicts should return fallback error dict."""
        # Create something that's still too large after all truncation
        # This is a bit contrived but tests the fallback
        huge_details = {f"key_{i:05d}": "x" * 1000 for i in range(1000)}
        result = sanitize_details(huge_details, max_size=100)

        assert result == {"_truncated": True, "_error": "details too large"}

    def test_result_is_json_serializable(self):
        """Result should always be JSON serializable."""
        details = {
            "decimal": Decimal("123.45"),
            "datetime": datetime.now(tz=timezone.utc),
            "uuid": uuid4(),
            "error": ValueError("test"),
            "nested": {"a": 1},  # Will be stringified
        }
        result = sanitize_details(details)
        # Should not raise
        json.dumps(result)

    def test_empty_dict(self):
        """Empty dict should return empty dict."""
        result = sanitize_details({})
        assert result == {}

    def test_custom_max_size(self):
        """Custom max_size should be respected."""
        details = {"key": "value" * 100}
        result = sanitize_details(details, max_size=50)
        # Should trigger truncation due to small max_size
        assert "_truncated" in result or len(json.dumps(result).encode()) <= 50
