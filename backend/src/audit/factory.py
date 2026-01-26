"""Audit factory and context manager for request-scoped auditing.

This module provides factory functions and a context manager for creating
audit events with consistent request context:

Functions:
    create_audit_event: Factory function to create validated AuditEvent instances
    audit_order_event: Convenience function for order-related audit events
    audit_config_change: Convenience function for configuration change events

Classes:
    AuditContext: Async context manager for request-scoped auditing

Example:
    >>> async with AuditContext(
    ...     request_id="req-123",
    ...     actor_id="user-456",
    ...     actor_type=ActorType.USER,
    ...     source=EventSource.WEB,
    ...     service=audit_service,
    ... ) as ctx:
    ...     ctx.log(
    ...         event_type=AuditEventType.ORDER_PLACED,
    ...         resource_type=ResourceType.ORDER,
    ...         resource_id="order-789",
    ...         severity=AuditSeverity.INFO,
    ...     )
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID, uuid4

from src.audit.config import get_value_mode
from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
)

if TYPE_CHECKING:
    from src.audit.service import AuditService


class OrderLike(Protocol):
    """Protocol for order-like objects that can be audited."""

    id: str


def create_audit_event(
    *,
    event_type: AuditEventType,
    actor_id: str,
    actor_type: ActorType,
    resource_type: ResourceType,
    resource_id: str,
    request_id: str,
    source: EventSource,
    severity: AuditSeverity,
    environment: str,
    service: str,
    version: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
    metadata: dict | None = None,
    correlation_id: str | None = None,
    trace_id: str | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    actor_display: str | None = None,
    impersonator_id: str | None = None,
) -> AuditEvent:
    """Create a validated AuditEvent with auto-generated UUID and timestamp.

    This factory function generates a unique UUID for the event, sets the
    timestamp to the current UTC time, validates required fields, and applies
    the appropriate value_mode based on the event type configuration.

    Args:
        event_type: Classification of the audit event.
        actor_id: Identifier of the actor who caused the event (must not be empty).
        actor_type: Type of the actor (USER, SYSTEM, etc.).
        resource_type: Type of resource affected.
        resource_id: Identifier of the affected resource (must not be empty).
        request_id: Identifier linking to the originating request (must not be empty).
        source: Where the event originated from.
        severity: How critical the event is.
        environment: Deployment environment (dev, staging, production).
        service: Name of the service that generated the event.
        version: Version of the service.
        old_value: Previous state (for updates/deletes).
        new_value: New state (for creates/updates).
        metadata: Additional arbitrary data.
        correlation_id: Correlation ID for related events.
        trace_id: Distributed tracing identifier.
        client_ip: Client IP address.
        user_agent: Client user agent.
        actor_display: Human-readable name for the actor.
        impersonator_id: If impersonating, the original actor's ID.

    Returns:
        A validated AuditEvent instance.

    Raises:
        ValueError: If actor_id, resource_id, or request_id is empty.
    """
    # Validate required string fields
    if not actor_id:
        raise ValueError("actor_id is required and cannot be empty")
    if not resource_id:
        raise ValueError("resource_id is required and cannot be empty")
    if not request_id:
        raise ValueError("request_id is required and cannot be empty")

    # Generate UUID and timestamp
    event_id = uuid4()
    timestamp = datetime.now(tz=timezone.utc)

    # Get value_mode from config based on event_type
    value_mode = get_value_mode(event_type)

    return AuditEvent(
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
        environment=environment,
        service=service,
        version=version,
        value_mode=value_mode,
        old_value=old_value,
        new_value=new_value,
        metadata=metadata,
        correlation_id=correlation_id,
        trace_id=trace_id,
        client_ip=client_ip,
        user_agent=user_agent,
        actor_display=actor_display,
        impersonator_id=impersonator_id,
    )


class AuditContext:
    """Async context manager for request-scoped auditing.

    AuditContext stores request context (request_id, actor_id, actor_type, source)
    and provides a log() method that automatically includes this context when
    logging audit events through the AuditService.

    This simplifies audit logging within a request handler by eliminating the
    need to pass request context to every audit call.

    Args:
        request_id: Identifier linking to the originating request.
        actor_id: Identifier of the actor who caused the events.
        actor_type: Type of the actor (USER, SYSTEM, etc.).
        source: Where the events originate from.
        service: AuditService instance for logging events.
        trace_id: Optional distributed tracing identifier.
        correlation_id: Optional correlation ID for related events.
        client_ip: Optional client IP address.
        user_agent: Optional client user agent.
        actor_display: Optional human-readable name for the actor.
        impersonator_id: Optional impersonator's ID if impersonating.

    Example:
        >>> async with AuditContext(
        ...     request_id="req-123",
        ...     actor_id="user-456",
        ...     actor_type=ActorType.USER,
        ...     source=EventSource.WEB,
        ...     service=audit_service,
        ... ) as ctx:
        ...     ctx.log(
        ...         event_type=AuditEventType.ORDER_PLACED,
        ...         resource_type=ResourceType.ORDER,
        ...         resource_id="order-789",
        ...         severity=AuditSeverity.INFO,
        ...     )
    """

    def __init__(
        self,
        request_id: str,
        actor_id: str,
        actor_type: ActorType,
        source: EventSource,
        service: AuditService,
        *,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
        actor_display: str | None = None,
        impersonator_id: str | None = None,
    ) -> None:
        """Initialize the AuditContext with request-scoped context."""
        self.request_id = request_id
        self.actor_id = actor_id
        self.actor_type = actor_type
        self.source = source
        self._service = service
        self.trace_id = trace_id
        self.correlation_id = correlation_id
        self.client_ip = client_ip
        self.user_agent = user_agent
        self.actor_display = actor_display
        self.impersonator_id = impersonator_id

    async def __aenter__(self) -> AuditContext:
        """Enter the async context, returning self."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit the async context."""
        pass

    def log(
        self,
        *,
        event_type: AuditEventType,
        resource_type: ResourceType,
        resource_id: str,
        severity: AuditSeverity,
        old_value: dict | None = None,
        new_value: dict | None = None,
        metadata: dict | None = None,
    ) -> UUID:
        """Log an audit event using the stored request context.

        This method delegates to the AuditService.log() method, automatically
        including the request context stored in this AuditContext.

        Args:
            event_type: Classification of the audit event.
            resource_type: Type of resource affected.
            resource_id: Identifier of the affected resource.
            severity: How critical the event is.
            old_value: Previous state (for updates/deletes).
            new_value: New state (for creates/updates).
            metadata: Additional arbitrary data.

        Returns:
            UUID of the created audit event.
        """
        return self._service.log(
            event_type=event_type,
            actor_id=self.actor_id,
            actor_type=self.actor_type,
            resource_type=resource_type,
            resource_id=resource_id,
            request_id=self.request_id,
            source=self.source,
            severity=severity,
            old_value=old_value,
            new_value=new_value,
            metadata=metadata,
            correlation_id=self.correlation_id,
            trace_id=self.trace_id,
            client_ip=self.client_ip,
            user_agent=self.user_agent,
            actor_display=self.actor_display,
            impersonator_id=self.impersonator_id,
        )


