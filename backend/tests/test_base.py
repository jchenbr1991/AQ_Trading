# backend/tests/test_base.py
import pytest
from datetime import datetime
from decimal import Decimal

from src.strategies.base import Strategy, MarketData, OrderFill
from src.strategies.signals import Signal
from unittest.mock import MagicMock


class TestMarketData:
    def test_market_data_creation(self):
        data = MarketData(
            symbol="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
            volume=1000000,
            timestamp=datetime(2026, 1, 23, 10, 30, 0),
        )

        assert data.symbol == "AAPL"
        assert data.price == Decimal("185.50")
        assert data.bid == Decimal("185.45")
        assert data.ask == Decimal("185.55")
        assert data.volume == 1000000


class TestOrderFill:
    def test_order_fill_creation(self):
        fill = OrderFill(
            order_id="ORD001",
            strategy_id="momentum_v1",
            symbol="AAPL",
            action="buy",
            quantity=100,
            price=Decimal("185.50"),
            commission=Decimal("1.00"),
            timestamp=datetime(2026, 1, 23, 10, 30, 0),
        )

        assert fill.order_id == "ORD001"
        assert fill.strategy_id == "momentum_v1"
        assert fill.action == "buy"
        assert fill.quantity == 100
        assert fill.price == Decimal("185.50")
        assert fill.commission == Decimal("1.00")


class TestStrategy:
    def test_concrete_strategy_must_implement_on_market_data(self):
        """Strategy ABC requires on_market_data implementation."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            class IncompleteStrategy(Strategy):
                name = "incomplete"
                symbols = ["AAPL"]

            IncompleteStrategy()

    def test_concrete_strategy_can_be_instantiated(self):
        """A complete Strategy subclass can be instantiated."""
        class SimpleStrategy(Strategy):
            name = "simple"
            symbols = ["AAPL"]

            async def on_market_data(self, data: MarketData, context) -> list[Signal]:
                return []

        strategy = SimpleStrategy()
        assert strategy.name == "simple"
        assert strategy.symbols == ["AAPL"]
