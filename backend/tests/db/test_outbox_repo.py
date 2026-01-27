"""Tests for OutboxRepository."""

import pytest
import pytest_asyncio
from src.db.repositories.outbox_repo import OutboxRepository
from src.models.outbox import OutboxEventStatus


@pytest_asyncio.fixture
async def repo(db_session):
    """Create repository with test session."""
    return OutboxRepository(db_session)


@pytest.mark.asyncio
async def test_create_event(repo):
    """Should create a new outbox event."""
    event = await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123", "symbol": "AAPL"},
    )

    assert event.id is not None
    assert event.event_type == "SUBMIT_CLOSE_ORDER"
    assert event.status == OutboxEventStatus.PENDING


@pytest.mark.asyncio
async def test_claim_pending_events(repo):
    """Should claim pending events for processing."""
    await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "1"},
    )
    await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "2"},
    )

    events = await repo.claim_pending(limit=1)
    assert len(events) == 1
    assert events[0].status == OutboxEventStatus.PROCESSING


@pytest.mark.asyncio
async def test_mark_completed(repo):
    """Should mark event as completed."""
    event = await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123"},
    )

    await repo.mark_completed(event.id)

    updated = await repo.get_by_id(event.id)
    assert updated.status == OutboxEventStatus.COMPLETED
    assert updated.processed_at is not None


@pytest.mark.asyncio
async def test_mark_failed(repo):
    """Should mark event as failed."""
    event = await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123"},
    )

    await repo.mark_failed(event.id)

    updated = await repo.get_by_id(event.id)
    assert updated.status == OutboxEventStatus.FAILED
    assert updated.processed_at is not None


@pytest.mark.asyncio
async def test_increment_retry(repo):
    """Should increment retry count and reset to pending."""
    event = await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123"},
    )

    # Mark as processing first
    events = await repo.claim_pending(limit=1)
    assert events[0].status == OutboxEventStatus.PROCESSING

    # Increment retry
    new_count = await repo.increment_retry(event.id)
    assert new_count == 1

    updated = await repo.get_by_id(event.id)
    assert updated.retry_count == 1
    assert updated.status == OutboxEventStatus.PENDING  # Reset to pending


@pytest.mark.asyncio
async def test_get_by_id_not_found(repo):
    """Should return None when event not found."""
    result = await repo.get_by_id(99999)
    assert result is None


@pytest.mark.asyncio
async def test_claim_pending_respects_limit(repo):
    """Should respect limit parameter when claiming events."""
    # Create 3 events
    await repo.create(event_type="SUBMIT_CLOSE_ORDER", payload={"id": "1"})
    await repo.create(event_type="SUBMIT_CLOSE_ORDER", payload={"id": "2"})
    await repo.create(event_type="SUBMIT_CLOSE_ORDER", payload={"id": "3"})

    # Claim only 2
    events = await repo.claim_pending(limit=2)
    assert len(events) == 2


@pytest.mark.asyncio
async def test_claim_pending_skips_processing_events(repo):
    """Should not claim events that are already processing."""
    await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "1"},
    )
    await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "2"},
    )

    # Claim first event
    first_events = await repo.claim_pending(limit=1)
    assert len(first_events) == 1
    first_id = first_events[0].id

    # Claim again - should get the second event
    second_events = await repo.claim_pending(limit=1)
    assert len(second_events) == 1
    assert second_events[0].id != first_id
