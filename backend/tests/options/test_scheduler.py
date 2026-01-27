"""Tests for expiration scheduler."""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_checker():
    """Create a mock ExpirationChecker."""
    checker = AsyncMock()
    checker.check_expirations.return_value = {
        "run_id": "test-run",
        "positions_checked": 5,
        "alerts_created": 2,
    }
    return checker


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    return session


class TestExpirationScheduler:
    """Tests for ExpirationScheduler class."""

    def test_scheduler_init(self, mock_checker, mock_session):
        """Should initialize with correct parameters."""
        from src.options.scheduler import ExpirationScheduler

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=True,
        )

        assert scheduler.checker == mock_checker
        assert scheduler.account_id == "acc123"
        assert scheduler.use_distributed_lock is True

    @pytest.mark.asyncio
    async def test_run_check_without_lock(self, mock_checker, mock_session):
        """Should run check directly when not using distributed lock."""
        from src.options.scheduler import ExpirationScheduler

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=False,
        )

        stats = await scheduler._run_check_with_lock()

        assert stats["executed"] is True
        assert stats["positions_checked"] == 5
        mock_checker.check_expirations.assert_called_once_with("acc123")

    @pytest.mark.asyncio
    async def test_run_check_with_lock_acquired(self, mock_checker, mock_session):
        """Should run check when advisory lock is acquired."""
        from src.options.scheduler import ExpirationScheduler

        # Mock successful lock acquisition
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=True,
        )

        stats = await scheduler._run_check_with_lock()

        assert stats["executed"] is True
        mock_checker.check_expirations.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_check_with_lock_not_acquired(self, mock_checker, mock_session):
        """Should skip check when advisory lock is held by another instance."""
        from src.options.scheduler import ExpirationScheduler

        # Mock failed lock acquisition
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=True,
        )

        stats = await scheduler._run_check_with_lock()

        assert stats["executed"] is False
        assert stats["reason"] == "lock_held_by_another_instance"
        mock_checker.check_expirations.assert_not_called()

    @pytest.mark.asyncio
    async def test_try_acquire_lock_success(self, mock_checker, mock_session):
        """Should return True when lock is acquired."""
        from src.options.scheduler import ExpirationScheduler

        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
        )

        acquired = await scheduler._try_acquire_lock()

        assert acquired is True

    @pytest.mark.asyncio
    async def test_try_acquire_lock_failure(self, mock_checker, mock_session):
        """Should return False when lock is held."""
        from src.options.scheduler import ExpirationScheduler

        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
        )

        acquired = await scheduler._try_acquire_lock()

        assert acquired is False

    @pytest.mark.asyncio
    async def test_release_lock(self, mock_checker, mock_session):
        """Should release the advisory lock."""
        from src.options.scheduler import ExpirationScheduler

        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
        )

        await scheduler._release_lock()

        # Verify pg_advisory_unlock was called
        assert mock_session.execute.called
