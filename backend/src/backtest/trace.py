"""Trace data models for signal-to-fill audit trail with slippage analysis.

This module provides frozen dataclasses to capture the complete audit trail
from signal generation through order execution, enabling post-hoc analysis
of trading decisions and execution quality.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

# Type alias for JSON-serializable scalar values
JsonScalar = str | int | float | bool | None


@dataclass(frozen=True)
class BarSnapshot:
    """Snapshot of OHLCV bar data at a point in time.

    Used to capture the market state when a signal was generated or filled.

    Attributes:
        symbol: Ticker symbol (e.g., "AAPL").
        timestamp: Bar close time (should be timezone-aware).
        open: Opening price of the interval.
        high: Highest price during the interval.
        low: Lowest price during the interval.
        close: Closing price of the interval.
        volume: Total shares traded during the interval.
    """

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Snapshot of portfolio state at signal generation time.

    Captures the portfolio's cash, position, and equity when a signal
    was generated, enabling analysis of position sizing and capital usage.

    Attributes:
        cash: Available cash balance.
        position_qty: Number of shares currently held (0 if flat).
        position_avg_cost: Average cost per share of current position,
            or None if no position is held.
        equity: Total portfolio value (cash + position market value).
    """

    cash: Decimal
    position_qty: int
    position_avg_cost: Decimal | None
    equity: Decimal


@dataclass(frozen=True)
class StrategySnapshot:
    """Snapshot of strategy state at signal generation time.

    Captures the strategy's parameters and internal state for debugging
    and analysis of trading decisions.

    Constraints:
        - params dict: max 20 keys, string values max 256 chars
        - state dict: max 20 keys, string values max 256 chars
        - Total serialized size should not exceed 8KB

    These constraints ensure efficient storage and prevent unbounded growth
    in trace data. Strategies should expose only essential state.

    Attributes:
        strategy_class: Fully qualified class name or identifier.
        params: Strategy configuration parameters (JSON-serializable scalars).
        state: Strategy internal state (JSON-serializable scalars).
    """

    strategy_class: str
    params: dict[str, JsonScalar]
    state: dict[str, JsonScalar]


@dataclass(frozen=True)
class SignalTrace:
    """Complete audit trail from signal generation to order fill.

    Captures all data needed to analyze trading decisions and execution
    quality, including market state, portfolio state, and slippage metrics.

    Slippage sign convention:
        slippage = fill_price - expected_price

        For BUY orders:
            - slippage > 0 means bought at higher price (unfavorable)
            - slippage < 0 means bought at lower price (favorable)

        For SELL orders:
            - slippage > 0 means sold at lower price (unfavorable)
            - slippage < 0 means sold at higher price (favorable)

        Note: This convention treats positive slippage as "bad" for both
        buy and sell orders, making it easier to aggregate slippage costs.

    Attributes:
        trace_id: Unique identifier for this trace record.
        signal_timestamp: When the signal was generated (bar close time).
        symbol: Ticker symbol for the trade.
        signal_direction: Trade direction ("buy" or "sell").
        signal_quantity: Number of shares requested.
        signal_reason: Optional human-readable reason for the signal.
        signal_bar: Market data bar that generated the signal.
        portfolio_state: Portfolio snapshot at signal time.
        strategy_snapshot: Optional strategy state snapshot.

        fill_bar: Market data bar when order was filled (None if unfilled).
        fill_timestamp: When the order was filled (None if unfilled).
        fill_quantity: Number of shares actually filled (None if unfilled).
        fill_price: Actual execution price (None if unfilled).

        expected_price: Price expected at signal time (None if unfilled).
        expected_price_type: How expected_price was determined.
        slippage: fill_price - expected_price (None if unfilled).
        slippage_bps: Slippage in basis points (None if unfilled).
        commission: Total commission paid for the fill (None if unfilled).
    """

    trace_id: str
    signal_timestamp: datetime
    symbol: str
    signal_direction: Literal["buy", "sell"]
    signal_quantity: int
    signal_reason: str | None
    signal_bar: BarSnapshot
    portfolio_state: PortfolioSnapshot
    strategy_snapshot: StrategySnapshot | None

    # Fill data (all None if order not yet filled)
    fill_bar: BarSnapshot | None
    fill_timestamp: datetime | None
    fill_quantity: int | None
    fill_price: Decimal | None

    # Slippage analysis (all None if order not yet filled)
    expected_price: Decimal | None
    expected_price_type: (
        Literal["next_bar_open", "signal_bar_close", "mid_quote", "limit_price"] | None
    )
    slippage: Decimal | None
    slippage_bps: Decimal | None
    commission: Decimal | None
