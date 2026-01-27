"""Schemas for close position API (Phase 1).

Defines request/response models for the new close_position implementation
that uses CloseRequest + OutboxEvent pattern.
"""

from pydantic import BaseModel


class ClosePositionRequestV2(BaseModel):
    """Request to close a position (Phase 1).

    No body required - idempotency key is in header.
    Reason field is optional for tracking.
    """

    reason: str | None = None


class ClosePositionResponseV2(BaseModel):
    """Response from close position endpoint (Phase 1).

    Returns CloseRequest details for client polling.
    """

    close_request_id: str
    position_id: int
    position_status: str
    close_request_status: str
    target_qty: int
    filled_qty: int = 0
    orders: list[str] = []
    poll_url: str | None = None
    poll_interval_ms: int = 1000
