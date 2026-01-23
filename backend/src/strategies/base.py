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


class Strategy(ABC):
    """
    Abstract base class for trading strategies.

    Strategies receive market data, analyze it, and emit Signals.
    They do not execute orders directly - Risk Manager validates
    and Order Manager executes.
    """
    name: str
    symbols: list[str]

    @abstractmethod
    async def on_market_data(
        self, data: "MarketData", context: "StrategyContext"
    ) -> list["Signal"]:
        """
        React to price updates.

        Args:
            data: New market data for a subscribed symbol
            context: Read-only view of portfolio and quotes

        Returns:
            List of signals (can be empty if no action needed)
        """
        pass

    async def on_fill(self, fill: "OrderFill") -> None:
        """
        Called when an order fills.

        Override to react to fill confirmations. Default does nothing.
        """
        pass

    async def on_start(self) -> None:
        """
        Called when strategy starts.

        Override for initialization logic. Default does nothing.
        """
        pass

    async def on_stop(self) -> None:
        """
        Called when strategy stops.

        Override for cleanup logic. Default does nothing.
        """
        pass
