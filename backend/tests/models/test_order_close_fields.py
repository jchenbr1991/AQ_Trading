"""Tests for OrderRecord close request fields."""

from uuid import uuid4


def test_order_record_has_close_request_id():
    """OrderRecord should have close_request_id field."""
    from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "close_request_id")
    assert order.close_request_id is None


def test_order_record_has_broker_update_seq():
    """OrderRecord should have broker_update_seq field."""
    from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "broker_update_seq")
    assert order.broker_update_seq is None


def test_order_record_has_reconcile_not_found_count():
    """OrderRecord should have reconcile_not_found_count field."""
    from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "reconcile_not_found_count")
    assert order.reconcile_not_found_count == 0


def test_order_record_has_last_broker_update_at():
    """OrderRecord should have last_broker_update_at field."""
    from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "last_broker_update_at")
    assert order.last_broker_update_at is None


def test_order_record_close_request_id_accepts_uuid():
    """OrderRecord close_request_id should accept UUID values."""
    from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType

    close_id = uuid4()
    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
        close_request_id=close_id,
    )

    assert order.close_request_id == close_id
