"""Tests for NotificationHub with async queue and retry."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.alerts.channels import DeliveryResult, NotificationChannel
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity


class TestSelfAlertTypes:
    """Tests for SELF_ALERT_TYPES constant."""

    def test_alert_delivery_failed_is_self_alert_type(self):
        """ALERT_DELIVERY_FAILED should be in SELF_ALERT_TYPES to prevent recursion."""
        from src.alerts.hub import SELF_ALERT_TYPES

        assert AlertType.ALERT_DELIVERY_FAILED in SELF_ALERT_TYPES

    def test_self_alert_types_is_frozenset(self):
        """SELF_ALERT_TYPES should be immutable."""
        from src.alerts.hub import SELF_ALERT_TYPES

        assert isinstance(SELF_ALERT_TYPES, frozenset)


class TestNotificationHubInit:
    """Tests for NotificationHub initialization."""

    def test_init_with_defaults(self):
        """NotificationHub initializes with default parameters."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {"email": MagicMock(), "webhook": MagicMock()}

        hub = NotificationHub(
            repository=mock_repo,
            channels=mock_channels,
        )

        assert hub.repository is mock_repo
        assert hub.channels == mock_channels
        assert hub.max_queue_size == 1000
        assert hub.max_retries == 5
        assert hub.retry_base_delay == 1.0
        assert hub.retry_multiplier == 2.0

    def test_init_with_custom_params(self):
        """NotificationHub accepts custom parameters."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        hub = NotificationHub(
            repository=mock_repo,
            channels=mock_channels,
            max_queue_size=500,
            max_retries=3,
            retry_base_delay=0.5,
            retry_multiplier=3.0,
        )

        assert hub.max_queue_size == 500
        assert hub.max_retries == 3
        assert hub.retry_base_delay == 0.5
        assert hub.retry_multiplier == 3.0


class TestNotificationHubStartStop:
    """Tests for NotificationHub start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_workers(self):
        """start() creates specified number of worker tasks."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        hub = NotificationHub(repository=mock_repo, channels=mock_channels)
        await hub.start(num_workers=3)

        try:
            assert len(hub._workers) == 3
            assert all(isinstance(w, asyncio.Task) for w in hub._workers)
        finally:
            await hub.stop()

    @pytest.mark.asyncio
    async def test_stop_cancels_workers(self):
        """stop() cancels all worker tasks gracefully."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        hub = NotificationHub(repository=mock_repo, channels=mock_channels)
        await hub.start(num_workers=2)

        # Workers should be running
        assert all(not w.done() for w in hub._workers)

        await hub.stop()

        # Workers should be cancelled
        assert all(w.done() for w in hub._workers)

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        """stop() handles case when hub was never started."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        hub = NotificationHub(repository=mock_repo, channels=mock_channels)

        # Should not raise
        await hub.stop()


class TestEnqueue:
    """Tests for NotificationHub.enqueue()."""

    @pytest.mark.asyncio
    async def test_enqueue_adds_to_queue(self):
        """enqueue() adds alert to the internal queue."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        hub = NotificationHub(repository=mock_repo, channels=mock_channels, max_queue_size=100)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        result = await hub.enqueue(alert)

        assert result is True
        assert hub._queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_enqueue_returns_false_when_queue_full_non_sev1(self):
        """enqueue() returns False for non-SEV1 alerts when queue is full."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        # Very small queue
        hub = NotificationHub(repository=mock_repo, channels=mock_channels, max_queue_size=1)

        alert1 = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Alert 1",
        )
        alert2 = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Alert 2",
        )

        # Fill the queue
        result1 = await hub.enqueue(alert1)
        assert result1 is True

        # Queue is now full, should return False for non-SEV1
        with patch("src.alerts.hub.logger") as mock_logger:
            result2 = await hub.enqueue(alert2)

        assert result2 is False
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_enqueue_calls_fallback_for_sev1_when_queue_full(self):
        """enqueue() calls _fallback_sync_send() for SEV1 alerts when queue is full."""
        from src.alerts.hub import NotificationHub

        mock_repo = MagicMock()
        mock_channels = {}

        hub = NotificationHub(repository=mock_repo, channels=mock_channels, max_queue_size=1)

        # Fill the queue
        filler_alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Filler",
        )
        await hub.enqueue(filler_alert)

        # Now try to enqueue SEV1
        sev1_alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Critical alert",
        )

        with patch.object(hub, "_fallback_sync_send", new_callable=AsyncMock) as mock_fallback:
            result = await hub.enqueue(sev1_alert)

        assert result is True
        mock_fallback.assert_called_once_with(sev1_alert)


class TestDeliverWithRetry:
    """Tests for _deliver_with_retry exponential backoff."""

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self):
        """Retry delays follow exponential backoff: 1s, 2s, 4s, 8s, 16s."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        # Fail first 4 attempts, succeed on 5th
        mock_channel.send = AsyncMock(
            side_effect=[
                DeliveryResult(success=False, error_message="fail 1"),
                DeliveryResult(success=False, error_message="fail 2"),
                DeliveryResult(success=False, error_message="fail 3"),
                DeliveryResult(success=False, error_message="fail 4"),
                DeliveryResult(success=True, response_code=200),
            ]
        )

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_retries=5,
            retry_base_delay=1.0,
            retry_multiplier=2.0,
        )

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )

        sleep_calls = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            sleep_calls.append(delay)
            # Actually sleep a tiny bit to not break async
            await original_sleep(0.001)

        with patch("asyncio.sleep", mock_sleep):
            result = await hub._deliver_with_retry(
                alert, mock_channel, "webhook", "http://example.com"
            )

        assert result is True
        # Should have slept 4 times (before retries 2, 3, 4, 5)
        assert sleep_calls == [1.0, 2.0, 4.0, 8.0]

    @pytest.mark.asyncio
    async def test_records_each_attempt_in_repository(self):
        """Each delivery attempt is recorded in the repository."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        delivery_ids = [uuid4() for _ in range(3)]
        mock_repo.record_delivery_attempt = AsyncMock(side_effect=delivery_ids)
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send = AsyncMock(
            side_effect=[
                DeliveryResult(success=False, error_message="fail 1"),
                DeliveryResult(success=False, error_message="fail 2"),
                DeliveryResult(success=True, response_code=200),
            ]
        )

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_retries=5,
            retry_base_delay=0.001,  # Fast for tests
        )

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )

        await hub._deliver_with_retry(alert, mock_channel, "webhook", "http://example.com")

        # Should have recorded 3 attempts
        assert mock_repo.record_delivery_attempt.call_count == 3

        # Verify attempt numbers
        calls = mock_repo.record_delivery_attempt.call_args_list
        assert calls[0].kwargs["attempt_number"] == 1
        assert calls[1].kwargs["attempt_number"] == 2
        assert calls[2].kwargs["attempt_number"] == 3

    @pytest.mark.asyncio
    async def test_calls_handle_failure_on_final_retry(self):
        """_handle_delivery_failure is called after all retries exhausted."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send = AsyncMock(
            return_value=DeliveryResult(success=False, error_message="always fails")
        )

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_retries=3,
            retry_base_delay=0.001,
        )

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )

        with patch.object(hub, "_handle_delivery_failure", new_callable=AsyncMock) as mock_handle:
            result = await hub._deliver_with_retry(
                alert, mock_channel, "webhook", "http://example.com"
            )

        assert result is False
        mock_handle.assert_called_once()
        call_args = mock_handle.call_args
        assert call_args.args[0] is alert
        assert call_args.args[1] == "webhook"
        assert "always fails" in str(call_args.args[2])


