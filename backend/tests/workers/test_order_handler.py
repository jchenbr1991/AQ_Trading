"""Tests for order update handler."""

import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import uuid4

from src.models.account import Account
from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType
from src.models.position import Position, PositionStatus, AssetType


@pytest_asyncio.fixture
async def account(db_session):
    """Create a test account."""
    acc = Account(
        account_id="ACC001",
        broker="futu",
        currency="USD",
    )
    db_session.add(acc)
    await db_session.commit()
    return acc


@pytest_asyncio.fixture
async def close_order_setup(db_session, account):
    """Create position, close request, and order for testing."""
    # Create position
    pos = Position(
        account_id="ACC001",
        symbol="AAPL240119C00150000",
        asset_type=AssetType.OPTION,
        quantity=10,
        status=PositionStatus.CLOSING,
    )
    db_session.add(pos)
    await db_session.flush()

    # Create close request
    cr = CloseRequest(
        id=uuid4(),
        position_id=pos.id,
        idempotency_key="test-key",
        status=CloseRequestStatus.SUBMITTED,
        symbol=pos.symbol,
        side="sell",
        asset_type="option",
        target_qty=10,
        filled_qty=0,
        retry_count=0,
        max_retries=3,
    )
    db_session.add(cr)
    pos.active_close_request_id = cr.id
    await db_session.flush()

    # Create order
    order = OrderRecord(
        order_id=f"ord-{uuid4()}",
        broker_order_id="BROKER-123",
        account_id="ACC001",
        strategy_id="close",
        symbol=pos.symbol,
        side=OrderSide.SELL,
        quantity=10,
        order_type=OrderType.LIMIT,
        limit_price=Decimal("1.50"),
        status=OrderStatus.SUBMITTED,
        filled_qty=0,
        close_request_id=cr.id,
    )
    db_session.add(order)
    await db_session.commit()

    return pos, cr, order


@pytest.mark.asyncio
async def test_on_order_update_updates_status(db_session, close_order_setup):
    """Should update order status on valid update."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="PARTIAL",
        filled_qty=5,
    )

    await db_session.refresh(order)
    assert order.status == OrderStatus.PARTIAL_FILL
    assert order.filled_qty == 5


@pytest.mark.asyncio
async def test_on_order_update_ignores_backward_status(db_session, close_order_setup):
    """Should ignore status that goes backward in progression."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.status = OrderStatus.PARTIAL_FILL
    order.filled_qty = 5
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="SUBMITTED",  # Backward from PARTIAL
        filled_qty=5,
    )

    await db_session.refresh(order)
    assert order.status == OrderStatus.PARTIAL_FILL  # Unchanged


@pytest.mark.asyncio
async def test_on_order_update_completes_close_request(db_session, close_order_setup):
    """Should mark close request completed when order filled."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="FILLED",
        filled_qty=10,
    )

    await db_session.refresh(cr)
    await db_session.refresh(pos)
    assert cr.status == CloseRequestStatus.COMPLETED
    assert cr.filled_qty == 10
    assert pos.status == PositionStatus.CLOSED


@pytest.mark.asyncio
async def test_on_order_update_unknown_order(db_session, account):
    """Should handle unknown order gracefully."""
    from src.workers.order_handler import OrderUpdateHandler

    handler = OrderUpdateHandler(db_session)
    # Should not raise
    await handler.on_order_update(
        broker_order_id="UNKNOWN-123",
        broker_status="FILLED",
        filled_qty=10,
    )


@pytest.mark.asyncio
async def test_on_order_update_idempotent_with_sequence(db_session, close_order_setup):
    """Should skip update with older sequence number."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.broker_update_seq = 5
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="FILLED",
        filled_qty=10,
        broker_update_seq=3,  # Older than 5
    )

    await db_session.refresh(order)
    assert order.status == OrderStatus.SUBMITTED  # Unchanged
    assert order.filled_qty == 0


@pytest.mark.asyncio
async def test_late_filled_upgrades_cancelled(db_session, close_order_setup):
    """Should upgrade CANCELLED to FILLED on late fill arrival."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.status = OrderStatus.CANCELLED
    order.filled_qty = 0
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="FILLED",
        filled_qty=10,
    )

    await db_session.refresh(order)
    assert order.status == OrderStatus.FILLED
    assert order.filled_qty == 10


@pytest.mark.asyncio
async def test_filled_qty_always_increases(db_session, close_order_setup):
    """Should never decrease filled_qty even on backward status."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.status = OrderStatus.PARTIAL_FILL
    order.filled_qty = 7
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="PARTIAL",
        filled_qty=5,  # Lower than current
    )

    await db_session.refresh(order)
    assert order.filled_qty == 7  # Should stay at 7


@pytest.mark.asyncio
async def test_partial_fill_sets_close_request_retryable(db_session, close_order_setup):
    """Should mark close request retryable when order cancelled with partial fill."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.status = OrderStatus.PARTIAL_FILL
    order.filled_qty = 5
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="CANCELLED",
        filled_qty=5,
    )

    await db_session.refresh(cr)
    await db_session.refresh(pos)
    assert cr.status == CloseRequestStatus.RETRYABLE
    assert cr.filled_qty == 5
    assert pos.status == PositionStatus.CLOSE_RETRYABLE


@pytest.mark.asyncio
async def test_zero_fill_cancellation_fails_request(db_session, close_order_setup):
    """Should mark close request failed when order cancelled with zero fills."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="CANCELLED",
        filled_qty=0,
    )

    await db_session.refresh(cr)
    await db_session.refresh(pos)
    assert cr.status == CloseRequestStatus.FAILED
    assert pos.status == PositionStatus.OPEN


@pytest.mark.asyncio
async def test_already_filled_ignores_updates(db_session, close_order_setup):
    """Should ignore any updates when order is already FILLED."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.status = OrderStatus.FILLED
    order.filled_qty = 10
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="CANCELLED",  # Should be ignored
        filled_qty=5,
    )

    await db_session.refresh(order)
    assert order.status == OrderStatus.FILLED  # Unchanged
    assert order.filled_qty == 10


@pytest.mark.asyncio
async def test_newer_sequence_accepted(db_session, close_order_setup):
    """Should accept update with newer sequence number."""
    from src.workers.order_handler import OrderUpdateHandler

    pos, cr, order = close_order_setup
    order.broker_update_seq = 5
    await db_session.commit()

    handler = OrderUpdateHandler(db_session)
    await handler.on_order_update(
        broker_order_id="BROKER-123",
        broker_status="PARTIAL",
        filled_qty=5,
        broker_update_seq=10,  # Newer than 5
    )

    await db_session.refresh(order)
    assert order.status == OrderStatus.PARTIAL_FILL
    assert order.filled_qty == 5
    assert order.broker_update_seq == 10
