"""Tests for expiration threshold configuration."""

from src.alerts.models import Severity


def test_threshold_dataclass():
    """ExpirationThreshold should be a proper dataclass."""
    from src.options.thresholds import ExpirationThreshold

    t = ExpirationThreshold(days=7, severity=Severity.SEV3)
    assert t.days == 7
    assert t.severity == Severity.SEV3


def test_expiration_thresholds_list():
    """EXPIRATION_THRESHOLDS should have 4 entries (0/1/3/7 days)."""
    from src.options.thresholds import EXPIRATION_THRESHOLDS

    assert len(EXPIRATION_THRESHOLDS) == 4

    # Should be sorted ascending by days
    days = [t.days for t in EXPIRATION_THRESHOLDS]
    assert days == [0, 1, 3, 7]


def test_max_threshold_days():
    """MAX_THRESHOLD_DAYS should be 7."""
    from src.options.thresholds import MAX_THRESHOLD_DAYS

    assert MAX_THRESHOLD_DAYS == 7


def test_get_applicable_thresholds_dte_10():
    """DTE=10 should return empty list (out of scope)."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(10)
    assert result == []


def test_get_applicable_thresholds_dte_6():
    """DTE=6 should return [7-day threshold]."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(6)
    assert len(result) == 1
    assert result[0].days == 7


def test_get_applicable_thresholds_dte_2():
    """DTE=2 should return [3-day, 7-day thresholds]."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(2)
    assert len(result) == 2
    days = [t.days for t in result]
    assert 3 in days
    assert 7 in days


def test_get_applicable_thresholds_dte_1():
    """DTE=1 should return [1-day, 3-day, 7-day thresholds]."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(1)
    assert len(result) == 3
    days = [t.days for t in result]
    assert days == [1, 3, 7]


def test_get_applicable_thresholds_dte_0():
    """DTE=0 should return all 4 thresholds."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(0)
    assert len(result) == 4
    days = [t.days for t in result]
    assert days == [0, 1, 3, 7]


def test_severity_mapping():
    """Check severity levels are correct."""
    from src.options.thresholds import EXPIRATION_THRESHOLDS

    severity_map = {t.days: t.severity for t in EXPIRATION_THRESHOLDS}

    assert severity_map[0] == Severity.SEV1  # Critical (today)
    assert severity_map[1] == Severity.SEV1  # Critical (tomorrow)
    assert severity_map[3] == Severity.SEV2  # Warning
    assert severity_map[7] == Severity.SEV3  # Info
