"""Tests for CloseRequestRepository."""

from uuid import uuid4

import pytest
import pytest_asyncio
from src.db.repositories.close_request_repo import CloseRequestRepository
from src.models.close_request import CloseRequestStatus


@pytest_asyncio.fixture
async def repo(db_session):
    """Create repository with test session."""
    return CloseRequestRepository(db_session)


@pytest.mark.asyncio
async def test_create_close_request(repo, db_session):
    """Should create a new close request."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.id is not None
    assert cr.position_id == 1
    assert cr.idempotency_key == "test-key"
    assert cr.status == CloseRequestStatus.PENDING


@pytest.mark.asyncio
async def test_get_by_position_and_key(repo, db_session):
    """Should find close request by position_id and idempotency_key."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    found = await repo.get_by_position_and_key(1, "test-key")
    assert found is not None
    assert found.id == cr.id


@pytest.mark.asyncio
async def test_get_by_position_and_key_not_found(repo):
    """Should return None when not found."""
    found = await repo.get_by_position_and_key(999, "nonexistent")
    assert found is None


@pytest.mark.asyncio
async def test_update_status(repo, db_session):
    """Should update close request status."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    await repo.update_status(cr.id, CloseRequestStatus.SUBMITTED)

    updated = await repo.get_by_id(cr.id)
    assert updated.status == CloseRequestStatus.SUBMITTED


@pytest.mark.asyncio
async def test_update_status_sets_submitted_at(repo, db_session):
    """Should set submitted_at when status changes to SUBMITTED."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.submitted_at is None
    await repo.update_status(cr.id, CloseRequestStatus.SUBMITTED)

    updated = await repo.get_by_id(cr.id)
    assert updated.submitted_at is not None


@pytest.mark.asyncio
async def test_update_status_sets_completed_at_on_completed(repo, db_session):
    """Should set completed_at when status changes to COMPLETED."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.completed_at is None
    await repo.update_status(cr.id, CloseRequestStatus.COMPLETED)

    updated = await repo.get_by_id(cr.id)
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_update_status_sets_completed_at_on_failed(repo, db_session):
    """Should set completed_at when status changes to FAILED."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.completed_at is None
    await repo.update_status(cr.id, CloseRequestStatus.FAILED)

    updated = await repo.get_by_id(cr.id)
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_get_by_id(repo, db_session):
    """Should retrieve close request by ID."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    found = await repo.get_by_id(cr.id)
    assert found is not None
    assert found.id == cr.id
    assert found.symbol == "AAPL"


@pytest.mark.asyncio
async def test_get_by_id_not_found(repo):
    """Should return None when ID not found."""
    found = await repo.get_by_id(uuid4())
    assert found is None


@pytest.mark.asyncio
async def test_increment_filled_qty(repo, db_session):
    """Should increment filled quantity."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.filled_qty == 0

    await repo.increment_filled_qty(cr.id, 50)
    updated = await repo.get_by_id(cr.id)
    assert updated.filled_qty == 50

    await repo.increment_filled_qty(cr.id, 30)
    updated = await repo.get_by_id(cr.id)
    assert updated.filled_qty == 80
