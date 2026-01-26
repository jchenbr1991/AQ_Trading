"""Tests for audit checksum and chain integrity verification.

TDD: Write tests FIRST, then implement integrity.py to make them pass.
"""

from datetime import datetime, timezone
from uuid import uuid4

from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
)


def create_test_event(
    event_id=None,
    timestamp=None,
    event_type=AuditEventType.ORDER_PLACED,
    actor_id="user-123",
    resource_type=ResourceType.ORDER,
    resource_id="order-456",
    old_value=None,
    new_value=None,
) -> AuditEvent:
    """Helper to create test audit events."""
    return AuditEvent(
        event_id=event_id or uuid4(),
        timestamp=timestamp or datetime.now(tz=timezone.utc),
        event_type=event_type,
        severity=AuditSeverity.INFO,
        actor_id=actor_id,
        actor_type=ActorType.USER,
        resource_type=resource_type,
        resource_id=resource_id,
        old_value=old_value,
        new_value=new_value,
        request_id="req-789",
        source=EventSource.WEB,
        environment="production",
        service="trading-api",
        version="1.0.0",
    )


class TestComputeChecksum:
    """Tests for compute_checksum function."""

    def test_compute_checksum_returns_hex_string(self):
        """compute_checksum should return a hex digest string."""
        from src.audit.integrity import compute_checksum

        event = create_test_event()
        checksum = compute_checksum(event, sequence_id=1, prev_checksum=None)

        assert isinstance(checksum, str)
        # SHA256 hex digest is 64 characters
        assert len(checksum) == 64
        # Should be valid hex
        int(checksum, 16)

    def test_compute_checksum_deterministic(self):
        """compute_checksum should return same value for same input."""
        from src.audit.integrity import compute_checksum

        event_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        event = create_test_event(event_id=event_id, timestamp=timestamp)

        checksum1 = compute_checksum(event, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event, sequence_id=1, prev_checksum=None)

        assert checksum1 == checksum2

    def test_compute_checksum_different_with_different_sequence_id(self):
        """compute_checksum should be different with different sequence_id."""
        from src.audit.integrity import compute_checksum

        event = create_test_event()

        checksum1 = compute_checksum(event, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event, sequence_id=2, prev_checksum=None)

        assert checksum1 != checksum2

    def test_compute_checksum_different_with_different_prev_checksum(self):
        """compute_checksum should be different with different prev_checksum."""
        from src.audit.integrity import compute_checksum

        event = create_test_event()

        checksum1 = compute_checksum(event, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event, sequence_id=1, prev_checksum="abc123")

        assert checksum1 != checksum2

    def test_compute_checksum_uses_checksum_fields(self):
        """compute_checksum should include all CHECKSUM_FIELDS."""
        from src.audit.integrity import compute_checksum

        event_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Create two events differing only in event_type (a checksum field)
        event1 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            event_type=AuditEventType.ORDER_PLACED,
        )
        event2 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            event_type=AuditEventType.ORDER_FILLED,
        )

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=1, prev_checksum=None)

        assert checksum1 != checksum2

    def test_compute_checksum_with_old_value(self):
        """compute_checksum should include old_value in hash."""
        from src.audit.integrity import compute_checksum

        event_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        event1 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            old_value={"key": "value1"},
        )
        event2 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            old_value={"key": "value2"},
        )

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=1, prev_checksum=None)

        assert checksum1 != checksum2

    def test_compute_checksum_with_new_value(self):
        """compute_checksum should include new_value in hash."""
        from src.audit.integrity import compute_checksum

        event_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        event1 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            new_value={"key": "value1"},
        )
        event2 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            new_value={"key": "value2"},
        )

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=1, prev_checksum=None)

        assert checksum1 != checksum2

    def test_compute_checksum_null_values_handled(self):
        """compute_checksum should handle None values for old_value/new_value."""
        from src.audit.integrity import compute_checksum

        event = create_test_event(old_value=None, new_value=None)
        checksum = compute_checksum(event, sequence_id=1, prev_checksum=None)

        assert isinstance(checksum, str)
        assert len(checksum) == 64

    def test_compute_checksum_uses_timestamp_isoformat(self):
        """compute_checksum should use isoformat for timestamp."""
        from src.audit.integrity import compute_checksum

        event_id = uuid4()
        # Same moment but different datetime objects
        timestamp1 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        timestamp2 = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        event1 = create_test_event(event_id=event_id, timestamp=timestamp1)
        event2 = create_test_event(event_id=event_id, timestamp=timestamp2)

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=1, prev_checksum=None)

        assert checksum1 == checksum2

    def test_compute_checksum_uses_enum_value(self):
        """compute_checksum should use .value for enum fields."""
        from src.audit.integrity import compute_checksum

        event = create_test_event(event_type=AuditEventType.ORDER_PLACED)
        checksum = compute_checksum(event, sequence_id=1, prev_checksum=None)

        # Should not raise - enum should be serialized to string value
        assert isinstance(checksum, str)
        assert len(checksum) == 64

    def test_compute_checksum_dict_values_sorted_keys(self):
        """compute_checksum should use sort_keys=True for dict values."""
        from src.audit.integrity import compute_checksum

        event_id = uuid4()
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Dicts with same content but different key order
        event1 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            new_value={"a": 1, "b": 2, "c": 3},
        )
        event2 = create_test_event(
            event_id=event_id,
            timestamp=timestamp,
            new_value={"c": 3, "b": 2, "a": 1},
        )

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=1, prev_checksum=None)

        assert checksum1 == checksum2


