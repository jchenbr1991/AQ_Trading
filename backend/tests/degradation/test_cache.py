"""Tests for cache with staleness tracking.

The cache module provides staleness tracking for SAFE_MODE_DISCONNECTED.
When broker is disconnected, queries return cached data with stale warnings.

Key design constraints:
- Dual timestamps: cached_at_wall (display) + cached_at_mono (logic)
- Staleness calculation based on monotonic time
- is_stale property compares age against threshold

Test cases:
- test_cached_data_not_stale_initially: Freshly cached data is not stale
- test_cached_data_becomes_stale: Data becomes stale after threshold
- test_dual_timestamps: Both wall and monotonic timestamps are captured
- test_cache_set_get: Basic set/get operations work
- test_get_if_fresh_returns_stale_flag: get_if_fresh returns proper stale flag
- test_cache_clear: Cache can be cleared selectively or entirely
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import pytest
from src.degradation.cache import CachedData, DataCache
from src.degradation.config import DegradationConfig


@pytest.fixture
def config() -> DegradationConfig:
    """Test configuration with controllable cache settings."""
    return DegradationConfig(
        position_cache_stale_ms=30000,
        market_data_cache_stale_ms=10000,
    )


@pytest.fixture
def data_cache(config: DegradationConfig) -> DataCache:
    """DataCache fixture for testing."""
    return DataCache(config=config)


class TestCachedDataNotStaleInitially:
    """Tests that freshly cached data is not stale."""

    def test_cached_data_not_stale_initially(self) -> None:
        """Freshly cached data is not stale."""
        cached = CachedData(
            data={"symbol": "AAPL", "price": 150.0},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=time.monotonic(),
            stale_threshold_ms=30000,
        )

        assert cached.is_stale is False

    def test_cached_data_fresh_just_under_threshold(self) -> None:
        """Data is fresh when age is just under threshold."""
        # Create data that's 29 seconds old (under 30 second threshold)
        old_mono = time.monotonic() - 29.0

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=old_mono,
            stale_threshold_ms=30000,
        )

        assert cached.is_stale is False


class TestCachedDataBecomesStale:
    """Tests that data becomes stale after threshold."""

    def test_cached_data_becomes_stale(self) -> None:
        """Data becomes stale after threshold."""
        # Create data that's 31 seconds old (over 30 second threshold)
        old_mono = time.monotonic() - 31.0

        cached = CachedData(
            data={"symbol": "AAPL", "price": 150.0},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=old_mono,
            stale_threshold_ms=30000,
        )

        assert cached.is_stale is True

    def test_cached_data_stale_at_exact_threshold(self) -> None:
        """Data is stale when age exceeds threshold (not at exact threshold)."""
        # Create data that's exactly at threshold
        old_mono = time.monotonic() - 30.001  # Just over threshold

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=old_mono,
            stale_threshold_ms=30000,
        )

        assert cached.is_stale is True

    def test_cached_data_with_short_threshold(self) -> None:
        """Data with short threshold becomes stale quickly."""
        # Create data that's 2 seconds old with 1 second threshold
        old_mono = time.monotonic() - 2.0

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=old_mono,
            stale_threshold_ms=1000,  # 1 second threshold
        )

        assert cached.is_stale is True


class TestDualTimestamps:
    """Tests for dual timestamp tracking."""

    def test_dual_timestamps(self) -> None:
        """Both wall and monotonic timestamps are captured correctly."""
        wall_time = datetime.now(tz=timezone.utc)
        mono_time = time.monotonic()

        cached = CachedData(
            data={"symbol": "AAPL"},
            cached_at_wall=wall_time,
            cached_at_mono=mono_time,
            stale_threshold_ms=30000,
        )

        assert cached.cached_at_wall == wall_time
        assert cached.cached_at_mono == mono_time

    def test_wall_time_for_display(self) -> None:
        """Wall time can be used for display purposes."""
        wall_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=wall_time,
            cached_at_mono=time.monotonic(),
            stale_threshold_ms=30000,
        )

        # Wall time should be preserved for display
        assert cached.cached_at_wall.year == 2024
        assert cached.cached_at_wall.month == 1
        assert cached.cached_at_wall.day == 15

    def test_monotonic_time_for_staleness(self) -> None:
        """Monotonic time is used for staleness calculation, not wall time."""
        # Wall time in the past
        old_wall_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

        # But monotonic time is recent
        recent_mono = time.monotonic()

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=old_wall_time,
            cached_at_mono=recent_mono,
            stale_threshold_ms=30000,
        )

        # Should NOT be stale because monotonic time is recent
        assert cached.is_stale is False


class TestAgeMs:
    """Tests for age_ms property."""

    def test_age_ms_calculation(self) -> None:
        """age_ms returns correct age in milliseconds."""
        # Create data that's about 5 seconds old
        old_mono = time.monotonic() - 5.0

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=old_mono,
            stale_threshold_ms=30000,
        )

        # Age should be approximately 5000ms (allowing some tolerance)
        assert 4900 < cached.age_ms < 5200

    def test_age_ms_increases_over_time(self) -> None:
        """age_ms increases as time passes."""
        mono = time.monotonic()

        cached = CachedData(
            data={"value": 1},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=mono,
            stale_threshold_ms=30000,
        )

        age1 = cached.age_ms
        time.sleep(0.05)  # Sleep 50ms
        age2 = cached.age_ms

        assert age2 > age1


class TestCacheSetGet:
    """Tests for basic cache set/get operations."""

    def test_cache_set_get(self, data_cache: DataCache) -> None:
        """Basic set/get operations work."""
        data = {"symbol": "AAPL", "price": 150.0}

        data_cache.set("positions", data)
        cached = data_cache.get("positions")

        assert cached is not None
        assert cached.data == data

    def test_cache_get_nonexistent_key(self, data_cache: DataCache) -> None:
        """Getting nonexistent key returns None."""
        cached = data_cache.get("nonexistent")

        assert cached is None

    def test_cache_set_overwrites(self, data_cache: DataCache) -> None:
        """Setting same key overwrites previous value."""
        data_cache.set("key1", {"value": 1})
        data_cache.set("key1", {"value": 2})

        cached = data_cache.get("key1")

        assert cached is not None
        assert cached.data == {"value": 2}

    def test_cache_set_with_custom_threshold(self, data_cache: DataCache) -> None:
        """Set can specify custom stale threshold."""
        data_cache.set("key1", {"value": 1}, stale_threshold_ms=5000)

        cached = data_cache.get("key1")

        assert cached is not None
        assert cached.stale_threshold_ms == 5000

    def test_cache_set_uses_default_threshold(self, data_cache: DataCache) -> None:
        """Set uses config's position_cache_stale_ms as default."""
        data_cache.set("key1", {"value": 1})

        cached = data_cache.get("key1")

        assert cached is not None
        assert cached.stale_threshold_ms == 30000  # From config

    def test_cache_timestamps_set_correctly(self, data_cache: DataCache) -> None:
        """Set creates correct timestamps."""
        before_wall = datetime.now(tz=timezone.utc)
        before_mono = time.monotonic()

        data_cache.set("key1", {"value": 1})

        after_mono = time.monotonic()

        cached = data_cache.get("key1")

        assert cached is not None
        assert cached.cached_at_wall >= before_wall
        assert cached.cached_at_mono >= before_mono
        assert cached.cached_at_mono <= after_mono


