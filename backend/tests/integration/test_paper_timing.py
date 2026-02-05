# backend/tests/integration/test_paper_timing.py
"""Integration tests for signal generation timing validation.

Implements T042: Signal generation timing validation (< 5 seconds per SC-005).

SC-005 requires that strategy signal generation completes in under 5 seconds
per bar to ensure real-time trading viability.
"""

import asyncio
import time
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from src.strategies.base import MarketData
from src.strategies.context import StrategyContext
from src.strategies.examples.trend_breakout import TrendBreakoutStrategy


class TestPaperTradingTiming:
    """Test timing requirements for paper trading signal generation."""

    # SC-005: Maximum allowed time for signal generation per bar
    MAX_SIGNAL_GENERATION_TIME_SECONDS = 5.0

    @pytest.fixture
    def strategy(self) -> TrendBreakoutStrategy:
        """Create a TrendBreakoutStrategy instance for testing."""
        return TrendBreakoutStrategy(
            name="test-timing-strategy",
            symbols=["AAPL"],
            entry_threshold=0.0,
            exit_threshold=-0.02,
            position_sizing="equal_weight",
            position_size=100,
        )

    @pytest.fixture
    def mock_context(self) -> StrategyContext:
        """Create a mock StrategyContext that returns no position."""
        context = MagicMock(spec=StrategyContext)

        async def get_position(symbol: str):
            return None

        context.get_position = get_position
        return context

    def _create_market_data(
        self,
        symbol: str = "AAPL",
        price: Decimal = Decimal("150.00"),
        volume: int = 1000000,
    ) -> MarketData:
        """Create MarketData for testing."""
        return MarketData(
            symbol=symbol,
            price=price,
            bid=price - Decimal("0.01"),
            ask=price + Decimal("0.01"),
            volume=volume,
            timestamp=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_single_bar_signal_generation_timing(
        self, strategy: TrendBreakoutStrategy, mock_context: StrategyContext
    ):
        """Test that processing a single bar completes in under 5 seconds.

        SC-005: Signal generation must complete in < 5 seconds per bar.
        """
        # Generate warmup data to prime the strategy
        warmup_bars = strategy.warmup_bars + 1

        # Warm up the strategy with initial data
        for i in range(warmup_bars):
            price = Decimal("140.00") + Decimal(str(i * 0.5))
            data = self._create_market_data(price=price, volume=1000000 + i * 10000)
            await strategy.on_market_data(data, mock_context)

        # Now test timing of a single bar processing
        test_data = self._create_market_data(
            price=Decimal("160.00"),
            volume=2000000,
        )

        start_time = time.perf_counter()
        signals = await strategy.on_market_data(test_data, mock_context)
        elapsed_time = time.perf_counter() - start_time

        # Assert timing requirement
        assert elapsed_time < self.MAX_SIGNAL_GENERATION_TIME_SECONDS, (
            f"Signal generation took {elapsed_time:.3f}s, "
            f"exceeds SC-005 limit of {self.MAX_SIGNAL_GENERATION_TIME_SECONDS}s"
        )

        # Log actual timing for monitoring
        print(f"\nSingle bar signal generation time: {elapsed_time * 1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_multiple_bars_average_timing(
        self, strategy: TrendBreakoutStrategy, mock_context: StrategyContext
    ):
        """Test average timing over multiple bars remains under threshold.

        This test simulates a more realistic scenario with multiple
        consecutive bars and validates the average processing time.
        """
        warmup_bars = strategy.warmup_bars + 1
        test_bars = 100  # Number of bars to test

        # Warm up the strategy
        for i in range(warmup_bars):
            price = Decimal("140.00") + Decimal(str(i * 0.5))
            data = self._create_market_data(price=price, volume=1000000 + i * 10000)
            await strategy.on_market_data(data, mock_context)

        # Test timing over multiple bars
        timings = []
        base_price = Decimal("160.00")

        for i in range(test_bars):
            # Simulate price movement
            price = base_price + Decimal(str((i % 20 - 10) * 0.25))
            volume = 1500000 + (i % 10) * 50000

            data = self._create_market_data(price=price, volume=volume)

            start_time = time.perf_counter()
            await strategy.on_market_data(data, mock_context)
            elapsed_time = time.perf_counter() - start_time

            timings.append(elapsed_time)

        # Calculate statistics
        avg_time = sum(timings) / len(timings)
        max_time = max(timings)
        min_time = min(timings)

        # All individual bars must be under the limit
        assert max_time < self.MAX_SIGNAL_GENERATION_TIME_SECONDS, (
            f"Maximum signal generation time {max_time:.3f}s "
            f"exceeds SC-005 limit of {self.MAX_SIGNAL_GENERATION_TIME_SECONDS}s"
        )

        # Log timing statistics
        print(f"\nTiming statistics over {test_bars} bars:")
        print(f"  Average: {avg_time * 1000:.2f}ms")
        print(f"  Min: {min_time * 1000:.2f}ms")
        print(f"  Max: {max_time * 1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_paper_broker_fill_timing(self):
        """Test that paper broker order execution is performant.

        While SC-005 focuses on signal generation, this test ensures
        the paper broker doesn't add significant latency.
        """
        from src.broker.paper_broker import PaperBroker
        from src.orders.models import Order, OrderStatus

        broker = PaperBroker(
            fill_delay=0.0,  # No artificial delay for timing test
            slippage_bps=5,
        )

        # Create a test order with all required fields
        order = Order(
            order_id="TEST-001",
            broker_order_id=None,
            strategy_id="test-timing-strategy",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.PENDING,
        )

        start_time = time.perf_counter()
        broker_id = await broker.submit_order(order)
        submit_time = time.perf_counter() - start_time

        # Wait for fill (with zero delay, should be nearly instant)
        await asyncio.sleep(0.01)

        status = await broker.get_order_status(broker_id)

        # Order submission should be nearly instantaneous
        assert submit_time < 0.1, f"Order submission took {submit_time:.3f}s, expected < 0.1s"

        print(f"\nPaper broker order submission time: {submit_time * 1000:.2f}ms")

    @pytest.mark.asyncio
    async def test_end_to_end_paper_trading_timing(
        self, strategy: TrendBreakoutStrategy, mock_context: StrategyContext
    ):
        """Test complete paper trading cycle timing.

        This tests the full cycle:
        1. Receive market data
        2. Process through strategy
        3. Generate signal
        4. Submit to paper broker

        Total time should remain under SC-005 limit.
        """
        from src.broker.paper_broker import PaperBroker
        from src.orders.models import Order, OrderStatus

        broker = PaperBroker(fill_delay=0.0, slippage_bps=5)

        # Warm up strategy
        warmup_bars = strategy.warmup_bars + 1
        for i in range(warmup_bars):
            price = Decimal("140.00") + Decimal(str(i * 0.5))
            data = self._create_market_data(price=price, volume=1000000 + i * 10000)
            await strategy.on_market_data(data, mock_context)

        # Test complete cycle
        test_data = self._create_market_data(
            price=Decimal("170.00"),  # Price that should trigger entry
            volume=3000000,  # High volume for breakout
        )

        start_time = time.perf_counter()

        # Step 1: Process market data and generate signal
        signals = await strategy.on_market_data(test_data, mock_context)

        signal_gen_time = time.perf_counter() - start_time

        # Step 2: If signal generated, submit order
        if signals:
            signal = signals[0]
            order = Order(
                order_id=f"ORDER-{signal.symbol}",
                broker_order_id=None,
                strategy_id=strategy.name,
                symbol=signal.symbol,
                side=signal.action,
                quantity=signal.quantity,
                order_type="market",
                limit_price=None,
                status=OrderStatus.PENDING,
            )
            await broker.submit_order(order)

        total_time = time.perf_counter() - start_time

        # Total cycle time should be under the limit
        assert total_time < self.MAX_SIGNAL_GENERATION_TIME_SECONDS, (
            f"End-to-end paper trading cycle took {total_time:.3f}s, "
            f"exceeds SC-005 limit of {self.MAX_SIGNAL_GENERATION_TIME_SECONDS}s"
        )

        print("\nEnd-to-end paper trading timing:")
        print(f"  Signal generation: {signal_gen_time * 1000:.2f}ms")
        print(f"  Total cycle: {total_time * 1000:.2f}ms")
        print(f"  Signals generated: {len(signals) if signals else 0}")


class TestTimingUnderLoad:
    """Test timing requirements under simulated load conditions."""

    MAX_SIGNAL_GENERATION_TIME_SECONDS = 5.0

    @pytest.fixture
    def strategies(self) -> list[TrendBreakoutStrategy]:
        """Create multiple strategy instances to simulate load."""
        return [
            TrendBreakoutStrategy(
                name=f"test-strategy-{i}",
                symbols=["AAPL", "MSFT", "GOOGL"],
                entry_threshold=0.0,
                exit_threshold=-0.02,
            )
            for i in range(5)
        ]

    @pytest.fixture
    def mock_context(self) -> StrategyContext:
        """Create a mock StrategyContext."""
        context = MagicMock(spec=StrategyContext)

        async def get_position(symbol: str):
            return None

        context.get_position = get_position
        return context

    def _create_market_data(
        self,
        symbol: str,
        price: Decimal,
        volume: int,
    ) -> MarketData:
        """Create MarketData for testing."""
        return MarketData(
            symbol=symbol,
            price=price,
            bid=price - Decimal("0.01"),
            ask=price + Decimal("0.01"),
            volume=volume,
            timestamp=datetime.now(timezone.utc),
        )

    @pytest.mark.asyncio
    async def test_concurrent_strategy_timing(
        self, strategies: list[TrendBreakoutStrategy], mock_context: StrategyContext
    ):
        """Test that multiple strategies processing concurrently meet timing requirements.

        Simulates a scenario where multiple strategies receive
        market data simultaneously.
        """
        warmup_bars = 21

        # Warm up all strategies
        for i in range(warmup_bars):
            for symbol in ["AAPL", "MSFT", "GOOGL"]:
                price = Decimal("150.00") + Decimal(str(i * 0.3))
                data = self._create_market_data(symbol, price, 1000000 + i * 10000)

                for strategy in strategies:
                    await strategy.on_market_data(data, mock_context)

        # Test concurrent processing
        test_data_list = [
            self._create_market_data("AAPL", Decimal("165.00"), 2000000),
            self._create_market_data("MSFT", Decimal("380.00"), 1500000),
            self._create_market_data("GOOGL", Decimal("140.00"), 1800000),
        ]

        start_time = time.perf_counter()

        # Process all strategies concurrently
        tasks = []
        for strategy in strategies:
            for data in test_data_list:
                tasks.append(strategy.on_market_data(data, mock_context))

        await asyncio.gather(*tasks)

        total_time = time.perf_counter() - start_time

        # Even with concurrent processing, total time should be reasonable
        # With 5 strategies x 3 symbols = 15 concurrent operations
        assert total_time < self.MAX_SIGNAL_GENERATION_TIME_SECONDS, (
            f"Concurrent strategy processing took {total_time:.3f}s, "
            f"exceeds limit of {self.MAX_SIGNAL_GENERATION_TIME_SECONDS}s"
        )

        strategies_count = len(strategies)
        symbols_count = len(test_data_list)
        print(f"\nConcurrent processing ({strategies_count} strategies x {symbols_count} symbols):")
        print(f"  Total time: {total_time * 1000:.2f}ms")
        print(f"  Per-operation: {total_time * 1000 / (strategies_count * symbols_count):.2f}ms")
