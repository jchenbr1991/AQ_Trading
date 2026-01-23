# backend/tests/orders/test_fill_handling.py
"""Tests for OrderManager fill handling with idempotency."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.orders.manager import OrderManager
from src.orders.models import OrderStatus
from src.strategies.signals import OrderFill, Signal


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.submit_order = AsyncMock(return_value="BRK-001")
    broker.subscribe_fills = MagicMock()
    return broker


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.record_fill = AsyncMock()
    return portfolio


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.brpop = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def order_manager(mock_broker, mock_portfolio, mock_redis):
    return OrderManager(
        broker=mock_broker,
        portfolio=mock_portfolio,
        redis=mock_redis,
        db_session=MagicMock(),
        account_id="ACC001",
    )


class TestFillHandling:
    @pytest.mark.asyncio
    async def test_full_fill_updates_order(self, order_manager):
        """Full fill updates order status to FILLED."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill)

        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 100
        assert order.avg_fill_price == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_partial_fill_updates_order(self, order_manager):
        """Partial fill updates status to PARTIAL_FILL."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=60,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill)

        assert order.status == OrderStatus.PARTIAL_FILL
        assert order.filled_qty == 60

    @pytest.mark.asyncio
    async def test_multiple_partials_complete_order(self, order_manager):
        """Multiple partial fills complete the order."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill1 = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=60,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )
        fill2 = OrderFill(
            fill_id="FILL-002",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=40,
            price=Decimal("151.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill1)
        await order_manager.handle_fill(fill2)

        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 100

    @pytest.mark.asyncio
    async def test_avg_price_calculation(self, order_manager):
        """Average fill price is calculated correctly."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        # 60 @ 150 + 40 @ 160 = 9000 + 6400 = 15400 / 100 = 154
        fill1 = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=60,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )
        fill2 = OrderFill(
            fill_id="FILL-002",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=40,
            price=Decimal("160.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill1)
        await order_manager.handle_fill(fill2)

        assert order.avg_fill_price == Decimal("154.00")

    @pytest.mark.asyncio
    async def test_fill_updates_portfolio(self, order_manager, mock_portfolio):
        """Fill triggers portfolio update."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill)

        mock_portfolio.record_fill.assert_called_once()

    @pytest.mark.asyncio
    async def test_fill_publishes_event(self, order_manager, mock_redis):
        """Fill publishes event to Redis."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fills"

    @pytest.mark.asyncio
    async def test_completed_order_removed_from_active(self, order_manager):
        """Filled orders are removed from active tracking."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)
        order_id = order.order_id

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill)

        assert order_id not in order_manager.active_orders


class TestFillIdempotency:
    """CRITICAL: Tests for fill deduplication."""

    @pytest.mark.asyncio
    async def test_duplicate_fill_ignored(self, order_manager, mock_portfolio):
        """Same fill_id is only processed once."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        # Process same fill twice
        await order_manager.handle_fill(fill)
        await order_manager.handle_fill(fill)  # Duplicate!

        # Should only update portfolio once
        assert mock_portfolio.record_fill.call_count == 1
        # Order was removed after first fill (status FILLED)
        # So we can't check filled_qty directly

    @pytest.mark.asyncio
    async def test_different_fill_ids_processed(self, order_manager, mock_portfolio):
        """Different fill_ids are all processed."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill1 = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=50,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )
        fill2 = OrderFill(
            fill_id="FILL-002",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=50,
            price=Decimal("151.00"),
            timestamp=datetime.utcnow(),
        )

        await order_manager.handle_fill(fill1)
        await order_manager.handle_fill(fill2)

        assert mock_portfolio.record_fill.call_count == 2
