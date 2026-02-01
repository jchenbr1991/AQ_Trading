# Agent Prompts Module
# Contains prompt templates and agent implementations for AI trading agents
"""Agent prompts module for AQ Trading.

This module provides role-specific agent implementations:
- ResearcherAgent: Strategy analysis and optimization
- AnalystAgent: Market data analysis and sentiment factors
- RiskControllerAgent: Portfolio risk assessment and dynamic bias
- OpsAgent: System operations and reconciliation

Each agent inherits from BaseAgent and includes a SYSTEM_PROMPT
constant that defines its capabilities and constraints.
"""

from agents.prompts.analyst import AnalystAgent
from agents.prompts.ops import OpsAgent
from agents.prompts.researcher import ResearcherAgent
from agents.prompts.risk_controller import RiskControllerAgent

__all__ = [
    "AnalystAgent",
    "OpsAgent",
    "ResearcherAgent",
    "RiskControllerAgent",
]
