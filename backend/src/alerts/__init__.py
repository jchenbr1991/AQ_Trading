"""Alert system package.

This package provides a complete alert system for the AQ Trading platform,
including:
- Alert models and types
- JSON serialization utilities
- Alert factory and validation
- Notification channels (Email, Webhook)
- Routing configuration
- Async delivery with NotificationHub
- AlertService as the main entry point
"""

from src.alerts.channels import (
    DeliveryResult,
    EmailChannel,
    NotificationChannel,
    WebhookChannel,
)
from src.alerts.factory import (
    COOLDOWN_WINDOW_MINUTES,
    compute_dedupe_key,
    create_alert,
    validate_alert,
)
from src.alerts.hub import (
    SELF_ALERT_TYPES,
    NotificationHub,
)
from src.alerts.models import (
    MAX_DETAILS_BYTES,
    MAX_KEYS,
    MAX_STRING_VALUE_LENGTH,
    RECOVERY_TYPES,
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    Severity,
    sanitize_details,
    to_json_safe,
)
from src.alerts.repository import AlertRepository
from src.alerts.routing import (
    DESTINATION_ENV_MAP,
    RoutingConfig,
    get_destinations_for_alert,
    resolve_destination,
)
from src.alerts.service import AlertService
from src.alerts.setup import (
    get_alert_service,
    init_alert_service,
)

__all__ = [
    # Models
    "AlertEvent",
    "AlertType",
    "EntityRef",
    "JsonScalar",
    "RECOVERY_TYPES",
    "Severity",
    # Constants
    "COOLDOWN_WINDOW_MINUTES",
    "DESTINATION_ENV_MAP",
    "MAX_DETAILS_BYTES",
    "MAX_KEYS",
    "MAX_STRING_VALUE_LENGTH",
    "SELF_ALERT_TYPES",
    # Factory
    "compute_dedupe_key",
    "create_alert",
    "validate_alert",
    # Serialization
    "sanitize_details",
    "to_json_safe",
    # Channels
    "DeliveryResult",
    "EmailChannel",
    "NotificationChannel",
    "WebhookChannel",
    # Hub
    "NotificationHub",
    # Repository
    "AlertRepository",
    # Routing
    "RoutingConfig",
    "get_destinations_for_alert",
    "resolve_destination",
    # Service
    "AlertService",
    "get_alert_service",
    "init_alert_service",
]