class TestHandleDeliveryFailure:
    """Tests for _handle_delivery_failure behavior."""

    @pytest.mark.asyncio
    async def test_self_alert_type_only_logs_critical(self):
        """ALERT_DELIVERY_FAILED alerts only log, don't create new alerts."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock()

        hub = NotificationHub(
            repository=mock_repo,
            channels={},
        )

        # Create an ALERT_DELIVERY_FAILED alert
        alert = create_alert(
            type=AlertType.ALERT_DELIVERY_FAILED,
            severity=Severity.SEV1,
            summary="Failed to deliver",
        )

        with patch("src.alerts.hub.logger") as mock_logger:
            await hub._handle_delivery_failure(alert, "email", "Connection refused")

        mock_logger.critical.assert_called()
        mock_repo.persist_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_sev1_creates_alert_delivery_failed_alert(self):
        """SEV1 failures create ALERT_DELIVERY_FAILED alert (persist only)."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))

        hub = NotificationHub(
            repository=mock_repo,
            channels={},
        )

        # SEV1 alert that failed delivery
        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Kill switch activated",
        )

        await hub._handle_delivery_failure(alert, "email", "SMTP connection failed")

        # Should have persisted a new ALERT_DELIVERY_FAILED alert
        mock_repo.persist_alert.assert_called_once()
        persisted_alert = mock_repo.persist_alert.call_args.args[0]
        assert persisted_alert.type == AlertType.ALERT_DELIVERY_FAILED
        assert persisted_alert.severity == Severity.SEV1
        assert "KILL_SWITCH_ACTIVATED" in persisted_alert.summary

    @pytest.mark.asyncio
    async def test_non_sev1_does_not_create_new_alert(self):
        """Non-SEV1 failures don't create new alerts."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock()

        hub = NotificationHub(
            repository=mock_repo,
            channels={},
        )

        # SEV2 alert that failed delivery
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )

        await hub._handle_delivery_failure(alert, "webhook", "Timeout")

        mock_repo.persist_alert.assert_not_called()


class TestFallbackSyncSend:
    """Tests for _fallback_sync_send immediate delivery."""

    @pytest.mark.asyncio
    async def test_fallback_delivers_directly(self):
        """_fallback_sync_send delivers alert immediately to all destinations."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_email = AsyncMock(spec=NotificationChannel)
        mock_email.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=250))

        mock_webhook = AsyncMock(spec=NotificationChannel)
        mock_webhook.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=200))

        hub = NotificationHub(
            repository=mock_repo,
            channels={"email": mock_email, "webhook": mock_webhook},
        )

        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Critical",
        )

        # Mock get_destinations_for_alert
        with patch(
            "src.alerts.hub.get_destinations_for_alert",
            return_value=[("email", "test@example.com"), ("webhook", "http://hook")],
        ):
            await hub._fallback_sync_send(alert)

        mock_email.send.assert_called_once_with(alert, "test@example.com")
        mock_webhook.send.assert_called_once_with(alert, "http://hook")


