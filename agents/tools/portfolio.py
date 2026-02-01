# AQ Trading AI Agents - Portfolio Tool
# T026: Read-only portfolio and position access
"""Portfolio tool for AI agents.

This tool provides read-only access to portfolio data,
positions, and Greeks exposure information via the backend portfolio service.

Usage:
    tool = create_portfolio_tool()
    result = await tool.execute(
        query_type="positions"
    )
"""

import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from agents.base import Tool
from agents.connections import get_db_session_or_none, get_redis_or_none

logger = logging.getLogger(__name__)

QueryType = Literal["summary", "positions", "greeks", "pnl"]


async def query_portfolio(
    query_type: QueryType = "summary",
    account_id: str = "default",
    symbol: str | None = None,
    strategy_id: str | None = None,
) -> dict[str, Any]:
    """Query portfolio data and positions.

    This is a read-only operation that retrieves current portfolio state.

    Args:
        query_type: Type of portfolio data to retrieve:
            - 'summary': Overall portfolio summary
            - 'positions': Current open positions
            - 'greeks': Greeks exposure data (delta, gamma, theta, vega)
            - 'pnl': Profit/loss breakdown
        account_id: Account ID to query (default: "default")
        symbol: Optional symbol to filter by (e.g., "AAPL")
        strategy_id: Optional strategy ID to filter by

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - query_type: The type of query performed
        - data: The portfolio data
        - timestamp: When the data was retrieved
        - error: Error message if status is 'error'

    Example:
        >>> result = await query_portfolio(query_type="positions")
        >>> result["status"]
        'success'
    """
    try:
        if query_type == "positions":
            return await _get_positions(account_id, symbol, strategy_id)
        elif query_type == "summary":
            return await _get_account_summary(account_id)
        elif query_type == "pnl":
            return await _get_pnl(account_id, strategy_id)
        elif query_type == "greeks":
            return await get_greeks_exposure(symbol)
        else:
            return {
                "status": "error",
                "error": f"Query type '{query_type}' not yet supported",
            }

    except Exception as e:
        logger.error("Portfolio query failed: %s", e)
        return {
            "status": "error",
            "error": f"Query failed: {str(e)}",
            "query_type": query_type,
        }


async def _get_positions(
    account_id: str,
    symbol: str | None,
    strategy_id: str | None,
) -> dict[str, Any]:
    """Get positions from the database."""
    try:
        from sqlalchemy import select
        from src.models.position import Position

        async with get_db_session_or_none() as session:
            if session is None:
                logger.warning("Database not available")
                return {
                    "status": "success",
                    "query_type": "positions",
                    "data": {"positions": [], "count": 0},
                    "message": "Database not available",
                }

            stmt = select(Position).where(Position.account_id == account_id)
            if symbol:
                stmt = stmt.where(Position.symbol == symbol)
            if strategy_id:
                stmt = stmt.where(Position.strategy_id == strategy_id)

            result = await session.execute(stmt)
            positions = result.scalars().all()

            position_list = [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": str(p.avg_cost) if p.avg_cost else None,
                    "current_price": str(p.current_price) if p.current_price else None,
                    "market_value": str(p.market_value) if hasattr(p, 'market_value') and p.market_value else None,
                    "asset_type": p.asset_type.value if hasattr(p, 'asset_type') and p.asset_type else "stock",
                    "strategy_id": p.strategy_id,
                }
                for p in positions
            ]

            return {
                "status": "success",
                "query_type": "positions",
                "data": {
                    "positions": position_list,
                    "count": len(position_list),
                },
                "timestamp": datetime.now().isoformat(),
            }

    except ImportError as e:
        logger.warning("Database dependencies not available: %s", e)
        return {
            "status": "success",
            "query_type": "positions",
            "data": {"positions": [], "count": 0},
            "message": "Database not available",
        }
    except Exception as e:
        logger.error("Position query failed: %s", e)
        return {
            "status": "error",
            "error": f"Position query failed: {str(e)}",
        }


