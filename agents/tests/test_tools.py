# AQ Trading AI Agents - Tool Tests
# Tests for T024-T028: Agent Tools
"""Tests for the agent tools module.

Tests cover:
- Tool creation and configuration
- Execute function signatures
- Key validation (redis_writer)
- Permission requirements
"""

import inspect
import pytest
from typing import Any

from agents.base import Tool

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


# ==============================================================================
# T024: Backtest Tool Tests
# ==============================================================================


class TestBacktestTool:
    """Tests for backtest tool (T024)."""

    def test_create_backtest_tool_returns_tool(self):
        """create_backtest_tool returns a Tool instance."""
        tool = create_backtest_tool()
        assert isinstance(tool, Tool)

    def test_backtest_tool_has_correct_name(self):
        """Backtest tool has name 'backtest'."""
        tool = create_backtest_tool()
        assert tool.name == "backtest"

    def test_backtest_tool_has_description(self):
        """Backtest tool has a non-empty description."""
        tool = create_backtest_tool()
        assert tool.description
        assert len(tool.description) > 10

    def test_backtest_tool_has_permissions(self):
        """Backtest tool requires backtest/* permission."""
        tool = create_backtest_tool()
        assert "backtest/*" in tool.required_permissions

    def test_run_backtest_is_async(self):
        """run_backtest is an async function."""
        assert inspect.iscoroutinefunction(run_backtest)

    @pytest.mark.asyncio
    async def test_run_backtest_with_strategy(self):
        """run_backtest returns structured response."""
        result = await run_backtest(strategy="momentum")
        assert result["status"] == "not_implemented"
        assert result["strategy"] == "momentum"

    @pytest.mark.asyncio
    async def test_run_backtest_without_strategy_returns_error(self):
        """run_backtest requires strategy parameter."""
        result = await run_backtest(strategy="")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_run_backtest_with_full_params(self):
        """run_backtest accepts all parameters."""
        result = await run_backtest(
            strategy="momentum",
            params={"lookback": 20},
            start_date="2024-01-01",
            end_date="2024-12-31",
        )
        assert result["strategy"] == "momentum"
        assert result["params"] == {"lookback": 20}
        assert result["period"]["start"] == "2024-01-01"
        assert result["period"]["end"] == "2024-12-31"


# ==============================================================================
# T025: Market Data Tool Tests
# ==============================================================================


class TestMarketDataTool:
    """Tests for market data tool (T025)."""

    def test_create_market_data_tool_returns_tool(self):
        """create_market_data_tool returns a Tool instance."""
        tool = create_market_data_tool()
        assert isinstance(tool, Tool)

    def test_market_data_tool_has_correct_name(self):
        """Market data tool has name 'market_data'."""
        tool = create_market_data_tool()
        assert tool.name == "market_data"

    def test_market_data_tool_has_permissions(self):
        """Market data tool requires market_data/* permission."""
        tool = create_market_data_tool()
        assert "market_data/*" in tool.required_permissions

    def test_create_vix_tool_returns_tool(self):
        """create_vix_tool returns a Tool instance."""
        tool = create_vix_tool()
        assert isinstance(tool, Tool)
        assert tool.name == "vix"

    def test_query_market_data_is_async(self):
        """query_market_data is an async function."""
        assert inspect.iscoroutinefunction(query_market_data)

    def test_get_vix_metrics_is_async(self):
        """get_vix_metrics is an async function."""
        assert inspect.iscoroutinefunction(get_vix_metrics)

    @pytest.mark.asyncio
    async def test_query_market_data_with_symbols(self):
        """query_market_data returns structured response."""
        result = await query_market_data(symbols=["AAPL", "SPY"])
        assert result["status"] == "not_implemented"
        assert result["symbols"] == ["AAPL", "SPY"]

    @pytest.mark.asyncio
    async def test_query_market_data_without_symbols_returns_error(self):
        """query_market_data requires symbols."""
        result = await query_market_data(symbols=[])
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_query_market_data_with_invalid_interval(self):
        """query_market_data validates interval."""
        result = await query_market_data(
            symbols=["AAPL"],
            interval="invalid",
        )
        assert result["status"] == "error"
        assert "interval" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_get_vix_metrics_returns_structure(self):
        """get_vix_metrics returns VIX data structure."""
        result = await get_vix_metrics()
        assert result["status"] == "not_implemented"
        assert "vix" in result
        assert "vix_futures" in result


# ==============================================================================
# T026: Portfolio Tool Tests
# ==============================================================================


