"""Tests for alert factory module."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from src.alerts.factory import (
    COOLDOWN_WINDOW_MINUTES,
    compute_dedupe_key,
    create_alert,
    validate_alert,
)
from src.alerts.models import (
    RECOVERY_TYPES,
    AlertEvent,
    AlertType,
    Severity,
)


class TestCooldownConstant:
    """Tests for COOLDOWN_WINDOW_MINUTES constant."""

    def test_cooldown_window_value(self):
        """COOLDOWN_WINDOW_MINUTES should be 10."""
        assert COOLDOWN_WINDOW_MINUTES == 10


class TestCreateAlert:
    """Tests for create_alert function."""

    def test_create_alert_minimal(self):
        """Create alert with only required fields."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )

        assert isinstance(alert, AlertEvent)
        assert isinstance(alert.alert_id, UUID)
        assert alert.type == AlertType.ORDER_REJECTED
        assert alert.severity == Severity.SEV2
        assert alert.summary == "Order rejected"
        assert alert.event_timestamp.tzinfo == timezone.utc
        assert alert.entity_ref is None
        assert alert.details == {}

    def test_create_alert_with_provided_uuid(self):
        """Alert should use provided UUID."""
        my_id = uuid4()
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
            alert_id=my_id,
        )
        assert alert.alert_id == my_id

    def test_create_alert_generates_uuid_if_not_provided(self):
        """Alert should generate UUID if not provided."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
        )
        assert isinstance(alert.alert_id, UUID)

    def test_create_alert_with_utc_timestamp(self):
        """Alert should preserve UTC timestamp."""
        ts = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
            timestamp=ts,
        )
        assert alert.event_timestamp == ts
        assert alert.event_timestamp.tzinfo == timezone.utc

    def test_create_alert_with_none_timestamp_uses_now(self):
        """Alert should use now() if timestamp is None."""
        before = datetime.now(tz=timezone.utc)
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
        )
        after = datetime.now(tz=timezone.utc)
        assert before <= alert.event_timestamp <= after
        assert alert.event_timestamp.tzinfo == timezone.utc

    def test_create_alert_naive_timestamp_assumes_utc(self):
        """Naive timestamp should be assumed UTC."""
        naive_ts = datetime(2026, 1, 25, 12, 0, 0)  # No tzinfo
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
            timestamp=naive_ts,
        )
        assert alert.event_timestamp.tzinfo == timezone.utc
        assert alert.event_timestamp.year == 2026
        assert alert.event_timestamp.month == 1
        assert alert.event_timestamp.day == 25
        assert alert.event_timestamp.hour == 12

    def test_create_alert_converts_non_utc_to_utc(self):
        """Non-UTC timestamp should be converted to UTC."""
        # Create a timestamp in US Eastern (UTC-5)
        eastern = timezone(timedelta(hours=-5))
        eastern_ts = datetime(2026, 1, 25, 12, 0, 0, tzinfo=eastern)

        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
            timestamp=eastern_ts,
        )

        # Should be converted to UTC (12:00 EST = 17:00 UTC)
        assert alert.event_timestamp.tzinfo == timezone.utc
        assert alert.event_timestamp.hour == 17

    def test_create_alert_builds_entity_ref_from_fields(self):
        """Entity fields should be used to build EntityRef."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            account_id="acc123",
            symbol="AAPL",
            strategy_id="strat456",
            run_id="run789",
        )

        assert alert.entity_ref is not None
        assert alert.entity_ref.account_id == "acc123"
        assert alert.entity_ref.symbol == "AAPL"
        assert alert.entity_ref.strategy_id == "strat456"
        assert alert.entity_ref.run_id == "run789"

    def test_create_alert_partial_entity_ref(self):
        """Partial entity fields should still create EntityRef."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            symbol="TSLA",
        )

        assert alert.entity_ref is not None
        assert alert.entity_ref.symbol == "TSLA"
        assert alert.entity_ref.account_id is None
        assert alert.entity_ref.strategy_id is None
        assert alert.entity_ref.run_id is None

    def test_create_alert_no_entity_ref_if_all_none(self):
        """EntityRef should be None if no entity fields provided."""
        alert = create_alert(
            type=AlertType.DB_WRITE_FAIL,
            severity=Severity.SEV1,
            summary="Database write failed",
        )
        assert alert.entity_ref is None

    def test_create_alert_fingerprint_format(self):
        """Fingerprint should be type:account_id:symbol:strategy_id."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            account_id="acc123",
            symbol="AAPL",
            strategy_id="strat456",
        )
        assert alert.fingerprint == "order_rejected:acc123:AAPL:strat456"

    def test_create_alert_fingerprint_with_empty_fields(self):
        """Fingerprint should use empty strings for missing fields."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            symbol="AAPL",
        )
        assert alert.fingerprint == "order_rejected::AAPL:"

    def test_create_alert_fingerprint_all_empty(self):
        """Fingerprint with no entity fields should have empty segments."""
        alert = create_alert(
            type=AlertType.DB_WRITE_FAIL,
            severity=Severity.SEV1,
            summary="Database write failed",
        )
        assert alert.fingerprint == "db_write_fail:::"

    def test_create_alert_sanitizes_details(self):
        """Details should be sanitized using sanitize_details."""
        from decimal import Decimal

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            details={
                "price": Decimal("123.45"),
                "timestamp": datetime(2026, 1, 25, tzinfo=timezone.utc),
            },
        )
        # Decimal should be converted to string
        assert alert.details["price"] == "123.45"
        # Datetime should be converted to ISO string
        assert isinstance(alert.details["timestamp"], str)

    def test_create_alert_truncates_long_summary(self):
        """Summary longer than 255 chars should be truncated with '...'."""
        long_summary = "x" * 300
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary=long_summary,
        )
        assert len(alert.summary) == 255
        assert alert.summary.endswith("...")

    def test_create_alert_preserves_short_summary(self):
        """Summary under 255 chars should not be truncated."""
        short_summary = "Order rejected due to insufficient funds"
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary=short_summary,
        )
        assert alert.summary == short_summary

    def test_create_alert_summary_exactly_255_chars(self):
        """Summary exactly 255 chars should not be truncated."""
        exact_summary = "x" * 255
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary=exact_summary,
        )
        assert alert.summary == exact_summary
        assert len(alert.summary) == 255

    def test_create_alert_with_none_details(self):
        """None details should result in empty dict."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            details=None,
        )
        assert alert.details == {}


