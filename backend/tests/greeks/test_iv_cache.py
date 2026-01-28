"""Tests for IV cache manager."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from src.greeks.iv_cache import IVCacheEntry, IVCacheManager


class TestIVCacheEntry:
    """Tests for IVCacheEntry."""

    def test_create_entry(self):
        entry = IVCacheEntry(
            symbol="AAPL",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc),
        )
        assert entry.symbol == "AAPL"
        assert entry.implied_vol == Decimal("0.25")

    def test_is_stale_fresh(self):
        entry = IVCacheEntry(
            symbol="AAPL",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc),
        )
        assert entry.is_stale(max_age_seconds=300) is False

    def test_is_stale_old(self):
        entry = IVCacheEntry(
            symbol="AAPL",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        assert entry.is_stale(max_age_seconds=300) is True


class TestIVCacheManager:
    """Tests for IVCacheManager."""

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_cached(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        cache = IVCacheManager(mock_redis)
        result = await cache.get("AAPL240119C00150000")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, ex=None):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        cache = IVCacheManager(mock_redis)

        entry = IVCacheEntry(
            symbol="AAPL240119C00150000",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc),
        )

        await cache.set(entry)
        result = await cache.get("AAPL240119C00150000")

        assert result is not None
        assert result.implied_vol == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_get_for_underlying(self):
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, ex=None):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        cache = IVCacheManager(mock_redis)

        # Set IV for a specific option
        entry = IVCacheEntry(
            symbol="AAPL240119C00150000",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            underlying_symbol="AAPL",
            as_of_ts=datetime.now(timezone.utc),
        )
        await cache.set(entry)

        # Get average IV for underlying
        result = await cache.get_underlying_iv("AAPL")

        # Should return the IV value for the underlying
        assert result is not None
        assert result == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_get_or_default_returns_default_when_empty(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        cache = IVCacheManager(mock_redis)

        result = await cache.get_or_default("AAPL240119C00150000", "AAPL", Decimal("0.35"))

        assert result == Decimal("0.35")