class TestPortfolioTool:
    """Tests for portfolio tool (T026)."""

    def test_create_portfolio_tool_returns_tool(self):
        """create_portfolio_tool returns a Tool instance."""
        tool = create_portfolio_tool()
        assert isinstance(tool, Tool)

    def test_portfolio_tool_has_correct_name(self):
        """Portfolio tool has name 'portfolio'."""
        tool = create_portfolio_tool()
        assert tool.name == "portfolio"

    def test_portfolio_tool_has_permissions(self):
        """Portfolio tool requires portfolio/* permission."""
        tool = create_portfolio_tool()
        assert "portfolio/*" in tool.required_permissions

    def test_create_greeks_tool_returns_tool(self):
        """create_greeks_tool returns a Tool instance."""
        tool = create_greeks_tool()
        assert isinstance(tool, Tool)
        assert tool.name == "greeks"

    def test_greeks_tool_has_permissions(self):
        """Greeks tool requires portfolio and risk permissions."""
        tool = create_greeks_tool()
        assert "portfolio/*" in tool.required_permissions
        assert "risk/*" in tool.required_permissions

    def test_query_portfolio_is_async(self):
        """query_portfolio is an async function."""
        assert inspect.iscoroutinefunction(query_portfolio)

    @pytest.mark.asyncio
    async def test_query_portfolio_default(self):
        """query_portfolio returns structured response."""
        result = await query_portfolio()
        assert result["status"] == "not_implemented"
        assert result["query_type"] == "summary"

    @pytest.mark.asyncio
    async def test_query_portfolio_positions(self):
        """query_portfolio can query positions."""
        result = await query_portfolio(query_type="positions")
        assert result["query_type"] == "positions"
        assert "positions" in result["data"]

    @pytest.mark.asyncio
    async def test_query_portfolio_greeks(self):
        """query_portfolio can query Greeks."""
        result = await query_portfolio(query_type="greeks")
        assert result["query_type"] == "greeks"
        assert "portfolio_delta" in result["data"]

    @pytest.mark.asyncio
    async def test_get_greeks_exposure(self):
        """get_greeks_exposure returns Greeks data."""
        result = await get_greeks_exposure()
        assert result["status"] == "not_implemented"
        assert "greeks" in result


# ==============================================================================
# T027: Redis Writer Tool Tests
# ==============================================================================


class TestRedisWriterTool:
    """Tests for Redis writer tool (T027)."""

    def test_create_redis_writer_tool_returns_tool(self):
        """create_redis_writer_tool returns a Tool instance."""
        tool = create_redis_writer_tool()
        assert isinstance(tool, Tool)

    def test_redis_writer_tool_has_correct_name(self):
        """Redis writer tool has name 'redis_write'."""
        tool = create_redis_writer_tool()
        assert tool.name == "redis_write"

    def test_create_risk_bias_tool_returns_tool(self):
        """create_risk_bias_tool returns a Tool instance."""
        tool = create_risk_bias_tool()
        assert isinstance(tool, Tool)
        assert tool.name == "risk_bias"

    def test_create_sentiment_tool_returns_tool(self):
        """create_sentiment_tool returns a Tool instance."""
        tool = create_sentiment_tool()
        assert isinstance(tool, Tool)
        assert tool.name == "sentiment"

    def test_write_redis_is_async(self):
        """write_redis is an async function."""
        assert inspect.iscoroutinefunction(write_redis)

    def test_allowed_key_prefixes_defined(self):
        """ALLOWED_KEY_PREFIXES contains expected keys."""
        assert "risk_bias" in ALLOWED_KEY_PREFIXES
        assert "sentiment" in ALLOWED_KEY_PREFIXES

    def test_validate_key_prefix_allows_risk_bias(self):
        """validate_key_prefix allows risk_bias key."""
        assert validate_key_prefix("risk_bias") is True
        assert validate_key_prefix("risk_bias:extra") is True

    def test_validate_key_prefix_allows_sentiment(self):
        """validate_key_prefix allows sentiment keys."""
        assert validate_key_prefix("sentiment") is True
        assert validate_key_prefix("sentiment:AAPL") is True
        assert validate_key_prefix("sentiment:SPY:news") is True

    def test_validate_key_prefix_rejects_disallowed(self):
        """validate_key_prefix rejects disallowed keys."""
        assert validate_key_prefix("orders") is False
        assert validate_key_prefix("positions") is False
        assert validate_key_prefix("risk_biased") is False  # Not exact match
        assert validate_key_prefix("") is False

    @pytest.mark.asyncio
    async def test_write_redis_with_valid_key(self):
        """write_redis accepts valid key."""
        result = await write_redis(
            key="sentiment:AAPL",
            value={"score": 0.75},
        )
        assert result["status"] == "not_implemented"
        assert result["key"] == "sentiment:AAPL"

    @pytest.mark.asyncio
    async def test_write_redis_with_invalid_key(self):
        """write_redis rejects invalid key."""
        result = await write_redis(
            key="orders:12345",
            value={"quantity": 100},
        )
        assert result["status"] == "error"
        assert "not allowed" in result["error"]

    @pytest.mark.asyncio
    async def test_write_redis_with_empty_key(self):
        """write_redis requires key."""
        result = await write_redis(key="", value="test")
        assert result["status"] == "error"

    @pytest.mark.asyncio
    async def test_write_risk_bias(self):
        """write_risk_bias convenience function works."""
        result = await write_risk_bias(value=-0.5, reason="VIX elevated")
        assert result["status"] == "not_implemented"
        assert result["key"] == "risk_bias"

    @pytest.mark.asyncio
    async def test_write_sentiment(self):
        """write_sentiment convenience function works."""
        result = await write_sentiment(
            symbol="AAPL",
            score=0.8,
            source="news",
        )
        assert result["status"] == "not_implemented"
        assert result["key"] == "sentiment:AAPL"


