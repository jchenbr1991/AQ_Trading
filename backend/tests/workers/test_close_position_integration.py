"""Integration tests for close position flow."""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from sqlalchemy import select

from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType
from src.models.outbox import OutboxEvent, OutboxEventStatus
from src.models.position import AssetType, Position, PositionStatus
from src.workers.order_handler import OrderUpdateHandler
from src.workers.outbox_worker import OutboxWorker
from src.workers.reconciler import Reconciler


@pytest_asyncio.fixture
async def mock_order_manager():
    """Mock order manager that simulates order submission."""
    manager = AsyncMock()
    return manager


@pytest_asyncio.fixture
async def mock_market_data():
    """Mock market data with valid quotes."""
    market_data = AsyncMock()
    quote = MagicMock()
    quote.bid = 1.50
    quote.ask = 1.55
    quote.last = 1.52
    market_data.get_quote.return_value = quote
    return market_data


class TestCloseToFillFlow:
    """E2E test: close → order submitted → fill → position closed."""

    @pytest.mark.asyncio
    async def test_full_close_flow_happy_path(
        self, db_session, mock_order_manager, mock_market_data
    ):
        """Complete flow from close request to position closed."""
        # Setup: Create open position
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.OPEN,
        )
        db_session.add(position)
        await db_session.flush()

        # Step 1: Create close request (simulating API endpoint)
        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-1",
            status=CloseRequestStatus.PENDING,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
        )
        db_session.add(close_request)
        position.status = PositionStatus.CLOSING
        position.active_close_request_id = close_request.id

        # Create outbox event
        outbox_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={
                "close_request_id": str(close_request.id),
                "position_id": position.id,
                "symbol": "AAPL240119C00150000",
                "side": "sell",
                "qty": 10,
                "asset_type": "option",
            },
            status=OutboxEventStatus.PENDING,
        )
        db_session.add(outbox_event)
        await db_session.commit()

        # Step 2: Process outbox event (simulating worker)
        # Mock order submission to return a submitted order
        mock_order = MagicMock()
        mock_order.status = "SUBMITTED"
        mock_order.broker_order_id = "BROKER-001"
        mock_order_manager.submit_order.return_value = mock_order

        outbox_worker = OutboxWorker(db_session, mock_order_manager, mock_market_data)
        await outbox_worker.process_event(outbox_event)

        await db_session.refresh(close_request)
        assert close_request.status == CloseRequestStatus.SUBMITTED

        # Step 3: Create order record (simulating OrderManager callback)
        order = OrderRecord(
            order_id="ord-001",
            broker_order_id="BROKER-001",
            account_id="ACC001",
            strategy_id="close",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
        )
        db_session.add(order)
        await db_session.commit()

        # Step 4: Order gets filled (simulating broker callback)
        handler = OrderUpdateHandler(db_session)
        await handler.on_order_update(
            broker_order_id="BROKER-001",
            broker_status="FILLED",
            filled_qty=10,
            broker_update_seq=1,
        )

        # Verify final state
        await db_session.refresh(position)
        await db_session.refresh(close_request)
        await db_session.refresh(order)

        assert position.status == PositionStatus.CLOSED
        assert position.closed_at is not None
        assert position.active_close_request_id is None
        assert close_request.status == CloseRequestStatus.COMPLETED
        assert close_request.filled_qty == 10
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 10


class TestPartialFillAndRetry:
    """Test partial fill → retry flow."""

    @pytest.mark.asyncio
    async def test_partial_fill_triggers_retryable_state(self, db_session):
        """Partial fill + cancel should result in RETRYABLE state."""
        # Setup position and close request
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-2",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        # Order submitted
        order = OrderRecord(
            order_id="ord-002",
            broker_order_id="BROKER-002",
            account_id="ACC001",
            strategy_id="close",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
        )
        db_session.add(order)
        await db_session.commit()

        # Partial fill then cancel
        handler = OrderUpdateHandler(db_session)

        # First partial fill
        await handler.on_order_update(
            broker_order_id="BROKER-002",
            broker_status="PARTIAL",
            filled_qty=5,
            broker_update_seq=1,
        )

        # Then cancelled
        await handler.on_order_update(
            broker_order_id="BROKER-002",
            broker_status="CANCELLED",
            filled_qty=5,
            broker_update_seq=2,
        )

        await db_session.refresh(position)
        await db_session.refresh(close_request)

        # Should be RETRYABLE
        assert position.status == PositionStatus.CLOSE_RETRYABLE
        assert close_request.status == CloseRequestStatus.RETRYABLE
        assert close_request.filled_qty == 5

    @pytest.mark.asyncio
    async def test_retry_creates_new_outbox_event(self, db_session):
        """Reconciler should create retry outbox event for partial fills."""
        # Setup retryable position
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSE_RETRYABLE,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-3",
            status=CloseRequestStatus.RETRYABLE,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=5,  # 5 filled, 5 remaining
            retry_count=0,
            max_retries=3,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id
        await db_session.commit()

        # Run reconciler retry
        broker_api = AsyncMock()
        reconciler = Reconciler(db_session, broker_api)
        await reconciler.retry_partial_fills()

        # Verify outbox event created for remaining qty
        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == "SUBMIT_CLOSE_ORDER")
        )
        outbox = result.scalar_one()

        assert outbox.payload["qty"] == 5  # Remaining qty
        assert outbox.payload["is_retry"] is True
        assert outbox.status == OutboxEventStatus.PENDING

        await db_session.refresh(close_request)
        await db_session.refresh(position)

        assert close_request.status == CloseRequestStatus.PENDING
        assert close_request.retry_count == 1
        assert position.status == PositionStatus.CLOSING


