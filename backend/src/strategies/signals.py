# backend/src/strategies/signals.py
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass
class Signal:
    """
    A trading signal emitted by a strategy.

    Signals express intent (buy/sell), not orders. Risk Manager
    validates and Order Manager executes.
    """
    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
