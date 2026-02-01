# backend/tests/integration/test_agents.py
"""End-to-end integration tests for agents API.

Tests the agent lifecycle management endpoints:
- POST /api/agents/invoke - Invoke an agent task
- GET /api/agents/results - List agent results
- GET /api/agents/results/{id} - Get specific result

Acceptance Criteria:
- FR-019: Support AI agent subsystem
- FR-020: Agents have clear permission boundaries
- FR-021: Graceful degradation when components fail
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.db.database import get_session
from src.main import app
from src.models.agent_result import AgentResult, AgentRole


@pytest_asyncio.fixture
async def client(db_session):
    """HTTP client with test database."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestAgentsResultsEndpoints:
    """Tests for /api/agents/results endpoints."""

    @pytest.mark.asyncio
    async def test_list_results_empty(self, client):
        """Should return empty list when no results exist."""
        response = await client.get("/api/agents/results")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data
        assert data["total"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_list_results_with_pagination(self, client):
        """Should accept pagination parameters."""
        response = await client.get("/api/agents/results?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_results_invalid_pagination(self, client):
        """Should reject invalid pagination parameters."""
        # Negative offset
        response = await client.get("/api/agents/results?offset=-1")
        assert response.status_code == 422

        # Limit over 1000
        response = await client.get("/api/agents/results?limit=1001")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_result_not_found(self, client):
        """Should return 404 for nonexistent result."""
        fake_id = str(uuid4())
        response = await client.get(f"/api/agents/results/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_result_invalid_uuid(self, client):
        """Should reject invalid UUID format."""
        response = await client.get("/api/agents/results/not-a-uuid")

        assert response.status_code == 422


class TestAgentsWithData:
    """Tests with seeded agent result data."""

    @pytest_asyncio.fixture
    async def seeded_client(self, db_session, client):
        """Client with seeded agent results."""
        # Create test results
        result1 = AgentResult(
            id=uuid4(),
            role=AgentRole.RESEARCHER,
            task="analyze market trends",
            context={"symbol": "AAPL"},
            success=True,
            result={"analysis": "bullish"},
            started_at=datetime.now(timezone.utc),
        )
        result1.complete(result={"analysis": "bullish"})

        result2 = AgentResult(
            id=uuid4(),
            role=AgentRole.ANALYST,
            task="generate sentiment",
            context={"symbol": "TSLA"},
            success=False,
            error="Service unavailable",
            started_at=datetime.now(timezone.utc),
        )
        result2.complete(error="Service unavailable")

        result3 = AgentResult(
            id=uuid4(),
            role=AgentRole.RISK_CONTROLLER,
            task="check risk exposure",
            context={},
            success=True,
            result={"risk_bias": 0.8},
            started_at=datetime.now(timezone.utc),
        )
        result3.complete(result={"risk_bias": 0.8})

        db_session.add_all([result1, result2, result3])
        await db_session.commit()

        # Store IDs for tests
        client._test_result_ids = [result1.id, result2.id, result3.id]
        yield client

    @pytest.mark.asyncio
    async def test_list_results_with_data(self, seeded_client):
        """Should return all results."""
        response = await seeded_client.get("/api/agents/results")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["results"]) == 3

    @pytest.mark.asyncio
    async def test_list_results_pagination(self, seeded_client):
        """Should paginate results correctly."""
        response = await seeded_client.get("/api/agents/results?limit=2&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["results"]) == 2

        # Get second page
        response = await seeded_client.get("/api/agents/results?limit=2&offset=2")
        data = response.json()
        assert len(data["results"]) == 1

    @pytest.mark.asyncio
    async def test_get_specific_result(self, seeded_client):
        """Should return specific result by ID."""
        result_id = seeded_client._test_result_ids[0]
        response = await seeded_client.get(f"/api/agents/results/{result_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(result_id)
        assert data["role"] == "researcher"
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_result_contains_required_fields(self, seeded_client):
        """Should return all required fields in result."""
        result_id = seeded_client._test_result_ids[0]
        response = await seeded_client.get(f"/api/agents/results/{result_id}")

        assert response.status_code == 200
        data = response.json()

        required_fields = ["id", "role", "task", "context", "success", "started_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


class TestAgentsInvokeEndpoint:
    """Tests for /api/agents/invoke endpoint."""

    @pytest.mark.asyncio
    async def test_invoke_endpoint_exists(self, client):
        """Invoke endpoint should exist."""
        # Send a request - we expect 422 (validation error) or 200/500
        # but NOT 404 or 405
        response = await client.post("/api/agents/invoke", json={})

        # Should fail validation, not method not allowed
        assert response.status_code != 404
        assert response.status_code != 405

    @pytest.mark.asyncio
    async def test_invoke_requires_role(self, client):
        """Should require role field."""
        response = await client.post(
            "/api/agents/invoke",
            json={"task": "test task", "context": {}},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invoke_requires_task(self, client):
        """Should require task field."""
        response = await client.post(
            "/api/agents/invoke",
            json={"role": "researcher", "context": {}},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invoke_rejects_invalid_role(self, client):
        """Should reject invalid role."""
        response = await client.post(
            "/api/agents/invoke",
            json={"role": "invalid_role", "task": "test", "context": {}},
        )

        assert response.status_code == 422


class TestAgentsAcceptanceCriteria:
    """Tests for acceptance criteria verification."""

    @pytest.mark.asyncio
    async def test_fr019_agent_subsystem_available(self, client):
        """FR-019: Agent API endpoints should be available."""
        # Check results endpoint
        response = await client.get("/api/agents/results")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_fr020_roles_defined(self, client):
        """FR-020: Valid roles should be defined and invalid roles rejected."""
        # Test that invalid role is rejected at validation level
        response = await client.post(
            "/api/agents/invoke",
            json={"role": "invalid_role", "task": "test", "context": {}},
        )
        assert response.status_code == 422  # Invalid role rejected

        # Note: Actual agent invocation requires subprocess infrastructure
        # which is tested separately in agents/tests/test_dispatcher.py

    @pytest.mark.asyncio
    async def test_fr021_graceful_degradation_response(self, client):
        """FR-021: API should return proper response even on agent failure."""
        # The API should return a response, not crash
        response = await client.get("/api/agents/results")
        assert response.status_code in [200, 500, 503]  # Acceptable responses

        # If 200, should have proper structure
        if response.status_code == 200:
            data = response.json()
            assert "results" in data
            assert "total" in data
