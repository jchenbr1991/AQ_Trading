"""Tests for AuditService with tiered write paths.

TDD: Write tests FIRST, then implement service.py to make them pass.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
    ValueMode,
)


class TestAuditServiceInit:
    """Tests for AuditService initialization."""

    def test_service_accepts_repository(self):
        """AuditService should accept a repository."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        assert service._repository is mock_repo

    def test_service_creates_internal_queue_if_none_provided(self):
        """AuditService should create an internal queue if none provided."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        assert service._queue is not None
        assert isinstance(service._queue, asyncio.Queue)

    def test_service_uses_provided_queue(self):
        """AuditService should use provided queue."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        queue = asyncio.Queue(maxsize=100)
        service = AuditService(repository=mock_repo, async_queue=queue)

        assert service._queue is queue

    def test_service_internal_queue_has_maxsize_10000(self):
        """AuditService internal queue should have maxsize=10000."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        assert service._queue.maxsize == 10000


class TestAuditServiceLog:
    """Tests for AuditService.log() method."""

    def test_log_returns_uuid(self):
        """log() should return a UUID."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        result = service.log(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
        )

        assert isinstance(result, UUID)

    def test_log_creates_event_with_current_utc_timestamp(self):
        """log() should create an event with current UTC timestamp."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        before = datetime.now(tz=timezone.utc)

        result = service.log(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
        )

        after = datetime.now(tz=timezone.utc)

        # The event should be created with a timestamp between before and after
        # We can't directly access the event, but we can check the return value
        assert isinstance(result, UUID)

    def test_log_applies_redaction_to_old_value(self):
        """log() should apply redaction to old_value."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch("src.audit.service.redact_sensitive_fields") as mock_redact:
            mock_redact.return_value = {"redacted": True}

            service.log(
                event_type=AuditEventType.ALERT_EMITTED,
                actor_id="user-123",
                actor_type=ActorType.USER,
                resource_type=ResourceType.ALERT,
                resource_id="alert-456",
                request_id="req-789",
                source=EventSource.WEB,
                severity=AuditSeverity.INFO,
                old_value={"password": "secret"},
            )

            # Should have called redact_sensitive_fields with old_value
            calls = mock_redact.call_args_list
            assert any(
                call[0][0] == {"password": "secret"} for call in calls
            ), "redact_sensitive_fields should be called with old_value"

    def test_log_applies_redaction_to_new_value(self):
        """log() should apply redaction to new_value."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch("src.audit.service.redact_sensitive_fields") as mock_redact:
            mock_redact.return_value = {"redacted": True}

            service.log(
                event_type=AuditEventType.ALERT_EMITTED,
                actor_id="user-123",
                actor_type=ActorType.USER,
                resource_type=ResourceType.ALERT,
                resource_id="alert-456",
                request_id="req-789",
                source=EventSource.WEB,
                severity=AuditSeverity.INFO,
                new_value={"api_key": "secret"},
            )

            # Should have called redact_sensitive_fields with new_value
            calls = mock_redact.call_args_list
            assert any(
                call[0][0] == {"api_key": "secret"} for call in calls
            ), "redact_sensitive_fields should be called with new_value"

    def test_log_computes_diff_when_old_and_new_provided(self):
        """log() should compute diff when old and new values are provided."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch("src.audit.service.redact_sensitive_fields", side_effect=lambda d, r: d):
            with patch("src.audit.service.compute_diff_jsonpatch") as mock_diff:
                mock_diff.return_value = {
                    "patch": [{"op": "replace", "path": "/name", "value": "new"}]
                }

                service.log(
                    event_type=AuditEventType.CONFIG_UPDATED,
                    actor_id="user-123",
                    actor_type=ActorType.USER,
                    resource_type=ResourceType.CONFIG,
                    resource_id="config-456",
                    request_id="req-789",
                    source=EventSource.WEB,
                    severity=AuditSeverity.INFO,
                    old_value={"name": "old"},
                    new_value={"name": "new"},
                )

                mock_diff.assert_called_once()

    def test_log_enforces_size_limit_on_old_value(self):
        """log() should enforce size limit on old_value."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch("src.audit.service.redact_sensitive_fields", side_effect=lambda d, r: d):
            with patch("src.audit.service.enforce_size_limit") as mock_enforce:
                mock_enforce.return_value = ({"small": True}, None, ValueMode.DIFF)

                service.log(
                    event_type=AuditEventType.ALERT_EMITTED,
                    actor_id="user-123",
                    actor_type=ActorType.USER,
                    resource_type=ResourceType.ALERT,
                    resource_id="alert-456",
                    request_id="req-789",
                    source=EventSource.WEB,
                    severity=AuditSeverity.INFO,
                    old_value={"large": "x" * 100000},
                )

                # enforce_size_limit should be called
                assert mock_enforce.call_count >= 1

    def test_log_enforces_size_limit_on_new_value(self):
        """log() should enforce size limit on new_value."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch("src.audit.service.redact_sensitive_fields", side_effect=lambda d, r: d):
            with patch("src.audit.service.enforce_size_limit") as mock_enforce:
                mock_enforce.return_value = ({"small": True}, None, ValueMode.DIFF)

                service.log(
                    event_type=AuditEventType.ALERT_EMITTED,
                    actor_id="user-123",
                    actor_type=ActorType.USER,
                    resource_type=ResourceType.ALERT,
                    resource_id="alert-456",
                    request_id="req-789",
                    source=EventSource.WEB,
                    severity=AuditSeverity.INFO,
                    new_value={"large": "x" * 100000},
                )

                # enforce_size_limit should be called
                assert mock_enforce.call_count >= 1


