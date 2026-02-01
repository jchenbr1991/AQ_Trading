# AQ Trading AI Agents - Prompt Agent Tests
"""Tests for the agent prompt implementations.

Tests cover:
- Agent initialization with correct roles
- SYSTEM_PROMPT constant presence and content
- Execute method signature and placeholder behavior
- Tool registration inheritance
"""

import pytest
from typing import Any

from agents.base import AgentRole, PermissionChecker, Tool

# Import directly from modules to avoid dispatcher import issues
from agents.prompts.researcher import ResearcherAgent
from agents.prompts.analyst import AnalystAgent
from agents.prompts.risk_controller import RiskControllerAgent
from agents.prompts.ops import OpsAgent


# ==============================================================================
# Test Fixtures and Helpers
# ==============================================================================


def dummy_execute(**kwargs: Any) -> dict[str, Any]:
    """A simple execute function for testing tool registration."""
    return {"executed": True, "kwargs": kwargs}


class AllowAllPermissionChecker:
    """Permission checker that allows everything."""

    def has_permission(self, role: AgentRole, permission: str) -> bool:
        return True


@pytest.fixture
def sample_tool() -> Tool:
    """Create a sample tool for testing."""
    return Tool(
        name="test_tool",
        description="A test tool",
        execute=dummy_execute,
        required_permissions=["read:test"],
    )


@pytest.fixture
def permission_checker() -> AllowAllPermissionChecker:
    """Create a permission checker for testing."""
    return AllowAllPermissionChecker()


# ==============================================================================
# ResearcherAgent Tests
# ==============================================================================


class TestResearcherAgent:
    """Tests for ResearcherAgent."""

    def test_init_with_defaults(self):
        """ResearcherAgent can be initialized with defaults."""
        agent = ResearcherAgent()

        assert agent.role == AgentRole.RESEARCHER
        assert agent.permission_checker is None
        assert agent.get_available_tools() == []

    def test_init_with_tools(self, sample_tool: Tool):
        """ResearcherAgent can be initialized with tools."""
        agent = ResearcherAgent(tools=[sample_tool])

        assert "test_tool" in agent.get_available_tools()

    def test_init_with_permission_checker(
        self, permission_checker: AllowAllPermissionChecker
    ):
        """ResearcherAgent can be initialized with permission checker."""
        agent = ResearcherAgent(permission_checker=permission_checker)

        assert agent.permission_checker is permission_checker

    def test_has_system_prompt(self):
        """ResearcherAgent has SYSTEM_PROMPT constant."""
        assert hasattr(ResearcherAgent, "SYSTEM_PROMPT")
        assert isinstance(ResearcherAgent.SYSTEM_PROMPT, str)
        assert len(ResearcherAgent.SYSTEM_PROMPT) > 100

    def test_system_prompt_contains_key_elements(self):
        """ResearcherAgent SYSTEM_PROMPT contains key elements."""
        prompt = ResearcherAgent.SYSTEM_PROMPT

        # Check for role identification
        assert "Researcher" in prompt or "researcher" in prompt

        # Check for overfitting prevention
        assert "Walk-Forward" in prompt or "walk-forward" in prompt
        assert "overfitting" in prompt.lower()

        # Check for validation requirements
        assert "validation" in prompt.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_placeholder(self):
        """ResearcherAgent.execute returns placeholder result."""
        agent = ResearcherAgent()

        result = await agent.execute(
            task="Optimize momentum strategy",
            context={"strategy_id": "momentum", "period": "30d"},
        )

        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is False
        assert "Not implemented" in result.get("error", "")
        assert result["task"] == "Optimize momentum strategy"
        assert "strategy_id" in result["context_keys"]

    @pytest.mark.asyncio
    async def test_execute_with_empty_context(self):
        """ResearcherAgent.execute handles empty context."""
        agent = ResearcherAgent()

        result = await agent.execute(task="Simple task", context={})

        assert result["context_keys"] == []

    def test_repr(self):
        """ResearcherAgent repr is informative."""
        agent = ResearcherAgent()
        repr_str = repr(agent)

        assert "ResearcherAgent" in repr_str
        assert "researcher" in repr_str


# ==============================================================================
# AnalystAgent Tests
# ==============================================================================


