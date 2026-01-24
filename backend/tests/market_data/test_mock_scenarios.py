# backend/tests/market_data/test_mock_scenarios.py
"""Tests for MockDataSource scenario behaviors."""

import asyncio
from decimal import Decimal

import pytest
from src.market_data.models import MarketDataConfig, SymbolScenario
from src.market_data.sources.mock import MockDataSource


class TestFlatScenario:
    @pytest.mark.asyncio
    async def test_flat_minimal_movement(self):
        """Flat scenario has near-zero price movement."""
        config = MarketDataConfig(
            symbols={
                "FLAT": SymbolScenario(
                    symbol="FLAT",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["FLAT"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 50:
                break
        await source.stop()

        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        assert variance < 0.1


class TestTrendScenarios:
    @pytest.mark.asyncio
    async def test_trend_up_positive_drift(self):
        """Trend up scenario shows upward bias."""
        config = MarketDataConfig(
            symbols={
                "UP": SymbolScenario(
                    symbol="UP",
                    scenario="trend_up",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["UP"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 100:
                break
        await source.stop()

        first_quarter = sum(prices[:25]) / 25
        last_quarter = sum(prices[-25:]) / 25
        assert last_quarter > first_quarter

    @pytest.mark.asyncio
    async def test_trend_down_negative_drift(self):
        """Trend down scenario shows downward bias."""
        config = MarketDataConfig(
            symbols={
                "DOWN": SymbolScenario(
                    symbol="DOWN",
                    scenario="trend_down",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["DOWN"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 100:
                break
        await source.stop()

        first_quarter = sum(prices[:25]) / 25
        last_quarter = sum(prices[-25:]) / 25
        assert last_quarter < first_quarter


class TestVolatileScenario:
    @pytest.mark.asyncio
    async def test_volatile_high_variance(self):
        """Volatile scenario has high price variance."""
        config = MarketDataConfig(
            symbols={
                "VOL": SymbolScenario(
                    symbol="VOL",
                    scenario="volatile",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["VOL"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 50:
                break
        await source.stop()

        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        assert variance > 0.5


class TestJumpScenario:
    @pytest.mark.asyncio
    async def test_jump_occasional_large_moves(self):
        """Jump scenario has occasional large price moves."""
        config = MarketDataConfig(
            symbols={
                "JUMP": SymbolScenario(
                    symbol="JUMP",
                    scenario="jump",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["JUMP"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 200:
                break
        await source.stop()

        changes = [abs(prices[i] - prices[i - 1]) / prices[i - 1] for i in range(1, len(prices))]
        large_moves = [c for c in changes if c > 0.03]
        assert len(large_moves) >= 1


class TestStaleScenario:
    @pytest.mark.asyncio
    async def test_stale_stops_emitting_periodically(self):
        """Stale scenario pauses emission periodically."""
        config = MarketDataConfig(
            symbols={
                "STALE": SymbolScenario(
                    symbol="STALE",
                    scenario="stale",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=10,
                )
            }
        )
        source = MockDataSource(config)
        source._stale_pause_probability = 0.3
        source._stale_pause_duration_ms = (50, 100)

        await source.subscribe(["STALE"])
        await source.start()

        timestamps = []
        start = asyncio.get_event_loop().time()
        async for _quote in source.quotes():
            timestamps.append(asyncio.get_event_loop().time() - start)
            if len(timestamps) >= 20:
                break
        await source.stop()

        gaps = [timestamps[i] - timestamps[i - 1] for i in range(1, len(timestamps))]
        large_gaps = [g for g in gaps if g > 0.04]
        assert len(large_gaps) >= 1
