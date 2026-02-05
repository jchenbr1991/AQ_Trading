# backend/tests/api/test_strategies_api.py
"""Tests for strategy management API endpoints.

Implements T041: Strategy start/stop API endpoints for paper mode.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.strategies import clear_running_strategies
from src.main import app


@pytest.fixture
def client():
    """Create a TestClient and clean up running strategies between tests."""
    clear_running_strategies()
    with TestClient(app) as c:
        yield c
    clear_running_strategies()


class TestStrategiesAPI:
    """Tests for /api/strategies endpoints."""

    def test_list_strategies_empty(self, client):
        """Test listing strategies when none are running."""
        response = client.get("/api/strategies")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        # Should discover trend_breakout from config
        names = [s["name"] for s in data]
        assert "trend_breakout" in names

        # All should be stopped
        for strategy in data:
            assert strategy["status"] == "stopped"

    def test_get_strategy_status_stopped(self, client):
        """Test getting status of a non-running strategy."""
        response = client.get("/api/strategies/trend_breakout/status")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "trend_breakout"
        assert data["status"] == "stopped"
        assert data["mode"] is None

    def test_start_strategy_paper_mode(self, client):
        """Test starting a strategy in paper mode."""
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "paper"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "trend_breakout"
        assert data["status"] == "running"
        assert data["mode"] == "paper"
        assert data["account_id"] == "PAPER001"
        assert data["started_at"] is not None
        assert "AAPL" in data["symbols"]

    def test_start_strategy_already_running(self, client):
        """Test that starting an already running strategy fails."""
        # Start the strategy
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "paper"},
        )
        assert response.status_code == 200

        # Try to start again
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "paper"},
        )

        assert response.status_code == 400
        assert "already running" in response.json()["detail"]

    def test_stop_strategy(self, client):
        """Test stopping a running strategy."""
        # Start the strategy first
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "paper"},
        )
        assert response.status_code == 200

        # Stop the strategy
        response = client.post("/api/strategies/trend_breakout/stop")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "trend_breakout"
        assert data["status"] == "stopped"

    def test_stop_strategy_not_running(self, client):
        """Test that stopping a non-running strategy fails."""
        response = client.post("/api/strategies/trend_breakout/stop")

        assert response.status_code == 404
        assert "not running" in response.json()["detail"]

    def test_get_strategy_status_running(self, client):
        """Test getting status of a running strategy."""
        # Start the strategy
        client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "paper"},
        )

        # Get status
        response = client.get("/api/strategies/trend_breakout/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["mode"] == "paper"

    def test_start_strategy_not_found(self, client):
        """Test starting a non-existent strategy."""
        response = client.post(
            "/api/strategies/nonexistent_strategy/start",
            json={"mode": "paper"},
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_start_strategy_live_mode_not_enabled(self, client):
        """Test that live mode is rejected when not enabled."""
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "live"},
        )

        assert response.status_code == 400
        assert "not enabled" in response.json()["detail"]

    def test_start_strategy_backtest_mode(self, client):
        """Test starting a strategy in backtest mode."""
        # Backtest mode doesn't require enabled check
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "backtest"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "backtest"
        assert data["status"] == "running"

    def test_list_strategies_with_running(self, client):
        """Test listing strategies when one is running."""
        # Start a strategy
        client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "paper"},
        )

        # List strategies
        response = client.get("/api/strategies")

        assert response.status_code == 200
        data = response.json()

        # Find the running strategy
        running_strategies = [s for s in data if s["status"] == "running"]
        assert len(running_strategies) == 1
        assert running_strategies[0]["name"] == "trend_breakout"
        assert running_strategies[0]["mode"] == "paper"


class TestStrategiesAPIValidation:
    """Tests for request validation."""

    def test_start_strategy_invalid_mode(self, client):
        """Test that invalid mode values are rejected."""
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={"mode": "invalid_mode"},
        )

        assert response.status_code == 422  # Validation error

    def test_start_strategy_missing_mode(self, client):
        """Test that missing mode is rejected."""
        response = client.post(
            "/api/strategies/trend_breakout/start",
            json={},
        )

        assert response.status_code == 422  # Validation error
