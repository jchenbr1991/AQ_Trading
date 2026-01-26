# backend/src/api/audit.py
"""Audit API endpoints for viewing and verifying audit logs."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.integrity import verify_chain
from src.db.database import get_session


# Response schemas
class AuditLogResponse(BaseModel):
    """Response model for a single audit log."""

    event_id: str
    sequence_id: int
    timestamp: datetime
    event_type: str
    severity: str
    actor_id: str
    actor_type: str
    resource_type: str
    resource_id: str
    request_id: str
    source: str
    environment: str
    service: str
    version: str
    correlation_id: str | None
    value_mode: str
    old_value: dict | None
    new_value: dict | None
    metadata: dict | None
    checksum: str
    prev_checksum: str | None
    chain_key: str


class AuditLogListResponse(BaseModel):
    """Response model for paginated audit log list."""

    logs: list[AuditLogResponse]
    total: int
    offset: int
    limit: int


class AuditStatsResponse(BaseModel):
    """Response model for audit statistics."""

    total: int
    by_event_type: dict[str, int]
    by_actor: dict[str, int]
    by_resource_type: dict[str, int]


class ChainIntegrityResponse(BaseModel):
    """Response model for chain integrity verification result."""

    chain_key: str
    is_valid: bool
    errors: list[str]
    events_verified: int


class AuditQueryParams(BaseModel):
    """Query parameters for filtering audit logs."""

    event_type: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    actor_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    offset: int = 0
    limit: int = 50


# Router
router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    db: AsyncSession = Depends(get_session),
) -> AuditStatsResponse:
    """Get audit log statistics.

    Returns:
        Statistics including total count, breakdown by event type, actor, and resource type
    """
    # Total audit logs
    total_sql = text("SELECT COUNT(*) FROM audit_logs")
    total_result = await db.execute(total_sql)
    total = total_result.scalar() or 0

    # Count by event_type
    event_type_sql = text("""
        SELECT event_type, COUNT(*) as count
        FROM audit_logs
        GROUP BY event_type
    """)
    event_type_result = await db.execute(event_type_sql)
    event_type_rows = event_type_result.fetchall()
    by_event_type = {row[0]: row[1] for row in event_type_rows}

    # Count by actor_id
    actor_sql = text("""
        SELECT actor_id, COUNT(*) as count
        FROM audit_logs
        GROUP BY actor_id
    """)
    actor_result = await db.execute(actor_sql)
    actor_rows = actor_result.fetchall()
    by_actor = {row[0]: row[1] for row in actor_rows}

    # Count by resource_type
    resource_type_sql = text("""
        SELECT resource_type, COUNT(*) as count
        FROM audit_logs
        GROUP BY resource_type
    """)
    resource_type_result = await db.execute(resource_type_sql)
    resource_type_rows = resource_type_result.fetchall()
    by_resource_type = {row[0]: row[1] for row in resource_type_rows}

    return AuditStatsResponse(
        total=total,
        by_event_type=by_event_type,
        by_actor=by_actor,
        by_resource_type=by_resource_type,
    )


@router.get("/integrity/{chain_key}", response_model=ChainIntegrityResponse)
async def verify_chain_integrity(
    chain_key: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_session),
) -> ChainIntegrityResponse:
    """Verify the integrity of an audit chain.

    Args:
        chain_key: The chain key to verify
        limit: Maximum number of events to verify (default 100, max 1000)
        db: Database session

    Returns:
        Chain integrity verification result including validity and any errors found
    """
    # Fetch events for the chain ordered by sequence_id
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

    result = await db.execute(query, {"chain_key": chain_key, "limit": limit})
    rows = result.fetchall()

    if not rows:
        return ChainIntegrityResponse(
            chain_key=chain_key,
            is_valid=True,
            errors=[],
            events_verified=0,
        )

    # Convert rows to dicts for verify_chain
    events = [_row_to_dict(row) for row in rows]

    # Verify the chain
    is_valid, errors = verify_chain(events)

    return ChainIntegrityResponse(
        chain_key=chain_key,
        is_valid=is_valid,
        errors=errors,
        events_verified=len(events),
    )


@router.get("/{event_id}", response_model=AuditLogResponse)
async def get_audit_event(
    event_id: UUID,
    db: AsyncSession = Depends(get_session),
) -> AuditLogResponse:
    """Get a single audit event by UUID.

    Args:
        event_id: The UUID of the audit event
        db: Database session

    Returns:
        The audit event details

    Raises:
        HTTPException: 404 if audit event not found
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

    result = await db.execute(query, {"event_id": str(event_id)})
    row = result.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Audit event not found")

    event_dict = _row_to_dict(row)
    return _dict_to_response(event_dict)


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    event_type: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    resource_id: str | None = Query(default=None),
    actor_id: str | None = Query(default=None),
    start_time: datetime | None = Query(default=None),
    end_time: datetime | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> AuditLogListResponse:
    """List audit logs with optional filtering and pagination.

    Args:
        event_type: Filter by event type (e.g., "order_placed", "config_updated")
        resource_type: Filter by resource type (e.g., "order", "config")
        resource_id: Filter by specific resource ID
        actor_id: Filter by actor ID
        start_time: Filter events after this time (inclusive)
        end_time: Filter events before this time (inclusive)
        offset: Number of records to skip (default 0)
        limit: Maximum number of records to return (default 50, max 100)
        db: Database session

    Returns:
        Paginated list of audit logs with total count
    """
    # Build WHERE clauses and params dynamically
    where_clauses: list[str] = []
    params: dict[str, Any] = {"limit": limit, "offset": offset}

    if event_type is not None:
        where_clauses.append("event_type = :event_type")
        params["event_type"] = event_type

    if resource_type is not None:
        where_clauses.append("resource_type = :resource_type")
        params["resource_type"] = resource_type

    if resource_id is not None:
        where_clauses.append("resource_id = :resource_id")
        params["resource_id"] = resource_id

    if actor_id is not None:
        where_clauses.append("actor_id = :actor_id")
        params["actor_id"] = actor_id

    if start_time is not None:
        where_clauses.append("timestamp >= :start_time")
        params["start_time"] = start_time.isoformat()

    if end_time is not None:
        where_clauses.append("timestamp <= :end_time")
        params["end_time"] = end_time.isoformat()

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # Get total count
    # Note: where_sql is built from hardcoded column names only, not user input
    count_sql = text(f"SELECT COUNT(*) FROM audit_logs {where_sql}")  # noqa: S608
    count_result = await db.execute(count_sql, params)
    total = count_result.scalar() or 0

    # Get paginated results
    # Note: where_sql is built from hardcoded column names only, not user input
    query_sql = text(  # noqa: S608
        f"""
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
    """
    )

    result = await db.execute(query_sql, params)
    rows = result.fetchall()

    logs = [_dict_to_response(_row_to_dict(row)) for row in rows]

    return AuditLogListResponse(
        logs=logs,
        total=total,
        offset=offset,
        limit=limit,
    )


