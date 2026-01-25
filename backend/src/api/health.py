# backend/src/api/health.py
"""Health monitoring API endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from src.health.models import ComponentStatus
from src.health.monitor import HealthMonitor

router = APIRouter(prefix="/api/health", tags=["health"])


class ComponentHealthResponse(BaseModel):
    """Response for single component health."""

    component: str
    status: str
    latency_ms: float | None
    last_check: datetime
    message: str | None


class SystemHealthResponse(BaseModel):
    """Response for system-wide health."""

    overall_status: str
    components: list[ComponentHealthResponse]
    checked_at: datetime


_health_monitor: HealthMonitor | None = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance."""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor(checkers=[])
    return _health_monitor


def set_health_monitor(monitor: HealthMonitor) -> None:
    """Set the global health monitor instance."""
    global _health_monitor
    _health_monitor = monitor


@router.get("/detailed", response_model=SystemHealthResponse)
async def get_detailed_health(response: Response) -> SystemHealthResponse:
    """Get detailed health status of all components.

    Returns 200 if healthy, 503 if degraded or down.
    """
    monitor = get_health_monitor()
    health = await monitor.check_all()

    result = SystemHealthResponse(
        overall_status=health.overall_status.value,
        components=[
            ComponentHealthResponse(
                component=c.component,
                status=c.status.value,
                latency_ms=c.latency_ms,
                last_check=c.last_check,
                message=c.message,
            )
            for c in health.components
        ],
        checked_at=health.checked_at,
    )

    if health.overall_status != ComponentStatus.HEALTHY:
        response.status_code = 503

    return result


@router.get("/component/{component_name}", response_model=ComponentHealthResponse)
async def get_component_health(component_name: str) -> ComponentHealthResponse:
    """Get health status for a specific component."""
    monitor = get_health_monitor()
    status = await monitor.get_component(component_name)

    if status is None:
        raise HTTPException(status_code=404, detail=f"Component '{component_name}' not found")

    return ComponentHealthResponse(
        component=status.component,
        status=status.status.value,
        latency_ms=status.latency_ms,
        last_check=status.last_check,
        message=status.message,
    )
