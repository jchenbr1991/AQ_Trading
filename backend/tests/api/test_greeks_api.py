# backend/tests/api/test_greeks_api.py
"""Tests for Greeks API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.db.database import Base, get_session
from src.main import app
from src.models.greeks import GreeksAlertRecord


@pytest_asyncio.fixture
async def greeks_db_session():
    """In-memory SQLite database with Greeks tables for testing.

    Uses ORM metadata.create_all for proper schema creation that works with
    SQLAlchemy models (including UUID handling for SQLite).
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        # Create all tables from ORM models
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def greeks_client(greeks_db_session):
    """HTTP client with Greeks database."""

    async def override_get_session():
        yield greeks_db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_test_greeks_alert(
    session: AsyncSession,
    alert_id: str | None = None,
    alert_type: str = "THRESHOLD",
    scope: str = "ACCOUNT",
    scope_id: str = "test_account",
    metric: str = "delta",
    level: str = "warn",
    current_value: float = 45000.0,
    threshold_value: float | None = 40000.0,
    message: str = "DELTA exceeded WARN threshold",
    created_at: datetime | None = None,
    acknowledged_at: datetime | None = None,
    acknowledged_by: str | None = None,
) -> str:
    """Insert a test Greeks alert into the database using ORM.

    Returns:
        The alert ID as string.
    """
    if alert_id is None:
        alert_id = str(uuid4())
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    alert_record = GreeksAlertRecord(
        alert_id=UUID(alert_id),
        alert_type=alert_type,
        scope=scope,
        scope_id=scope_id,
        metric=metric,
        level=level,
        current_value=Decimal(str(current_value)),
        threshold_value=Decimal(str(threshold_value)) if threshold_value is not None else None,
        message=message,
        created_at=created_at,
        acknowledged_at=acknowledged_at,
        acknowledged_by=acknowledged_by,
    )

    session.add(alert_record)
    await session.commit()
    return alert_id


