# AQ Trading AI Agents - Base Module Tests
"""Tests for the agent base classes and protocols.

Tests cover:
- Tool dataclass creation and validation
- AgentRole enum values
- PermissionChecker protocol
- BaseAgent abstract class functionality
- Tool registration and management
- Permission checking and enforcement
"""

import pytest
from typing import Any

from agents.base import (
    AgentRole,
    BaseAgent,
    PermissionChecker,
    PermissionError,
    Tool,
)


# ==============================================================================
# Test Fixtures and Helpers
# ==============================================================================


def dummy_execute(**kwargs: Any) -> dict[str, Any]:
    """A simple synchronous execute function for testing."""
    return {"executed": True, "kwargs": kwargs}


async def async_dummy_execute(**kwargs: Any) -> dict[str, Any]:
    """A simple async execute function for testing."""
    return {"executed": True, "async": True, "kwargs": kwargs}


class AllowAllPermissionChecker:
    """Permission checker that allows everything."""

    def has_permission(self, role: AgentRole, permission: str) -> bool:
        return True


class DenyAllPermissionChecker:
    """Permission checker that denies everything."""

    def has_permission(self, role: AgentRole, permission: str) -> bool:
        return False


class RoleBasedPermissionChecker:
    """Permission checker with role-based rules."""

    PERMISSIONS = {
        AgentRole.RESEARCHER: {
            "read:strategies",
            "execute:backtest",
            "write:candidates",
        },
        AgentRole.ANALYST: {
            "read:market_data",
            "write:sentiment",
        },
        AgentRole.RISK_CONTROLLER: {
            "read:portfolio",
            "read:risk",
            "write:risk_bias",
        },
        AgentRole.OPS: {
            "read:all",
            "execute:docker",
            "execute:systemctl",
        },
    }

    def has_permission(self, role: AgentRole, permission: str) -> bool:
        allowed = self.PERMISSIONS.get(role, set())
        return permission in allowed


class ConcreteAgent(BaseAgent):
    """Concrete implementation of BaseAgent for testing."""

    async def execute(self, task: str, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "result": f"Executed task: {task}",
            "context_keys": list(context.keys()),
        }


# ==============================================================================
# Tool Tests
# ==============================================================================


