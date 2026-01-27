"""Tests for Outbox Cleaner job."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from src.models.outbox import OutboxEvent, OutboxEventStatus


@pytest_asyncio.fixture
async def cleaner(db_session):
    """Create cleaner with test session."""
    from src.workers.outbox_cleaner import OutboxCleaner

    return OutboxCleaner(db_session)


class TestOutboxCleaner:
    """Tests for outbox cleanup functionality."""

    @pytest.mark.asyncio
    async def test_deletes_old_completed_events(self, db_session, cleaner):
        """Should delete completed events older than retention period."""
        old_time = datetime.now(timezone.utc) - timedelta(days=5)

        # Create old completed event
        old_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "old-123"},
            status=OutboxEventStatus.COMPLETED,
            created_at=old_time,
            processed_at=old_time,
        )
        db_session.add(old_event)
        await db_session.commit()
        old_event_id = old_event.id

        # Run cleanup
        count = await cleaner.cleanup(retention_days=3)

        # Should have deleted 1 event
        assert count == 1

        # Verify it's gone
        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.id == old_event_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_deletes_old_failed_events(self, db_session, cleaner):
        """Should delete failed events older than retention period."""
        old_time = datetime.now(timezone.utc) - timedelta(days=4)

        old_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "old-456"},
            status=OutboxEventStatus.FAILED,
            created_at=old_time,
            processed_at=old_time,
        )
        db_session.add(old_event)
        await db_session.commit()

        count = await cleaner.cleanup(retention_days=3)

        assert count == 1

    @pytest.mark.asyncio
    async def test_preserves_recent_completed_events(self, db_session, cleaner):
        """Should NOT delete completed events within retention period."""
        recent_time = datetime.now(timezone.utc) - timedelta(days=1)

        recent_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "recent-123"},
            status=OutboxEventStatus.COMPLETED,
            created_at=recent_time,
            processed_at=recent_time,
        )
        db_session.add(recent_event)
        await db_session.commit()
        event_id = recent_event.id

        count = await cleaner.cleanup(retention_days=3)

        # Should NOT delete recent events
        assert count == 0

        # Verify it still exists
        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_preserves_pending_events(self, db_session, cleaner):
        """Should NOT delete pending events regardless of age."""
        old_time = datetime.now(timezone.utc) - timedelta(days=10)

        old_pending = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "old-pending"},
            status=OutboxEventStatus.PENDING,
            created_at=old_time,
        )
        db_session.add(old_pending)
        await db_session.commit()
        event_id = old_pending.id

        count = await cleaner.cleanup(retention_days=3)

        # Should NOT delete pending events
        assert count == 0

        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_preserves_processing_events(self, db_session, cleaner):
        """Should NOT delete processing events regardless of age."""
        old_time = datetime.now(timezone.utc) - timedelta(days=10)

        old_processing = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "old-processing"},
            status=OutboxEventStatus.PROCESSING,
            created_at=old_time,
        )
        db_session.add(old_processing)
        await db_session.commit()
        event_id = old_processing.id

        count = await cleaner.cleanup(retention_days=3)

        # Should NOT delete processing events
        assert count == 0

        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        assert result.scalar_one_or_none() is not None

    @pytest.mark.asyncio
    async def test_deletes_multiple_old_events(self, db_session, cleaner):
        """Should delete multiple old events in one cleanup."""
        old_time = datetime.now(timezone.utc) - timedelta(days=5)

        # Create 3 old events
        for i in range(3):
            event = OutboxEvent(
                event_type="SUBMIT_CLOSE_ORDER",
                payload={"close_request_id": f"old-{i}"},
                status=OutboxEventStatus.COMPLETED,
                created_at=old_time,
                processed_at=old_time,
            )
            db_session.add(event)

        await db_session.commit()

        count = await cleaner.cleanup(retention_days=3)

        assert count == 3

    @pytest.mark.asyncio
    async def test_uses_default_retention_period(self, db_session, cleaner):
        """Should use default 3-day retention when not specified."""
        # Event from 4 days ago (should be deleted with 3-day retention)
        old_time = datetime.now(timezone.utc) - timedelta(days=4)
        old_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "old"},
            status=OutboxEventStatus.COMPLETED,
            created_at=old_time,
            processed_at=old_time,
        )
        db_session.add(old_event)

        # Event from 2 days ago (should be preserved with 3-day retention)
        recent_time = datetime.now(timezone.utc) - timedelta(days=2)
        recent_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": "recent"},
            status=OutboxEventStatus.COMPLETED,
            created_at=recent_time,
            processed_at=recent_time,
        )
        db_session.add(recent_event)
        await db_session.commit()

        # Use default retention
        count = await cleaner.cleanup()

        # Should delete only the 4-day-old event
        assert count == 1
