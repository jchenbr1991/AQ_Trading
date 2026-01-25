# backend/src/api/orders.py
"""Orders API endpoints for position management."""

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, model_validator

from src.api.risk import get_state_manager


# Request/Response schemas
class ClosePositionRequest(BaseModel):
    """Request body for close position endpoint."""

    symbol: str
    quantity: int | Literal["all"]
    order_type: Literal["market", "limit"]
    time_in_force: Literal["GTC", "DAY", "IOC"]
    limit_price: float | None = None

    @model_validator(mode="after")
    def validate_limit_price(self) -> "ClosePositionRequest":
        """Validate limit_price is provided for limit orders."""
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for limit orders")
        return self


class ClosePositionResponse(BaseModel):
    """Response for close position endpoint."""

    success: bool
    order_id: str
    message: str


# Router
router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("/close", response_model=ClosePositionResponse)
async def close_position(request: ClosePositionRequest) -> ClosePositionResponse:
    """Close a single position.

    Submits an order to close (sell) a position. For Phase 1, order submission
    is mocked and returns a fake order_id.

    Args:
        request: ClosePositionRequest with symbol, quantity, order_type, etc.

    Returns:
        ClosePositionResponse with success status and order_id

    Raises:
        HTTPException: 400 if trading is HALTED
    """
    # Check trading state - closing is allowed in RUNNING or PAUSED
    state_manager = get_state_manager()
    if not state_manager.is_close_allowed():
        raise HTTPException(
            status_code=400,
            detail="Cannot close position: trading is halted",
        )

    # Phase 1: Mock order submission - generate a fake order_id
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    return ClosePositionResponse(
        success=True,
        order_id=order_id,
        message=f"Close order submitted for {request.symbol}",
    )
