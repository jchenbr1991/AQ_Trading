from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    broker: Mapped[str] = mapped_column(String(20), default="futu")
    currency: Mapped[str] = mapped_column(String(10), default="USD")

    # Balances
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    buying_power: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    margin_used: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
