# backend/src/api/risk.py
"""Risk API endpoints for trading state management."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.risk.state import TradingStateManager

# Singleton state manager instance
_state_manager: TradingStateManager | None = None


def get_state_manager() -> TradingStateManager:
    """Get the singleton TradingStateManager instance.

    Returns:
        TradingStateManager instance
    """
    global _state_manager
    if _state_manager is None:
        _state_manager = TradingStateManager()
    return _state_manager


def reset_state_manager() -> None:
    """Reset the state manager for testing.

    Creates a fresh TradingStateManager instance.
    """
    global _state_manager
    _state_manager = TradingStateManager()


# Request/Response schemas
class HaltRequest(BaseModel):
    """Request body for halt endpoint."""

    reason: str


class PauseRequest(BaseModel):
    """Request body for pause endpoint (optional)."""

    reason: str | None = None


class StateResponse(BaseModel):
    """Response for state endpoint."""

    state: str
    since: datetime
    changed_by: str
    reason: str | None
    can_resume: bool


class ActionResponse(BaseModel):
    """Response for action endpoints (halt, pause, resume, enable-resume)."""

    success: bool
    state: str


class KillSwitchActionsExecuted(BaseModel):
    """Details of actions executed by kill switch."""

    halted: bool
    orders_cancelled: int
    positions_flattened: int
    flatten_orders: list[str]


class KillSwitchResult(BaseModel):
    """Response for kill-switch compound endpoint."""

    success: bool
    state: str
    actions_executed: KillSwitchActionsExecuted
    errors: list[str]
    timestamp: datetime
    triggered_by: str


# Router
router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/state", response_model=StateResponse)
async def get_state() -> StateResponse:
    """Get the current trading state.

    Returns:
        Current trading state with metadata
    """
    manager = get_state_manager()
    state = manager.get_state()

    return StateResponse(
        state=state.state.value,
        since=state.since,
        changed_by=state.changed_by,
        reason=state.reason,
        can_resume=state.can_resume,
    )


@router.post("/halt", response_model=ActionResponse)
async def halt(request: HaltRequest) -> ActionResponse:
    """Halt trading - emergency stop.

    Requires a reason. Resume is not allowed until enable_resume is called.

    Args:
        request: HaltRequest with reason

    Returns:
        Action result with new state
    """
    manager = get_state_manager()
    manager.halt(changed_by="api", reason=request.reason)

    return ActionResponse(
        success=True,
        state=manager.get_state().state.value,
    )


@router.post("/pause", response_model=ActionResponse)
async def pause(request: PauseRequest | None = None) -> ActionResponse:
    """Pause trading - temporary stop.

    Optionally accepts a reason. Close operations are still allowed.

    Args:
        request: Optional PauseRequest with reason

    Returns:
        Action result with new state
    """
    manager = get_state_manager()
    reason = request.reason if request else None
    manager.pause(changed_by="api", reason=reason)

    return ActionResponse(
        success=True,
        state=manager.get_state().state.value,
    )


@router.post("/resume", response_model=ActionResponse)
async def resume() -> ActionResponse:
    """Resume trading to RUNNING state.

    Only succeeds if can_resume is True. Returns 400 error if cannot resume.

    Returns:
        Action result with new state

    Raises:
        HTTPException: 400 if cannot resume (HALTED without enable_resume)
    """
    manager = get_state_manager()
    success = manager.resume(changed_by="api")

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Cannot resume: trading is halted and resume has not been enabled",
        )

    return ActionResponse(
        success=True,
        state=manager.get_state().state.value,
    )


@router.post("/enable-resume", response_model=ActionResponse)
async def enable_resume() -> ActionResponse:
    """Enable resume for HALTED state.

    Only affects HALTED state. Has no effect on other states.

    Returns:
        Action result with current state
    """
    manager = get_state_manager()
    manager.enable_resume(changed_by="api")

    return ActionResponse(
        success=True,
        state=manager.get_state().state.value,
    )


@router.post("/kill-switch", response_model=KillSwitchResult)
async def kill_switch() -> KillSwitchResult:
    """Emergency kill switch - compound action.

    Performs the following actions:
    1. HALTs trading (sets state to HALTED, can_resume=False)
    2. Cancels all orders (TODO: wire to OrderManager - Phase 1: mocked)
    3. Flattens all positions (TODO: wire to OrderManager - Phase 1: mocked)

    Returns:
        Kill switch result with actions executed and any errors
    """
    manager = get_state_manager()
    errors: list[str] = []

    # Step 1: HALT trading
    manager.halt(changed_by="api", reason="Kill switch activated")

    # Step 2: Cancel all orders (Phase 1: mocked - TODO: wire to OrderManager)
    orders_cancelled = 0

    # Step 3: Flatten all positions (Phase 1: mocked - TODO: wire to OrderManager)
    positions_flattened = 0
    flatten_orders: list[str] = []

    return KillSwitchResult(
        success=True,
        state=manager.get_state().state.value,
        actions_executed=KillSwitchActionsExecuted(
            halted=True,
            orders_cancelled=orders_cancelled,
            positions_flattened=positions_flattened,
            flatten_orders=flatten_orders,
        ),
        errors=errors,
        timestamp=datetime.now(timezone.utc),
        triggered_by="api",
    )
