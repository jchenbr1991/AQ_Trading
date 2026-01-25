"""TraceBuilder for constructing SignalTrace instances.

This module provides factory methods for creating trace records at different
stages of the order lifecycle: pending (signal generated) and complete (filled).
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from src.backtest.models import Bar
from src.backtest.trace import (
    BarSnapshot,
    PortfolioSnapshot,
    SignalTrace,
    StrategySnapshot,
)


class TraceBuilder:
    """Factory for creating SignalTrace instances at different lifecycle stages.

    This class provides static methods to create traces when signals are generated
    and to complete them when fills occur, including slippage calculation.
    """

    @staticmethod
    def create_pending(
        signal_bar: Bar,
        signal_direction: Literal["buy", "sell"],
        signal_quantity: int,
        signal_reason: str | None,
        cash: Decimal,
        position_qty: int,
        position_avg_cost: Decimal | None,
        equity: Decimal,
        strategy_snapshot: StrategySnapshot | None,
    ) -> SignalTrace:
        """Create a pending trace when a signal is generated.

        Creates a trace record capturing the signal and market/portfolio state
        at signal generation time. All fill-related fields are set to None.

        Args:
            signal_bar: The bar that generated the signal.
            signal_direction: Trade direction ("buy" or "sell").
            signal_quantity: Number of shares requested.
            signal_reason: Optional human-readable reason for the signal.
            cash: Available cash balance at signal time.
            position_qty: Number of shares held at signal time.
            position_avg_cost: Average cost of current position, or None if flat.
            equity: Total portfolio value at signal time.
            strategy_snapshot: Optional snapshot of strategy state.

        Returns:
            A SignalTrace with signal data populated and fill fields as None.
        """
        # Generate unique trace ID
        trace_id = str(uuid.uuid4())

        # Convert Bar to BarSnapshot
        bar_snapshot = BarSnapshot(
            symbol=signal_bar.symbol,
            timestamp=signal_bar.timestamp,
            open=signal_bar.open,
            high=signal_bar.high,
            low=signal_bar.low,
            close=signal_bar.close,
            volume=signal_bar.volume,
        )

        # Create portfolio snapshot
        portfolio_state = PortfolioSnapshot(
            cash=cash,
            position_qty=position_qty,
            position_avg_cost=position_avg_cost,
            equity=equity,
        )

        return SignalTrace(
            trace_id=trace_id,
            signal_timestamp=signal_bar.timestamp,
            symbol=signal_bar.symbol,
            signal_direction=signal_direction,
            signal_quantity=signal_quantity,
            signal_reason=signal_reason,
            signal_bar=bar_snapshot,
            portfolio_state=portfolio_state,
            strategy_snapshot=strategy_snapshot,
            fill_bar=None,
            fill_timestamp=None,
            fill_quantity=None,
            fill_price=None,
            expected_price=None,
            expected_price_type=None,
            slippage=None,
            slippage_bps=None,
            commission=None,
        )

    @staticmethod
    def complete(
        pending_trace: SignalTrace,
        fill_bar: Bar | None,
        fill_price: Decimal | None,
        fill_quantity: int | None,
        commission: Decimal | None,
    ) -> SignalTrace:
        """Complete a pending trace with fill data and slippage calculation.

        Takes a pending trace and adds fill information, calculating slippage
        using the next_bar_open model (expected_price = fill_bar.open).

        Slippage calculation (MVP rules):
            - expected_price = fill_bar.open (next_bar_open model)
            - expected_price_type = "next_bar_open"
            - slippage = fill_price - expected_price
            - slippage_bps = (slippage / expected_price) * 10000, ROUND_HALF_UP
            - If fill_price, expected_price is None, or expected_price == 0:
              slippage = None, slippage_bps = None

        Args:
            pending_trace: The pending trace to complete.
            fill_bar: The bar when the order was filled, or None if unfilled.
            fill_price: Actual execution price, or None if unfilled.
            fill_quantity: Number of shares actually filled, or None if unfilled.
            commission: Total commission paid, or None if unfilled.

        Returns:
            A new SignalTrace with fill data and slippage analysis populated.
        """
        # Determine expected price from fill bar (next_bar_open model)
        expected_price: Decimal | None = None
        expected_price_type: (
            Literal["next_bar_open", "signal_bar_close", "mid_quote", "limit_price"] | None
        ) = None
        slippage: Decimal | None = None
        slippage_bps: Decimal | None = None
        fill_bar_snapshot: BarSnapshot | None = None
        fill_timestamp = None

        if fill_bar is not None:
            # Convert fill bar to snapshot
            fill_bar_snapshot = BarSnapshot(
                symbol=fill_bar.symbol,
                timestamp=fill_bar.timestamp,
                open=fill_bar.open,
                high=fill_bar.high,
                low=fill_bar.low,
                close=fill_bar.close,
                volume=fill_bar.volume,
            )
            fill_timestamp = fill_bar.timestamp
            expected_price = fill_bar.open
            expected_price_type = "next_bar_open"

        # Calculate slippage if we have valid data
        if fill_price is not None and expected_price is not None and expected_price != Decimal("0"):
            slippage = fill_price - expected_price
            # slippage_bps = (slippage / expected_price) * 10000, rounded HALF_UP
            slippage_bps = (slippage / expected_price * Decimal("10000")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )

        return SignalTrace(
            trace_id=pending_trace.trace_id,
            signal_timestamp=pending_trace.signal_timestamp,
            symbol=pending_trace.symbol,
            signal_direction=pending_trace.signal_direction,
            signal_quantity=pending_trace.signal_quantity,
            signal_reason=pending_trace.signal_reason,
            signal_bar=pending_trace.signal_bar,
            portfolio_state=pending_trace.portfolio_state,
            strategy_snapshot=pending_trace.strategy_snapshot,
            fill_bar=fill_bar_snapshot,
            fill_timestamp=fill_timestamp,
            fill_quantity=fill_quantity,
            fill_price=fill_price,
            expected_price=expected_price,
            expected_price_type=expected_price_type,
            slippage=slippage,
            slippage_bps=slippage_bps,
            commission=commission,
        )
