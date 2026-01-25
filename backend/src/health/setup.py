# backend/src/health/setup.py
"""Health monitoring initialization."""

from datetime import datetime, timezone

from src.api.health import set_health_monitor
from src.health.checkers import MarketDataHealthChecker
from src.health.monitor import HealthMonitor


class MockMarketDataService:
    """Mock market data service for development."""

    def __init__(self):
        self.last_update = datetime.now(tz=timezone.utc)


def init_health_monitor() -> HealthMonitor:
    """Initialize the health monitor with configured checkers.

    In production, this would use real Redis/PostgreSQL/MarketData services.
    For development, we use mocks.

    Returns:
        Configured HealthMonitor instance
    """
    checkers = []

    # MarketData checker (using mock for now)
    mock_market_data = MockMarketDataService()
    checkers.append(MarketDataHealthChecker(mock_market_data, stale_threshold_seconds=30))

    # Create and register the monitor
    monitor = HealthMonitor(checkers=checkers)
    set_health_monitor(monitor)

    return monitor
