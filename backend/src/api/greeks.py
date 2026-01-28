# backend/src/api/greeks.py
"""Greeks API endpoints for monitoring and alerts."""

from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.greeks.aggregator import GreeksAggregator
from src.greeks.calculator import GreeksCalculator
from src.greeks.models import AggregatedGreeks, PositionGreeks, RiskMetric
from src.greeks.monitor import load_positions_from_db
from src.greeks.repository import GreeksRepository
from src.schemas.greeks import (
    AggregatedGreeksResponse,
    AlertAcknowledgeRequest,
    GreeksAlertResponse,
    GreeksOverviewResponse,
    PositionGreeksResponse,
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
            _position_greeks_to_response(pg) for pg, _ in contributors
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

    Stub implementation - will be integrated with monitoring loop later.
    Accepts connection and sends periodic updates.

    Args:
        websocket: The WebSocket connection.
        account_id: The account identifier.
    """
    await websocket.accept()
    try:
        while True:
            # Stub: receive messages but don't process
            data = await websocket.receive_text()
            await websocket.send_json({"status": "received", "message": data})
    except WebSocketDisconnect:
        pass
