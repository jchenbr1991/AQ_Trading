"""Cache with staleness tracking for graceful degradation.

This module provides caching with dual timestamps for SAFE_MODE_DISCONNECTED.
When broker is disconnected, queries return cached data with stale warnings.

Key design:
- Dual timestamps: cached_at_wall (display) + cached_at_mono (logic)
- Staleness calculation based on monotonic time (not wall clock)
- is_stale property compares age against configurable threshold
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from src.degradation.config import DegradationConfig


@dataclass
class CachedData:
    """Cached data with staleness tracking.

    Uses dual timestamps:
    - cached_at_wall: Wall clock time for display purposes
    - cached_at_mono: Monotonic time for staleness calculation

    Staleness is determined using monotonic time to avoid issues
    with wall clock adjustments (NTP, daylight saving, etc.).
    """

    data: Any
    cached_at_wall: datetime  # For display
    cached_at_mono: float  # For stale calculation (time.monotonic())
    stale_threshold_ms: int = 30000

    @property
    def is_stale(self) -> bool:
        """Check if cache is stale using monotonic time.

        Returns:
            True if elapsed time exceeds stale_threshold_ms, False otherwise.
        """
        elapsed_ms = (time.monotonic() - self.cached_at_mono) * 1000
        return elapsed_ms > self.stale_threshold_ms

    @property
    def age_ms(self) -> float:
        """Age of cached data in milliseconds.

        Returns:
            Elapsed time since cache was created, in milliseconds.
        """
        return (time.monotonic() - self.cached_at_mono) * 1000


class DataCache:
    """Cache manager with staleness tracking.

    Provides a simple key-value cache with built-in staleness detection.
    All cached values include dual timestamps for both display and
    staleness calculation purposes.
    """

    def __init__(self, config: DegradationConfig) -> None:
        """Initialize the cache.

        Args:
            config: Degradation configuration with cache thresholds.
        """
        self._config = config
        self._cache: dict[str, CachedData] = {}

    def set(self, key: str, data: Any, stale_threshold_ms: int | None = None) -> None:
        """Store data with current timestamps.

        Args:
            key: Cache key for retrieval.
            data: Data to cache (any serializable value).
            stale_threshold_ms: Optional staleness threshold in milliseconds.
                               Defaults to config.position_cache_stale_ms.
        """
        threshold = (
            stale_threshold_ms
            if stale_threshold_ms is not None
            else self._config.position_cache_stale_ms
        )

        self._cache[key] = CachedData(
            data=data,
            cached_at_wall=datetime.now(tz=timezone.utc),
            cached_at_mono=time.monotonic(),
            stale_threshold_ms=threshold,
        )

    def get(self, key: str) -> CachedData | None:
        """Get cached data if exists.

        Args:
            key: Cache key to retrieve.

        Returns:
            CachedData object if key exists, None otherwise.
        """
        return self._cache.get(key)

    def get_if_fresh(self, key: str) -> tuple[Any, bool]:
        """Get data with freshness indicator.

        Args:
            key: Cache key to retrieve.

        Returns:
            Tuple of (data, is_stale). If key doesn't exist,
            returns (None, True).
        """
        cached = self._cache.get(key)

        if cached is None:
            return (None, True)

        return (cached.data, cached.is_stale)

    def clear(self, key: str | None = None) -> None:
        """Clear one or all cache entries.

        Args:
            key: Specific key to clear. If None, clears all entries.
        """
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)

    def keys(self) -> Iterator[str]:
        """Get all cache keys.

        Returns:
            Iterator over cache keys.
        """
        return iter(self._cache.keys())

    @property
    def size(self) -> int:
        """Number of entries in the cache.

        Returns:
            Count of cached entries.
        """
        return len(self._cache)
