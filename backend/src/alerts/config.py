"""Alert deduplication strategy configuration.

This module defines configurable deduplication strategies for different alert types.
The default strategy (WINDOWED_10M) groups alerts within 10-minute windows.
Special strategies can be registered for specific alert types.
"""

from enum import Enum

from src.alerts.models import AlertType


class DedupeStrategy(str, Enum):
    """Alert deduplication strategies.

    WINDOWED_10M: Group alerts within 10-minute windows (default)
    PERMANENT_PER_THRESHOLD: Dedupe permanently by threshold, no time window
    """

    WINDOWED_10M = "windowed_10m"
    PERMANENT_PER_THRESHOLD = "permanent_per_threshold"


# Alert type to deduplication strategy mapping
DEDUPE_STRATEGIES: dict[AlertType, DedupeStrategy] = {
    AlertType.OPTION_EXPIRING: DedupeStrategy.PERMANENT_PER_THRESHOLD,
    # All other types default to WINDOWED_10M
}


def get_dedupe_strategy(alert_type: AlertType) -> DedupeStrategy:
    """Get deduplication strategy for an alert type.

    Args:
        alert_type: The type of alert

    Returns:
        The deduplication strategy to use
    """
    return DEDUPE_STRATEGIES.get(alert_type, DedupeStrategy.WINDOWED_10M)
