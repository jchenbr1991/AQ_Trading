# backend/src/orders/manager.py
"""Order lifecycle management."""

import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from src.broker.base import Broker
from src.broker.errors import BrokerError
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill, Signal

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Manages order lifecycle from signal to fill.

    Responsibilities:
    - Convert signals to orders
    - Submit orders to broker
    - Track active orders
    - Handle fills with idempotency
    - Update portfolio on fills

    CRITICAL: Uses _on_fill_sync wrapper for thread-safe Futu callbacks
    """

    def __init__(
        self,
        broker: Broker,
        portfolio,  # PortfolioManager
        redis,  # Redis client
        db_session,  # AsyncSession
        account_id: str,
    ):
        self._broker = broker
        self._portfolio = portfolio
        self._redis = redis
        self._db = db_session
        self._account_id = account_id
        self._active_orders: dict[str, Order] = {}
        self._broker_id_map: dict[str, str] = {}  # broker_id -> order_id
        self._processed_fills: set[str] = set()  # For idempotency
        self._running = False
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def active_orders(self) -> dict[str, Order]:
        """Get active orders dict."""
        return self._active_orders

    async def start(self) -> None:
        """Start consuming signals from Redis queue."""
        self._loop = asyncio.get_running_loop()
        # CRITICAL: Use sync wrapper for broker callback (Futu calls from different thread)
        self._broker.subscribe_fills(self._on_fill_sync)
        self._running = True
        asyncio.create_task(self._consume_signals())

    async def stop(self) -> None:
        """Stop the order manager."""
        self._running = False

    async def _consume_signals(self) -> None:
        """Consume approved signals from Redis queue."""
        while self._running:
            try:
                result = await self._redis.brpop("approved_signals", timeout=1)
                if result:
                    _, signal_data = result
                    signal = Signal.from_json(signal_data)
                    await self.process_signal(signal)
            except Exception:
                logger.exception("Error consuming signal")

    async def process_signal(self, signal: Signal) -> Order:
        """
        Convert signal to order and submit to broker.

        CRITICAL: Persist order as PENDING before submitting to broker.
        This ensures we can recover if crash occurs after broker accepts.
        """
        order = Order.from_signal(signal, order_id=str(uuid4()))
        self._active_orders[order.order_id] = order

        # TODO: Persist PENDING order to DB before broker submit
        # await self._persist_order(order)

        try:
            broker_id = await self._broker.submit_order(order)
            order.broker_order_id = broker_id
            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.utcnow()
            self._broker_id_map[broker_id] = order.order_id
        except BrokerError as e:
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)
            order.updated_at = datetime.utcnow()

        return order

    def get_order(self, order_id: str) -> Order | None:
        """Get order by internal ID."""
        return self._active_orders.get(order_id)

    def get_orders_by_strategy(self, strategy_id: str) -> list[Order]:
        """Get all active orders for a strategy."""
        return [order for order in self._active_orders.values() if order.strategy_id == strategy_id]

    def _on_fill_sync(self, fill: OrderFill) -> None:
        """
        Sync callback for broker fills.

        IMPORTANT: Futu SDK calls this from a different thread.
        We use run_coroutine_threadsafe to schedule on the event loop.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.handle_fill(fill), self._loop)

    async def handle_fill(self, fill: OrderFill) -> None:
        """
        Handle fill notification from broker (idempotent).

        CRITICAL: Check fill_id to prevent duplicate processing.
        """
        # IDEMPOTENCY CHECK - Must be first!
        if fill.fill_id in self._processed_fills:
            return  # Duplicate, ignore
        self._processed_fills.add(fill.fill_id)

        order_id = self._broker_id_map.get(fill.order_id)
        if not order_id:
            return  # Unknown order

        order = self._active_orders.get(order_id)
        if not order:
            return

        # Update order state
        prev_qty = order.filled_qty
        prev_avg = order.avg_fill_price or Decimal("0")

        order.filled_qty += fill.quantity
        order.avg_fill_price = self._calc_avg_price(prev_qty, prev_avg, fill)
        order.updated_at = datetime.utcnow()

        if order.filled_qty >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIAL_FILL

        # Update portfolio
        await self._portfolio.record_fill(
            account_id=self._account_id,
            symbol=order.symbol,
            side=order.side,
            quantity=fill.quantity,
            price=fill.price,
            strategy_id=order.strategy_id,
        )

        # Publish fill event
        await self._redis.publish("fills", fill.to_json())

        # Cleanup if fully filled
        if order.status == OrderStatus.FILLED:
            await self._persist_order(order)
            del self._active_orders[order.order_id]
            del self._broker_id_map[order.broker_order_id]

    def _calc_avg_price(self, prev_qty: int, prev_avg: Decimal, fill: OrderFill) -> Decimal:
        """Calculate volume-weighted average fill price."""
        total_qty = prev_qty + fill.quantity
        total_value = (prev_avg * prev_qty) + (fill.price * fill.quantity)
        return total_value / total_qty

    async def _persist_order(self, order: Order) -> None:
        """Save completed order to database."""
        # TODO: Implement DB persistence
        pass

    def _on_fill(self, fill: OrderFill) -> None:
        """Legacy callback - use _on_fill_sync instead."""
        asyncio.create_task(self.handle_fill(fill))
