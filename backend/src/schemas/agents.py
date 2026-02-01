# backend/src/schemas/agents.py
"""Pydantic schemas for Agent API endpoints.

These schemas support the agent invocation and result retrieval API routes.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.models.agent_result import AgentRole


class AgentInvokeRequest(BaseModel):
    """Request schema for invoking an agent task.

    Attributes:
        role: The agent role to invoke (researcher, analyst, risk_controller, ops)
        task: Description of the task for the agent to perform
        context: Additional context data for the agent
    """

    role: AgentRole = Field(..., description="The agent role to invoke")
    task: str = Field(..., min_length=1, max_length=500, description="Task description")
    context: dict[str, Any] = Field(..., description="Context data for the agent")


class AgentResultResponse(BaseModel):
    """Response schema for an agent result.

    Attributes:
        id: Unique identifier for the result
        role: The agent role that executed the task
        task: The task that was executed
        context: Context data provided to the agent
        result: The result data (if successful)
        success: Whether the task completed successfully
        error: Error message (if failed)
        started_at: When the agent started execution
        completed_at: When the agent completed execution
        duration_ms: Execution duration in milliseconds
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    role: AgentRole
    task: str
    context: dict[str, Any]
    result: dict[str, Any] | None
    success: bool
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    duration_ms: int | None


class AgentResultsListResponse(BaseModel):
    """Response schema for listing agent results.

    Attributes:
        results: List of agent results
        total: Total number of results (for pagination)
    """

    model_config = ConfigDict(from_attributes=True)

    results: list[AgentResultResponse]
    total: int
