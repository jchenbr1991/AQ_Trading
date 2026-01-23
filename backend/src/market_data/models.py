# backend/src/market_data/models.py
"""Market data models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategies.base import MarketData


@dataclass
class QuoteSnapshot:
    """
    Cached quote state with system metadata.

    Distinction from MarketData:
    - MarketData: Event flowing through queue
    - QuoteSnapshot: Cached state with staleness tracking
    """

    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime  # Event-time (from source)
    cached_at: datetime  # System-time (when cached, for debugging)

    def is_stale(self, threshold_ms: int) -> bool:
        """
        Check staleness using event-time, NOT cached_at.

        This ensures correct behavior with delayed/out-of-order data.
        """
        age_ms = (datetime.utcnow() - self.timestamp).total_seconds() * 1000
        return age_ms > threshold_ms

    @classmethod
    def from_market_data(cls, data: "MarketData") -> "QuoteSnapshot":
        """Create QuoteSnapshot from MarketData event."""
        return cls(
            symbol=data.symbol,
            price=data.price,
            bid=data.bid,
            ask=data.ask,
            volume=data.volume,
            timestamp=data.timestamp,
            cached_at=datetime.utcnow(),
        )
