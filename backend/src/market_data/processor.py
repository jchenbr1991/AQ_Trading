# backend/src/market_data/processor.py
"""Quote processor with fault injection and Redis caching."""

import asyncio
import json
import logging
from datetime import timedelta
from random import random, uniform
from typing import Protocol

from src.market_data.models import FaultConfig, QuoteSnapshot
from src.strategies.base import MarketData

logger = logging.getLogger(__name__)


class RedisClient(Protocol):
    """Protocol for Redis client."""

    async def set(self, key: str, value: str) -> None: ...

    async def get(self, key: str) -> str | None: ...


class QuoteProcessor:
    """
    Processes quotes: caches to Redis and applies fault injection.
    """

    def __init__(self, redis: RedisClient, faults: FaultConfig):
        self._redis = redis
        self._faults = faults

    async def process(self, quote: MarketData) -> MarketData | list[MarketData]:
        """
        Process a quote: apply faults, cache to Redis, return.

        Returns:
            - Single MarketData normally
            - List of 2 MarketData for duplicate fault
        """
        if not self._faults.enabled:
            snapshot = QuoteSnapshot.from_market_data(quote)
            await self._write_to_redis(snapshot)
            return quote

        # Apply delay fault
        # Using standard random for fault injection simulation (not cryptographic)
        if random() < self._faults.delay_probability:  # noqa: S311
            delay_ms = uniform(*self._faults.delay_ms_range)  # noqa: S311
            await asyncio.sleep(delay_ms / 1000)

        # Apply out-of-order fault (modify timestamp)
        if random() < self._faults.out_of_order_probability:  # noqa: S311
            offset = timedelta(milliseconds=self._faults.out_of_order_offset_ms)
            quote = MarketData(
                symbol=quote.symbol,
                price=quote.price,
                bid=quote.bid,
                ask=quote.ask,
                volume=quote.volume,
                timestamp=quote.timestamp - offset,
            )

        # Write to Redis
        snapshot = QuoteSnapshot.from_market_data(quote)
        await self._write_to_redis(snapshot)

        # Apply duplicate fault
        if random() < self._faults.duplicate_probability:  # noqa: S311
            return [quote, quote]

        return quote

    async def _write_to_redis(self, snapshot: QuoteSnapshot) -> None:
        """Write quote snapshot to Redis."""
        key = f"quote:{snapshot.symbol}"
        value = json.dumps(
            {
                "symbol": snapshot.symbol,
                "price": str(snapshot.price),
                "bid": str(snapshot.bid),
                "ask": str(snapshot.ask),
                "volume": snapshot.volume,
                "timestamp": snapshot.timestamp.isoformat(),
                "cached_at": snapshot.cached_at.isoformat(),
            }
        )
        await self._redis.set(key, value)
