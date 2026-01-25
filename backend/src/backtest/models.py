"""Backtest data models."""

from dataclasses import dataclass, field
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


@dataclass
class Trade:
    """Execution record for a filled order in backtesting.

    Represents a trade that was executed at the next bar's open price
    after a signal was generated.

    The fill_price is computed automatically based on side:
    - Buy: fill_price = gross_price + slippage (pays more)
    - Sell: fill_price = gross_price - slippage (receives less)

    Attributes:
        trade_id: Unique identifier (UUID string).
        timestamp: Fill time (next bar open after signal).
        symbol: Ticker symbol (e.g., "AAPL").
        side: Trade direction ("buy" or "sell").
        quantity: Number of shares traded.
        gross_price: Next bar open price before slippage.
        slippage: Per-share slippage amount.
        fill_price: Actual execution price (computed from gross_price and slippage).
        commission: Total commission for the trade.
        signal_bar_timestamp: When the signal was generated (bar close time).
    """

    trade_id: str
    timestamp: datetime
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    gross_price: Decimal
    slippage: Decimal
    commission: Decimal
    signal_bar_timestamp: datetime
    fill_price: Decimal = field(init=False)

    def __post_init__(self) -> None:
        """Compute fill_price based on side and slippage."""
        if self.side == "buy":
            # Buying costs more due to slippage
            self.fill_price = self.gross_price + self.slippage
        else:
            # Selling receives less due to slippage
            self.fill_price = self.gross_price - self.slippage
