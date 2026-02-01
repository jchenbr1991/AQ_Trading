"""
Unit tests for the agent permission model.

Tests cover:
- ToolPermission pattern matching
- RolePermissions read/write/execute checks
- PermissionChecker validation
- Default permissions from STRATEGY.md
"""

import pytest

from agents.permissions import (
    AgentRole,
    DEFAULT_PERMISSIONS,
    PermissionChecker,
    RolePermissions,
    ToolPermission,
)


class TestToolPermission:
    """Tests for ToolPermission dataclass."""

    def test_matches_exact_pattern(self):
        """ToolPermission matches exact pattern."""
        perm = ToolPermission(tool_name="backtest", allowed_patterns=["^momentum$"])
        assert perm.matches("momentum") is True
        assert perm.matches("momentum_v2") is False

    def test_matches_wildcard_pattern(self):
        """ToolPermission matches wildcard patterns."""
        perm = ToolPermission(tool_name="read", allowed_patterns=["^strategies/.*$"])
        assert perm.matches("strategies/momentum.py") is True
        assert perm.matches("strategies/examples/test.py") is True
        assert perm.matches("core/portfolio.py") is False

    def test_matches_empty_patterns(self):
        """ToolPermission with no patterns matches nothing."""
        perm = ToolPermission(tool_name="forbidden")
        assert perm.matches("anything") is False

    def test_matches_multiple_patterns(self):
        """ToolPermission matches if any pattern matches."""
        perm = ToolPermission(
            tool_name="read",
            allowed_patterns=["^logs/.*$", "^reports/.*$"]
        )
        assert perm.matches("logs/app.log") is True
        assert perm.matches("reports/daily.pdf") is True
        assert perm.matches("data/prices.csv") is False

    def test_immutable(self):
        """ToolPermission is immutable (frozen dataclass)."""
        perm = ToolPermission(tool_name="test", allowed_patterns=["^test$"])
        with pytest.raises(AttributeError):
            perm.tool_name = "changed"


class TestRolePermissions:
    """Tests for RolePermissions dataclass."""

    def test_can_read_resource_simple(self):
        """RolePermissions.can_read_resource with simple pattern."""
        perms = RolePermissions(
            role=AgentRole.RESEARCHER,
            can_read=["strategies/*"]
        )
        assert perms.can_read_resource("strategies/momentum.py") is True
        # Note: * matches zero or more characters, so strategies/ matches
        assert perms.can_read_resource("strategies/") is True
        assert perms.can_read_resource("core/risk.py") is False

    def test_can_read_resource_recursive(self):
        """RolePermissions.can_read_resource with ** pattern."""
        perms = RolePermissions(
            role=AgentRole.RESEARCHER,
            can_read=["strategies/**"]
        )
        assert perms.can_read_resource("strategies/momentum.py") is True
        assert perms.can_read_resource("strategies/examples/test.py") is True
        assert perms.can_read_resource("strategies/live/prod/algo.py") is True

    def test_can_write_resource_redis(self):
        """RolePermissions.can_write_resource for Redis keys."""
        perms = RolePermissions(
            role=AgentRole.ANALYST,
            can_write=["redis:sentiment:*"]
        )
        assert perms.can_write_resource("redis:sentiment:AAPL") is True
        assert perms.can_write_resource("redis:sentiment:SPY") is True
        assert perms.can_write_resource("redis:risk_bias") is False

    def test_can_write_resource_exact(self):
        """RolePermissions.can_write_resource with exact match."""
        perms = RolePermissions(
            role=AgentRole.RISK_CONTROLLER,
            can_write=["redis:risk_bias"]
        )
        assert perms.can_write_resource("redis:risk_bias") is True
        assert perms.can_write_resource("redis:risk_bias_old") is False

    def test_can_execute_tool(self):
        """RolePermissions.can_execute_tool checks tool list."""
        perms = RolePermissions(
            role=AgentRole.RESEARCHER,
            can_execute=["backtest", "pytest"]
        )
        assert perms.can_execute_tool("backtest") is True
        assert perms.can_execute_tool("pytest") is True
        assert perms.can_execute_tool("docker") is False

    def test_empty_permissions(self):
        """RolePermissions with empty lists denies all."""
        perms = RolePermissions(role=AgentRole.ANALYST)
        assert perms.can_read_resource("anything") is False
        assert perms.can_write_resource("anything") is False
        assert perms.can_execute_tool("anything") is False

    def test_immutable(self):
        """RolePermissions is immutable (frozen dataclass)."""
        perms = RolePermissions(role=AgentRole.ANALYST)
        with pytest.raises(AttributeError):
            perms.role = AgentRole.OPS


