# backend/src/api/backtest.py
"""Backtest API endpoint for running backtests."""

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig


class BacktestRequest(BaseModel):
    """Request body for running a backtest."""

    strategy_class: str
    strategy_params: dict
    symbol: str
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("100000")
    slippage_bps: int = 5
    commission_per_share: Decimal = Decimal("0.005")
    benchmark_symbol: str | None = None


class BarSnapshotResponse(BaseModel):
    """Schema for bar snapshot data."""

    symbol: str
    timestamp: str  # ISO format
    open: str
    high: str
    low: str
    close: str
    volume: int


class PortfolioSnapshotResponse(BaseModel):
    """Schema for portfolio snapshot data."""

    cash: str
    position_qty: int
    position_avg_cost: str | None
    equity: str


class StrategySnapshotResponse(BaseModel):
    """Schema for strategy snapshot data."""

    strategy_class: str
    params: dict[str, Any]
    state: dict[str, Any]


class SignalTraceResponse(BaseModel):
    """Schema for signal trace data."""

    trace_id: str
    signal_timestamp: str
    symbol: str
    signal_direction: str
    signal_quantity: int
    signal_reason: str | None
    signal_bar: BarSnapshotResponse
    portfolio_state: PortfolioSnapshotResponse
    strategy_snapshot: StrategySnapshotResponse | None
    fill_bar: BarSnapshotResponse | None
    fill_timestamp: str | None
    fill_quantity: int | None
    fill_price: str | None
    expected_price: str | None
    expected_price_type: str | None
    slippage: str | None
    slippage_bps: str | None
    commission: str | None


class BenchmarkComparisonResponse(BaseModel):
    """Schema for benchmark comparison metrics."""

    benchmark_symbol: str
    benchmark_total_return: str  # Decimal as string
    alpha: str
    beta: str
    tracking_error: str
    information_ratio: str
    sortino_ratio: str
    up_capture: str
    down_capture: str


class BacktestResultSchema(BaseModel):
    """Schema for backtest result metrics."""

    final_equity: str
    final_cash: str
    final_position_qty: int
    total_return: str
    annualized_return: str
    sharpe_ratio: str
    max_drawdown: str
    win_rate: str
    total_trades: int
    avg_trade_pnl: str
    warm_up_required_bars: int
    warm_up_bars_used: int


class BacktestResponse(BaseModel):
    """Response body for backtest endpoint."""

    backtest_id: str
    status: str  # "completed" or "failed"
    result: BacktestResultSchema | None = None
    benchmark: BenchmarkComparisonResponse | None = None
    traces: list[SignalTraceResponse] = []
    error: str | None = None


def get_bar_loader():
    """Get bar loader. Override in tests."""
    csv_path = Path(__file__).parent.parent.parent / "data" / "bars.csv"
    return CSVBarLoader(csv_path)


def _convert_bar_snapshot(bar) -> BarSnapshotResponse:
    """Convert BarSnapshot to BarSnapshotResponse."""
    return BarSnapshotResponse(
        symbol=bar.symbol,
        timestamp=bar.timestamp.isoformat(),
        open=str(bar.open),
        high=str(bar.high),
        low=str(bar.low),
        close=str(bar.close),
        volume=bar.volume,
    )


def _convert_portfolio_snapshot(portfolio) -> PortfolioSnapshotResponse:
    """Convert PortfolioSnapshot to PortfolioSnapshotResponse."""
    return PortfolioSnapshotResponse(
        cash=str(portfolio.cash),
        position_qty=portfolio.position_qty,
        position_avg_cost=str(portfolio.position_avg_cost)
        if portfolio.position_avg_cost is not None
        else None,
        equity=str(portfolio.equity),
    )


def _convert_strategy_snapshot(strategy) -> StrategySnapshotResponse:
    """Convert StrategySnapshot to StrategySnapshotResponse."""
    return StrategySnapshotResponse(
        strategy_class=strategy.strategy_class,
        params=dict(strategy.params),
        state=dict(strategy.state),
    )


