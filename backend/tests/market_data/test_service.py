# backend/tests/market_data/test_service.py
"""Tests for MarketDataService."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.market_data.models import MarketDataConfig, SymbolScenario


class TestMarketDataServiceSubscription:
    @pytest.mark.asyncio
    async def test_ensure_subscribed_idempotent(self):
        """ensure_subscribed is idempotent."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        config = MarketDataConfig(
            symbols={
                "AAPL": SymbolScenario(symbol="AAPL", scenario="flat", base_price=Decimal("150.00"))
            }
        )
        service = MarketDataService(redis=mock_redis, config=config)

        service.ensure_subscribed(["AAPL", "TSLA"])
        service.ensure_subscribed(["AAPL", "SPY"])

        assert len(service._subscribed) == 3


class TestMarketDataServiceStream:
    @pytest.mark.asyncio
    async def test_get_stream_returns_queue(self):
        """get_stream returns asyncio.Queue."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        config = MarketDataConfig()
        service = MarketDataService(redis=mock_redis, config=config)

        stream = service.get_stream()

        assert isinstance(stream, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_stream_receives_quotes(self):
        """Started service puts quotes on stream."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

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
        service = MarketDataService(redis=mock_redis, config=config)
        service.ensure_subscribed(["TEST"])

        stream = service.get_stream()
        await service.start()

        quotes = []
        for _ in range(3):
            quote = await asyncio.wait_for(stream.get(), timeout=1.0)
            quotes.append(quote)

        await service.stop()

        assert len(quotes) == 3
        assert all(q.symbol == "TEST" for q in quotes)


class TestMarketDataServiceOverflow:
    @pytest.mark.asyncio
    async def test_queue_overflow_drops_oldest(self):
        """Queue overflow drops oldest quotes."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        config = MarketDataConfig(
            queue_max_size=3,
            symbols={
                "FAST": SymbolScenario(
                    symbol="FAST",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            },
        )
        service = MarketDataService(redis=mock_redis, config=config)
        service.ensure_subscribed(["FAST"])

        stream = service.get_stream()
        await service.start()

        await asyncio.sleep(0.05)

        await service.stop()

        assert stream.qsize() <= 3
        assert service._overflow_count > 0


class TestMarketDataServiceGetQuote:
    @pytest.mark.asyncio
    async def test_get_quote_returns_cached(self):
        """get_quote returns cached QuoteSnapshot."""
        from src.market_data.models import QuoteSnapshot
        from src.market_data.service import MarketDataService

        cached_json = '{"symbol": "AAPL", "price": "150.00", "bid": "149.90", "ask": "150.10", "volume": 1000, "timestamp": "2024-01-15T10:00:00", "cached_at": "2024-01-15T10:00:01"}'
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=cached_json)

        config = MarketDataConfig()
        service = MarketDataService(redis=mock_redis, config=config)

        quote = await service.get_quote("AAPL")

        assert quote is not None
        assert isinstance(quote, QuoteSnapshot)
        assert quote.symbol == "AAPL"
        assert quote.price == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_get_quote_returns_none_if_not_cached(self):
        """get_quote returns None if not in Redis."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        config = MarketDataConfig()
        service = MarketDataService(redis=mock_redis, config=config)

        quote = await service.get_quote("UNKNOWN")

        assert quote is None