class TestPermissionChecker:
    """Tests for PermissionChecker class."""

    def test_init_with_default_permissions(self):
        """PermissionChecker uses DEFAULT_PERMISSIONS when none provided."""
        checker = PermissionChecker()
        # Should have all default roles
        assert checker.get_permissions(AgentRole.RESEARCHER) is not None
        assert checker.get_permissions(AgentRole.ANALYST) is not None
        assert checker.get_permissions(AgentRole.RISK_CONTROLLER) is not None
        assert checker.get_permissions(AgentRole.OPS) is not None

    def test_init_with_custom_permissions(self):
        """PermissionChecker accepts custom permission mapping."""
        custom_perms = {
            AgentRole.RESEARCHER: RolePermissions(
                role=AgentRole.RESEARCHER,
                can_read=["custom/*"]
            )
        }
        checker = PermissionChecker(permissions=custom_perms)
        assert checker.can_read(AgentRole.RESEARCHER, "custom/file.txt") is True
        assert checker.can_read(AgentRole.RESEARCHER, "strategies/file.txt") is False

    def test_get_permissions_unknown_role(self):
        """PermissionChecker.get_permissions raises KeyError for unknown role."""
        checker = PermissionChecker(permissions={})
        with pytest.raises(KeyError):
            checker.get_permissions(AgentRole.RESEARCHER)

    def test_can_read(self):
        """PermissionChecker.can_read delegates to RolePermissions."""
        checker = PermissionChecker()
        # Researcher can read strategies
        assert checker.can_read(AgentRole.RESEARCHER, "strategies/momentum.py") is True
        # Analyst cannot read strategies
        assert checker.can_read(AgentRole.ANALYST, "strategies/momentum.py") is False

    def test_can_read_unknown_role(self):
        """PermissionChecker.can_read returns False for unknown role."""
        checker = PermissionChecker(permissions={})
        assert checker.can_read(AgentRole.RESEARCHER, "anything") is False

    def test_can_write(self):
        """PermissionChecker.can_write delegates to RolePermissions."""
        checker = PermissionChecker()
        # Analyst can write sentiment
        assert checker.can_write(AgentRole.ANALYST, "redis:sentiment:AAPL") is True
        # Researcher cannot write sentiment
        assert checker.can_write(AgentRole.RESEARCHER, "redis:sentiment:AAPL") is False

    def test_can_write_unknown_role(self):
        """PermissionChecker.can_write returns False for unknown role."""
        checker = PermissionChecker(permissions={})
        assert checker.can_write(AgentRole.ANALYST, "anything") is False

    def test_validate_tool_call_execute_allowed(self):
        """PermissionChecker.validate_tool_call allows permitted tools."""
        checker = PermissionChecker()
        # Researcher can execute backtest
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "backtest", {"strategy": "momentum"}
        ) is True

    def test_validate_tool_call_execute_denied(self):
        """PermissionChecker.validate_tool_call denies unpermitted tools."""
        checker = PermissionChecker()
        # Analyst cannot execute backtest
        assert checker.validate_tool_call(
            AgentRole.ANALYST, "backtest", {}
        ) is False

    def test_validate_tool_call_read_file(self):
        """PermissionChecker.validate_tool_call checks read permissions for read tool."""
        checker = PermissionChecker()
        # Researcher can read strategies
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "read", {"path": "strategies/momentum.py"}
        ) is True
        # Analyst cannot read strategies
        assert checker.validate_tool_call(
            AgentRole.ANALYST, "read", {"path": "strategies/momentum.py"}
        ) is False

    def test_validate_tool_call_write_file(self):
        """PermissionChecker.validate_tool_call checks write permissions for write tool."""
        checker = PermissionChecker()
        # Researcher can write to examples
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "write", {"path": "strategies/examples/test.py"}
        ) is True
        # Researcher cannot write to live
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "write", {"path": "strategies/live/prod.py"}
        ) is False

    def test_validate_tool_call_redis_write(self):
        """PermissionChecker.validate_tool_call checks Redis write permissions."""
        checker = PermissionChecker()
        # Analyst can write sentiment
        assert checker.validate_tool_call(
            AgentRole.ANALYST, "redis_write", {"key": "sentiment:AAPL"}
        ) is True
        # Analyst cannot write risk_bias
        assert checker.validate_tool_call(
            AgentRole.ANALYST, "redis_write", {"key": "risk_bias"}
        ) is False
        # RiskController can write risk_bias
        assert checker.validate_tool_call(
            AgentRole.RISK_CONTROLLER, "redis_write", {"key": "risk_bias"}
        ) is True

    def test_validate_tool_call_with_resource_args(self):
        """PermissionChecker.validate_tool_call checks resource args for allowed tools."""
        checker = PermissionChecker()
        # Researcher can execute backtest with valid read path
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "backtest",
            {"read_path": "strategies/momentum.py"}
        ) is True
        # Researcher cannot execute backtest with invalid read path
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "backtest",
            {"read_path": "broker/api.py"}
        ) is False

    def test_validate_tool_call_unknown_role(self):
        """PermissionChecker.validate_tool_call returns False for unknown role."""
        checker = PermissionChecker(permissions={})
        assert checker.validate_tool_call(AgentRole.RESEARCHER, "backtest", {}) is False

    def test_get_blocked_reason_read(self):
        """PermissionChecker.get_blocked_reason explains read denial."""
        checker = PermissionChecker()
        reason = checker.get_blocked_reason(
            AgentRole.ANALYST, "read", "strategies/momentum.py"
        )
        assert reason is not None
        assert "Analyst" in reason or "analyst" in reason
        assert "cannot read" in reason

    def test_get_blocked_reason_write(self):
        """PermissionChecker.get_blocked_reason explains write denial."""
        checker = PermissionChecker()
        reason = checker.get_blocked_reason(
            AgentRole.RESEARCHER, "write", "redis:sentiment:AAPL"
        )
        assert reason is not None
        assert "cannot write" in reason

    def test_get_blocked_reason_execute(self):
        """PermissionChecker.get_blocked_reason explains execute denial."""
        checker = PermissionChecker()
        reason = checker.get_blocked_reason(
            AgentRole.ANALYST, "execute", "docker"
        )
        assert reason is not None
        assert "cannot execute" in reason

    def test_get_blocked_reason_allowed(self):
        """PermissionChecker.get_blocked_reason returns None when allowed."""
        checker = PermissionChecker()
        reason = checker.get_blocked_reason(
            AgentRole.RESEARCHER, "read", "strategies/momentum.py"
        )
        assert reason is None

    def test_get_blocked_reason_unknown_role(self):
        """PermissionChecker.get_blocked_reason handles unknown role."""
        checker = PermissionChecker(permissions={})
        reason = checker.get_blocked_reason(
            AgentRole.RESEARCHER, "read", "anything"
        )
        assert reason is not None
        assert "Unknown role" in reason

    def test_get_blocked_reason_unknown_operation(self):
        """PermissionChecker.get_blocked_reason handles unknown operation."""
        checker = PermissionChecker()
        reason = checker.get_blocked_reason(
            AgentRole.RESEARCHER, "delete", "anything"
        )
        assert reason is not None
        assert "Unknown operation" in reason


