"""Pydantic models for options API endpoints.

Defines request/response schemas for:
- GET /api/options/expiring
- POST /api/options/{position_id}/close
- POST /api/options/{position_id}/acknowledge
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class AlertSummary(BaseModel):
    """Summary counts by severity."""

    critical_count: int
    warning_count: int
    info_count: int


class ExpiringAlertRow(BaseModel):
    """Single expiring alert with position details.

    This is the primary row type for the expiring alerts list.
    Note: Same position may have multiple alerts (one per threshold).
    """

    # Alert info (primary key)
    alert_id: str
    severity: Literal["critical", "warning", "info"]
    threshold_days: int
    created_at: datetime
    acknowledged: bool
    acknowledged_at: datetime | None = None

    # Position info
    position_id: int
    symbol: str
    strike: float
    put_call: Literal["put", "call"]
    expiry_date: str
    quantity: int

    # Expiration info
    days_to_expiry: int

    # Valuation (optional)
    current_price: float | None = None
    market_value: float | None = None
    unrealized_pnl: float | None = None

    # Operability
    is_closable: bool

    model_config = ConfigDict(from_attributes=True)


class ExpiringAlertsResponse(BaseModel):
    """Response for GET /api/options/expiring."""

    alerts: list[ExpiringAlertRow]
    total: int
    summary: AlertSummary


class ClosePositionRequest(BaseModel):
    """Request body for POST /api/options/{position_id}/close."""

    reason: str | None = None


class ClosePositionResponse(BaseModel):
    """Response for POST /api/options/{position_id}/close."""

    success: bool
    order_id: str | None = None
    message: str


class AcknowledgeAlertRequest(BaseModel):
    """Request body for POST /api/options/alerts/{alert_id}/acknowledge."""

    pass  # No body required, but defined for consistency


class AcknowledgeAlertResponse(BaseModel):
    """Response for POST /api/options/alerts/{alert_id}/acknowledge."""

    success: bool
    message: str
    acknowledged_at: datetime | None = None


class ManualCheckResponse(BaseModel):
    """Response for POST /api/options/check-expirations."""

    run_id: str
    positions_checked: int
    alerts_created: int
    alerts_deduplicated: int
    errors: list[str]
