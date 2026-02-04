"""Pydantic models for governance audit logging.

This module defines the AuditLogEntry model used to represent
governance audit events in a structured, type-safe format.

Classes:
    AuditLogEntry: Structured representation of a governance audit event

The model uses GovernanceBaseModel (extra='forbid') to ensure
strict validation of audit entries.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from src.governance.models import GovernanceAuditEventType, GovernanceBaseModel


class AuditLogEntry(GovernanceBaseModel):
    """Structured representation of a governance audit event.

    Each entry corresponds to a single governance action that was logged,
    such as a constraint activation, falsifier check, or risk budget adjustment.

    Attributes:
        id: Auto-generated unique event identifier.
        timestamp: When the event occurred (UTC).
        event_type: Type of governance event (from GovernanceAuditEventType enum).
        hypothesis_id: ID of related hypothesis (if applicable).
        constraint_id: ID of related constraint (if applicable).
        symbol: Trading symbol (if applicable).
        strategy_id: Strategy ID (if applicable).
        action_details: Structured payload with event-specific details.
        trace_id: Links to signal traces for debugging.
    """

    id: int
    timestamp: datetime
    event_type: GovernanceAuditEventType
    hypothesis_id: str | None = None
    constraint_id: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    action_details: dict[str, Any] = Field(default_factory=dict)
    trace_id: str | None = None


__all__ = ["AuditLogEntry"]
