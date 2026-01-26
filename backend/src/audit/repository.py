"""Audit repository for persisting and querying audit events.

This module provides the AuditRepository class for database operations:
- persist_audit_event: Persist an audit event with chain integrity
- get_audit_event: Fetch a single audit event by ID
- query_audit_logs: Query audit logs with filters and pagination
- get_chain_head: Get the current chain head for a chain key
- verify_chain_integrity: Verify the integrity of an audit chain

The repository implements blockchain-style chain integrity by:
1. Locking the chain head row FOR UPDATE to prevent concurrent modifications
2. Computing checksums that include the previous event's checksum
3. Using database sequences for monotonically increasing sequence IDs
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.integrity import compute_checksum, verify_chain
from src.audit.models import AuditEvent, AuditEventType, ResourceType


@dataclass
class AuditQueryFilters:
    """Filter parameters for querying audit logs.

    Attributes:
        event_type: Filter by event type
        resource_type: Filter by resource type
        resource_id: Filter by specific resource ID
        actor_id: Filter by actor ID
        start_time: Filter events after this time (inclusive)
        end_time: Filter events before this time (inclusive)
        offset: Number of records to skip (for pagination)
        limit: Maximum number of records to return
    """

    event_type: AuditEventType | None = None
    resource_type: ResourceType | None = None
    resource_id: str | None = None
    actor_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    offset: int = 0
    limit: int = 100


class AuditRepository:
    """Repository for audit log database operations.

    Provides methods for persisting and querying audit events with
    blockchain-style chain integrity verification.

    Args:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the repository with an async session.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self._session = session

    async def persist_audit_event(
        self,
        event: AuditEvent,
        chain_key: str = "default",
    ) -> tuple[int, str]:
        """Persist an audit event with chain integrity.

        This method:
        1. Locks the chain head row FOR UPDATE
        2. Gets the previous checksum from chain head (if exists)
        3. Gets the next sequence ID from audit_sequence
        4. Computes the checksum including prev_checksum
        5. INSERTs the event into audit_logs
        6. UPSERTs the chain head with the new checksum

        Args:
            event: The audit event to persist
            chain_key: The chain key for this event (default: "default")

        Returns:
            Tuple of (sequence_id, checksum) for the persisted event
        """
        # 1. Lock chain head FOR UPDATE and get prev_checksum
        chain_head_query = text("""
            SELECT chain_key, checksum, sequence_id
            FROM audit_chain_head
            WHERE chain_key = :chain_key
            FOR UPDATE
        """)
        result = await self._session.execute(chain_head_query, {"chain_key": chain_key})
        chain_head = result.fetchone()

        prev_checksum: str | None = None
        if chain_head:
            prev_checksum = chain_head[1]  # checksum column

        # 2. Get next sequence ID
        sequence_query = text("SELECT nextval('audit_sequence')")
        result = await self._session.execute(sequence_query)
        sequence_id = result.scalar()

        # 3. Compute checksum
        checksum = compute_checksum(event, sequence_id, prev_checksum)

        # 4. INSERT into audit_logs
        insert_query = text("""
            INSERT INTO audit_logs (
                id, sequence_id, timestamp, event_type, severity,
                actor_id, actor_type, resource_type, resource_id,
                request_id, source, environment, service, version,
                correlation_id, value_mode, old_value, new_value,
                metadata, checksum, prev_checksum, chain_key
            ) VALUES (
                :id, :sequence_id, :timestamp, :event_type, :severity,
                :actor_id, :actor_type, :resource_type, :resource_id,
                :request_id, :source, :environment, :service, :version,
                :correlation_id, :value_mode, :old_value, :new_value,
                :metadata, :checksum, :prev_checksum, :chain_key
            )
        """)

        await self._session.execute(
            insert_query,
            {
                "id": event.event_id,
                "sequence_id": sequence_id,
                "timestamp": event.timestamp,
                "event_type": event.event_type.value,
                "severity": event.severity.value,
                "actor_id": event.actor_id,
                "actor_type": event.actor_type.value,
                "resource_type": event.resource_type.value,
                "resource_id": event.resource_id,
                "request_id": event.request_id,
                "source": event.source.value,
                "environment": event.environment,
                "service": event.service,
                "version": event.version,
                "correlation_id": event.correlation_id,
                "value_mode": event.value_mode.value,
                "old_value": event.old_value,
                "new_value": event.new_value,
                "metadata": event.metadata,
                "checksum": checksum,
                "prev_checksum": prev_checksum,
                "chain_key": chain_key,
            },
        )

        # 5. UPSERT chain head
        upsert_query = text("""
            INSERT INTO audit_chain_head (chain_key, checksum, sequence_id, updated_at)
            VALUES (:chain_key, :checksum, :sequence_id, NOW())
            ON CONFLICT (chain_key) DO UPDATE SET
                checksum = EXCLUDED.checksum,
                sequence_id = EXCLUDED.sequence_id,
                updated_at = NOW()
        """)

        await self._session.execute(
            upsert_query,
            {
                "chain_key": chain_key,
                "checksum": checksum,
                "sequence_id": sequence_id,
            },
        )

        return (sequence_id, checksum)

    async def get_audit_event(self, event_id: UUID) -> dict | None:
        """Fetch a single audit event by ID.

        Args:
            event_id: The UUID of the event to fetch

        Returns:
            Dict containing event data, or None if not found
        """
        query = text("""
            SELECT
                id, sequence_id, timestamp, event_type, severity,
                actor_id, actor_type, resource_type, resource_id,
                request_id, source, environment, service, version,
                correlation_id, value_mode, old_value, new_value,
                metadata, checksum, prev_checksum, chain_key
            FROM audit_logs
            WHERE id = :event_id
        """)

        result = await self._session.execute(query, {"event_id": event_id})
        row = result.fetchone()

        if row is None:
            return None

        return self._row_to_dict(row)

    async def query_audit_logs(self, filters: AuditQueryFilters) -> list[dict]:
        """Query audit logs with filters and pagination.

        Args:
            filters: Filter parameters for the query

        Returns:
            List of dicts containing matching audit events
        """
        # Build query with dynamic WHERE clauses
        where_clauses = []
        params: dict[str, Any] = {}

        if filters.event_type is not None:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = filters.event_type.value

        if filters.resource_type is not None:
            where_clauses.append("resource_type = :resource_type")
            params["resource_type"] = filters.resource_type.value

        if filters.resource_id is not None:
            where_clauses.append("resource_id = :resource_id")
            params["resource_id"] = filters.resource_id

        if filters.actor_id is not None:
            where_clauses.append("actor_id = :actor_id")
            params["actor_id"] = filters.actor_id

        if filters.start_time is not None:
            where_clauses.append("timestamp >= :start_time")
            params["start_time"] = filters.start_time

        if filters.end_time is not None:
            where_clauses.append("timestamp <= :end_time")
            params["end_time"] = filters.end_time

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = text(f"""
            SELECT
                id, sequence_id, timestamp, event_type, severity,
                actor_id, actor_type, resource_type, resource_id,
                request_id, source, environment, service, version,
                correlation_id, value_mode, old_value, new_value,
                metadata, checksum, prev_checksum, chain_key
            FROM audit_logs
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """)

        params["limit"] = filters.limit
        params["offset"] = filters.offset

        result = await self._session.execute(query, params)
        rows = result.fetchall()

        return [self._row_to_dict(row) for row in rows]

    async def get_chain_head(self, chain_key: str) -> dict | None:
        """Fetch the chain head record for a chain key.

        Args:
            chain_key: The chain key to look up

        Returns:
            Dict containing chain head data, or None if not found
        """
        query = text("""
            SELECT chain_key, checksum, sequence_id, updated_at
            FROM audit_chain_head
            WHERE chain_key = :chain_key
        """)

        result = await self._session.execute(query, {"chain_key": chain_key})
        row = result.fetchone()

        if row is None:
            return None

        return {
            "chain_key": row[0],
            "checksum": row[1],
            "sequence_id": row[2],
            "updated_at": row[3],
        }

    async def verify_chain_integrity(
        self,
        chain_key: str,
        limit: int = 100,
    ) -> tuple[bool, list[str]]:
        """Verify the integrity of an audit chain.

        Fetches events for the given chain key and verifies:
        - Sequence IDs are monotonically increasing
        - Each event's prev_checksum matches previous event's checksum
        - Each event's stored checksum is valid

        Args:
            chain_key: The chain key to verify
            limit: Maximum number of events to verify (default: 100)

        Returns:
            Tuple of (is_valid, errors) where is_valid is True if all
            checks pass, and errors is a list of error descriptions
        """
        query = text("""
            SELECT
                id, sequence_id, timestamp, event_type, severity,
                actor_id, actor_type, resource_type, resource_id,
                request_id, source, environment, service, version,
                correlation_id, value_mode, old_value, new_value,
                metadata, checksum, prev_checksum, chain_key
            FROM audit_logs
            WHERE chain_key = :chain_key
            ORDER BY sequence_id ASC
            LIMIT :limit
        """)

        result = await self._session.execute(query, {"chain_key": chain_key, "limit": limit})
        rows = result.fetchall()

        if not rows:
            return (True, [])

        # Convert rows to dicts for verify_chain
        events = [self._row_to_dict(row) for row in rows]

        return verify_chain(events)

    def _row_to_dict(self, row: Any) -> dict:
        """Convert a database row to a dict.

        Args:
            row: Database row (tuple or Row object)

        Returns:
            Dict with column names as keys
        """
        columns = [
            "id",
            "sequence_id",
            "timestamp",
            "event_type",
            "severity",
            "actor_id",
            "actor_type",
            "resource_type",
            "resource_id",
            "request_id",
            "source",
            "environment",
            "service",
            "version",
            "correlation_id",
            "value_mode",
            "old_value",
            "new_value",
            "metadata",
            "checksum",
            "prev_checksum",
            "chain_key",
        ]

        # Handle both tuple and Row objects
        if hasattr(row, "_mapping"):
            return dict(row._mapping)
        else:
            return {col: row[i] for i, col in enumerate(columns)}
