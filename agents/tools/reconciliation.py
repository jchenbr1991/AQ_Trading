# AQ Trading AI Agents - Reconciliation Tool
# T028: Query broker positions and compare with local
"""Reconciliation tool for AI agents.

This tool provides access to the reconciliation service for
comparing local positions with broker positions and identifying
discrepancies.

Usage:
    tool = create_reconciliation_tool()
    result = await tool.execute()
"""

import json
import logging
from datetime import datetime
from typing import Any, Literal

from agents.base import Tool
from agents.connections import get_db_session_or_none, get_redis_or_none

logger = logging.getLogger(__name__)

DiscrepancyType = Literal["missing_local", "missing_broker", "quantity_mismatch"]


async def get_cached_broker_positions() -> dict[str, Any]:
    """Get broker positions from Redis cache.

    NOTE: This reads from a Redis cache that should be populated
    by a separate broker sync service. The data may be stale.
    Check the 'timestamp' field to verify data freshness.

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - positions: List of broker positions from cache
        - timestamp: When data was last synced to cache
        - source: Always 'cache' to indicate data source
        - error: Error message if status is 'error'

    Example:
        >>> result = await get_cached_broker_positions()
        >>> result["status"]
        'success'
        >>> result["source"]
        'cache'
    """
    try:
        async with get_redis_or_none() as client:
            if client is None:
                # Return error when Redis is unavailable to prevent false discrepancies
                return {
                    "status": "error",
                    "positions": [],
                    "source": "cache",
                    "error": "Redis not available - cannot verify broker positions",
                }

            positions_data = await client.get("broker:positions")

            if positions_data:
                positions = json.loads(positions_data)
                return {
                    "status": "success",
                    "positions": positions.get("positions", []),
                    "timestamp": positions.get("timestamp"),
                    "source": "cache",
                }

            # Cache key doesn't exist - broker sync hasn't run or cache expired
            # Return error to prevent false discrepancies
            return {
                "status": "error",
                "positions": [],
                "source": "cache",
                "error": "Broker position cache not populated - sync may not have run",
            }

    except Exception as e:
        logger.error("Broker position cache query failed: %s", e)
        return {
            "status": "error",
            "error": f"Query failed: {str(e)}",
            "source": "cache",
        }


# Alias for backward compatibility
query_broker_positions = get_cached_broker_positions


async def get_local_positions(account_id: str = "default") -> dict[str, Any]:
    """Get current positions from local database.

    Args:
        account_id: Account ID to query positions for

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - positions: List of local positions
        - timestamp: When data was retrieved
        - error: Error message if status is 'error'

    Example:
        >>> result = await get_local_positions()
        >>> result["status"]
        'success'
    """
    try:
        from sqlalchemy import select
        from src.models.position import Position

        async with get_db_session_or_none() as session:
            if session is None:
                # Return error when DB is unavailable to prevent false discrepancies
                return {
                    "status": "error",
                    "positions": [],
                    "count": 0,
                    "error": "Database not available - cannot verify local positions",
                }

            stmt = select(Position).where(Position.account_id == account_id)
            result = await session.execute(stmt)
            positions = result.scalars().all()

            position_list = [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_cost": str(p.avg_cost) if p.avg_cost else None,
                }
                for p in positions
            ]

            return {
                "status": "success",
                "positions": position_list,
                "count": len(position_list),
                "timestamp": datetime.now().isoformat(),
            }

    except ImportError:
        # Return error when DB dependencies not available
        return {
            "status": "error",
            "positions": [],
            "count": 0,
            "error": "Database dependencies not available",
        }
    except Exception as e:
        logger.error("Local position query failed: %s", e)
        return {
            "status": "error",
            "error": f"Query failed: {str(e)}",
        }


