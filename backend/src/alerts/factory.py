"""Alert factory module for creating and validating alerts.

This module provides functions for:
- Creating AlertEvent instances with proper defaults and normalization
- Computing deduplication keys for alert grouping
- Validating alert constraints

Usage:
    from src.alerts.factory import create_alert, compute_dedupe_key, validate_alert

    alert = create_alert(
        type=AlertType.ORDER_REJECTED,
        severity=Severity.SEV2,
        summary="Order rejected: insufficient funds",
        account_id="acc123",
        symbol="AAPL",
    )

    dedupe_key = compute_dedupe_key(alert)
    validate_alert(alert)  # Raises ValueError if invalid
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from src.alerts.config import DedupeStrategy, get_dedupe_strategy
from src.alerts.models import (
    RECOVERY_TYPES,
    AlertEvent,
    AlertType,
    EntityRef,
    Severity,
    sanitize_details,
)

# Deduplication cooldown window in minutes
COOLDOWN_WINDOW_MINUTES = 10


def create_alert(
    type: AlertType,
    severity: Severity,
    summary: str,
    *,
    alert_id: UUID | None = None,
    timestamp: datetime | None = None,
    account_id: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    run_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AlertEvent:
    """Create an AlertEvent with proper defaults and normalization.

    Args:
        type: The type of alert
        severity: How critical the alert is
        summary: Human-readable one-line summary (max 255 chars, will be truncated)
        alert_id: Unique identifier (generated if not provided)
        timestamp: When the alert occurred (normalized to UTC)
        account_id: Trading account identifier
        symbol: Ticker symbol
        strategy_id: Strategy identifier
        run_id: Strategy run identifier
        details: Additional structured data (sanitized for JSON)

    Returns:
        An immutable AlertEvent instance
    """
    # Generate UUID if not provided
    if alert_id is None:
        alert_id = uuid4()

    # Normalize timestamp to UTC
    event_timestamp = _normalize_timestamp(timestamp)

    # Build EntityRef if any entity field provided
    entity_ref = _build_entity_ref(account_id, symbol, strategy_id, run_id)

    # Build fingerprint (pass details for special types like OPTION_EXPIRING)
    fingerprint = _build_fingerprint(type, account_id, symbol, strategy_id, details)

    # Sanitize details
    sanitized_details = sanitize_details(details) if details else {}

    # Truncate summary to 255 chars if too long
    truncated_summary = _truncate_summary(summary)

    return AlertEvent(
        alert_id=alert_id,
        type=type,
        severity=severity,
        event_timestamp=event_timestamp,
        fingerprint=fingerprint,
        entity_ref=entity_ref,
        summary=truncated_summary,
        details=sanitized_details,
    )


def compute_dedupe_key(alert: AlertEvent) -> str:
    """Compute deduplication key for an alert.

    Strategy depends on alert type:
    - RECOVERY_TYPES: {fingerprint}:recovery:{alert_id}
    - PERMANENT_PER_THRESHOLD: {fingerprint}:threshold_{N}:permanent
    - WINDOWED_10M (default): {fingerprint}:{bucket}
    """
    import logging

    logger = logging.getLogger(__name__)

    if alert.type in RECOVERY_TYPES:
        # Recovery events: unique by alert_id
        return f"{alert.fingerprint}:recovery:{alert.alert_id}"

    strategy = get_dedupe_strategy(alert.type)

    if strategy == DedupeStrategy.PERMANENT_PER_THRESHOLD:
        # Permanent deduplication by threshold (e.g., OPTION_EXPIRING)
        threshold_days = alert.details.get("threshold_days")
        position_id = alert.details.get("position_id", "UNKNOWN")

        if threshold_days is None:
            logger.error(
                f"Alert type {alert.type} requires 'threshold_days' in details "
                f"(position_id={position_id}, alert_id={alert.alert_id})"
            )
            raise ValueError(
                f"Alert type {alert.type} requires 'threshold_days' in details "
                f"(position_id={position_id})"
            )

        return f"{alert.fingerprint}:threshold_{threshold_days}:permanent"

    else:  # WINDOWED_10M (default)
        bucket = int(alert.event_timestamp.timestamp()) // (COOLDOWN_WINDOW_MINUTES * 60)
        return f"{alert.fingerprint}:{bucket}"


def validate_alert(alert: AlertEvent) -> None:
    """Validate an alert event.

    Raises:
        ValueError: If timestamp.tzinfo is None
        ValueError: If timestamp.tzinfo != timezone.utc
        ValueError: If len(summary) > 255
    """
    if alert.event_timestamp.tzinfo is None:
        raise ValueError("Alert timestamp must have tzinfo set")

    if alert.event_timestamp.tzinfo != timezone.utc:
        raise ValueError("Alert timestamp must be in UTC")

    if len(alert.summary) > 255:
        raise ValueError("Alert summary must not exceed 255 characters")


def _normalize_timestamp(timestamp: datetime | None) -> datetime:
    """Normalize timestamp to UTC.

    - If None: use now in UTC
    - If naive: assume UTC
    - If other tz: convert to UTC
    """
    if timestamp is None:
        return datetime.now(tz=timezone.utc)

    if timestamp.tzinfo is None:
        # Naive datetime: assume UTC
        return timestamp.replace(tzinfo=timezone.utc)

    if timestamp.tzinfo == timezone.utc:
        return timestamp

    # Convert to UTC
    return timestamp.astimezone(timezone.utc)


def _build_entity_ref(
    account_id: str | None,
    symbol: str | None,
    strategy_id: str | None,
    run_id: str | None,
) -> EntityRef | None:
    """Build EntityRef if any field is provided, else return None."""
    if account_id is None and symbol is None and strategy_id is None and run_id is None:
        return None

    return EntityRef(
        account_id=account_id,
        symbol=symbol,
        strategy_id=strategy_id,
        run_id=run_id,
    )


def _build_fingerprint(
    alert_type: AlertType,
    account_id: str | None,
    symbol: str | None,
    strategy_id: str | None,
    details: dict[str, Any] | None = None,
) -> str:
    """Build fingerprint for alert deduplication.

    For OPTION_EXPIRING: uses position_id instead of symbol
    For other types: uses standard format {type}:{account}:{symbol}:{strategy}
    """
    # OPTION_EXPIRING uses position_id for stable entity identification
    if alert_type == AlertType.OPTION_EXPIRING:
        position_id = details.get("position_id") if details else None
        if position_id is None:
            raise ValueError("OPTION_EXPIRING alert requires 'position_id' in details")
        # fingerprint: option_expiring:{account_id}:{position_id}
        # Note: strategy_id excluded - expiration is position-level event
        return f"{alert_type.value}:{account_id or ''}:{position_id}"

    # Standard fingerprint for other types
    return f"{alert_type.value}:{account_id or ''}:{symbol or ''}:{strategy_id or ''}"


def _truncate_summary(summary: str) -> str:
    """Truncate summary to 255 chars, adding '...' if truncated."""
    if len(summary) <= 255:
        return summary

    # Truncate to 252 chars + "..."
    return summary[:252] + "..."
