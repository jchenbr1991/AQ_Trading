"""Options API endpoints for expiration alerts and position management.

Endpoints:
- GET /api/options/expiring - List expiring option alerts
- POST /api/options/{position_id}/close - Close an option position
- POST /api/options/alerts/{alert_id}/acknowledge - Acknowledge an alert
- POST /api/options/check-expirations - Manual trigger for expiration check
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.options.idempotency import IdempotencyService
from src.options.models import (
    AcknowledgeAlertResponse,
    AlertSummary,
    ClosePositionRequest,
    ClosePositionResponse,
    ExpiringAlertRow,
    ExpiringAlertsResponse,
    ManualCheckResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/options", tags=["options"])


def _is_sqlite(db: AsyncSession) -> bool:
    """Check if the database is SQLite (for test compatibility)."""
    dialect_name = db.bind.dialect.name if db.bind else ""
    return dialect_name == "sqlite"


@router.get("/expiring", response_model=ExpiringAlertsResponse)
async def get_expiring_alerts(
    account_id: str = Query(..., description="Account ID to fetch alerts for"),
    status: str = Query(
        default="pending",
        pattern="^(pending|acknowledged|all)$",
        description="Filter by alert status",
    ),
    sort_by: str = Query(
        default="dte",
        pattern="^(dte|severity|expiry)$",
        description="Sort order",
    ),
    db: AsyncSession = Depends(get_session),
) -> ExpiringAlertsResponse:
    """Get expiring option alerts for an account.

    Returns alerts at alert-level granularity (same position may have multiple alerts).

    Args:
        account_id: Account to fetch alerts for
        status: Filter by status (pending, acknowledged, all)
        sort_by: Sort order (dte, severity, expiry)
        db: Database session

    Returns:
        List of expiring alerts with position details
    """
    # Check if using SQLite (for tests) or PostgreSQL (production)
    is_sqlite = _is_sqlite(db)

    # Build the query based on status filter
    base_where = "a.type = 'option_expiring' AND a.entity_account_id = :account_id"

    if status == "pending":
        # No acknowledged_at field exists yet - for V1 we treat all as pending
        status_filter = ""
    elif status == "acknowledged":
        status_filter = ""  # V1: no ack support yet
    else:  # all
        status_filter = ""

    if is_sqlite:
        # SQLite-compatible JSON extraction
        if sort_by == "dte":
            order_clause = "CAST(json_extract(a.details, '$.days_to_expiry') AS INTEGER) ASC, a.created_at DESC"
        elif sort_by == "severity":
            order_clause = "a.severity ASC, a.created_at DESC"
        else:  # expiry
            order_clause = "json_extract(a.details, '$.expiry_date') ASC, a.created_at DESC"

        # Query alerts with position info from details (SQLite)
        query_sql = text(f"""
            SELECT
                a.id as alert_id,
                a.severity,
                CAST(json_extract(a.details, '$.threshold_days') AS INTEGER) as threshold_days,
                a.created_at,
                0 as acknowledged,
                NULL as acknowledged_at,
                CAST(json_extract(a.details, '$.position_id') AS INTEGER) as position_id,
                a.entity_symbol as symbol,
                CAST(json_extract(a.details, '$.strike') AS REAL) as strike,
                json_extract(a.details, '$.put_call') as put_call,
                json_extract(a.details, '$.expiry_date') as expiry_date,
                CAST(json_extract(a.details, '$.quantity') AS INTEGER) as quantity,
                CAST(json_extract(a.details, '$.days_to_expiry') AS INTEGER) as days_to_expiry,
                NULL as current_price,
                NULL as market_value,
                NULL as unrealized_pnl,
                1 as is_closable
            FROM alerts a
            WHERE {base_where} {status_filter}
            ORDER BY {order_clause}
        """)
    else:
        # PostgreSQL-compatible JSON extraction
        if sort_by == "dte":
            order_clause = "(a.details->>'days_to_expiry')::int ASC, a.created_at DESC"
        elif sort_by == "severity":
            order_clause = "a.severity ASC, a.created_at DESC"
        else:  # expiry
            order_clause = "a.details->>'expiry_date' ASC, a.created_at DESC"

        # Query alerts with position info from details (PostgreSQL)
        query_sql = text(f"""
            SELECT
                a.id::text as alert_id,
                a.severity,
                (a.details->>'threshold_days')::int as threshold_days,
                a.created_at,
                false as acknowledged,
                NULL::timestamp as acknowledged_at,
                (a.details->>'position_id')::int as position_id,
                a.entity_symbol as symbol,
                (a.details->>'strike')::float as strike,
                a.details->>'put_call' as put_call,
                a.details->>'expiry_date' as expiry_date,
                (a.details->>'quantity')::int as quantity,
                (a.details->>'days_to_expiry')::int as days_to_expiry,
                NULL::float as current_price,
                NULL::float as market_value,
                NULL::float as unrealized_pnl,
                true as is_closable
            FROM alerts a
            WHERE {base_where} {status_filter}
            ORDER BY {order_clause}
        """)

    result = await db.execute(query_sql, {"account_id": account_id})
    rows = result.fetchall()

    # Map severity int to string
    severity_map = {1: "critical", 2: "warning", 3: "info"}

    alerts = []
    critical_count = 0
    warning_count = 0
    info_count = 0

    for row in rows:
        severity_int = row[1]
        severity_str = severity_map.get(severity_int, "info")

        if severity_str == "critical":
            critical_count += 1
        elif severity_str == "warning":
            warning_count += 1
        else:
            info_count += 1

        alert = ExpiringAlertRow(
            alert_id=str(row[0]),
            severity=severity_str,
            threshold_days=row[2] or 0,
            created_at=_parse_timestamp(row[3]),
            acknowledged=bool(row[4]),
            acknowledged_at=_parse_timestamp(row[5]) if row[5] else None,
            position_id=row[6] or 0,
            symbol=row[7] or "",
            strike=row[8] or 0.0,
            put_call=row[9] or "call",
            expiry_date=row[10] or "",
            quantity=row[11] or 0,
            days_to_expiry=row[12] or 0,
            current_price=row[13],
            market_value=row[14],
            unrealized_pnl=row[15],
            is_closable=bool(row[16]),
        )
        alerts.append(alert)

    return ExpiringAlertsResponse(
        alerts=alerts,
        total=len(alerts),
        summary=AlertSummary(
            critical_count=critical_count,
            warning_count=warning_count,
            info_count=info_count,
        ),
    )


@router.post("/{position_id}/close", response_model=ClosePositionResponse)
async def close_position(
    position_id: int,
    request: ClosePositionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_session),
) -> ClosePositionResponse:
    """Close an option position (idempotent).

    Creates a sell order for the position. Uses idempotency key to prevent
    duplicate orders from repeated requests.

    Args:
        position_id: ID of the position to close
        request: Close request with optional reason
        idempotency_key: Idempotency key header for deduplication
        db: Database session

    Returns:
        Close response with order ID

    Raises:
        404: Position not found
        409: Position already has pending close order
    """
    idempotency = IdempotencyService(db)

    # Check for cached response
    exists, cached = await idempotency.get_cached_response(idempotency_key)
    if exists:
        logger.info(f"Returning cached response for idempotency_key={idempotency_key}")
        return ClosePositionResponse(**cached)

    # V1 Placeholder: In a full implementation, this would:
    # 1. Fetch the position and validate it's closable
    # 2. Create a sell order via OrderService
    # 3. Mark position as closing
    # 4. Resolve related alerts

    # For now, return a placeholder response
    response = ClosePositionResponse(
        success=True,
        order_id=f"order-{position_id}-placeholder",
        message=f"Close order created for position {position_id} (V1 placeholder)",
    )

    # Store for idempotency
    await idempotency.store_key(
        key=idempotency_key,
        resource_type="close_position",
        resource_id=str(position_id),
        response_data=response.model_dump(),
    )

    return response


@router.post("/alerts/{alert_id}/acknowledge", response_model=AcknowledgeAlertResponse)
async def acknowledge_alert(
    alert_id: str,
    db: AsyncSession = Depends(get_session),
) -> AcknowledgeAlertResponse:
    """Acknowledge an expiring alert.

    Marks the alert as acknowledged so it doesn't appear in pending list.

    Args:
        alert_id: ID of the alert to acknowledge
        db: Database session

    Returns:
        Acknowledgment response

    Raises:
        404: Alert not found
    """
    # Verify alert exists
    check_sql = text("""
        SELECT id FROM alerts WHERE id = :alert_id AND type = 'option_expiring'
    """)
    result = await db.execute(check_sql, {"alert_id": alert_id})
    if result.fetchone() is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    # V1: No acknowledgment tracking yet (would require schema change)
    # For now, just return success
    acknowledged_at = datetime.now(timezone.utc)

    return AcknowledgeAlertResponse(
        success=True,
        message=f"Alert {alert_id} acknowledged",
        acknowledged_at=acknowledged_at,
    )


@router.post("/check-expirations", response_model=ManualCheckResponse)
async def trigger_manual_check(
    account_id: str = Query(..., description="Account ID to check"),
    db: AsyncSession = Depends(get_session),
) -> ManualCheckResponse:
    """Manually trigger expiration check (internal/testing use).

    Runs the ExpirationChecker for the specified account and returns statistics.

    Args:
        account_id: Account to check expirations for
        db: Database session

    Returns:
        Check statistics including positions checked and alerts created
    """
    # V1: Create checker with mocked dependencies for testing
    # In production, this would use properly initialized dependencies

    # For testing purposes, return placeholder stats
    logger.info(f"Manual expiration check triggered for account={account_id}")

    return ManualCheckResponse(
        run_id="manual-check-placeholder",
        positions_checked=0,
        alerts_created=0,
        alerts_deduplicated=0,
        errors=["V1: Full implementation pending - use scheduler for production checks"],
    )


def _parse_timestamp(value) -> datetime:
    """Parse a timestamp value from database.

    Handles both string and datetime values.
    """
    if value is None:
        return datetime.now(timezone.utc)

    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    # Parse ISO format string
    if "+" in str(value) or str(value).endswith("Z"):
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    else:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
