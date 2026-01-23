# backend/src/orders/models.py
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
import json

from src.strategies.signals import Signal


class OrderStatus(Enum):
    """Order lifecycle status."""
    # Active states
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL_FILL = "partial"
    CANCEL_REQUESTED = "cancel_req"

    # Terminal states
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    # Phase 2 placeholders
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass
class Order:
    """
    Represents a trading order.

    Created from a Signal, submitted via Broker, and tracked until terminal state.
    """
    order_id: str
    broker_order_id: str | None
    strategy_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"]
    limit_price: Decimal | None
    status: OrderStatus
    filled_qty: int = 0
    avg_fill_price: Decimal | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: str | None = None

    @classmethod
    def from_signal(cls, signal: Signal, order_id: str) -> "Order":
        """Create an Order from a Signal."""
        return cls(
            order_id=order_id,
            broker_order_id=None,
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side=signal.action,
            quantity=signal.quantity,
            order_type=signal.order_type,
            limit_price=signal.limit_price,
            status=OrderStatus.PENDING
        )

    def to_json(self) -> str:
        """Serialize order to JSON string."""
        return json.dumps({
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": str(self.limit_price) if self.limit_price else None,
            "status": self.status.value,
            "filled_qty": self.filled_qty,
            "avg_fill_price": str(self.avg_fill_price) if self.avg_fill_price else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "error_message": self.error_message
        })

    @classmethod
    def from_json(cls, data: str) -> "Order":
        """Deserialize order from JSON string."""
        d = json.loads(data)
        return cls(
            order_id=d["order_id"],
            broker_order_id=d["broker_order_id"],
            strategy_id=d["strategy_id"],
            symbol=d["symbol"],
            side=d["side"],
            quantity=d["quantity"],
            order_type=d["order_type"],
            limit_price=Decimal(d["limit_price"]) if d["limit_price"] else None,
            status=OrderStatus(d["status"]),
            filled_qty=d["filled_qty"],
            avg_fill_price=Decimal(d["avg_fill_price"]) if d["avg_fill_price"] else None,
            created_at=datetime.fromisoformat(d["created_at"]) if d["created_at"] else None,
            updated_at=datetime.fromisoformat(d["updated_at"]) if d["updated_at"] else None,
            error_message=d["error_message"]
        )
