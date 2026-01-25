"""Health monitoring models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ComponentStatus(str, Enum):
    """Status of a system component."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class HealthStatus:
    """Health status of a single component.

    Attributes:
        component: Name of the component (redis, postgres, market_data)
        status: Current status
        latency_ms: Response time in milliseconds, None if check failed
        last_check: Timestamp of last health check
        message: Optional status message (usually for errors)
    """

    component: str
    status: ComponentStatus
    latency_ms: float | None
    last_check: datetime
    message: str | None


@dataclass
class SystemHealth:
    """Aggregate health status of the entire system.

    Attributes:
        overall_status: HEALTHY if all components healthy,
                       DEGRADED if any component is down,
                       DOWN if critical components are down
        components: List of individual component statuses
        checked_at: When this aggregate was computed
    """

    overall_status: ComponentStatus
    components: list[HealthStatus]
    checked_at: datetime
