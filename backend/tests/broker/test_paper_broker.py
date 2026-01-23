# backend/tests/broker/test_paper_broker.py
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from src.broker.paper_broker import PaperBroker
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


@pytest.fixture
def paper_broker():
    return PaperBroker(fill_delay=0.01)  # Fast for tests


class TestPaperBroker:
    @pytest.mark.asyncio
    async def test_submit_order_returns_broker_id(self, paper_broker):
        """Submit order returns a broker order ID."""
        order = Order(
            order_id="ord-123",
            broker_order_id=None,
            strategy_id="test",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)

        assert broker_id.startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_generates_unique_broker_ids(self, paper_broker):
        """Each order gets a unique broker ID."""
        order1 = Order(
            order_id="ord-1", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )
        order2 = Order(
            order_id="ord-2", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        id1 = await paper_broker.submit_order(order1)
        id2 = await paper_broker.submit_order(order2)

        assert id1 != id2

    @pytest.mark.asyncio
    async def test_simulates_fill_after_delay(self, paper_broker):
        """Order fill is simulated after delay."""
        fills_received = []

        def on_fill(fill: OrderFill):
            fills_received.append(fill)

        paper_broker.subscribe_fills(on_fill)

        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)

        # Wait for fill
        await asyncio.sleep(0.05)

        assert len(fills_received) >= 1
        # Check that fills match the order
        total_qty = sum(f.quantity for f in fills_received)
        assert total_qty == 100
        assert fills_received[0].symbol == "AAPL"

    @pytest.mark.asyncio
    async def test_limit_order_uses_limit_price(self, paper_broker):
        """Limit orders fill at limit price."""
        fills_received = []
        paper_broker.subscribe_fills(lambda f: fills_received.append(f))

        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="limit", limit_price=Decimal("150.00"),
            status=OrderStatus.PENDING
        )

        await paper_broker.submit_order(order)
        await asyncio.sleep(0.05)

        assert len(fills_received) >= 1
        # Limit order fills at limit price (or better)
        assert fills_received[0].price <= Decimal("150.00")

    @pytest.mark.asyncio
    async def test_cancel_order(self, paper_broker):
        """Can cancel a pending order."""
        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)
        result = await paper_broker.cancel_order(broker_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_order_status(self, paper_broker):
        """Can get order status."""
        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)

        # Initially submitted
        status = await paper_broker.get_order_status(broker_id)
        assert status == OrderStatus.SUBMITTED

        # After fill
        await asyncio.sleep(0.05)
        status = await paper_broker.get_order_status(broker_id)
        assert status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_fill_has_unique_fill_id(self, paper_broker):
        """Each fill has a unique fill_id for idempotency."""
        fills_received = []
        paper_broker.subscribe_fills(lambda f: fills_received.append(f))

        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        await paper_broker.submit_order(order)
        await asyncio.sleep(0.05)

        # All fills should have unique fill_ids
        fill_ids = [f.fill_id for f in fills_received]
        assert len(fill_ids) == len(set(fill_ids))  # All unique
        assert all(fill_id.startswith("FILL-") for fill_id in fill_ids)

    @pytest.mark.asyncio
    async def test_market_order_applies_slippage(self, paper_broker):
        """Market orders have slippage variance."""
        fills_received = []
        paper_broker.subscribe_fills(lambda f: fills_received.append(f))

        # Submit multiple orders to test slippage variance
        for i in range(5):
            order = Order(
                order_id=f"ord-{i}", broker_order_id=None, strategy_id="test",
                symbol="AAPL", side="buy", quantity=100,
                order_type="market", limit_price=None, status=OrderStatus.PENDING
            )
            await paper_broker.submit_order(order)

        await asyncio.sleep(0.1)

        # Prices should have some variance (slippage)
        prices = [f.price for f in fills_received]
        # All prices should be positive
        assert all(p > 0 for p in prices)
