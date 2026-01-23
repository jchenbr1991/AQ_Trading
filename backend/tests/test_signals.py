# backend/tests/test_signals.py
from datetime import datetime
from decimal import Decimal

from src.strategies.signals import OrderFill, Signal


class TestSignal:
    def test_signal_creation_with_defaults(self):
        signal = Signal(
            strategy_id="momentum_v1",
            symbol="AAPL",
            action="buy",
            quantity=100,
        )

        assert signal.strategy_id == "momentum_v1"
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.quantity == 100
        assert signal.order_type == "market"
        assert signal.limit_price is None
        assert signal.reason == ""
        assert isinstance(signal.timestamp, datetime)

    def test_signal_with_limit_order(self):
        signal = Signal(
            strategy_id="mean_rev",
            symbol="TSLA",
            action="sell",
            quantity=50,
            order_type="limit",
            limit_price=Decimal("250.00"),
            reason="Mean reversion target hit",
        )

        assert signal.order_type == "limit"
        assert signal.limit_price == Decimal("250.00")
        assert signal.reason == "Mean reversion target hit"


class TestSignalSerialization:
    def test_signal_to_json(self):
        """Signal serializes to JSON."""
        signal = Signal(
            strategy_id="momentum",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("150.50"),
            reason="Price crossed MA",
        )

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.strategy_id == signal.strategy_id
        assert restored.symbol == signal.symbol
        assert restored.action == signal.action
        assert restored.quantity == signal.quantity
        assert restored.order_type == signal.order_type
        assert restored.limit_price == signal.limit_price
        assert restored.reason == signal.reason

    def test_signal_market_order(self):
        """Market order signal without limit price."""
        signal = Signal(
            strategy_id="test",
            symbol="GOOGL",
            action="sell",
            quantity=50,
        )

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.order_type == "market"
        assert restored.limit_price is None


class TestOrderFillSerialization:
    def test_order_fill_to_json(self):
        """OrderFill serializes to JSON."""
        fill = OrderFill(
            fill_id="FILL-123",
            order_id="ord-123",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.25"),
            timestamp=datetime(2026, 1, 23, 12, 0, 0),
        )

        json_str = fill.to_json()
        restored = OrderFill.from_json(json_str)

        assert restored.fill_id == fill.fill_id
        assert restored.order_id == fill.order_id
        assert restored.symbol == fill.symbol
        assert restored.side == fill.side
        assert restored.quantity == fill.quantity
        assert restored.price == fill.price
