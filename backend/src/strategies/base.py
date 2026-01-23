# backend/src/strategies/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategies.context import StrategyContext
    from src.strategies.signals import Signal


@dataclass
class MarketData:
    """Real-time market data for a symbol."""
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime


@dataclass
class OrderFill:
    """Notification of an executed order."""
    order_id: str
    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    price: Decimal
    commission: Decimal
    timestamp: datetime
