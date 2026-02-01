# AQ Trading AI Agents - Backtest Tool
# T024: Run backtest with specified parameters
"""Backtest tool for AI agents.

This tool allows agents to run backtests on trading strategies
and retrieve performance metrics using the backend backtest engine.

Usage:
    tool = create_backtest_tool()
    result = await tool.execute(
        strategy="src.strategies.momentum.MomentumStrategy",
        params={"lookback": 20},
        symbol="AAPL",
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
"""

import logging
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from agents.base import Tool
from agents.config import get_bars_csv_path

logger = logging.getLogger(__name__)


async def run_backtest(
    strategy: str,
    symbol: str,
    params: dict[str, Any] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: str | None = None,
    slippage_bps: int = 5,
    commission_per_share: str = "0.005",
    benchmark_symbol: str | None = None,
) -> dict[str, Any]:
    """Run backtest with given parameters using the backend engine.

    Args:
        strategy: Fully qualified strategy class name (e.g., "src.strategies.momentum.MomentumStrategy")
        symbol: Ticker symbol to backtest (e.g., "AAPL")
        params: Strategy-specific parameters (e.g., {"lookback": 20, "threshold": 0.02})
        start_date: Backtest start date in YYYY-MM-DD format
        end_date: Backtest end date in YYYY-MM-DD format
        initial_capital: Starting capital (default: "100000")
        slippage_bps: Slippage in basis points (default: 5)
        commission_per_share: Commission per share (default: "0.005")
        benchmark_symbol: Optional benchmark symbol for comparison (e.g., "SPY")

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - strategy: The strategy that was backtested
        - metrics: Performance metrics (sharpe_ratio, max_drawdown, etc.)
        - benchmark: Benchmark comparison metrics (if benchmark_symbol provided)
        - error: Error message if status is 'error'

    Example:
        >>> result = await run_backtest(
        ...     strategy="src.strategies.momentum.MomentumStrategy",
        ...     symbol="AAPL",
        ...     params={"lookback": 20, "threshold": 0.02},
        ...     start_date="2024-01-01",
        ...     end_date="2024-06-30"
        ... )
        >>> result["status"]
        'success'
    """
    # Validate required inputs
    if not strategy:
        return {
            "status": "error",
            "error": "Strategy class name is required",
        }

    if not symbol:
        return {
            "status": "error",
            "error": "Symbol is required",
        }

    if not start_date or not end_date:
        return {
            "status": "error",
            "error": "Both start_date and end_date are required",
        }

    try:
        # Import backend modules here to avoid circular imports
        from src.backtest.bar_loader import CSVBarLoader
        from src.backtest.engine import BacktestEngine
        from src.backtest.models import BacktestConfig

        # Parse dates
        parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()

        # Create config
        config = BacktestConfig(
            strategy_class=strategy,
            strategy_params=params or {},
            symbol=symbol,
            start_date=parsed_start,
            end_date=parsed_end,
            initial_capital=Decimal(initial_capital or "100000"),
            slippage_bps=slippage_bps,
            commission_per_share=Decimal(commission_per_share),
            benchmark_symbol=benchmark_symbol,
        )

        # Get bar loader (use configured data path)
        csv_path = Path(get_bars_csv_path())
        bar_loader = CSVBarLoader(csv_path)

        # Create engine and run backtest
        logger.info(
            "Running backtest: strategy=%s, symbol=%s, period=%s to %s",
            strategy,
            symbol,
            start_date,
            end_date,
        )

        engine = BacktestEngine(bar_loader=bar_loader)
        result = await engine.run(config)

        # Build response with metrics
        metrics = {
            "total_return": str(result.total_return),
            "annualized_return": str(result.annualized_return),
            "sharpe_ratio": str(result.sharpe_ratio),
            "max_drawdown": str(result.max_drawdown),
            "win_rate": str(result.win_rate),
            "total_trades": result.total_trades,
            "avg_trade_pnl": str(result.avg_trade_pnl),
            "final_equity": str(result.final_equity),
            "final_cash": str(result.final_cash),
            "final_position_qty": result.final_position_qty,
        }

        # Build benchmark comparison if available
        benchmark = None
        if result.benchmark:
            benchmark = {
                "benchmark_symbol": result.benchmark.benchmark_symbol,
                "benchmark_total_return": str(result.benchmark.benchmark_total_return),
                "alpha": str(result.benchmark.alpha),
                "beta": str(result.benchmark.beta),
                "tracking_error": str(result.benchmark.tracking_error),
                "information_ratio": str(result.benchmark.information_ratio),
                "sortino_ratio": str(result.benchmark.sortino_ratio),
                "up_capture": str(result.benchmark.up_capture),
                "down_capture": str(result.benchmark.down_capture),
            }

        logger.info(
            "Backtest completed: sharpe=%s, max_dd=%s, trades=%d",
            result.sharpe_ratio,
            result.max_drawdown,
            result.total_trades,
        )

        return {
            "status": "success",
            "strategy": strategy,
            "symbol": symbol,
            "params": params or {},
            "period": {
                "start": start_date,
                "end": end_date,
            },
            "metrics": metrics,
            "benchmark": benchmark,
            "warmup": {
                "required_bars": result.warm_up_required_bars,
                "bars_used": result.warm_up_bars_used,
            },
        }

    except ValueError as e:
        # Strategy not allowed or insufficient data
        logger.error("Backtest validation error: %s", e)
        return {
            "status": "error",
            "error": f"Validation error: {str(e)}",
            "strategy": strategy,
            "symbol": symbol,
        }
    except FileNotFoundError as e:
        logger.error("Backtest data file not found: %s", e)
        return {
            "status": "error",
            "error": f"Data file not found: {str(e)}",
            "strategy": strategy,
            "symbol": symbol,
        }
    except Exception as e:
        logger.error("Backtest failed: %s", e)
        return {
            "status": "error",
            "error": f"Backtest failed: {str(e)}",
            "strategy": strategy,
            "symbol": symbol,
        }


def create_backtest_tool() -> Tool:
    """Create and return the backtest tool.

    Returns:
        Tool instance configured for backtest operations.

    The tool requires the following permissions:
    - backtest/*: Execute backtest operations
    """
    return Tool(
        name="backtest",
        description="Run backtest with specified strategy and parameters. "
        "Returns performance metrics including Sharpe ratio, drawdown, and returns.",
        execute=run_backtest,
        required_permissions=["backtest/*"],
    )
