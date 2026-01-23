# backend/tests/market_data/test_processor.py
"""Tests for QuoteProcessor."""

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.market_data.models import FaultConfig
from src.strategies.base import MarketData


class TestQuoteProcessorRedisCache:
    @pytest.mark.asyncio
    async def test_writes_quote_to_redis(self):
        """QuoteProcessor writes quote to Redis."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        processor = QuoteProcessor(redis=mock_redis, faults=FaultConfig())

        quote = MarketData(
            symbol="AAPL",
            price=Decimal("150.25"),
            bid=Decimal("150.20"),
            ask=Decimal("150.30"),
            volume=1000,
            timestamp=datetime.utcnow(),
        )

        await processor.process(quote)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "quote:AAPL"

        stored_json = call_args[0][1]
        stored = json.loads(stored_json)
        assert stored["symbol"] == "AAPL"
        assert stored["price"] == "150.25"
        assert "cached_at" in stored

    @pytest.mark.asyncio
    async def test_returns_processed_quote(self):
        """QuoteProcessor returns the processed quote."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        processor = QuoteProcessor(redis=mock_redis, faults=FaultConfig())

        quote = MarketData(
            symbol="TSLA",
            price=Decimal("250.00"),
            bid=Decimal("249.90"),
            ask=Decimal("250.10"),
            volume=500,
            timestamp=datetime.utcnow(),
        )

        result = await processor.process(quote)

        assert result is not None
        assert result.symbol == "TSLA"
        assert result.price == Decimal("250.00")


class TestFaultInjectionDelay:
    @pytest.mark.asyncio
    async def test_delay_adds_latency(self):
        """Delay fault adds latency before processing."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=True,
            delay_probability=1.0,
            delay_ms_range=(50, 50),
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        quote = MarketData(
            symbol="TEST",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=datetime.utcnow(),
        )

        start = asyncio.get_event_loop().time()
        await processor.process(quote)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.045

    @pytest.mark.asyncio
    async def test_faults_disabled_no_delay(self):
        """No delay when faults disabled."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=False,
            delay_probability=1.0,
            delay_ms_range=(100, 100),
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        quote = MarketData(
            symbol="TEST",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=datetime.utcnow(),
        )

        start = asyncio.get_event_loop().time()
        await processor.process(quote)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.05


class TestFaultInjectionDuplicate:
    @pytest.mark.asyncio
    async def test_duplicate_emits_twice(self):
        """Duplicate fault causes quote to be processed twice."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=True,
            duplicate_probability=1.0,
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        quote = MarketData(
            symbol="DUP",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=datetime.utcnow(),
        )

        results = await processor.process(quote)

        assert isinstance(results, list)
        assert len(results) == 2


class TestFaultInjectionOutOfOrder:
    @pytest.mark.asyncio
    async def test_out_of_order_older_timestamp(self):
        """Out of order fault modifies timestamp to appear older."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=True,
            out_of_order_probability=1.0,
            out_of_order_offset_ms=500,
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        original_time = datetime.utcnow()
        quote = MarketData(
            symbol="OOO",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=original_time,
        )

        result = await processor.process(quote)

        assert result.timestamp < original_time
        time_diff = original_time - result.timestamp
        assert time_diff >= timedelta(milliseconds=400)
