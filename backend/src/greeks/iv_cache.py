"""IV Cache Manager for Greeks fallback calculations.

Caches implied volatility data in Redis for use when Futu API is unavailable.
Provides fallback IV for Black-Scholes model calculations.

Cache Keys:
    - iv:{symbol} - Per-option IV cache
    - iv:underlying:{symbol} - Per-underlying average IV

TTL: 1 hour for individual options, 4 hours for underlying averages
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)

# Cache TTL settings
OPTION_IV_TTL_SECONDS = 3600  # 1 hour
UNDERLYING_IV_TTL_SECONDS = 14400  # 4 hours


class RedisClient(Protocol):
    """Protocol for async Redis client."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...


@dataclass
class IVCacheEntry:
    """Cached IV entry.

    Attributes:
        symbol: Option symbol
        implied_vol: Implied volatility (decimal, e.g., 0.25 = 25%)
        underlying_price: Underlying spot price at cache time
        underlying_symbol: Underlying symbol (optional)
        as_of_ts: Timestamp of the IV data
    """

    symbol: str
    implied_vol: Decimal
    underlying_price: Decimal
    as_of_ts: datetime
    underlying_symbol: str | None = None

    def is_stale(self, max_age_seconds: int = OPTION_IV_TTL_SECONDS) -> bool:
        """Check if entry is stale."""
        age = (datetime.now(timezone.utc) - self.as_of_ts).total_seconds()
        return age > max_age_seconds

    def to_json(self) -> str:
        """Serialize to JSON."""
        data = {
            "symbol": self.symbol,
            "implied_vol": str(self.implied_vol),
            "underlying_price": str(self.underlying_price),
            "underlying_symbol": self.underlying_symbol,
            "as_of_ts": self.as_of_ts.isoformat(),
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "IVCacheEntry":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(
            symbol=data["symbol"],
            implied_vol=Decimal(data["implied_vol"]),
            underlying_price=Decimal(data["underlying_price"]),
            underlying_symbol=data.get("underlying_symbol"),
            as_of_ts=datetime.fromisoformat(data["as_of_ts"]),
        )


class IVCacheManager:
    """Manages IV cache in Redis.

    Usage:
        cache = IVCacheManager(redis_client)

        # Cache IV from Futu
        await cache.set(IVCacheEntry(...))

        # Get cached IV for fallback
        entry = await cache.get("AAPL240119C00150000")
        if entry and not entry.is_stale():
            use entry.implied_vol
    """

    def __init__(self, redis: RedisClient):
        """Initialize cache manager.

        Args:
            redis: Async Redis client
        """
        self._redis = redis

    def _option_key(self, symbol: str) -> str:
        """Generate Redis key for option IV."""
        return f"iv:{symbol}"

    def _underlying_key(self, symbol: str) -> str:
        """Generate Redis key for underlying average IV."""
        return f"iv:underlying:{symbol}"

    async def get(self, symbol: str) -> IVCacheEntry | None:
        """Get cached IV for an option.

        Args:
            symbol: Option symbol

        Returns:
            IVCacheEntry if found, None otherwise
        """
        try:
            data = await self._redis.get(self._option_key(symbol))
            if data is None:
                return None
            return IVCacheEntry.from_json(data)
        except Exception as e:
            logger.warning(f"Error reading IV cache for {symbol}: {e}")
            return None

    async def set(self, entry: IVCacheEntry) -> None:
        """Cache IV for an option.

        Args:
            entry: IV cache entry to store
        """
        try:
            await self._redis.set(
                self._option_key(entry.symbol),
                entry.to_json(),
                ex=OPTION_IV_TTL_SECONDS,
            )

            # Also update underlying average if we have the underlying symbol
            if entry.underlying_symbol:
                await self._update_underlying_iv(entry)
        except Exception as e:
            logger.warning(f"Error writing IV cache for {entry.symbol}: {e}")

    async def _update_underlying_iv(self, entry: IVCacheEntry) -> None:
        """Update underlying-level IV cache.

        Simple approach: just use the latest option IV as a proxy.
        A more sophisticated approach would track multiple options
        and compute a weighted average.
        """
        try:
            underlying_entry = IVCacheEntry(
                symbol=entry.underlying_symbol,
                implied_vol=entry.implied_vol,
                underlying_price=entry.underlying_price,
                as_of_ts=entry.as_of_ts,
            )
            await self._redis.set(
                self._underlying_key(entry.underlying_symbol),
                underlying_entry.to_json(),
                ex=UNDERLYING_IV_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(f"Error updating underlying IV: {e}")

    async def get_underlying_iv(self, underlying_symbol: str) -> Decimal | None:
        """Get cached average IV for an underlying.

        Args:
            underlying_symbol: Underlying symbol (e.g., "AAPL")

        Returns:
            Average IV as Decimal, or None if not cached
        """
        try:
            data = await self._redis.get(self._underlying_key(underlying_symbol))
            if data is None:
                return None
            entry = IVCacheEntry.from_json(data)
            if entry.is_stale(UNDERLYING_IV_TTL_SECONDS):
                return None
            return entry.implied_vol
        except Exception as e:
            logger.warning(f"Error reading underlying IV for {underlying_symbol}: {e}")
            return None

    async def get_or_default(
        self,
        symbol: str,
        underlying_symbol: str,
        default_iv: Decimal = Decimal("0.30"),
    ) -> Decimal:
        """Get IV with fallback chain.

        Tries in order:
        1. Specific option IV cache
        2. Underlying average IV cache
        3. Default IV

        Args:
            symbol: Option symbol
            underlying_symbol: Underlying symbol
            default_iv: Default IV if nothing cached

        Returns:
            Best available IV estimate
        """
        # Try option-specific cache
        entry = await self.get(symbol)
        if entry and not entry.is_stale():
            return entry.implied_vol

        # Try underlying cache
        underlying_iv = await self.get_underlying_iv(underlying_symbol)
        if underlying_iv is not None:
            return underlying_iv

        # Fall back to default
        logger.debug(f"Using default IV {default_iv} for {symbol}")
        return default_iv
