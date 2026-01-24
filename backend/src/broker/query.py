# backend/src/broker/query.py
"""Read-only interface for querying broker state."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from src.models.position import AssetType


@dataclass
class BrokerPosition:
    """Position as reported by broker."""

    symbol: str
    quantity: int
    avg_cost: Decimal
    market_value: Decimal
    asset_type: AssetType


@dataclass
class BrokerAccount:
    """Account balances as reported by broker."""

    account_id: str
    cash: Decimal
    buying_power: Decimal
    total_equity: Decimal
    margin_used: Decimal


@runtime_checkable
class BrokerQuery(Protocol):
    """Read-only interface for querying broker state."""

    async def get_positions(self, account_id: str) -> list[BrokerPosition]:
        """Get all positions from broker."""
        ...

    async def get_account(self, account_id: str) -> BrokerAccount:
        """Get account balances from broker."""
        ...
