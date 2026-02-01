# backend/src/api/routes/agents.py
"""Agent API routes for invoking agents and retrieving results.

This module provides FastAPI endpoints for agent lifecycle management:
- POST /invoke - Invoke an agent task
- GET /results - List agent results with pagination
- GET /results/{id} - Get a specific agent result by ID
"""

import logging
import sys
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.models.agent_result import AgentResult, AgentRole
from src.schemas.agents import (
    AgentInvokeRequest,
    AgentResultResponse,
    AgentResultsListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])


def _to_response(agent_result: AgentResult) -> AgentResultResponse:
    """Convert an AgentResult model to an AgentResultResponse.

    Handles enum coercion for SQLite which may return strings instead of enums.
    """
    return AgentResultResponse(
        id=agent_result.id,
        role=(
            agent_result.role
            if isinstance(agent_result.role, AgentRole)
            else AgentRole(agent_result.role)
        ),
        task=agent_result.task,
        context=agent_result.context,
        result=agent_result.result,
        success=agent_result.success,
        error=agent_result.error,
        started_at=agent_result.started_at,
        completed_at=agent_result.completed_at,
        duration_ms=agent_result.duration_ms,
    )


def get_dispatcher():
    """Get the agent dispatcher instance.

    This function imports and instantiates the AgentDispatcher.
    It's separated for easy mocking in tests.
    """
    # Add agents directory to path if needed
    import os

    agents_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agents")
    if agents_dir not in sys.path:
        sys.path.insert(0, os.path.abspath(agents_dir))

    try:
        from agents.dispatcher import AgentDispatcher
    except ImportError:
        # Fallback for when running from project root
        from dispatcher import AgentDispatcher

    # Create a simple session factory for the dispatcher
    # Note: The dispatcher uses sync sessions for subprocess management
    def session_factory():
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        # Use a separate sync engine for the dispatcher
        from src.db.database import DATABASE_URL

        sync_url = DATABASE_URL.replace("+asyncpg", "").replace("+aiosqlite", "")
        engine = create_engine(sync_url)
        Session = sessionmaker(bind=engine)
        return Session()

    return AgentDispatcher(session_factory=session_factory)


@router.post("/invoke", response_model=AgentResultResponse)
async def invoke_agent(
    request: AgentInvokeRequest,
    session: AsyncSession = Depends(get_session),
) -> AgentResultResponse:
    """Invoke an agent task.

    This endpoint dispatches a task to the specified agent role.
    The agent runs as a subprocess and returns results asynchronously.

    Args:
        request: The agent invocation request containing role, task, and context

    Returns:
        AgentResultResponse with the execution result

    Example:
        POST /api/agents/invoke
        {
            "role": "researcher",
            "task": "analyze market trends for AAPL",
            "context": {"symbol": "AAPL", "timeframe": "1D"}
        }
    """
    logger.info(
        "Invoking agent: role=%s, task=%s",
        request.role.value,
        request.task[:50],
    )

    dispatcher = get_dispatcher()

    # Dispatch the task to the agent
    result = dispatcher.dispatch(
        role=request.role,
        task=request.task,
        context=request.context,
    )

    logger.info(
        "Agent completed: role=%s, success=%s, duration_ms=%s",
        result.role.value if hasattr(result.role, "value") else result.role,
        result.success,
        result.duration_ms,
    )

    return _to_response(result)


@router.get("/results", response_model=AgentResultsListResponse)
async def list_agent_results(
    limit: int = Query(default=50, ge=0, le=1000, description="Maximum results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
    session: AsyncSession = Depends(get_session),
) -> AgentResultsListResponse:
    """List agent results with pagination.

    Args:
        limit: Maximum number of results to return (default 50, max 1000)
        offset: Number of results to skip for pagination

    Returns:
        AgentResultsListResponse containing results and total count

    Example:
        GET /api/agents/results?limit=10&offset=0
        Returns first 10 agent results
    """
    logger.info("Listing agent results: limit=%d, offset=%d", limit, offset)

    # Get total count
    count_stmt = select(func.count()).select_from(AgentResult)
    count_result = await session.execute(count_stmt)
    total = count_result.scalar() or 0

    # Get paginated results
    stmt = select(AgentResult).order_by(AgentResult.started_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    results = result.scalars().all()

    return AgentResultsListResponse(
        results=[_to_response(r) for r in results],
        total=total,
    )


@router.get("/results/{result_id}", response_model=AgentResultResponse)
async def get_agent_result(
    result_id: UUID = Path(..., description="The agent result UUID"),
    session: AsyncSession = Depends(get_session),
) -> AgentResultResponse:
    """Get a specific agent result by ID.

    Args:
        result_id: The UUID of the agent result

    Returns:
        AgentResultResponse with the result details

    Raises:
        404: If the result is not found

    Example:
        GET /api/agents/results/550e8400-e29b-41d4-a716-446655440000
    """
    logger.info("Getting agent result: id=%s", result_id)

    stmt = select(AgentResult).where(AgentResult.id == result_id)
    result = await session.execute(stmt)
    agent_result = result.scalar_one_or_none()

    if agent_result is None:
        logger.warning("Agent result not found: id=%s", result_id)
        raise HTTPException(
            status_code=404,
            detail=f"Agent result '{result_id}' not found",
        )

    return _to_response(agent_result)
