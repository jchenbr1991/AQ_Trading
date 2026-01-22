from datetime import datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy import String, Numeric, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class TransactionAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    INTEREST = "interest"
    TRANSFER = "transfer"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(50), ForeignKey("accounts.account_id"), index=True)

    # Transaction details
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    action: Mapped[TransactionAction] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # P&L
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Strategy tagging
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Order reference
    order_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.price
