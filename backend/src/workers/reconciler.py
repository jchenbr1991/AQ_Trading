"""Reconciler jobs for close position recovery and consistency."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.order import OrderRecord
from src.models.outbox import OutboxEvent, OutboxEventStatus
from src.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)


class OrderNotFoundError(Exception):
    """Raised when order not found at broker."""

    pass


class BrokerAPI(Protocol):
    """Protocol for broker API interactions."""

    async def query_order(self, broker_order_id: str) -> object: ...


class Reconciler:
    """Reconciler for close position recovery and consistency.

    Runs on different schedules:
    - detect_zombies: Every 1 minute (fast detection of crashed requests)
    - recover_stuck_orders: Every 5 minutes (respect broker rate limits)
    - retry_partial_fills: Every 2 minutes (timely retry of partial fills)
    """

    ZOMBIE_THRESHOLD_MINUTES = 2
    STUCK_THRESHOLD_MINUTES = 10
    MAX_NOT_FOUND_RETRIES = 3

    def __init__(self, session: AsyncSession, broker_api: BrokerAPI):
        self.session = session
        self.broker_api = broker_api

    async def detect_zombies(self) -> None:
        """Detect and fix zombie requests (PENDING for too long without outbox).

        Case 1: Close request stuck in PENDING for >2 minutes without a
        pending outbox event. This can happen if system crashes after
        creating CloseRequest but before writing outbox event.
        """
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=self.ZOMBIE_THRESHOLD_MINUTES)

        # Find old PENDING close requests
        result = await self.session.execute(
            select(CloseRequest)
            .where(CloseRequest.status == CloseRequestStatus.PENDING)
            .where(CloseRequest.created_at < threshold)
        )
        zombie_requests = result.scalars().all()

        for request in zombie_requests:
            # Check if there's a pending outbox event for this request
            # Load pending events and filter in Python (works with SQLite and PostgreSQL)
            outbox_result = await self.session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.event_type == "SUBMIT_CLOSE_ORDER")
                .where(OutboxEvent.status == OutboxEventStatus.PENDING)
            )
            pending_events = outbox_result.scalars().all()
            outbox = next(
                (e for e in pending_events
                 if e.payload.get("close_request_id") == str(request.id)),
                None
            )

            if outbox:
                # Outbox exists - let worker handle it
                logger.debug(f"Zombie {request.id} has pending outbox, skipping")
                continue

            # No outbox event - system crashed before writing it
            logger.warning(f"Zombie close_request: {request.id}, rolling back")

            request.status = CloseRequestStatus.FAILED
            request.completed_at = now

            pos_result = await self.session.execute(
                select(Position).where(Position.id == request.position_id)
            )
            position = pos_result.scalar_one_or_none()
            if position:
                position.status = PositionStatus.OPEN
                position.active_close_request_id = None

        await self.session.commit()

    async def recover_stuck_orders(self) -> None:
        """Recover stuck SUBMITTED orders by querying broker.

        Case 2: Close request stuck in SUBMITTED for >10 minutes without
        order updates. Query broker directly to get current status.
        """
        now = datetime.now(timezone.utc)
        threshold = now - timedelta(minutes=self.STUCK_THRESHOLD_MINUTES)

        # Find old SUBMITTED close requests
        result = await self.session.execute(
            select(CloseRequest)
            .where(CloseRequest.status == CloseRequestStatus.SUBMITTED)
            .where(CloseRequest.submitted_at < threshold)
        )
        stuck_requests = result.scalars().all()

        for request in stuck_requests:
            # Get all orders for this request
            orders_result = await self.session.execute(
                select(OrderRecord).where(OrderRecord.close_request_id == request.id)
            )
            orders = orders_result.scalars().all()

            for order in orders:
                if not order.broker_order_id:
                    continue

                try:
                    broker_status = await self.broker_api.query_order(order.broker_order_id)
                    # TODO: Call order update handler with broker status
                    logger.info(
                        f"Recovered order {order.broker_order_id}: {broker_status.status}"
                    )

                except OrderNotFoundError:
                    order.reconcile_not_found_count = (
                        order.reconcile_not_found_count or 0
                    ) + 1

                    if order.reconcile_not_found_count >= self.MAX_NOT_FOUND_RETRIES:
                        logger.error(
                            f"Order {order.broker_order_id} not found after "
                            f"{self.MAX_NOT_FOUND_RETRIES} attempts"
                        )

                        request.status = CloseRequestStatus.FAILED
                        request.completed_at = now

                        pos_result = await self.session.execute(
                            select(Position).where(Position.id == request.position_id)
                        )
                        position = pos_result.scalar_one_or_none()
                        if position:
                            position.status = PositionStatus.CLOSE_FAILED

                except Exception as e:
                    logger.warning(f"Broker API error for {order.broker_order_id}: {e}")

        await self.session.commit()

    async def retry_partial_fills(self) -> None:
        """Auto-retry CLOSE_RETRYABLE requests.

        Case 3: Close request with partial fill, cancelled remainder.
        Create new outbox event for remaining quantity.
        """
        # Find retryable close requests under max retries
        result = await self.session.execute(
            select(CloseRequest)
            .where(CloseRequest.status == CloseRequestStatus.RETRYABLE)
            .where(CloseRequest.retry_count < CloseRequest.max_retries)
        )
        retryable_requests = result.scalars().all()

        for request in retryable_requests:
            remaining_qty = request.target_qty - request.filled_qty

            if remaining_qty <= 0:
                # Nothing to retry
                continue

            logger.info(
                f"Retrying close_request {request.id}: "
                f"{remaining_qty} remaining of {request.target_qty}"
            )

            # Create new outbox event for remaining qty
            # Use stored side/symbol from CloseRequest, NOT recalculate from position
            outbox_event = OutboxEvent(
                event_type="SUBMIT_CLOSE_ORDER",
                payload={
                    "close_request_id": str(request.id),
                    "position_id": request.position_id,
                    "symbol": request.symbol,
                    "side": request.side,
                    "qty": remaining_qty,
                    "asset_type": request.asset_type,
                    "is_retry": True,
                },
                status=OutboxEventStatus.PENDING,
            )
            self.session.add(outbox_event)

            # Update request status
            request.status = CloseRequestStatus.PENDING
            request.retry_count += 1

            # Update position status back to CLOSING
            pos_result = await self.session.execute(
                select(Position).where(Position.id == request.position_id)
            )
            position = pos_result.scalar_one_or_none()
            if position:
                position.status = PositionStatus.CLOSING

        await self.session.commit()

    async def check_invariants(self) -> None:
        """Check and fix status invariant violations.

        Invariants:
        - CLOSING position must have active_close_request_id
        - SUBMITTED close_request's position must be CLOSING
        """
        # Find positions CLOSING without active close request
        result = await self.session.execute(
            select(Position)
            .where(Position.status == PositionStatus.CLOSING)
            .where(Position.active_close_request_id.is_(None))
        )
        orphaned_positions = result.scalars().all()

        for position in orphaned_positions:
            logger.error(
                f"Invariant violation: Position {position.id} CLOSING "
                "but no active_close_request_id"
            )
            position.status = PositionStatus.CLOSE_FAILED

        await self.session.commit()
