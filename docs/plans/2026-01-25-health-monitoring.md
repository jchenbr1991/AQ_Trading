# Health Monitoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build end-to-end health monitoring system that tracks component status and displays it on a dedicated dashboard page.

**Architecture:** Backend HealthMonitor service performs periodic heartbeat checks on components (Redis, PostgreSQL, MarketData). API exposes `/api/health/detailed` endpoint. Frontend `/health` page shows real-time component status with color-coded indicators.

**Tech Stack:** Python (FastAPI, asyncio), TypeScript (React, TanStack Query), Tailwind CSS

---

## Task 1: HealthStatus Models

**Files:**
- Create: `backend/src/health/models.py`
- Test: `backend/tests/health/test_models.py`

**Step 1: Write the failing test**

```python
# backend/tests/health/test_models.py
"""Tests for health monitoring models."""

import pytest
from datetime import datetime, timezone

from src.health.models import ComponentStatus, HealthStatus, SystemHealth


class TestComponentStatus:
    """Tests for ComponentStatus enum."""

    def test_healthy_value(self):
        assert ComponentStatus.HEALTHY.value == "healthy"

    def test_degraded_value(self):
        assert ComponentStatus.DEGRADED.value == "degraded"

    def test_down_value(self):
        assert ComponentStatus.DOWN.value == "down"

    def test_unknown_value(self):
        assert ComponentStatus.UNKNOWN.value == "unknown"


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_create_healthy_status(self):
        status = HealthStatus(
            component="redis",
            status=ComponentStatus.HEALTHY,
            latency_ms=5.2,
            last_check=datetime.now(tz=timezone.utc),
            message=None,
        )
        assert status.component == "redis"
        assert status.status == ComponentStatus.HEALTHY
        assert status.latency_ms == 5.2
        assert status.message is None

    def test_create_down_status_with_message(self):
        status = HealthStatus(
            component="postgres",
            status=ComponentStatus.DOWN,
            latency_ms=None,
            last_check=datetime.now(tz=timezone.utc),
            message="Connection refused",
        )
        assert status.status == ComponentStatus.DOWN
        assert status.message == "Connection refused"
        assert status.latency_ms is None


class TestSystemHealth:
    """Tests for SystemHealth aggregate."""

    def test_all_healthy_means_system_healthy(self):
        now = datetime.now(tz=timezone.utc)
        components = [
            HealthStatus("redis", ComponentStatus.HEALTHY, 5.0, now, None),
            HealthStatus("postgres", ComponentStatus.HEALTHY, 10.0, now, None),
        ]
        system = SystemHealth(
            overall_status=ComponentStatus.HEALTHY,
            components=components,
            checked_at=now,
        )
        assert system.overall_status == ComponentStatus.HEALTHY

    def test_one_down_means_system_degraded(self):
        now = datetime.now(tz=timezone.utc)
        components = [
            HealthStatus("redis", ComponentStatus.HEALTHY, 5.0, now, None),
            HealthStatus("postgres", ComponentStatus.DOWN, None, now, "Connection refused"),
        ]
        system = SystemHealth(
            overall_status=ComponentStatus.DEGRADED,
            components=components,
            checked_at=now,
        )
        assert system.overall_status == ComponentStatus.DEGRADED
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/health/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.health'"

**Step 3: Create __init__.py for health package**

```python
# backend/src/health/__init__.py
"""Health monitoring package."""
```

**Step 4: Write minimal implementation**

```python
# backend/src/health/models.py
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
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/health/test_models.py -v`
Expected: PASS (6 tests)

**Step 6: Commit**

```bash
git add backend/src/health/__init__.py backend/src/health/models.py backend/tests/health/test_models.py
git commit -m "feat(health): add health monitoring models"
```

---

## Task 2: Component Health Checkers

**Files:**
- Create: `backend/src/health/checkers.py`
- Test: `backend/tests/health/test_checkers.py`

**Step 1: Write the failing test**

```python
# backend/tests/health/test_checkers.py
"""Tests for health checkers."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.health.checkers import (
    HealthChecker,
    RedisHealthChecker,
    MarketDataHealthChecker,
)
from src.health.models import ComponentStatus


class TestHealthCheckerProtocol:
    """Tests for HealthChecker protocol."""

    def test_protocol_requires_check_method(self):
        # HealthChecker is a Protocol, verify it defines check()
        assert hasattr(HealthChecker, "check")


class TestRedisHealthChecker:
    """Tests for Redis health checker."""

    @pytest.mark.asyncio
    async def test_healthy_when_redis_responds(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        checker = RedisHealthChecker(mock_redis)
        result = await checker.check()

        assert result.component == "redis"
        assert result.status == ComponentStatus.HEALTHY
        assert result.latency_ms is not None
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_down_when_redis_fails(self):
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=ConnectionError("Connection refused"))

        checker = RedisHealthChecker(mock_redis)
        result = await checker.check()

        assert result.component == "redis"
        assert result.status == ComponentStatus.DOWN
        assert "Connection refused" in result.message

    @pytest.mark.asyncio
    async def test_down_when_redis_timeout(self):
        import asyncio

        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=asyncio.TimeoutError())

        checker = RedisHealthChecker(mock_redis)
        result = await checker.check()

        assert result.status == ComponentStatus.DOWN
        assert "timeout" in result.message.lower()


class TestMarketDataHealthChecker:
    """Tests for MarketData health checker."""

    @pytest.mark.asyncio
    async def test_healthy_when_data_fresh(self):
        mock_service = MagicMock()
        # Data updated 5 seconds ago
        mock_service.last_update = datetime.now(tz=timezone.utc)

        checker = MarketDataHealthChecker(mock_service, stale_threshold_seconds=30)
        result = await checker.check()

        assert result.component == "market_data"
        assert result.status == ComponentStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_degraded_when_data_stale(self):
        from datetime import timedelta

        mock_service = MagicMock()
        # Data updated 60 seconds ago (stale)
        mock_service.last_update = datetime.now(tz=timezone.utc) - timedelta(seconds=60)

        checker = MarketDataHealthChecker(mock_service, stale_threshold_seconds=30)
        result = await checker.check()

        assert result.component == "market_data"
        assert result.status == ComponentStatus.DEGRADED
        assert "stale" in result.message.lower()

    @pytest.mark.asyncio
    async def test_unknown_when_no_data_yet(self):
        mock_service = MagicMock()
        mock_service.last_update = None

        checker = MarketDataHealthChecker(mock_service, stale_threshold_seconds=30)
        result = await checker.check()

        assert result.status == ComponentStatus.UNKNOWN
        assert "no data" in result.message.lower()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/health/test_checkers.py -v`
Expected: FAIL with "cannot import name 'HealthChecker'"

**Step 3: Write minimal implementation**

```python
# backend/src/health/checkers.py
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
        except asyncio.TimeoutError:
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/health/test_checkers.py -v`
Expected: PASS (8 tests)

**Step 5: Commit**

```bash
git add backend/src/health/checkers.py backend/tests/health/test_checkers.py
git commit -m "feat(health): add Redis and MarketData health checkers"
```

---

## Task 3: HealthMonitor Service

**Files:**
- Create: `backend/src/health/monitor.py`
- Test: `backend/tests/health/test_monitor.py`

**Step 1: Write the failing test**

```python
# backend/tests/health/test_monitor.py
"""Tests for HealthMonitor service."""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime, timezone

from src.health.monitor import HealthMonitor
from src.health.models import ComponentStatus, HealthStatus


class TestHealthMonitor:
    """Tests for HealthMonitor aggregate service."""

    @pytest.mark.asyncio
    async def test_check_all_returns_system_health(self):
        # Create mock checkers
        redis_checker = AsyncMock()
        redis_checker.check = AsyncMock(
            return_value=HealthStatus(
                component="redis",
                status=ComponentStatus.HEALTHY,
                latency_ms=5.0,
                last_check=datetime.now(tz=timezone.utc),
                message=None,
            )
        )

        market_checker = AsyncMock()
        market_checker.check = AsyncMock(
            return_value=HealthStatus(
                component="market_data",
                status=ComponentStatus.HEALTHY,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message=None,
            )
        )

        monitor = HealthMonitor(checkers=[redis_checker, market_checker])
        result = await monitor.check_all()

        assert result.overall_status == ComponentStatus.HEALTHY
        assert len(result.components) == 2

    @pytest.mark.asyncio
    async def test_overall_degraded_when_one_component_down(self):
        redis_checker = AsyncMock()
        redis_checker.check = AsyncMock(
            return_value=HealthStatus(
                component="redis",
                status=ComponentStatus.DOWN,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message="Connection refused",
            )
        )

        market_checker = AsyncMock()
        market_checker.check = AsyncMock(
            return_value=HealthStatus(
                component="market_data",
                status=ComponentStatus.HEALTHY,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message=None,
            )
        )

        monitor = HealthMonitor(checkers=[redis_checker, market_checker])
        result = await monitor.check_all()

        assert result.overall_status == ComponentStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_overall_down_when_all_components_down(self):
        redis_checker = AsyncMock()
        redis_checker.check = AsyncMock(
            return_value=HealthStatus(
                component="redis",
                status=ComponentStatus.DOWN,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message="Error",
            )
        )

        market_checker = AsyncMock()
        market_checker.check = AsyncMock(
            return_value=HealthStatus(
                component="market_data",
                status=ComponentStatus.DOWN,
                latency_ms=None,
                last_check=datetime.now(tz=timezone.utc),
                message="Error",
            )
        )

        monitor = HealthMonitor(checkers=[redis_checker, market_checker])
        result = await monitor.check_all()

        assert result.overall_status == ComponentStatus.DOWN

    @pytest.mark.asyncio
    async def test_checks_run_concurrently(self):
        import asyncio

        call_times = []

        async def slow_check():
            call_times.append(asyncio.get_event_loop().time())
            await asyncio.sleep(0.1)
            return HealthStatus(
                component="slow",
                status=ComponentStatus.HEALTHY,
                latency_ms=100,
                last_check=datetime.now(tz=timezone.utc),
                message=None,
            )

        checker1 = AsyncMock()
        checker1.check = slow_check

        checker2 = AsyncMock()
        checker2.check = slow_check

        monitor = HealthMonitor(checkers=[checker1, checker2])

        start = asyncio.get_event_loop().time()
        await monitor.check_all()
        elapsed = asyncio.get_event_loop().time() - start

        # If concurrent, should take ~0.1s, not ~0.2s
        assert elapsed < 0.15, "Checks should run concurrently"

    @pytest.mark.asyncio
    async def test_get_component_returns_specific_status(self):
        redis_checker = AsyncMock()
        redis_status = HealthStatus(
            component="redis",
            status=ComponentStatus.HEALTHY,
            latency_ms=5.0,
            last_check=datetime.now(tz=timezone.utc),
            message=None,
        )
        redis_checker.check = AsyncMock(return_value=redis_status)

        monitor = HealthMonitor(checkers=[redis_checker])
        result = await monitor.get_component("redis")

        assert result == redis_status

    @pytest.mark.asyncio
    async def test_get_component_returns_none_for_unknown(self):
        monitor = HealthMonitor(checkers=[])
        result = await monitor.get_component("unknown")

        assert result is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/health/test_monitor.py -v`
Expected: FAIL with "cannot import name 'HealthMonitor'"

**Step 3: Write minimal implementation**

```python
# backend/src/health/monitor.py
"""Health monitoring service that aggregates component health checks."""

import asyncio
from datetime import datetime, timezone
from typing import Sequence

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

    def _compute_overall_status(
        self, statuses: list[HealthStatus]
    ) -> ComponentStatus:
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/health/test_monitor.py -v`
Expected: PASS (6 tests)

**Step 5: Commit**

```bash
git add backend/src/health/monitor.py backend/tests/health/test_monitor.py
git commit -m "feat(health): add HealthMonitor aggregation service"
```

---

## Task 4: Health API Endpoint

**Files:**
- Create: `backend/src/api/health.py`
- Test: `backend/tests/api/test_health.py`
- Modify: `backend/src/main.py`

**Step 1: Write the failing test**

```python
# backend/tests/api/test_health.py
"""Tests for health API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from src.main import app
from src.health.models import ComponentStatus, HealthStatus, SystemHealth


