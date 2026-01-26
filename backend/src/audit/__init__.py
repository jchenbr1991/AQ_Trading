"""Audit logging module for the AQ Trading system.

This module provides comprehensive audit logging capabilities with:
- Immutable audit events with blockchain-style chain integrity
- Tiered write paths (sync for critical events, async for non-critical)
- Sensitive data redaction
- JSON Patch diff computation for change tracking
- Size limit enforcement with automatic reference mode fallback

Usage:
    from src.audit import (
        # Service initialization
        init_audit_service,
        get_audit_service,

        # Core models
        AuditEvent,
        AuditEventType,
        ActorType,
        AuditSeverity,
        ResourceType,
        EventSource,
        ValueMode,

        # Factory and context
        create_audit_event,
        AuditContext,
        audit_order_event,
        audit_config_change,
    )

    # Initialize during startup
    service = init_audit_service(db_session)

    # Log an event
    service.log(
        event_type=AuditEventType.ORDER_PLACED,
        actor_id="user-123",
        actor_type=ActorType.USER,
        resource_type=ResourceType.ORDER,
        resource_id="order-456",
        request_id="req-789",
        source=EventSource.WEB,
        severity=AuditSeverity.INFO,
    )
"""

# Models - core data structures and enums
# Config - tier configuration and rules
from src.audit.config import (
    CHECKSUM_FIELDS,
    MAX_VALUE_SIZE_BYTES,
    REDACTION_RULES,
    TIER_0_EVENTS,
    TIER_1_EVENTS,
    get_tier,
    get_value_mode,
    is_sync_required,
)

# Diff - diff computation and redaction
from src.audit.diff import (
    compute_diff_jsonpatch,
    enforce_size_limit,
    redact_sensitive_fields,
)

# Factory - event creation and context
from src.audit.factory import (
    AuditContext,
    audit_config_change,
    audit_order_event,
    create_audit_event,
)

# Integrity - checksum and chain verification
from src.audit.integrity import (
    compute_checksum,
    verify_chain,
    verify_checksum,
)
from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
    ValueMode,
)

# Repository - database operations
from src.audit.repository import (
    AuditQueryFilters,
    AuditRepository,
)

# Service - main audit service
from src.audit.service import AuditService

# Setup - initialization
from src.audit.setup import (
    get_audit_service,
    init_audit_service,
)

__all__ = [
    # Models
    "AuditEventType",
    "ActorType",
    "AuditSeverity",
    "ResourceType",
    "EventSource",
    "ValueMode",
    "AuditEvent",
    # Config
    "TIER_0_EVENTS",
    "TIER_1_EVENTS",
    "get_tier",
    "get_value_mode",
    "is_sync_required",
    "CHECKSUM_FIELDS",
    "REDACTION_RULES",
    "MAX_VALUE_SIZE_BYTES",
    # Integrity
    "compute_checksum",
    "verify_checksum",
    "verify_chain",
    # Diff
    "compute_diff_jsonpatch",
    "redact_sensitive_fields",
    "enforce_size_limit",
    # Repository
    "AuditRepository",
    "AuditQueryFilters",
    # Service
    "AuditService",
    # Factory
    "create_audit_event",
    "AuditContext",
    "audit_order_event",
    "audit_config_change",
    # Setup
    "init_audit_service",
    "get_audit_service",
]
