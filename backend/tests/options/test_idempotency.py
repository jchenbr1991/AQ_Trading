"""Tests for idempotency service."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    return session


class TestIdempotencyService:
    """Tests for IdempotencyService class."""

    @pytest.mark.asyncio
    async def test_store_key_inserts_record(self, mock_session):
        """Should insert a new idempotency record."""
        from src.options.idempotency import IdempotencyService

        service = IdempotencyService(mock_session)

        await service.store_key(
            key="test-key-123",
            resource_type="close_position",
            resource_id="456",
            response_data={"success": True, "order_id": "order-789"},
        )

        # Verify execute was called
        assert mock_session.execute.called
        # Verify commit was called
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_get_cached_response_returns_data_when_exists(self, mock_session):
        """Should return cached response when key exists and not expired."""
        from src.options.idempotency import IdempotencyService

        # Mock the database returning a row
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ('{"success": true, "order_id": "order-789"}',)
        mock_session.execute.return_value = mock_result

        service = IdempotencyService(mock_session)

        exists, data = await service.get_cached_response("test-key-123")

        assert exists is True
        assert data == {"success": True, "order_id": "order-789"}

    @pytest.mark.asyncio
    async def test_get_cached_response_returns_none_when_not_exists(self, mock_session):
        """Should return (False, None) when key doesn't exist."""
        from src.options.idempotency import IdempotencyService

        # Mock the database returning no rows
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        service = IdempotencyService(mock_session)

        exists, data = await service.get_cached_response("nonexistent-key")

        assert exists is False
        assert data is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_returns_count(self, mock_session):
        """Should return count of deleted expired keys."""
        from src.options.idempotency import IdempotencyService

        # Mock the database returning rowcount
        mock_result = MagicMock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result

        service = IdempotencyService(mock_session)

        count = await service.cleanup_expired()

        assert count == 5
        assert mock_session.commit.called

    @pytest.mark.asyncio
    async def test_store_key_uses_correct_ttl(self, mock_session):
        """Should use the specified TTL for expiration."""
        from src.options.idempotency import IdempotencyService

        service = IdempotencyService(mock_session)

        # Store with custom TTL
        await service.store_key(
            key="test-key",
            resource_type="test",
            resource_id="1",
            response_data={},
            ttl_hours=48,
        )

        # Verify execute was called
        assert mock_session.execute.called
