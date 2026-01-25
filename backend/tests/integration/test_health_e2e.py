# backend/tests/integration/test_health_e2e.py
"""End-to-end integration tests for health monitoring."""

import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    """Create a TestClient with proper lifecycle management.

    Using TestClient as context manager ensures startup/shutdown events fire,
    which initializes the health monitor with configured checkers.
    """
    with TestClient(app) as c:
        yield c


class TestHealthE2E:
    """End-to-end health monitoring tests."""

    def test_simple_health_endpoint(self, client):
        """Simple /health endpoint should always return healthy."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_detailed_health_endpoint(self, client):
        """Detailed health should return component statuses."""
        response = client.get("/api/health/detailed")

        # Returns 200 (healthy) - we have mock service that's always healthy
        assert response.status_code == 200

        data = response.json()
        assert "overall_status" in data
        assert "components" in data
        assert "checked_at" in data
        assert data["overall_status"] == "healthy"

    def test_component_health_endpoint(self, client):
        """Should be able to check individual component health."""
        # Check market_data component (the one we initialized)
        response = client.get("/api/health/component/market_data")
        assert response.status_code == 200

        data = response.json()
        assert data["component"] == "market_data"
        assert data["status"] == "healthy"

    def test_unknown_component_returns_404(self, client):
        """Unknown component should return 404."""
        response = client.get("/api/health/component/nonexistent")
        assert response.status_code == 404
