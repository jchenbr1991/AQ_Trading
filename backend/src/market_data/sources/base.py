# backend/src/market_data/sources/base.py
"""Abstract data source interface."""

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from src.strategies.base import MarketData


@runtime_checkable
class DataSource(Protocol):
    """
    Abstract interface for market data sources.

    Implementations:
    - MockDataSource: Random walk with scenarios (Phase 1)
    - TigerDataSource: Real-time quotes via Tiger Trading (tigeropen SDK)
    - FutuDataSource: Real Futu OpenD connection (Phase 2)
    - HistoricalReplaySource: Historical data replay (Phase 2)
    """

    async def start(self) -> None:
        """Start the data source."""
        ...

    async def stop(self) -> None:
        """Stop the data source and cleanup."""
        ...

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols. Idempotent."""
        ...

    def quotes(self) -> AsyncIterator[MarketData]:
        """Async iterator yielding MarketData events."""
        ...