# ==============================================================================
# T028: Reconciliation Tool Tests
# ==============================================================================


class TestReconciliationTool:
    """Tests for reconciliation tool (T028)."""

    def test_create_reconciliation_tool_returns_tool(self):
        """create_reconciliation_tool returns a Tool instance."""
        tool = create_reconciliation_tool()
        assert isinstance(tool, Tool)

    def test_reconciliation_tool_has_correct_name(self):
        """Reconciliation tool has name 'reconciliation'."""
        tool = create_reconciliation_tool()
        assert tool.name == "reconciliation"

    def test_reconciliation_tool_has_permissions(self):
        """Reconciliation tool requires correct permissions."""
        tool = create_reconciliation_tool()
        assert "reconciliation/*" in tool.required_permissions
        assert "broker/*" in tool.required_permissions

    def test_create_broker_positions_tool_returns_tool(self):
        """create_broker_positions_tool returns a Tool instance."""
        tool = create_broker_positions_tool()
        assert isinstance(tool, Tool)
        assert tool.name == "broker_positions"

    def test_create_discrepancy_analysis_tool_returns_tool(self):
        """create_discrepancy_analysis_tool returns a Tool instance."""
        tool = create_discrepancy_analysis_tool()
        assert isinstance(tool, Tool)
        assert tool.name == "discrepancy_analysis"

    def test_run_reconciliation_is_async(self):
        """run_reconciliation is an async function."""
        assert inspect.iscoroutinefunction(run_reconciliation)

    def test_query_broker_positions_is_async(self):
        """query_broker_positions is an async function."""
        assert inspect.iscoroutinefunction(query_broker_positions)

    @pytest.mark.asyncio
    async def test_run_reconciliation_returns_structure(self):
        """run_reconciliation returns expected structure."""
        result = await run_reconciliation()
        assert result["status"] == "not_implemented"
        assert "is_reconciled" in result
        assert "discrepancies" in result
        assert "local_positions" in result
        assert "broker_positions" in result

    @pytest.mark.asyncio
    async def test_query_broker_positions(self):
        """query_broker_positions returns broker data."""
        result = await query_broker_positions()
        assert result["status"] == "not_implemented"
        assert "positions" in result

    @pytest.mark.asyncio
    async def test_get_local_positions(self):
        """get_local_positions returns local data."""
        result = await get_local_positions()
        assert result["status"] == "not_implemented"
        assert "positions" in result

    @pytest.mark.asyncio
    async def test_analyze_discrepancies(self):
        """analyze_discrepancies returns analysis."""
        result = await analyze_discrepancies()
        assert result["status"] == "not_implemented"
        assert "analysis" in result
        assert "recommendations" in result
        assert "risk_assessment" in result


# ==============================================================================
# Cross-Tool Tests
# ==============================================================================


class TestAllTools:
    """Cross-cutting tests for all tools."""

    @pytest.fixture
    def all_tool_factories(self):
        """Return all tool factory functions."""
        return [
            create_backtest_tool,
            create_market_data_tool,
            create_vix_tool,
            create_portfolio_tool,
            create_greeks_tool,
            create_redis_writer_tool,
            create_risk_bias_tool,
            create_sentiment_tool,
            create_reconciliation_tool,
            create_broker_positions_tool,
            create_discrepancy_analysis_tool,
        ]

    def test_all_factories_return_tools(self, all_tool_factories):
        """All factory functions return Tool instances."""
        for factory in all_tool_factories:
            tool = factory()
            assert isinstance(tool, Tool), f"{factory.__name__} should return Tool"

    def test_all_tools_have_unique_names(self, all_tool_factories):
        """All tools have unique names."""
        names = [factory().name for factory in all_tool_factories]
        assert len(names) == len(set(names)), "Tool names must be unique"

    def test_all_tools_have_descriptions(self, all_tool_factories):
        """All tools have non-empty descriptions."""
        for factory in all_tool_factories:
            tool = factory()
            assert tool.description, f"{tool.name} should have description"
            assert len(tool.description) > 10, f"{tool.name} description too short"

    def test_all_tools_have_callable_execute(self, all_tool_factories):
        """All tools have callable execute functions."""
        for factory in all_tool_factories:
            tool = factory()
            assert callable(tool.execute), f"{tool.name} execute should be callable"

    def test_all_tools_have_permissions(self, all_tool_factories):
        """All tools have at least one permission."""
        for factory in all_tool_factories:
            tool = factory()
            assert tool.required_permissions, f"{tool.name} should have permissions"
