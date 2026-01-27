"""Tests for Reconciler jobs."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType
from src.models.outbox import OutboxEvent, OutboxEventStatus
from src.models.position import AssetType, Position, PositionStatus


@pytest_asyncio.fixture
async def broker_api():
    """Mock broker API."""
    return AsyncMock()


@pytest_asyncio.fixture
async def reconciler(db_session, broker_api):
    """Create reconciler with test session."""
    from src.workers.reconciler import Reconciler

    return Reconciler(db_session, broker_api)


class TestZombieDetection:
    """Tests for Case 1: Zombie request detection."""

    @pytest.mark.asyncio
    async def test_detects_zombie_request_without_outbox(
        self, db_session, reconciler
    ):
        """Zombie PENDING request with no outbox should be marked FAILED."""
        # Create position and old close request (3 min old)
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
            idempotency_key="key1",
            status=CloseRequestStatus.PENDING,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=3),
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id
        await db_session.commit()

        # Run zombie detection
        await reconciler.detect_zombies()
        await db_session.refresh(close_request)
        await db_session.refresh(position)

        # Should be marked as FAILED
        assert close_request.status == CloseRequestStatus.FAILED
        assert position.status == PositionStatus.OPEN
        assert position.active_close_request_id is None

    @pytest.mark.asyncio
    async def test_skips_zombie_with_pending_outbox(self, db_session, reconciler):
        """Zombie request with pending outbox should not be touched."""
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
        )
        db_session.add(position)
        await db_session.flush()

        close_request_id = uuid4()
        close_request = CloseRequest(
            id=close_request_id,
            position_id=position.id,
            idempotency_key="key1",
            status=CloseRequestStatus.PENDING,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
            created_at=datetime.now(timezone.utc) - timedelta(minutes=3),
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        # Create pending outbox event
        outbox = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={"close_request_id": str(close_request_id)},
            status=OutboxEventStatus.PENDING,
        )
        db_session.add(outbox)
        await db_session.commit()

        # Run zombie detection
        await reconciler.detect_zombies()
        await db_session.refresh(close_request)
        await db_session.refresh(position)

        # Should still be PENDING (outbox worker will handle)
        assert close_request.status == CloseRequestStatus.PENDING
        assert position.status == PositionStatus.CLOSING

    @pytest.mark.asyncio
    async def test_ignores_recent_pending_requests(self, db_session, reconciler):
        """Recent PENDING requests (<2 min) should not be touched."""
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
            idempotency_key="key1",
            status=CloseRequestStatus.PENDING,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
            created_at=datetime.now(timezone.utc) - timedelta(seconds=30),  # Only 30s old
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id
        await db_session.commit()

        await reconciler.detect_zombies()
        await db_session.refresh(close_request)

        # Should still be PENDING
        assert close_request.status == CloseRequestStatus.PENDING


class TestStuckOrderRecovery:
    """Tests for Case 2: Stuck SUBMITTED order recovery."""

    @pytest.mark.asyncio
    async def test_queries_broker_for_stuck_orders(self, db_session, reconciler, broker_api):
        """Stuck SUBMITTED orders should query broker for status."""
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
            idempotency_key="key1",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
            submitted_at=datetime.now(timezone.utc) - timedelta(minutes=15),  # 15 min old
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        order = OrderRecord(
            order_id="ord-001",
            broker_order_id="BROKER-001",
            account_id="ACC001",
            strategy_id="test",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
        )
        db_session.add(order)
        await db_session.commit()

        # Mock broker returns FILLED
        broker_api.query_order.return_value = MagicMock(
            status="FILLED",
            filled_qty=10,
            update_seq=100,
        )

        await reconciler.recover_stuck_orders()

        # Should have queried broker
        broker_api.query_order.assert_called_once_with("BROKER-001")

    @pytest.mark.asyncio
    async def test_handles_order_not_found_at_broker(
        self, db_session, reconciler, broker_api
    ):
        """Order not found at broker should increment not_found_count."""
        from src.workers.reconciler import OrderNotFoundError

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
            idempotency_key="key1",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
            submitted_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        order = OrderRecord(
            order_id="ord-001",
            broker_order_id="BROKER-001",
            account_id="ACC001",
            strategy_id="test",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
            reconcile_not_found_count=0,
        )
        db_session.add(order)
        await db_session.commit()

        # Mock broker returns not found
        broker_api.query_order.side_effect = OrderNotFoundError("Order not found")

        await reconciler.recover_stuck_orders()
        await db_session.refresh(order)

        # Should increment not_found_count
        assert order.reconcile_not_found_count == 1

    @pytest.mark.asyncio
    async def test_marks_close_failed_after_3_not_found(
        self, db_session, reconciler, broker_api
    ):
        """After 3 not found attempts, should mark as CLOSE_FAILED."""
        from src.workers.reconciler import OrderNotFoundError

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
            idempotency_key="key1",
            status=CloseRequestStatus.SUBMITTED,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=0,
            submitted_at=datetime.now(timezone.utc) - timedelta(minutes=15),
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id

        order = OrderRecord(
            order_id="ord-001",
            broker_order_id="BROKER-001",
            account_id="ACC001",
            strategy_id="test",
            symbol="AAPL240119C00150000",
            side=OrderSide.SELL,
            quantity=10,
            order_type=OrderType.LIMIT,
            status=OrderStatus.SUBMITTED,
            close_request_id=close_request.id,
            reconcile_not_found_count=2,  # Already 2 failed attempts
        )
        db_session.add(order)
        await db_session.commit()

        broker_api.query_order.side_effect = OrderNotFoundError("Order not found")

        await reconciler.recover_stuck_orders()
        await db_session.refresh(order)
        await db_session.refresh(close_request)
        await db_session.refresh(position)

        # Should be CLOSE_FAILED
        assert order.reconcile_not_found_count == 3
        assert close_request.status == CloseRequestStatus.FAILED
        assert position.status == PositionStatus.CLOSE_FAILED


class TestAutoRetry:
    """Tests for Case 3: Auto-retry CLOSE_RETRYABLE."""

    @pytest.mark.asyncio
    async def test_creates_retry_outbox_event(self, db_session, reconciler):
        """RETRYABLE request should create new outbox event for remaining qty."""
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
            idempotency_key="key1",
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

        await reconciler.retry_partial_fills()
        await db_session.refresh(close_request)
        await db_session.refresh(position)

        # Should have created outbox event
        from sqlalchemy import select

        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == "SUBMIT_CLOSE_ORDER")
        )
        outbox = result.scalar_one()

        assert outbox.payload["close_request_id"] == str(close_request.id)
        assert outbox.payload["qty"] == 5  # Remaining qty
        assert outbox.payload["is_retry"] is True

        # CloseRequest should be back to PENDING
        assert close_request.status == CloseRequestStatus.PENDING
        assert close_request.retry_count == 1
        assert position.status == PositionStatus.CLOSING

    @pytest.mark.asyncio
    async def test_stops_retry_after_max_retries(self, db_session, reconciler):
        """Should not retry after max_retries reached."""
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
            idempotency_key="key1",
            status=CloseRequestStatus.RETRYABLE,
            symbol="AAPL240119C00150000",
            side="sell",
            asset_type="option",
            target_qty=10,
            filled_qty=5,
            retry_count=3,  # Already at max
            max_retries=3,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id
        await db_session.commit()

        await reconciler.retry_partial_fills()
        await db_session.refresh(close_request)

        # Should still be RETRYABLE (no new outbox event)
        assert close_request.status == CloseRequestStatus.RETRYABLE
        assert close_request.retry_count == 3  # Unchanged

    @pytest.mark.asyncio
    async def test_uses_stored_side_from_close_request(self, db_session, reconciler):
        """Retry should use side from CloseRequest, not recalculate from position."""
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=-5,  # Position quantity may have changed
            status=PositionStatus.CLOSE_RETRYABLE,
        )
        db_session.add(position)
        await db_session.flush()

        close_request = CloseRequest(
            id=uuid4(),
            position_id=position.id,
            idempotency_key="key1",
            status=CloseRequestStatus.RETRYABLE,
            symbol="AAPL240119C00150000",
            side="sell",  # Original side was sell
            asset_type="option",
            target_qty=10,
            filled_qty=5,
            retry_count=0,
            max_retries=3,
        )
        db_session.add(close_request)
        position.active_close_request_id = close_request.id
        await db_session.commit()

        await reconciler.retry_partial_fills()

        from sqlalchemy import select

        result = await db_session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == "SUBMIT_CLOSE_ORDER")
        )
        outbox = result.scalar_one()

        # Should use stored side "sell", not recalculate from negative position
        assert outbox.payload["side"] == "sell"


class TestInvariantCheck:
    """Tests for status invariant checking."""

    @pytest.mark.asyncio
    async def test_fixes_closing_without_active_request(self, db_session, reconciler):
        """Position CLOSING but no active_close_request_id should be fixed."""
        position = Position(
            account_id="ACC001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            quantity=10,
            status=PositionStatus.CLOSING,
            active_close_request_id=None,  # Invariant violation
        )
        db_session.add(position)
        await db_session.commit()

        await reconciler.check_invariants()
        await db_session.refresh(position)

        # Should be marked CLOSE_FAILED
        assert position.status == PositionStatus.CLOSE_FAILED
