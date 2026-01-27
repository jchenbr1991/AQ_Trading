"""Tests for OPTION_EXPIRING fingerprint and dedupe key generation."""

import pytest
from src.alerts.factory import compute_dedupe_key, create_alert
from src.alerts.models import AlertType, Severity


def test_option_expiring_fingerprint_uses_position_id():
    """Fingerprint should use position_id from details, not symbol."""
    alert = create_alert(
        type=AlertType.OPTION_EXPIRING,
        severity=Severity.SEV1,
        summary="Test option expiring",
        account_id="acc123",
        symbol="AAPL240119C150",  # This should NOT be in fingerprint
        details={
            "position_id": 456,
            "threshold_days": 7,
            "expiry_date": "2024-01-19",
            "days_to_expiry": 7,
            "strike": 150.0,
            "put_call": "call",
        },
    )

    # Fingerprint should be: option_expiring:acc123:456
    # NOT: option_expiring:acc123:AAPL240119C150::
    assert "456" in alert.fingerprint
    assert "AAPL240119C150" not in alert.fingerprint


def test_option_expiring_dedupe_key_is_permanent():
    """Dedupe key should include threshold and 'permanent' suffix."""
    alert = create_alert(
        type=AlertType.OPTION_EXPIRING,
        severity=Severity.SEV1,
        summary="Test option expiring",
        account_id="acc123",
        symbol="AAPL240119C150",
        details={
            "position_id": 456,
            "threshold_days": 7,
            "expiry_date": "2024-01-19",
            "days_to_expiry": 7,
            "strike": 150.0,
            "put_call": "call",
        },
    )

    dedupe_key = compute_dedupe_key(alert)

    # Should contain threshold and permanent marker
    assert "threshold_7" in dedupe_key
    assert "permanent" in dedupe_key
    # Should NOT contain time bucket
    assert dedupe_key.count(":") >= 3  # Multiple colons in permanent format


def test_option_expiring_raises_without_position_id():
    """Should raise ValueError if position_id is missing."""
    with pytest.raises(ValueError, match="position_id"):
        create_alert(
            type=AlertType.OPTION_EXPIRING,
            severity=Severity.SEV1,
            summary="Test option expiring",
            account_id="acc123",
            details={
                "threshold_days": 7,
                # position_id is missing!
            },
        )


def test_option_expiring_dedupe_key_raises_without_threshold():
    """compute_dedupe_key should raise if threshold_days is missing."""
    # Create alert without going through factory validation
    from datetime import datetime, timezone
    from uuid import uuid4

    from src.alerts.models import AlertEvent

    alert = AlertEvent(
        alert_id=uuid4(),
        type=AlertType.OPTION_EXPIRING,
        severity=Severity.SEV1,
        event_timestamp=datetime.now(timezone.utc),
        fingerprint="option_expiring:acc123:456",
        entity_ref=None,
        summary="Test",
        details={"position_id": 456},  # No threshold_days
    )

    with pytest.raises(ValueError, match="threshold_days"):
        compute_dedupe_key(alert)


def test_other_alert_types_unchanged():
    """Other alert types should still use original fingerprint logic."""
    alert = create_alert(
        type=AlertType.ORDER_REJECTED,
        severity=Severity.SEV2,
        summary="Order rejected",
        account_id="acc123",
        symbol="AAPL",
    )

    # Should use symbol in fingerprint
    assert "AAPL" in alert.fingerprint

    dedupe_key = compute_dedupe_key(alert)
    # Should NOT contain 'permanent'
    assert "permanent" not in dedupe_key