def _row_to_dict(row: Any) -> dict:
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


def _parse_timestamp(value: str | datetime) -> datetime:
    """Parse a timestamp value from database.

    Handles both string (SQLite) and datetime (PostgreSQL) values.

    Args:
        value: The timestamp value from the database

    Returns:
        A datetime object with UTC timezone
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    # Parse ISO format string (SQLite stores as string)
    if "+" in value or value.endswith("Z"):
        # Has timezone info
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        # No timezone info, assume UTC
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def _parse_json_field(value: str | dict | None) -> dict | None:
    """Parse a JSON field from database.

    Args:
        value: JSON string or dict from database

    Returns:
        Parsed dict or None
    """
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    # SQLite stores JSON as string
    import json

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _dict_to_response(event_dict: dict) -> AuditLogResponse:
    """Convert an event dict to an AuditLogResponse.

    Args:
        event_dict: Dict containing event data

    Returns:
        AuditLogResponse model
    """
    return AuditLogResponse(
        event_id=str(event_dict["id"]),
        sequence_id=event_dict["sequence_id"],
        timestamp=_parse_timestamp(event_dict["timestamp"]),
        event_type=event_dict["event_type"],
        severity=event_dict["severity"],
        actor_id=event_dict["actor_id"],
        actor_type=event_dict["actor_type"],
        resource_type=event_dict["resource_type"],
        resource_id=event_dict["resource_id"],
        request_id=event_dict["request_id"],
        source=event_dict["source"],
        environment=event_dict["environment"],
        service=event_dict["service"],
        version=event_dict["version"],
        correlation_id=event_dict["correlation_id"],
        value_mode=event_dict["value_mode"],
        old_value=_parse_json_field(event_dict["old_value"]),
        new_value=_parse_json_field(event_dict["new_value"]),
        metadata=_parse_json_field(event_dict["metadata"]),
        checksum=event_dict["checksum"],
        prev_checksum=event_dict["prev_checksum"],
        chain_key=event_dict["chain_key"],
    )
