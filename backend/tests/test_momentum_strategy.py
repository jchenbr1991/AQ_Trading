# backend/tests/test_momentum_strategy.py
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.strategies.examples.momentum import MomentumStrategy
from src.strategies.base import MarketData
from src.strategies.context import StrategyContext


def make_data(symbol: str, price: float) -> MarketData:
    return MarketData(
        symbol=symbol,
        price=Decimal(str(price)),
        bid=Decimal(str(price - 0.05)),
        ask=Decimal(str(price + 0.05)),
        volume=100000,
        timestamp=datetime.utcnow(),
    )


class TestMomentumStrategy:
    @pytest.fixture
    def strategy(self):
        return MomentumStrategy(
            name="test_momentum",
            symbols=["AAPL"],
            lookback_period=5,
            threshold=0.05,
            position_size=100,
        )

    @pytest.fixture
    def mock_context(self):
        context = MagicMock(spec=StrategyContext)
        context.get_position = AsyncMock(return_value=None)
        return context

    async def test_no_signal_during_warmup(self, strategy, mock_context):
        """No signals until lookback period is filled."""
        # First 4 data points (need 5 for lookback)
        for price in [100, 101, 102, 103]:
            signals = await strategy.on_market_data(
                make_data("AAPL", price), mock_context
            )
            assert signals == []

    async def test_buy_signal_on_momentum_up(self, strategy, mock_context):
        """Buy signal when momentum exceeds threshold."""
        # Fill lookback period with price 100
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price jumps 10% (above 5% threshold)
        signals = await strategy.on_market_data(make_data("AAPL", 110), mock_context)

        assert len(signals) == 1
        assert signals[0].action == "buy"
        assert signals[0].quantity == 100
        assert "10.00%" in signals[0].reason

    async def test_no_signal_when_below_threshold(self, strategy, mock_context):
        """No signal when momentum is below threshold."""
        # Fill lookback period
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price rises only 2% (below 5% threshold)
        signals = await strategy.on_market_data(make_data("AAPL", 102), mock_context)

        assert signals == []

    async def test_sell_signal_on_momentum_down(self, strategy, mock_context):
        """Sell signal when holding and momentum reverses."""
        # Setup: have a position
        mock_position = MagicMock()
        mock_position.quantity = 100
        mock_context.get_position = AsyncMock(return_value=mock_position)

        # Fill lookback period
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price drops 10%
        signals = await strategy.on_market_data(make_data("AAPL", 90), mock_context)

        assert len(signals) == 1
        assert signals[0].action == "sell"
        assert signals[0].quantity == 100

    async def test_no_buy_when_already_holding(self, strategy, mock_context):
        """No buy signal when already holding a position."""
        # Setup: have a position
        mock_position = MagicMock()
        mock_position.quantity = 100
        mock_context.get_position = AsyncMock(return_value=mock_position)

        # Fill lookback period
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price rises 10% but we already hold
        signals = await strategy.on_market_data(make_data("AAPL", 110), mock_context)

        assert signals == []
