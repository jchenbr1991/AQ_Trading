# backend/src/api/backtest.py
"""Backtest API endpoint for running backtests."""

import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

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
    error: str | None = None


def get_bar_loader():
    """Get bar loader. Override in tests."""
    csv_path = Path(__file__).parent.parent.parent / "data" / "bars.csv"
    return CSVBarLoader(csv_path)


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
        )

        engine = BacktestEngine(bar_loader=get_bar_loader())
        result = await engine.run(config)

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