class TestHealthEndpoints:
    """Tests for /api/health endpoints."""

    def test_simple_health_returns_ok(self):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_detailed_health_returns_components(self):
        client = TestClient(app)

        # Mock the health monitor
        mock_health = SystemHealth(
            overall_status=ComponentStatus.HEALTHY,
            components=[
                HealthStatus(
                    component="redis",
                    status=ComponentStatus.HEALTHY,
                    latency_ms=5.0,
                    last_check=datetime.now(tz=timezone.utc),
                    message=None,
                ),
                HealthStatus(
                    component="market_data",
                    status=ComponentStatus.HEALTHY,
                    latency_ms=None,
                    last_check=datetime.now(tz=timezone.utc),
                    message=None,
                ),
            ],
            checked_at=datetime.now(tz=timezone.utc),
        )

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.check_all = AsyncMock(return_value=mock_health)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert len(data["components"]) == 2
        assert data["components"][0]["component"] == "redis"
        assert data["components"][0]["status"] == "healthy"

    def test_detailed_health_returns_503_when_degraded(self):
        client = TestClient(app)

        mock_health = SystemHealth(
            overall_status=ComponentStatus.DEGRADED,
            components=[
                HealthStatus(
                    component="redis",
                    status=ComponentStatus.DOWN,
                    latency_ms=None,
                    last_check=datetime.now(tz=timezone.utc),
                    message="Connection refused",
                ),
            ],
            checked_at=datetime.now(tz=timezone.utc),
        )

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.check_all = AsyncMock(return_value=mock_health)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/detailed")

        # 503 Service Unavailable for degraded health
        assert response.status_code == 503
        data = response.json()
        assert data["overall_status"] == "degraded"

    def test_component_health_endpoint(self):
        client = TestClient(app)

        mock_status = HealthStatus(
            component="redis",
            status=ComponentStatus.HEALTHY,
            latency_ms=5.0,
            last_check=datetime.now(tz=timezone.utc),
            message=None,
        )

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.get_component = AsyncMock(return_value=mock_status)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/component/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "redis"
        assert data["status"] == "healthy"

    def test_component_health_returns_404_for_unknown(self):
        client = TestClient(app)

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.get_component = AsyncMock(return_value=None)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/component/unknown")

        assert response.status_code == 404
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_health.py -v`
Expected: FAIL with route not found or import error

**Step 3: Write minimal implementation**

```python
# backend/src/api/health.py
"""Health monitoring API endpoints."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.health.models import ComponentStatus, SystemHealth
from src.health.monitor import HealthMonitor


router = APIRouter(prefix="/api/health", tags=["health"])


# Response models
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


# Singleton health monitor (will be initialized with real checkers in production)
_health_monitor: HealthMonitor | None = None


def get_health_monitor() -> HealthMonitor:
    """Get the global health monitor instance.

    Returns:
        HealthMonitor instance
    """
    global _health_monitor
    if _health_monitor is None:
        # Create with empty checkers for now
        # In production, this would be initialized with real checkers
        _health_monitor = HealthMonitor(checkers=[])
    return _health_monitor


def set_health_monitor(monitor: HealthMonitor) -> None:
    """Set the global health monitor instance (for testing/initialization).

    Args:
        monitor: HealthMonitor instance to use
    """
    global _health_monitor
    _health_monitor = monitor


@router.get("/detailed", response_model=SystemHealthResponse)
async def get_detailed_health() -> Any:
    """Get detailed health status of all components.

    Returns 200 if healthy, 503 if degraded or down.
    """
    monitor = get_health_monitor()
    health = await monitor.check_all()

    response = SystemHealthResponse(
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
        raise HTTPException(status_code=503, detail=response.model_dump())

    return response


@router.get("/component/{component_name}", response_model=ComponentHealthResponse)
async def get_component_health(component_name: str) -> ComponentHealthResponse:
    """Get health status for a specific component.

    Args:
        component_name: Name of the component to check

    Returns:
        ComponentHealthResponse

    Raises:
        404 if component not found
    """
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
```

**Step 4: Register the router in main.py**

```python
# backend/src/main.py
# Add this import at the top:
from src.api.health import router as health_router

# Add this line after existing router includes:
app.include_router(health_router)
```

**Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_health.py -v`
Expected: PASS (5 tests)

**Step 6: Commit**

```bash
git add backend/src/api/health.py backend/tests/api/test_health.py backend/src/main.py
git commit -m "feat(health): add health API endpoints"
```

---

## Task 5: Frontend Health Types

**Files:**
- Modify: `frontend/src/types/index.ts`
- Test: Manual verification (TypeScript compilation)

**Step 1: Add health types**

```typescript
// Add to frontend/src/types/index.ts

export type HealthStatusValue = 'healthy' | 'degraded' | 'down' | 'unknown';

export interface ComponentHealth {
  component: string;
  status: HealthStatusValue;
  latency_ms: number | null;
  last_check: string;
  message: string | null;
}

export interface SystemHealth {
  overall_status: HealthStatusValue;
  components: ComponentHealth[];
  checked_at: string;
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(health): add frontend health types"
```

---

## Task 6: useHealth Hook

**Files:**
- Create: `frontend/src/hooks/useHealth.ts`
- Test: `frontend/src/hooks/useHealth.test.ts`

**Step 1: Write the failing test**

```typescript
// frontend/src/hooks/useHealth.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useHealth } from './useHealth';
import * as healthApi from '../api/health';

vi.mock('../api/health');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useHealth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches health data on mount', async () => {
    const mockHealth = {
      overall_status: 'healthy' as const,
      components: [
        {
          component: 'redis',
          status: 'healthy' as const,
          latency_ms: 5.0,
          last_check: '2026-01-25T10:00:00Z',
          message: null,
        },
      ],
      checked_at: '2026-01-25T10:00:00Z',
    };

    vi.mocked(healthApi.fetchHealth).mockResolvedValue(mockHealth);

    const { result } = renderHook(() => useHealth(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockHealth);
    expect(healthApi.fetchHealth).toHaveBeenCalledTimes(1);
  });

  it('returns loading state initially', () => {
    vi.mocked(healthApi.fetchHealth).mockImplementation(
      () => new Promise(() => {})
    );

    const { result } = renderHook(() => useHealth(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);
  });

  it('refetches every 10 seconds by default', async () => {
    vi.useFakeTimers();
    const mockHealth = {
      overall_status: 'healthy' as const,
      components: [],
      checked_at: '2026-01-25T10:00:00Z',
    };

    vi.mocked(healthApi.fetchHealth).mockResolvedValue(mockHealth);

    renderHook(() => useHealth(), {
      wrapper: createWrapper(),
    });

    // Initial fetch
    await waitFor(() => {
      expect(healthApi.fetchHealth).toHaveBeenCalledTimes(1);
    });

    // Advance 10 seconds
    vi.advanceTimersByTime(10000);

    await waitFor(() => {
      expect(healthApi.fetchHealth).toHaveBeenCalledTimes(2);
    });

    vi.useRealTimers();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run useHealth`
Expected: FAIL with "Cannot find module '../api/health'"

**Step 3: Create the API function first**

```typescript
// frontend/src/api/health.ts
import { apiClient } from './client';
import { SystemHealth } from '../types';

export async function fetchHealth(): Promise<SystemHealth> {
  const response = await apiClient.get<SystemHealth>('/health/detailed');
  return response.data;
}
```

**Step 4: Write the hook implementation**

```typescript
// frontend/src/hooks/useHealth.ts
import { useQuery } from '@tanstack/react-query';
import { fetchHealth } from '../api/health';
import { SystemHealth } from '../types';

export function useHealth(refetchIntervalMs: number = 10000) {
  return useQuery<SystemHealth>({
    queryKey: ['health'],
    queryFn: fetchHealth,
    refetchInterval: refetchIntervalMs,
  });
}
```

**Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- --run useHealth`
Expected: PASS (3 tests)

**Step 6: Export from hooks index**

```typescript
// frontend/src/hooks/index.ts - add this export
export { useHealth } from './useHealth';
```

**Step 7: Commit**

```bash
git add frontend/src/api/health.ts frontend/src/hooks/useHealth.ts frontend/src/hooks/useHealth.test.ts frontend/src/hooks/index.ts
git commit -m "feat(health): add useHealth hook and API"
```

---

## Task 7: HealthStatusBadge Component

**Files:**
- Create: `frontend/src/components/HealthStatusBadge.tsx`
- Test: `frontend/src/components/HealthStatusBadge.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/components/HealthStatusBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HealthStatusBadge } from './HealthStatusBadge';

describe('HealthStatusBadge', () => {
  it('renders healthy status with green color', () => {
    render(<HealthStatusBadge status="healthy" />);

    const badge = screen.getByText('healthy');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-green-100', 'text-green-800');
  });

  it('renders degraded status with yellow color', () => {
    render(<HealthStatusBadge status="degraded" />);

    const badge = screen.getByText('degraded');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-yellow-100', 'text-yellow-800');
  });

  it('renders down status with red color', () => {
    render(<HealthStatusBadge status="down" />);

    const badge = screen.getByText('down');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-red-100', 'text-red-800');
  });

  it('renders unknown status with gray color', () => {
    render(<HealthStatusBadge status="unknown" />);

    const badge = screen.getByText('unknown');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-gray-100', 'text-gray-800');
  });

  it('accepts custom className', () => {
    render(<HealthStatusBadge status="healthy" className="ml-2" />);

    const badge = screen.getByText('healthy');
    expect(badge).toHaveClass('ml-2');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run HealthStatusBadge`
Expected: FAIL with "Cannot find module"

**Step 3: Write minimal implementation**

```typescript
// frontend/src/components/HealthStatusBadge.tsx
import { HealthStatusValue } from '../types';

interface HealthStatusBadgeProps {
  status: HealthStatusValue;
  className?: string;
}

const statusStyles: Record<HealthStatusValue, string> = {
  healthy: 'bg-green-100 text-green-800',
  degraded: 'bg-yellow-100 text-yellow-800',
  down: 'bg-red-100 text-red-800',
  unknown: 'bg-gray-100 text-gray-800',
};

export function HealthStatusBadge({ status, className = '' }: HealthStatusBadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusStyles[status]} ${className}`}
    >
      {status}
    </span>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run HealthStatusBadge`
Expected: PASS (5 tests)

**Step 5: Export from components index**

```typescript
// frontend/src/components/index.ts - add this export (create file if needed)
export { HealthStatusBadge } from './HealthStatusBadge';
```

**Step 6: Commit**

```bash
git add frontend/src/components/HealthStatusBadge.tsx frontend/src/components/HealthStatusBadge.test.tsx
git commit -m "feat(health): add HealthStatusBadge component"
```

---

## Task 8: ComponentHealthCard Component

**Files:**
- Create: `frontend/src/components/ComponentHealthCard.tsx`
- Test: `frontend/src/components/ComponentHealthCard.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/components/ComponentHealthCard.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ComponentHealthCard } from './ComponentHealthCard';
import { ComponentHealth } from '../types';

describe('ComponentHealthCard', () => {
  const healthyComponent: ComponentHealth = {
    component: 'redis',
    status: 'healthy',
    latency_ms: 5.2,
    last_check: '2026-01-25T10:00:00Z',
    message: null,
  };

  it('renders component name', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    expect(screen.getByText('redis')).toBeInTheDocument();
  });

  it('renders status badge', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('renders latency when available', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    expect(screen.getByText(/5.2\s*ms/)).toBeInTheDocument();
  });

  it('renders message when present', () => {
    const componentWithMessage: ComponentHealth = {
      ...healthyComponent,
      status: 'down',
      message: 'Connection refused',
    };

    render(<ComponentHealthCard component={componentWithMessage} />);

    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });

  it('does not render latency when null', () => {
    const componentNoLatency: ComponentHealth = {
      ...healthyComponent,
      latency_ms: null,
    };

    render(<ComponentHealthCard component={componentNoLatency} />);

    expect(screen.queryByText(/ms/)).not.toBeInTheDocument();
  });

  it('renders last check time', () => {
    render(<ComponentHealthCard component={healthyComponent} />);

    // Should show relative time or formatted date
    expect(screen.getByText(/Last check:/)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run ComponentHealthCard`
Expected: FAIL with "Cannot find module"

**Step 3: Write minimal implementation**

```typescript
// frontend/src/components/ComponentHealthCard.tsx
import { ComponentHealth } from '../types';
import { HealthStatusBadge } from './HealthStatusBadge';

interface ComponentHealthCardProps {
  component: ComponentHealth;
}

export function ComponentHealthCard({ component }: ComponentHealthCardProps) {
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString();
  };

  return (
    <div className="bg-white rounded-lg shadow p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-lg font-medium text-gray-900 capitalize">
          {component.component}
        </h3>
        <HealthStatusBadge status={component.status} />
      </div>

      <div className="space-y-1 text-sm text-gray-500">
        {component.latency_ms !== null && (
          <p>Latency: {component.latency_ms.toFixed(1)} ms</p>
        )}

        <p>Last check: {formatTime(component.last_check)}</p>

        {component.message && (
          <p className="text-red-600 mt-2">{component.message}</p>
        )}
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run ComponentHealthCard`
Expected: PASS (6 tests)

**Step 5: Export from components**

```typescript
// frontend/src/components/index.ts - add this export
export { ComponentHealthCard } from './ComponentHealthCard';
```

**Step 6: Commit**

```bash
git add frontend/src/components/ComponentHealthCard.tsx frontend/src/components/ComponentHealthCard.test.tsx
git commit -m "feat(health): add ComponentHealthCard component"
```

---

## Task 9: HealthPage Component

**Files:**
- Create: `frontend/src/pages/HealthPage.tsx`
- Test: `frontend/src/pages/HealthPage.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/pages/HealthPage.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { HealthPage } from './HealthPage';
import * as useHealthModule from '../hooks/useHealth';

vi.mock('../hooks/useHealth');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('HealthPage', () => {
  it('shows loading state', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('shows overall status when loaded', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: {
        overall_status: 'healthy',
        components: [
          {
            component: 'redis',
            status: 'healthy',
            latency_ms: 5.0,
            last_check: '2026-01-25T10:00:00Z',
            message: null,
          },
        ],
        checked_at: '2026-01-25T10:00:00Z',
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText('System Health')).toBeInTheDocument();
    expect(screen.getByText('healthy')).toBeInTheDocument();
    expect(screen.getByText('redis')).toBeInTheDocument();
  });

  it('shows error state when fetch fails', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/error/i)).toBeInTheDocument();
  });

  it('renders all components', () => {
    vi.mocked(useHealthModule.useHealth).mockReturnValue({
      data: {
        overall_status: 'degraded',
        components: [
          {
            component: 'redis',
            status: 'healthy',
            latency_ms: 5.0,
            last_check: '2026-01-25T10:00:00Z',
            message: null,
          },
          {
            component: 'market_data',
            status: 'down',
            latency_ms: null,
            last_check: '2026-01-25T10:00:00Z',
            message: 'Connection refused',
          },
        ],
        checked_at: '2026-01-25T10:00:00Z',
      },
      isLoading: false,
      isError: false,
    } as any);

    render(<HealthPage />, { wrapper: createWrapper() });

    expect(screen.getByText('redis')).toBeInTheDocument();
    expect(screen.getByText('market_data')).toBeInTheDocument();
    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- --run HealthPage`
Expected: FAIL with "Cannot find module"

**Step 3: Write minimal implementation**

```typescript
// frontend/src/pages/HealthPage.tsx
import { useHealth } from '../hooks/useHealth';
import { HealthStatusBadge } from '../components/HealthStatusBadge';
import { ComponentHealthCard } from '../components/ComponentHealthCard';

export function HealthPage() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-4xl mx-auto">
          <p className="text-gray-500">Loading health status...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-4xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error loading health status</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between">
            <h1 className="text-2xl font-bold text-gray-900">System Health</h1>
            <HealthStatusBadge status={data.overall_status} className="text-sm" />
          </div>
          <p className="text-sm text-gray-500 mt-1">
            Last checked: {new Date(data.checked_at).toLocaleString()}
          </p>
        </div>

        {/* Components Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {data.components.map((component) => (
            <ComponentHealthCard key={component.component} component={component} />
          ))}
        </div>

        {/* Empty state */}
        {data.components.length === 0 && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No health checks configured
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- --run HealthPage`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add frontend/src/pages/HealthPage.tsx frontend/src/pages/HealthPage.test.tsx
git commit -m "feat(health): add HealthPage component"
```

---

## Task 10: Add Routing and Navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/DashboardPage.tsx`

**Step 1: Install react-router-dom if not present**

Run: `cd frontend && npm install react-router-dom`

**Step 2: Create DashboardPage from existing App content**

```typescript
// frontend/src/pages/DashboardPage.tsx
import { Header } from '../components/Header';
import { AccountSummary } from '../components/AccountSummary';
import { PositionsTable } from '../components/PositionsTable';
import { AlertsPanel } from '../components/AlertsPanel';
import { ErrorBanner } from '../components/ErrorBanner';
import { useAccount } from '../hooks/useAccount';
import { usePositions } from '../hooks/usePositions';
import { useTradingState } from '../hooks/useTradingState';
import { useAlerts } from '../hooks/useAlerts';
import { useFreshness } from '../hooks/useFreshness';
import { closePosition } from '../api/orders';

const ACCOUNT_ID = 'ACC001'; // TODO: Make configurable

export function DashboardPage() {
  const account = useAccount(ACCOUNT_ID);
  const positions = usePositions(ACCOUNT_ID);
  const tradingState = useTradingState();
  const alerts = useAlerts();

  const positionsFreshness = useFreshness(
    positions.dataUpdatedAt,
    positions.isError,
    positions.failureCount ?? 0
  );

  const handleKillSwitch = async () => {
    await tradingState.triggerKillSwitch();
  };

  const handleClosePosition = async (symbol: string) => {
    await closePosition({
      symbol,
      quantity: 'all',
      order_type: 'market',
      time_in_force: 'IOC',
    });
    positions.refetch();
  };

  return (
    <>
      <Header
        tradingState={tradingState.data?.state ?? 'RUNNING'}
        onKillSwitch={handleKillSwitch}
      />

      <main className="max-w-7xl mx-auto px-4 py-6">
        <ErrorBanner
          failureCount={positions.failureCount ?? 0}
          lastSuccessful={positions.dataUpdatedAt ? new Date(positions.dataUpdatedAt).toISOString() : undefined}
          onRetry={() => positions.refetch()}
        />

        <AccountSummary
          account={account.data}
          isLoading={account.isLoading}
        />

        <PositionsTable
          positions={positions.data}
          isLoading={positions.isLoading}
          tradingState={tradingState.data?.state ?? 'RUNNING'}
          freshness={positionsFreshness}
          onClosePosition={handleClosePosition}
        />

        <AlertsPanel
          alerts={alerts.data}
          isLoading={alerts.isLoading}
        />
      </main>
    </>
  );
}
```

**Step 3: Update App.tsx with routing**

```typescript
// frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import { DashboardPage } from './pages/DashboardPage';
import { HealthPage } from './pages/HealthPage';

function Navigation() {
  return (
    <nav className="bg-gray-800">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-12">
          <div className="flex items-center space-x-4">
            <Link to="/" className="text-white font-medium hover:text-gray-300">
              Dashboard
            </Link>
            <Link to="/health" className="text-gray-300 hover:text-white">
              Health
            </Link>
          </div>
        </div>
      </div>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-gray-100">
        <Navigation />
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/health" element={<HealthPage />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
```

**Step 4: Verify it works**

Run: `cd frontend && npm run dev`
Expected: Navigate to http://localhost:3000/health and see the health page

**Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/pages/DashboardPage.tsx
git commit -m "feat(health): add routing and navigation"
```

---

## Task 11: Initialize Backend Health Checkers

**Files:**
- Modify: `backend/src/main.py`
- Create: `backend/src/health/setup.py`

**Step 1: Create setup module**

```python
# backend/src/health/setup.py
"""Health monitoring initialization."""

from src.health.monitor import HealthMonitor
from src.health.checkers import MarketDataHealthChecker
from src.api.health import set_health_monitor


class MockMarketDataService:
    """Mock market data service for development."""

    def __init__(self):
        from datetime import datetime, timezone
        self.last_update = datetime.now(tz=timezone.utc)


def init_health_monitor() -> HealthMonitor:
    """Initialize the health monitor with configured checkers.

    In production, this would use real Redis/PostgreSQL/MarketData services.
    For development, we use mocks.

    Returns:
        Configured HealthMonitor instance
    """
    checkers = []

    # MarketData checker (using mock for now)
    mock_market_data = MockMarketDataService()
    checkers.append(MarketDataHealthChecker(mock_market_data, stale_threshold_seconds=30))

    # Create and register the monitor
    monitor = HealthMonitor(checkers=checkers)
    set_health_monitor(monitor)

    return monitor
```

**Step 2: Update main.py to initialize health on startup**

```python
# backend/src/main.py - add at the end after router includes
from src.health.setup import init_health_monitor

# Initialize health monitoring on startup
@app.on_event("startup")
async def startup_event():
    init_health_monitor()
```

**Step 3: Run backend and test**

Run: `cd backend && python -m uvicorn src.main:app --reload`
Then: `curl http://localhost:8000/api/health/detailed`
Expected: JSON response with market_data component status

**Step 4: Commit**

```bash
git add backend/src/health/setup.py backend/src/main.py
git commit -m "feat(health): initialize health monitoring on startup"
```

---

## Task 12: Final Integration Test

**Files:**
- Create: `backend/tests/integration/test_health_e2e.py`

**Step 1: Write integration test**

```python
# backend/tests/integration/test_health_e2e.py
"""End-to-end integration tests for health monitoring."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestHealthE2E:
    """End-to-end health monitoring tests."""

    def test_simple_health_endpoint(self):
        """Simple /health endpoint should always return healthy."""
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_detailed_health_endpoint(self):
        """Detailed health should return component statuses."""
        client = TestClient(app)
        response = client.get("/api/health/detailed")

        # May return 200 (healthy) or 503 (degraded) depending on component status
        assert response.status_code in [200, 503]

        data = response.json()
        if response.status_code == 503:
            data = data["detail"]

        assert "overall_status" in data
        assert "components" in data
        assert "checked_at" in data

    def test_component_health_endpoint(self):
        """Should be able to check individual component health."""
        client = TestClient(app)

        # First get all components
        response = client.get("/api/health/detailed")
        data = response.json()
        if response.status_code == 503:
            data = data["detail"]

        if data["components"]:
            component_name = data["components"][0]["component"]
            response = client.get(f"/api/health/component/{component_name}")
            assert response.status_code == 200

    def test_unknown_component_returns_404(self):
        """Unknown component should return 404."""
        client = TestClient(app)
        response = client.get("/api/health/component/nonexistent")
        assert response.status_code == 404
```

**Step 2: Run integration tests**

Run: `cd backend && python -m pytest tests/integration/test_health_e2e.py -v`
Expected: PASS (4 tests)

**Step 3: Commit**

```bash
git add backend/tests/integration/test_health_e2e.py
git commit -m "test(health): add end-to-end integration tests"
```

---

## Summary

**Total Tasks:** 12
**Estimated Time:** 2-3 hours with TDD

**What's Built:**
- Backend: HealthMonitor service with pluggable checkers
- Backend: Health API endpoints (detailed, component-specific)
- Frontend: useHealth hook for data fetching
- Frontend: HealthStatusBadge and ComponentHealthCard components
- Frontend: HealthPage with navigation

**Next Steps (Future Slices):**
- Add PostgreSQL health checker (requires database setup)
- Add Redis health checker (requires Redis setup)
- Add WebSocket real-time health updates
- Add alerting when status changes
