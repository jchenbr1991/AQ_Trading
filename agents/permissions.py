"""
Permission model for AI agent role-based access control.

This module implements permission boundaries for AI agents as defined in
STRATEGY.md (Safety Red Lines / Air Gap section). Agents have read-only
database access and can only write to specific Redis keys.

Permission model:
- Researcher: read strategies/*, write None
- Analyst: read market_data/*, news/*, write redis:sentiment:*
- RiskController: read portfolio/*, risk/*, write redis:risk_bias
- Ops: read broker/*, reconciliation/*, write None
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRole(str, Enum):
    """Agent roles matching backend/src/models/agent_result.py.

    Defined here to avoid import dependencies between agents/ and backend/.
    """

    RESEARCHER = "researcher"
    ANALYST = "analyst"
    RISK_CONTROLLER = "risk_controller"
    OPS = "ops"


@dataclass(frozen=True)
class ToolPermission:
    """Permission definition for a specific tool.

    Attributes:
        tool_name: Name of the tool (e.g., 'backtest', 'portfolio')
        allowed_patterns: List of regex patterns for allowed arguments/resources
    """

    tool_name: str
    allowed_patterns: list[str] = field(default_factory=list)

    def matches(self, resource: str) -> bool:
        """Check if a resource matches any of the allowed patterns.

        Args:
            resource: The resource path or identifier to check

        Returns:
            True if the resource matches at least one allowed pattern
        """
        if not self.allowed_patterns:
            return False
        return any(re.match(pattern, resource) for pattern in self.allowed_patterns)


@dataclass(frozen=True)
class RolePermissions:
    """Permission set for an agent role.

    Attributes:
        role: The agent role (e.g., AgentRole.RESEARCHER)
        can_read: List of glob patterns for readable resources
        can_write: List of glob patterns for writable resources (typically Redis keys)
        can_execute: List of allowed tool/command names
    """

    role: AgentRole
    can_read: list[str] = field(default_factory=list)
    can_write: list[str] = field(default_factory=list)
    can_execute: list[str] = field(default_factory=list)

    def _pattern_to_regex(self, pattern: str) -> str:
        """Convert a glob-like pattern to a regex pattern.

        Supports:
        - * matches any sequence of characters except /
        - ** matches any sequence including /
        - Literal characters are escaped

        Args:
            pattern: Glob-like pattern (e.g., 'strategies/*', 'redis:sentiment:*')

        Returns:
            Regex pattern string
        """
        # Escape special regex characters except * and /
        escaped = re.escape(pattern)
        # Convert ** to match anything (including /)
        escaped = escaped.replace(r"\*\*", ".*")
        # Convert remaining * to match anything except /
        escaped = escaped.replace(r"\*", "[^/]*")
        return f"^{escaped}$"

    def can_read_resource(self, resource: str) -> bool:
        """Check if this role can read the given resource.

        Args:
            resource: Resource path (e.g., 'strategies/momentum.py', 'market_data/AAPL')

        Returns:
            True if reading is allowed
        """
        for pattern in self.can_read:
            regex = self._pattern_to_regex(pattern)
            if re.match(regex, resource):
                return True
        return False

    def can_write_resource(self, resource: str) -> bool:
        """Check if this role can write to the given resource.

        Args:
            resource: Resource path (e.g., 'redis:sentiment:AAPL', 'redis:risk_bias')

        Returns:
            True if writing is allowed
        """
        for pattern in self.can_write:
            regex = self._pattern_to_regex(pattern)
            if re.match(regex, resource):
                return True
        return False

    def can_execute_tool(self, tool_name: str) -> bool:
        """Check if this role can execute the given tool.

        Args:
            tool_name: Name of the tool (e.g., 'backtest', 'pytest')

        Returns:
            True if execution is allowed
        """
        return tool_name in self.can_execute


# Default permissions as defined in STRATEGY.md
DEFAULT_PERMISSIONS: dict[AgentRole, RolePermissions] = {
    AgentRole.RESEARCHER: RolePermissions(
        role=AgentRole.RESEARCHER,
        can_read=[
            "strategies/*",
            "strategies/**",
            "backtest/*",
            "backtest/**",
            "logs/*",
            "logs/**",
        ],
        can_write=[
            "strategies/examples/*",
            "strategies/examples/**",
            "agents/outputs/*",
            "agents/outputs/**",
        ],
        can_execute=["backtest", "pytest"],
    ),
    AgentRole.ANALYST: RolePermissions(
        role=AgentRole.ANALYST,
        can_read=[
            "market_data/*",
            "market_data/**",
            "news/*",
            "news/**",
        ],
        can_write=[
            "redis:sentiment:*",
            "redis:events:*",
        ],
        can_execute=[],
    ),
    AgentRole.RISK_CONTROLLER: RolePermissions(
        role=AgentRole.RISK_CONTROLLER,
        can_read=[
            "portfolio/*",
            "portfolio/**",
            "risk/*",
            "risk/**",
            "market_data/*",
            "market_data/**",
        ],
        can_write=[
            "redis:risk_bias",
        ],
        can_execute=[],
    ),
    AgentRole.OPS: RolePermissions(
        role=AgentRole.OPS,
        can_read=[
            "broker/*",
            "broker/**",
            "reconciliation/*",
            "reconciliation/**",
            "logs/*",
            "logs/**",
            "health/*",
            "health/**",
        ],
        can_write=[
            "logs/*",
            "logs/**",
            "agents/outputs/*",
            "agents/outputs/**",
        ],
        can_execute=["docker", "systemctl"],
    ),
}


class PermissionChecker:
    """Validates agent operations against role-based permissions.

    This class is the central authority for permission checks. It validates
    read/write operations and tool calls against the defined permission matrix.

    Example:
        checker = PermissionChecker()
        if checker.can_read(AgentRole.RESEARCHER, "strategies/momentum.py"):
            # Allow reading the file
            ...

        if not checker.validate_tool_call(AgentRole.ANALYST, "backtest", {}):
            raise PermissionError("Analyst cannot execute backtest")
    """

    def __init__(
        self, permissions: dict[AgentRole, RolePermissions] | None = None
    ) -> None:
        """Initialize the permission checker.

        Args:
            permissions: Custom permission mapping. If None, uses DEFAULT_PERMISSIONS.
        """
        self._permissions = DEFAULT_PERMISSIONS if permissions is None else permissions

    def get_permissions(self, role: AgentRole) -> RolePermissions:
        """Get the permissions for a specific role.

        Args:
            role: The agent role

        Returns:
            RolePermissions for the given role

        Raises:
            KeyError: If the role is not found in the permissions mapping
        """
        if role not in self._permissions:
            raise KeyError(f"No permissions defined for role: {role}")
        return self._permissions[role]

    def can_read(self, role: AgentRole, resource: str) -> bool:
        """Check if an agent role can read a resource.

        Args:
            role: The agent role
            resource: Resource path to check

        Returns:
            True if the role can read the resource
        """
        try:
            perms = self.get_permissions(role)
            return perms.can_read_resource(resource)
        except KeyError:
            return False

    def can_write(self, role: AgentRole, resource: str) -> bool:
        """Check if an agent role can write to a resource.

        Args:
            role: The agent role
            resource: Resource path to check

        Returns:
            True if the role can write to the resource
        """
        try:
            perms = self.get_permissions(role)
            return perms.can_write_resource(resource)
        except KeyError:
            return False

    def validate_tool_call(
        self, role: AgentRole, tool: str, args: dict[str, Any]
    ) -> bool:
        """Validate if an agent role can execute a tool with given arguments.

        This method checks:
        1. If the tool is in the role's allowed execution list
        2. If any resource arguments (read/write paths) are permitted

        Args:
            role: The agent role
            tool: Tool name to execute
            args: Tool arguments (may contain 'read_path', 'write_path', etc.)

        Returns:
            True if the tool call is permitted
        """
        try:
            perms = self.get_permissions(role)
        except KeyError:
            return False

        # Check if tool execution is allowed
        if not perms.can_execute_tool(tool):
            # Special case: read/write tools that don't need execute permission
            # but need resource permission
            if tool in ("read", "read_file"):
                read_path = args.get("path") or args.get("read_path")
                if read_path:
                    return perms.can_read_resource(read_path)
                return False
            elif tool in ("write", "write_file"):
                write_path = args.get("path") or args.get("write_path")
                if write_path:
                    return perms.can_write_resource(write_path)
                return False
            elif tool in ("redis_write", "redis_set"):
                key = args.get("key")
                if key:
                    return perms.can_write_resource(f"redis:{key}")
                return False
            return False

        # Tool is allowed, now check resource-specific permissions in args
        read_path = args.get("read_path") or args.get("input_path")
        if read_path and not perms.can_read_resource(read_path):
            return False

        write_path = args.get("write_path") or args.get("output_path")
        if write_path and not perms.can_write_resource(write_path):
            return False

        return True

    def get_blocked_reason(
        self, role: AgentRole, operation: str, resource: str
    ) -> str | None:
        """Get a human-readable reason why an operation is blocked.

        Args:
            role: The agent role
            operation: 'read', 'write', or 'execute'
            resource: Resource path or tool name

        Returns:
            Reason string if blocked, None if allowed
        """
        try:
            perms = self.get_permissions(role)
        except KeyError:
            return f"Unknown role: {role}"

        if operation == "read":
            if not perms.can_read_resource(resource):
                return (
                    f"Role '{role.value}' cannot read '{resource}'. "
                    f"Allowed patterns: {perms.can_read}"
                )
        elif operation == "write":
            if not perms.can_write_resource(resource):
                return (
                    f"Role '{role.value}' cannot write to '{resource}'. "
                    f"Allowed patterns: {perms.can_write}"
                )
        elif operation == "execute":
            if not perms.can_execute_tool(resource):
                return (
                    f"Role '{role.value}' cannot execute '{resource}'. "
                    f"Allowed tools: {perms.can_execute}"
                )
        else:
            return f"Unknown operation: {operation}"

        return None
