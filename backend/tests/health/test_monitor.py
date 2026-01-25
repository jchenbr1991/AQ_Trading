"""Tests for HealthMonitor service."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from src.health.models import ComponentStatus, HealthStatus
from src.health.monitor import HealthMonitor


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
