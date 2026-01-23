# backend/tests/orders/test_manager.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.orders.manager import OrderManager
from src.orders.models import OrderStatus
from src.strategies.signals import Signal


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
def mock_db():
    return MagicMock()


@pytest.fixture
def order_manager(mock_broker, mock_portfolio, mock_redis, mock_db):
    return OrderManager(
        broker=mock_broker,
        portfolio=mock_portfolio,
        redis=mock_redis,
        db_session=mock_db,
        account_id="ACC001",
    )


class TestOrderManagerProcessSignal:
    @pytest.mark.asyncio
    async def test_creates_order_from_signal(self, order_manager, mock_broker):
        """Signal is converted to Order."""
        signal = Signal(
            strategy_id="momentum", symbol="AAPL", action="buy", quantity=100, order_type="market"
        )

        order = await order_manager.process_signal(signal)

        assert order.strategy_id == "momentum"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.quantity == 100
        assert order.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_submits_to_broker(self, order_manager, mock_broker):
        """Order is submitted to broker."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)

        order = await order_manager.process_signal(signal)

        mock_broker.submit_order.assert_called_once()
        assert order.broker_order_id == "BRK-001"

    @pytest.mark.asyncio
    async def test_tracks_active_order(self, order_manager):
        """Order is tracked in active orders."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)

        order = await order_manager.process_signal(signal)

        assert order.order_id in order_manager.active_orders
        assert order_manager.get_order(order.order_id) == order

    @pytest.mark.asyncio
    async def test_broker_rejection_handled(self, order_manager, mock_broker):
        """Broker rejection updates order status."""
        from src.broker.errors import OrderSubmissionError

        mock_broker.submit_order = AsyncMock(side_effect=OrderSubmissionError("Insufficient funds"))

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)

        order = await order_manager.process_signal(signal)

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient funds" in order.error_message


class TestOrderManagerGetters:
    @pytest.mark.asyncio
    async def test_get_order_by_id(self, order_manager):
        """Can retrieve order by ID."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)

        order = await order_manager.process_signal(signal)
        retrieved = order_manager.get_order(order.order_id)

        assert retrieved == order

    @pytest.mark.asyncio
    async def test_get_orders_by_strategy(self, order_manager, mock_broker):
        """Can filter orders by strategy."""
        # Need unique broker IDs for each order
        mock_broker.submit_order = AsyncMock(side_effect=["BRK-001", "BRK-002", "BRK-003"])

        signal1 = Signal(strategy_id="strat_a", symbol="AAPL", action="buy", quantity=100)
        signal2 = Signal(strategy_id="strat_b", symbol="GOOGL", action="buy", quantity=50)
        signal3 = Signal(strategy_id="strat_a", symbol="MSFT", action="sell", quantity=25)

        await order_manager.process_signal(signal1)
        await order_manager.process_signal(signal2)
        await order_manager.process_signal(signal3)

        strat_a_orders = order_manager.get_orders_by_strategy("strat_a")

        assert len(strat_a_orders) == 2
        assert all(o.strategy_id == "strat_a" for o in strat_a_orders)