class TestVerifyChecksum:
    """Tests for verify_checksum function."""

    def test_verify_checksum_returns_true_for_valid(self):
        """verify_checksum should return True when checksum matches."""
        from src.audit.integrity import compute_checksum, verify_checksum

        event = create_test_event()
        sequence_id = 1
        prev_checksum = None
        expected_checksum = compute_checksum(event, sequence_id, prev_checksum)

        # Create event_row dict similar to what would come from DB
        event_row = {
            "event_id": str(event.event_id),
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "actor_id": event.actor_id,
            "resource_type": event.resource_type.value,
            "resource_id": event.resource_id,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "checksum": expected_checksum,
        }

        result = verify_checksum(event_row, sequence_id, prev_checksum)
        assert result is True

    def test_verify_checksum_returns_false_for_tampered_data(self):
        """verify_checksum should return False when data has been tampered."""
        from src.audit.integrity import compute_checksum, verify_checksum

        event = create_test_event()
        sequence_id = 1
        prev_checksum = None
        original_checksum = compute_checksum(event, sequence_id, prev_checksum)

        # Create tampered event_row
        event_row = {
            "event_id": str(event.event_id),
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "actor_id": "hacker-999",  # Tampered!
            "resource_type": event.resource_type.value,
            "resource_id": event.resource_id,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "checksum": original_checksum,
        }

        result = verify_checksum(event_row, sequence_id, prev_checksum)
        assert result is False

    def test_verify_checksum_returns_false_for_wrong_checksum(self):
        """verify_checksum should return False when stored checksum is wrong."""
        from src.audit.integrity import verify_checksum

        event = create_test_event()

        event_row = {
            "event_id": str(event.event_id),
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "actor_id": event.actor_id,
            "resource_type": event.resource_type.value,
            "resource_id": event.resource_id,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "checksum": "0" * 64,  # Wrong checksum
        }

        result = verify_checksum(event_row, sequence_id=1, prev_checksum=None)
        assert result is False

    def test_verify_checksum_with_dict_values(self):
        """verify_checksum should work with dict old_value/new_value."""
        from src.audit.integrity import compute_checksum, verify_checksum

        event = create_test_event(
            old_value={"level": 10},
            new_value={"level": 20},
        )
        sequence_id = 1
        prev_checksum = None
        expected_checksum = compute_checksum(event, sequence_id, prev_checksum)

        event_row = {
            "event_id": str(event.event_id),
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "actor_id": event.actor_id,
            "resource_type": event.resource_type.value,
            "resource_id": event.resource_id,
            "old_value": {"level": 10},
            "new_value": {"level": 20},
            "checksum": expected_checksum,
        }

        result = verify_checksum(event_row, sequence_id, prev_checksum)
        assert result is True

    def test_verify_checksum_with_prev_checksum(self):
        """verify_checksum should use prev_checksum in verification."""
        from src.audit.integrity import compute_checksum, verify_checksum

        event = create_test_event()
        sequence_id = 2
        prev_checksum = "a" * 64  # Previous event's checksum
        expected_checksum = compute_checksum(event, sequence_id, prev_checksum)

        event_row = {
            "event_id": str(event.event_id),
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "actor_id": event.actor_id,
            "resource_type": event.resource_type.value,
            "resource_id": event.resource_id,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "checksum": expected_checksum,
        }

        result = verify_checksum(event_row, sequence_id, prev_checksum)
        assert result is True


