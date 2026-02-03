"""Alert generation and delivery for governance monitoring.

This module provides the AlertGenerator class for creating alerts from
falsifier check results and delivering them through registered handlers.

Classes:
    AlertGenerator: Generates and delivers governance alerts

Spec Requirements:
    FR-026: Review alerts with hypothesis_id, triggered_falsifier, metric_value,
            threshold, recommended_action (review/sunset)
    FR-027: Notification delivery (configurable: log file, email, webhook)

Example:
    >>> from src.governance.monitoring.alerts import AlertGenerator
    >>> generator = AlertGenerator()
    >>> generator.add_handler(lambda alert: print(alert.message))
    >>> alert = generator.generate_from_check(check_result)
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.governance.models import AlertSeverity, TriggerAction
from src.governance.monitoring.models import Alert

if TYPE_CHECKING:
    from src.governance.monitoring.models import FalsifierCheckResult

logger = logging.getLogger(__name__)


class AlertGenerator:
    """Generates and delivers governance alerts.

    Creates Alert objects from falsifier check results when falsifiers
    are triggered. Supports multiple delivery handlers (log, email, webhook)
    that are called when an alert is generated.

    Attributes:
        _alerts: List of all generated alerts.
        _handlers: List of registered delivery handler callables.

    Example:
        >>> generator = AlertGenerator()
        >>> generator.add_handler(log_handler)
        >>> alert = generator.generate_from_check(triggered_result)
    """

    def __init__(self) -> None:
        """Initialize AlertGenerator with empty alert list and handler list."""
        self._alerts: list[Alert] = []
        self._handlers: list[Callable[[Alert], None]] = []

    def generate_from_check(self, result: FalsifierCheckResult) -> Alert | None:
        """Generate an alert from a falsifier check result.

        Only generates an alert if the falsifier was triggered.
        The alert severity is determined by the trigger action:
        - sunset -> CRITICAL
        - review -> WARNING

        The alert includes FR-026 required details:
        - hypothesis_id, triggered_falsifier (metric), metric_value,
          threshold, recommended_action

        Args:
            result: The FalsifierCheckResult to potentially generate an alert from.

        Returns:
            The generated Alert if the check was triggered, None otherwise.
        """
        if not result.triggered:
            return None

        # Determine severity based on trigger action
        if result.trigger_action == TriggerAction.SUNSET:
            severity = AlertSeverity.CRITICAL
        else:
            severity = AlertSeverity.WARNING

        alert = Alert(
            id=str(uuid.uuid4()),
            severity=severity,
            source="falsifier_checker",
            hypothesis_id=result.hypothesis_id,
            title=(
                f"Falsifier triggered: {result.metric} " f"for hypothesis '{result.hypothesis_id}'"
            ),
            message=(
                f"Falsifier [{result.falsifier_index}] triggered: "
                f"{result.metric}={result.metric_value} "
                f"{result.operator.value} {result.threshold} "
                f"(window={result.window}). "
                f"Recommended action: {result.trigger_action.value}"
            ),
            details={
                "hypothesis_id": result.hypothesis_id,
                "falsifier_index": result.falsifier_index,
                "metric": result.metric,
                "metric_value": result.metric_value,
                "operator": result.operator.value,
                "threshold": result.threshold,
                "window": result.window,
                "recommended_action": result.trigger_action.value,
            },
            created_at=datetime.now(timezone.utc),
        )

        # Store alert
        self._alerts.append(alert)

        # Deliver through handlers
        if self._handlers:
            self.deliver(alert)

        return alert

    def add_handler(self, handler: Callable[[Alert], None]) -> None:
        """Add an alert delivery handler.

        Handlers are callable that receive an Alert object. They can
        implement different delivery channels: log file, email, webhook, etc.

        Args:
            handler: Callable that accepts an Alert and delivers it.
        """
        self._handlers.append(handler)
        logger.debug(f"Added alert handler: {handler}")

    def deliver(self, alert: Alert) -> None:
        """Deliver an alert through all registered handlers.

        Calls each handler with the alert. If a handler raises an exception,
        it is logged but does not prevent other handlers from being called.

        After delivery, the alert's delivered flag is set to True.

        Args:
            alert: The Alert to deliver.
        """
        delivered = False
        for handler in self._handlers:
            try:
                handler(alert)
                delivered = True
            except Exception:
                logger.warning(
                    f"Alert handler raised exception for alert {alert.id}",
                    exc_info=True,
                )

        if delivered:
            alert.delivered = True

    def get_alerts(self) -> list[Alert]:
        """Get all generated alerts.

        Returns:
            List of all Alert objects generated by this generator.
        """
        return list(self._alerts)


__all__ = ["AlertGenerator"]