class TestAnalystAgent:
    """Tests for AnalystAgent."""

    def test_init_with_defaults(self):
        """AnalystAgent can be initialized with defaults."""
        agent = AnalystAgent()

        assert agent.role == AgentRole.ANALYST
        assert agent.permission_checker is None
        assert agent.get_available_tools() == []

    def test_init_with_tools(self, sample_tool: Tool):
        """AnalystAgent can be initialized with tools."""
        agent = AnalystAgent(tools=[sample_tool])

        assert "test_tool" in agent.get_available_tools()

    def test_has_system_prompt(self):
        """AnalystAgent has SYSTEM_PROMPT constant."""
        assert hasattr(AnalystAgent, "SYSTEM_PROMPT")
        assert isinstance(AnalystAgent.SYSTEM_PROMPT, str)
        assert len(AnalystAgent.SYSTEM_PROMPT) > 100

    def test_system_prompt_contains_key_elements(self):
        """AnalystAgent SYSTEM_PROMPT contains key elements."""
        prompt = AnalystAgent.SYSTEM_PROMPT

        # Check for role identification
        assert "Analyst" in prompt or "analyst" in prompt

        # Check for sentiment analysis
        assert "sentiment" in prompt.lower()

        # Check for event tagging
        assert "event" in prompt.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_placeholder(self):
        """AnalystAgent.execute returns placeholder result."""
        agent = AnalystAgent()

        result = await agent.execute(
            task="Analyze TSLA sentiment",
            context={"symbol": "TSLA", "hours": 24},
        )

        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is False
        assert result["task"] == "Analyze TSLA sentiment"

    def test_repr(self):
        """AnalystAgent repr is informative."""
        agent = AnalystAgent()
        repr_str = repr(agent)

        assert "AnalystAgent" in repr_str
        assert "analyst" in repr_str


# ==============================================================================
# RiskControllerAgent Tests
# ==============================================================================


class TestRiskControllerAgent:
    """Tests for RiskControllerAgent."""

    def test_init_with_defaults(self):
        """RiskControllerAgent can be initialized with defaults."""
        agent = RiskControllerAgent()

        assert agent.role == AgentRole.RISK_CONTROLLER
        assert agent.permission_checker is None
        assert agent.get_available_tools() == []

    def test_init_with_tools(self, sample_tool: Tool):
        """RiskControllerAgent can be initialized with tools."""
        agent = RiskControllerAgent(tools=[sample_tool])

        assert "test_tool" in agent.get_available_tools()

    def test_has_system_prompt(self):
        """RiskControllerAgent has SYSTEM_PROMPT constant."""
        assert hasattr(RiskControllerAgent, "SYSTEM_PROMPT")
        assert isinstance(RiskControllerAgent.SYSTEM_PROMPT, str)
        assert len(RiskControllerAgent.SYSTEM_PROMPT) > 100

    def test_system_prompt_contains_key_elements(self):
        """RiskControllerAgent SYSTEM_PROMPT contains key elements."""
        prompt = RiskControllerAgent.SYSTEM_PROMPT

        # Check for role identification
        assert "Risk" in prompt

        # Check for bias concept
        assert "bias" in prompt.lower()

        # Check for VIX reference
        assert "VIX" in prompt

        # Check for safety rules
        assert "emergency" in prompt.lower() or "safety" in prompt.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_placeholder(self):
        """RiskControllerAgent.execute returns placeholder result."""
        agent = RiskControllerAgent()

        result = await agent.execute(
            task="Calculate risk bias",
            context={"vix": 25.5, "drawdown_5d": -3.2},
        )

        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is False
        assert result["task"] == "Calculate risk bias"
        assert "vix" in result["context_keys"]

    def test_repr(self):
        """RiskControllerAgent repr is informative."""
        agent = RiskControllerAgent()
        repr_str = repr(agent)

        assert "RiskControllerAgent" in repr_str
        assert "risk_controller" in repr_str


# ==============================================================================
# OpsAgent Tests
# ==============================================================================


