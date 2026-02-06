# backend/src/market_data/service.py
"""Market data distribution service."""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from src.market_data.models import MarketDataConfig, QuoteSnapshot
from src.market_data.processor import QuoteProcessor
from src.market_data.sources.mock import MockDataSource
from src.strategies.base import MarketData

logger = logging.getLogger(__name__)


class RedisClient(Protocol):
    """Protocol for Redis client."""

    async def set(self, key: str, value: str) -> None: ...

    async def get(self, key: str) -> str | None: ...


class MarketDataService:
    """
    Market data distribution service.

    Generates mock quotes, caches to Redis, distributes via queue.
    """

    def __init__(self, redis: RedisClient, config: MarketDataConfig, source=None):
        self._redis = redis
        self._config = config
        self._subscribed: set[str] = set()
        self._stream: asyncio.Queue[MarketData] = asyncio.Queue(maxsize=config.queue_max_size)
        self._running = False
        self._overflow_count = 0
        self._task: asyncio.Task | None = None

        self._source = source or MockDataSource(config)
        self._processor = QuoteProcessor(redis=redis, faults=config.faults)

    async def start(self) -> None:
        """Start generating quotes for subscribed symbols."""
        if self._running:
            return

        self._running = True
        await self._source.subscribe(list(self._subscribed))
        await self._source.start()

        self._task = asyncio.create_task(self._pump_quotes())
        logger.info(f"MarketDataService started for {len(self._subscribed)} symbols")

    async def stop(self) -> None:
        """Stop generation, cleanup."""
        self._running = False
        await self._source.stop()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(f"MarketDataService stopped. Overflow count: {self._overflow_count}")

    def ensure_subscribed(self, symbols: list[str]) -> None:
        """
        Ensure symbols are subscribed. Idempotent.
        Can be called before or after start().
        """
        self._subscribed.update(symbols)

    async def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        """
        Get latest cached quote snapshot. Async (reads Redis).
        Returns QuoteSnapshot or None if unavailable.
        """
        key = f"quote:{symbol}"
        data = await self._redis.get(key)
        if not data:
            return None

        parsed = json.loads(data)
        return QuoteSnapshot(
            symbol=parsed["symbol"],
            price=Decimal(parsed["price"]),
            bid=Decimal(parsed["bid"]),
            ask=Decimal(parsed["ask"]),
            volume=parsed["volume"],
            timestamp=datetime.fromisoformat(parsed["timestamp"]),
            cached_at=datetime.fromisoformat(parsed["cached_at"]),
        )

    def get_stream(self) -> asyncio.Queue[MarketData]:
        """
        Get the distribution queue.
        Consumer (StrategyEngine) reads from this.
        """
        return self._stream

    async def _pump_quotes(self) -> None:
        """Background task: read from source, process, enqueue."""
        try:
            async for quote in self._source.quotes():
                if not self._running:
                    break

                result = await self._processor.process(quote)

                if isinstance(result, list):
                    for q in result:
                        await self._enqueue(q)
                elif result:
                    await self._enqueue(result)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in quote pump: {e}", exc_info=True)

    async def _enqueue(self, quote: MarketData) -> None:
        """Enqueue quote with drop-oldest overflow policy."""
        if self._stream.full():
            try:
                self._stream.get_nowait()
                self._overflow_count += 1
                if self._overflow_count % 100 == 1:
                    logger.warning(
                        f"Queue overflow, dropped oldest. Total drops: {self._overflow_count}"
                    )
            except asyncio.QueueEmpty:
                pass
        await self._stream.put(quote)
