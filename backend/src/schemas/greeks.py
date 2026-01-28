# backend/src/schemas/greeks.py
"""Pydantic response schemas for Greeks API endpoints."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PositionGreeksResponse(BaseModel):
    """Response schema for a single position's Greeks."""

    model_config = ConfigDict(from_attributes=True)

    position_id: int
    symbol: str
    underlying_symbol: str
    quantity: int
    dollar_delta: float
    gamma_dollar: float
    gamma_pnl_1pct: float
    vega_per_1pct: float
    theta_per_day: float
    notional: float
    valid: bool
    source: str
    as_of_ts: datetime


class AggregatedGreeksResponse(BaseModel):
    """Response schema for aggregated Greeks."""

    model_config = ConfigDict(from_attributes=True)

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    strategy_id: str | None

    # Dollar Greeks
    dollar_delta: float
    gamma_dollar: float
    gamma_pnl_1pct: float
    vega_per_1pct: float
    theta_per_day: float

    # Coverage
    coverage_pct: float
    is_coverage_sufficient: bool
    has_high_risk_missing_legs: bool
    valid_legs_count: int
    total_legs_count: int

    # Timing
    staleness_seconds: int
    as_of_ts: datetime


class GreeksAlertResponse(BaseModel):
    """Response schema for a Greeks alert."""

    model_config = ConfigDict(from_attributes=True)

    alert_id: str
    alert_type: str
    scope: str
    scope_id: str
    metric: str
    level: str
    current_value: float
    threshold_value: float | None
    message: str
    created_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: str | None


class GreeksOverviewResponse(BaseModel):
    """Full overview response with account, strategies, and alerts."""

    account: AggregatedGreeksResponse
    strategies: dict[str, AggregatedGreeksResponse]
    alerts: list[GreeksAlertResponse]
    top_contributors: dict[str, list[PositionGreeksResponse]]  # metric -> positions


class AlertAcknowledgeRequest(BaseModel):
    """Request to acknowledge an alert."""

    acknowledged_by: str
