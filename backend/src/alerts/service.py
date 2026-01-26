"""AlertService module for emitting alerts.

This module provides the AlertService class - the main entry point for
emitting alerts in the trading system. All business modules use this
service to send notifications.

Usage:
    from src.alerts.service import AlertService

    service = AlertService(repository=alert_repo, hub=notification_hub)
    success = await service.emit(alert)

    # Persist only (no notification delivery)
    success = await service.emit(alert, send=False)
"""

import logging
from typing import TYPE_CHECKING

from src.alerts.factory import validate_alert
from src.alerts.models import RECOVERY_TYPES, AlertEvent

if TYPE_CHECKING:
    from src.alerts.hub import NotificationHub
    from src.alerts.repository import AlertRepository

logger = logging.getLogger(__name__)


class AlertService:
    """Main service for emitting alerts.

    Business modules use this to emit alerts. This is the ONLY entry point
    for sending notifications in the system.

    Features:
    - Validates alerts before persisting
    - Deduplication: doesn't send if alert already exists (unless recovery type)
    - send=False allows persist-only mode (useful for ALERT_DELIVERY_FAILED)
    - Never raises exceptions - returns False on failure

    Example:
        service = AlertService(repository=alert_repo, hub=notification_hub)

        # Create and emit an alert
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected: insufficient funds",
        )
        success = await service.emit(alert)
    """

    def __init__(self, repository: "AlertRepository", hub: "NotificationHub"):
        """Initialize AlertService.

        Args:
            repository: AlertRepository for persisting alerts
            hub: NotificationHub for delivering notifications
        """
        self._repo = repository
        self._hub = hub

    async def emit(self, alert: AlertEvent, *, send: bool = True) -> bool:
        """Emit an alert.

        This method:
        1. Validates the alert
        2. Persists to database (with deduplication)
        3. If send=True and should_send: enqueues for delivery

        Args:
            alert: Alert event to emit
            send: If False, only persist (don't send notifications).
                  Use this for ALERT_DELIVERY_FAILED to avoid recursion.

        Returns:
            True if alert was processed successfully, False on any error
        """
        try:
            # Step 1: Validate alert
            validate_alert(alert)

            # Step 2: Persist alert
            is_new, alert_id = await self._repo.persist_alert(alert)

            # Step 3: Check if we should send
            if not send:
                # Persist only mode
                return True

            # Step 4: Decide whether to enqueue
            if is_new or alert.type in RECOVERY_TYPES:
                # New alert or recovery type - send notification
                await self._hub.enqueue(alert)
            else:
                # Deduplicated - don't send
                logger.debug(
                    "Alert deduplicated (alert_id=%s, type=%s, fingerprint=%s)",
                    alert.alert_id,
                    alert.type.value,
                    alert.fingerprint,
                )

            return True

        except Exception as e:
            logger.error(
                "Error emitting alert (alert_id=%s, type=%s): %s",
                alert.alert_id,
                alert.type.value,
                e,
            )
            return False
