# AQ Trading AI Agents - Base Module
# Phase 3 - US6: AI Agents for automated trading decisions
"""Base classes and protocols for the AI agent subsystem.

This module provides:
- Tool: Protocol/dataclass for tools that agents can use
- AgentRole: Enum defining agent roles and their capabilities
- PermissionChecker: Protocol for permission validation
- BaseAgent: Abstract base class for all agent implementations

Design Principles:
- Agents output parameters/suggestions, never direct trading commands
- Tools are registered with required permissions
- Permission checks happen before any tool execution
- Read-only access by default, write access requires explicit permission
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol, runtime_checkable


class AgentRole(str, Enum):
    """Agent roles with specific capabilities and permissions.

    Each role has predefined access boundaries:
    - RESEARCHER: Strategy optimization, backtest analysis
    - ANALYST: Factor production, sentiment scoring
    - RISK_CONTROLLER: Dynamic risk bias adjustment
    - OPS: System maintenance, reconciliation
    """

    RESEARCHER = "researcher"
    ANALYST = "analyst"
    RISK_CONTROLLER = "risk_controller"
    OPS = "ops"


@dataclass(frozen=True)
class Tool:
    """Definition of a tool that agents can invoke.

    Tools represent discrete operations that agents can perform.
    Each tool has:
    - A unique name for identification
    - A description for the agent to understand its purpose
    - An execute callable that performs the operation
    - Required permissions that must be satisfied before execution

    Attributes:
        name: Unique identifier for the tool
        description: Human-readable description of what the tool does
        execute: Callable that performs the tool's operation
        required_permissions: List of permission strings needed to use this tool

    Example:
        >>> tool = Tool(
        ...     name="backtest",
        ...     description="Run backtest on a strategy",
        ...     execute=run_backtest_fn,
        ...     required_permissions=["read:strategies", "execute:backtest"]
        ... )
    """

    name: str
    description: str
    execute: Callable[..., Any]
    required_permissions: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate tool definition."""
        if not self.name:
            raise ValueError("Tool name cannot be empty")
        if not self.description:
            raise ValueError("Tool description cannot be empty")
        if not callable(self.execute):
            raise ValueError("Tool execute must be callable")


@runtime_checkable
class PermissionChecker(Protocol):
    """Protocol for checking agent permissions.

    Implementations should verify whether an agent with a given role
    has the required permissions to perform an operation.

    Example implementation:
        class SimplePermissionChecker:
            def has_permission(self, role: AgentRole, permission: str) -> bool:
                allowed = ROLE_PERMISSIONS.get(role, set())
                return permission in allowed
    """

    def has_permission(self, role: AgentRole, permission: str) -> bool:
        """Check if the role has the specified permission.

        Args:
            role: The agent's role
            permission: The permission string to check (e.g., "read:strategies")

        Returns:
            True if the role has the permission, False otherwise
        """
        ...


class PermissionError(Exception):
    """Raised when an agent lacks required permissions for an operation."""

    def __init__(
        self,
        role: AgentRole,
        permission: str,
        tool_name: str | None = None,
        message: str | None = None,
    ) -> None:
        self.role = role
        self.permission = permission
        self.tool_name = tool_name

        if message:
            super().__init__(message)
        else:
            tool_info = f" for tool '{tool_name}'" if tool_name else ""
            super().__init__(
                f"Agent role '{role.value}' lacks permission '{permission}'{tool_info}"
            )


