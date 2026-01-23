from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, computed_field

from src.models.position import AssetType, PutCall


class PositionBase(BaseModel):
    symbol: str
    asset_type: AssetType = AssetType.STOCK
    strategy_id: str | None = None


class PositionCreate(PositionBase):
    account_id: str
    quantity: int
    avg_cost: Decimal
    strike: Decimal | None = None
    expiry: date | None = None
    put_call: PutCall | None = None


class PositionUpdate(BaseModel):
    quantity: int | None = None
    avg_cost: Decimal | None = None
    current_price: Decimal | None = None


class PositionRead(PositionBase):
    id: int
    account_id: str
    quantity: int
    avg_cost: Decimal
    current_price: Decimal
    strike: Decimal | None
    expiry: date | None
    put_call: PutCall | None
    opened_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def market_value(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return self.quantity * self.current_price * multiplier

    @computed_field
    @property
    def unrealized_pnl(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return (self.current_price - self.avg_cost) * self.quantity * multiplier

    class Config:
        from_attributes = True
