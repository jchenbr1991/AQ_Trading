# AQ Trading AI Agents - Market Data Tool
# T025: Query historical and live market data
"""Market data tool for AI agents.

This tool provides access to historical and live market data,
including VIX and other volatility metrics via the backend market data service.

Usage:
    tool = create_market_data_tool()
    result = await tool.execute(
        symbols=["AAPL", "SPY"],
        data_type="ohlcv",
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
"""

import json
import logging
from datetime import datetime
from typing import Any, Literal

from agents.base import Tool
from agents.config import get_bars_csv_path
from agents.connections import get_redis_or_none

logger = logging.getLogger(__name__)

DataType = Literal["ohlcv", "quote", "vix"]


async def query_market_data(
    symbols: list[str] | None = None,
    data_type: DataType = "quote",
    start_date: str | None = None,
    end_date: str | None = None,
    interval: str = "1d",
) -> dict[str, Any]:
    """Query historical or live market data.

    Args:
        symbols: List of ticker symbols (e.g., ["AAPL", "SPY", "^VIX"])
        data_type: Type of data to retrieve:
            - 'ohlcv': Open, High, Low, Close, Volume (historical, daily only)
            - 'quote': Current quote data (live)
            - 'vix': VIX volatility index
        start_date: Start date for historical data (YYYY-MM-DD)
        end_date: End date for historical data (YYYY-MM-DD)
        interval: Data interval (only '1d' supported for OHLCV currently)

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - data_type: The type of data requested
        - symbols: The symbols queried
        - data: The market data
        - error: Error message if status is 'error'

    Example:
        >>> result = await query_market_data(
        ...     symbols=["AAPL"],
        ...     data_type="quote"
        ... )
        >>> result["status"]
        'success'
    """
    # Validate inputs
    if not symbols or len(symbols) == 0:
        return {
            "status": "error",
            "error": "At least one symbol is required",
        }

    valid_intervals = ["1m", "5m", "15m", "1h", "1d", "1w", "1M"]
    if interval not in valid_intervals:
        return {
            "status": "error",
            "error": f"Invalid interval '{interval}'. Must be one of: {valid_intervals}",
        }

    # OHLCV data only supports daily bars from CSV loader
    # Reject unsupported intervals upfront to avoid silent incorrect data
    ohlcv_supported_intervals = ["1d"]
    if data_type == "ohlcv" and interval not in ohlcv_supported_intervals:
        return {
            "status": "error",
            "error": f"OHLCV data only supports daily bars (interval='1d'). "
            f"Requested interval '{interval}' is not available.",
        }

    try:
        # For quote data, use Redis-cached quotes
        if data_type == "quote":
            return await _get_quotes_from_redis(symbols)

        # For historical OHLCV data, use CSVBarLoader (daily bars only)
        if data_type == "ohlcv":
            return await _get_historical_bars(symbols, start_date, end_date)

        # For VIX data - wrap response to include consistent fields
        if data_type == "vix":
            vix_result = await get_vix_metrics()
            # Add data_type and symbols for consistent schema
            vix_result["data_type"] = "vix"
            vix_result["symbols"] = symbols
            return vix_result

        return {
            "status": "error",
            "error": f"Data type '{data_type}' not yet supported",
        }

    except Exception as e:
        logger.error("Market data query failed: %s", e)
        return {
            "status": "error",
            "error": f"Query failed: {str(e)}",
            "data_type": data_type,
            "symbols": symbols,
        }


