"""Tests for alert deduplication strategy configuration."""


def test_dedupe_strategy_enum_exists():
    """DedupeStrategy enum should exist with expected values."""
    from src.alerts.config import DedupeStrategy

    assert DedupeStrategy.WINDOWED_10M.value == "windowed_10m"
    assert DedupeStrategy.PERMANENT_PER_THRESHOLD.value == "permanent_per_threshold"


def test_option_expiring_uses_permanent_strategy():
    """OPTION_EXPIRING should use PERMANENT_PER_THRESHOLD strategy."""
    from src.alerts.config import DedupeStrategy, get_dedupe_strategy
    from src.alerts.models import AlertType

    strategy = get_dedupe_strategy(AlertType.OPTION_EXPIRING)
    assert strategy == DedupeStrategy.PERMANENT_PER_THRESHOLD


def test_other_types_use_windowed_strategy():
    """Other alert types should default to WINDOWED_10M."""
    from src.alerts.config import DedupeStrategy, get_dedupe_strategy
    from src.alerts.models import AlertType

    strategy = get_dedupe_strategy(AlertType.ORDER_REJECTED)
    assert strategy == DedupeStrategy.WINDOWED_10M
