"""In-memory audit log store for governance events.

This module provides an InMemoryAuditStore that stores audit events
in memory, suitable for use in tests and when no database is available.
It provides the same query interface as GovernanceAuditLogger but
without requiring a database connection.

Classes:
    InMemoryAuditStore: Thread-safe in-memory audit log store

Example:
    >>> store = InMemoryAuditStore()
    >>> entry_id = store.log(
    ...     event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
    ...     constraint_id="growth_leverage_guard",
    ... )
    >>> entries = store.query(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from src.governance.audit.models import AuditLogEntry
from src.governance.models import GovernanceAuditEventType

logger = logging.getLogger(__name__)


class InMemoryAuditStore:
    """Thread-safe in-memory audit log store.

    Stores governance audit events in an in-memory list. Provides
    synchronous log() and query() methods matching the GovernanceAuditLogger
    interface pattern.

    This store is used by:
    - The audit API endpoint when no database is configured
    - Constraint resolver and falsifier checker audit hooks (sync context)
    - Tests

    Attributes:
        _entries: Internal list of AuditLogEntry objects.
        _lock: Threading lock for thread-safe access.
        _next_id: Auto-incrementing ID counter.
    """

    def __init__(self) -> None:
        """Initialize an empty audit store."""
        self._entries: list[AuditLogEntry] = []
        self._lock = threading.Lock()
        self._next_id = 1

    def log(
        self,
        event_type: GovernanceAuditEventType,
        hypothesis_id: str | None = None,
        constraint_id: str | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        action_details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> int:
        """Log an audit event to the in-memory store.

        Creates a new AuditLogEntry and appends it to the internal list.

        Args:
            event_type: Type of governance event.
            hypothesis_id: ID of related hypothesis (if applicable).
            constraint_id: ID of related constraint (if applicable).
            symbol: Trading symbol (if applicable).
            strategy_id: Strategy ID (if applicable).
            action_details: Structured payload with event details.
            trace_id: Links to signal traces for debugging.

        Returns:
            The auto-generated event ID.
        """
        with self._lock:
            entry_id = self._next_id
            self._next_id += 1

            entry = AuditLogEntry(
                id=entry_id,
                timestamp=datetime.now(tz=timezone.utc),
                event_type=event_type,
                hypothesis_id=hypothesis_id,
                constraint_id=constraint_id,
                symbol=symbol,
                strategy_id=strategy_id,
                action_details=action_details or {},
                trace_id=trace_id,
            )

            self._entries.append(entry)

            logger.debug(
                "Logged governance audit event: type=%s, id=%s",
                event_type.value,
                entry_id,
            )

            return entry_id

    def query(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_type: GovernanceAuditEventType | None = None,
        symbol: str | None = None,
        constraint_id: str | None = None,
        limit: int = 100,
    ) -> list[AuditLogEntry]:
        """Query audit logs with filters.

        Args:
            start_time: Filter events after this time (inclusive).
            end_time: Filter events before this time (inclusive).
            event_type: Filter by event type.
            symbol: Filter by trading symbol.
            constraint_id: Filter by constraint ID.
            limit: Maximum number of records to return (default: 100).

        Returns:
            List of AuditLogEntry objects matching the filters,
            ordered by timestamp descending.
        """
        with self._lock:
            results = list(self._entries)

        # Apply filters
        if start_time is not None:
            results = [e for e in results if e.timestamp >= start_time]

        if end_time is not None:
            results = [e for e in results if e.timestamp <= end_time]

        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]

        if symbol is not None:
            results = [e for e in results if e.symbol == symbol]

        if constraint_id is not None:
            results = [e for e in results if e.constraint_id == constraint_id]

        # Sort by timestamp descending (newest first)
        results.sort(key=lambda e: e.timestamp, reverse=True)

        # Apply limit
        return results[:limit]

    def count(self) -> int:
        """Return the total number of audit entries.

        Returns:
            Count of all stored entries.
        """
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        """Clear all audit entries.

        Used primarily for testing.
        """
        with self._lock:
            self._entries.clear()
            self._next_id = 1


__all__ = ["InMemoryAuditStore"]