class TestBrokerRejection:
    """Test broker rejection → rollback flow."""

    @pytest.mark.asyncio
    async def test_immediate_rejection_marks_close_failed(
        self, db_session, mock_order_manager, mock_market_data
    ):
        """Immediate broker rejection should mark position as CLOSE_FAILED."""
        # Setup position and close request
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-4",
            status=CloseRequestStatus.PENDING,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        outbox_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={
                "close_request_id": str(close_request.id),
                "position_id": position.id,
                "symbol": "AAPL240119C00150000",
                "side": "sell",
                "qty": 10,
                "asset_type": "option",
            },
            status=OutboxEventStatus.PENDING,
        )
        db_session.add(outbox_event)
        await db_session.commit()

        # Mock rejection from broker
        mock_order = MagicMock()
        mock_order.status = "REJECTED"
        mock_order_manager.submit_order.return_value = mock_order

        outbox_worker = OutboxWorker(db_session, mock_order_manager, mock_market_data)
        await outbox_worker.process_event(outbox_event)

        await db_session.refresh(position)
        await db_session.refresh(close_request)

        # Should be CLOSE_FAILED
        assert position.status == PositionStatus.CLOSE_FAILED
        assert position.active_close_request_id is None
        assert close_request.status == CloseRequestStatus.FAILED

    @pytest.mark.asyncio
    async def test_zero_fill_cancel_rollbacks_to_open(self, db_session):
        """Zero fill + cancel should rollback position to OPEN."""
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-5",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        order = OrderRecord(
            order_id="ord-003",
            broker_order_id="BROKER-003",
            account_id="ACC001",
            strategy_id="close",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
        )
        db_session.add(order)
        await db_session.commit()

        # Order cancelled with zero fill
        handler = OrderUpdateHandler(db_session)
        await handler.on_order_update(
            broker_order_id="BROKER-003",
            broker_status="CANCELLED",
            filled_qty=0,
            broker_update_seq=1,
        )

        await db_session.refresh(position)
        await db_session.refresh(close_request)

        # Should rollback to OPEN
        assert position.status == PositionStatus.OPEN
        assert position.active_close_request_id is None
        assert close_request.status == CloseRequestStatus.FAILED


class TestMonotonicStatusProgression:
    """Test monotonic status progression (no regression)."""

    @pytest.mark.asyncio
    async def test_filled_cannot_regress_to_cancelled(self, db_session):
        """Once FILLED, cannot go back to CANCELLED."""
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-6",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        order = OrderRecord(
            order_id="ord-004",
            broker_order_id="BROKER-004",
            account_id="ACC001",
            strategy_id="close",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
        )
        db_session.add(order)
        await db_session.commit()

        handler = OrderUpdateHandler(db_session)

        # First fill
        await handler.on_order_update(
            broker_order_id="BROKER-004",
            broker_status="FILLED",
            filled_qty=10,
            broker_update_seq=1,
        )

        await db_session.refresh(order)
        assert order.status == OrderStatus.FILLED

        # Late cancel should be ignored
        await handler.on_order_update(
            broker_order_id="BROKER-004",
            broker_status="CANCELLED",
            filled_qty=10,
            broker_update_seq=2,
        )

        await db_session.refresh(order)
        # Should still be FILLED
        assert order.status == OrderStatus.FILLED

    @pytest.mark.asyncio
    async def test_late_filled_overrides_cancelled(self, db_session):
        """Late FILLED arrival should upgrade from CANCELLED."""
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="test-key-7",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        order = OrderRecord(
            order_id="ord-005",
            broker_order_id="BROKER-005",
            account_id="ACC001",
            strategy_id="close",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
        )
        db_session.add(order)
        await db_session.commit()

        handler = OrderUpdateHandler(db_session)

        # Cancel arrives first (out of order)
        await handler.on_order_update(
            broker_order_id="BROKER-005",
            broker_status="CANCELLED",
            filled_qty=0,
            broker_update_seq=1,
        )

        await db_session.refresh(order)
        assert order.status == OrderStatus.CANCELLED

        # Late FILLED arrives with higher fill qty
        await handler.on_order_update(
            broker_order_id="BROKER-005",
            broker_status="FILLED",
            filled_qty=10,
            broker_update_seq=2,
        )

        await db_session.refresh(order)
        await db_session.refresh(close_request)
        await db_session.refresh(position)

        # Should upgrade to FILLED
        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 10
        assert close_request.status == CloseRequestStatus.COMPLETED
        assert position.status == PositionStatus.CLOSED
