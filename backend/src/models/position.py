import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class AssetType(str, Enum):
    STOCK = "stock"
    OPTION = "option"
    FUTURE = "future"


class PutCall(str, Enum):
    PUT = "put"
    CALL = "call"


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    CLOSE_RETRYABLE = "close_retryable"
    CLOSE_FAILED = "close_failed"


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("accounts.account_id"), index=True
    )

    # Identification
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    asset_type: Mapped[AssetType] = mapped_column(String(20), default=AssetType.STOCK)

    # Strategy tagging
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Lifecycle status
    status: Mapped[PositionStatus] = mapped_column(
        String(20), default=PositionStatus.OPEN, index=True
    )

    # Position data
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Options-specific (nullable for stocks)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    put_call: Mapped[PutCall | None] = mapped_column(String(10), nullable=True)

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Close request tracking
    active_close_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def market_value(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return self.quantity * self.current_price * multiplier

    @property
    def unrealized_pnl(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return (self.current_price - self.avg_cost) * self.quantity * multiplier