def _convert_trace(trace) -> SignalTraceResponse:
    """Convert SignalTrace to SignalTraceResponse."""
    return SignalTraceResponse(
        trace_id=trace.trace_id,
        signal_timestamp=trace.signal_timestamp.isoformat(),
        symbol=trace.symbol,
        signal_direction=trace.signal_direction,
        signal_quantity=trace.signal_quantity,
        signal_reason=trace.signal_reason,
        signal_bar=_convert_bar_snapshot(trace.signal_bar),
        portfolio_state=_convert_portfolio_snapshot(trace.portfolio_state),
        strategy_snapshot=_convert_strategy_snapshot(trace.strategy_snapshot)
        if trace.strategy_snapshot
        else None,
        fill_bar=_convert_bar_snapshot(trace.fill_bar) if trace.fill_bar else None,
        fill_timestamp=trace.fill_timestamp.isoformat() if trace.fill_timestamp else None,
        fill_quantity=trace.fill_quantity,
        fill_price=str(trace.fill_price) if trace.fill_price is not None else None,
        expected_price=str(trace.expected_price) if trace.expected_price is not None else None,
        expected_price_type=trace.expected_price_type,
        slippage=str(trace.slippage) if trace.slippage is not None else None,
        slippage_bps=str(trace.slippage_bps) if trace.slippage_bps is not None else None,
        commission=str(trace.commission) if trace.commission is not None else None,
    )


router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """Run a backtest with given configuration.

    Args:
        request: Backtest configuration including strategy, symbol, and date range.

    Returns:
        BacktestResponse with status and results or error.

    Raises:
        HTTPException: 400 if strategy is not allowed or insufficient data.
    """
    backtest_id = str(uuid.uuid4())

    try:
        config = BacktestConfig(
            strategy_class=request.strategy_class,
            strategy_params=request.strategy_params,
            symbol=request.symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            slippage_bps=request.slippage_bps,
            commission_per_share=request.commission_per_share,
            benchmark_symbol=request.benchmark_symbol,
        )

        engine = BacktestEngine(bar_loader=get_bar_loader())
        result = await engine.run(config)

        # Convert benchmark comparison if present
        benchmark_response = None
        if result.benchmark:
            benchmark_response = BenchmarkComparisonResponse(
                benchmark_symbol=result.benchmark.benchmark_symbol,
                benchmark_total_return=str(result.benchmark.benchmark_total_return),
                alpha=str(result.benchmark.alpha),
                beta=str(result.benchmark.beta),
                tracking_error=str(result.benchmark.tracking_error),
                information_ratio=str(result.benchmark.information_ratio),
                sortino_ratio=str(result.benchmark.sortino_ratio),
                up_capture=str(result.benchmark.up_capture),
                down_capture=str(result.benchmark.down_capture),
            )

        # Convert traces to response format
        traces_response = [_convert_trace(trace) for trace in result.traces]

        return BacktestResponse(
            backtest_id=backtest_id,
            status="completed",
            result=BacktestResultSchema(
                final_equity=str(result.final_equity),
                final_cash=str(result.final_cash),
                final_position_qty=result.final_position_qty,
                total_return=str(result.total_return),
                annualized_return=str(result.annualized_return),
                sharpe_ratio=str(result.sharpe_ratio),
                max_drawdown=str(result.max_drawdown),
                win_rate=str(result.win_rate),
                total_trades=result.total_trades,
                avg_trade_pnl=str(result.avg_trade_pnl),
                warm_up_required_bars=result.warm_up_required_bars,
                warm_up_bars_used=result.warm_up_bars_used,
            ),
            benchmark=benchmark_response,
            traces=traces_response,
            error=None,
        )
    except ValueError as e:
        # Strategy not in allowlist or insufficient data
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # Other failures (import errors, etc.)
        return BacktestResponse(
            backtest_id=backtest_id,
            status="failed",
            result=None,
            error=str(e),
        )
