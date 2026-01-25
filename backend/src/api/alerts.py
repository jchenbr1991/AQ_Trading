# backend/src/api/alerts.py
"""Alerts API endpoints for viewing and monitoring alerts."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session


# Response schemas
class AlertResponse(BaseModel):
    """Response model for a single alert."""

    id: str
    type: str
    severity: int
    summary: str
    fingerprint: str
    suppressed_count: int
    event_timestamp: datetime
    created_at: datetime
    entity_account_id: str | None
    entity_symbol: str | None


class AlertListResponse(BaseModel):
    """Response model for paginated alert list."""

    alerts: list[AlertResponse]
    total: int
    offset: int
    limit: int


class DeliveryResponse(BaseModel):
    """Response model for a delivery attempt."""

    id: str
    channel: str
    destination_key: str
    attempt_number: int
    status: str
    response_code: int | None
    error_message: str | None
    created_at: datetime
    sent_at: datetime | None


class AlertStatsResponse(BaseModel):
    """Response model for alert statistics."""

    total_24h: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    delivery_success_rate: float


# Router
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    severity: int | None = Query(default=None, ge=1, le=3),
    type: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> AlertListResponse:
    """List alerts with optional filtering and pagination.

    Args:
        severity: Filter by severity level (1=SEV1/Critical, 2=SEV2/Warning, 3=SEV3/Info)
        type: Filter by alert type (e.g., "order_rejected", "component_unhealthy")
        offset: Number of records to skip (default 0)
        limit: Maximum number of records to return (default 50, max 100)
        db: Database session

    Returns:
        Paginated list of alerts with total count
    """
    # Build params dict for parameterized queries
    params: dict = {"limit": limit, "offset": offset}

    # Choose the appropriate SQL based on filters
    # This approach avoids dynamic SQL construction that triggers security warnings
    if severity is not None and type is not None:
        params["severity"] = severity
        params["type"] = type
        count_sql = text("SELECT COUNT(*) FROM alerts WHERE severity = :severity AND type = :type")
        query_sql = text("""
            SELECT id, type, severity, summary, fingerprint, suppressed_count,
                   event_timestamp, created_at, entity_account_id, entity_symbol
            FROM alerts
            WHERE severity = :severity AND type = :type
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
    elif severity is not None:
        params["severity"] = severity
        count_sql = text("SELECT COUNT(*) FROM alerts WHERE severity = :severity")
        query_sql = text("""
            SELECT id, type, severity, summary, fingerprint, suppressed_count,
                   event_timestamp, created_at, entity_account_id, entity_symbol
            FROM alerts
            WHERE severity = :severity
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
    elif type is not None:
        params["type"] = type
        count_sql = text("SELECT COUNT(*) FROM alerts WHERE type = :type")
        query_sql = text("""
            SELECT id, type, severity, summary, fingerprint, suppressed_count,
                   event_timestamp, created_at, entity_account_id, entity_symbol
            FROM alerts
            WHERE type = :type
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)
    else:
        count_sql = text("SELECT COUNT(*) FROM alerts")
        query_sql = text("""
            SELECT id, type, severity, summary, fingerprint, suppressed_count,
                   event_timestamp, created_at, entity_account_id, entity_symbol
            FROM alerts
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
        """)

    # Get total count
    count_result = await db.execute(count_sql, params)
    total = count_result.scalar() or 0

    # Get paginated results
    result = await db.execute(query_sql, params)
    rows = result.fetchall()

    alerts = [
        AlertResponse(
            id=row[0],
            type=row[1],
            severity=row[2],
            summary=row[3],
            fingerprint=row[4],
            suppressed_count=row[5],
            event_timestamp=_parse_timestamp(row[6]),
            created_at=_parse_timestamp(row[7]),
            entity_account_id=row[8],
            entity_symbol=row[9],
        )
        for row in rows
    ]

    return AlertListResponse(
        alerts=alerts,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    db: AsyncSession = Depends(get_session),
) -> AlertStatsResponse:
    """Get alert statistics for the last 24 hours.

    Returns:
        Statistics including total count, breakdown by severity and type,
        and delivery success rate
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    cutoff_str = cutoff.isoformat()

    # Total alerts in last 24h
    total_sql = text("""
        SELECT COUNT(*) FROM alerts WHERE created_at >= :cutoff
    """)
    total_result = await db.execute(total_sql, {"cutoff": cutoff_str})
    total_24h = total_result.scalar() or 0

    # Count by severity
    severity_sql = text("""
        SELECT severity, COUNT(*) as count
        FROM alerts
        WHERE created_at >= :cutoff
        GROUP BY severity
    """)
    severity_result = await db.execute(severity_sql, {"cutoff": cutoff_str})
    severity_rows = severity_result.fetchall()
    by_severity = {f"SEV{row[0]}": row[1] for row in severity_rows}

    # Count by type
    type_sql = text("""
        SELECT type, COUNT(*) as count
        FROM alerts
        WHERE created_at >= :cutoff
        GROUP BY type
    """)
    type_result = await db.execute(type_sql, {"cutoff": cutoff_str})
    type_rows = type_result.fetchall()
    by_type = {row[0]: row[1] for row in type_rows}

    # Delivery success rate
    delivery_sql = text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent
        FROM alert_deliveries
        WHERE created_at >= :cutoff
    """)
    delivery_result = await db.execute(delivery_sql, {"cutoff": cutoff_str})
    delivery_row = delivery_result.fetchone()

    if delivery_row and delivery_row[0] > 0:
        delivery_success_rate = (delivery_row[1] or 0) / delivery_row[0]
    else:
        delivery_success_rate = 1.0  # No deliveries means 100% success (no failures)

    return AlertStatsResponse(
        total_24h=total_24h,
        by_severity=by_severity,
        by_type=by_type,
        delivery_success_rate=delivery_success_rate,
    )


@router.get("/{alert_id}/deliveries", response_model=list[DeliveryResponse])
async def get_alert_deliveries(
    alert_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[DeliveryResponse]:
    """Get delivery attempts for a specific alert.

    Args:
        alert_id: The UUID of the alert
        db: Database session

    Returns:
        List of delivery attempts for the alert

    Raises:
        HTTPException: 404 if alert not found
    """
    # Check if alert exists
    check_sql = text("SELECT id FROM alerts WHERE id = :alert_id")
    check_result = await db.execute(check_sql, {"alert_id": alert_id})
    if check_result.fetchone() is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Get deliveries
    query_sql = text("""
        SELECT id, channel, destination_key, attempt_number, status,
               response_code, error_message, created_at, sent_at
        FROM alert_deliveries
        WHERE alert_id = :alert_id
        ORDER BY attempt_number ASC, created_at ASC
    """)
    result = await db.execute(query_sql, {"alert_id": alert_id})
    rows = result.fetchall()

    return [
        DeliveryResponse(
            id=row[0],
            channel=row[1],
            destination_key=row[2],
            attempt_number=row[3],
            status=row[4],
            response_code=row[5],
            error_message=row[6],
            created_at=_parse_timestamp(row[7]),
            sent_at=_parse_timestamp(row[8]) if row[8] else None,
        )
        for row in rows
    ]


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
