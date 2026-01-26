"""Tests for EventBus with drop-on-full behavior."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from src.degradation.config import DegradationConfig
from src.degradation.event_bus import EventBus
from src.degradation.models import (
    ComponentSource,
    EventType,
    ReasonCode,
    Severity,
    SystemEvent,
    create_event,
)


@pytest.fixture
def config() -> DegradationConfig:
    """Create a test config with small queue size for testing."""
    return DegradationConfig(event_bus_queue_size=3)


@pytest.fixture
def fallback_log_path(tmp_path: Path) -> Path:
    """Create a temporary fallback log path."""
    return tmp_path / "fallback.log"


@pytest.fixture
def event_bus(config: DegradationConfig, fallback_log_path: Path) -> EventBus:
    """Create an EventBus instance for testing."""
    return EventBus(config=config, fallback_log_path=fallback_log_path)


def create_test_event(
    reason_code: ReasonCode = ReasonCode.MD_STALE,
    severity: Severity = Severity.WARNING,
) -> SystemEvent:
    """Create a test event with sensible defaults."""
    return create_event(
        event_type=EventType.FAIL_SUPP,
        source=ComponentSource.MARKET_DATA,
        severity=severity,
        reason_code=reason_code,
    )


def create_critical_event() -> SystemEvent:
    """Create a critical event that's in MUST_DELIVER_EVENTS."""
    return create_event(
        event_type=EventType.FAIL_CRIT,
        source=ComponentSource.BROKER,
        severity=Severity.CRITICAL,
        reason_code=ReasonCode.BROKER_DISCONNECT,
    )


class TestPublishSuccess:
    """Tests for successful event publishing."""

    @pytest.mark.asyncio
    async def test_publish_success(self, event_bus: EventBus) -> None:
        """Event should be added to queue on publish."""
        event = create_test_event()

        result = await event_bus.publish(event)

        assert result is True
        assert event_bus.pending_count == 1

    @pytest.mark.asyncio
    async def test_publish_multiple_events(self, event_bus: EventBus) -> None:
        """Multiple events should be added to queue."""
        events = [create_test_event() for _ in range(3)]

        for event in events:
            result = await event_bus.publish(event)
            assert result is True

        assert event_bus.pending_count == 3

    @pytest.mark.asyncio
    async def test_publish_returns_true_on_success(self, event_bus: EventBus) -> None:
        """publish() should return True when event is queued."""
        event = create_test_event()
        result = await event_bus.publish(event)
        assert result is True


