# backend/tests/api/test_agents_routes.py
"""Tests for agent API endpoints.

Tests the agent invocation and result retrieval API routes:
- POST /api/agents/invoke - Invoke agent task
- GET /api/agents/results - List agent results with pagination
- GET /api/agents/results/{id} - Get specific agent result
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.db.database import Base, get_session
from src.main import app
from src.models.agent_result import AgentResult, AgentRole


@pytest_asyncio.fixture
async def agents_db_session():
    """In-memory SQLite database with agent_results table for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables using SQLAlchemy metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def agents_client(agents_db_session):
    """HTTP client with agents database."""

    async def override_get_session():
        yield agents_db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_agent_result(
    session: AsyncSession,
    role: AgentRole,
    task: str,
    context: dict,
    result: dict | None = None,
    success: bool = True,
    error: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    duration_ms: int | None = None,
) -> AgentResult:
    """Insert a test agent result into the database."""
    now = datetime.now(timezone.utc)
    agent_result = AgentResult(
        role=role,
        task=task,
        context=context,
        result=result,
        success=success,
        error=error,
        started_at=started_at or now,
        completed_at=completed_at or now,
        duration_ms=duration_ms or 100,
    )
    session.add(agent_result)
    await session.commit()
    await session.refresh(agent_result)
    return agent_result


