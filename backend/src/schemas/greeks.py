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


# =============================================================================
# V2 Schemas: Scenario Shock API
# =============================================================================


class CurrentGreeksResponse(BaseModel):
    """Current Greeks snapshot for scenario response."""

    model_config = ConfigDict(from_attributes=True)

    dollar_delta: float
    gamma_dollar: float
    gamma_pnl_1pct: float
    vega_per_1pct: float
    theta_per_day: float


class ScenarioResultResponse(BaseModel):
    """Single scenario result."""

    model_config = ConfigDict(from_attributes=True)

    shock_pct: float
    direction: Literal["up", "down"]
    pnl_from_delta: float
    pnl_from_gamma: float
    pnl_impact: float
    delta_change: float
    new_dollar_delta: float
    breach_level: Literal["none", "warn", "crit", "hard"]
    breach_dims: list[str]


class ScenarioShockApiResponse(BaseModel):
    """Response for GET /scenario endpoint."""

    model_config = ConfigDict(from_attributes=True)

    account_id: str
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str | None
    asof_ts: datetime
    current: CurrentGreeksResponse
    scenarios: dict[str, ScenarioResultResponse]


# =============================================================================
# V2 Schemas: Limits API
# =============================================================================


class ThresholdLevelsRequest(BaseModel):
    """Threshold levels for a single Greek."""

    warn: float
    crit: float
    hard: float


class GreeksLimitSetRequest(BaseModel):
    """Limit set for PUT /limits request."""

    dollar_delta: ThresholdLevelsRequest
    gamma_dollar: ThresholdLevelsRequest
    vega_per_1pct: ThresholdLevelsRequest
    theta_per_day: ThresholdLevelsRequest


class GreeksLimitsApiRequest(BaseModel):
    """Request body for PUT /limits."""

    strategy_id: str | None = None
    limits: GreeksLimitSetRequest


class GreeksLimitsApiResponse(BaseModel):
    """Response for PUT /limits endpoint."""

    model_config = ConfigDict(from_attributes=True)

    account_id: str
    strategy_id: str | None
    limits: GreeksLimitSetRequest
    updated_at: datetime
    updated_by: str
    effective_scope: Literal["ACCOUNT", "STRATEGY"]


# =============================================================================
# V2 Schemas: History API
# =============================================================================


class GreeksHistoryPointResponse(BaseModel):
    """Single point in Greeks history."""

    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    dollar_delta: float
    gamma_dollar: float
    vega_per_1pct: float
    theta_per_day: float
    coverage_pct: float
    point_count: int = 1


class GreeksHistoryApiResponse(BaseModel):
    """Response for GET /history endpoint."""

    model_config = ConfigDict(from_attributes=True)

    account_id: str
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str | None
    window: str
    interval: str
    start_ts: datetime
    end_ts: datetime
    points: list[GreeksHistoryPointResponse]