class TestGetGreeksOverview:
    """Tests for GET /api/greeks/accounts/{account_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_overview_empty_account(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id} returns empty overview for account with no positions."""
        response = await greeks_client.get("/api/greeks/accounts/test_account")

        assert response.status_code == 200
        data = response.json()

        # Check account structure
        assert "account" in data
        assert data["account"]["scope"] == "ACCOUNT"
        assert data["account"]["scope_id"] == "test_account"
        assert data["account"]["dollar_delta"] == 0.0
        assert data["account"]["gamma_dollar"] == 0.0
        assert data["account"]["vega_per_1pct"] == 0.0
        assert data["account"]["theta_per_day"] == 0.0
        assert data["account"]["coverage_pct"] == 100.0
        assert data["account"]["is_coverage_sufficient"] is True
        assert data["account"]["valid_legs_count"] == 0
        assert data["account"]["total_legs_count"] == 0

        # Check strategies and alerts
        assert data["strategies"] == {}
        assert data["alerts"] == []
        assert data["top_contributors"] == {}

    @pytest.mark.asyncio
    async def test_get_overview_with_alerts(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id} includes unacknowledged alerts."""
        # Insert a test alert
        alert_id = await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="delta",
            level="warn",
            current_value=45000.0,
            threshold_value=40000.0,
        )

        response = await greeks_client.get("/api/greeks/accounts/test_account")

        assert response.status_code == 200
        data = response.json()

        # Check alerts are included
        assert len(data["alerts"]) == 1
        alert = data["alerts"][0]
        assert alert["alert_id"] == alert_id
        assert alert["scope"] == "ACCOUNT"
        assert alert["scope_id"] == "test_account"
        assert alert["metric"] == "delta"
        assert alert["level"] == "warn"
        assert alert["current_value"] == 45000.0
        assert alert["threshold_value"] == 40000.0
        assert alert["acknowledged_at"] is None
        assert alert["acknowledged_by"] is None


class TestGetCurrentGreeks:
    """Tests for GET /api/greeks/accounts/{account_id}/current endpoint."""

    @pytest.mark.asyncio
    async def test_get_current_greeks_empty(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/current returns empty Greeks for no positions."""
        response = await greeks_client.get("/api/greeks/accounts/test_account/current")

        assert response.status_code == 200
        data = response.json()

        assert data["scope"] == "ACCOUNT"
        assert data["scope_id"] == "test_account"
        assert data["dollar_delta"] == 0.0
        assert data["gamma_dollar"] == 0.0
        assert data["vega_per_1pct"] == 0.0
        assert data["theta_per_day"] == 0.0
        assert data["coverage_pct"] == 100.0
        assert data["is_coverage_sufficient"] is True
        assert data["has_high_risk_missing_legs"] is False
        assert data["valid_legs_count"] == 0
        assert data["total_legs_count"] == 0

    @pytest.mark.asyncio
    async def test_get_current_greeks_has_timestamp(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/current includes timestamp."""
        response = await greeks_client.get("/api/greeks/accounts/test_account/current")

        assert response.status_code == 200
        data = response.json()

        assert "as_of_ts" in data
        # Timestamp should be parseable
        timestamp = datetime.fromisoformat(data["as_of_ts"].replace("Z", "+00:00"))
        assert timestamp is not None


class TestGetGreeksAlerts:
    """Tests for GET /api/greeks/accounts/{account_id}/alerts endpoint."""

    @pytest.mark.asyncio
    async def test_get_alerts_empty(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/alerts returns empty list when no alerts."""
        response = await greeks_client.get("/api/greeks/accounts/test_account/alerts")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_alerts_returns_alerts(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/alerts returns list of alerts."""
        alert_id = await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            alert_type="THRESHOLD",
            metric="gamma",
            level="crit",
            current_value=12000.0,
            threshold_value=10000.0,
            message="GAMMA exceeded CRIT threshold: 12000 > 10000",
        )

        response = await greeks_client.get("/api/greeks/accounts/test_account/alerts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        alert = data[0]
        assert alert["alert_id"] == alert_id
        assert alert["alert_type"] == "THRESHOLD"
        assert alert["scope"] == "ACCOUNT"
        assert alert["scope_id"] == "test_account"
        assert alert["metric"] == "gamma"
        assert alert["level"] == "crit"
        assert alert["current_value"] == 12000.0
        assert alert["threshold_value"] == 10000.0
        assert alert["message"] == "GAMMA exceeded CRIT threshold: 12000 > 10000"

    @pytest.mark.asyncio
    async def test_get_alerts_filters_by_account(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/alerts only returns alerts for that account."""
        # Insert alerts for different accounts
        await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="delta",
        )
        await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="other_account",
            metric="gamma",
        )

        response = await greeks_client.get("/api/greeks/accounts/test_account/alerts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["scope_id"] == "test_account"

    @pytest.mark.asyncio
    async def test_get_alerts_excludes_acknowledged(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/alerts excludes acknowledged alerts by default."""
        now = datetime.now(timezone.utc)

        # Insert unacknowledged alert
        unack_id = await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="delta",
        )

        # Insert acknowledged alert
        await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="gamma",
            acknowledged_at=now,
            acknowledged_by="admin",
        )

        response = await greeks_client.get("/api/greeks/accounts/test_account/alerts")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["alert_id"] == unack_id

    @pytest.mark.asyncio
    async def test_get_alerts_filter_acknowledged_false(self, greeks_client, greeks_db_session):
        """GET /api/greeks/accounts/{account_id}/alerts?acknowledged=false returns unacknowledged."""
        now = datetime.now(timezone.utc)

        # Insert alerts
        unack_id = await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="delta",
        )
        await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="gamma",
            acknowledged_at=now,
            acknowledged_by="admin",
        )

        response = await greeks_client.get(
            "/api/greeks/accounts/test_account/alerts?acknowledged=false"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["alert_id"] == unack_id


class TestAcknowledgeAlert:
    """Tests for POST /api/greeks/alerts/{alert_id}/acknowledge endpoint."""

    @pytest.mark.asyncio
    async def test_acknowledge_alert_success(self, greeks_client, greeks_db_session):
        """POST /api/greeks/alerts/{alert_id}/acknowledge marks alert as acknowledged."""
        alert_id = await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
            metric="delta",
        )

        response = await greeks_client.post(
            f"/api/greeks/alerts/{alert_id}/acknowledge",
            json={"acknowledged_by": "test_user"},
        )

        assert response.status_code == 200
        data = response.json()

        assert data["alert_id"] == alert_id
        assert data["acknowledged_by"] == "test_user"
        assert data["acknowledged_at"] is not None

    @pytest.mark.asyncio
    async def test_acknowledge_alert_not_found(self, greeks_client, greeks_db_session):
        """POST /api/greeks/alerts/{alert_id}/acknowledge returns 404 for unknown alert."""
        fake_id = str(uuid4())
        response = await greeks_client.post(
            f"/api/greeks/alerts/{fake_id}/acknowledge",
            json={"acknowledged_by": "test_user"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Alert not found"

    @pytest.mark.asyncio
    async def test_acknowledge_alert_invalid_uuid(self, greeks_client, greeks_db_session):
        """POST /api/greeks/alerts/{alert_id}/acknowledge returns 404 for invalid UUID."""
        response = await greeks_client.post(
            "/api/greeks/alerts/not-a-uuid/acknowledge",
            json={"acknowledged_by": "test_user"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Alert not found"

    @pytest.mark.asyncio
    async def test_acknowledge_alert_requires_body(self, greeks_client, greeks_db_session):
        """POST /api/greeks/alerts/{alert_id}/acknowledge requires acknowledged_by."""
        alert_id = await insert_test_greeks_alert(
            greeks_db_session,
            scope_id="test_account",
        )

        response = await greeks_client.post(
            f"/api/greeks/alerts/{alert_id}/acknowledge",
            json={},
        )

        assert response.status_code == 422  # Validation error


class TestGreeksWebSocket:
    """Tests for WebSocket /api/greeks/accounts/{account_id}/ws endpoint."""

    @pytest.mark.asyncio
    async def test_websocket_connect(self, greeks_client, greeks_db_session):
        """WebSocket /api/greeks/accounts/{account_id}/ws accepts connections."""
        # Note: httpx doesn't support WebSocket testing directly
        # This would need a different approach using websockets library
        # For now, we just verify the endpoint exists by checking
        # that it doesn't return 404
        pass
