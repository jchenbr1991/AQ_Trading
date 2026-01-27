"""Tests for worker setup and lifecycle."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class TestWorkerSetup:
    """Tests for worker initialization and shutdown."""

    @pytest.mark.asyncio
    async def test_init_workers_starts_scheduler_and_task(self):
        """init_workers should start scheduler and outbox worker task."""
        from src.workers import setup

        # Reset global state
        setup._scheduler = None
        setup._outbox_worker_task = None

        order_manager = AsyncMock()
        market_data = AsyncMock()
        broker_api = AsyncMock()

        # Mock async_session to prevent actual DB connections
        with patch("src.workers.setup.async_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()

            await setup.init_workers(order_manager, market_data, broker_api)

            # Verify scheduler was started
            assert setup._scheduler is not None
            assert setup._scheduler.running

            # Verify outbox worker task was created
            assert setup._outbox_worker_task is not None
            assert not setup._outbox_worker_task.done()

            # Verify scheduled jobs were added
            jobs = setup._scheduler.get_jobs()
            job_ids = [job.id for job in jobs]
            assert "zombie_detection" in job_ids
            assert "stuck_order_recovery" in job_ids
            assert "partial_fill_retry" in job_ids
            assert "invariant_check" in job_ids
            assert "outbox_cleanup" in job_ids

            # Clean up
            await setup.shutdown_workers()

    @pytest.mark.asyncio
    async def test_shutdown_workers_stops_everything(self):
        """shutdown_workers should stop scheduler and cancel task."""
        from src.workers import setup

        # Reset global state
        setup._scheduler = None
        setup._outbox_worker_task = None

        order_manager = AsyncMock()
        market_data = AsyncMock()
        broker_api = AsyncMock()

        with patch("src.workers.setup.async_session") as mock_session:
            mock_session.return_value.__aenter__ = AsyncMock()
            mock_session.return_value.__aexit__ = AsyncMock()

            await setup.init_workers(order_manager, market_data, broker_api)

            # Shutdown
            await setup.shutdown_workers()

            # Verify everything is stopped
            assert setup._scheduler is None
            assert setup._outbox_worker_task is None

    @pytest.mark.asyncio
    async def test_shutdown_workers_handles_no_init(self):
        """shutdown_workers should handle case where init was never called."""
        from src.workers import setup

        # Reset global state
        setup._scheduler = None
        setup._outbox_worker_task = None

        # Should not raise
        await setup.shutdown_workers()

        assert setup._scheduler is None
        assert setup._outbox_worker_task is None


class TestScheduledJobs:
    """Tests for scheduled job functions (integration with real session)."""

    @pytest.mark.asyncio
    async def test_zombie_detection_job_runs_without_error(self, db_session):
        """_run_zombie_detection should complete without error."""
        from src.workers.reconciler import Reconciler

        broker_api = AsyncMock()
        reconciler = Reconciler(db_session, broker_api)

        # Should not raise
        await reconciler.detect_zombies()

    @pytest.mark.asyncio
    async def test_outbox_cleanup_job_runs_without_error(self, db_session):
        """_run_outbox_cleanup should complete without error."""
        from src.workers.outbox_cleaner import OutboxCleaner

        cleaner = OutboxCleaner(db_session)

        # Should not raise
        count = await cleaner.cleanup()
        assert count == 0  # No old events to clean

    @pytest.mark.asyncio
    async def test_partial_fill_retry_job_runs_without_error(self, db_session):
        """_run_partial_fill_retry should complete without error."""
        from src.workers.reconciler import Reconciler

        broker_api = AsyncMock()
        reconciler = Reconciler(db_session, broker_api)

        # Should not raise
        await reconciler.retry_partial_fills()
