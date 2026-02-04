"""Audit logger for governance events.

This module provides the GovernanceAuditLogger class for logging
governance-specific events to PostgreSQL for compliance and debugging.

Classes:
    GovernanceAuditLogger: Log governance events to PostgreSQL

The governance audit log table schema:
    CREATE TABLE governance_audit_log (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        event_type VARCHAR(50) NOT NULL,
        hypothesis_id VARCHAR(100),
        constraint_id VARCHAR(100),
        symbol VARCHAR(20),
        strategy_id VARCHAR(100),
        action_details JSONB NOT NULL,
        trace_id VARCHAR(100),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

Example:
    >>> async with get_session() as session:
    ...     logger = GovernanceAuditLogger(session=session)
    ...     event_id = await logger.log(
    ...         event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
    ...         constraint_id="growth_leverage_guard",
    ...         action_details={"reason": "hypothesis active"},
    ...     )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from src.governance.models import GovernanceAuditEventType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class GovernanceAuditLogger:
    """Log governance events to PostgreSQL audit table.

    Provides methods for logging and querying governance-specific events
    such as constraint activations, falsifier checks, pool builds, etc.

    Args:
        session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the logger with a database session.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self.session = session

    async def log(
        self,
        event_type: GovernanceAuditEventType,
        hypothesis_id: str | None = None,
        constraint_id: str | None = None,
        symbol: str | None = None,
        strategy_id: str | None = None,
        action_details: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> int:
        """Log an audit event.

        Creates a new record in the governance_audit_log table.

        Args:
            event_type: Type of governance event
            hypothesis_id: ID of related hypothesis (if applicable)
            constraint_id: ID of related constraint (if applicable)
            symbol: Trading symbol (if applicable)
            strategy_id: Strategy ID (if applicable)
            action_details: JSONB payload with event details
            trace_id: Links to signal traces for debugging

        Returns:
            The auto-generated event ID
        """
        timestamp = datetime.now(tz=timezone.utc)

        query = text("""
            INSERT INTO governance_audit_log (
                timestamp,
                event_type,
                hypothesis_id,
                constraint_id,
                symbol,
                strategy_id,
                action_details,
                trace_id
            ) VALUES (
                :timestamp,
                :event_type,
                :hypothesis_id,
                :constraint_id,
                :symbol,
                :strategy_id,
                :action_details::jsonb,
                :trace_id
            )
            RETURNING id
        """)

        result = await self.session.execute(
            query,
            {
                "timestamp": timestamp,
                "event_type": event_type.value,
                "hypothesis_id": hypothesis_id,
                "constraint_id": constraint_id,
                "symbol": symbol,
                "strategy_id": strategy_id,
                "action_details": action_details or {},
                "trace_id": trace_id,
            },
        )

        event_id = result.scalar()
        logger.debug(
            "Logged governance audit event: type=%s, id=%s",
            event_type.value,
            event_id,
        )
        return event_id

    async def query(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        event_type: GovernanceAuditEventType | None = None,
        symbol: str | None = None,
        constraint_id: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query audit logs with filters.

        Args:
            start_time: Filter events after this time (inclusive)
            end_time: Filter events before this time (inclusive)
            event_type: Filter by event type
            symbol: Filter by trading symbol
            constraint_id: Filter by constraint ID
            limit: Maximum number of records to return (default: 100)

        Returns:
            List of dicts containing matching audit events
        """
        where_clauses: list[str] = []
        params: dict[str, Any] = {"limit": limit}

        if start_time is not None:
            where_clauses.append("timestamp >= :start_time")
            params["start_time"] = start_time

        if end_time is not None:
            where_clauses.append("timestamp <= :end_time")
            params["end_time"] = end_time

        if event_type is not None:
            where_clauses.append("event_type = :event_type")
            params["event_type"] = event_type.value

        if symbol is not None:
            where_clauses.append("symbol = :symbol")
            params["symbol"] = symbol

        if constraint_id is not None:
            where_clauses.append("constraint_id = :constraint_id")
            params["constraint_id"] = constraint_id

        where_sql = ""
        if where_clauses:
            where_sql = "WHERE " + " AND ".join(where_clauses)

        query = text(f"""
            SELECT
                id,
                timestamp,
                event_type,
                hypothesis_id,
                constraint_id,
                symbol,
                strategy_id,
                action_details,
                trace_id
            FROM governance_audit_log
            {where_sql}
            ORDER BY timestamp DESC
            LIMIT :limit
        """)  # noqa: S608 — where_clauses built from validated params, not user input

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: Any) -> dict:
        """Convert a database row to a dict.

        Args:
            row: Database row (tuple or Row object)

        Returns:
            Dict with column names as keys
        """
        # Handle Row objects with _mapping attribute
        if hasattr(row, "_mapping"):
            return dict(row._mapping)

        # Handle tuple-style rows
        columns = [
            "id",
            "timestamp",
            "event_type",
            "hypothesis_id",
            "constraint_id",
            "symbol",
            "strategy_id",
            "action_details",
            "trace_id",
        ]
        return {col: row[i] for i, col in enumerate(columns)}


__all__ = ["GovernanceAuditLogger"]
