"""Audit system initialization.

This module provides functions to initialize and access the global AuditService
instance. The AuditService is the main entry point for logging audit events
throughout the application.

Usage:
    from src.audit.setup import init_audit_service, get_audit_service

    # During startup (with a database session):
    service = init_audit_service(db_session)

    # Later, anywhere in the app:
    service = get_audit_service()
    if service:
        event_id = service.log(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
        )

Example integration for other modules:
    # In an order handler:
    from src.audit.setup import get_audit_service
    from src.audit.models import ActorType, AuditEventType, AuditSeverity, EventSource, ResourceType

    async def place_order(order: Order, user_id: str, request_id: str):
        # ... place order logic ...

        service = get_audit_service()
        if service:
            service.log(
                event_type=AuditEventType.ORDER_PLACED,
                actor_id=user_id,
                actor_type=ActorType.USER,
                resource_type=ResourceType.ORDER,
                resource_id=str(order.id),
                request_id=request_id,
                source=EventSource.API,
                severity=AuditSeverity.INFO,
                new_value={"symbol": order.symbol, "quantity": order.quantity},
            )

    # Using AuditContext for request-scoped auditing:
    from src.audit.factory import AuditContext
    from src.audit.setup import get_audit_service

    async def handle_request(request):
        service = get_audit_service()
        if service:
            async with AuditContext(
                request_id=request.id,
                actor_id=request.user_id,
                actor_type=ActorType.USER,
                source=EventSource.WEB,
                service=service,
            ) as ctx:
                # Log multiple events with same context
                ctx.log(
                    event_type=AuditEventType.CONFIG_UPDATED,
                    resource_type=ResourceType.CONFIG,
                    resource_id="risk-limits",
                    severity=AuditSeverity.WARNING,
                    old_value={"max_position": 1000},
                    new_value={"max_position": 2000},
                )
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.audit.repository import AuditRepository
from src.audit.service import AuditService

logger = logging.getLogger(__name__)

_audit_service: AuditService | None = None


def init_audit_service(db_session: AsyncSession) -> AuditService:
    """Initialize audit service with database session.

    Creates the AuditRepository with the provided session and
    creates the AuditService with that repository. Stores the
    service in a global instance for access via get_audit_service().

    Args:
        db_session: Database session for persistence

    Returns:
        Configured AuditService instance
    """
    global _audit_service

    # Create repository
    repo = AuditRepository(db_session)

    # Create service
    _audit_service = AuditService(repository=repo)
    logger.info("AuditService initialized")

    return _audit_service


def get_audit_service() -> AuditService | None:
    """Get the global audit service instance.

    Returns:
        The initialized AuditService, or None if not yet initialized.
        Callers should check for None before using.
    """
    return _audit_service
