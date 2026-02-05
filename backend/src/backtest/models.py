"""Backtest data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.backtest.benchmark import BenchmarkComparison
    from src.backtest.trace import SignalTrace


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
        entry_factors: Factor scores at trade entry for attribution (FR-025).
        exit_factors: Factor scores at trade exit for attribution.
        attribution: PnL attribution by factor after trade close (FR-023).
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
    entry_factors: dict[str, Decimal] = field(default_factory=dict)
    exit_factors: dict[str, Decimal] = field(default_factory=dict)
    attribution: dict[str, Decimal] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Compute fill_price based on side and slippage."""
        if self.side == "buy":
            # Buying costs more due to slippage
            self.fill_price = self.gross_price + self.slippage
        else:
            # Selling receives less due to slippage
            self.fill_price = self.gross_price - self.slippage


@dataclass
class BacktestConfig:
    """Configuration for a backtest run.

    Attributes:
        strategy_class: Fully qualified name or identifier of the strategy.
        strategy_params: Dictionary of parameters to pass to the strategy.
        symbol: Ticker symbol to backtest (e.g., "AAPL").
        start_date: First date of the backtest period (inclusive).
        end_date: Last date of the backtest period (inclusive).
        initial_capital: Starting cash amount for the backtest.
        fill_model: How orders are filled. Currently only "next_bar_open".
        slippage_model: How slippage is calculated. Currently only "fixed_bps".
        slippage_bps: Slippage in basis points (5 = 0.05%).
        commission_model: How commission is calculated. Currently only "per_share".
        commission_per_share: Commission charged per share traded.
        benchmark_symbol: Optional benchmark symbol for comparison (e.g., "SPY").
    """

    strategy_class: str
    strategy_params: dict
    symbol: str
    start_date: date
    end_date: date
    initial_capital: Decimal
    fill_model: Literal["next_bar_open"] = "next_bar_open"
    slippage_model: Literal["fixed_bps"] = "fixed_bps"
    slippage_bps: int = 5
    commission_model: Literal["per_share"] = "per_share"
    commission_per_share: Decimal = field(default_factory=lambda: Decimal("0.005"))
    benchmark_symbol: str | None = None


@dataclass
class BacktestResult:
    """Complete results from a backtest run.

    Attributes:
        config: The configuration used for this backtest.
        equity_curve: Time series of (timestamp, equity) tuples.
        trades: List of all executed trades during the backtest.
        final_equity: Total portfolio value at end (cash + positions).
        final_cash: Cash balance at end of backtest.
        final_position_qty: Number of shares held at end of backtest.
        total_return: Total return as a decimal (0.10 = 10%).
        annualized_return: Annualized return as a decimal.
        sharpe_ratio: Risk-adjusted return metric.
        max_drawdown: Maximum peak-to-trough decline as a decimal.
        win_rate: Fraction of trades that were profitable.
        total_trades: Total number of trades executed.
        avg_trade_pnl: Average profit/loss per trade.
        warm_up_required_bars: Number of bars strategy needs for warm-up.
        warm_up_bars_used: Actual bars used for warm-up.
        first_signal_bar: Timestamp of bar that generated first signal, if any.
        started_at: When the backtest computation started.
        completed_at: When the backtest computation completed.
        benchmark: Optional BenchmarkComparison when benchmark comparison was computed.
        traces: List of SignalTrace objects capturing the audit trail from signal
            generation to order fill, including slippage analysis.
        attribution_summary: Total PnL attributed to each factor across all trades (FR-023).
    """

    config: BacktestConfig
    equity_curve: list[tuple[datetime, Decimal]]
    trades: list[Trade]
    final_equity: Decimal
    final_cash: Decimal
    final_position_qty: int
    total_return: Decimal
    annualized_return: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    total_trades: int
    avg_trade_pnl: Decimal
    warm_up_required_bars: int
    warm_up_bars_used: int
    first_signal_bar: datetime | None
    started_at: datetime
    completed_at: datetime
    benchmark: BenchmarkComparison | None = None
    traces: list[SignalTrace] = field(default_factory=list)
    attribution_summary: dict[str, Decimal] = field(default_factory=dict)
