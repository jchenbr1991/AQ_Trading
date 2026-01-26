"""Alert system initialization.

This module provides functions to initialize and access the global AlertService
instance. The AlertService is the main entry point for emitting alerts throughout
the application.

Usage:
    from src.alerts.setup import init_alert_service, get_alert_service

    # During startup (with a database session):
    service = await init_alert_service(db_session)

    # Later, anywhere in the app:
    service = get_alert_service()
    if service:
        await service.emit(alert)

Example integration (for future use in health/monitor.py):
    from src.alerts.factory import create_alert
    from src.alerts.models import AlertType, Severity
    from src.alerts.setup import get_alert_service

    async def emit_health_alert(component: str, status: str):
        service = get_alert_service()
        if service:
            alert = create_alert(
                type=AlertType.COMPONENT_UNHEALTHY,
                severity=Severity.SEV1,
                summary=f"{component} is {status}",
            )
            await service.emit(alert)
"""

import logging
import os

from src.alerts.channels import EmailChannel, WebhookChannel
from src.alerts.hub import NotificationHub
from src.alerts.repository import AlertRepository
from src.alerts.service import AlertService

logger = logging.getLogger(__name__)

_alert_service: AlertService | None = None


async def init_alert_service(db_session) -> AlertService:
    """Initialize alert service with channels.

    Creates the AlertRepository, notification channels (email if configured,
    webhook always), NotificationHub with workers, and AlertService.

    Args:
        db_session: Database session for persistence

    Returns:
        Configured AlertService instance
    """
    global _alert_service

    # Create repository
    repo = AlertRepository(db_session)

    # Create channels
    channels = {}

    # Email channel (if configured)
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        channels["email"] = EmailChannel(
            smtp_host=smtp_host,
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            sender=os.getenv("SMTP_SENDER", "alerts@localhost"),
            username=os.getenv("SMTP_USERNAME"),
            password=os.getenv("SMTP_PASSWORD"),
        )
        logger.info("Email channel configured")

    # Webhook channel (always available)
    channels["webhook"] = WebhookChannel()
    logger.info("Webhook channel configured")

    # Create hub
    hub = NotificationHub(repository=repo, channels=channels)
    await hub.start(num_workers=2)

    # Create service
    _alert_service = AlertService(repository=repo, hub=hub)
    logger.info("AlertService initialized")

    return _alert_service


def get_alert_service() -> AlertService | None:
    """Get the global alert service instance.

    Returns:
        The initialized AlertService, or None if not yet initialized.
        Callers should check for None before using.
    """
    return _alert_service
