"""Backtest data models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class Bar:
    """OHLCV bar representing a closed interval (prev_close, timestamp].

    Signal generated at bar close, fill at next bar open.

    The timestamp marks the end of the bar interval. For a daily bar with
    timestamp 2024-01-15 16:00:00 UTC, the bar contains price data for
    trading that occurred after the previous close up to and including
    16:00:00 UTC on January 15th.

    Attributes:
        symbol: Ticker symbol (e.g., "AAPL").
        timestamp: Bar close time. Must be timezone-aware (tzinfo is not None)
            to avoid ambiguity across market sessions and data sources.
        open: Opening price of the interval.
        high: Highest price during the interval.
        low: Lowest price during the interval.
        close: Closing price of the interval.
        volume: Total shares traded during the interval.
        interval: Bar duration. Currently only "1d" (daily) is supported.
    """

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    interval: Literal["1d"] = "1d"
