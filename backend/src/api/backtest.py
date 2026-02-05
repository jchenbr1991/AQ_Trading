# backend/src/api/backtest.py
"""Backtest API endpoint for running backtests."""

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig, BacktestResult

# In-memory storage for backtest results (MVP - use database in production)
_backtest_results: dict[str, BacktestResult] = {}


def get_backtest_results() -> dict[str, BacktestResult]:
    """Get the backtest results storage. Override in tests."""
    return _backtest_results


def clear_backtest_results() -> None:
    """Clear the backtest results storage (for testing)."""
    _backtest_results.clear()


# ============================================================================
# Request/Response Models matching OpenAPI Contract (backtest-api.yaml)
# ============================================================================


class StrategyConfig(BaseModel):
    """Strategy configuration options."""

    entry_threshold: float = 0.0
    exit_threshold: float = -0.02
    position_sizing: str = "equal_weight"
    position_size: int = 100
    risk_per_trade: float = 0.02
    feature_weights: dict[str, float] | None = None
    factor_weights: dict[str, float] | None = None


class BacktestRequest(BaseModel):
    """Request body for running a backtest (matches OpenAPI contract)."""

    strategy: str = Field(..., description="Strategy identifier")
    universe: str = Field(default="mvp-universe", description="Universe name")
    start_date: date = Field(..., description="Backtest start date")
    end_date: date = Field(..., description="Backtest end date")
    initial_capital: Decimal = Field(default=Decimal("100000"), description="Starting capital")
    config: StrategyConfig | None = Field(default=None, description="Strategy configuration")


class LegacyBacktestRequest(BaseModel):
    """Legacy request body for backward compatibility."""

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
    """Schema for backtest result metrics (legacy format)."""

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


class LegacyBacktestResponse(BaseModel):
    """Legacy response body for backward compatibility."""

    backtest_id: str
    status: str  # "completed" or "failed"
    result: BacktestResultSchema | None = None
    benchmark: BenchmarkComparisonResponse | None = None
    traces: list[SignalTraceResponse] = []
    error: str | None = None


# ============================================================================
# New OpenAPI Contract Models (backtest-api.yaml)
# ============================================================================


class MetricsResponse(BaseModel):
    """Performance metrics matching OpenAPI Metrics schema."""

    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int


class TradeResponse(BaseModel):
    """Trade record matching OpenAPI Trade schema."""

    id: str
    symbol: str
    entry_date: str  # ISO datetime
    entry_price: float
    exit_date: str | None  # ISO datetime, None if position still open
    exit_price: float | None
    quantity: int
    pnl: float | None  # None if position still open
    entry_factors: dict[str, float]
    exit_factors: dict[str, float]
    attribution: dict[str, float]


class AttributionSummaryResponse(BaseModel):
    """Attribution summary matching OpenAPI AttributionSummary schema."""

    momentum_factor: float
    breakout_factor: float
    total: float


class EquityCurvePoint(BaseModel):
    """Single point in equity curve."""

    date: str  # ISO date
    equity: float


class BacktestResponse(BaseModel):
    """Response body for POST /api/backtest (matches OpenAPI BacktestResponse)."""

    id: str
    status: str  # "completed" or "failed"
    metrics: MetricsResponse | None = None
    trades: list[TradeResponse] = []
    attribution_summary: AttributionSummaryResponse | None = None
    equity_curve: list[EquityCurvePoint] = []
    error: str | None = None


# ============================================================================
# Attribution Response Models
# ============================================================================


class TradeAttributionResponse(BaseModel):
    """Per-trade attribution data."""

    trade_id: str
    symbol: str
    pnl: float
    attribution: dict[str, float]


class SymbolAttributionResponse(BaseModel):
    """Per-symbol attribution breakdown."""

    momentum_factor: float
    breakout_factor: float
    total: float


class AttributionResponse(BaseModel):
    """Response for GET /api/backtest/{id}/attribution."""

    backtest_id: str
    summary: AttributionSummaryResponse
    by_trade: list[TradeAttributionResponse]
    by_symbol: dict[str, SymbolAttributionResponse]


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


# Strategy name to class mapping for the new API
STRATEGY_CLASS_MAP = {
    "trend_breakout": "src.strategies.examples.trend_breakout.TrendBreakoutStrategy",
    "momentum": "src.strategies.examples.momentum.MomentumStrategy",
}