def audit_order_event(
    *,
    order: OrderLike,
    event_type: AuditEventType,
    old_status: str | None,
    new_status: str,
    ctx: AuditContext,
    severity: AuditSeverity = AuditSeverity.INFO,
) -> UUID:
    """Convenience function for logging order-related audit events.

    This helper function simplifies logging order events by:
    - Using the order's ID as the resource_id
    - Setting the resource_type to ORDER
    - Including status changes in old_value and new_value

    Args:
        order: The order object (must have an 'id' attribute).
        event_type: The type of order event (ORDER_PLACED, ORDER_FILLED, etc.).
        old_status: The previous order status (None for new orders).
        new_status: The new order status.
        ctx: The AuditContext with request-scoped context.
        severity: How critical the event is (default: INFO).

    Returns:
        UUID of the created audit event.
    """
    old_value = {"status": old_status} if old_status is not None else {"status": None}
    new_value = {"status": new_status}

    return ctx.log(
        event_type=event_type,
        resource_type=ResourceType.ORDER,
        resource_id=str(order.id),
        severity=severity,
        old_value=old_value,
        new_value=new_value,
    )


def audit_config_change(
    *,
    config_key: str,
    old_value: dict,
    new_value: dict,
    ctx: AuditContext,
    severity: AuditSeverity = AuditSeverity.WARNING,
) -> UUID:
    """Convenience function for logging configuration change events.

    This helper function simplifies logging config changes by:
    - Using the config_key as the resource_id
    - Setting the resource_type to CONFIG
    - Setting the event_type to CONFIG_UPDATED
    - Defaulting severity to WARNING (config changes are important)

    Args:
        config_key: The configuration key that was changed.
        old_value: The previous configuration value.
        new_value: The new configuration value.
        ctx: The AuditContext with request-scoped context.
        severity: How critical the event is (default: WARNING).

    Returns:
        UUID of the created audit event.
    """
    return ctx.log(
        event_type=AuditEventType.CONFIG_UPDATED,
        resource_type=ResourceType.CONFIG,
        resource_id=config_key,
        severity=severity,
        old_value=old_value,
        new_value=new_value,
    )