class TestTool:
    """Tests for Tool dataclass."""

    def test_create_tool_with_minimal_fields(self):
        """Tool can be created with required fields only."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            execute=dummy_execute,
        )

        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.execute == dummy_execute
        assert tool.required_permissions == []

    def test_create_tool_with_permissions(self):
        """Tool can be created with required permissions."""
        tool = Tool(
            name="backtest",
            description="Run strategy backtest",
            execute=dummy_execute,
            required_permissions=["read:strategies", "execute:backtest"],
        )

        assert tool.name == "backtest"
        assert tool.required_permissions == ["read:strategies", "execute:backtest"]

    def test_tool_is_frozen(self):
        """Tool is immutable (frozen dataclass)."""
        tool = Tool(
            name="test_tool",
            description="A test tool",
            execute=dummy_execute,
        )

        with pytest.raises(AttributeError):
            tool.name = "modified"  # type: ignore

    def test_tool_empty_name_raises_error(self):
        """Tool with empty name raises ValueError."""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            Tool(
                name="",
                description="A test tool",
                execute=dummy_execute,
            )

    def test_tool_empty_description_raises_error(self):
        """Tool with empty description raises ValueError."""
        with pytest.raises(ValueError, match="Tool description cannot be empty"):
            Tool(
                name="test_tool",
                description="",
                execute=dummy_execute,
            )

    def test_tool_non_callable_execute_raises_error(self):
        """Tool with non-callable execute raises ValueError."""
        with pytest.raises(ValueError, match="Tool execute must be callable"):
            Tool(
                name="test_tool",
                description="A test tool",
                execute="not a callable",  # type: ignore
            )


# ==============================================================================
# AgentRole Tests
# ==============================================================================


class TestAgentRole:
    """Tests for AgentRole enum."""

    def test_researcher_value(self):
        assert AgentRole.RESEARCHER.value == "researcher"

    def test_analyst_value(self):
        assert AgentRole.ANALYST.value == "analyst"

    def test_risk_controller_value(self):
        assert AgentRole.RISK_CONTROLLER.value == "risk_controller"

    def test_ops_value(self):
        assert AgentRole.OPS.value == "ops"

    def test_role_is_string_enum(self):
        """AgentRole values are strings."""
        assert isinstance(AgentRole.RESEARCHER.value, str)
        # String enum allows direct string comparison
        assert AgentRole.RESEARCHER == "researcher"


# ==============================================================================
# PermissionChecker Protocol Tests
# ==============================================================================


class TestPermissionChecker:
    """Tests for PermissionChecker protocol."""

    def test_allow_all_checker_implements_protocol(self):
        """AllowAllPermissionChecker implements PermissionChecker protocol."""
        checker = AllowAllPermissionChecker()
        assert isinstance(checker, PermissionChecker)

    def test_deny_all_checker_implements_protocol(self):
        """DenyAllPermissionChecker implements PermissionChecker protocol."""
        checker = DenyAllPermissionChecker()
        assert isinstance(checker, PermissionChecker)

    def test_role_based_checker_implements_protocol(self):
        """RoleBasedPermissionChecker implements PermissionChecker protocol."""
        checker = RoleBasedPermissionChecker()
        assert isinstance(checker, PermissionChecker)

    def test_allow_all_checker_returns_true(self):
        """AllowAllPermissionChecker always returns True."""
        checker = AllowAllPermissionChecker()
        assert checker.has_permission(AgentRole.RESEARCHER, "any:permission") is True
        assert checker.has_permission(AgentRole.OPS, "dangerous:action") is True

    def test_deny_all_checker_returns_false(self):
        """DenyAllPermissionChecker always returns False."""
        checker = DenyAllPermissionChecker()
        assert checker.has_permission(AgentRole.RESEARCHER, "any:permission") is False
        assert checker.has_permission(AgentRole.OPS, "read:all") is False

    def test_role_based_checker_allows_valid_permissions(self):
        """RoleBasedPermissionChecker allows defined permissions."""
        checker = RoleBasedPermissionChecker()
        assert (
            checker.has_permission(AgentRole.RESEARCHER, "read:strategies") is True
        )
        assert (
            checker.has_permission(AgentRole.ANALYST, "write:sentiment") is True
        )
        assert (
            checker.has_permission(AgentRole.RISK_CONTROLLER, "write:risk_bias") is True
        )

    def test_role_based_checker_denies_invalid_permissions(self):
        """RoleBasedPermissionChecker denies undefined permissions."""
        checker = RoleBasedPermissionChecker()
        # Researcher cannot write risk_bias
        assert (
            checker.has_permission(AgentRole.RESEARCHER, "write:risk_bias") is False
        )
        # Analyst cannot execute backtest
        assert (
            checker.has_permission(AgentRole.ANALYST, "execute:backtest") is False
        )


# ==============================================================================
# PermissionError Tests
# ==============================================================================


class TestPermissionError:
    """Tests for PermissionError exception."""

    def test_permission_error_with_defaults(self):
        """PermissionError can be created with role and permission."""
        error = PermissionError(
            role=AgentRole.RESEARCHER,
            permission="write:risk_bias",
        )

        assert error.role == AgentRole.RESEARCHER
        assert error.permission == "write:risk_bias"
        assert error.tool_name is None
        assert "researcher" in str(error)
        assert "write:risk_bias" in str(error)

    def test_permission_error_with_tool_name(self):
        """PermissionError includes tool name in message."""
        error = PermissionError(
            role=AgentRole.ANALYST,
            permission="execute:backtest",
            tool_name="backtest",
        )

        assert error.tool_name == "backtest"
        assert "backtest" in str(error)

    def test_permission_error_with_custom_message(self):
        """PermissionError can have a custom message."""
        error = PermissionError(
            role=AgentRole.OPS,
            permission="write:strategies",
            message="Custom error message",
        )

        assert str(error) == "Custom error message"


# ==============================================================================
# BaseAgent Tests
# ==============================================================================


class TestBaseAgentInit:
    """Tests for BaseAgent initialization."""

    def test_create_agent_with_role_only(self):
        """Agent can be created with just a role."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)

        assert agent.role == AgentRole.RESEARCHER
        assert agent.permission_checker is None
        assert agent.get_available_tools() == []

    def test_create_agent_with_tools(self):
        """Agent can be created with initial tools."""
        tool = Tool(
            name="test_tool",
            description="Test tool",
            execute=dummy_execute,
        )
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
        )

        assert agent.get_available_tools() == ["test_tool"]

    def test_create_agent_with_permission_checker(self):
        """Agent can be created with a permission checker."""
        checker = AllowAllPermissionChecker()
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            permission_checker=checker,
        )

        assert agent.permission_checker is checker

    def test_create_agent_with_invalid_role_raises_error(self):
        """Creating agent with invalid role raises ValueError."""
        with pytest.raises(ValueError, match="Invalid role"):
            ConcreteAgent(role="invalid")  # type: ignore