class TestDefaultPermissions:
    """Tests for DEFAULT_PERMISSIONS from STRATEGY.md."""

    def test_researcher_permissions(self):
        """Researcher has correct default permissions."""
        perms = DEFAULT_PERMISSIONS[AgentRole.RESEARCHER]
        assert perms.role == AgentRole.RESEARCHER

        # Can read strategies and backtest results
        assert perms.can_read_resource("strategies/momentum.py") is True
        assert perms.can_read_resource("backtest/results.json") is True
        assert perms.can_read_resource("logs/app.log") is True

        # Cannot read broker or order data
        assert perms.can_read_resource("broker/api.py") is False
        assert perms.can_read_resource("orders/pending.json") is False

        # Can write to examples and outputs
        assert perms.can_write_resource("strategies/examples/test.py") is True
        assert perms.can_write_resource("agents/outputs/report.md") is True

        # Cannot write to live strategies
        assert perms.can_write_resource("strategies/live/prod.py") is False

        # Can execute backtest and pytest
        assert perms.can_execute_tool("backtest") is True
        assert perms.can_execute_tool("pytest") is True
        assert perms.can_execute_tool("docker") is False

    def test_analyst_permissions(self):
        """Analyst has correct default permissions."""
        perms = DEFAULT_PERMISSIONS[AgentRole.ANALYST]
        assert perms.role == AgentRole.ANALYST

        # Can read market data and news
        assert perms.can_read_resource("market_data/AAPL.csv") is True
        assert perms.can_read_resource("news/headlines.json") is True

        # Cannot read strategies or orders
        assert perms.can_read_resource("strategies/momentum.py") is False
        assert perms.can_read_resource("orders/pending.json") is False

        # Can write sentiment and events to Redis
        assert perms.can_write_resource("redis:sentiment:AAPL") is True
        assert perms.can_write_resource("redis:events:earnings") is True

        # Cannot write risk bias
        assert perms.can_write_resource("redis:risk_bias") is False

        # Cannot execute any tools
        assert perms.can_execute_tool("backtest") is False
        assert perms.can_execute_tool("docker") is False

    def test_risk_controller_permissions(self):
        """RiskController has correct default permissions."""
        perms = DEFAULT_PERMISSIONS[AgentRole.RISK_CONTROLLER]
        assert perms.role == AgentRole.RISK_CONTROLLER

        # Can read portfolio, risk, and market data
        assert perms.can_read_resource("portfolio/positions.json") is True
        assert perms.can_read_resource("risk/limits.yaml") is True
        assert perms.can_read_resource("market_data/VIX.csv") is True

        # Cannot read strategies or orders
        assert perms.can_read_resource("strategies/momentum.py") is False
        assert perms.can_read_resource("broker/api.py") is False

        # Can write risk_bias to Redis
        assert perms.can_write_resource("redis:risk_bias") is True

        # Cannot write sentiment
        assert perms.can_write_resource("redis:sentiment:AAPL") is False

        # Cannot execute any tools
        assert perms.can_execute_tool("backtest") is False

    def test_ops_permissions(self):
        """Ops has correct default permissions."""
        perms = DEFAULT_PERMISSIONS[AgentRole.OPS]
        assert perms.role == AgentRole.OPS

        # Can read broker, reconciliation, logs, and health
        assert perms.can_read_resource("broker/status.json") is True
        assert perms.can_read_resource("reconciliation/report.json") is True
        assert perms.can_read_resource("logs/app.log") is True
        assert perms.can_read_resource("health/status.json") is True

        # Cannot read strategies (live)
        # Note: Ops reads all but cannot modify strategies/live
        assert perms.can_read_resource("strategies/live/prod.py") is False

        # Can write to logs and outputs
        assert perms.can_write_resource("logs/ops.log") is True
        assert perms.can_write_resource("agents/outputs/report.md") is True

        # Cannot write to Redis keys
        assert perms.can_write_resource("redis:risk_bias") is False

        # Can execute docker and systemctl
        assert perms.can_execute_tool("docker") is True
        assert perms.can_execute_tool("systemctl") is True
        assert perms.can_execute_tool("backtest") is False