async def _get_quotes_from_redis(symbols: list[str]) -> dict[str, Any]:
    """Get quote data from Redis cache."""
    try:
        async with get_redis_or_none() as client:
            if client is None:
                logger.warning("Redis not available, returning empty quotes")
                return {
                    "status": "success",
                    "data_type": "quote",
                    "symbols": symbols,
                    "data": {s: None for s in symbols},
                    "message": "Redis not available",
                }

            quotes = {}
            for symbol in symbols:
                key = f"quote:{symbol}"
                data = await client.get(key)
                if data:
                    quotes[symbol] = json.loads(data)
                else:
                    quotes[symbol] = None

            return {
                "status": "success",
                "data_type": "quote",
                "symbols": symbols,
                "data": quotes,
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error("Redis query failed: %s", e)
        return {
            "status": "error",
            "error": f"Redis query failed: {str(e)}",
        }


async def _get_historical_bars(
    symbols: list[str],
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    """Get historical bar data from CSV."""
    if not start_date or not end_date:
        return {
            "status": "error",
            "error": "start_date and end_date required for historical data",
        }

    try:
        from pathlib import Path

        from src.backtest.bar_loader import CSVBarLoader

        csv_path = Path(get_bars_csv_path())
        loader = CSVBarLoader(csv_path)

        parsed_start = datetime.strptime(start_date, "%Y-%m-%d").date()
        parsed_end = datetime.strptime(end_date, "%Y-%m-%d").date()

        all_data = {}
        for symbol in symbols:
            bars = await loader.load(symbol, parsed_start, parsed_end)
            all_data[symbol] = [
                {
                    "timestamp": b.timestamp.isoformat(),
                    "open": str(b.open),
                    "high": str(b.high),
                    "low": str(b.low),
                    "close": str(b.close),
                    "volume": b.volume,
                }
                for b in bars
            ]

        return {
            "status": "success",
            "data_type": "ohlcv",
            "symbols": symbols,
            "period": {"start": start_date, "end": end_date},
            "data": all_data,
        }

    except FileNotFoundError:
        return {
            "status": "error",
            "error": "Historical data file not found",
        }
    except Exception as e:
        return {
            "status": "error",
            "error": f"Failed to load historical data: {str(e)}",
        }


async def get_vix_metrics() -> dict[str, Any]:
    """Get VIX and related volatility metrics.

    Returns:
        Dictionary containing VIX current value and related metrics.

    Example:
        >>> result = await get_vix_metrics()
        >>> result["status"]
        'success'
    """
    try:
        async with get_redis_or_none() as client:
            if client is None:
                return {
                    "status": "success",
                    "vix": {"current": None},
                    "volatility_regime": None,
                    "message": "Redis not available",
                }

            # Try to get VIX from Redis quote cache
            vix_data = await client.get("quote:^VIX")

            if vix_data:
                vix = json.loads(vix_data)
                price = vix.get("price")

                # Handle missing or invalid price
                if price is None:
                    return {
                        "status": "success",
                        "vix": {"current": None},
                        "volatility_regime": None,
                        "message": "VIX price not available in cached data",
                    }

                current = float(price)

                # Determine volatility regime using centralized logic
                from agents.tools.volatility import classify_vix_regime
                regime = classify_vix_regime(current)

                return {
                    "status": "success",
                    "vix": {
                        "current": current,
                        "bid": vix.get("bid"),
                        "ask": vix.get("ask"),
                        "timestamp": vix.get("timestamp"),
                    },
                    "volatility_regime": regime,
                }

            return {
                "status": "success",
                "vix": {"current": None},
                "volatility_regime": None,
                "message": "VIX data not available in cache",
            }

    except Exception as e:
        logger.error("VIX query failed: %s", e)
        return {
            "status": "error",
            "error": f"VIX query failed: {str(e)}",
        }


def create_market_data_tool() -> Tool:
    """Create and return the market data tool.

    Returns:
        Tool instance configured for market data queries.

    The tool requires the following permissions:
    - market_data/*: Read market data
    """
    return Tool(
        name="market_data",
        description="Query historical and live market data including OHLCV, "
        "quotes, VIX, and volatility metrics. Supports multiple symbols and intervals.",
        execute=query_market_data,
        required_permissions=["market_data/*"],
    )


def create_vix_tool() -> Tool:
    """Create and return the VIX metrics tool.

    Returns:
        Tool instance configured for VIX and volatility queries.

    The tool requires the following permissions:
    - market_data/*: Read market data
    """
    return Tool(
        name="vix",
        description="Get current VIX value and related volatility metrics "
        "including volatility regime classification.",
        execute=get_vix_metrics,
        required_permissions=["market_data/*"],
    )