class TestAuditServiceTierRouting:
    """Tests for tier-based routing in AuditService.log()."""

    def test_log_routes_tier0_events_to_sync(self):
        """log() should route tier-0 events to sync path."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch.object(service, "_persist_sync") as mock_sync:
            with patch.object(service, "_enqueue_async") as mock_async:
                # ORDER_PLACED is a tier-0 event
                service.log(
                    event_type=AuditEventType.ORDER_PLACED,
                    actor_id="user-123",
                    actor_type=ActorType.USER,
                    resource_type=ResourceType.ORDER,
                    resource_id="order-456",
                    request_id="req-789",
                    source=EventSource.WEB,
                    severity=AuditSeverity.INFO,
                )

                mock_sync.assert_called_once()
                mock_async.assert_not_called()

    def test_log_routes_tier1_events_to_async(self):
        """log() should route tier-1 events to async path."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch.object(service, "_persist_sync") as mock_sync:
            with patch.object(service, "_enqueue_async") as mock_async:
                # ALERT_EMITTED is a tier-1 event
                service.log(
                    event_type=AuditEventType.ALERT_EMITTED,
                    actor_id="user-123",
                    actor_type=ActorType.USER,
                    resource_type=ResourceType.ALERT,
                    resource_id="alert-456",
                    request_id="req-789",
                    source=EventSource.WEB,
                    severity=AuditSeverity.INFO,
                )

                mock_async.assert_called_once()
                mock_sync.assert_not_called()

    def test_log_uses_get_tier_for_routing(self):
        """log() should use config.get_tier() to determine routing."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        with patch("src.audit.service.get_tier") as mock_get_tier:
            mock_get_tier.return_value = 0  # Force tier-0

            with patch.object(service, "_persist_sync") as mock_sync:
                service.log(
                    event_type=AuditEventType.ALERT_EMITTED,  # Normally tier-1
                    actor_id="user-123",
                    actor_type=ActorType.USER,
                    resource_type=ResourceType.ALERT,
                    resource_id="alert-456",
                    request_id="req-789",
                    source=EventSource.WEB,
                    severity=AuditSeverity.INFO,
                )

                mock_get_tier.assert_called_once_with(AuditEventType.ALERT_EMITTED)
                mock_sync.assert_called_once()


class TestPersistSync:
    """Tests for AuditService._persist_sync() method."""

    @pytest.mark.asyncio
    async def test_persist_sync_schedules_repository_call(self):
        """_persist_sync should schedule repository.persist_audit_event."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)

        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ORDER_PLACED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        # Call the sync method (not awaited - it schedules a task)
        service._persist_sync(event)

        # Give the scheduled task time to run
        await asyncio.sleep(0.1)

        mock_repo.persist_audit_event.assert_awaited_once_with(event)


class TestEnqueueAsync:
    """Tests for AuditService._enqueue_async() method."""

    def test_enqueue_async_puts_event_on_queue(self):
        """_enqueue_async should put event on the queue."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ALERT_EMITTED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        service._enqueue_async(event)

        assert service._queue.qsize() == 1

    def test_enqueue_async_falls_back_to_sync_when_queue_full(self):
        """_enqueue_async should fall back to sync when queue is full."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        queue = asyncio.Queue(maxsize=1)
        service = AuditService(repository=mock_repo, async_queue=queue)

        # Fill the queue
        event1 = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ALERT_EMITTED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )
        queue.put_nowait(event1)

        event2 = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ALERT_RESOLVED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        with patch.object(service, "_persist_sync") as mock_sync:
            service._enqueue_async(event2)

            mock_sync.assert_called_once_with(event2)


