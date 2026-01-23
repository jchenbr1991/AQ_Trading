from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class AccountBase(BaseModel):
    account_id: str
    broker: str = "futu"
    currency: str = "USD"


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    cash: Decimal | None = None
    buying_power: Decimal | None = None
    margin_used: Decimal | None = None
    total_equity: Decimal | None = None


class AccountRead(AccountBase):
    id: int
    cash: Decimal
    buying_power: Decimal
    margin_used: Decimal
    total_equity: Decimal
    created_at: datetime
    updated_at: datetime
    synced_at: datetime | None

    class Config:
        from_attributes = True
