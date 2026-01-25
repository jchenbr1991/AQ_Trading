# backend/src/api/reconciliation.py
"""Reconciliation API endpoints for alert management."""

from collections import deque
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

# Type aliases
Severity = Literal["info", "warning", "critical"]

# In-memory storage for recent alerts (last 10)
_recent_alerts: deque[dict] = deque(maxlen=10)


class ReconciliationAlert(BaseModel):
    """Response model for reconciliation alerts."""

    timestamp: str
    severity: Severity
    type: str
    symbol: str | None
    local_value: str | None
    broker_value: str | None
    message: str


def add_alert(
    severity: Severity,
    alert_type: str,
    symbol: str | None,
    local_value: str | None,
    broker_value: str | None,
    message: str,
) -> None:
    """Add a reconciliation alert.

    Args:
        severity: Alert severity (info, warning, critical)
        alert_type: Type of alert (MISSING_LOCAL, CASH_MISMATCH, etc.)
        symbol: Symbol affected (if applicable)
        local_value: Local/expected value
        broker_value: Broker/actual value
        message: Human-readable alert message
    """
    alert = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "severity": severity,
        "type": alert_type,
        "symbol": symbol,
        "local_value": local_value,
        "broker_value": broker_value,
        "message": message,
    }
    _recent_alerts.append(alert)


def clear_alerts() -> None:
    """Clear all alerts. Used for testing."""
    _recent_alerts.clear()


def reset_alerts() -> None:
    """Reset alerts to initial mock state for frontend development.

    Creates 3 mock alerts for testing the UI.
    """
    clear_alerts()
    _init_mock_alerts()


def _init_mock_alerts() -> None:
    """Initialize with mock alerts for frontend development."""
    add_alert(
        severity="critical",
        alert_type="MISSING_LOCAL",
        symbol="TSLA",
        local_value=None,
        broker_value="50",
        message="Broker has 50 shares we don't track",
    )
    add_alert(
        severity="warning",
        alert_type="QUANTITY_MISMATCH",
        symbol="AAPL",
        local_value="100",
        broker_value="95",
        message="Position quantity mismatch: expected 100, broker shows 95",
    )
    add_alert(
        severity="info",
        alert_type="RECONCILIATION_PASSED",
        symbol=None,
        local_value=None,
        broker_value=None,
        message="Daily reconciliation completed successfully",
    )


# Initialize mock data on module load
_init_mock_alerts()


# Router
router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


@router.get("/recent", response_model=list[ReconciliationAlert])
async def get_recent_alerts() -> list[dict]:
    """Get the last 10 reconciliation alerts.

    Returns:
        List of recent alerts, newest first
    """
    # Return alerts in reverse order (newest first)
    return list(reversed(_recent_alerts))
