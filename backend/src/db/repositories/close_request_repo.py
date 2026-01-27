"""Repository for CloseRequest operations."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.close_request import CloseRequest, CloseRequestStatus


class CloseRequestRepository:
    """Repository for close request database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        position_id: int,
        idempotency_key: str,
        symbol: str,
        side: str,
        asset_type: str,
        target_qty: int,
    ) -> CloseRequest:
        """Create a new close request."""
        cr = CloseRequest(
            id=uuid.uuid4(),
            position_id=position_id,
            idempotency_key=idempotency_key,
            status=CloseRequestStatus.PENDING,
            symbol=symbol,
            side=side,
            asset_type=asset_type,
            target_qty=target_qty,
            filled_qty=0,
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(cr)
        await self.session.flush()
        return cr

    async def get_by_id(self, request_id: uuid.UUID) -> CloseRequest | None:
        """Get close request by ID."""
        result = await self.session.execute(
            select(CloseRequest).where(CloseRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_by_position_and_key(
        self, position_id: int, idempotency_key: str
    ) -> CloseRequest | None:
        """Get close request by position ID and idempotency key."""
        result = await self.session.execute(
            select(CloseRequest)
            .where(CloseRequest.position_id == position_id)
            .where(CloseRequest.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def update_status(self, request_id: uuid.UUID, status: CloseRequestStatus) -> None:
        """Update close request status."""
        cr = await self.get_by_id(request_id)
        if cr:
            cr.status = status
            if status == CloseRequestStatus.SUBMITTED:
                cr.submitted_at = datetime.now(timezone.utc)
            elif status in (CloseRequestStatus.COMPLETED, CloseRequestStatus.FAILED):
                cr.completed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def increment_filled_qty(self, request_id: uuid.UUID, delta: int) -> None:
        """Increment filled quantity."""
        cr = await self.get_by_id(request_id)
        if cr:
            cr.filled_qty += delta
            await self.session.flush()
