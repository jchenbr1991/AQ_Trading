# backend/tests/api/test_alerts.py
"""Tests for Alerts API endpoints."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.db.database import get_session
from src.main import app


@pytest_asyncio.fixture
async def alerts_db_session():
    """In-memory SQLite database with alerts tables for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        # Create alerts table (SQLite compatible)
        await conn.execute(
            text("""
            CREATE TABLE alerts (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                severity INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                dedupe_key TEXT NOT NULL UNIQUE,
                summary TEXT NOT NULL,
                details TEXT,
                entity_account_id TEXT,
                entity_symbol TEXT,
                entity_strategy_id TEXT,
                suppressed_count INTEGER DEFAULT 0,
                event_timestamp TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        )

        # Create alert_deliveries table
        await conn.execute(
            text("""
            CREATE TABLE alert_deliveries (
                id TEXT PRIMARY KEY,
                alert_id TEXT NOT NULL REFERENCES alerts(id),
                channel TEXT NOT NULL,
                destination_key TEXT NOT NULL,
                attempt_number INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending',
                response_code INTEGER,
                error_message TEXT,
                sent_at TEXT,
                created_at TEXT NOT NULL
            )
        """)
        )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def alerts_client(alerts_db_session):
    """HTTP client with alerts database."""

    async def override_get_session():
        yield alerts_db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_test_alert(
    session: AsyncSession,
    alert_id: str | None = None,
    alert_type: str = "order_rejected",
    severity: int = 2,
    summary: str = "Test alert",
    fingerprint: str | None = None,
    dedupe_key: str | None = None,
    account_id: str | None = None,
    symbol: str | None = None,
    suppressed_count: int = 0,
    event_timestamp: datetime | None = None,
    created_at: datetime | None = None,
) -> str:
    """Insert a test alert into the database.

    Returns:
        The alert ID
    """
    if alert_id is None:
        alert_id = str(uuid4())
    if fingerprint is None:
        fingerprint = f"fp-{alert_id[:8]}"
    if dedupe_key is None:
        dedupe_key = f"dk-{alert_id}"
    if event_timestamp is None:
        event_timestamp = datetime.now(timezone.utc)
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    await session.execute(
        text("""
            INSERT INTO alerts (
                id, type, severity, fingerprint, dedupe_key, summary,
                entity_account_id, entity_symbol, suppressed_count,
                event_timestamp, created_at
            ) VALUES (
                :id, :type, :severity, :fingerprint, :dedupe_key, :summary,
                :account_id, :symbol, :suppressed_count,
                :event_timestamp, :created_at
            )
        """),
        {
            "id": alert_id,
            "type": alert_type,
            "severity": severity,
            "fingerprint": fingerprint,
            "dedupe_key": dedupe_key,
            "summary": summary,
            "account_id": account_id,
            "symbol": symbol,
            "suppressed_count": suppressed_count,
            "event_timestamp": event_timestamp.isoformat(),
            "created_at": created_at.isoformat(),
        },
    )
    await session.commit()
    return alert_id


async def insert_test_delivery(
    session: AsyncSession,
    alert_id: str,
    delivery_id: str | None = None,
    channel: str = "email",
    destination_key: str = "test@example.com",
    attempt_number: int = 1,
    status: str = "pending",
    response_code: int | None = None,
    error_message: str | None = None,
    sent_at: datetime | None = None,
    created_at: datetime | None = None,
) -> str:
    """Insert a test delivery into the database.

    Returns:
        The delivery ID
    """
    if delivery_id is None:
        delivery_id = str(uuid4())
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    await session.execute(
        text("""
            INSERT INTO alert_deliveries (
                id, alert_id, channel, destination_key, attempt_number,
                status, response_code, error_message, sent_at, created_at
            ) VALUES (
                :id, :alert_id, :channel, :destination_key, :attempt_number,
                :status, :response_code, :error_message, :sent_at, :created_at
            )
        """),
        {
            "id": delivery_id,
            "alert_id": alert_id,
            "channel": channel,
            "destination_key": destination_key,
            "attempt_number": attempt_number,
            "status": status,
            "response_code": response_code,
            "error_message": error_message,
            "sent_at": sent_at.isoformat() if sent_at else None,
            "created_at": created_at.isoformat(),
        },
    )
    await session.commit()
    return delivery_id


class TestListAlerts:
    """Tests for GET /api/alerts endpoint."""

    @pytest.mark.asyncio
    async def test_list_alerts_empty(self, alerts_client):
        """GET /api/alerts returns empty list when no alerts."""
        response = await alerts_client.get("/api/alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["alerts"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    @pytest.mark.asyncio
    async def test_list_alerts_returns_alerts(self, alerts_client, alerts_db_session):
        """GET /api/alerts returns list of alerts."""
        # Insert test alerts
        alert_id = await insert_test_alert(
            alerts_db_session,
            alert_type="order_rejected",
            severity=2,
            summary="Order rejected: insufficient funds",
            account_id="acc123",
            symbol="AAPL",
        )

        response = await alerts_client.get("/api/alerts")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["alerts"]) == 1
        alert = data["alerts"][0]
        assert alert["id"] == alert_id
        assert alert["type"] == "order_rejected"
        assert alert["severity"] == 2
        assert alert["summary"] == "Order rejected: insufficient funds"
        assert alert["entity_account_id"] == "acc123"
        assert alert["entity_symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_list_alerts_pagination(self, alerts_client, alerts_db_session):
        """GET /api/alerts supports pagination."""
        # Insert multiple alerts
        for i in range(10):
            await insert_test_alert(
                alerts_db_session,
                summary=f"Alert {i}",
            )

        # Get first page
        response = await alerts_client.get("/api/alerts?limit=3&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["alerts"]) == 3
        assert data["offset"] == 0
        assert data["limit"] == 3

        # Get second page
        response = await alerts_client.get("/api/alerts?limit=3&offset=3")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["alerts"]) == 3
        assert data["offset"] == 3

    @pytest.mark.asyncio
    async def test_list_alerts_filter_by_severity(self, alerts_client, alerts_db_session):
        """GET /api/alerts filters by severity."""
        await insert_test_alert(alerts_db_session, severity=1, summary="SEV1 alert")
        await insert_test_alert(alerts_db_session, severity=2, summary="SEV2 alert")
        await insert_test_alert(alerts_db_session, severity=3, summary="SEV3 alert")

        response = await alerts_client.get("/api/alerts?severity=1")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["severity"] == 1

    @pytest.mark.asyncio
    async def test_list_alerts_filter_by_type(self, alerts_client, alerts_db_session):
        """GET /api/alerts filters by type."""
        await insert_test_alert(alerts_db_session, alert_type="order_rejected")
        await insert_test_alert(alerts_db_session, alert_type="kill_switch_activated")
        await insert_test_alert(alerts_db_session, alert_type="order_rejected")

        response = await alerts_client.get("/api/alerts?type=kill_switch_activated")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["type"] == "kill_switch_activated"

    @pytest.mark.asyncio
    async def test_list_alerts_combined_filters(self, alerts_client, alerts_db_session):
        """GET /api/alerts combines severity and type filters."""
        await insert_test_alert(alerts_db_session, alert_type="order_rejected", severity=1)
        await insert_test_alert(alerts_db_session, alert_type="order_rejected", severity=2)
        await insert_test_alert(alerts_db_session, alert_type="kill_switch_activated", severity=1)

        response = await alerts_client.get("/api/alerts?severity=1&type=order_rejected")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["alerts"]) == 1
        assert data["alerts"][0]["severity"] == 1
        assert data["alerts"][0]["type"] == "order_rejected"

    @pytest.mark.asyncio
    async def test_list_alerts_limit_max_100(self, alerts_client):
        """GET /api/alerts enforces max limit of 100."""
        response = await alerts_client.get("/api/alerts?limit=200")

        assert response.status_code == 422  # Validation error


class TestGetAlertStats:
    """Tests for GET /api/alerts/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, alerts_client):
        """GET /api/alerts/stats returns empty stats when no alerts."""
        response = await alerts_client.get("/api/alerts/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_24h"] == 0
        assert data["by_severity"] == {}
        assert data["by_type"] == {}
        assert data["delivery_success_rate"] == 1.0

    @pytest.mark.asyncio
    async def test_get_stats_with_alerts(self, alerts_client, alerts_db_session):
        """GET /api/alerts/stats returns statistics."""
        now = datetime.now(timezone.utc)

        # Insert alerts within last 24h
        await insert_test_alert(
            alerts_db_session, severity=1, alert_type="kill_switch_activated", created_at=now
        )
        await insert_test_alert(
            alerts_db_session, severity=2, alert_type="order_rejected", created_at=now
        )
        await insert_test_alert(
            alerts_db_session, severity=2, alert_type="order_rejected", created_at=now
        )
        await insert_test_alert(
            alerts_db_session, severity=3, alert_type="order_filled", created_at=now
        )

        response = await alerts_client.get("/api/alerts/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_24h"] == 4
        assert data["by_severity"] == {"SEV1": 1, "SEV2": 2, "SEV3": 1}
        assert data["by_type"] == {
            "kill_switch_activated": 1,
            "order_rejected": 2,
            "order_filled": 1,
        }

    @pytest.mark.asyncio
    async def test_get_stats_excludes_old_alerts(self, alerts_client, alerts_db_session):
        """GET /api/alerts/stats only counts alerts from last 24h."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=25)

        # Insert one recent and one old alert
        await insert_test_alert(alerts_db_session, severity=1, created_at=now)
        await insert_test_alert(alerts_db_session, severity=2, created_at=old)

        response = await alerts_client.get("/api/alerts/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_24h"] == 1
        assert data["by_severity"] == {"SEV1": 1}

    @pytest.mark.asyncio
    async def test_get_stats_delivery_success_rate(self, alerts_client, alerts_db_session):
        """GET /api/alerts/stats calculates delivery success rate."""
        now = datetime.now(timezone.utc)

        # Insert an alert
        alert_id = await insert_test_alert(alerts_db_session, created_at=now)

        # Insert deliveries: 3 sent, 1 failed
        await insert_test_delivery(alerts_db_session, alert_id, status="sent", created_at=now)
        await insert_test_delivery(alerts_db_session, alert_id, status="sent", created_at=now)
        await insert_test_delivery(alerts_db_session, alert_id, status="sent", created_at=now)
        await insert_test_delivery(alerts_db_session, alert_id, status="failed", created_at=now)

        response = await alerts_client.get("/api/alerts/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["delivery_success_rate"] == 0.75  # 3/4


class TestGetAlertDeliveries:
    """Tests for GET /api/alerts/{alert_id}/deliveries endpoint."""

    @pytest.mark.asyncio
    async def test_get_deliveries_not_found(self, alerts_client):
        """GET /api/alerts/{alert_id}/deliveries returns 404 for unknown alert."""
        fake_id = str(uuid4())
        response = await alerts_client.get(f"/api/alerts/{fake_id}/deliveries")

        assert response.status_code == 404
        assert response.json()["detail"] == "Alert not found"

    @pytest.mark.asyncio
    async def test_get_deliveries_empty(self, alerts_client, alerts_db_session):
        """GET /api/alerts/{alert_id}/deliveries returns empty list when no deliveries."""
        alert_id = await insert_test_alert(alerts_db_session)

        response = await alerts_client.get(f"/api/alerts/{alert_id}/deliveries")

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_deliveries_returns_list(self, alerts_client, alerts_db_session):
        """GET /api/alerts/{alert_id}/deliveries returns delivery list."""
        now = datetime.now(timezone.utc)
        alert_id = await insert_test_alert(alerts_db_session)

        # Insert deliveries
        delivery_id = await insert_test_delivery(
            alerts_db_session,
            alert_id,
            channel="email",
            destination_key="admin@example.com",
            attempt_number=1,
            status="sent",
            response_code=200,
            sent_at=now,
            created_at=now,
        )

        response = await alerts_client.get(f"/api/alerts/{alert_id}/deliveries")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1

        delivery = data[0]
        assert delivery["id"] == delivery_id
        assert delivery["channel"] == "email"
        assert delivery["destination_key"] == "admin@example.com"
        assert delivery["attempt_number"] == 1
        assert delivery["status"] == "sent"
        assert delivery["response_code"] == 200
        assert delivery["sent_at"] is not None
        assert delivery["error_message"] is None

    @pytest.mark.asyncio
    async def test_get_deliveries_multiple(self, alerts_client, alerts_db_session):
        """GET /api/alerts/{alert_id}/deliveries returns multiple deliveries."""
        now = datetime.now(timezone.utc)
        alert_id = await insert_test_alert(alerts_db_session)

        # Insert multiple deliveries with different attempts
        await insert_test_delivery(
            alerts_db_session,
            alert_id,
            channel="email",
            attempt_number=1,
            status="failed",
            error_message="Connection timeout",
            created_at=now,
        )
        await insert_test_delivery(
            alerts_db_session,
            alert_id,
            channel="email",
            attempt_number=2,
            status="sent",
            response_code=200,
            sent_at=now + timedelta(minutes=1),
            created_at=now + timedelta(minutes=1),
        )

        response = await alerts_client.get(f"/api/alerts/{alert_id}/deliveries")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Should be ordered by attempt_number
        assert data[0]["attempt_number"] == 1
        assert data[0]["status"] == "failed"
        assert data[0]["error_message"] == "Connection timeout"
        assert data[1]["attempt_number"] == 2
        assert data[1]["status"] == "sent"
