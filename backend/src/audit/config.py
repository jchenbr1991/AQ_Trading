"""Audit tier configuration and value mode rules.

This module defines the configuration for the audit logging system:
- Tier classification for sync vs async write behavior
- Value mode configuration for how event values are recorded
- Checksum fields for integrity verification
- Redaction rules for sensitive data protection
- Size limits for value and metadata storage

Tier 0: Critical events requiring synchronous (blocking) write
        These events must be durably persisted before the operation completes.

Tier 1: Non-critical events suitable for asynchronous (non-blocking) write
        These events can be queued and persisted in the background.
"""

from src.audit.models import AuditEventType, ValueMode

# =============================================================================
# TIER CONFIGURATION
# =============================================================================

TIER_0_EVENTS: frozenset[AuditEventType] = frozenset(
    {
        # Order events - financial transactions requiring audit guarantee
        AuditEventType.ORDER_PLACED,
        AuditEventType.ORDER_FILLED,
        AuditEventType.ORDER_CANCELLED,
        AuditEventType.ORDER_REJECTED,
        # Config events - system configuration changes
        AuditEventType.CONFIG_CREATED,
        AuditEventType.CONFIG_UPDATED,
        AuditEventType.CONFIG_DELETED,
        # Security events - authentication and authorization
        AuditEventType.PERMISSION_CHANGED,
        AuditEventType.AUTH_LOGIN,
        AuditEventType.AUTH_FAILED,
    }
)
"""Events requiring synchronous (blocking) write.

These events represent critical operations where the audit record must
be durably persisted before the operation is considered complete.
Includes financial transactions, configuration changes, and security events.
"""

TIER_1_EVENTS: frozenset[AuditEventType] = frozenset(
    {
        # Alert events - operational notifications
        AuditEventType.ALERT_EMITTED,
        AuditEventType.ALERT_ACKNOWLEDGED,
        AuditEventType.ALERT_RESOLVED,
        # System events - lifecycle and health
        AuditEventType.HEALTH_CHANGED,
        AuditEventType.SYSTEM_STARTED,
        AuditEventType.SYSTEM_STOPPED,
    }
)
"""Events suitable for asynchronous (non-blocking) write.

These events represent non-critical operations that can be queued
and persisted in the background without blocking the main operation.
Includes alerts and system health/lifecycle events.
"""


# =============================================================================
# VALUE MODE CONFIGURATION
# =============================================================================

VALUE_MODE_CONFIG: dict[AuditEventType, ValueMode] = {
    # DIFF mode: record old and new values for change tracking
    AuditEventType.CONFIG_UPDATED: ValueMode.DIFF,
    AuditEventType.PERMISSION_CHANGED: ValueMode.DIFF,
    # SNAPSHOT mode: record complete state at point in time
    AuditEventType.ORDER_PLACED: ValueMode.SNAPSHOT,
    AuditEventType.ORDER_FILLED: ValueMode.SNAPSHOT,
    AuditEventType.ORDER_CANCELLED: ValueMode.SNAPSHOT,
}
"""Mapping of event types to their value recording mode.

DIFF: Record old_value and new_value showing what changed.
      Best for update operations where tracking changes is important.

SNAPSHOT: Record complete state at the point in time.
          Best for operations where the full context is needed.

Events not in this mapping default to DIFF mode.
"""


# =============================================================================
# CHECKSUM CONFIGURATION
# =============================================================================

CHECKSUM_FIELDS: list[str] = [
    "event_id",
    "timestamp",
    "event_type",
    "actor_id",
    "resource_type",
    "resource_id",
    "old_value",
    "new_value",
]
"""Field names included in checksum computation for integrity verification.

These fields form the core identity and content of an audit event.
The checksum is computed over these fields to detect tampering.
"""


# =============================================================================
# REDACTION RULES
# =============================================================================

REDACTION_RULES: dict[str, list[str]] = {
    "account": ["api_key", "api_secret", "password", "token"],
    "config": ["credentials", "secret", "password", "key"],
    "*": ["email", "phone", "id_card", "ssn"],
}
"""Mapping of resource_type to sensitive field patterns for redaction.

When logging audit events, values matching these patterns will be redacted
to protect sensitive information.

The "*" key defines global rules that apply to all resource types.
"""


# =============================================================================
# SIZE LIMITS
# =============================================================================

MAX_VALUE_SIZE_BYTES: int = 32768
"""Maximum size in bytes for old_value or new_value fields (32 KB)."""

MAX_METADATA_SIZE_BYTES: int = 8192
"""Maximum size in bytes for the metadata field (8 KB)."""


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def get_tier(event_type: AuditEventType) -> int:
    """Get the tier classification for an event type.

    Args:
        event_type: The audit event type to classify.

    Returns:
        0 for tier 0 (sync write required), 1 for tier 1 or uncategorized (async).
    """
    if event_type in TIER_0_EVENTS:
        return 0
    return 1


def get_value_mode(event_type: AuditEventType) -> ValueMode:
    """Get the value recording mode for an event type.

    Args:
        event_type: The audit event type.

    Returns:
        The configured ValueMode, or DIFF as the default.
    """
    return VALUE_MODE_CONFIG.get(event_type, ValueMode.DIFF)


def is_sync_required(event_type: AuditEventType) -> bool:
    """Check if an event type requires synchronous write.

    Args:
        event_type: The audit event type to check.

    Returns:
        True if the event is tier 0 (requires sync write), False otherwise.
    """
    return event_type in TIER_0_EVENTS
