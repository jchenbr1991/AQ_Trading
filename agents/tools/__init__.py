# Agent Tools Module
# Contains tools that AI agents can use for trading operations
"""Agent tools for AQ Trading.

This module provides tools that agents can use to interact with
various trading system components. Each tool is a wrapper around
specific operations with defined permissions.

Tools:
- backtest: Run backtests on trading strategies (T024)
- market_data: Query historical and live market data (T025)
- portfolio: Read-only portfolio and position access (T026)
- redis_writer: Write to allowed Redis keys only (T027)
- reconciliation: Query and compare broker positions (T028)

Usage:
    from agents.tools import (
        create_backtest_tool,
        create_market_data_tool,
        create_portfolio_tool,
        create_redis_writer_tool,
        create_reconciliation_tool,
    )

    # Create tools for an agent
    backtest_tool = create_backtest_tool()
    agent.register_tool(backtest_tool)
"""

# T024: Backtest tool
from agents.tools.backtest import (
    run_backtest,
    create_backtest_tool,
)

# T025: Market data tool
from agents.tools.market_data import (
    query_market_data,
    get_vix_metrics,
    create_market_data_tool,
    create_vix_tool,
)

# T026: Portfolio tool
from agents.tools.portfolio import (
    query_portfolio,
    get_greeks_exposure,
    create_portfolio_tool,
    create_greeks_tool,
)

# T027: Redis writer tool
from agents.tools.redis_writer import (
    write_redis,
    write_risk_bias,
    write_sentiment,
    validate_key_prefix,
    create_redis_writer_tool,
    create_risk_bias_tool,
    create_sentiment_tool,
    ALLOWED_KEY_PREFIXES,
)

# T028: Reconciliation tool
from agents.tools.reconciliation import (
    query_broker_positions,
    get_local_positions,
    run_reconciliation,
    analyze_discrepancies,
    create_reconciliation_tool,
    create_broker_positions_tool,
    create_discrepancy_analysis_tool,
)

__all__ = [
    # T024: Backtest
    "run_backtest",
    "create_backtest_tool",
    # T025: Market data
    "query_market_data",
    "get_vix_metrics",
    "create_market_data_tool",
    "create_vix_tool",
    # T026: Portfolio
    "query_portfolio",
    "get_greeks_exposure",
    "create_portfolio_tool",
    "create_greeks_tool",
    # T027: Redis writer
    "write_redis",
    "write_risk_bias",
    "write_sentiment",
    "validate_key_prefix",
    "create_redis_writer_tool",
    "create_risk_bias_tool",
    "create_sentiment_tool",
    "ALLOWED_KEY_PREFIXES",
    # T028: Reconciliation
    "query_broker_positions",
    "get_local_positions",
    "run_reconciliation",
    "analyze_discrepancies",
    "create_reconciliation_tool",
    "create_broker_positions_tool",
    "create_discrepancy_analysis_tool",
]
