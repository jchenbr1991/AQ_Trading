# backend/src/broker/base.py
"""Abstract broker interface for order execution."""
from typing import Protocol, Callable, runtime_checkable

from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


@runtime_checkable
class Broker(Protocol):
    """
    Abstract broker interface for order execution.

    Implementations:
    - PaperBroker: Simulated execution for paper trading
    - FutuBroker: Real execution via Futu OpenD (Phase 2)
    """

    async def submit_order(self, order: Order) -> str:
        """
        Submit order to broker.

        Args:
            order: The order to submit

        Returns:
            broker_order_id on success

        Raises:
            OrderSubmissionError on failure
        """
        ...

    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            broker_order_id: The broker's order ID

        Returns:
            True if cancelled successfully

        Raises:
            OrderCancelError on failure
        """
        ...

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Get current status of an order."""
        ...

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        """
        Register callback for fill notifications.

        IMPORTANT: The callback will be called from a different thread
        in Futu broker. Implementations must handle thread safety.
        """
        ...