class TestBaseAgentToolManagement:
    """Tests for BaseAgent tool registration and management."""

    def test_register_tool(self):
        """Tool can be registered after agent creation."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)
        tool = Tool(
            name="new_tool",
            description="A new tool",
            execute=dummy_execute,
        )

        agent.register_tool(tool)

        assert "new_tool" in agent.get_available_tools()
        assert agent.get_tool("new_tool") == tool

    def test_register_duplicate_tool_raises_error(self):
        """Registering a tool with duplicate name raises ValueError."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)
        tool = Tool(
            name="duplicate",
            description="First tool",
            execute=dummy_execute,
        )
        agent.register_tool(tool)

        duplicate = Tool(
            name="duplicate",
            description="Second tool",
            execute=dummy_execute,
        )

        with pytest.raises(ValueError, match="already registered"):
            agent.register_tool(duplicate)

    def test_register_non_tool_raises_error(self):
        """Registering a non-Tool object raises TypeError."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)

        with pytest.raises(TypeError, match="Expected Tool instance"):
            agent.register_tool({"name": "not a tool"})  # type: ignore

    def test_unregister_tool(self):
        """Tool can be unregistered."""
        tool = Tool(
            name="removable",
            description="A removable tool",
            execute=dummy_execute,
        )
        agent = ConcreteAgent(role=AgentRole.RESEARCHER, tools=[tool])

        agent.unregister_tool("removable")

        assert "removable" not in agent.get_available_tools()
        assert agent.get_tool("removable") is None

    def test_unregister_nonexistent_tool_raises_error(self):
        """Unregistering a non-existent tool raises KeyError."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)

        with pytest.raises(KeyError, match="not registered"):
            agent.unregister_tool("nonexistent")

    def test_get_tool_returns_none_for_unknown(self):
        """get_tool returns None for unknown tool name."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)
        assert agent.get_tool("unknown") is None

    def test_get_available_tools_returns_all_registered(self):
        """get_available_tools returns all registered tool names."""
        tools = [
            Tool(name="tool1", description="Tool 1", execute=dummy_execute),
            Tool(name="tool2", description="Tool 2", execute=dummy_execute),
            Tool(name="tool3", description="Tool 3", execute=dummy_execute),
        ]
        agent = ConcreteAgent(role=AgentRole.RESEARCHER, tools=tools)

        available = agent.get_available_tools()

        assert set(available) == {"tool1", "tool2", "tool3"}


class TestBaseAgentCallTool:
    """Tests for BaseAgent tool calling with permissions."""

    def test_call_tool_without_permission_checker(self):
        """Tool can be called when no permission checker is set."""
        tool = Tool(
            name="unrestricted",
            description="Unrestricted tool",
            execute=dummy_execute,
            required_permissions=["some:permission"],
        )
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
            permission_checker=None,
        )

        result = agent.call_tool("unrestricted", arg1="value1")

        assert result["executed"] is True
        assert result["kwargs"] == {"arg1": "value1"}

    def test_call_tool_with_allowed_permission(self):
        """Tool can be called when permission is granted."""
        tool = Tool(
            name="allowed",
            description="Allowed tool",
            execute=dummy_execute,
            required_permissions=["read:strategies"],
        )
        checker = RoleBasedPermissionChecker()
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
            permission_checker=checker,
        )

        result = agent.call_tool("allowed")

        assert result["executed"] is True

    def test_call_tool_with_denied_permission_raises_error(self):
        """Tool call raises PermissionError when permission is denied."""
        tool = Tool(
            name="denied",
            description="Denied tool",
            execute=dummy_execute,
            required_permissions=["write:risk_bias"],  # Researcher can't do this
        )
        checker = RoleBasedPermissionChecker()
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
            permission_checker=checker,
        )

        with pytest.raises(PermissionError) as exc_info:
            agent.call_tool("denied")

        assert exc_info.value.role == AgentRole.RESEARCHER
        assert exc_info.value.permission == "write:risk_bias"
        assert exc_info.value.tool_name == "denied"

    def test_call_tool_checks_all_permissions(self):
        """Tool call checks all required permissions."""
        tool = Tool(
            name="multi_perm",
            description="Multi-permission tool",
            execute=dummy_execute,
            required_permissions=[
                "read:strategies",  # Researcher has this
                "write:risk_bias",  # Researcher does NOT have this
            ],
        )
        checker = RoleBasedPermissionChecker()
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
            permission_checker=checker,
        )

        with pytest.raises(PermissionError) as exc_info:
            agent.call_tool("multi_perm")

        assert exc_info.value.permission == "write:risk_bias"

    def test_call_unknown_tool_raises_key_error(self):
        """Calling unknown tool raises KeyError."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)

        with pytest.raises(KeyError, match="not registered"):
            agent.call_tool("unknown_tool")

    def test_call_tool_with_deny_all_checker(self):
        """All tool calls fail with deny-all checker."""
        tool = Tool(
            name="any_tool",
            description="Any tool",
            execute=dummy_execute,
            required_permissions=["any:permission"],
        )
        checker = DenyAllPermissionChecker()
        agent = ConcreteAgent(
            role=AgentRole.OPS,
            tools=[tool],
            permission_checker=checker,
        )

        with pytest.raises(PermissionError):
            agent.call_tool("any_tool")


