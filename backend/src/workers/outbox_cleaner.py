"""Outbox cleaner job for removing old processed events."""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outbox import OutboxEvent, OutboxEventStatus

logger = logging.getLogger(__name__)


class OutboxCleaner:
    """Cleaner for removing old completed/failed outbox events.

    Runs daily to prevent table bloat and maintain vacuum performance.
    Only removes events in terminal states (COMPLETED, FAILED).
    """

    DEFAULT_RETENTION_DAYS = 3

    def __init__(self, session: AsyncSession):
        self.session = session

    async def cleanup(self, retention_days: int | None = None) -> int:
        """Remove old completed/failed outbox events.

        Args:
            retention_days: Days to retain events. Defaults to 3.

        Returns:
            Number of events deleted.
        """
        if retention_days is None:
            retention_days = self.DEFAULT_RETENTION_DAYS

        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

        # Delete old events in terminal states only
        result = await self.session.execute(
            delete(OutboxEvent)
            .where(OutboxEvent.status.in_([OutboxEventStatus.COMPLETED, OutboxEventStatus.FAILED]))
            .where(OutboxEvent.created_at < cutoff)
        )

        count = result.rowcount
        await self.session.commit()

        if count > 0:
            logger.info(f"Cleaned up {count} old outbox events (retention={retention_days} days)")

        return count
