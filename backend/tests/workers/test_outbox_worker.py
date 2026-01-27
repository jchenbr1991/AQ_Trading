"""Tests for OutboxWorker."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
import pytest_asyncio
from src.models.account import Account
from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.outbox import OutboxEvent, OutboxEventStatus
from src.models.position import AssetType, Position, PositionStatus


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
async def pending_event(db_session, account):
    """Create a pending outbox event with close request."""
    # Create position
    pos = Position(
        account_id=account.account_id,
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
        status=CloseRequestStatus.PENDING,
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

    # Create outbox event
    event = OutboxEvent(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={
            "close_request_id": str(cr.id),
            "position_id": pos.id,
            "symbol": pos.symbol,
            "side": "sell",
            "qty": 10,
            "asset_type": "option",
        },
        status=OutboxEventStatus.PENDING,
        retry_count=0,
    )
    db_session.add(event)
    await db_session.commit()

    return event, cr, pos


@pytest.mark.asyncio
async def test_process_event_submits_order(db_session, pending_event):
    """Should submit order to broker when processing event."""
    from src.workers.outbox_worker import OutboxWorker

    event, cr, pos = pending_event

    # Mock order manager
    mock_order = MagicMock()
    mock_order.status = "SUBMITTED"
    mock_order.order_id = "ORD-123"

    mock_order_manager = AsyncMock()
    mock_order_manager.submit_order.return_value = mock_order

    # Mock market data
    mock_quote = MagicMock()
    mock_quote.bid = Decimal("1.50")
    mock_quote.ask = Decimal("1.55")
    mock_quote.last = Decimal("1.52")

    mock_market_data = AsyncMock()
    mock_market_data.get_quote.return_value = mock_quote

    worker = OutboxWorker(
        db_session,
        order_manager=mock_order_manager,
        market_data=mock_market_data,
    )

    await worker.process_event(event)

    # Verify order submitted
    mock_order_manager.submit_order.assert_called_once()
    call_args = mock_order_manager.submit_order.call_args
    assert call_args.kwargs["symbol"] == "AAPL240119C00150000"
    assert call_args.kwargs["side"] == "sell"
    assert call_args.kwargs["qty"] == 10


@pytest.mark.asyncio
async def test_process_event_marks_completed_on_success(db_session, pending_event):
    """Should mark event as completed after successful processing."""
    from src.workers.outbox_worker import OutboxWorker

    event, cr, pos = pending_event

    mock_order = MagicMock()
    mock_order.status = "SUBMITTED"

    mock_order_manager = AsyncMock()
    mock_order_manager.submit_order.return_value = mock_order

    mock_quote = MagicMock()
    mock_quote.bid = Decimal("1.50")
    mock_quote.ask = Decimal("1.55")

    mock_market_data = AsyncMock()
    mock_market_data.get_quote.return_value = mock_quote

    worker = OutboxWorker(db_session, mock_order_manager, mock_market_data)
    await worker.process_event(event)

    await db_session.refresh(event)
    assert event.status == OutboxEventStatus.COMPLETED


@pytest.mark.asyncio
async def test_process_event_retries_on_failure(db_session, pending_event):
    """Should increment retry count on failure."""
    from src.workers.outbox_worker import OutboxWorker

    event, cr, pos = pending_event

    mock_order_manager = AsyncMock()
    mock_order_manager.submit_order.side_effect = RuntimeError("Broker error")

    mock_quote = MagicMock()
    mock_quote.bid = Decimal("1.50")
    mock_quote.ask = Decimal("1.55")

    mock_market_data = AsyncMock()
    mock_market_data.get_quote.return_value = mock_quote

    worker = OutboxWorker(db_session, mock_order_manager, mock_market_data)

    with pytest.raises(RuntimeError):
        await worker.process_event(event)

    await db_session.refresh(event)
    assert event.retry_count == 1
    assert event.status == OutboxEventStatus.PENDING  # Reset for retry


@pytest.mark.asyncio
async def test_process_event_marks_failed_after_max_retries(db_session, pending_event):
    """Should mark as failed after max retries."""
    from src.workers.outbox_worker import OutboxWorker

    event, cr, pos = pending_event
    event.retry_count = 2  # Already retried twice
    await db_session.commit()

    mock_order_manager = AsyncMock()
    mock_order_manager.submit_order.side_effect = RuntimeError("Broker error")

    mock_quote = MagicMock()
    mock_quote.bid = Decimal("1.50")
    mock_quote.ask = Decimal("1.55")

    mock_market_data = AsyncMock()
    mock_market_data.get_quote.return_value = mock_quote

    worker = OutboxWorker(db_session, mock_order_manager, mock_market_data)

    with pytest.raises(RuntimeError):
        await worker.process_event(event)

    await db_session.refresh(event)
    assert event.status == OutboxEventStatus.FAILED
    assert event.retry_count == 3
