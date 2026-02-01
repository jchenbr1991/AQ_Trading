# AQ Trading AI Agents Module
# Phase 3 - US6: AI Agents for automated trading decisions
"""AI Agent subsystem for AQ Trading.

This module provides the foundation for AI-powered trading automation:
- BaseAgent: Abstract base class for all agent implementations
- Tool: Protocol for tools that agents can invoke
- AgentRole: Enum defining agent roles (researcher, analyst, etc.)
- PermissionChecker: Protocol for permission validation

Design principles:
- Agents suggest, Python executes (no direct trading commands)
- Permission-based access control for all tools
- Sidecar architecture (agents run as subprocesses)
"""

from agents.base import (
    AgentRole,
    BaseAgent,
    PermissionChecker,
    PermissionError,
    Tool,
)

# AgentDispatcher requires backend models which may not be available
# in all contexts (e.g., standalone agent testing)
try:
    from agents.dispatcher import AgentDispatcher
except ImportError:
    AgentDispatcher = None  # type: ignore

__all__ = [
    "AgentDispatcher",
    "AgentRole",
    "BaseAgent",
    "PermissionChecker",
    "PermissionError",
    "Tool",
]
