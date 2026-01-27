# backend/src/models/order.py
import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class OrderStatus(str, Enum):
    """Order lifecycle status (DB version)."""

    # Active states
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL_FILL = "partial"
    CANCEL_REQUESTED = "cancel_req"

    # Terminal states
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class OrderRecord(Base):
    """Persistent order record in database.

    This is the SQLAlchemy model for persisted orders.
    The in-memory Order dataclass (orders/models.py) is used during runtime.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    account_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("accounts.account_id"), index=True
    )
    strategy_id: Mapped[str] = mapped_column(String(50), index=True)
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    side: Mapped[OrderSide] = mapped_column(String(10))
    quantity: Mapped[int] = mapped_column(Integer)
    order_type: Mapped[OrderType] = mapped_column(String(20))
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(String(20), index=True)
    filled_qty: Mapped[int] = mapped_column(Integer, default=0)
    avg_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Close request tracking (nullable - only set for close orders)
    close_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )

    # Broker update sequence for monotonic updates (nullable if broker doesn't provide)
    broker_update_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_broker_update_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reconciler retry tracking
    reconcile_not_found_count: Mapped[int] = mapped_column(Integer, default=0)

    def __init__(self, **kwargs):
        """Initialize OrderRecord with defaults for optional fields."""
        # Apply defaults for fields not provided
        kwargs.setdefault("filled_qty", 0)
        kwargs.setdefault("reconcile_not_found_count", 0)
        super().__init__(**kwargs)

    @property
    def is_terminal(self) -> bool:
        """Check if order is in a terminal state."""
        return self.status in (
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.EXPIRED,
        )

    @property
    def is_active(self) -> bool:
        """Check if order is still active."""
        return not self.is_terminal
