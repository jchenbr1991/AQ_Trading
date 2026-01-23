from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from src.models.transaction import TransactionAction


class TransactionBase(BaseModel):
    symbol: str
    action: TransactionAction
    quantity: int
    price: Decimal


class TransactionCreate(TransactionBase):
    account_id: str
    commission: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    strategy_id: str | None = None
    order_id: str | None = None
    broker_order_id: str | None = None
    executed_at: datetime | None = None


class TransactionRead(TransactionBase):
    id: int
    account_id: str
    commission: Decimal
    realized_pnl: Decimal
    strategy_id: str | None
    order_id: str | None
    executed_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
