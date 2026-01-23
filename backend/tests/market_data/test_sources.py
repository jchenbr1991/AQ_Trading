# backend/tests/market_data/test_sources.py
"""Tests for data source protocol and implementations."""

from collections.abc import AsyncIterator

from src.strategies.base import MarketData


class TestDataSourceProtocol:
    def test_protocol_is_runtime_checkable(self):
        """DataSource protocol can be checked at runtime."""
        from src.market_data.sources.base import DataSource

        class FakeSource:
            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

            async def subscribe(self, symbols: list[str]) -> None:
                pass

            def quotes(self) -> AsyncIterator[MarketData]:
                pass

        assert isinstance(FakeSource(), DataSource)

    def test_incomplete_implementation_not_instance(self):
        """Incomplete implementation is not a DataSource."""
        from src.market_data.sources.base import DataSource

        class IncompleteSource:
            async def start(self) -> None:
                pass

            # Missing other methods

        assert not isinstance(IncompleteSource(), DataSource)