class TestVerifyChain:
    """Tests for verify_chain function."""

    def test_verify_chain_empty_list_returns_valid(self):
        """verify_chain should return valid for empty list."""
        from src.audit.integrity import verify_chain

        is_valid, errors = verify_chain([])

        assert is_valid is True
        assert errors == []

    def test_verify_chain_single_event_valid(self):
        """verify_chain should validate single event with prev_checksum=None."""
        from src.audit.integrity import compute_checksum, verify_chain

        event = create_test_event()
        checksum = compute_checksum(event, sequence_id=1, prev_checksum=None)

        events = [
            {
                "sequence_id": 1,
                "event_id": str(event.event_id),
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "actor_id": event.actor_id,
                "resource_type": event.resource_type.value,
                "resource_id": event.resource_id,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "checksum": checksum,
                "prev_checksum": None,
            }
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is True
        assert errors == []

    def test_verify_chain_multiple_events_valid(self):
        """verify_chain should validate chain of events."""
        from src.audit.integrity import compute_checksum, verify_chain

        event1 = create_test_event()
        event2 = create_test_event()
        event3 = create_test_event()

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=2, prev_checksum=checksum1)
        checksum3 = compute_checksum(event3, sequence_id=3, prev_checksum=checksum2)

        events = [
            {
                "sequence_id": 1,
                "event_id": str(event1.event_id),
                "timestamp": event1.timestamp.isoformat(),
                "event_type": event1.event_type.value,
                "actor_id": event1.actor_id,
                "resource_type": event1.resource_type.value,
                "resource_id": event1.resource_id,
                "old_value": event1.old_value,
                "new_value": event1.new_value,
                "checksum": checksum1,
                "prev_checksum": None,
            },
            {
                "sequence_id": 2,
                "event_id": str(event2.event_id),
                "timestamp": event2.timestamp.isoformat(),
                "event_type": event2.event_type.value,
                "actor_id": event2.actor_id,
                "resource_type": event2.resource_type.value,
                "resource_id": event2.resource_id,
                "old_value": event2.old_value,
                "new_value": event2.new_value,
                "checksum": checksum2,
                "prev_checksum": checksum1,
            },
            {
                "sequence_id": 3,
                "event_id": str(event3.event_id),
                "timestamp": event3.timestamp.isoformat(),
                "event_type": event3.event_type.value,
                "actor_id": event3.actor_id,
                "resource_type": event3.resource_type.value,
                "resource_id": event3.resource_id,
                "old_value": event3.old_value,
                "new_value": event3.new_value,
                "checksum": checksum3,
                "prev_checksum": checksum2,
            },
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is True
        assert errors == []

    def test_verify_chain_detects_non_monotonic_sequence(self):
        """verify_chain should detect non-monotonic sequence_id."""
        from src.audit.integrity import compute_checksum, verify_chain

        event1 = create_test_event()
        event2 = create_test_event()

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=1, prev_checksum=checksum1)

        events = [
            {
                "sequence_id": 1,
                "event_id": str(event1.event_id),
                "timestamp": event1.timestamp.isoformat(),
                "event_type": event1.event_type.value,
                "actor_id": event1.actor_id,
                "resource_type": event1.resource_type.value,
                "resource_id": event1.resource_id,
                "old_value": event1.old_value,
                "new_value": event1.new_value,
                "checksum": checksum1,
                "prev_checksum": None,
            },
            {
                "sequence_id": 1,  # Not monotonically increasing!
                "event_id": str(event2.event_id),
                "timestamp": event2.timestamp.isoformat(),
                "event_type": event2.event_type.value,
                "actor_id": event2.actor_id,
                "resource_type": event2.resource_type.value,
                "resource_id": event2.resource_id,
                "old_value": event2.old_value,
                "new_value": event2.new_value,
                "checksum": checksum2,
                "prev_checksum": checksum1,
            },
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is False
        assert len(errors) >= 1
        assert any("sequence" in err.lower() for err in errors)

    def test_verify_chain_detects_broken_chain(self):
        """verify_chain should detect when prev_checksum doesn't match."""
        from src.audit.integrity import compute_checksum, verify_chain

        event1 = create_test_event()
        event2 = create_test_event()

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=2, prev_checksum=checksum1)

        events = [
            {
                "sequence_id": 1,
                "event_id": str(event1.event_id),
                "timestamp": event1.timestamp.isoformat(),
                "event_type": event1.event_type.value,
                "actor_id": event1.actor_id,
                "resource_type": event1.resource_type.value,
                "resource_id": event1.resource_id,
                "old_value": event1.old_value,
                "new_value": event1.new_value,
                "checksum": checksum1,
                "prev_checksum": None,
            },
            {
                "sequence_id": 2,
                "event_id": str(event2.event_id),
                "timestamp": event2.timestamp.isoformat(),
                "event_type": event2.event_type.value,
                "actor_id": event2.actor_id,
                "resource_type": event2.resource_type.value,
                "resource_id": event2.resource_id,
                "old_value": event2.old_value,
                "new_value": event2.new_value,
                "checksum": checksum2,
                "prev_checksum": "wrong_checksum",  # Broken chain!
            },
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is False
        assert len(errors) >= 1
        assert any("prev_checksum" in err.lower() or "chain" in err.lower() for err in errors)

    def test_verify_chain_detects_tampered_checksum(self):
        """verify_chain should detect when stored checksum is wrong."""
        from src.audit.integrity import compute_checksum, verify_chain

        event1 = create_test_event()
        event2 = create_test_event()

        checksum1 = compute_checksum(event1, sequence_id=1, prev_checksum=None)
        checksum2 = compute_checksum(event2, sequence_id=2, prev_checksum=checksum1)

        events = [
            {
                "sequence_id": 1,
                "event_id": str(event1.event_id),
                "timestamp": event1.timestamp.isoformat(),
                "event_type": event1.event_type.value,
                "actor_id": event1.actor_id,
                "resource_type": event1.resource_type.value,
                "resource_id": event1.resource_id,
                "old_value": event1.old_value,
                "new_value": event1.new_value,
                "checksum": "tampered_checksum",  # Tampered!
                "prev_checksum": None,
            },
            {
                "sequence_id": 2,
                "event_id": str(event2.event_id),
                "timestamp": event2.timestamp.isoformat(),
                "event_type": event2.event_type.value,
                "actor_id": event2.actor_id,
                "resource_type": event2.resource_type.value,
                "resource_id": event2.resource_id,
                "old_value": event2.old_value,
                "new_value": event2.new_value,
                "checksum": checksum2,
                "prev_checksum": checksum1,
            },
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is False
        assert len(errors) >= 1

    def test_verify_chain_first_event_must_have_null_prev_checksum(self):
        """verify_chain should require first event to have prev_checksum=None."""
        from src.audit.integrity import compute_checksum, verify_chain

        event = create_test_event()
        # Compute with wrong prev_checksum
        checksum = compute_checksum(event, sequence_id=1, prev_checksum="some_value")

        events = [
            {
                "sequence_id": 1,
                "event_id": str(event.event_id),
                "timestamp": event.timestamp.isoformat(),
                "event_type": event.event_type.value,
                "actor_id": event.actor_id,
                "resource_type": event.resource_type.value,
                "resource_id": event.resource_id,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "checksum": checksum,
                "prev_checksum": "some_value",  # Should be None!
            }
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is False
        assert len(errors) >= 1
        assert any("first" in err.lower() or "prev_checksum" in err.lower() for err in errors)

    def test_verify_chain_returns_all_errors(self):
        """verify_chain should return all detected errors, not just first."""
        from src.audit.integrity import verify_chain

        # Create chain with multiple errors
        events = [
            {
                "sequence_id": 1,
                "event_id": "event-1",
                "timestamp": "2024-01-15T10:00:00+00:00",
                "event_type": "order_placed",
                "actor_id": "user-1",
                "resource_type": "order",
                "resource_id": "order-1",
                "old_value": None,
                "new_value": None,
                "checksum": "wrong1",
                "prev_checksum": "not_none",  # Error 1: should be None
            },
            {
                "sequence_id": 1,  # Error 2: non-monotonic
                "event_id": "event-2",
                "timestamp": "2024-01-15T10:01:00+00:00",
                "event_type": "order_placed",
                "actor_id": "user-1",
                "resource_type": "order",
                "resource_id": "order-2",
                "old_value": None,
                "new_value": None,
                "checksum": "wrong2",
                "prev_checksum": "wrong_chain",  # Error 3: broken chain
            },
        ]

        is_valid, errors = verify_chain(events)

        assert is_valid is False
        # Should have multiple errors
        assert len(errors) >= 2