class TestGetIfFreshReturnsStaleFlag:
    """Tests for get_if_fresh method."""

    def test_get_if_fresh_returns_stale_flag(self, data_cache: DataCache) -> None:
        """get_if_fresh returns proper stale flag for fresh data."""
        data_cache.set("key1", {"value": 1})

        data, is_stale = data_cache.get_if_fresh("key1")

        assert data == {"value": 1}
        assert is_stale is False

    def test_get_if_fresh_returns_stale_true(self, config: DegradationConfig) -> None:
        """get_if_fresh returns stale=True for old data."""
        cache = DataCache(config=config)

        # Manually create a stale cache entry
        old_mono = time.monotonic() - 35.0  # 35 seconds old

        cache._cache["key1"] = CachedData(
            data={"value": 1},
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=old_mono,
            stale_threshold_ms=30000,
        )

        data, is_stale = cache.get_if_fresh("key1")

        assert data == {"value": 1}
        assert is_stale is True

    def test_get_if_fresh_nonexistent_key(self, data_cache: DataCache) -> None:
        """get_if_fresh returns (None, True) for nonexistent key."""
        data, is_stale = data_cache.get_if_fresh("nonexistent")

        assert data is None
        assert is_stale is True


class TestCacheClear:
    """Tests for cache clearing."""

    def test_cache_clear(self, data_cache: DataCache) -> None:
        """Cache can be cleared entirely."""
        data_cache.set("key1", {"value": 1})
        data_cache.set("key2", {"value": 2})

        data_cache.clear()

        assert data_cache.get("key1") is None
        assert data_cache.get("key2") is None

    def test_cache_clear_single_key(self, data_cache: DataCache) -> None:
        """Cache can clear a single key."""
        data_cache.set("key1", {"value": 1})
        data_cache.set("key2", {"value": 2})

        data_cache.clear("key1")

        assert data_cache.get("key1") is None
        assert data_cache.get("key2") is not None

    def test_cache_clear_nonexistent_key(self, data_cache: DataCache) -> None:
        """Clearing nonexistent key does not raise."""
        # Should not raise
        data_cache.clear("nonexistent")

    def test_cache_clear_empty(self, data_cache: DataCache) -> None:
        """Clearing empty cache does not raise."""
        # Should not raise
        data_cache.clear()


class TestCacheKeys:
    """Tests for cache key management."""

    def test_cache_keys(self, data_cache: DataCache) -> None:
        """Cache exposes keys for inspection."""
        data_cache.set("key1", {"value": 1})
        data_cache.set("key2", {"value": 2})

        keys = data_cache.keys()

        assert set(keys) == {"key1", "key2"}

    def test_cache_keys_empty(self, data_cache: DataCache) -> None:
        """Empty cache returns empty keys."""
        keys = data_cache.keys()

        assert list(keys) == []


class TestCacheSize:
    """Tests for cache size tracking."""

    def test_cache_size(self, data_cache: DataCache) -> None:
        """Cache tracks number of entries."""
        assert data_cache.size == 0

        data_cache.set("key1", {"value": 1})
        assert data_cache.size == 1

        data_cache.set("key2", {"value": 2})
        assert data_cache.size == 2

        data_cache.clear("key1")
        assert data_cache.size == 1

        data_cache.clear()
        assert data_cache.size == 0