class TestPostInvokeAgent:
    """Tests for POST /api/agents/invoke endpoint."""

    @pytest.mark.asyncio
    async def test_invoke_agent_success(self, agents_client, agents_db_session):
        """Should invoke an agent and return the result."""
        # Mock the dispatcher to avoid actual subprocess calls
        mock_result = AgentResult(
            id=uuid.uuid4(),
            role=AgentRole.RESEARCHER,
            task="analyze market trends",
            context={"symbol": "AAPL"},
            result={"summary": "bullish trend"},
            success=True,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_ms=150,
        )

        with patch("src.api.routes.agents.get_dispatcher") as mock_get_dispatcher:
            mock_dispatcher = MagicMock()
            mock_dispatcher.dispatch.return_value = mock_result
            mock_get_dispatcher.return_value = mock_dispatcher

            response = await agents_client.post(
                "/api/agents/invoke",
                json={
                    "role": "researcher",
                    "task": "analyze market trends",
                    "context": {"symbol": "AAPL"},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "researcher"
        assert data["task"] == "analyze market trends"
        assert data["context"] == {"symbol": "AAPL"}
        assert data["result"] == {"summary": "bullish trend"}
        assert data["success"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_invoke_agent_invalid_role(self, agents_client):
        """Should return 422 for invalid agent role."""
        response = await agents_client.post(
            "/api/agents/invoke",
            json={
                "role": "invalid_role",
                "task": "some task",
                "context": {},
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invoke_agent_missing_task(self, agents_client):
        """Should return 422 when task is missing."""
        response = await agents_client.post(
            "/api/agents/invoke",
            json={
                "role": "researcher",
                "context": {},
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invoke_agent_missing_context(self, agents_client):
        """Should return 422 when context is missing."""
        response = await agents_client.post(
            "/api/agents/invoke",
            json={
                "role": "researcher",
                "task": "analyze market",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invoke_agent_failure(self, agents_client, agents_db_session):
        """Should handle agent execution failure gracefully."""
        mock_result = AgentResult(
            id=uuid.uuid4(),
            role=AgentRole.ANALYST,
            task="analyze data",
            context={},
            result=None,
            success=False,
            error="Permission denied",
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            duration_ms=50,
        )

        with patch("src.api.routes.agents.get_dispatcher") as mock_get_dispatcher:
            mock_dispatcher = MagicMock()
            mock_dispatcher.dispatch.return_value = mock_result
            mock_get_dispatcher.return_value = mock_dispatcher

            response = await agents_client.post(
                "/api/agents/invoke",
                json={
                    "role": "analyst",
                    "task": "analyze data",
                    "context": {},
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Permission denied"

    @pytest.mark.asyncio
    async def test_invoke_all_valid_roles(self, agents_client, agents_db_session):
        """Should accept all valid agent roles."""
        valid_roles = ["researcher", "analyst", "risk_controller", "ops"]

        for role in valid_roles:
            mock_result = AgentResult(
                id=uuid.uuid4(),
                role=AgentRole(role),
                task="test task",
                context={},
                result={"status": "ok"},
                success=True,
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                duration_ms=100,
            )

            with patch("src.api.routes.agents.get_dispatcher") as mock_get_dispatcher:
                mock_dispatcher = MagicMock()
                mock_dispatcher.dispatch.return_value = mock_result
                mock_get_dispatcher.return_value = mock_dispatcher

                response = await agents_client.post(
                    "/api/agents/invoke",
                    json={
                        "role": role,
                        "task": "test task",
                        "context": {},
                    },
                )

            assert response.status_code == 200, f"Role '{role}' should be accepted"


class TestGetAgentResults:
    """Tests for GET /api/agents/results endpoint."""

    @pytest.mark.asyncio
    async def test_get_results_empty(self, agents_client):
        """Should return empty list when no results exist."""
        response = await agents_client.get("/api/agents/results")

        assert response.status_code == 200
        data = response.json()
        assert data["results"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_get_results_with_data(self, agents_client, agents_db_session):
        """Should return list of agent results."""
        # Insert test results
        await insert_agent_result(
            agents_db_session,
            role=AgentRole.RESEARCHER,
            task="task 1",
            context={"key": "value1"},
            result={"output": "result1"},
        )
        await insert_agent_result(
            agents_db_session,
            role=AgentRole.ANALYST,
            task="task 2",
            context={"key": "value2"},
            result={"output": "result2"},
        )

        response = await agents_client.get("/api/agents/results")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["results"]) == 2

    @pytest.mark.asyncio
    async def test_get_results_pagination_limit(self, agents_client, agents_db_session):
        """Should respect limit parameter."""
        # Insert 5 results
        for i in range(5):
            await insert_agent_result(
                agents_db_session,
                role=AgentRole.RESEARCHER,
                task=f"task {i}",
                context={},
                result={},
            )

        response = await agents_client.get("/api/agents/results?limit=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2
        assert data["total"] == 5  # Total count is still 5

    @pytest.mark.asyncio
    async def test_get_results_pagination_offset(self, agents_client, agents_db_session):
        """Should respect offset parameter."""
        # Insert 5 results
        for i in range(5):
            await insert_agent_result(
                agents_db_session,
                role=AgentRole.RESEARCHER,
                task=f"task {i}",
                context={},
                result={},
            )

        response = await agents_client.get("/api/agents/results?offset=3")

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 2  # 5 total, offset 3 = 2 remaining

    @pytest.mark.asyncio
    async def test_get_results_pagination_limit_and_offset(self, agents_client, agents_db_session):
        """Should respect both limit and offset parameters."""
        # Insert 10 results
        for i in range(10):
            await insert_agent_result(
                agents_db_session,
                role=AgentRole.RESEARCHER,
                task=f"task {i}",
                context={},
                result={},
            )

        response = await agents_client.get("/api/agents/results?limit=3&offset=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 3
        assert data["total"] == 10

    @pytest.mark.asyncio
    async def test_get_results_invalid_limit(self, agents_client):
        """Should return 422 for invalid limit (negative)."""
        response = await agents_client.get("/api/agents/results?limit=-1")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_results_invalid_offset(self, agents_client):
        """Should return 422 for invalid offset (negative)."""
        response = await agents_client.get("/api/agents/results?offset=-1")

        assert response.status_code == 422


class TestGetAgentResultById:
    """Tests for GET /api/agents/results/{id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_result_by_id_success(self, agents_client, agents_db_session):
        """Should return specific agent result by ID."""
        agent_result = await insert_agent_result(
            agents_db_session,
            role=AgentRole.RISK_CONTROLLER,
            task="check risk limits",
            context={"portfolio_id": "123"},
            result={"risk_level": "acceptable"},
            success=True,
            duration_ms=250,
        )

        response = await agents_client.get(f"/api/agents/results/{agent_result.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(agent_result.id)
        assert data["role"] == "risk_controller"
        assert data["task"] == "check risk limits"
        assert data["context"] == {"portfolio_id": "123"}
        assert data["result"] == {"risk_level": "acceptable"}
        assert data["success"] is True
        assert data["duration_ms"] == 250

    @pytest.mark.asyncio
    async def test_get_result_by_id_not_found(self, agents_client):
        """Should return 404 for non-existent result ID."""
        non_existent_id = uuid.uuid4()
        response = await agents_client.get(f"/api/agents/results/{non_existent_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_result_by_id_invalid_uuid(self, agents_client):
        """Should return 422 for invalid UUID format."""
        response = await agents_client.get("/api/agents/results/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_result_includes_error_field(self, agents_client, agents_db_session):
        """Should include error field when agent failed."""
        agent_result = await insert_agent_result(
            agents_db_session,
            role=AgentRole.OPS,
            task="execute trade",
            context={"order_id": "456"},
            result=None,
            success=False,
            error="Timeout exceeded",
        )

        response = await agents_client.get(f"/api/agents/results/{agent_result.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert data["error"] == "Timeout exceeded"
        assert data["result"] is None

    @pytest.mark.asyncio
    async def test_get_result_includes_timing_fields(self, agents_client, agents_db_session):
        """Should include started_at, completed_at, and duration_ms."""
        started = datetime.now(timezone.utc)
        completed = started + timedelta(milliseconds=500)

        agent_result = await insert_agent_result(
            agents_db_session,
            role=AgentRole.RESEARCHER,
            task="research task",
            context={},
            result={},
            started_at=started,
            completed_at=completed,
            duration_ms=500,
        )

        response = await agents_client.get(f"/api/agents/results/{agent_result.id}")

        assert response.status_code == 200
        data = response.json()
        assert "started_at" in data
        assert "completed_at" in data
        assert data["duration_ms"] == 500