class TestBaseAgentCallToolAsync:
    """Tests for async tool calling."""

    @pytest.mark.asyncio
    async def test_call_tool_async_with_async_execute(self):
        """Async tool can be called with call_tool_async."""
        tool = Tool(
            name="async_tool",
            description="Async tool",
            execute=async_dummy_execute,
        )
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
        )

        result = await agent.call_tool_async("async_tool", key="value")

        assert result["executed"] is True
        assert result["async"] is True
        assert result["kwargs"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_call_tool_async_with_sync_execute(self):
        """Sync tool can also be called with call_tool_async."""
        tool = Tool(
            name="sync_tool",
            description="Sync tool",
            execute=dummy_execute,
        )
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,
            tools=[tool],
        )

        result = await agent.call_tool_async("sync_tool")

        assert result["executed"] is True

    @pytest.mark.asyncio
    async def test_call_tool_async_permission_check(self):
        """Async tool call respects permission checks."""
        tool = Tool(
            name="restricted_async",
            description="Restricted async tool",
            execute=async_dummy_execute,
            required_permissions=["write:sentiment"],
        )
        checker = RoleBasedPermissionChecker()
        agent = ConcreteAgent(
            role=AgentRole.RESEARCHER,  # Can't write:sentiment
            tools=[tool],
            permission_checker=checker,
        )

        with pytest.raises(PermissionError):
            await agent.call_tool_async("restricted_async")


class TestBaseAgentExecute:
    """Tests for BaseAgent.execute abstract method."""

    @pytest.mark.asyncio
    async def test_concrete_agent_execute(self):
        """ConcreteAgent.execute returns expected result."""
        agent = ConcreteAgent(role=AgentRole.RESEARCHER)

        result = await agent.execute(
            task="Analyze strategy performance",
            context={"strategy_id": "momentum", "period": "30d"},
        )

        assert result["success"] is True
        assert "Analyze strategy performance" in result["result"]
        assert set(result["context_keys"]) == {"strategy_id", "period"}

    def test_abstract_agent_cannot_be_instantiated(self):
        """BaseAgent cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            BaseAgent(role=AgentRole.RESEARCHER)  # type: ignore


class TestBaseAgentRepr:
    """Tests for BaseAgent string representation."""

    def test_repr_shows_role_and_tool_count(self):
        """__repr__ shows role and tool count."""
        tools = [
            Tool(name="tool1", description="Tool 1", execute=dummy_execute),
            Tool(name="tool2", description="Tool 2", execute=dummy_execute),
        ]
        agent = ConcreteAgent(role=AgentRole.RESEARCHER, tools=tools)

        repr_str = repr(agent)

        assert "ConcreteAgent" in repr_str
        assert "researcher" in repr_str
        assert "tools=2" in repr_str

    def test_repr_with_no_tools(self):
        """__repr__ works with no tools."""
        agent = ConcreteAgent(role=AgentRole.ANALYST)

        repr_str = repr(agent)

        assert "analyst" in repr_str
        assert "tools=0" in repr_str