def _convert_trade_to_response(trade, entry_trade=None) -> TradeResponse:
    """Convert a Trade model to TradeResponse.

    Args:
        trade: The trade to convert
        entry_trade: If this is a sell trade, the corresponding entry trade

    Returns:
        TradeResponse matching the OpenAPI schema
    """
    # Determine if this is an entry or exit
    is_exit = trade.side == "sell"

    if is_exit and entry_trade:
        # This is an exit trade - pair with entry
        pnl = float(
            (trade.fill_price - entry_trade.fill_price) * trade.quantity
            - trade.commission
            - entry_trade.commission
        )
        return TradeResponse(
            id=entry_trade.trade_id,  # Use entry trade ID as the trade ID
            symbol=trade.symbol,
            entry_date=entry_trade.timestamp.isoformat(),
            entry_price=float(entry_trade.fill_price),
            exit_date=trade.timestamp.isoformat(),
            exit_price=float(trade.fill_price),
            quantity=trade.quantity,
            pnl=pnl,
            entry_factors={k: float(v) for k, v in entry_trade.entry_factors.items()},
            exit_factors={k: float(v) for k, v in trade.exit_factors.items()},
            attribution={k: float(v) for k, v in trade.attribution.items()},
        )
    else:
        # This is an entry trade without matching exit (open position)
        return TradeResponse(
            id=trade.trade_id,
            symbol=trade.symbol,
            entry_date=trade.timestamp.isoformat(),
            entry_price=float(trade.fill_price),
            exit_date=None,
            exit_price=None,
            quantity=trade.quantity,
            pnl=None,
            entry_factors={k: float(v) for k, v in trade.entry_factors.items()},
            exit_factors={},
            attribution={},
        )


def _build_trade_responses(trades: list) -> list[TradeResponse]:
    """Build trade responses from raw trades, pairing entries with exits.

    Args:
        trades: List of Trade objects from backtest

    Returns:
        List of TradeResponse objects with paired entry/exit trades
    """
    responses = []
    pending_entries: dict[str, Any] = {}  # symbol -> entry trade

    for trade in trades:
        if trade.side == "buy":
            pending_entries[trade.symbol] = trade
        elif trade.side == "sell":
            entry_trade = pending_entries.pop(trade.symbol, None)
            responses.append(_convert_trade_to_response(trade, entry_trade))

    # Add any remaining open positions
    for entry_trade in pending_entries.values():
        responses.append(_convert_trade_to_response(entry_trade))

    return responses


def _build_attribution_summary(result: BacktestResult) -> AttributionSummaryResponse:
    """Build attribution summary from backtest result."""
    summary = result.attribution_summary or {}
    total_pnl = sum(float(v) for v in summary.values()) if summary else 0.0

    return AttributionSummaryResponse(
        momentum_factor=float(summary.get("momentum_factor", 0)),
        breakout_factor=float(summary.get("breakout_factor", 0)),
        total=total_pnl,
    )


def _build_equity_curve(result: BacktestResult) -> list[EquityCurvePoint]:
    """Build equity curve from backtest result."""
    return [
        EquityCurvePoint(
            date=ts.date().isoformat(),
            equity=float(equity),
        )
        for ts, equity in result.equity_curve
    ]


