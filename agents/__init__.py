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
from agents.dispatcher import AgentDispatcher

__all__ = [
    "AgentDispatcher",
    "AgentRole",
    "BaseAgent",
    "PermissionChecker",
    "PermissionError",
    "Tool",
]
