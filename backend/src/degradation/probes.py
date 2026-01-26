"""Component probes for health checking.

Component probes provide health checking interfaces for recovery orchestration.
Each Hot Path component provides a probe interface that can be queried for
health status and triggered to restore ready state.

Key concepts:
- HealthSignal: Result of a health check (healthy, latency, message)
- ComponentProbe: Protocol defining the probe interface
- Concrete probes: BrokerProbe, MarketDataProbe, RiskProbe

Usage:
    probe = BrokerProbe()
    signal = await probe.health_check()
    if not signal.healthy:
        success = await probe.ensure_ready()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class HealthSignal:
    """Result of a health check.

    Captures the health status, latency, and optional message from a
    component health probe.

    Attributes:
        healthy: Whether the component is healthy
        latency_ms: Time taken to perform the health check in milliseconds
        message: Optional human-readable status message
        timestamp_mono: Monotonic timestamp when signal was created
    """

    healthy: bool
    latency_ms: float | None = None
    message: str | None = None
    timestamp_mono: float = field(default_factory=time.monotonic)


@runtime_checkable
class ComponentProbe(Protocol):
    """Protocol for component health probes.

    Component probes provide a standard interface for:
    - Quick health checks for recovery orchestration
    - Attempting to restore ready state
    - Tracking last successful update time
    """

    async def health_check(self) -> HealthSignal:
        """Quick health check for recovery orchestration.

        Returns:
            HealthSignal with current health status
        """
        ...

    async def ensure_ready(self) -> bool:
        """Attempt to restore ready state.

        Returns:
            True if ready state was restored, False otherwise
        """
        ...

    def get_last_update_mono(self) -> float:
        """Monotonic timestamp of last successful update.

        Returns:
            Monotonic timestamp (from time.monotonic())
        """
        ...


class BrokerProbe:
    """Probe for broker connection health.

    Provides health checking and readiness restoration for the broker
    connection component.

    Args:
        simulate_healthy: If False, health_check returns unhealthy (for testing)
        simulate_ready: If False, ensure_ready returns False (for testing)
    """

    def __init__(
        self,
        simulate_healthy: bool = True,
        simulate_ready: bool = True,
    ) -> None:
        """Initialize BrokerProbe.

        Args:
            simulate_healthy: Whether to simulate healthy status
            simulate_ready: Whether to simulate successful ready restoration
        """
        self._simulate_healthy = simulate_healthy
        self._simulate_ready = simulate_ready
        self._last_update_mono = time.monotonic()

    async def health_check(self) -> HealthSignal:
        """Quick health check for broker connection.

        Returns:
            HealthSignal with broker connection status
        """
        start = time.monotonic()

        # In production, this would actually check broker connectivity
        # For now, we simulate the result
        healthy = self._simulate_healthy

        end = time.monotonic()
        latency_ms = (end - start) * 1000

        if healthy:
            self._last_update_mono = end

        return HealthSignal(
            healthy=healthy,
            latency_ms=latency_ms,
            message=None if healthy else "Broker connection failed",
        )

    async def ensure_ready(self) -> bool:
        """Attempt to restore broker connection.

        Returns:
            True if broker connection was restored, False otherwise
        """
        # In production, this would attempt reconnection
        # For now, we simulate the result
        if self._simulate_ready:
            self._last_update_mono = time.monotonic()
            return True
        return False

    def get_last_update_mono(self) -> float:
        """Monotonic timestamp of last successful broker update.

        Returns:
            Monotonic timestamp
        """
        return self._last_update_mono


class MarketDataProbe:
    """Probe for market data freshness.

    Provides health checking and readiness restoration for the market data
    component.

    Args:
        simulate_healthy: If False, health_check returns unhealthy (for testing)
        simulate_ready: If False, ensure_ready returns False (for testing)
    """

    def __init__(
        self,
        simulate_healthy: bool = True,
        simulate_ready: bool = True,
    ) -> None:
        """Initialize MarketDataProbe.

        Args:
            simulate_healthy: Whether to simulate healthy status
            simulate_ready: Whether to simulate successful ready restoration
        """
        self._simulate_healthy = simulate_healthy
        self._simulate_ready = simulate_ready
        self._last_update_mono = time.monotonic()

    async def health_check(self) -> HealthSignal:
        """Quick health check for market data freshness.

        Returns:
            HealthSignal with market data status
        """
        start = time.monotonic()

        # In production, this would check market data age
        # For now, we simulate the result
        healthy = self._simulate_healthy

        end = time.monotonic()
        latency_ms = (end - start) * 1000

        if healthy:
            self._last_update_mono = end

        return HealthSignal(
            healthy=healthy,
            latency_ms=latency_ms,
            message=None if healthy else "Market data stale",
        )

    async def ensure_ready(self) -> bool:
        """Attempt to restore market data feed.

        Returns:
            True if market data feed was restored, False otherwise
        """
        # In production, this would attempt to refresh market data
        # For now, we simulate the result
        if self._simulate_ready:
            self._last_update_mono = time.monotonic()
            return True
        return False

    def get_last_update_mono(self) -> float:
        """Monotonic timestamp of last successful market data update.

        Returns:
            Monotonic timestamp
        """
        return self._last_update_mono


class RiskProbe:
    """Probe for risk engine health.

    Provides health checking and readiness restoration for the risk
    engine component.

    Args:
        simulate_healthy: If False, health_check returns unhealthy (for testing)
        simulate_ready: If False, ensure_ready returns False (for testing)
    """

    def __init__(
        self,
        simulate_healthy: bool = True,
        simulate_ready: bool = True,
    ) -> None:
        """Initialize RiskProbe.

        Args:
            simulate_healthy: Whether to simulate healthy status
            simulate_ready: Whether to simulate successful ready restoration
        """
        self._simulate_healthy = simulate_healthy
        self._simulate_ready = simulate_ready
        self._last_update_mono = time.monotonic()

    async def health_check(self) -> HealthSignal:
        """Quick health check for risk engine.

        Returns:
            HealthSignal with risk engine status
        """
        start = time.monotonic()

        # In production, this would check risk engine responsiveness
        # For now, we simulate the result
        healthy = self._simulate_healthy

        end = time.monotonic()
        latency_ms = (end - start) * 1000

        if healthy:
            self._last_update_mono = end

        return HealthSignal(
            healthy=healthy,
            latency_ms=latency_ms,
            message=None if healthy else "Risk engine timeout",
        )

    async def ensure_ready(self) -> bool:
        """Attempt to restore risk engine.

        Returns:
            True if risk engine was restored, False otherwise
        """
        # In production, this would attempt to reinitialize risk engine
        # For now, we simulate the result
        if self._simulate_ready:
            self._last_update_mono = time.monotonic()
            return True
        return False

    def get_last_update_mono(self) -> float:
        """Monotonic timestamp of last successful risk engine update.

        Returns:
            Monotonic timestamp
        """
        return self._last_update_mono