async def _get_account_summary(account_id: str) -> dict[str, Any]:
    """Get account summary from the database."""
    try:
        from sqlalchemy import select
        from src.models.account import Account

        async with get_db_session_or_none() as session:
            if session is None:
                return {
                    "status": "success",
                    "query_type": "summary",
                    "data": {"account_id": account_id, "cash": None},
                    "message": "Database not available",
                }

            stmt = select(Account).where(Account.account_id == account_id)
            result = await session.execute(stmt)
            account = result.scalar_one_or_none()

            if account:
                summary = {
                    "account_id": account.account_id,
                    "cash": str(account.cash) if account.cash else "0",
                    "buying_power": str(account.buying_power) if hasattr(account, 'buying_power') and account.buying_power else None,
                    "total_equity": str(account.total_equity) if hasattr(account, 'total_equity') and account.total_equity else None,
                    "margin_used": str(account.margin_used) if hasattr(account, 'margin_used') and account.margin_used else None,
                }
            else:
                summary = {"account_id": account_id, "cash": None, "message": "Account not found"}

            return {
                "status": "success",
                "query_type": "summary",
                "data": summary,
                "timestamp": datetime.now().isoformat(),
            }

    except ImportError:
        return {
            "status": "success",
            "query_type": "summary",
            "data": {"account_id": account_id, "cash": None},
            "message": "Database not available",
        }
    except Exception as e:
        logger.error("Account summary query failed: %s", e)
        return {
            "status": "error",
            "error": f"Summary query failed: {str(e)}",
        }


async def _get_pnl(account_id: str, strategy_id: str | None) -> dict[str, Any]:
    """Get P&L breakdown."""
    try:
        async with get_redis_or_none() as client:
            if client is None:
                return {
                    "status": "success",
                    "query_type": "pnl",
                    "data": {"realized": None, "unrealized": None},
                    "message": "Redis not available",
                }

            pnl_key = f"pnl:{account_id}"
            if strategy_id:
                pnl_key = f"pnl:{account_id}:{strategy_id}"

            pnl_data = await client.get(pnl_key)

            if pnl_data:
                return {
                    "status": "success",
                    "query_type": "pnl",
                    "data": json.loads(pnl_data),
                    "timestamp": datetime.now().isoformat(),
                }

            return {
                "status": "success",
                "query_type": "pnl",
                "data": {
                    "realized": None,
                    "unrealized": None,
                    "day_pnl": None,
                },
                "message": "P&L data not available in cache",
            }

    except Exception as e:
        return {
            "status": "error",
            "error": f"P&L query failed: {str(e)}",
        }


async def get_greeks_exposure(
    underlying: str | None = None,
) -> dict[str, Any]:
    """Get aggregated Greeks exposure data for the portfolio.

    Args:
        underlying: Optional underlying symbol to filter by

    Returns:
        Dictionary containing aggregated Greeks exposure data.

    Example:
        >>> result = await get_greeks_exposure()
        >>> result["status"]
        'success'
    """
    try:
        async with get_redis_or_none() as client:
            if client is None:
                return {
                    "status": "success",
                    "query_type": "greeks",
                    "data": {"delta": None, "gamma": None, "theta": None, "vega": None},
                    "message": "Redis not available",
                }

            # Get aggregated Greeks from Redis cache
            greeks_key = "greeks:portfolio"
            if underlying:
                greeks_key = f"greeks:{underlying}"

            greeks_data = await client.get(greeks_key)

            if greeks_data:
                return {
                    "status": "success",
                    "query_type": "greeks",
                    "underlying_filter": underlying,
                    "data": json.loads(greeks_data),
                    "timestamp": datetime.now().isoformat(),
                }

            return {
                "status": "success",
                "query_type": "greeks",
                "data": {
                    "delta": None,
                    "gamma": None,
                    "theta": None,
                    "vega": None,
                },
                "message": "Greeks data not available in cache",
            }

    except Exception as e:
        logger.error("Greeks query failed: %s", e)
        return {
            "status": "error",
            "error": f"Greeks query failed: {str(e)}",
        }


def create_portfolio_tool() -> Tool:
    """Create and return the portfolio tool.

    Returns:
        Tool instance configured for portfolio queries.

    The tool requires the following permissions:
    - portfolio/*: Read portfolio data
    """
    return Tool(
        name="portfolio",
        description="Read-only access to portfolio data including positions, "
        "summary, P&L, and exposure. Use query_type to specify what data to retrieve.",
        execute=query_portfolio,
        required_permissions=["portfolio/*"],
    )


def create_greeks_tool() -> Tool:
    """Create and return the Greeks exposure tool.

    Returns:
        Tool instance configured for Greeks queries.

    The tool requires the following permissions:
    - portfolio/*: Read portfolio data
    - risk/*: Read risk metrics
    """
    return Tool(
        name="greeks",
        description="Get Greeks exposure data (delta, gamma, theta, vega) "
        "for the portfolio. Can filter by underlying and aggregate or show by position.",
        execute=get_greeks_exposure,
        required_permissions=["portfolio/*", "risk/*"],
    )
