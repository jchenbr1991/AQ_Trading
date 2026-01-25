"""Health monitoring service that aggregates component health checks."""

import asyncio
from collections.abc import Sequence
from datetime import datetime, timezone

from src.health.checkers import HealthChecker
from src.health.models import ComponentStatus, HealthStatus, SystemHealth


class HealthMonitor:
    """Aggregates health checks from multiple components.

    Runs all checks concurrently and computes overall system health.
    """

    def __init__(self, checkers: Sequence[HealthChecker]) -> None:
        """Initialize with list of health checkers.

        Args:
            checkers: List of HealthChecker implementations
        """
        self._checkers = list(checkers)
        self._last_results: dict[str, HealthStatus] = {}

    async def check_all(self) -> SystemHealth:
        """Run all health checks concurrently.

        Returns:
            SystemHealth with overall status and individual component statuses
        """
        # Run all checks concurrently
        results = await asyncio.gather(
            *[checker.check() for checker in self._checkers],
            return_exceptions=True,
        )

        # Process results
        component_statuses: list[HealthStatus] = []
        for result in results:
            if isinstance(result, Exception):
                # Checker itself failed
                component_statuses.append(
                    HealthStatus(
                        component="unknown",
                        status=ComponentStatus.DOWN,
                        latency_ms=None,
                        last_check=datetime.now(tz=timezone.utc),
                        message=f"Checker error: {result}",
                    )
                )
            else:
                component_statuses.append(result)
                self._last_results[result.component] = result

        # Compute overall status
        overall = self._compute_overall_status(component_statuses)

        return SystemHealth(
            overall_status=overall,
            components=component_statuses,
            checked_at=datetime.now(tz=timezone.utc),
        )

    async def get_component(self, component_name: str) -> HealthStatus | None:
        """Get health status for a specific component.

        Args:
            component_name: Name of the component

        Returns:
            HealthStatus if found, None otherwise
        """
        # Check cached results first
        if component_name in self._last_results:
            return self._last_results[component_name]

        # Run fresh check
        for checker in self._checkers:
            result = await checker.check()
            if result.component == component_name:
                self._last_results[component_name] = result
                return result

        return None

    def _compute_overall_status(self, statuses: list[HealthStatus]) -> ComponentStatus:
        """Compute overall system status from component statuses.

        Args:
            statuses: List of component health statuses

        Returns:
            HEALTHY if all healthy, DEGRADED if some down, DOWN if all down
        """
        if not statuses:
            return ComponentStatus.UNKNOWN

        down_count = sum(1 for s in statuses if s.status == ComponentStatus.DOWN)

        if down_count == 0:
            return ComponentStatus.HEALTHY
        elif down_count == len(statuses):
            return ComponentStatus.DOWN
        else:
            return ComponentStatus.DEGRADED
