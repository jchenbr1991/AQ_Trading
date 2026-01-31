# backend/src/api/routes/derivatives.py
"""Derivatives API routes for expiration monitoring and futures rolling.

This module provides FastAPI endpoints for derivative lifecycle management:
- GET /expiring - List expiring positions using default warning window
- GET /expiring/{days} - List positions expiring within N days
- POST /roll/{symbol} - Generate roll plan for a futures position

Acceptance Criteria:
- SC-011: User receives expiration warning at least 5 days before expiry
- FR-016: System tracks derivative expiry dates
- FR-017: System supports futures auto-roll
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.derivatives.expiration_manager import ExpirationManager
from src.derivatives.futures_roll import FuturesRollManager
from src.models.derivative_contract import ContractType, DerivativeContract, PutCall
from src.schemas.derivatives import (
    ExpirationAlertResponse,
    ExpiringPositionsResponse,
    RollPlanResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/derivatives", tags=["derivatives"])

# Default warning window per SC-011
DEFAULT_WARNING_DAYS = 5


def _coerce_contract_type(value: ContractType | str) -> ContractType:
    """Coerce contract_type to enum, handling string values from SQLite."""
    if isinstance(value, ContractType):
        return value
    return ContractType(value)


def _coerce_put_call(value: PutCall | str | None) -> PutCall | None:
    """Coerce put_call to enum, handling string values from SQLite."""
    if value is None:
        return None
    if isinstance(value, PutCall):
        return value
    return PutCall(value)


async def get_expiration_manager(
    session: AsyncSession = Depends(get_session),
) -> ExpirationManager:
    """Dependency to create ExpirationManager with session."""
    return ExpirationManager(session=session, warning_days=DEFAULT_WARNING_DAYS)


async def get_futures_roll_manager(
    session: AsyncSession = Depends(get_session),
) -> FuturesRollManager:
    """Dependency to create FuturesRollManager with session."""
    return FuturesRollManager(session=session, default_days_before=DEFAULT_WARNING_DAYS)


@router.get("/expiring", response_model=ExpiringPositionsResponse)
async def get_expiring_positions(
    manager: ExpirationManager = Depends(get_expiration_manager),
) -> ExpiringPositionsResponse:
    """List derivative positions expiring within the default warning window.

    Returns positions expiring within DEFAULT_WARNING_DAYS (5 days per SC-011).

    Returns:
        ExpiringPositionsResponse containing list of expiring positions

    Example:
        GET /api/derivatives/expiring
        Returns positions expiring within 5 days
    """
    logger.info("Fetching expiring positions with default window (%d days)", DEFAULT_WARNING_DAYS)

    # Get positions directly to avoid enum coercion issues in check_expirations
    positions_db = await manager.get_expiring_positions()
    today = date.today()

    positions = [
        ExpirationAlertResponse(
            symbol=p.symbol,
            underlying=p.underlying,
            expiry=p.expiry,
            days_to_expiry=(p.expiry - today).days,
            contract_type=_coerce_contract_type(p.contract_type),
            put_call=_coerce_put_call(p.put_call),
            strike=p.strike,
        )
        for p in positions_db
    ]

    return ExpiringPositionsResponse(
        positions=positions,
        total=len(positions),
        warning_days=DEFAULT_WARNING_DAYS,
    )


@router.get("/expiring/{days}", response_model=ExpiringPositionsResponse)
async def get_expiring_positions_within_days(
    days: int = Path(..., ge=0, le=365, description="Number of days to look ahead"),
    manager: ExpirationManager = Depends(get_expiration_manager),
) -> ExpiringPositionsResponse:
    """List derivative positions expiring within N days.

    Args:
        days: Number of days to look ahead (0-365)

    Returns:
        ExpiringPositionsResponse containing list of expiring positions

    Example:
        GET /api/derivatives/expiring/7
        Returns positions expiring within 7 days
    """
    logger.info("Fetching expiring positions within %d days", days)

    # Get positions with custom days window
    positions_db = await manager.get_expiring_positions(days=days)
    today = date.today()

    positions = [
        ExpirationAlertResponse(
            symbol=p.symbol,
            underlying=p.underlying,
            expiry=p.expiry,
            days_to_expiry=(p.expiry - today).days,
            contract_type=_coerce_contract_type(p.contract_type),
            put_call=_coerce_put_call(p.put_call),
            strike=p.strike,
        )
        for p in positions_db
    ]

    return ExpiringPositionsResponse(
        positions=positions,
        total=len(positions),
        warning_days=days,
    )


@router.post("/roll/{symbol}", response_model=RollPlanResponse)
async def generate_roll_plan(
    symbol: str = Path(..., description="The futures contract symbol to roll"),
    session: AsyncSession = Depends(get_session),
    manager: FuturesRollManager = Depends(get_futures_roll_manager),
) -> RollPlanResponse:
    """Generate a roll plan for a futures position.

    This endpoint generates instructions for rolling a futures position
    but does NOT execute any trades. Use the returned plan to manually
    or programmatically execute the roll.

    Args:
        symbol: The futures contract symbol to roll (e.g., ESH24)

    Returns:
        RollPlanResponse containing the roll instructions

    Raises:
        404: If the futures contract is not found
        400: If the contract is not a futures contract

    Example:
        POST /api/derivatives/roll/ESH24
        Returns roll plan with close and open instructions
    """
    logger.info("Generating roll plan for symbol: %s", symbol)

    # Query the contract by symbol
    stmt = select(DerivativeContract).where(DerivativeContract.symbol == symbol)
    result = await session.execute(stmt)
    contract = result.scalar_one_or_none()

    if contract is None:
        logger.warning("Contract not found: %s", symbol)
        raise HTTPException(
            status_code=404,
            detail=f"Futures contract '{symbol}' not found",
        )

    contract_type = _coerce_contract_type(contract.contract_type)
    if contract_type != ContractType.FUTURE:
        logger.warning(
            "Cannot roll non-futures contract: %s (type=%s)",
            symbol,
            contract_type.value,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Contract '{symbol}' is not a futures contract (type={contract_type.value})",
        )

    # Ensure contract has proper enum types for the roll manager
    # This handles SQLite returning strings instead of enums
    contract.contract_type = contract_type
    contract.put_call = _coerce_put_call(contract.put_call)

    # Generate the roll plan
    plan = manager.generate_roll_plan(contract)

    return RollPlanResponse(
        symbol=plan.symbol,
        strategy=plan.strategy.value,
        close_action=plan.close_action,
        open_action=plan.open_action,
    )
