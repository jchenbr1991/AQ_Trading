# backend/src/db/repositories/order_repo.py
from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, select

from src.db.repositories.base import BaseRepository
from src.models import OrderRecord, OrderSide, OrderStatus, OrderType


class OrderRepository(BaseRepository):
    """Repository for order persistence operations."""

    async def create_order(
        self,
        order_id: str,
        account_id: str,
        strategy_id: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        order_type: OrderType,
        status: OrderStatus = OrderStatus.PENDING,
        limit_price: Decimal | None = None,
        broker_order_id: str | None = None,
    ) -> OrderRecord:
        """Create a new order record.

        Args:
            order_id: Internal order UUID
            account_id: Account placing the order
            strategy_id: Strategy that generated the signal
            symbol: Trading symbol
            side: Buy or sell
            quantity: Order quantity
            order_type: Market or limit
            status: Initial status (default PENDING)
            limit_price: Limit price for limit orders
            broker_order_id: Broker's order ID if already submitted

        Returns:
            Created OrderRecord
        """
        order = OrderRecord(
            order_id=order_id,
            broker_order_id=broker_order_id,
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            status=status,
            filled_qty=0,
        )
        self.session.add(order)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def get_order(self, order_id: str) -> OrderRecord | None:
        """Get an order by its internal ID.

        Args:
            order_id: Internal order UUID

        Returns:
            OrderRecord if found, None otherwise
        """
        result = await self.session.execute(
            select(OrderRecord).where(OrderRecord.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_order_by_broker_id(self, broker_order_id: str) -> OrderRecord | None:
        """Get an order by broker's order ID.

        Args:
            broker_order_id: Broker's order ID

        Returns:
            OrderRecord if found, None otherwise
        """
        result = await self.session.execute(
            select(OrderRecord).where(OrderRecord.broker_order_id == broker_order_id)
        )
        return result.scalar_one_or_none()

    async def update_order(
        self,
        order_id: str,
        broker_order_id: str | None = None,
        status: OrderStatus | None = None,
        filled_qty: int | None = None,
        avg_fill_price: Decimal | None = None,
        error_message: str | None = None,
    ) -> OrderRecord | None:
        """Update an existing order.

        Args:
            order_id: Internal order UUID
            broker_order_id: Broker's order ID (set on submission)
            status: New status
            filled_qty: Cumulative filled quantity
            avg_fill_price: Volume-weighted average fill price
            error_message: Error/rejection message

        Returns:
            Updated OrderRecord or None if not found
        """
        order = await self.get_order(order_id)
        if not order:
            return None

        if broker_order_id is not None:
            order.broker_order_id = broker_order_id
        if status is not None:
            order.status = status
        if filled_qty is not None:
            order.filled_qty = filled_qty
        if avg_fill_price is not None:
            order.avg_fill_price = avg_fill_price
        if error_message is not None:
            order.error_message = error_message

        order.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def get_orders_by_account(
        self,
        account_id: str,
        status: OrderStatus | None = None,
        limit: int = 100,
    ) -> list[OrderRecord]:
        """Get orders for an account.

        Args:
            account_id: Account ID
            status: Filter by status (optional)
            limit: Maximum number of orders to return

        Returns:
            List of OrderRecords
        """
        conditions = [OrderRecord.account_id == account_id]
        if status is not None:
            conditions.append(OrderRecord.status == status)

        result = await self.session.execute(
            select(OrderRecord)
            .where(and_(*conditions))
            .order_by(OrderRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_orders_by_strategy(
        self,
        strategy_id: str,
        status: OrderStatus | None = None,
        limit: int = 100,
    ) -> list[OrderRecord]:
        """Get orders for a strategy.

        Args:
            strategy_id: Strategy ID
            status: Filter by status (optional)
            limit: Maximum number of orders to return

        Returns:
            List of OrderRecords
        """
        conditions = [OrderRecord.strategy_id == strategy_id]
        if status is not None:
            conditions.append(OrderRecord.status == status)

        result = await self.session.execute(
            select(OrderRecord)
            .where(and_(*conditions))
            .order_by(OrderRecord.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_active_orders(
        self,
        account_id: str | None = None,
    ) -> list[OrderRecord]:
        """Get all active (non-terminal) orders.

        Args:
            account_id: Filter by account (optional)

        Returns:
            List of active OrderRecords
        """
        active_statuses = [
            OrderStatus.PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIAL_FILL,
            OrderStatus.CANCEL_REQUESTED,
        ]

        conditions = [OrderRecord.status.in_(active_statuses)]
        if account_id is not None:
            conditions.append(OrderRecord.account_id == account_id)

        result = await self.session.execute(
            select(OrderRecord).where(and_(*conditions)).order_by(OrderRecord.created_at.asc())
        )
        return list(result.scalars().all())
