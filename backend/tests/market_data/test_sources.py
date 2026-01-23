# backend/tests/market_data/test_sources.py
"""Tests for data source protocol and implementations."""

from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
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


class TestMockDataSource:
    @pytest.mark.asyncio
    async def test_implements_datasource_protocol(self):
        """MockDataSource implements DataSource protocol."""
        from src.market_data.models import MarketDataConfig, SymbolScenario
        from src.market_data.sources.base import DataSource
        from src.market_data.sources.mock import MockDataSource

        config = MarketDataConfig(
            symbols={
                "AAPL": SymbolScenario(
                    symbol="AAPL",
                    scenario="flat",
                    base_price=Decimal("150.00"),
                )
            }
        )
        source = MockDataSource(config)

        assert isinstance(source, DataSource)

    @pytest.mark.asyncio
    async def test_generates_quotes_for_subscribed_symbols(self):
        """MockDataSource generates quotes for subscribed symbols."""
        from src.market_data.models import MarketDataConfig, SymbolScenario
        from src.market_data.sources.mock import MockDataSource

        config = MarketDataConfig(
            symbols={
                "AAPL": SymbolScenario(
                    symbol="AAPL",
                    scenario="flat",
                    base_price=Decimal("150.00"),
                    tick_interval_ms=10,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["AAPL"])
        await source.start()

        quotes = []
        async for quote in source.quotes():
            quotes.append(quote)
            if len(quotes) >= 3:
                break

        await source.stop()

        assert len(quotes) == 3
        assert all(q.symbol == "AAPL" for q in quotes)
        assert all(q.price > 0 for q in quotes)

    @pytest.mark.asyncio
    async def test_quote_has_bid_ask_spread(self):
        """Generated quotes have bid < price < ask."""
        from src.market_data.models import MarketDataConfig, SymbolScenario
        from src.market_data.sources.mock import MockDataSource

        config = MarketDataConfig(
            symbols={
                "TEST": SymbolScenario(
                    symbol="TEST",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=10,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["TEST"])
        await source.start()

        async for quote in source.quotes():
            assert quote.bid < quote.price < quote.ask
            break

        await source.stop()
