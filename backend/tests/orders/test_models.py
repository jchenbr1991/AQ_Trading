# backend/tests/orders/test_models.py
import pytest
from datetime import datetime
from decimal import Decimal

from src.orders.models import Order, OrderStatus


class TestOrderStatus:
    def test_all_statuses_exist(self):
        """All order statuses are defined."""
        # Active states
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.SUBMITTED.value == "submitted"
        assert OrderStatus.PARTIAL_FILL.value == "partial"
        assert OrderStatus.CANCEL_REQUESTED.value == "cancel_req"
        # Terminal states
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        # Phase 2 placeholders
        assert OrderStatus.EXPIRED.value == "expired"
        assert OrderStatus.UNKNOWN.value == "unknown"


class TestOrder:
    def test_create_market_order(self):
        """Create a market order."""
        order = Order(
            order_id="ord-123",
            broker_order_id=None,
            strategy_id="momentum",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.PENDING
        )

        assert order.order_id == "ord-123"
        assert order.broker_order_id is None
        assert order.strategy_id == "momentum"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.quantity == 100
        assert order.order_type == "market"
        assert order.status == OrderStatus.PENDING
        assert order.filled_qty == 0

    def test_create_limit_order(self):
        """Create a limit order with price."""
        order = Order(
            order_id="ord-456",
            broker_order_id=None,
            strategy_id="mean_rev",
            symbol="GOOGL",
            side="sell",
            quantity=50,
            order_type="limit",
            limit_price=Decimal("150.50"),
            status=OrderStatus.PENDING
        )

        assert order.order_type == "limit"
        assert order.limit_price == Decimal("150.50")

    def test_order_from_signal(self):
        """Create order from Signal."""
        from src.strategies.signals import Signal

        signal = Signal(
            strategy_id="test",
            symbol="MSFT",
            action="buy",
            quantity=25,
            order_type="limit",
            limit_price=Decimal("400.00")
        )

        order = Order.from_signal(signal, order_id="ord-789")

        assert order.order_id == "ord-789"
        assert order.strategy_id == "test"
        assert order.symbol == "MSFT"
        assert order.side == "buy"
        assert order.quantity == 25
        assert order.order_type == "limit"
        assert order.limit_price == Decimal("400.00")
        assert order.status == OrderStatus.PENDING

    def test_order_to_json(self):
        """Serialize order to JSON."""
        order = Order(
            order_id="ord-123",
            broker_order_id="BRK-456",
            strategy_id="test",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.FILLED,
            filled_qty=100,
            avg_fill_price=Decimal("150.25")
        )

        data = order.to_json()
        restored = Order.from_json(data)

        assert restored.order_id == order.order_id
        assert restored.status == order.status
        assert restored.avg_fill_price == order.avg_fill_price
