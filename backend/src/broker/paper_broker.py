# backend/src/broker/paper_broker.py
"""Simulated broker for paper trading."""
import asyncio
import random
from datetime import datetime
from decimal import Decimal
from typing import Callable

from src.broker.errors import OrderCancelError
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


class PaperBroker:
    """
    Simulates order execution for paper trading.

    Features:
    - Configurable fill delay
    - Simulated partial fills (for realism)
    - Slippage variance for market orders
    - Unique fill_id for each fill (critical for idempotency)
    """

    def __init__(
        self,
        fill_delay: float = 0.1,
        default_price: Decimal = Decimal("100"),
        slippage_bps: int = 5,  # Basis points of slippage
        partial_fill_probability: float = 0.0  # 0 = always full fill
    ):
        self._fill_delay = fill_delay
        self._default_price = default_price
        self._slippage_bps = slippage_bps
        self._partial_fill_probability = partial_fill_probability
        self._fill_callback: Callable[[OrderFill], None] | None = None
        self._order_counter = 0
        self._fill_counter = 0
        self._orders: dict[str, Order] = {}
        self._order_statuses: dict[str, OrderStatus] = {}
        self._filled_qty: dict[str, int] = {}
        self._cancelled: set[str] = set()

    async def submit_order(self, order: Order) -> str:
        """Submit order and schedule simulated fill."""
        self._order_counter += 1
        broker_id = f"PAPER-{self._order_counter:06d}"

        self._orders[broker_id] = order
        self._order_statuses[broker_id] = OrderStatus.SUBMITTED
        self._filled_qty[broker_id] = 0

        # Schedule fill simulation
        asyncio.create_task(self._simulate_fill(order, broker_id))

        return broker_id

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an order if not yet filled."""
        if broker_order_id not in self._orders:
            raise OrderCancelError("Order not found", broker_order_id)

        if self._order_statuses.get(broker_order_id) == OrderStatus.FILLED:
            raise OrderCancelError("Order already filled", broker_order_id)

        self._cancelled.add(broker_order_id)
        self._order_statuses[broker_order_id] = OrderStatus.CANCELLED
        return True

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Get current order status."""
        return self._order_statuses.get(broker_order_id, OrderStatus.PENDING)

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        """Register fill callback."""
        self._fill_callback = callback

    async def _simulate_fill(self, order: Order, broker_id: str) -> None:
        """Simulate order fill after delay, potentially with partial fills."""
        await asyncio.sleep(self._fill_delay)

        # Check if cancelled
        if broker_id in self._cancelled:
            return

        remaining_qty = order.quantity - self._filled_qty.get(broker_id, 0)

        while remaining_qty > 0:
            # Check cancellation each iteration
            if broker_id in self._cancelled:
                return

            # Determine fill quantity
            if (self._partial_fill_probability > 0 and
                random.random() < self._partial_fill_probability and
                remaining_qty > 1):
                # Partial fill: random portion
                fill_qty = random.randint(1, remaining_qty - 1)
            else:
                # Full fill
                fill_qty = remaining_qty

            # Determine fill price
            fill_price = self._calculate_fill_price(order)

            # Generate unique fill ID
            self._fill_counter += 1
            fill_id = f"FILL-{self._fill_counter:08d}"

            # Create fill
            fill = OrderFill(
                fill_id=fill_id,
                order_id=broker_id,
                symbol=order.symbol,
                side=order.side,
                quantity=fill_qty,
                price=fill_price,
                timestamp=datetime.utcnow()
            )

            # Update tracking
            self._filled_qty[broker_id] = self._filled_qty.get(broker_id, 0) + fill_qty
            remaining_qty -= fill_qty

            # Update status
            if remaining_qty > 0:
                self._order_statuses[broker_id] = OrderStatus.PARTIAL_FILL
            else:
                self._order_statuses[broker_id] = OrderStatus.FILLED

            # Notify callback
            if self._fill_callback:
                self._fill_callback(fill)

            # Small delay between partial fills
            if remaining_qty > 0:
                await asyncio.sleep(self._fill_delay / 2)

    def _calculate_fill_price(self, order: Order) -> Decimal:
        """Calculate fill price with optional slippage."""
        if order.order_type == "limit" and order.limit_price:
            # Limit orders fill at limit price or better
            base_price = order.limit_price
            # Simulate improvement: buy at lower, sell at higher
            if order.side == "buy":
                improvement = Decimal(random.uniform(0, 0.001))
                return base_price * (Decimal("1") - improvement)
            else:
                improvement = Decimal(random.uniform(0, 0.001))
                return base_price * (Decimal("1") + improvement)
        else:
            # Market orders have slippage
            base_price = self._default_price
            slippage_pct = Decimal(random.uniform(-self._slippage_bps, self._slippage_bps)) / Decimal("10000")

            # Adverse slippage: buy high, sell low
            if order.side == "buy":
                return base_price * (Decimal("1") + abs(slippage_pct))
            else:
                return base_price * (Decimal("1") - abs(slippage_pct))