class TestDeliverAlert:
    """Tests for _deliver_alert routing and delivery."""

    @pytest.mark.asyncio
    async def test_delivers_to_all_destinations(self):
        """_deliver_alert sends to all destinations from routing."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=200))

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_retries=1,
            retry_base_delay=0.001,
        )

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )

        destinations = [
            ("webhook", "http://hook1.example.com"),
            ("webhook", "http://hook2.example.com"),
        ]

        with patch("src.alerts.hub.get_destinations_for_alert", return_value=destinations):
            await hub._deliver_alert(alert)

        assert mock_channel.send.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_unknown_channel(self):
        """_deliver_alert skips destinations with unknown channel type."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=200))

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},  # No email channel
        )

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )

        destinations = [
            ("email", "test@example.com"),  # Unknown channel
            ("webhook", "http://hook.example.com"),
        ]

        with patch("src.alerts.hub.get_destinations_for_alert", return_value=destinations):
            with patch("src.alerts.hub.logger") as mock_logger:
                await hub._deliver_alert(alert)

        # Should have logged warning for missing email channel
        mock_logger.warning.assert_called()
        # Should still have sent to webhook
        mock_channel.send.assert_called_once()


class TestWorker:
    """Tests for _worker and _process_one."""

    @pytest.mark.asyncio
    async def test_worker_processes_queue_items(self):
        """_worker continuously processes alerts from the queue."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=200))

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_retries=1,
            retry_base_delay=0.001,
        )

        # Enqueue some alerts
        alert1 = create_alert(
            type=AlertType.ORDER_FILLED, severity=Severity.SEV3, summary="Alert 1"
        )
        alert2 = create_alert(
            type=AlertType.ORDER_FILLED, severity=Severity.SEV3, summary="Alert 2"
        )

        await hub.enqueue(alert1)
        await hub.enqueue(alert2)

        # Mock destinations
        with patch(
            "src.alerts.hub.get_destinations_for_alert",
            return_value=[("webhook", "http://hook")],
        ):
            await hub.start(num_workers=1)
            # Wait for processing
            await asyncio.sleep(0.1)
            await hub.stop()

        # Both alerts should have been processed
        assert mock_channel.send.call_count == 2

    @pytest.mark.asyncio
    async def test_worker_handles_exceptions(self):
        """_worker continues processing after exceptions."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        # First call raises, second succeeds
        mock_channel.send = AsyncMock(
            side_effect=[
                Exception("Unexpected error"),
                DeliveryResult(success=True, response_code=200),
            ]
        )

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_retries=1,
            retry_base_delay=0.001,
        )

        alert1 = create_alert(
            type=AlertType.ORDER_FILLED, severity=Severity.SEV3, summary="Alert 1"
        )
        alert2 = create_alert(
            type=AlertType.ORDER_FILLED, severity=Severity.SEV3, summary="Alert 2"
        )

        await hub.enqueue(alert1)
        await hub.enqueue(alert2)

        with patch(
            "src.alerts.hub.get_destinations_for_alert",
            return_value=[("webhook", "http://hook")],
        ):
            await hub.start(num_workers=1)
            await asyncio.sleep(0.1)
            await hub.stop()

        # Worker should have attempted both
        assert mock_channel.send.call_count == 2


class TestSev1NeverDropped:
    """Tests ensuring SEV1 alerts are never dropped."""

    @pytest.mark.asyncio
    async def test_sev1_delivered_even_when_queue_full(self):
        """SEV1 alerts get fallback delivery when queue is full."""
        from src.alerts.hub import NotificationHub

        mock_repo = AsyncMock()
        mock_repo.record_delivery_attempt = AsyncMock(return_value=uuid4())
        mock_repo.update_delivery_status = AsyncMock()

        mock_channel = AsyncMock(spec=NotificationChannel)
        mock_channel.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=200))

        hub = NotificationHub(
            repository=mock_repo,
            channels={"webhook": mock_channel},
            max_queue_size=1,  # Very small queue
        )

        # Fill queue
        filler = create_alert(type=AlertType.ORDER_FILLED, severity=Severity.SEV3, summary="Filler")
        await hub.enqueue(filler)

        # SEV1 should still be delivered via fallback
        sev1 = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Critical",
        )

        with patch(
            "src.alerts.hub.get_destinations_for_alert",
            return_value=[("webhook", "http://hook")],
        ):
            result = await hub.enqueue(sev1)

        assert result is True
        mock_channel.send.assert_called_once()
