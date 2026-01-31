# backend/src/api/greeks.py
"""Greeks API endpoints for monitoring and alerts."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from src.db.database import get_session
from src.greeks.aggregator import GreeksAggregator
from src.greeks.calculator import GreeksCalculator
from src.greeks.limits_store import NotImplementedError, get_limits_store
from src.greeks.models import AggregatedGreeks, PositionGreeks, RiskMetric
from src.greeks.monitor import load_positions_from_db
from src.greeks.repository import GreeksRepository
from src.greeks.scenario import get_scenario_shocks
from src.greeks.v2_models import CurrentGreeks, GreeksLimitSet, ThresholdLevels
from src.greeks.websocket import greeks_ws_manager
from src.schemas.greeks import (
    AggregatedGreeksResponse,
    AlertAcknowledgeRequest,
    CurrentGreeksResponse,
    GreeksAlertResponse,
    GreeksHistoryApiResponse,
    GreeksHistoryPointResponse,
    GreeksLimitsApiRequest,
    GreeksLimitsApiResponse,
    GreeksOverviewResponse,
    PositionGreeksResponse,
    ScenarioResultResponse,
    ScenarioShockApiResponse,
)

router = APIRouter(prefix="/api/greeks", tags=["greeks"])


def _aggregated_to_response(greeks: AggregatedGreeks) -> AggregatedGreeksResponse:
    """Convert AggregatedGreeks dataclass to API response.

    Args:
        greeks: The AggregatedGreeks dataclass to convert.

    Returns:
        AggregatedGreeksResponse suitable for API serialization.
    """
    return AggregatedGreeksResponse(
        scope=greeks.scope,
        scope_id=greeks.scope_id,
        strategy_id=greeks.strategy_id,
        dollar_delta=float(greeks.dollar_delta),
        gamma_dollar=float(greeks.gamma_dollar),
        gamma_pnl_1pct=float(greeks.gamma_pnl_1pct),
        vega_per_1pct=float(greeks.vega_per_1pct),
        theta_per_day=float(greeks.theta_per_day),
        coverage_pct=float(greeks.coverage_pct),
        is_coverage_sufficient=greeks.is_coverage_sufficient,
        has_high_risk_missing_legs=greeks.has_high_risk_missing_legs,
        valid_legs_count=greeks.valid_legs_count,
        total_legs_count=greeks.total_legs_count,
        staleness_seconds=greeks.staleness_seconds,
        as_of_ts=greeks.as_of_ts,
    )


def _position_greeks_to_response(pg: PositionGreeks) -> PositionGreeksResponse:
    """Convert PositionGreeks dataclass to API response.

    Args:
        pg: The PositionGreeks dataclass to convert.

    Returns:
        PositionGreeksResponse suitable for API serialization.
    """
    return PositionGreeksResponse(
        position_id=pg.position_id,
        symbol=pg.symbol,
        underlying_symbol=pg.underlying_symbol,
        quantity=pg.quantity,
        dollar_delta=float(pg.dollar_delta),
        gamma_dollar=float(pg.gamma_dollar),
        gamma_pnl_1pct=float(pg.gamma_pnl_1pct),
        vega_per_1pct=float(pg.vega_per_1pct),
        theta_per_day=float(pg.theta_per_day),
        notional=float(pg.notional),
        valid=pg.valid,
        source=pg.source.value,
        as_of_ts=pg.as_of_ts,
    )


def _create_empty_aggregated_greeks(account_id: str) -> AggregatedGreeks:
    """Create an empty AggregatedGreeks for an account with no positions.

    Args:
        account_id: The account identifier.

    Returns:
        AggregatedGreeks with zero values and no positions.
    """
    return AggregatedGreeks(
        scope="ACCOUNT",
        scope_id=account_id,
        strategy_id=None,
        dollar_delta=Decimal("0"),
        gamma_dollar=Decimal("0"),
        gamma_pnl_1pct=Decimal("0"),
        vega_per_1pct=Decimal("0"),
        theta_per_day=Decimal("0"),
        valid_legs_count=0,
        total_legs_count=0,
        valid_notional=Decimal("0"),
        total_notional=Decimal("0"),
        has_positions=False,
        as_of_ts=datetime.now(timezone.utc),
    )


@router.get("/accounts/{account_id}", response_model=GreeksOverviewResponse)
async def get_greeks_overview(
    account_id: str,
    db: AsyncSession = Depends(get_session),
) -> GreeksOverviewResponse:
    """Get full Greeks overview for an account.

    Returns account-level Greeks, per-strategy breakdown, alerts, and top contributors.

    Args:
        account_id: The account identifier.
        db: Database session.

    Returns:
        GreeksOverviewResponse with full Greeks data.
    """
    repository = GreeksRepository(db)

    # Load positions from database
    positions = await load_positions_from_db(db, account_id)

    # If no positions, return empty overview
    if not positions:
        empty_greeks = _create_empty_aggregated_greeks(account_id)
        alerts = await repository.get_unacknowledged_alerts(scope="ACCOUNT", scope_id=account_id)
        alert_responses = [
            GreeksAlertResponse(
                alert_id=str(alert.alert_id),
                alert_type=alert.alert_type,
                scope=alert.scope,
                scope_id=alert.scope_id,
                metric=alert.metric,
                level=alert.level,
                current_value=float(alert.current_value),
                threshold_value=float(alert.threshold_value) if alert.threshold_value else None,
                message=alert.message,
                created_at=alert.created_at,
                acknowledged_at=alert.acknowledged_at,
                acknowledged_by=alert.acknowledged_by,
            )
            for alert in alerts
        ]
        return GreeksOverviewResponse(
            account=_aggregated_to_response(empty_greeks),
            strategies={},
            alerts=alert_responses,
            top_contributors={},
        )

    # Calculate Greeks using monitor
    calculator = GreeksCalculator()
    aggregator = GreeksAggregator()

    # Calculate position Greeks
    position_greeks = calculator.calculate(positions)

    # Aggregate to account and strategy levels
    account_greeks, strategy_greeks = aggregator.aggregate_by_strategy(position_greeks, account_id)

    # Get top contributors for each Greek metric
    top_contributors: dict[str, list[PositionGreeksResponse]] = {}
    for metric in [RiskMetric.DELTA, RiskMetric.GAMMA, RiskMetric.VEGA, RiskMetric.THETA]:
        contributors = aggregator.get_top_contributors(position_greeks, metric, top_n=5)
        top_contributors[metric.value] = [
            _position_greeks_to_response(c.position) for c in contributors
        ]

    # Get unacknowledged alerts
    alerts = await repository.get_unacknowledged_alerts(scope="ACCOUNT", scope_id=account_id)
    alert_responses = [
        GreeksAlertResponse(
            alert_id=str(alert.alert_id),
            alert_type=alert.alert_type,
            scope=alert.scope,
            scope_id=alert.scope_id,
            metric=alert.metric,
            level=alert.level,
            current_value=float(alert.current_value),
            threshold_value=float(alert.threshold_value) if alert.threshold_value else None,
            message=alert.message,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=alert.acknowledged_by,
        )
        for alert in alerts
    ]

    # Convert strategy Greeks to response format
    strategy_responses = {
        strategy_id: _aggregated_to_response(greeks)
        for strategy_id, greeks in strategy_greeks.items()
    }

    return GreeksOverviewResponse(
        account=_aggregated_to_response(account_greeks),
        strategies=strategy_responses,
        alerts=alert_responses,
        top_contributors=top_contributors,
    )


@router.get("/accounts/{account_id}/current", response_model=AggregatedGreeksResponse)
async def get_current_greeks(
    account_id: str,
    db: AsyncSession = Depends(get_session),
) -> AggregatedGreeksResponse:
    """Get current aggregated Greeks for an account.

    Args:
        account_id: The account identifier.
        db: Database session.

    Returns:
        AggregatedGreeksResponse with current Greeks data.
    """
    # Load positions from database
    positions = await load_positions_from_db(db, account_id)

    # If no positions, return empty Greeks
    if not positions:
        return _aggregated_to_response(_create_empty_aggregated_greeks(account_id))

    # Calculate Greeks
    calculator = GreeksCalculator()
    aggregator = GreeksAggregator()

    position_greeks = calculator.calculate(positions)
    account_greeks = aggregator.aggregate(position_greeks, scope="ACCOUNT", scope_id=account_id)

    return _aggregated_to_response(account_greeks)


@router.get("/accounts/{account_id}/alerts", response_model=list[GreeksAlertResponse])
async def get_greeks_alerts(
    account_id: str,
    acknowledged: bool | None = None,
    db: AsyncSession = Depends(get_session),
) -> list[GreeksAlertResponse]:
    """Get Greeks alerts for an account.

    Args:
        account_id: The account identifier.
        acknowledged: Optional filter - True for acknowledged only, False for unacknowledged only.
        db: Database session.

    Returns:
        List of GreeksAlertResponse for the account.
    """
    repository = GreeksRepository(db)

    if acknowledged is False or acknowledged is None:
        # Get unacknowledged alerts (default behavior)
        alerts = await repository.get_unacknowledged_alerts(scope="ACCOUNT", scope_id=account_id)
    else:
        # acknowledged is True - need to get all and filter
        # For now, we only have get_unacknowledged_alerts in repository
        # Return empty list for acknowledged=True until repository supports it
        alerts = []

    return [
        GreeksAlertResponse(
            alert_id=str(alert.alert_id),
            alert_type=alert.alert_type,
            scope=alert.scope,
            scope_id=alert.scope_id,
            metric=alert.metric,
            level=alert.level,
            current_value=float(alert.current_value),
            threshold_value=float(alert.threshold_value) if alert.threshold_value else None,
            message=alert.message,
            created_at=alert.created_at,
            acknowledged_at=alert.acknowledged_at,
            acknowledged_by=alert.acknowledged_by,
        )
        for alert in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge", response_model=GreeksAlertResponse)
async def acknowledge_alert(
    alert_id: str,
    request: AlertAcknowledgeRequest,
    db: AsyncSession = Depends(get_session),
) -> GreeksAlertResponse:
    """Acknowledge a Greeks alert.

    Args:
        alert_id: The UUID string of the alert to acknowledge.
        request: Request body with acknowledged_by field.
        db: Database session.

    Returns:
        GreeksAlertResponse with updated acknowledgment fields.

    Raises:
        HTTPException: 404 if alert not found.
    """
    repository = GreeksRepository(db)

    # Acknowledge the alert
    success = await repository.acknowledge_alert(alert_id, request.acknowledged_by)

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    # Fetch the updated alert record to return
    # We need to get the alert by ID - add a helper query
    from uuid import UUID

    from sqlalchemy import select

    from src.models.greeks import GreeksAlertRecord

    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Alert not found") from None

    stmt = select(GreeksAlertRecord).where(GreeksAlertRecord.alert_id == alert_uuid)
    result = await db.execute(stmt)
    alert = result.scalar_one_or_none()

    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")

    return GreeksAlertResponse(
        alert_id=str(alert.alert_id),
        alert_type=alert.alert_type,
        scope=alert.scope,
        scope_id=alert.scope_id,
        metric=alert.metric,
        level=alert.level,
        current_value=float(alert.current_value),
        threshold_value=float(alert.threshold_value) if alert.threshold_value else None,
        message=alert.message,
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        acknowledged_by=alert.acknowledged_by,
    )


@router.websocket("/accounts/{account_id}/ws")
async def greeks_websocket(
    websocket: WebSocket,
    account_id: str,
):
    """WebSocket for real-time Greeks updates.

    Connects client to receive real-time Greeks and alert updates.
    Messages are JSON with types: greeks_update, greeks_alert

    Args:
        websocket: The WebSocket connection.
        account_id: The account identifier.
    """
    await websocket.accept()
    await greeks_ws_manager.connect(account_id, websocket)

    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Echo back for ping/pong
            await websocket.send_json({"type": "pong", "received": data})
    except WebSocketDisconnect:
        await greeks_ws_manager.disconnect(account_id, websocket)


# =============================================================================
# V2 Endpoints
# =============================================================================


@router.get("/accounts/{account_id}/scenario", response_model=ScenarioShockApiResponse)
async def get_scenario_shock(
    account_id: str,
    shocks: str | None = Query(None, description="Comma-separated shock percentages (e.g., '1,2')"),
    scope: Literal["ACCOUNT", "STRATEGY"] = Query("ACCOUNT", description="Scope for scenario"),
    strategy_id: str | None = Query(None, description="Strategy ID (required if scope=STRATEGY)"),
    db: AsyncSession = Depends(get_session),
) -> ScenarioShockApiResponse:
    """Get scenario shock analysis for Greeks.

    V2 Feature: Scenario Shock API

    Returns PnL and delta projections for ±X% underlying price shocks.
    Default shocks are ±1% and ±2%.

    Args:
        account_id: Account identifier.
        shocks: Comma-separated shock percentages (default: "1,2").
        scope: ACCOUNT or STRATEGY.
        strategy_id: Required if scope=STRATEGY.
        db: Database session.

    Returns:
        ScenarioShockApiResponse with current Greeks and scenario results.

    Raises:
        HTTPException: 400 if scope=STRATEGY and strategy_id not provided.
        HTTPException: 404 if no positions found.
    """
    # Validate scope/strategy_id
    if scope == "STRATEGY" and not strategy_id:
        raise HTTPException(
            status_code=400,
            detail="strategy_id is required when scope=STRATEGY",
        )

    # Load positions
    positions = await load_positions_from_db(db, account_id)
    if not positions:
        raise HTTPException(status_code=404, detail="No positions found")

    # Calculate Greeks
    calculator = GreeksCalculator()
    aggregator = GreeksAggregator()

    position_greeks = calculator.calculate(positions)

    if scope == "STRATEGY":
        account_greeks, strategy_greeks = aggregator.aggregate_by_strategy(
            position_greeks, account_id
        )
        if strategy_id not in strategy_greeks:
            raise HTTPException(status_code=404, detail=f"Strategy {strategy_id} not found")
        greeks = strategy_greeks[strategy_id]
        scope_id = strategy_id
    else:
        greeks = aggregator.aggregate(position_greeks, scope="ACCOUNT", scope_id=account_id)
        scope_id = None

    # Parse shock percentages
    shock_pcts: list[Decimal] = []
    if shocks:
        for s in shocks.split(","):
            try:
                shock_pcts.append(Decimal(s.strip()))
            except (ValueError, ArithmeticError):
                continue  # Skip invalid shock values
    if not shock_pcts:
        shock_pcts = [Decimal("1"), Decimal("2")]

    # Convert to CurrentGreeks
    current = CurrentGreeks(
        dollar_delta=greeks.dollar_delta,
        gamma_dollar=greeks.gamma_dollar,
        gamma_pnl_1pct=greeks.gamma_pnl_1pct,
        vega_per_1pct=greeks.vega_per_1pct,
        theta_per_day=greeks.theta_per_day,
    )

    # Get account limits from store for breach detection
    limits_store = get_limits_store()
    account_limits = await limits_store.get_limits(account_id)
    limits = {
        "dollar_delta": account_limits.dollar_delta.hard,
        "gamma_dollar": account_limits.gamma_dollar.hard,
        "vega_per_1pct": account_limits.vega_per_1pct.hard,
        "theta_per_day": account_limits.theta_per_day.hard,
    }

    # Get scenario results
    scenarios = get_scenario_shocks(current=current, limits=limits, shock_pcts=shock_pcts)

    # Convert to response
    scenario_responses = {
        key: ScenarioResultResponse(
            shock_pct=float(result.shock_pct),
            direction=result.direction,
            pnl_from_delta=float(result.pnl_from_delta),
            pnl_from_gamma=float(result.pnl_from_gamma),
            pnl_impact=float(result.pnl_impact),
            delta_change=float(result.delta_change),
            new_dollar_delta=float(result.new_dollar_delta),
            breach_level=result.breach_level,
            breach_dims=result.breach_dims,
        )
        for key, result in scenarios.items()
    }

    return ScenarioShockApiResponse(
        account_id=account_id,
        scope=scope,
        scope_id=scope_id,
        asof_ts=greeks.as_of_ts,
        current=CurrentGreeksResponse(
            dollar_delta=float(current.dollar_delta),
            gamma_dollar=float(current.gamma_dollar),
            gamma_pnl_1pct=float(current.gamma_pnl_1pct),
            vega_per_1pct=float(current.vega_per_1pct),
            theta_per_day=float(current.theta_per_day),
        ),
        scenarios=scenario_responses,
    )


def _request_to_limit_set(request: GreeksLimitsApiRequest) -> GreeksLimitSet:
    """Convert API request to GreeksLimitSet."""
    return GreeksLimitSet(
        dollar_delta=ThresholdLevels(
            warn=Decimal(str(request.limits.dollar_delta.warn)),
            crit=Decimal(str(request.limits.dollar_delta.crit)),
            hard=Decimal(str(request.limits.dollar_delta.hard)),
        ),
        gamma_dollar=ThresholdLevels(
            warn=Decimal(str(request.limits.gamma_dollar.warn)),
            crit=Decimal(str(request.limits.gamma_dollar.crit)),
            hard=Decimal(str(request.limits.gamma_dollar.hard)),
        ),
        vega_per_1pct=ThresholdLevels(
            warn=Decimal(str(request.limits.vega_per_1pct.warn)),
            crit=Decimal(str(request.limits.vega_per_1pct.crit)),
            hard=Decimal(str(request.limits.vega_per_1pct.hard)),
        ),
        theta_per_day=ThresholdLevels(
            warn=Decimal(str(request.limits.theta_per_day.warn)),
            crit=Decimal(str(request.limits.theta_per_day.crit)),
            hard=Decimal(str(request.limits.theta_per_day.hard)),
        ),
    )


def _limit_set_to_response(limits: GreeksLimitSet) -> dict:
    """Convert GreeksLimitSet to response dict."""
    return {
        "dollar_delta": {
            "warn": float(limits.dollar_delta.warn),
            "crit": float(limits.dollar_delta.crit),
            "hard": float(limits.dollar_delta.hard),
        },
        "gamma_dollar": {
            "warn": float(limits.gamma_dollar.warn),
            "crit": float(limits.gamma_dollar.crit),
            "hard": float(limits.gamma_dollar.hard),
        },
        "vega_per_1pct": {
            "warn": float(limits.vega_per_1pct.warn),
            "crit": float(limits.vega_per_1pct.crit),
            "hard": float(limits.vega_per_1pct.hard),
        },
        "theta_per_day": {
            "warn": float(limits.theta_per_day.warn),
            "crit": float(limits.theta_per_day.crit),
            "hard": float(limits.theta_per_day.hard),
        },
    }


@router.put("/accounts/{account_id}/limits", response_model=GreeksLimitsApiResponse)
async def put_limits(
    account_id: str,
    request: GreeksLimitsApiRequest,
    x_user_id: str | None = Header(None, alias="X-User-ID"),
) -> GreeksLimitsApiResponse:
    """Update Greeks limits for an account.

    V2 Feature: PUT /limits

    Args:
        account_id: Account identifier.
        request: New limits configuration.
        x_user_id: User ID from header.

    Returns:
        GreeksLimitsApiResponse with applied limits.

    Raises:
        HTTPException: 400 if limits validation fails.
        HTTPException: 501 if strategy_id provided.
    """
    # Get user from header
    user_id = x_user_id or "unknown"

    # Check for strategy_id (not implemented)
    if request.strategy_id:
        raise HTTPException(
            status_code=501,
            detail="Strategy-level limits not implemented in V2",
        )

    # Convert request to domain model
    limit_set = _request_to_limit_set(request)

    # Store limits
    store = get_limits_store()
    try:
        result = await store.set_limits(
            account_id=account_id,
            limits=limit_set,
            updated_by=user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e)) from e

    return GreeksLimitsApiResponse(
        account_id=result.account_id,
        strategy_id=result.strategy_id,
        limits=_limit_set_to_response(result.limits),
        updated_at=result.updated_at,
        updated_by=result.updated_by,
        effective_scope=result.effective_scope,
    )


@router.get("/accounts/{account_id}/limits")
async def get_limits(account_id: str) -> dict:
    """Get current Greeks limits for an account.

    V2 Feature: GET /limits

    Args:
        account_id: Account identifier.

    Returns:
        Current limits configuration.
    """
    store = get_limits_store()
    limits = await store.get_limits(account_id)

    return {
        "account_id": account_id,
        "limits": _limit_set_to_response(limits),
    }


# Window to interval mapping for history aggregation
# interval_seconds: None = raw data, else aggregation bucket size
HISTORY_WINDOW_CONFIG = {
    "1h": {"interval_seconds": None, "interval_display": "30s"},
    "4h": {"interval_seconds": 60, "interval_display": "1m"},
    "1d": {"interval_seconds": 300, "interval_display": "5m"},
    "7d": {"interval_seconds": 3600, "interval_display": "1h"},
}


@router.get("/accounts/{account_id}/history", response_model=GreeksHistoryApiResponse)
async def get_history(
    account_id: str,
    window: str = Query(..., description="Time window: 1h, 4h, 1d, 7d"),
    scope: Literal["ACCOUNT", "STRATEGY"] = Query("ACCOUNT"),
    strategy_id: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
) -> GreeksHistoryApiResponse:
    """Get historical Greeks data.

    V2 Feature: GET /history

    Returns time-bucketed historical Greeks with automatic aggregation:
    - 1h: raw 30s data (~120 points)
    - 4h: 1min aggregation (~240 points)
    - 1d: 5min aggregation (~288 points)
    - 7d: 1h aggregation (~168 points)

    Args:
        account_id: Account identifier.
        window: Time window (1h, 4h, 1d, 7d).
        scope: ACCOUNT or STRATEGY.
        strategy_id: Required if scope=STRATEGY.
        db: Database session.

    Returns:
        GreeksHistoryApiResponse with aggregated history points.

    Raises:
        HTTPException: 400 if invalid window or missing strategy_id.
    """
    # Validate window
    if window not in HISTORY_WINDOW_CONFIG:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid window '{window}'. Valid: 1h, 4h, 1d, 7d",
        )

    # Validate scope/strategy_id
    if scope == "STRATEGY" and not strategy_id:
        raise HTTPException(
            status_code=400,
            detail="strategy_id is required when scope=STRATEGY",
        )

    config = HISTORY_WINDOW_CONFIG[window]
    interval_display = config["interval_display"]
    interval_seconds = config["interval_seconds"]

    # Calculate time range
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    window_hours = {"1h": 1, "4h": 4, "1d": 24, "7d": 168}
    start_ts = now - timedelta(hours=window_hours[window])

    # Get history from repository with aggregation
    repository = GreeksRepository(db)
    scope_id = strategy_id if scope == "STRATEGY" else account_id

    history_points = await repository.get_history(
        scope=scope,
        scope_id=scope_id,
        start_ts=start_ts,
        end_ts=now,
        interval_seconds=interval_seconds,
    )

    # Convert to response format
    points = [
        GreeksHistoryPointResponse(
            ts=point.ts,
            dollar_delta=float(point.dollar_delta),
            gamma_dollar=float(point.gamma_dollar),
            vega_per_1pct=float(point.vega_per_1pct),
            theta_per_day=float(point.theta_per_day),
            coverage_pct=float(point.coverage_pct),
            point_count=point.point_count,
        )
        for point in history_points
    ]

    return GreeksHistoryApiResponse(
        account_id=account_id,
        scope=scope,
        scope_id=scope_id if scope == "STRATEGY" else None,
        window=window,
        interval=interval_display,
        start_ts=start_ts,
        end_ts=now,
        points=points,
    )