@router.post("", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """Run a backtest with given configuration (OpenAPI contract).

    Args:
        request: Backtest configuration including strategy, universe, and date range.

    Returns:
        BacktestResponse with id, status, metrics, trades, attribution, and equity curve.

    Raises:
        HTTPException: 400 if strategy is not found or invalid parameters.
        HTTPException: 500 if backtest execution fails.
    """
    backtest_id = str(uuid.uuid4())

    try:
        # Map strategy name to class
        strategy_class = STRATEGY_CLASS_MAP.get(request.strategy)
        if not strategy_class:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy: {request.strategy}. "
                f"Available strategies: {list(STRATEGY_CLASS_MAP.keys())}",
            )

        # Build strategy params from config
        strategy_params: dict[str, Any] = {"name": request.strategy}
        if request.config:
            strategy_params["entry_threshold"] = request.config.entry_threshold
            strategy_params["exit_threshold"] = request.config.exit_threshold
            strategy_params["position_sizing"] = request.config.position_sizing
            strategy_params["position_size"] = request.config.position_size
            if request.config.feature_weights:
                strategy_params["feature_weights"] = request.config.feature_weights
            if request.config.factor_weights:
                strategy_params["factor_weights"] = request.config.factor_weights

        # For MVP, use a default symbol (first in universe or AAPL)
        # In production, this would iterate over universe symbols
        symbol = "AAPL"  # Default for MVP

        config = BacktestConfig(
            strategy_class=strategy_class,
            strategy_params=strategy_params,
            symbol=symbol,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
        )

        engine = BacktestEngine(bar_loader=get_bar_loader())
        result = await engine.run(config)

        # Store result for attribution endpoint
        backtest_results = get_backtest_results()
        backtest_results[backtest_id] = result

        # Build response
        metrics = MetricsResponse(
            total_return=float(result.total_return),
            sharpe_ratio=float(result.sharpe_ratio),
            max_drawdown=float(result.max_drawdown),
            win_rate=float(result.win_rate),
            total_trades=result.total_trades,
        )

        trades = _build_trade_responses(result.trades)
        attribution_summary = _build_attribution_summary(result)
        equity_curve = _build_equity_curve(result)

        return BacktestResponse(
            id=backtest_id,
            status="completed",
            metrics=metrics,
            trades=trades,
            attribution_summary=attribution_summary,
            equity_curve=equity_curve,
            error=None,
        )
    except HTTPException:
        raise
    except ValueError as e:
        # Strategy validation or insufficient data
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        # Other failures
        return BacktestResponse(
            id=backtest_id,
            status="failed",
            metrics=None,
            trades=[],
            attribution_summary=None,
            equity_curve=[],
            error=str(e),
        )


@router.get("/{backtest_id}/attribution", response_model=AttributionResponse)
async def get_attribution(backtest_id: str) -> AttributionResponse:
    """Get factor attribution for a completed backtest.

    Args:
        backtest_id: UUID of the backtest run.

    Returns:
        AttributionResponse with summary, per-trade, and per-symbol breakdowns.

    Raises:
        HTTPException: 404 if backtest not found.
    """
    backtest_results = get_backtest_results()
    result = backtest_results.get(backtest_id)

    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Backtest not found: {backtest_id}",
        )

    # Build summary
    summary = _build_attribution_summary(result)

    # Build per-trade attribution
    by_trade: list[TradeAttributionResponse] = []
    for trade in result.trades:
        if trade.side == "sell" and trade.attribution:
            # Calculate PnL from trade
            pnl = float(sum(Decimal(str(v)) for v in trade.attribution.values()))
            by_trade.append(
                TradeAttributionResponse(
                    trade_id=trade.trade_id,
                    symbol=trade.symbol,
                    pnl=pnl,
                    attribution={k: float(v) for k, v in trade.attribution.items()},
                )
            )

    # Build per-symbol attribution
    by_symbol: dict[str, SymbolAttributionResponse] = {}
    symbol_totals: dict[str, dict[str, float]] = {}

    for trade in result.trades:
        if trade.side == "sell" and trade.attribution:
            if trade.symbol not in symbol_totals:
                symbol_totals[trade.symbol] = {"momentum_factor": 0.0, "breakout_factor": 0.0}
            for factor, value in trade.attribution.items():
                if factor in symbol_totals[trade.symbol]:
                    symbol_totals[trade.symbol][factor] += float(value)

    for symbol, totals in symbol_totals.items():
        by_symbol[symbol] = SymbolAttributionResponse(
            momentum_factor=totals.get("momentum_factor", 0.0),
            breakout_factor=totals.get("breakout_factor", 0.0),
            total=totals.get("momentum_factor", 0.0) + totals.get("breakout_factor", 0.0),
        )

    return AttributionResponse(
        backtest_id=backtest_id,
        summary=summary,
        by_trade=by_trade,
        by_symbol=by_symbol,
    )


# ============================================================================
# Legacy Endpoint (backward compatibility)
# ============================================================================


@router.post("/legacy", response_model=LegacyBacktestResponse)
async def run_backtest_legacy(request: LegacyBacktestRequest) -> LegacyBacktestResponse:
    """Run a backtest with legacy configuration format.

    This endpoint maintains backward compatibility with the original API.

    Args:
        request: Legacy backtest configuration.

    Returns:
        LegacyBacktestResponse with status and results or error.

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

        # Store result for attribution endpoint
        backtest_results = get_backtest_results()
        backtest_results[backtest_id] = result

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

        return LegacyBacktestResponse(
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
        return LegacyBacktestResponse(
            backtest_id=backtest_id,
            status="failed",
            result=None,
            error=str(e),
        )
