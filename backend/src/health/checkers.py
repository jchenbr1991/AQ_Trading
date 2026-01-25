"""Health check implementations for system components."""

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Protocol

from src.health.models import ComponentStatus, HealthStatus


class HealthChecker(Protocol):
    """Protocol for health checkers."""

    async def check(self) -> HealthStatus:
        """Perform health check and return status."""
        ...


class RedisHealthChecker:
    """Health checker for Redis connection."""

    def __init__(self, redis_client: Any) -> None:
        """Initialize with Redis client.

        Args:
            redis_client: Redis client with async ping() method
        """
        self._redis = redis_client

    async def check(self) -> HealthStatus:
        """Check Redis health via PING command.

        Returns:
            HealthStatus with latency if successful, error message if failed
        """
        start = time.perf_counter()
        try:
            await asyncio.wait_for(self._redis.ping(), timeout=5.0)
            latency_ms = (time.perf_counter() - start) * 1000
            return HealthStatus(
                component="redis",
                status=ComponentStatus.HEALTHY,
                latency_ms=latency_ms,
                last_check=datetime.now(tz=timezone.utc),
                message=None,
            )
        except TimeoutError:
            return HealthStatus(
                component="redis",
                status=ComponentStatus.DOWN,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message="Health check timeout",
            )
        except Exception as e:
            return HealthStatus(
                component="redis",
                status=ComponentStatus.DOWN,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message=str(e),
            )


class MarketDataHealthChecker:
    """Health checker for market data service freshness."""

    def __init__(self, market_data_service: Any, stale_threshold_seconds: int = 30) -> None:
        """Initialize with market data service.

        Args:
            market_data_service: Service with last_update datetime attribute
            stale_threshold_seconds: Seconds before data is considered stale
        """
        self._service = market_data_service
        self._threshold = stale_threshold_seconds

    async def check(self) -> HealthStatus:
        """Check market data freshness.

        Returns:
            HEALTHY if data is fresh, DEGRADED if stale, UNKNOWN if no data
        """
        now = datetime.now(tz=timezone.utc)
        last_update = self._service.last_update

        if last_update is None:
            return HealthStatus(
                component="market_data",
                status=ComponentStatus.UNKNOWN,
                latency_ms=None,
                last_check=now,
                message="No data received yet",
            )

        age_seconds = (now - last_update).total_seconds()

        if age_seconds <= self._threshold:
            return HealthStatus(
                component="market_data",
                status=ComponentStatus.HEALTHY,
                latency_ms=None,
                last_check=now,
                message=None,
            )
        else:
            return HealthStatus(
                component="market_data",
                status=ComponentStatus.DEGRADED,
                latency_ms=None,
                last_check=now,
                message=f"Data stale: {age_seconds:.0f}s old",
            )