async def run_reconciliation(account_id: str = "default") -> dict[str, Any]:
    """Run full reconciliation between local and broker positions.

    Compares local positions with broker positions and identifies
    any discrepancies.

    Args:
        account_id: Account ID to reconcile

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - is_reconciled: True if positions match
        - discrepancies: List of discrepancy records
        - local_positions: Summary of local positions
        - broker_positions: Summary of broker positions
        - timestamp: When reconciliation was performed
        - error: Error message if status is 'error'

    Each discrepancy contains:
        - symbol: The affected symbol
        - type: 'missing_local', 'missing_broker', 'quantity_mismatch'
        - local_value: Value from local system (if any)
        - broker_value: Value from broker (if any)
        - severity: 'low', 'medium', 'high', 'critical'

    Example:
        >>> result = await run_reconciliation()
        >>> result["status"]
        'success'
    """
    try:
        # Get positions from both sources
        local_result = await get_local_positions(account_id)
        broker_result = await query_broker_positions()

        if local_result["status"] == "error":
            return local_result
        if broker_result["status"] == "error":
            return broker_result

        local_positions = {p["symbol"]: p for p in local_result.get("positions", [])}
        broker_positions = {p["symbol"]: p for p in broker_result.get("positions", [])}

        discrepancies = []
        all_symbols = set(local_positions.keys()) | set(broker_positions.keys())

        for symbol in all_symbols:
            local = local_positions.get(symbol)
            broker = broker_positions.get(symbol)

            if local and not broker:
                discrepancies.append({
                    "symbol": symbol,
                    "type": "missing_broker",
                    "local_value": local.get("quantity"),
                    "broker_value": None,
                    "severity": "high",
                    "description": f"Position exists locally but not at broker",
                })
            elif broker and not local:
                discrepancies.append({
                    "symbol": symbol,
                    "type": "missing_local",
                    "local_value": None,
                    "broker_value": broker.get("quantity"),
                    "severity": "high",
                    "description": f"Position exists at broker but not locally",
                })
            elif local and broker:
                local_qty = local.get("quantity", 0)
                broker_qty = broker.get("quantity", 0)
                if local_qty != broker_qty:
                    diff = abs(local_qty - broker_qty)
                    severity = "low" if diff <= 10 else "medium" if diff <= 100 else "high"
                    discrepancies.append({
                        "symbol": symbol,
                        "type": "quantity_mismatch",
                        "local_value": local_qty,
                        "broker_value": broker_qty,
                        "difference": diff,
                        "severity": severity,
                        "description": f"Quantity mismatch: local={local_qty}, broker={broker_qty}",
                    })

        is_reconciled = len(discrepancies) == 0

        logger.info(
            "Reconciliation complete: is_reconciled=%s, discrepancies=%d",
            is_reconciled,
            len(discrepancies),
        )

        return {
            "status": "success",
            "is_reconciled": is_reconciled,
            "discrepancies": discrepancies,
            "discrepancy_count": len(discrepancies),
            "local_positions": {
                "count": len(local_positions),
                "symbols": list(local_positions.keys()),
            },
            "broker_positions": {
                "count": len(broker_positions),
                "symbols": list(broker_positions.keys()),
            },
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Reconciliation failed: %s", e)
        return {
            "status": "error",
            "error": f"Reconciliation failed: {str(e)}",
        }


async def analyze_discrepancies(
    discrepancies: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Analyze reconciliation discrepancies and provide recommendations.

    Args:
        discrepancies: Optional list of discrepancies to analyze.
                      If None, runs fresh reconciliation first.

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - analysis: Detailed analysis of discrepancies
        - recommendations: Suggested actions for each discrepancy
        - risk_assessment: Overall risk level
        - error: Error message if status is 'error'

    Example:
        >>> result = await analyze_discrepancies()
        >>> result["status"]
        'success'
    """
    try:
        # If no discrepancies provided, run fresh reconciliation
        if discrepancies is None:
            recon_result = await run_reconciliation()
            if recon_result["status"] == "error":
                return recon_result
            discrepancies = recon_result.get("discrepancies", [])

        if not discrepancies:
            return {
                "status": "success",
                "analysis": {
                    "total_discrepancies": 0,
                    "message": "No discrepancies found",
                },
                "recommendations": [],
                "risk_assessment": {
                    "level": "low",
                    "factors": [],
                },
            }

        # Analyze discrepancies
        by_type = {}
        by_severity = {}
        affected_symbols = []

        for d in discrepancies:
            disc_type = d.get("type", "unknown")
            severity = d.get("severity", "unknown")
            symbol = d.get("symbol")

            by_type[disc_type] = by_type.get(disc_type, 0) + 1
            by_severity[severity] = by_severity.get(severity, 0) + 1
            if symbol:
                affected_symbols.append(symbol)

        # Generate recommendations
        recommendations = []
        for d in discrepancies:
            disc_type = d.get("type")
            symbol = d.get("symbol")

            if disc_type == "missing_broker":
                recommendations.append({
                    "symbol": symbol,
                    "action": "verify_broker_sync",
                    "description": f"Verify if {symbol} was sold externally or if sync failed",
                    "priority": "high",
                })
            elif disc_type == "missing_local":
                recommendations.append({
                    "symbol": symbol,
                    "action": "sync_from_broker",
                    "description": f"Sync {symbol} position from broker to local database",
                    "priority": "high",
                })
            elif disc_type == "quantity_mismatch":
                recommendations.append({
                    "symbol": symbol,
                    "action": "investigate_fills",
                    "description": f"Check order fill history for {symbol} - possible missed fill",
                    "priority": "medium",
                })

        # Assess overall risk
        risk_factors = []
        if by_severity.get("critical", 0) > 0:
            risk_level = "critical"
            risk_factors.append("Critical discrepancies found")
        elif by_severity.get("high", 0) > 0:
            risk_level = "high"
            risk_factors.append("High severity discrepancies found")
        elif by_severity.get("medium", 0) > 0:
            risk_level = "medium"
            risk_factors.append("Medium severity discrepancies found")
        else:
            risk_level = "low"

        if by_type.get("missing_local", 0) > 0:
            risk_factors.append("Positions missing from local database")
        if by_type.get("missing_broker", 0) > 0:
            risk_factors.append("Positions not reflected at broker")

        return {
            "status": "success",
            "analysis": {
                "total_discrepancies": len(discrepancies),
                "by_type": by_type,
                "by_severity": by_severity,
                "affected_symbols": affected_symbols,
            },
            "recommendations": recommendations,
            "risk_assessment": {
                "level": risk_level,
                "factors": risk_factors,
            },
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error("Discrepancy analysis failed: %s", e)
        return {
            "status": "error",
            "error": f"Analysis failed: {str(e)}",
        }


def create_reconciliation_tool() -> Tool:
    """Create and return the reconciliation tool.

    Returns:
        Tool instance configured for reconciliation operations.

    The tool requires the following permissions:
    - reconciliation/*: Access reconciliation service
    - broker/*: Query broker positions
    """
    return Tool(
        name="reconciliation",
        description="Run reconciliation between local and broker positions. "
        "Identifies discrepancies in quantities and missing positions.",
        execute=run_reconciliation,
        required_permissions=["reconciliation/*", "broker/*"],
    )


def create_broker_positions_tool() -> Tool:
    """Create and return the broker positions cache query tool.

    Returns:
        Tool instance configured for cached broker position queries.

    NOTE: This tool reads from Redis cache, not directly from the broker.
    The cache is populated by a separate broker sync service.

    The tool requires the following permissions:
    - broker/*: Read cached broker data
    """
    return Tool(
        name="broker_positions",
        description="Query cached broker positions from Redis. "
        "NOTE: This reads from cache, not live broker API. Check timestamp for freshness.",
        execute=query_broker_positions,
        required_permissions=["broker/*"],
    )


def create_discrepancy_analysis_tool() -> Tool:
    """Create and return the discrepancy analysis tool.

    Returns:
        Tool instance configured for discrepancy analysis.

    The tool requires the following permissions:
    - reconciliation/*: Access reconciliation data
    """
    return Tool(
        name="discrepancy_analysis",
        description="Analyze reconciliation discrepancies and provide "
        "recommendations for resolution. Used by Ops agent for investigation.",
        execute=analyze_discrepancies,
        required_permissions=["reconciliation/*"],
    )
