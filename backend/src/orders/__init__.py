"""Order management module."""

from src.orders.models import Order, OrderStatus

__all__ = [
    "Order",
    "OrderStatus",
]


def get_order_manager_class():
    """Lazy import to avoid circular dependency with broker module."""
    from src.orders.manager import OrderManager

    return OrderManager