class TestEdgeCases:
    """Edge case tests for permission model."""

    def test_pattern_with_special_characters(self):
        """Patterns with special regex characters are handled correctly."""
        perms = RolePermissions(
            role=AgentRole.RESEARCHER,
            can_read=["strategies/test.py"]  # . should be literal
        )
        assert perms.can_read_resource("strategies/test.py") is True
        assert perms.can_read_resource("strategies/testXpy") is False

    def test_empty_resource_string(self):
        """Empty resource string is handled correctly."""
        perms = RolePermissions(
            role=AgentRole.RESEARCHER,
            can_read=["strategies/*"]
        )
        assert perms.can_read_resource("") is False

    def test_pattern_anchoring(self):
        """Patterns are properly anchored to prevent partial matches."""
        perms = RolePermissions(
            role=AgentRole.ANALYST,
            can_write=["redis:sentiment:*"]
        )
        # Should not match if there's a prefix before the pattern
        assert perms.can_write_resource("prefix:redis:sentiment:AAPL") is False
        # Note: * matches any sequence without /, so AAPL:suffix matches *
        # If we want to prevent suffixes, we'd need to use a more specific pattern
        # For this test, verify that prefix matching is blocked (anchored at start)
        assert perms.can_write_resource("redis:sentiment:AAPL") is True

    def test_multiple_wildcards(self):
        """Multiple wildcards in pattern work correctly."""
        perms = RolePermissions(
            role=AgentRole.RESEARCHER,
            can_read=["data/*/processed/*"]
        )
        assert perms.can_read_resource("data/2024/processed/file.csv") is True
        assert perms.can_read_resource("data/2024/raw/file.csv") is False

    def test_validate_tool_with_read_path_key(self):
        """validate_tool_call handles different arg key names."""
        checker = PermissionChecker()
        # Using 'read_path'
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "read_file",
            {"read_path": "strategies/test.py"}
        ) is True
        # Using 'path'
        assert checker.validate_tool_call(
            AgentRole.RESEARCHER, "read_file",
            {"path": "strategies/test.py"}
        ) is True
