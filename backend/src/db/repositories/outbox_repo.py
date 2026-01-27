"""Repository for OutboxEvent operations."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from src.db.repositories.base import BaseRepository
from src.models.outbox import OutboxEvent, OutboxEventStatus


class OutboxRepository(BaseRepository):
    """Repository for outbox event database operations."""

    async def create(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        """Create a new outbox event."""
        event = OutboxEvent(
            event_type=event_type,
            payload=payload,
            status=OutboxEventStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            retry_count=0,
        )
        self.session.add(event)
        await self.session.commit()
        await self.session.refresh(event)
        return event

    async def get_by_id(self, event_id: int) -> OutboxEvent | None:
        """Get outbox event by ID."""
        result = await self.session.execute(select(OutboxEvent).where(OutboxEvent.id == event_id))
        return result.scalar_one_or_none()

    async def claim_pending(self, limit: int = 1) -> list[OutboxEvent]:
        """Claim pending events for processing.

        Uses FOR UPDATE SKIP LOCKED for concurrent worker safety.
        """
        result = await self.session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxEventStatus.PENDING)
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())

        for event in events:
            event.status = OutboxEventStatus.PROCESSING

        await self.session.commit()
        for event in events:
            await self.session.refresh(event)
        return events

    async def mark_completed(self, event_id: int) -> OutboxEvent | None:
        """Mark event as completed."""
        event = await self.get_by_id(event_id)
        if event:
            event.status = OutboxEventStatus.COMPLETED
            event.processed_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(event)
        return event

    async def mark_failed(self, event_id: int) -> OutboxEvent | None:
        """Mark event as failed."""
        event = await self.get_by_id(event_id)
        if event:
            event.status = OutboxEventStatus.FAILED
            event.processed_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(event)
        return event

    async def increment_retry(self, event_id: int) -> int:
        """Increment retry count and return new count."""
        event = await self.get_by_id(event_id)
        if event:
            event.retry_count += 1
            event.status = OutboxEventStatus.PENDING  # Reset to pending for retry
            await self.session.commit()
            await self.session.refresh(event)
            return event.retry_count
        return 0
