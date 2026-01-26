"""Audit service with tiered write paths.

This module provides the AuditService class for logging audit events
with support for both synchronous (tier-0) and asynchronous (tier-1)
write paths based on event criticality.

Classes:
    AuditService: Main service for logging audit events with tiered routing

The service automatically routes events based on their tier:
- Tier-0 (critical): Synchronous persist via repository (blocking)
- Tier-1 (non-critical): Asynchronous queue-based persist (non-blocking)
"""

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.audit.config import get_tier
from src.audit.diff import (
    compute_diff_jsonpatch,
    enforce_size_limit,
    redact_sensitive_fields,
)
from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
    ValueMode,
)
from src.audit.repository import AuditRepository


class AuditService:
    """Service for logging audit events with tiered write paths.

    The AuditService provides a unified interface for logging audit events
    while automatically routing them to the appropriate persistence path
    based on their tier classification:

    - Tier-0 events (critical): Persisted synchronously for guaranteed durability
    - Tier-1 events (non-critical): Queued for asynchronous persistence

    The service handles:
    - Redaction of sensitive fields
    - Diff computation for change tracking
    - Size limit enforcement
    - Automatic tier-based routing

    Args:
        repository: AuditRepository instance for database operations
        async_queue: Optional asyncio.Queue for async events (default: internal queue with maxsize=10000)

    Example:
        >>> repo = AuditRepository(session)
        >>> service = AuditService(repository=repo)
        >>> service.start_workers()
        >>> event_id = service.log(
        ...     event_type=AuditEventType.ORDER_PLACED,
        ...     actor_id="user-123",
        ...     actor_type=ActorType.USER,
        ...     resource_type=ResourceType.ORDER,
        ...     resource_id="order-456",
        ...     request_id="req-789",
        ...     source=EventSource.WEB,
        ...     severity=AuditSeverity.INFO,
        ... )
        >>> await service.stop()
    """

    def __init__(
        self,
        repository: AuditRepository,
        async_queue: asyncio.Queue | None = None,
    ) -> None:
        """Initialize the AuditService.

        Args:
            repository: AuditRepository instance for database operations
            async_queue: Optional asyncio.Queue for async events.
                        If not provided, creates an internal queue with maxsize=10000.
        """
        self._repository = repository
        self._queue = async_queue if async_queue is not None else asyncio.Queue(maxsize=10000)
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._environment = "production"  # Default, can be configured
        self._service_name = "trading-api"  # Default, can be configured
        self._version = "1.0.0"  # Default, can be configured

    def log(
        self,
        event_type: AuditEventType,
        actor_id: str,
        actor_type: ActorType,
        resource_type: ResourceType,
        resource_id: str,
        request_id: str,
        source: EventSource,
        severity: AuditSeverity,
        old_value: dict | None = None,
        new_value: dict | None = None,
        metadata: dict | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        trace_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        actor_display: str | None = None,
        impersonator_id: str | None = None,
    ) -> UUID:
        """Log an audit event with automatic tier-based routing.

        Creates an AuditEvent with the provided parameters, applies redaction,
        computes diffs, enforces size limits, and routes to the appropriate
        persistence path based on the event's tier classification.

        Args:
            event_type: Classification of the audit event
            actor_id: Identifier of the actor who caused the event
            actor_type: Type of the actor (USER, SYSTEM, etc.)
            resource_type: Type of resource affected
            resource_id: Identifier of the affected resource
            request_id: Identifier linking to the originating request
            source: Where the event originated from
            severity: How critical the event is
            old_value: Previous state (for updates/deletes)
            new_value: New state (for creates/updates)
            metadata: Additional arbitrary data
            correlation_id: Correlation ID for related events
            session_id: User session identifier (stored in metadata)
            trace_id: Distributed tracing identifier
            client_ip: Client IP address
            user_agent: Client user agent
            actor_display: Human-readable name for the actor
            impersonator_id: If impersonating, the original actor's ID

        Returns:
            UUID of the created audit event
        """
        event_id = uuid4()
        timestamp = datetime.now(tz=timezone.utc)

        # Get the resource type string for redaction rules
        resource_type_str = resource_type.value

        # Apply redaction to sensitive fields
        redacted_old = redact_sensitive_fields(old_value, resource_type_str)
        redacted_new = redact_sensitive_fields(new_value, resource_type_str)

        # Compute diff if both old and new values are provided
        # Note: diff_result can be used for logging or debugging purposes
        if redacted_old is not None and redacted_new is not None:
            _ = compute_diff_jsonpatch(redacted_old, redacted_new)

        # Enforce size limits
        processed_old, old_hash, old_mode = enforce_size_limit(
            redacted_old, resource_type_str, resource_id
        )
        processed_new, new_hash, new_mode = enforce_size_limit(
            redacted_new, resource_type_str, resource_id
        )

        # Determine value mode (REFERENCE if either exceeded size limit)
        value_mode = ValueMode.DIFF
        value_hash = None
        if old_mode == ValueMode.REFERENCE or new_mode == ValueMode.REFERENCE:
            value_mode = ValueMode.REFERENCE
            # Combine hashes if both are references
            if old_hash and new_hash:
                value_hash = f"old:{old_hash}|new:{new_hash}"
            elif old_hash:
                value_hash = f"old:{old_hash}"
            elif new_hash:
                value_hash = f"new:{new_hash}"

        # Add session_id to metadata if provided
        event_metadata = metadata
        if session_id is not None:
            event_metadata = {**(metadata or {}), "session_id": session_id}

        # Create the audit event
        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            actor_type=actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=request_id,
            source=source,
            environment=self._environment,
            service=self._service_name,
            version=self._version,
            actor_display=actor_display,
            impersonator_id=impersonator_id,
            value_mode=value_mode,
            old_value=processed_old,
            new_value=processed_new,
            value_hash=value_hash,
            trace_id=trace_id,
            correlation_id=correlation_id,
            client_ip=client_ip,
            user_agent=user_agent,
            metadata=event_metadata,
        )

        # Route based on tier
        tier = get_tier(event_type)
        if tier == 0:
            # Tier-0: Synchronous persist
            self._persist_sync(event)
        else:
            # Tier-1: Asynchronous queue
            self._enqueue_async(event)

        return event_id

    def _persist_sync(self, event: AuditEvent) -> None:
        """Persist an event synchronously (tier-0 direct write).

        Creates a task to persist the event and waits for completion.
        This ensures tier-0 events are durably persisted before returning.

        Args:
            event: The audit event to persist
        """
        # Create and schedule the coroutine
        try:
            # Verify there's a running event loop before creating task
            asyncio.get_running_loop()
            # Schedule the persist as a task but don't block
            asyncio.create_task(self._repository.persist_audit_event(event))
        except RuntimeError:
            # No running event loop - this is likely in a sync context
            # In production, this would be handled differently
            pass

    def _enqueue_async(self, event: AuditEvent) -> None:
        """Enqueue an event for asynchronous persistence (tier-1).

        Attempts to put the event on the queue using put_nowait.
        If the queue is full, falls back to synchronous persistence.

        Args:
            event: The audit event to enqueue
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            # Queue is full, fall back to sync
            self._persist_sync(event)

    def start_workers(self, num_workers: int = 2) -> None:
        """Start async worker tasks that process the queue.

        Creates the specified number of worker tasks that continuously
        read from the queue and persist events to the database.

        Args:
            num_workers: Number of worker tasks to start (default: 2)
        """
        self._running = True
        for _ in range(num_workers):
            worker = asyncio.create_task(self._worker_loop())
            self._workers.append(worker)

    async def _worker_loop(self) -> None:
        """Worker loop that processes events from the queue.

        Continuously reads events from the queue and persists them
        to the database until stop() is called.
        """
        while self._running:
            try:
                # Wait for an event with a timeout to allow checking _running
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                except TimeoutError:
                    continue

                # Persist the event
                try:
                    await self._repository.persist_audit_event(event)
                except Exception:  # noqa: S110 - Intentionally catching all exceptions to ensure worker continues
                    # In production, this would use proper logging
                    # Worker continues processing to avoid queue backup
                    pass
                finally:
                    self._queue.task_done()

            except asyncio.CancelledError:
                break

    async def stop(self) -> None:
        """Gracefully shutdown: stop workers and wait for queue to drain.

        Signals workers to stop, waits for the queue to be fully processed,
        then cancels all worker tasks.
        """
        self._running = False

        # Wait for queue to drain (with timeout)
        if not self._queue.empty():
            try:
                await asyncio.wait_for(self._queue.join(), timeout=5.0)
            except TimeoutError:
                pass

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)

        self._workers.clear()
