"""EventBus for non-blocking event propagation.

CRITICAL: publish() must NEVER block. It uses put_nowait().
- Non-critical events are dropped when the queue is full (drop_count incremented)
- Critical events (in MUST_DELIVER_EVENTS) trigger _local_emergency_degrade() when dropped
- Fallback log written when events are dropped
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from src.degradation.config import DegradationConfig
from src.degradation.models import SystemEvent

logger = logging.getLogger(__name__)


class EventHandler(Protocol):
    """Protocol for event handlers."""

    async def __call__(self, event: SystemEvent) -> None:
        """Handle a system event."""
        ...


# Type alias for the emergency callback
EmergencyCallback = Callable[[SystemEvent], None]


class EventBus:
    """Non-blocking event bus for system events.

    The EventBus provides publish-subscribe functionality for SystemEvent instances.
    CRITICAL: publish() must NEVER block - it uses put_nowait().

    Key behaviors:
    - Non-critical events are silently dropped when queue is full
    - Critical events trigger local emergency degradation when dropped
    - All dropped events are written to fallback log
    - Subscribers are notified asynchronously via a dispatch task

    Attributes:
        drop_count: Number of events dropped due to queue full
        pending_count: Current number of events in the queue
        subscriber_count: Number of registered subscribers
        is_running: Whether the dispatch task is running
    """

    def __init__(
        self,
        config: DegradationConfig,
        fallback_log_path: Path | None = None,
    ) -> None:
        """Initialize the EventBus.

        Args:
            config: Degradation configuration containing queue size settings
            fallback_log_path: Path to write fallback log for dropped events
        """
        self._config = config
        self._queue: asyncio.Queue[SystemEvent] = asyncio.Queue(maxsize=config.event_bus_queue_size)
        self._subscribers: list[EventHandler] = []
        self._drop_count = 0
        self._fallback_log_path = fallback_log_path
        self._emergency_callback: EmergencyCallback | None = None
        self._dispatch_task: asyncio.Task[None] | None = None
        self._running = False

    @property
    def drop_count(self) -> int:
        """Number of events dropped due to queue full."""
        return self._drop_count

    @property
    def pending_count(self) -> int:
        """Current number of events in the queue."""
        return self._queue.qsize()

    @property
    def subscriber_count(self) -> int:
        """Number of registered subscribers."""
        return len(self._subscribers)

    @property
    def is_running(self) -> bool:
        """Whether the dispatch task is running."""
        return self._running

    async def publish(self, event: SystemEvent) -> bool:
        """Non-blocking publish. MUST use put_nowait.

        Attempts to add the event to the queue. If the queue is full,
        the event is dropped and handled according to its criticality.

        Args:
            event: The system event to publish

        Returns:
            True if event was queued, False if dropped
        """
        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._drop_count += 1
            self._write_fallback_log("QueueFull", event)

            if event.is_critical():
                self._local_emergency_degrade(event)

            return False

    def subscribe(self, handler: EventHandler) -> None:
        """Register a handler to receive events.

        Handlers are called asynchronously when events are dispatched.
        Errors in handlers are logged but do not stop the bus.

        Args:
            handler: Async callable that accepts a SystemEvent
        """
        self._subscribers.append(handler)

    def set_emergency_callback(self, callback: EmergencyCallback) -> None:
        """Set the callback for local emergency degradation.

        This callback is invoked when a critical event cannot be queued.
        It should trigger immediate local protective action.

        Args:
            callback: Sync callable that accepts a SystemEvent
        """
        self._emergency_callback = callback

    async def start(self) -> None:
        """Start the dispatch loop.

        Creates an asyncio task that continuously reads from the queue
        and notifies subscribers. Safe to call multiple times.
        """
        if self._running:
            return

        self._running = True
        self._dispatch_task = asyncio.create_task(self._dispatch_loop())
        logger.info("EventBus started")

    async def stop(self) -> None:
        """Stop the dispatch loop.

        Cancels the dispatch task and waits for it to complete.
        Safe to call multiple times.
        """
        if not self._running:
            return

        self._running = False

        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            try:
                await self._dispatch_task
            except asyncio.CancelledError:
                pass
            self._dispatch_task = None

        logger.info("EventBus stopped")

    async def _dispatch_loop(self) -> None:
        """Internal dispatch loop that reads from queue and notifies subscribers."""
        while self._running:
            try:
                # Wait for an event with timeout to allow checking _running flag
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.1)
                except TimeoutError:
                    continue

                # Notify all subscribers
                await self._notify_subscribers(event)
                self._queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in dispatch loop: {e}")

    async def _notify_subscribers(self, event: SystemEvent) -> None:
        """Notify all subscribers of an event.

        Errors in individual handlers are logged but do not prevent
        other handlers from receiving the event.

        Args:
            event: The event to dispatch to subscribers
        """
        for handler in self._subscribers:
            try:
                await handler(event)
            except Exception as e:
                logger.exception(f"Error in event handler: {e}")

    def _local_emergency_degrade(self, event: SystemEvent) -> None:
        """Trigger local emergency degradation for critical events.

        Called when a critical event cannot be queued. This should
        trigger immediate local protective action.

        Args:
            event: The critical event that could not be queued
        """
        logger.critical(
            f"Critical event dropped, triggering emergency degrade: {event.reason_code.value}"
        )

        if self._emergency_callback is not None:
            try:
                self._emergency_callback(event)
            except Exception as e:
                logger.exception(f"Error in emergency callback: {e}")

    def _write_fallback_log(self, reason: str, event: SystemEvent) -> None:
        """Write dropped event to fallback log file.

        Args:
            reason: Why the event was dropped (e.g., "QueueFull")
            event: The dropped event
        """
        if self._fallback_log_path is None:
            return

        try:
            log_entry = {
                "reason": reason,
                "event_type": event.event_type.value,
                "source": event.source.value,
                "severity": event.severity.value,
                "reason_code": event.reason_code.value,
                "event_time_wall": event.event_time_wall.isoformat(),
                "is_critical": event.is_critical(),
            }

            with open(self._fallback_log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

        except Exception as e:
            logger.exception(f"Error writing fallback log: {e}")
