"""Order update handler with idempotent, monotonic status progression."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.order import OrderRecord, OrderStatus
from src.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)

# Terminal states - once reached, special handling required
TERMINAL_STATES = frozenset({
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
})

# Status progression order (monotonic)
# FILLED is highest - once filled, nothing can override it
STATUS_ORDER = {
    "pending": 0,
    "submitted": 1,
    "partial": 2,
    "cancel_req": 2,
    "cancelled": 3,
    "rejected": 3,
    "expired": 3,
    "filled": 4,  # Highest
}

# Map broker status to our OrderStatus enum
BROKER_STATUS_MAP = {
    "NEW": OrderStatus.PENDING,
    "SUBMITTED": OrderStatus.SUBMITTED,
    "PARTIAL": OrderStatus.PARTIAL_FILL,
    "PARTIAL_FILL": OrderStatus.PARTIAL_FILL,
    "FILLED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
}


class OrderUpdateHandler:
    """Handler for broker order updates with idempotent, monotonic processing."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def on_order_update(
        self,
        broker_order_id: str,
        broker_status: str,
        filled_qty: int,
        broker_update_seq: int | None = None,
    ) -> None:
        """Handle broker order update with idempotency and monotonic progression."""
        # Get and lock order
        result = await self.session.execute(
            select(OrderRecord)
            .where(OrderRecord.broker_order_id == broker_order_id)
            .with_for_update()
        )
        order = result.scalar_one_or_none()

        if not order:
            logger.warning(f"Unknown order update: {broker_order_id}")
            return

        # Map broker status to our enum
        new_status = BROKER_STATUS_MAP.get(broker_status.upper())
        if not new_status:
            logger.warning(f"Unknown broker status: {broker_status}")
            return

        # Idempotency: skip if already processed (when sequence available)
        if broker_update_seq is not None and order.broker_update_seq is not None:
            if broker_update_seq <= order.broker_update_seq:
                logger.debug(f"Skipping stale update for {broker_order_id}")
                return

        # Terminal state handling
        if order.status in TERMINAL_STATES:
            if order.status == OrderStatus.FILLED:
                logger.debug(f"Order {broker_order_id} already FILLED, ignoring")
                return

            # Late FILLED arrival - upgrade from CANCELLED/REJECTED/EXPIRED
            if new_status == OrderStatus.FILLED and filled_qty > order.filled_qty:
                logger.info(f"Late FILLED for {broker_order_id}: upgrading from {order.status}")
                order.status = OrderStatus.FILLED
                order.filled_qty = filled_qty
                order.broker_update_seq = broker_update_seq
                order.last_broker_update_at = datetime.now(timezone.utc)
                if order.close_request_id:
                    await self._update_close_request(order)
                await self.session.commit()
                return

            # Other terminal->terminal: just update filled_qty if higher
            order.filled_qty = max(order.filled_qty, filled_qty)
            order.broker_update_seq = broker_update_seq
            await self.session.commit()
            return

        # Monotonic: only allow forward status progression
        current_priority = STATUS_ORDER.get(order.status.value, 0)
        new_priority = STATUS_ORDER.get(new_status.value, 0)

        if new_priority < current_priority:
            logger.warning(f"Ignoring backward status: {order.status} -> {new_status}")
            order.filled_qty = max(order.filled_qty, filled_qty)
            order.broker_update_seq = broker_update_seq
            await self.session.commit()
            return

        # Update order
        order.status = new_status
        order.filled_qty = max(order.filled_qty, filled_qty)
        order.broker_update_seq = broker_update_seq
        order.last_broker_update_at = datetime.now(timezone.utc)

        # Update close request if applicable
        if order.close_request_id:
            await self._update_close_request(order)

        await self.session.commit()

    async def _update_close_request(self, order: OrderRecord) -> None:
        """Update close request and position based on order state."""
        # Get close request
        result = await self.session.execute(
            select(CloseRequest)
            .where(CloseRequest.id == order.close_request_id)
            .with_for_update()
        )
        close_request = result.scalar_one_or_none()
        if not close_request:
            return

        # Get position
        pos_result = await self.session.execute(
            select(Position).where(Position.id == close_request.position_id)
        )
        position = pos_result.scalar_one_or_none()
        if not position:
            return

        # Aggregate filled_qty from all orders for this close request
        total_result = await self.session.execute(
            select(func.coalesce(func.sum(OrderRecord.filled_qty), 0))
            .where(OrderRecord.close_request_id == close_request.id)
        )
        total_filled = total_result.scalar()
        close_request.filled_qty = total_filled

        # Check if all orders are terminal
        orders_result = await self.session.execute(
            select(OrderRecord).where(OrderRecord.close_request_id == close_request.id)
        )
        orders = orders_result.scalars().all()

        all_terminal = all(o.status in TERMINAL_STATES for o in orders)
        all_filled = all(o.status == OrderStatus.FILLED for o in orders)

        if not all_terminal:
            return  # Still waiting

        if all_filled and close_request.remaining_qty == 0:
            # Fully closed
            close_request.status = CloseRequestStatus.COMPLETED
            close_request.completed_at = datetime.now(timezone.utc)
            position.status = PositionStatus.CLOSED
            position.closed_at = datetime.now(timezone.utc)
            position.active_close_request_id = None

        elif close_request.filled_qty == 0:
            # Zero fill - rollback to OPEN
            close_request.status = CloseRequestStatus.FAILED
            close_request.completed_at = datetime.now(timezone.utc)
            position.status = PositionStatus.OPEN
            position.active_close_request_id = None

        else:
            # Partial fill - need retry
            close_request.status = CloseRequestStatus.RETRYABLE
            position.status = PositionStatus.CLOSE_RETRYABLE
