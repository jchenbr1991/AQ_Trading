# backend/tests/api/test_health.py
"""Tests for health API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from src.health.models import ComponentStatus, HealthStatus, SystemHealth
from src.main import app


class TestHealthEndpoints:
    """Tests for /api/health endpoints."""

    def test_simple_health_returns_ok(self):
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_detailed_health_returns_components(self):
        client = TestClient(app)

        mock_health = SystemHealth(
            overall_status=ComponentStatus.HEALTHY,
            components=[
                HealthStatus(
                    component="redis",
                    status=ComponentStatus.HEALTHY,
                    latency_ms=5.0,
                    last_check=datetime.now(tz=timezone.utc),
                    message=None,
                ),
                HealthStatus(
                    component="market_data",
                    status=ComponentStatus.HEALTHY,
                    latency_ms=None,
                    last_check=datetime.now(tz=timezone.utc),
                    message=None,
                ),
            ],
            checked_at=datetime.now(tz=timezone.utc),
        )

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.check_all = AsyncMock(return_value=mock_health)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/detailed")

        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "healthy"
        assert len(data["components"]) == 2
        assert data["components"][0]["component"] == "redis"
        assert data["components"][0]["status"] == "healthy"

    def test_detailed_health_returns_503_when_degraded(self):
        client = TestClient(app)

        mock_health = SystemHealth(
            overall_status=ComponentStatus.DEGRADED,
            components=[
                HealthStatus(
                    component="redis",
                    status=ComponentStatus.DOWN,
                    latency_ms=None,
                    last_check=datetime.now(tz=timezone.utc),
                    message="Connection refused",
                ),
            ],
            checked_at=datetime.now(tz=timezone.utc),
        )

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.check_all = AsyncMock(return_value=mock_health)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/detailed")

        assert response.status_code == 503
        data = response.json()
        assert data["overall_status"] == "degraded"

    def test_component_health_endpoint(self):
        client = TestClient(app)

        mock_status = HealthStatus(
            component="redis",
            status=ComponentStatus.HEALTHY,
            latency_ms=5.0,
            last_check=datetime.now(tz=timezone.utc),
            message=None,
        )

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.get_component = AsyncMock(return_value=mock_status)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/component/redis")

        assert response.status_code == 200
        data = response.json()
        assert data["component"] == "redis"
        assert data["status"] == "healthy"

    def test_component_health_returns_404_for_unknown(self):
        client = TestClient(app)

        with patch("src.api.health.get_health_monitor") as mock_get:
            mock_monitor = AsyncMock()
            mock_monitor.get_component = AsyncMock(return_value=None)
            mock_get.return_value = mock_monitor

            response = client.get("/api/health/component/unknown")

        assert response.status_code == 404
