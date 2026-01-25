"""NotificationHub for async alert delivery with retry.

This module provides the NotificationHub class which handles:
- Async queue-based alert delivery with configurable workers
- Exponential backoff retry for failed deliveries
- Fallback synchronous delivery for SEV1 alerts when queue is full
- Prevention of alert recursion for delivery failure alerts

Usage:
    from src.alerts.hub import NotificationHub

    hub = NotificationHub(
        repository=alert_repo,
        channels={"email": email_channel, "webhook": webhook_channel},
    )
    await hub.start(num_workers=3)

    # Enqueue alerts for async delivery
    await hub.enqueue(alert)

    # Shutdown gracefully
    await hub.stop()
"""

import asyncio
import logging
from typing import Any

from src.alerts.channels import NotificationChannel
from src.alerts.factory import create_alert
from src.alerts.models import AlertEvent, AlertType, Severity
from src.alerts.routing import get_destinations_for_alert

logger = logging.getLogger(__name__)

# Alert types that should not trigger more alerts (prevent recursion)
SELF_ALERT_TYPES: frozenset[AlertType] = frozenset({AlertType.ALERT_DELIVERY_FAILED})


class NotificationHub:
    """Async notification hub with queue-based delivery and retry logic.

    Features:
    - Background worker tasks process alerts from an async queue
    - Exponential backoff retry for failed deliveries
    - SEV1 alerts are never dropped (fallback sync delivery if queue full)
    - ALERT_DELIVERY_FAILED alerts don't trigger more alerts (prevent recursion)
    """

    def __init__(
        self,
        repository: Any,
        channels: dict[str, NotificationChannel],
        max_queue_size: int = 1000,
        max_retries: int = 5,
        retry_base_delay: float = 1.0,
        retry_multiplier: float = 2.0,
    ):
        """Initialize the NotificationHub.

        Args:
            repository: AlertRepository for persisting alerts and delivery records
            channels: Dictionary mapping channel type to NotificationChannel instance
            max_queue_size: Maximum number of alerts in the queue (default: 1000)
            max_retries: Maximum delivery attempts per destination (default: 5)
            retry_base_delay: Initial retry delay in seconds (default: 1.0)
            retry_multiplier: Multiplier for exponential backoff (default: 2.0)
        """
        self.repository = repository
        self.channels = channels
        self.max_queue_size = max_queue_size
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_multiplier = retry_multiplier

        self._queue: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._workers: list[asyncio.Task[None]] = []
        self._running = False

    async def start(self, num_workers: int = 3) -> None:
        """Start worker tasks for processing the alert queue.

        Args:
            num_workers: Number of concurrent worker tasks (default: 3)
        """
        self._running = True
        for worker_id in range(num_workers):
            task = asyncio.create_task(
                self._worker(worker_id), name=f"notification_worker_{worker_id}"
            )
            self._workers.append(task)
        logger.info("NotificationHub started with %d workers", num_workers)

    async def stop(self) -> None:
        """Stop all worker tasks gracefully."""
        self._running = False

        if not self._workers:
            return

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for all workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("NotificationHub stopped")

    async def enqueue(self, alert: AlertEvent) -> bool:
        """Add an alert to the delivery queue.

        For SEV1 alerts when queue is full, uses fallback synchronous delivery.
        For non-SEV1 alerts when queue is full, logs warning and returns False.

        Args:
            alert: The alert event to deliver

        Returns:
            True if alert was queued (or delivered via fallback), False if dropped
        """
        try:
            self._queue.put_nowait(alert)
            return True
        except asyncio.QueueFull:
            if alert.severity == Severity.SEV1:
                # SEV1 alerts are never dropped - use fallback
                logger.warning(
                    "Queue full, using fallback sync delivery for SEV1 alert %s",
                    alert.alert_id,
                )
                await self._fallback_sync_send(alert)
                return True
            else:
                logger.warning(
                    "Queue full, dropping non-SEV1 alert %s (type=%s, severity=SEV%d)",
                    alert.alert_id,
                    alert.type.value,
                    alert.severity.value,
                )
                return False

    async def _worker(self, worker_id: int) -> None:
        """Worker loop that continuously processes alerts from the queue.

        Args:
            worker_id: Identifier for this worker (for logging)
        """
        logger.debug("Worker %d starting", worker_id)
        while self._running:
            try:
                await self._process_one()
            except asyncio.CancelledError:
                logger.debug("Worker %d cancelled", worker_id)
                raise
            except Exception as e:
                logger.exception("Worker %d error processing alert: %s", worker_id, e)
                # Continue processing after error
        logger.debug("Worker %d stopped", worker_id)

    async def _process_one(self) -> None:
        """Get one alert from the queue and deliver it."""
        try:
            # Use timeout to allow checking _running flag periodically
            alert = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except TimeoutError:
            return

        try:
            await self._deliver_alert(alert)
        finally:
            self._queue.task_done()

    async def _deliver_alert(self, alert: AlertEvent) -> None:
        """Deliver an alert to all configured destinations.

        Args:
            alert: The alert event to deliver
        """
        destinations = get_destinations_for_alert(alert)

        if not destinations:
            logger.debug(
                "No destinations for alert %s (type=%s, severity=SEV%d)",
                alert.alert_id,
                alert.type.value,
                alert.severity.value,
            )
            return

        for channel_type, destination in destinations:
            channel = self.channels.get(channel_type)
            if channel is None:
                logger.warning(
                    "Unknown channel type '%s' for alert %s, skipping",
                    channel_type,
                    alert.alert_id,
                )
                continue

            await self._deliver_with_retry(alert, channel, channel_type, destination)

    async def _deliver_with_retry(
        self,
        alert: AlertEvent,
        channel: NotificationChannel,
        channel_type: str,
        destination: str,
    ) -> bool:
        """Deliver an alert to a single destination with exponential backoff retry.

        Retry delays follow exponential backoff: base_delay * (multiplier ^ attempt)
        For defaults (base=1.0, multiplier=2.0): 1s, 2s, 4s, 8s, 16s

        Args:
            alert: The alert event to deliver
            channel: The notification channel to use
            channel_type: Type of channel (for logging and recording)
            destination: Destination address (email, webhook URL, etc.)

        Returns:
            True if delivery succeeded, False if all retries exhausted
        """
        last_error: str | None = None

        for attempt in range(1, self.max_retries + 1):
            # Record delivery attempt
            delivery_id = await self.repository.record_delivery_attempt(
                alert_id=alert.alert_id,
                channel=channel_type,
                destination_key=destination,
                attempt_number=attempt,
                status="pending",
            )

            try:
                result = await channel.send(alert, destination)

                if result.success:
                    await self.repository.update_delivery_status(
                        delivery_id=delivery_id,
                        status="sent",
                        response_code=result.response_code,
                    )
                    logger.debug(
                        "Alert %s delivered via %s to %s (attempt %d)",
                        alert.alert_id,
                        channel_type,
                        destination,
                        attempt,
                    )
                    return True
                else:
                    last_error = result.error_message or "Unknown error"
                    await self.repository.update_delivery_status(
                        delivery_id=delivery_id,
                        status="failed",
                        response_code=result.response_code,
                        error_message=last_error,
                    )
                    logger.warning(
                        "Alert %s delivery failed via %s (attempt %d/%d): %s",
                        alert.alert_id,
                        channel_type,
                        attempt,
                        self.max_retries,
                        last_error,
                    )
            except Exception as e:
                last_error = str(e)
                await self.repository.update_delivery_status(
                    delivery_id=delivery_id,
                    status="failed",
                    error_message=last_error,
                )
                logger.warning(
                    "Alert %s delivery exception via %s (attempt %d/%d): %s",
                    alert.alert_id,
                    channel_type,
                    attempt,
                    self.max_retries,
                    last_error,
                )

            # Wait before retry (except on last attempt)
            if attempt < self.max_retries:
                delay = self.retry_base_delay * (self.retry_multiplier ** (attempt - 1))
                await asyncio.sleep(delay)

        # All retries exhausted
        await self._handle_delivery_failure(alert, channel_type, last_error or "Unknown")
        return False

    async def _handle_delivery_failure(
        self, alert: AlertEvent, channel_type: str, error: str
    ) -> None:
        """Handle final delivery failure after all retries exhausted.

        For ALERT_DELIVERY_FAILED alerts: only log (prevent recursion)
        For SEV1 alerts: create ALERT_DELIVERY_FAILED alert (persist only)

        Args:
            alert: The original alert that failed delivery
            channel_type: The channel type that failed
            error: The error message from the last attempt
        """
        if alert.type in SELF_ALERT_TYPES:
            # Prevent recursion - just log critical
            logger.critical(
                "ALERT_DELIVERY_FAILED alert %s failed delivery via %s: %s "
                "(not creating new alert to prevent recursion)",
                alert.alert_id,
                channel_type,
                error,
            )
            return

        if alert.severity == Severity.SEV1:
            # Create ALERT_DELIVERY_FAILED alert for SEV1 failures
            failure_alert = create_alert(
                type=AlertType.ALERT_DELIVERY_FAILED,
                severity=Severity.SEV1,
                summary=f"Failed to deliver {alert.type.value.upper()} alert via {channel_type}",
                details={
                    "original_alert_id": str(alert.alert_id),
                    "original_type": alert.type.value,
                    "channel": channel_type,
                    "error": error,
                },
            )
            # Persist only - do not enqueue for delivery
            await self.repository.persist_alert(failure_alert)
            logger.error(
                "Created ALERT_DELIVERY_FAILED for SEV1 alert %s (failed via %s)",
                alert.alert_id,
                channel_type,
            )
        else:
            # Non-SEV1 failures are logged but don't create new alerts
            logger.error(
                "Alert %s (SEV%d) delivery failed via %s after all retries: %s",
                alert.alert_id,
                alert.severity.value,
                channel_type,
                error,
            )

    async def _fallback_sync_send(self, alert: AlertEvent) -> None:
        """Deliver a SEV1 alert synchronously when queue is full.

        This bypasses the queue and delivers directly to all destinations.

        Args:
            alert: The SEV1 alert to deliver immediately
        """
        destinations = get_destinations_for_alert(alert)

        for channel_type, destination in destinations:
            channel = self.channels.get(channel_type)
            if channel is None:
                logger.warning(
                    "Fallback: unknown channel type '%s' for alert %s, skipping",
                    channel_type,
                    alert.alert_id,
                )
                continue

            try:
                # Record delivery attempt
                delivery_id = await self.repository.record_delivery_attempt(
                    alert_id=alert.alert_id,
                    channel=channel_type,
                    destination_key=destination,
                    attempt_number=1,
                    status="pending",
                )

                result = await channel.send(alert, destination)

                if result.success:
                    await self.repository.update_delivery_status(
                        delivery_id=delivery_id,
                        status="sent",
                        response_code=result.response_code,
                    )
                    logger.info(
                        "Fallback: alert %s delivered via %s to %s",
                        alert.alert_id,
                        channel_type,
                        destination,
                    )
                else:
                    await self.repository.update_delivery_status(
                        delivery_id=delivery_id,
                        status="failed",
                        response_code=result.response_code,
                        error_message=result.error_message,
                    )
                    logger.error(
                        "Fallback: alert %s delivery failed via %s: %s",
                        alert.alert_id,
                        channel_type,
                        result.error_message,
                    )
            except Exception as e:
                logger.exception(
                    "Fallback: alert %s delivery exception via %s: %s",
                    alert.alert_id,
                    channel_type,
                    e,
                )