class TestPublishNonBlocking:
    """Tests for non-blocking publish behavior."""

    @pytest.mark.asyncio
    async def test_publish_non_blocking(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """publish() should not block when queue is full."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # This should complete immediately, not block
        start_time = asyncio.get_event_loop().time()
        result = await bus.publish(create_test_event())
        elapsed = asyncio.get_event_loop().time() - start_time

        # Should complete in under 100ms (non-blocking)
        assert elapsed < 0.1
        assert result is False

    @pytest.mark.asyncio
    async def test_publish_uses_put_nowait(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """publish() must use put_nowait internally."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Mock the queue to verify put_nowait is called
        original_queue = bus._queue
        mock_queue = MagicMock()
        mock_queue.put_nowait = MagicMock()
        bus._queue = mock_queue

        event = create_test_event()
        await bus.publish(event)

        mock_queue.put_nowait.assert_called_once_with(event)

        # Restore original queue
        bus._queue = original_queue


class TestDropOnFullNonCritical:
    """Tests for non-critical event dropping when queue is full."""

    @pytest.mark.asyncio
    async def test_drop_on_full_non_critical(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Non-critical events should be dropped when queue is full."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Attempt to publish another non-critical event
        result = await bus.publish(create_test_event())

        assert result is False
        assert bus.drop_count == 1

    @pytest.mark.asyncio
    async def test_drop_count_increments(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Drop count should increment for each dropped event."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Drop 3 events
        for _ in range(3):
            await bus.publish(create_test_event())

        assert bus.drop_count == 3

    @pytest.mark.asyncio
    async def test_queue_remains_at_max_size_after_drop(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Queue size should remain at max after drops."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Try to add more
        await bus.publish(create_test_event())
        await bus.publish(create_test_event())

        assert bus.pending_count == config.event_bus_queue_size


class TestCriticalEventTriggersLocalFallback:
    """Tests for critical event handling when queue is full."""

    @pytest.mark.asyncio
    async def test_critical_event_triggers_local_fallback(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Critical events should trigger local emergency degrade when dropped."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)
        callback_called = False
        callback_event = None

        def emergency_callback(event: SystemEvent) -> None:
            nonlocal callback_called, callback_event
            callback_called = True
            callback_event = event

        bus.set_emergency_callback(emergency_callback)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Publish a critical event
        critical_event = create_critical_event()
        result = await bus.publish(critical_event)

        assert result is False
        assert callback_called is True
        assert callback_event == critical_event

    @pytest.mark.asyncio
    async def test_critical_event_also_increments_drop_count(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Critical events should also increment drop count when dropped."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Drop a critical event
        await bus.publish(create_critical_event())

        assert bus.drop_count == 1

    @pytest.mark.asyncio
    async def test_critical_event_writes_fallback_log(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Critical events should also be written to fallback log."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Drop a critical event
        critical_event = create_critical_event()
        await bus.publish(critical_event)

        # Check fallback log was written
        assert fallback_log_path.exists()
        log_content = fallback_log_path.read_text()
        assert "QueueFull" in log_content
        assert critical_event.reason_code.value in log_content


class TestSubscribeReceivesEvents:
    """Tests for subscriber functionality."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_events(self, event_bus: EventBus) -> None:
        """Subscribers should receive published events."""
        received_events: list[SystemEvent] = []

        async def handler(event: SystemEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(handler)

        # Start the event bus
        await event_bus.start()

        try:
            # Publish an event
            event = create_test_event()
            await event_bus.publish(event)

            # Give the dispatcher time to process
            await asyncio.sleep(0.1)

            assert len(received_events) == 1
            assert received_events[0] == event
        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_multiple_subscribers_receive_events(self, event_bus: EventBus) -> None:
        """All subscribers should receive each event."""
        received_1: list[SystemEvent] = []
        received_2: list[SystemEvent] = []

        async def handler1(event: SystemEvent) -> None:
            received_1.append(event)

        async def handler2(event: SystemEvent) -> None:
            received_2.append(event)

        event_bus.subscribe(handler1)
        event_bus.subscribe(handler2)

        await event_bus.start()

        try:
            event = create_test_event()
            await event_bus.publish(event)

            await asyncio.sleep(0.1)

            assert len(received_1) == 1
            assert len(received_2) == 1
            assert received_1[0] == event
            assert received_2[0] == event
        finally:
            await event_bus.stop()

    @pytest.mark.asyncio
    async def test_subscriber_error_does_not_stop_bus(self, event_bus: EventBus) -> None:
        """Errors in subscribers should not crash the bus."""
        received_events: list[SystemEvent] = []

        async def failing_handler(event: SystemEvent) -> None:
            raise ValueError("Handler error")

        async def working_handler(event: SystemEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(failing_handler)
        event_bus.subscribe(working_handler)

        await event_bus.start()

        try:
            event = create_test_event()
            await event_bus.publish(event)

            await asyncio.sleep(0.1)

            # Working handler should still receive event
            assert len(received_events) == 1
        finally:
            await event_bus.stop()


class TestFallbackLogOnDrop:
    """Tests for fallback logging when events are dropped."""

    @pytest.mark.asyncio
    async def test_fallback_log_on_drop(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Dropped events should be logged to fallback file."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Drop an event
        dropped_event = create_test_event(reason_code=ReasonCode.MD_QUALITY_DEGRADED)
        await bus.publish(dropped_event)

        # Check fallback log
        assert fallback_log_path.exists()
        log_content = fallback_log_path.read_text()
        assert "QueueFull" in log_content
        assert dropped_event.reason_code.value in log_content

    @pytest.mark.asyncio
    async def test_fallback_log_contains_event_details(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Fallback log should contain essential event details."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Drop an event
        dropped_event = create_test_event()
        await bus.publish(dropped_event)

        log_content = fallback_log_path.read_text()

        # Check essential fields are logged
        assert dropped_event.source.value in log_content
        assert dropped_event.event_type.value in log_content
        assert dropped_event.reason_code.value in log_content

    @pytest.mark.asyncio
    async def test_fallback_log_appends(
        self, config: DegradationConfig, fallback_log_path: Path
    ) -> None:
        """Multiple dropped events should all be logged."""
        bus = EventBus(config=config, fallback_log_path=fallback_log_path)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # Drop multiple events
        await bus.publish(create_test_event(reason_code=ReasonCode.MD_STALE))
        await bus.publish(create_test_event(reason_code=ReasonCode.MD_QUALITY_DEGRADED))

        log_content = fallback_log_path.read_text()

        assert log_content.count("QueueFull") == 2

    @pytest.mark.asyncio
    async def test_no_fallback_log_when_path_not_set(self, config: DegradationConfig) -> None:
        """No error when fallback_log_path is None."""
        bus = EventBus(config=config, fallback_log_path=None)

        # Fill the queue
        for _ in range(config.event_bus_queue_size):
            await bus.publish(create_test_event())

        # This should not raise, even without a log path
        result = await bus.publish(create_test_event())
        assert result is False


class TestLifecycle:
    """Tests for EventBus lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_begins_dispatch(self, event_bus: EventBus) -> None:
        """start() should begin dispatching events to subscribers."""
        received: list[SystemEvent] = []

        async def handler(event: SystemEvent) -> None:
            received.append(event)

        event_bus.subscribe(handler)

        # Publish before start - should queue but not dispatch
        event = create_test_event()
        await event_bus.publish(event)
        assert len(received) == 0

        # Start should begin dispatching
        await event_bus.start()
        await asyncio.sleep(0.1)

        assert len(received) == 1
        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_stop_stops_dispatch(self, event_bus: EventBus) -> None:
        """stop() should stop the dispatch loop."""
        await event_bus.start()
        assert event_bus.is_running is True

        await event_bus.stop()
        assert event_bus.is_running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self, event_bus: EventBus) -> None:
        """Calling start() twice should be safe."""
        await event_bus.start()
        await event_bus.start()  # Should not raise
        assert event_bus.is_running is True
        await event_bus.stop()

    @pytest.mark.asyncio
    async def test_double_stop_is_safe(self, event_bus: EventBus) -> None:
        """Calling stop() twice should be safe."""
        await event_bus.start()
        await event_bus.stop()
        await event_bus.stop()  # Should not raise
        assert event_bus.is_running is False


class TestMetrics:
    """Tests for EventBus metrics."""

    @pytest.mark.asyncio
    async def test_drop_count_starts_at_zero(self, event_bus: EventBus) -> None:
        """Drop count should start at zero."""
        assert event_bus.drop_count == 0

    @pytest.mark.asyncio
    async def test_pending_count_property(self, event_bus: EventBus) -> None:
        """pending_count should reflect current queue depth."""
        assert event_bus.pending_count == 0

        await event_bus.publish(create_test_event())
        assert event_bus.pending_count == 1

        await event_bus.publish(create_test_event())
        assert event_bus.pending_count == 2

    @pytest.mark.asyncio
    async def test_subscriber_count(self, event_bus: EventBus) -> None:
        """subscriber_count should reflect number of handlers."""
        assert event_bus.subscriber_count == 0

        async def handler1(event: SystemEvent) -> None:
            pass

        async def handler2(event: SystemEvent) -> None:
            pass

        event_bus.subscribe(handler1)
        assert event_bus.subscriber_count == 1

        event_bus.subscribe(handler2)
        assert event_bus.subscriber_count == 2