class TestOpsAgent:
    """Tests for OpsAgent."""

    def test_init_with_defaults(self):
        """OpsAgent can be initialized with defaults."""
        agent = OpsAgent()

        assert agent.role == AgentRole.OPS
        assert agent.permission_checker is None
        assert agent.get_available_tools() == []

    def test_init_with_tools(self, sample_tool: Tool):
        """OpsAgent can be initialized with tools."""
        agent = OpsAgent(tools=[sample_tool])

        assert "test_tool" in agent.get_available_tools()

    def test_has_system_prompt(self):
        """OpsAgent has SYSTEM_PROMPT constant."""
        assert hasattr(OpsAgent, "SYSTEM_PROMPT")
        assert isinstance(OpsAgent.SYSTEM_PROMPT, str)
        assert len(OpsAgent.SYSTEM_PROMPT) > 100

    def test_system_prompt_contains_key_elements(self):
        """OpsAgent SYSTEM_PROMPT contains key elements."""
        prompt = OpsAgent.SYSTEM_PROMPT

        # Check for role identification
        assert "Ops" in prompt

        # Check for reconciliation
        assert "reconciliation" in prompt.lower() or "discrepancy" in prompt.lower()

        # Check for fix suggestions
        assert "fix" in prompt.lower()

        # Check for safety rules
        assert "rollback" in prompt.lower() or "review" in prompt.lower()

    @pytest.mark.asyncio
    async def test_execute_returns_placeholder(self):
        """OpsAgent.execute returns placeholder result."""
        agent = OpsAgent()

        result = await agent.execute(
            task="Investigate AAPL position mismatch",
            context={"local_qty": 100, "broker_qty": 110, "symbol": "AAPL"},
        )

        assert isinstance(result, dict)
        assert "success" in result
        assert result["success"] is False
        assert result["task"] == "Investigate AAPL position mismatch"
        assert "local_qty" in result["context_keys"]
        assert "broker_qty" in result["context_keys"]

    def test_repr(self):
        """OpsAgent repr is informative."""
        agent = OpsAgent()
        repr_str = repr(agent)

        assert "OpsAgent" in repr_str
        assert "ops" in repr_str


# ==============================================================================
# Cross-Agent Tests
# ==============================================================================


class TestAgentCommonBehavior:
    """Tests for behavior common to all agents."""

    @pytest.mark.parametrize(
        "agent_class,expected_role",
        [
            (ResearcherAgent, AgentRole.RESEARCHER),
            (AnalystAgent, AgentRole.ANALYST),
            (RiskControllerAgent, AgentRole.RISK_CONTROLLER),
            (OpsAgent, AgentRole.OPS),
        ],
    )
    def test_all_agents_have_correct_role(self, agent_class, expected_role):
        """All agents initialize with correct role."""
        agent = agent_class()
        assert agent.role == expected_role

    @pytest.mark.parametrize(
        "agent_class",
        [ResearcherAgent, AnalystAgent, RiskControllerAgent, OpsAgent],
    )
    def test_all_agents_have_system_prompt(self, agent_class):
        """All agents have non-empty SYSTEM_PROMPT."""
        assert hasattr(agent_class, "SYSTEM_PROMPT")
        assert isinstance(agent_class.SYSTEM_PROMPT, str)
        assert len(agent_class.SYSTEM_PROMPT) > 100

    @pytest.mark.parametrize(
        "agent_class",
        [ResearcherAgent, AnalystAgent, RiskControllerAgent, OpsAgent],
    )
    def test_all_agents_inherit_tool_registration(
        self, agent_class, sample_tool: Tool
    ):
        """All agents can register and use tools."""
        agent = agent_class()
        agent.register_tool(sample_tool)

        assert "test_tool" in agent.get_available_tools()
        assert agent.get_tool("test_tool") == sample_tool

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "agent_class",
        [ResearcherAgent, AnalystAgent, RiskControllerAgent, OpsAgent],
    )
    async def test_all_agents_execute_is_async(self, agent_class):
        """All agents have async execute method."""
        agent = agent_class()
        result = await agent.execute("test task", {})

        assert isinstance(result, dict)
        assert "success" in result

    @pytest.mark.parametrize(
        "agent_class",
        [ResearcherAgent, AnalystAgent, RiskControllerAgent, OpsAgent],
    )
    def test_all_agents_prompt_defines_boundaries(self, agent_class):
        """All agents have boundaries defined in SYSTEM_PROMPT."""
        prompt = agent_class.SYSTEM_PROMPT

        # All prompts should mention what agents can/cannot do
        assert (
            "can read" in prompt.lower()
            or "can_read" in prompt.lower()
            or "you can read" in prompt.lower()
        )
