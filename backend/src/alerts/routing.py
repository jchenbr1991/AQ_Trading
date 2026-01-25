"""Alert routing configuration module.

This module defines routing rules for alert delivery:
- RoutingConfig: Configurable routing rules for alerts
- DESTINATION_ENV_MAP: Maps destination keys to environment variable names
- resolve_destination: Resolves destination keys to actual addresses
- get_destinations_for_alert: Gets all delivery destinations for an alert

Routing logic:
1. Severity determines which channels are enabled (email, webhook)
2. Type recipients add alert-type-specific destinations
3. Global recipients apply to all alerts
4. All recipients are filtered by enabled channels for the severity
5. Destinations are resolved via environment variables
"""

import os
from dataclasses import dataclass, field

from src.alerts.models import AlertEvent, AlertType, Severity

# Maps destination keys to environment variable names
DESTINATION_ENV_MAP: dict[str, str] = {
    "email:default": "ALERT_EMAIL_DEFAULT",
    "email:risk": "ALERT_EMAIL_RISK",
    "email:ops": "ALERT_EMAIL_OPS",
    "webhook:default": "ALERT_WEBHOOK_DEFAULT",
    "webhook:wecom": "ALERT_WEBHOOK_WECOM",
}


@dataclass
class RoutingConfig:
    """Configuration for alert routing.

    Attributes:
        severity_channels: Maps severity levels to enabled channel types.
            SEV1 (Critical) -> email + webhook
            SEV2 (Warning) -> webhook only
            SEV3 (Info) -> no channels (log only)
        type_recipients: Maps alert types to specific destination keys.
            These are additional recipients beyond global_recipients.
        global_recipients: Default recipients for all alerts.
            Applied in addition to type-specific recipients.
    """

    severity_channels: dict[Severity, list[str]] = field(
        default_factory=lambda: {
            Severity.SEV1: ["email", "webhook"],
            Severity.SEV2: ["webhook"],
            Severity.SEV3: [],  # Log only
        }
    )
    type_recipients: dict[AlertType, list[str]] = field(
        default_factory=lambda: {
            AlertType.DAILY_LOSS_LIMIT: ["email:risk"],
            AlertType.KILL_SWITCH_ACTIVATED: ["email:ops", "email:risk"],
            AlertType.POSITION_LIMIT_HIT: ["email:risk"],
        }
    )
    global_recipients: list[str] = field(
        default_factory=lambda: [
            "email:default",
            "webhook:default",
        ]
    )

    def get_channels_for_severity(self, severity: Severity) -> list[str]:
        """Get enabled channel types for a severity level.

        Args:
            severity: The alert severity level

        Returns:
            List of enabled channel type strings (e.g., ["email", "webhook"])
        """
        return self.severity_channels.get(severity, [])


def resolve_destination(key: str) -> str | None:
    """Resolve a destination key to an actual address via environment variables.

    Args:
        key: Destination key (e.g., "email:default", "webhook:wecom")

    Returns:
        The resolved address from the environment variable, or None if not set
        or the key is unknown.
    """
    env_var_name = DESTINATION_ENV_MAP.get(key)
    if env_var_name is None:
        return None
    return os.getenv(env_var_name)


def get_destinations_for_alert(
    alert: AlertEvent, config: RoutingConfig | None = None
) -> list[tuple[str, str]]:
    """Get all delivery destinations for an alert.

    Routing logic:
    1. Get enabled channels for the alert's severity
    2. Collect destination keys from type_recipients (if alert type matches)
       and global_recipients
    3. Filter destinations by enabled channels
    4. Resolve each destination key to an actual address
    5. Return unique (channel_type, resolved_destination) tuples

    Args:
        alert: The AlertEvent to route
        config: Optional RoutingConfig, uses default if not provided

    Returns:
        List of (channel_type, resolved_destination) tuples for delivery
    """
    if config is None:
        config = RoutingConfig()

    # Get enabled channels for this severity
    enabled_channels = config.get_channels_for_severity(alert.severity)

    if not enabled_channels:
        return []

    # Collect all destination keys
    destination_keys: list[str] = []

    # Add type-specific recipients
    if alert.type in config.type_recipients:
        destination_keys.extend(config.type_recipients[alert.type])

    # Add global recipients
    destination_keys.extend(config.global_recipients)

    # Build result, filtering by enabled channels and resolving destinations
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []

    for key in destination_keys:
        # Extract channel type from key (e.g., "email" from "email:default")
        channel_type = key.split(":")[0]

        # Skip if channel not enabled for this severity
        if channel_type not in enabled_channels:
            continue

        # Resolve the destination
        resolved = resolve_destination(key)
        if resolved is None:
            continue

        # Add to result if not already present (deduplicate)
        dest_tuple = (channel_type, resolved)
        if dest_tuple not in seen:
            seen.add(dest_tuple)
            result.append(dest_tuple)

    return result
