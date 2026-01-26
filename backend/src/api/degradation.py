# backend/src/api/degradation.py
"""Degradation API endpoints for system status and control.

This module provides endpoints to:
- Get current system degradation status
- Force override the system mode (for manual intervention)
- Get trading permissions for each action type
"""

from enum import Enum

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.degradation.models import ActionType, SystemMode
from src.degradation.setup import get_system_state, get_trading_gate

# Request/Response schemas


class SystemModeEnum(str, Enum):
    """Valid system modes for API requests."""

    NORMAL = "normal"
    DEGRADED = "degraded"
    SAFE_MODE = "safe_mode"
    SAFE_MODE_DISCONNECTED = "safe_mode_disconnected"
    HALT = "halt"
    RECOVERING = "recovering"


class SystemStatusResponse(BaseModel):
    """Response model for system status."""

    mode: str
    stage: str | None
    is_override: bool


class ForceOverrideRequest(BaseModel):
    """Request model for forcing system mode."""

    mode: SystemModeEnum
    ttl_seconds: int = Field(..., gt=0, description="TTL must be positive")
    operator_id: str = Field(..., min_length=1, description="Operator ID required")
    reason: str = Field(..., min_length=1, description="Reason required")

    @field_validator("operator_id", "reason")
    @classmethod
    def validate_not_whitespace_only(cls, v: str) -> str:
        """Validate that the string is not just whitespace."""
        if not v.strip():
            raise ValueError("Value cannot be only whitespace")
        return v


class ForceOverrideResponse(BaseModel):
    """Response model for force override operation."""

    success: bool
    mode: str
    ttl_seconds: int
    operator_id: str


class PermissionInfo(BaseModel):
    """Permission info for a single action type."""

    allowed: bool
    restricted: bool = False
    warning: str | None = None
    local_only: bool = False


class TradingPermissionsResponse(BaseModel):
    """Response model for trading permissions."""

    mode: str
    stage: str | None
    permissions: dict[str, PermissionInfo]


# Router
router = APIRouter(prefix="/api/degradation", tags=["degradation"])


@router.get("/status", response_model=SystemStatusResponse)
async def get_status() -> SystemStatusResponse:
    """Get current system degradation status.

    Returns the current system mode, recovery stage (if recovering),
    and whether a force override is active.

    Returns:
        SystemStatusResponse with mode, stage, and override status

    Raises:
        HTTPException: 503 if degradation service is not initialized
    """
    state = get_system_state()
    if state is None:
        raise HTTPException(status_code=503, detail="Degradation service not initialized")

    return SystemStatusResponse(
        mode=state.mode.value,
        stage=state.stage.value if state.stage else None,
        is_override=state.is_force_override,
    )


@router.post("/force", response_model=ForceOverrideResponse)
async def force_override(request: ForceOverrideRequest) -> ForceOverrideResponse:
    """Force the system into a specific mode.

    This is for manual intervention when the system needs human control.
    The override is temporary and will expire after the specified TTL.

    Args:
        request: ForceOverrideRequest with mode, TTL, operator ID, and reason

    Returns:
        ForceOverrideResponse confirming the operation

    Raises:
        HTTPException: 503 if degradation service is not initialized
    """
    state = get_system_state()
    if state is None:
        raise HTTPException(status_code=503, detail="Degradation service not initialized")

    # Convert API mode enum to internal SystemMode enum
    target_mode = SystemMode(request.mode.value)

    await state.force_mode(
        mode=target_mode,
        ttl_seconds=request.ttl_seconds,
        operator_id=request.operator_id,
        reason=request.reason,
    )

    return ForceOverrideResponse(
        success=True,
        mode=state.mode.value,
        ttl_seconds=request.ttl_seconds,
        operator_id=request.operator_id,
    )


@router.get("/permissions", response_model=TradingPermissionsResponse)
async def get_permissions() -> TradingPermissionsResponse:
    """Get current trading permissions for all action types.

    Returns permissions for each trading action (open, send, amend,
    cancel, reduce_only, query) based on the current system mode
    and recovery stage.

    Returns:
        TradingPermissionsResponse with mode, stage, and permission details

    Raises:
        HTTPException: 503 if degradation service is not initialized
    """
    gate = get_trading_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="Degradation service not initialized")

    # Get permissions for each action type
    permissions: dict[str, PermissionInfo] = {}
    for action in ActionType:
        result = gate.check_permission(action)
        permissions[action.value] = PermissionInfo(
            allowed=result.allowed,
            restricted=result.restricted,
            warning=result.warning,
            local_only=result.local_only,
        )

    return TradingPermissionsResponse(
        mode=gate.mode.value,
        stage=gate.stage.value if gate.stage else None,
        permissions=permissions,
    )
