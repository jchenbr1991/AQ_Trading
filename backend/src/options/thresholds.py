"""Expiration threshold configuration for options alerts.

This module defines the threshold-driven logic for option expiration alerts.
Thresholds are table-driven for easy modification (upgrade to config file later).
"""

from dataclasses import dataclass

from src.alerts.models import Severity


@dataclass(frozen=True)
class ExpirationThreshold:
    """Expiration threshold configuration.

    Attributes:
        days: Days to expiry that triggers this threshold
        severity: Alert severity level for this threshold
    """

    days: int
    severity: Severity


# Threshold table (ascending by days: 0 is most urgent, 7 is least)
EXPIRATION_THRESHOLDS = [
    ExpirationThreshold(days=0, severity=Severity.SEV1),  # Today - critical
    ExpirationThreshold(days=1, severity=Severity.SEV1),  # Tomorrow - critical
    ExpirationThreshold(days=3, severity=Severity.SEV2),  # 3 days - warning
    ExpirationThreshold(days=7, severity=Severity.SEV3),  # 7 days - info
]

# Maximum threshold for "out of scope" classification
MAX_THRESHOLD_DAYS = max(t.days for t in EXPIRATION_THRESHOLDS)


def get_applicable_thresholds(days_to_expiry: int) -> list[ExpirationThreshold]:
    """Return all thresholds that should trigger for given DTE.

    Returns thresholds where threshold.days >= days_to_expiry.
    This enables "catch-up" behavior on restart: DTE=0 triggers all 4 thresholds,
    relying on dedupe_key to filter already-created alerts.

    Args:
        days_to_expiry: Days until option expiration (must be >= 0)

    Returns:
        List of applicable thresholds, sorted by days ascending

    Examples:
        DTE=10 -> []
        DTE=6  -> [7-day]
        DTE=2  -> [3-day, 7-day]
        DTE=1  -> [1-day, 3-day, 7-day]
        DTE=0  -> [0-day, 1-day, 3-day, 7-day]
    """
    return [t for t in EXPIRATION_THRESHOLDS if t.days >= days_to_expiry]
