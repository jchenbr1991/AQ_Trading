"""Tests for close_position API endpoint (Phase 1).

Tests the new close_position implementation that creates CloseRequest + OutboxEvent
atomically, replacing the old IdempotencyService-based approach.
"""

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
async def close_position_db():
    """In-memory SQLite database with required tables for close position tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
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

        # Create positions table
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

        # Create close_requests table
        await conn.execute(
            text("""
            CREATE TABLE close_requests (
                id TEXT PRIMARY KEY,
                position_id INTEGER NOT NULL,
                idempotency_key TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                target_qty INTEGER NOT NULL,
                filled_qty INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                created_at TEXT NOT NULL,
                submitted_at TEXT,
                completed_at TEXT
            )
        """)
        )

        # Create outbox_events table
        await conn.execute(
            text("""
            CREATE TABLE outbox_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                processed_at TEXT,
                retry_count INTEGER DEFAULT 0
            )
        """)
        )

        # Create idempotency_keys table (for backwards compatibility)
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

        # Insert a test account
        await conn.execute(
            text("""
                INSERT INTO accounts (account_id, broker, currency)
                VALUES ('ACC001', 'futu', 'USD')
            """)
        )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def close_position_client(close_position_db):
    """HTTP client with close position test database."""

    async def override_get_session():
        yield close_position_db

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_open_position(
    session: AsyncSession,
    account_id: str = "ACC001",
    symbol: str = "AAPL240119C00150000",
    asset_type: str = "option",
    quantity: int = 10,
    status: str = "open",
) -> int:
    """Insert an open position for testing.

    Returns:
        The position ID
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()

    result = await session.execute(
        text("""
            INSERT INTO positions (
                account_id, symbol, asset_type, quantity, status,
                avg_cost, current_price, opened_at, updated_at
            ) VALUES (
                :account_id, :symbol, :asset_type, :quantity, :status,
                :avg_cost, :current_price, :opened_at, :updated_at
            )
        """),
        {
            "account_id": account_id,
            "symbol": symbol,
            "asset_type": asset_type,
            "quantity": quantity,
            "status": status,
            "avg_cost": 2.50,
            "current_price": 3.00,
            "opened_at": now,
            "updated_at": now,
        },
    )
    await session.commit()
    # Get last inserted ID
    id_result = await session.execute(text("SELECT last_insert_rowid()"))
    return id_result.scalar()


class TestClosePositionPhase1:
    """Tests for close_position API endpoint - Phase 1 (CloseRequest + OutboxEvent)."""

    @pytest.mark.asyncio
    async def test_close_position_creates_close_request(
        self, close_position_client, close_position_db
    ):
        """Should create CloseRequest and return pending status."""
        position_id = await insert_open_position(close_position_db, quantity=10)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["close_request_id"] is not None
        assert data["position_status"] == "closing"
        assert data["close_request_status"] == "pending"
        assert data["target_qty"] == 10

    @pytest.mark.asyncio
    async def test_close_position_creates_outbox_event(
        self, close_position_client, close_position_db
    ):
        """Should create OutboxEvent for async processing."""
        position_id = await insert_open_position(close_position_db, quantity=5)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 201

        # Verify outbox event was created
        result = await close_position_db.execute(
            text("SELECT event_type, payload, status FROM outbox_events")
        )
        row = result.fetchone()
        assert row is not None
        assert row[0] == "SUBMIT_CLOSE_ORDER"
        assert row[2] == "pending"

    @pytest.mark.asyncio
    async def test_close_position_idempotent(self, close_position_client, close_position_db):
        """Should return same response for same idempotency key."""
        position_id = await insert_open_position(close_position_db)
        key = str(uuid4())

        response1 = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": key},
        )
        response2 = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": key},
        )

        assert response1.status_code == 201
        assert response2.status_code == 200  # Idempotent replay
        assert response1.json()["close_request_id"] == response2.json()["close_request_id"]

    @pytest.mark.asyncio
    async def test_close_position_rejects_different_key_while_closing(
        self, close_position_client, close_position_db
    ):
        """Should reject different key while position is CLOSING."""
        position_id = await insert_open_position(close_position_db)

        response1 = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )
        assert response1.status_code == 201

        response2 = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response2.status_code == 409
        assert response2.json()["detail"]["error"] == "position_already_closing"

    @pytest.mark.asyncio
    async def test_close_position_not_found(self, close_position_client):
        """Should return 404 for nonexistent position."""
        response = await close_position_client.post(
            "/api/options/99999/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_close_position_zero_quantity(self, close_position_client, close_position_db):
        """Should reject position with zero quantity."""
        position_id = await insert_open_position(
            close_position_db,
            symbol="AAPL",
            asset_type="option",
            quantity=0,
        )

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 400
        assert "zero quantity" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_close_position_requires_idempotency_key(
        self, close_position_client, close_position_db
    ):
        """Should require Idempotency-Key header."""
        position_id = await insert_open_position(close_position_db)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
        )

        assert response.status_code == 400
        assert "idempotency" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_close_position_updates_position_status(
        self, close_position_client, close_position_db
    ):
        """Should update position status to CLOSING."""
        position_id = await insert_open_position(close_position_db)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 201

        # Verify position status was updated
        result = await close_position_db.execute(
            text("SELECT status, active_close_request_id FROM positions WHERE id = :id"),
            {"id": position_id},
        )
        row = result.fetchone()
        assert row[0] == "closing"
        assert row[1] is not None  # Should have active_close_request_id set

    @pytest.mark.asyncio
    async def test_close_position_returns_poll_url(self, close_position_client, close_position_db):
        """Should return poll_url for status checking."""
        position_id = await insert_open_position(close_position_db)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["poll_url"] is not None
        assert data["close_request_id"] in data["poll_url"]

    @pytest.mark.asyncio
    async def test_close_position_short_position_uses_buy_side(
        self, close_position_client, close_position_db
    ):
        """Should use 'buy' side for short (negative quantity) positions."""
        position_id = await insert_open_position(close_position_db, quantity=-5)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["target_qty"] == 5  # Absolute value

        # Verify close_request has 'buy' side by checking the database
        # Note: The HTTP request creates its own session, so we need to refresh ours
        await close_position_db.rollback()
        result = await close_position_db.execute(text("SELECT side FROM close_requests"))
        rows = result.fetchall()
        # Should have at least one close request with 'buy' side
        assert len(rows) > 0
        assert rows[-1][0] == "buy"

    @pytest.mark.asyncio
    async def test_close_position_long_position_uses_sell_side(
        self, close_position_client, close_position_db
    ):
        """Should use 'sell' side for long (positive quantity) positions."""
        position_id = await insert_open_position(close_position_db, quantity=10)

        response = await close_position_client.post(
            f"/api/options/{position_id}/close",
            json={},
            headers={"Idempotency-Key": str(uuid4())},
        )

        assert response.status_code == 201
        data = response.json()

        # Verify close_request has 'sell' side by checking the database
        # Note: The HTTP request creates its own session, so we need to refresh ours
        await close_position_db.rollback()
        result = await close_position_db.execute(text("SELECT side FROM close_requests"))
        rows = result.fetchall()
        # Should have at least one close request with 'sell' side
        assert len(rows) > 0
        assert rows[-1][0] == "sell"