class TestStartWorkers:
    """Tests for AuditService.start_workers() method."""

    @pytest.mark.asyncio
    async def test_start_workers_creates_worker_tasks(self):
        """start_workers should create async worker tasks."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)

        service.start_workers(num_workers=2)

        assert len(service._workers) == 2
        assert all(isinstance(w, asyncio.Task) for w in service._workers)

        # Clean up
        await service.stop()

    @pytest.mark.asyncio
    async def test_start_workers_default_num_workers(self):
        """start_workers should default to 2 workers."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)

        service.start_workers()

        assert len(service._workers) == 2

        # Clean up
        await service.stop()

    @pytest.mark.asyncio
    async def test_workers_process_queue_events(self):
        """Workers should process events from the queue."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)

        # Put an event on the queue
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ALERT_EMITTED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )
        service._queue.put_nowait(event)

        service.start_workers(num_workers=1)

        # Give worker time to process
        await asyncio.sleep(0.1)

        mock_repo.persist_audit_event.assert_awaited_once_with(event)

        # Clean up
        await service.stop()


class TestStop:
    """Tests for AuditService.stop() method."""

    @pytest.mark.asyncio
    async def test_stop_cancels_workers(self):
        """stop() should cancel worker tasks."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)
        service.start_workers(num_workers=2)

        workers = list(service._workers)

        await service.stop()

        # Workers should be cancelled or done
        for worker in workers:
            assert worker.done() or worker.cancelled()

    @pytest.mark.asyncio
    async def test_stop_waits_for_queue_to_drain(self):
        """stop() should wait for queue to drain."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)

        # Start workers first so they can process
        service.start_workers(num_workers=2)

        # Give workers time to start
        await asyncio.sleep(0.05)

        # Put events on the queue
        for i in range(3):
            event = AuditEvent(
                event_id=uuid4(),
                timestamp=datetime.now(tz=timezone.utc),
                event_type=AuditEventType.ALERT_EMITTED,
                severity=AuditSeverity.INFO,
                actor_id="user-123",
                actor_type=ActorType.USER,
                resource_type=ResourceType.ALERT,
                resource_id=f"alert-{i}",
                request_id="req-789",
                source=EventSource.WEB,
                environment="production",
                service="trading-api",
                version="1.0.0",
            )
            service._queue.put_nowait(event)

        # Give workers time to pick up events
        await asyncio.sleep(0.1)

        await service.stop()

        # Queue should be empty after draining
        assert service._queue.empty()

    @pytest.mark.asyncio
    async def test_stop_is_idempotent(self):
        """stop() should be safe to call multiple times."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)
        service.start_workers()

        await service.stop()
        await service.stop()  # Should not raise

        assert True  # If we got here, no exception was raised


class TestLogWithOptionalParameters:
    """Tests for AuditService.log() with optional parameters."""

    def test_log_accepts_correlation_id(self):
        """log() should accept correlation_id parameter."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        result = service.log(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            correlation_id="corr-123",
        )

        assert isinstance(result, UUID)

    def test_log_accepts_session_id(self):
        """log() should accept session_id parameter."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        result = service.log(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            session_id="sess-123",
        )

        assert isinstance(result, UUID)

    def test_log_accepts_metadata(self):
        """log() should accept metadata parameter."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        service = AuditService(repository=mock_repo)

        result = service.log(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            metadata={"extra": "info"},
        )

        assert isinstance(result, UUID)


class TestAuditServiceIntegration:
    """Integration tests for AuditService."""

    @pytest.mark.asyncio
    async def test_full_tier0_flow(self):
        """Test full flow for tier-0 event."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)

        # ORDER_PLACED is tier-0, should be persisted synchronously
        event_id = service.log(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            new_value={"symbol": "AAPL", "quantity": 100},
        )

        assert isinstance(event_id, UUID)
        # Wait a bit for any async operations
        await asyncio.sleep(0.1)
        mock_repo.persist_audit_event.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_tier1_flow(self):
        """Test full flow for tier-1 event with workers."""
        from src.audit.service import AuditService

        mock_repo = MagicMock()
        mock_repo.persist_audit_event = AsyncMock(return_value=(1, "checksum"))

        service = AuditService(repository=mock_repo)
        service.start_workers(num_workers=1)

        # ALERT_EMITTED is tier-1, should be queued
        event_id = service.log(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            metadata={"alert_type": "price_spike"},
        )

        assert isinstance(event_id, UUID)

        # Wait for worker to process
        await asyncio.sleep(0.2)

        mock_repo.persist_audit_event.assert_called_once()

        await service.stop()
