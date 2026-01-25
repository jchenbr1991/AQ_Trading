"""Tests for health checkers."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.health.checkers import (
    HealthChecker,
    MarketDataHealthChecker,
    RedisHealthChecker,
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
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(side_effect=TimeoutError())

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
