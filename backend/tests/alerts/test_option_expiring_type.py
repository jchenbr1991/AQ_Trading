"""Tests for OPTION_EXPIRING alert type."""

from src.alerts.models import AlertType


def test_option_expiring_alert_type_exists():
    """OPTION_EXPIRING should be a valid AlertType."""
    assert hasattr(AlertType, "OPTION_EXPIRING")
    assert AlertType.OPTION_EXPIRING.value == "option_expiring"


def test_option_expiring_is_not_recovery_type():
    """OPTION_EXPIRING should not be in RECOVERY_TYPES."""
    from src.alerts.models import RECOVERY_TYPES

    assert AlertType.OPTION_EXPIRING not in RECOVERY_TYPES
