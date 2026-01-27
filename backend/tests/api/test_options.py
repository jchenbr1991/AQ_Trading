"""Tests for options API endpoints."""

from datetime import datetime, timezone
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
async def options_db_session():
    """In-memory SQLite database with alerts table for testing."""
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

        # Create idempotency_keys table for close position tests
        await conn.execute(
            text("""
            CREATE TABLE idempotency_keys (
                key TEXT PRIMARY KEY,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                response_data TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        )

        # Create positions table for close position tests
        await conn.execute(
            text("""
            CREATE TABLE positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                asset_type TEXT DEFAULT 'stock',
                strategy_id TEXT,
                status TEXT DEFAULT 'open',
                quantity INTEGER DEFAULT 0,
                avg_cost REAL DEFAULT 0,
                current_price REAL DEFAULT 0,
                strike REAL,
                expiry TEXT,
                put_call TEXT,
                opened_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                active_close_request_id TEXT,
                closed_at TEXT
            )
        """)
        )

        # Create accounts table (foreign key reference)
        await conn.execute(
            text("""
            CREATE TABLE accounts (
                account_id TEXT PRIMARY KEY,
                broker TEXT DEFAULT 'futu',
                currency TEXT DEFAULT 'USD',
                cash REAL DEFAULT 0,
                buying_power REAL DEFAULT 0,
                margin_used REAL DEFAULT 0,
                total_equity REAL DEFAULT 0,
                synced_at TEXT
            )
        """)
        )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def options_client(options_db_session):
    """HTTP client with options database."""

    async def override_get_session():
        yield options_db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_test_option_alert(
    session: AsyncSession,
    alert_id: str | None = None,
    account_id: str = "acc123",
    symbol: str = "AAPL",
    severity: int = 2,
    position_id: int = 1,
    strike: float = 150.0,
    put_call: str = "call",
    expiry_date: str = "2025-02-15",
    quantity: int = 10,
    days_to_expiry: int = 7,
    threshold_days: int = 7,
    created_at: datetime | None = None,
) -> str:
    """Insert a test option_expiring alert into the database.

    Returns:
        The alert ID
    """
    import json

    if alert_id is None:
        alert_id = str(uuid4())
    if created_at is None:
        created_at = datetime.now(timezone.utc)

    details = json.dumps(
        {
            "position_id": position_id,
            "strike": strike,
            "put_call": put_call,
            "expiry_date": expiry_date,
            "quantity": quantity,
            "days_to_expiry": days_to_expiry,
            "threshold_days": threshold_days,
        }
    )

    await session.execute(
        text("""
            INSERT INTO alerts (
                id, type, severity, fingerprint, dedupe_key, summary,
                details, entity_account_id, entity_symbol, suppressed_count,
                event_timestamp, created_at
            ) VALUES (
                :id, :type, :severity, :fingerprint, :dedupe_key, :summary,
                :details, :account_id, :symbol, :suppressed_count,
                :event_timestamp, :created_at
            )
        """),
        {
            "id": alert_id,
            "type": "option_expiring",
            "severity": severity,
            "fingerprint": f"fp-{alert_id[:8]}",
            "dedupe_key": f"dk-{alert_id}",
            "summary": f"Option {symbol} expiring in {days_to_expiry} days",
            "details": details,
            "account_id": account_id,
            "symbol": symbol,
            "suppressed_count": 0,
            "event_timestamp": created_at.isoformat(),
            "created_at": created_at.isoformat(),
        },
    )
    await session.commit()
    return alert_id


class TestGetExpiringAlerts:
    """Tests for GET /api/options/expiring endpoint."""

    @pytest.mark.asyncio
    async def test_get_expiring_alerts_returns_empty_list(self, options_client):
        """Should return empty list when no alerts exist."""
        response = await options_client.get("/api/options/expiring?account_id=acc123")

        assert response.status_code == 200
        data = response.json()
        assert data["alerts"] == []
        assert data["total"] == 0
        assert data["summary"]["critical_count"] == 0
        assert data["summary"]["warning_count"] == 0
        assert data["summary"]["info_count"] == 0

    @pytest.mark.asyncio
    async def test_get_expiring_alerts_returns_alerts(self, options_client, options_db_session):
        """Should return list of alerts when alerts exist."""
        alert_id = await insert_test_option_alert(
            options_db_session,
            account_id="acc123",
            symbol="AAPL",
            severity=1,  # critical
            days_to_expiry=3,
        )

        response = await options_client.get("/api/options/expiring?account_id=acc123")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["alerts"]) == 1

        alert = data["alerts"][0]
        assert alert["alert_id"] == alert_id
        assert alert["severity"] == "critical"
        assert alert["symbol"] == "AAPL"
        assert alert["days_to_expiry"] == 3

    @pytest.mark.asyncio
    async def test_get_expiring_alerts_filters_by_account(self, options_client, options_db_session):
        """Should only return alerts for specified account."""
        await insert_test_option_alert(options_db_session, account_id="acc123")
        await insert_test_option_alert(options_db_session, account_id="other_account")

        response = await options_client.get("/api/options/expiring?account_id=acc123")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_get_expiring_alerts_summary_counts(self, options_client, options_db_session):
        """Should correctly count alerts by severity."""
        await insert_test_option_alert(options_db_session, severity=1)  # critical
        await insert_test_option_alert(options_db_session, severity=2)  # warning
        await insert_test_option_alert(options_db_session, severity=2)  # warning
        await insert_test_option_alert(options_db_session, severity=3)  # info

        response = await options_client.get("/api/options/expiring?account_id=acc123")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4
        assert data["summary"]["critical_count"] == 1
        assert data["summary"]["warning_count"] == 2
        assert data["summary"]["info_count"] == 1

    @pytest.mark.asyncio
    async def test_get_expiring_alerts_requires_account_id(self, options_client):
        """Should return 422 when account_id is missing."""
        response = await options_client.get("/api/options/expiring")

        assert response.status_code == 422


class TestManualCheck:
    """Tests for POST /api/options/check-expirations endpoint."""

    @pytest.mark.asyncio
    async def test_manual_check_returns_placeholder(self, options_client):
        """Should return placeholder response for V1."""
        response = await options_client.post("/api/options/check-expirations?account_id=acc123")

        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == "manual-check-placeholder"
        assert data["positions_checked"] == 0
        assert data["alerts_created"] == 0
        assert data["alerts_deduplicated"] == 0
        assert len(data["errors"]) == 1  # Placeholder message

    @pytest.mark.asyncio
    async def test_manual_check_requires_account_id(self, options_client):
        """Should return 422 when account_id is missing."""
        response = await options_client.post("/api/options/check-expirations")

        assert response.status_code == 422


class TestAcknowledgeAlert:
    """Tests for POST /api/options/alerts/{alert_id}/acknowledge endpoint."""

    @pytest.mark.asyncio
    async def test_acknowledge_alert_not_found(self, options_client):
        """Should return 404 for unknown alert."""
        fake_id = str(uuid4())
        response = await options_client.post(f"/api/options/alerts/{fake_id}/acknowledge")

        assert response.status_code == 404
        assert response.json()["detail"] == "Alert not found"

    @pytest.mark.asyncio
    async def test_acknowledge_alert_success(self, options_client, options_db_session):
        """Should acknowledge existing alert."""
        alert_id = await insert_test_option_alert(options_db_session)

        response = await options_client.post(f"/api/options/alerts/{alert_id}/acknowledge")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == f"Alert {alert_id} acknowledged"
        assert data["acknowledged_at"] is not None


async def insert_test_position(
    session: AsyncSession,
    position_id: int | None = None,
    account_id: str = "acc123",
    symbol: str = "AAPL",
    quantity: int = 10,
    asset_type: str = "option",
    strike: float = 150.0,
    put_call: str = "call",
    expiry: str = "2025-02-15",
) -> int:
    """Insert a test position into the database.

    Returns:
        The position ID
    """
    now = datetime.now(timezone.utc).isoformat()

    if position_id is not None:
        await session.execute(
            text("""
                INSERT INTO positions (
                    id, account_id, symbol, asset_type, quantity,
                    avg_cost, current_price, strike, expiry, put_call,
                    opened_at, updated_at
                ) VALUES (
                    :id, :account_id, :symbol, :asset_type, :quantity,
                    :avg_cost, :current_price, :strike, :expiry, :put_call,
                    :opened_at, :updated_at
                )
            """),
            {
                "id": position_id,
                "account_id": account_id,
                "symbol": symbol,
                "asset_type": asset_type,
                "quantity": quantity,
                "avg_cost": 2.50,
                "current_price": 3.00,
                "strike": strike,
                "expiry": expiry,
                "put_call": put_call,
                "opened_at": now,
                "updated_at": now,
            },
        )
        await session.commit()
        return position_id
    else:
        result = await session.execute(
            text("""
                INSERT INTO positions (
                    account_id, symbol, asset_type, quantity,
                    avg_cost, current_price, strike, expiry, put_call,
                    opened_at, updated_at
                ) VALUES (
                    :account_id, :symbol, :asset_type, :quantity,
                    :avg_cost, :current_price, :strike, :expiry, :put_call,
                    :opened_at, :updated_at
                )
            """),
            {
                "account_id": account_id,
                "symbol": symbol,
                "asset_type": asset_type,
                "quantity": quantity,
                "avg_cost": 2.50,
                "current_price": 3.00,
                "strike": strike,
                "expiry": expiry,
                "put_call": put_call,
                "opened_at": now,
                "updated_at": now,
            },
        )
        await session.commit()
        # Get last inserted ID
        id_result = await session.execute(text("SELECT last_insert_rowid()"))
        return id_result.scalar()


class TestClosePosition:
    """Tests for POST /api/options/{position_id}/close endpoint."""

    @pytest.mark.asyncio
    async def test_close_position_requires_idempotency_key(self, options_client):
        """Should return 422 when Idempotency-Key header is missing."""
        response = await options_client.post(
            "/api/options/123/close",
            json={"reason": "test"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_close_position_not_found(self, options_client):
        """Should return 404 when position doesn't exist."""
        from unittest.mock import AsyncMock, patch

        with patch("src.api.options.IdempotencyService") as MockIdempotency:
            mock_service = AsyncMock()
            mock_service.get_cached_response.return_value = (False, None)
            MockIdempotency.return_value = mock_service

            response = await options_client.post(
                "/api/options/99999/close",
                json={"reason": "test close"},
                headers={"Idempotency-Key": "test-key-notfound"},
            )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_close_position_success(self, options_client, options_db_session):
        """Should return close order response for existing position."""
        from unittest.mock import AsyncMock, patch

        # Create a test position
        position_id = await insert_test_position(
            options_db_session,
            symbol="AAPL",
            quantity=10,
        )

        with patch("src.api.options.IdempotencyService") as MockIdempotency:
            mock_service = AsyncMock()
            mock_service.get_cached_response.return_value = (False, None)
            mock_service.store_key.return_value = None
            MockIdempotency.return_value = mock_service

            response = await options_client.post(
                f"/api/options/{position_id}/close",
                json={"reason": "expiring_soon"},
                headers={"Idempotency-Key": "test-key-123"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["order_id"].startswith(f"close-{position_id}-")
        assert "AAPL" in data["message"]
        assert "qty: 10" in data["message"]

    @pytest.mark.asyncio
    async def test_close_position_zero_quantity(self, options_client, options_db_session):
        """Should return 400 when position has zero quantity."""
        from unittest.mock import AsyncMock, patch

        # Create a position with zero quantity
        position_id = await insert_test_position(
            options_db_session,
            symbol="MSFT",
            quantity=0,
        )

        with patch("src.api.options.IdempotencyService") as MockIdempotency:
            mock_service = AsyncMock()
            mock_service.get_cached_response.return_value = (False, None)
            MockIdempotency.return_value = mock_service

            response = await options_client.post(
                f"/api/options/{position_id}/close",
                json={"reason": "test"},
                headers={"Idempotency-Key": "test-key-zero"},
            )

        assert response.status_code == 400
        assert "zero quantity" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_close_position_idempotent(self, options_client, options_db_session):
        """Should return cached response for duplicate requests."""
        from unittest.mock import AsyncMock, patch

        cached_response = {
            "success": True,
            "order_id": "close-1-cached",
            "message": "Close order created for AAPL (qty: 10)",
        }

        with patch("src.api.options.IdempotencyService") as MockIdempotency:
            mock_service = AsyncMock()
            mock_service.get_cached_response.return_value = (True, cached_response)
            MockIdempotency.return_value = mock_service

            response = await options_client.post(
                "/api/options/1/close",
                json={"reason": "test"},
                headers={"Idempotency-Key": "already-used-key"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["order_id"] == "close-1-cached"