class TestComputeDedupeKey:
    """Tests for compute_dedupe_key function."""

    def test_normal_event_dedupe_key_format(self):
        """Normal events should have fingerprint:bucket format."""
        ts = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            timestamp=ts,
            account_id="acc123",
            symbol="AAPL",
            strategy_id="strat456",
        )

        key = compute_dedupe_key(alert)

        # Expected: fingerprint:bucket where bucket = timestamp // (10*60)
        expected_bucket = int(ts.timestamp()) // (10 * 60)
        expected_key = f"order_rejected:acc123:AAPL:strat456:{expected_bucket}"
        assert key == expected_key

    def test_recovery_event_dedupe_key_format(self):
        """Recovery events should have fingerprint:recovery:alert_id format."""
        my_id = uuid4()
        alert = create_alert(
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV3,
            summary="Component recovered",
            alert_id=my_id,
            account_id="acc123",
        )

        key = compute_dedupe_key(alert)
        # fingerprint = component_recovered:acc123:: (empty symbol and strategy)
        # key = fingerprint:recovery:alert_id
        expected_key = f"component_recovered:acc123:::recovery:{my_id}"
        assert key == expected_key

    def test_dedupe_key_same_bucket(self):
        """Alerts in same 10-minute bucket should have same dedupe key."""
        ts1 = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 25, 12, 5, 0, tzinfo=timezone.utc)  # 5 minutes later

        alert1 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            timestamp=ts1,
            symbol="AAPL",
        )
        alert2 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected again",
            timestamp=ts2,
            symbol="AAPL",
        )

        assert compute_dedupe_key(alert1) == compute_dedupe_key(alert2)

    def test_dedupe_key_different_bucket(self):
        """Alerts in different 10-minute buckets should have different dedupe keys."""
        ts1 = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 25, 12, 15, 0, tzinfo=timezone.utc)  # 15 minutes later

        alert1 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            timestamp=ts1,
            symbol="AAPL",
        )
        alert2 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected again",
            timestamp=ts2,
            symbol="AAPL",
        )

        assert compute_dedupe_key(alert1) != compute_dedupe_key(alert2)

    def test_recovery_types_use_recovery_format(self):
        """All RECOVERY_TYPES should use recovery dedupe key format."""
        for alert_type in RECOVERY_TYPES:
            my_id = uuid4()
            alert = create_alert(
                type=alert_type,
                severity=Severity.SEV3,
                summary="Recovered",
                alert_id=my_id,
            )
            key = compute_dedupe_key(alert)
            assert ":recovery:" in key or f":{my_id}" in key


class TestValidateAlert:
    """Tests for validate_alert function."""

    def test_validate_alert_valid(self):
        """Valid alert should not raise."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )
        # Should not raise
        validate_alert(alert)

    def test_validate_alert_raises_if_no_tzinfo(self):
        """Should raise ValueError if timestamp has no tzinfo."""
        # Create an alert with naive timestamp by manually constructing it
        alert = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            event_timestamp=datetime(2026, 1, 25, 12, 0, 0),  # naive
            fingerprint="test",
            entity_ref=None,
            summary="Order rejected",
            details={},
        )

        with pytest.raises(ValueError, match="tzinfo"):
            validate_alert(alert)

    def test_validate_alert_raises_if_not_utc(self):
        """Should raise ValueError if timestamp is not UTC."""
        eastern = timezone(timedelta(hours=-5))
        alert = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            event_timestamp=datetime(2026, 1, 25, 12, 0, 0, tzinfo=eastern),  # not UTC
            fingerprint="test",
            entity_ref=None,
            summary="Order rejected",
            details={},
        )

        with pytest.raises(ValueError, match="UTC"):
            validate_alert(alert)

    def test_validate_alert_raises_if_summary_too_long(self):
        """Should raise ValueError if summary exceeds 255 chars."""
        alert = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            event_timestamp=datetime.now(tz=timezone.utc),
            fingerprint="test",
            entity_ref=None,
            summary="x" * 256,  # too long
            details={},
        )

        with pytest.raises(ValueError, match="255"):
            validate_alert(alert)

    def test_validate_alert_summary_exactly_255(self):
        """Summary exactly 255 chars should be valid."""
        alert = AlertEvent(
            alert_id=uuid4(),
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            event_timestamp=datetime.now(tz=timezone.utc),
            fingerprint="test",
            entity_ref=None,
            summary="x" * 255,  # exactly at limit
            details={},
        )
        # Should not raise
        validate_alert(alert)
