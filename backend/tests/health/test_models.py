"""Tests for health monitoring models."""

from datetime import datetime, timezone

from src.health.models import ComponentStatus, HealthStatus, SystemHealth


class TestComponentStatus:
    """Tests for ComponentStatus enum."""

    def test_healthy_value(self):
        assert ComponentStatus.HEALTHY.value == "healthy"

    def test_degraded_value(self):
        assert ComponentStatus.DEGRADED.value == "degraded"

    def test_down_value(self):
        assert ComponentStatus.DOWN.value == "down"

    def test_unknown_value(self):
        assert ComponentStatus.UNKNOWN.value == "unknown"


class TestHealthStatus:
    """Tests for HealthStatus dataclass."""

    def test_create_healthy_status(self):
        status = HealthStatus(
            component="redis",
            status=ComponentStatus.HEALTHY,
            latency_ms=5.2,
            last_check=datetime.now(tz=timezone.utc),
            message=None,
        )
        assert status.component == "redis"
        assert status.status == ComponentStatus.HEALTHY
        assert status.latency_ms == 5.2
        assert status.message is None

    def test_create_down_status_with_message(self):
        status = HealthStatus(
            component="postgres",
            status=ComponentStatus.DOWN,
            latency_ms=None,
            last_check=datetime.now(tz=timezone.utc),
            message="Connection refused",
        )
        assert status.status == ComponentStatus.DOWN
        assert status.message == "Connection refused"
        assert status.latency_ms is None


class TestSystemHealth:
    """Tests for SystemHealth aggregate."""

    def test_all_healthy_means_system_healthy(self):
        now = datetime.now(tz=timezone.utc)
        components = [
            HealthStatus("redis", ComponentStatus.HEALTHY, 5.0, now, None),
            HealthStatus("postgres", ComponentStatus.HEALTHY, 10.0, now, None),
        ]
        system = SystemHealth(
            overall_status=ComponentStatus.HEALTHY,
            components=components,
            checked_at=now,
        )
        assert system.overall_status == ComponentStatus.HEALTHY

    def test_one_down_means_system_degraded(self):
        now = datetime.now(tz=timezone.utc)
        components = [
            HealthStatus("redis", ComponentStatus.HEALTHY, 5.0, now, None),
            HealthStatus("postgres", ComponentStatus.DOWN, None, now, "Connection refused"),
        ]
        system = SystemHealth(
            overall_status=ComponentStatus.DEGRADED,
            components=components,
            checked_at=now,
        )
        assert system.overall_status == ComponentStatus.DEGRADED