class BaseAgent(ABC):
    """Abstract base class for all AI agents.

    Provides common infrastructure for agent implementations:
    - Tool registration and management
    - Permission-checked tool execution
    - Task execution interface

    Subclasses must implement the `execute` method to define
    role-specific behavior.

    Attributes:
        role: The agent's role determining its capabilities
        permission_checker: Checker for validating permissions

    Example:
        >>> class ResearcherAgent(BaseAgent):
        ...     async def execute(self, task: str, context: dict) -> dict:
        ...         # Analyze strategy performance
        ...         result = await self.call_tool("backtest", strategy_id="momentum")
        ...         return {"analysis": result}
    """

    def __init__(
        self,
        role: AgentRole,
        tools: list[Tool] | None = None,
        permission_checker: PermissionChecker | None = None,
    ) -> None:
        """Initialize the base agent.

        Args:
            role: The agent's role (determines capabilities)
            tools: Initial list of tools to register
            permission_checker: Checker for permission validation.
                               If None, all permissions are granted.

        Raises:
            ValueError: If role is not a valid AgentRole
        """
        if not isinstance(role, AgentRole):
            raise ValueError(f"Invalid role: {role}. Must be an AgentRole enum.")

        self._role = role
        self._permission_checker = permission_checker
        self._tools: dict[str, Tool] = {}

        # Register initial tools
        if tools:
            for tool in tools:
                self.register_tool(tool)

    @property
    def role(self) -> AgentRole:
        """The agent's role."""
        return self._role

    @property
    def permission_checker(self) -> PermissionChecker | None:
        """The permission checker instance."""
        return self._permission_checker

    def register_tool(self, tool: Tool) -> None:
        """Register a tool for the agent to use.

        Args:
            tool: The tool to register

        Raises:
            ValueError: If a tool with the same name is already registered
            TypeError: If tool is not a Tool instance
        """
        if not isinstance(tool, Tool):
            raise TypeError(f"Expected Tool instance, got {type(tool).__name__}")

        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool

    def unregister_tool(self, tool_name: str) -> None:
        """Unregister a tool by name.

        Args:
            tool_name: Name of the tool to unregister

        Raises:
            KeyError: If no tool with that name is registered
        """
        if tool_name not in self._tools:
            raise KeyError(f"Tool '{tool_name}' is not registered")

        del self._tools[tool_name]

    def get_tool(self, tool_name: str) -> Tool | None:
        """Get a registered tool by name.

        Args:
            tool_name: Name of the tool to retrieve

        Returns:
            The Tool if found, None otherwise
        """
        return self._tools.get(tool_name)

    def get_available_tools(self) -> list[str]:
        """Get names of all registered tools.

        Returns:
            List of tool names that are registered with this agent
        """
        return list(self._tools.keys())

    def _check_permissions(self, tool: Tool) -> None:
        """Verify the agent has all required permissions for a tool.

        Args:
            tool: The tool to check permissions for

        Raises:
            PermissionError: If any required permission is missing
        """
        if self._permission_checker is None:
            # No permission checker means all permissions are granted
            return

        for permission in tool.required_permissions:
            if not self._permission_checker.has_permission(self._role, permission):
                raise PermissionError(
                    role=self._role,
                    permission=permission,
                    tool_name=tool.name,
                )

    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a registered tool with permission checking.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Arguments to pass to the tool's execute function

        Returns:
            The result from the tool's execute function

        Raises:
            KeyError: If the tool is not registered
            PermissionError: If the agent lacks required permissions
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' is not registered")

        # Check permissions before execution
        self._check_permissions(tool)

        # Execute the tool
        return tool.execute(**kwargs)

    async def call_tool_async(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a registered tool asynchronously with permission checking.

        For tools that have async execute functions.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Arguments to pass to the tool's execute function

        Returns:
            The result from the tool's execute function

        Raises:
            KeyError: If the tool is not registered
            PermissionError: If the agent lacks required permissions
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            raise KeyError(f"Tool '{tool_name}' is not registered")

        # Check permissions before execution
        self._check_permissions(tool)

        # Execute the tool (await if coroutine)
        result = tool.execute(**kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    @abstractmethod
    async def execute(self, task: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a task with the given context.

        This is the main entry point for agent operations. Subclasses
        must implement this method to define role-specific behavior.

        Args:
            task: Description of the task to perform
            context: Additional context data for the task (e.g., market data,
                    portfolio state, historical traces)

        Returns:
            A dictionary containing the task result. The structure depends
            on the agent role but should include at minimum:
            - success: bool indicating if the task completed
            - result: The actual output data
            - error: Error message if success is False
        """
        ...

    def __repr__(self) -> str:
        tool_count = len(self._tools)
        return f"{self.__class__.__name__}(role={self._role.value}, tools={tool_count})"
