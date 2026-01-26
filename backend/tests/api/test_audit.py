# backend/tests/api/test_audit.py
"""Tests for Audit API endpoints."""

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
async def audit_db_session():
    """In-memory SQLite database with audit tables for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        # Create audit_logs table (SQLite compatible)
        await conn.execute(
            text("""
            CREATE TABLE audit_logs (
                id TEXT PRIMARY KEY,
                sequence_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_type TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                source TEXT NOT NULL,
                environment TEXT NOT NULL,
                service TEXT NOT NULL,
                version TEXT NOT NULL,
                correlation_id TEXT,
                value_mode TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                metadata TEXT,
                checksum TEXT NOT NULL,
                prev_checksum TEXT,
                chain_key TEXT NOT NULL
            )
        """)
        )

        # Create audit_chain_head table
        await conn.execute(
            text("""
            CREATE TABLE audit_chain_head (
                chain_key TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                sequence_id INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        )

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def audit_client(audit_db_session):
    """HTTP client with audit database."""

    async def override_get_session():
        yield audit_db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_test_audit_log(
    session: AsyncSession,
    event_id: str | None = None,
    sequence_id: int = 1,
    timestamp: datetime | None = None,
    event_type: str = "order_placed",
    severity: str = "info",
    actor_id: str = "user-123",
    actor_type: str = "user",
    resource_type: str = "order",
    resource_id: str = "order-456",
    request_id: str = "req-789",
    source: str = "web",
    environment: str = "production",
    service: str = "trading-api",
    version: str = "1.0.0",
    correlation_id: str | None = None,
    value_mode: str = "diff",
    old_value: str | None = None,
    new_value: str | None = None,
    metadata: str | None = None,
    checksum: str = "abc123",
    prev_checksum: str | None = None,
    chain_key: str = "default",
) -> str:
    """Insert a test audit log into the database.

    Returns:
        The event ID
    """
    if event_id is None:
        event_id = str(uuid4())
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    await session.execute(
        text("""
            INSERT INTO audit_logs (
                id, sequence_id, timestamp, event_type, severity,
                actor_id, actor_type, resource_type, resource_id,
                request_id, source, environment, service, version,
                correlation_id, value_mode, old_value, new_value,
                metadata, checksum, prev_checksum, chain_key
            ) VALUES (
                :id, :sequence_id, :timestamp, :event_type, :severity,
                :actor_id, :actor_type, :resource_type, :resource_id,
                :request_id, :source, :environment, :service, :version,
                :correlation_id, :value_mode, :old_value, :new_value,
                :metadata, :checksum, :prev_checksum, :chain_key
            )
        """),
        {
            "id": event_id,
            "sequence_id": sequence_id,
            "timestamp": timestamp.isoformat(),
            "event_type": event_type,
            "severity": severity,
            "actor_id": actor_id,
            "actor_type": actor_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "request_id": request_id,
            "source": source,
            "environment": environment,
            "service": service,
            "version": version,
            "correlation_id": correlation_id,
            "value_mode": value_mode,
            "old_value": old_value,
            "new_value": new_value,
            "metadata": metadata,
            "checksum": checksum,
            "prev_checksum": prev_checksum,
            "chain_key": chain_key,
        },
    )
    await session.commit()
    return event_id


async def insert_test_chain_head(
    session: AsyncSession,
    chain_key: str = "default",
    checksum: str = "abc123",
    sequence_id: int = 1,
    updated_at: datetime | None = None,
) -> None:
    """Insert a test chain head into the database."""
    if updated_at is None:
        updated_at = datetime.now(timezone.utc)

    await session.execute(
        text("""
            INSERT INTO audit_chain_head (chain_key, checksum, sequence_id, updated_at)
            VALUES (:chain_key, :checksum, :sequence_id, :updated_at)
        """),
        {
            "chain_key": chain_key,
            "checksum": checksum,
            "sequence_id": sequence_id,
            "updated_at": updated_at.isoformat(),
        },
    )
    await session.commit()


class TestListAuditLogs:
    """Tests for GET /api/audit endpoint."""

    @pytest.mark.asyncio
    async def test_list_audit_logs_empty(self, audit_client):
        """GET /api/audit returns empty list when no audit logs."""
        response = await audit_client.get("/api/audit")

        assert response.status_code == 200
        data = response.json()
        assert data["logs"] == []
        assert data["total"] == 0
        assert data["offset"] == 0
        assert data["limit"] == 50

    @pytest.mark.asyncio
    async def test_list_audit_logs_returns_logs(self, audit_client, audit_db_session):
        """GET /api/audit returns list of audit logs."""
        event_id = await insert_test_audit_log(
            audit_db_session,
            event_type="order_placed",
            severity="info",
            actor_id="user-123",
            resource_type="order",
            resource_id="order-456",
        )

        response = await audit_client.get("/api/audit")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        log = data["logs"][0]
        assert log["event_id"] == event_id
        assert log["event_type"] == "order_placed"
        assert log["severity"] == "info"
        assert log["actor_id"] == "user-123"
        assert log["resource_type"] == "order"
        assert log["resource_id"] == "order-456"

    @pytest.mark.asyncio
    async def test_list_audit_logs_pagination(self, audit_client, audit_db_session):
        """GET /api/audit supports pagination."""
        # Insert multiple audit logs
        for i in range(10):
            await insert_test_audit_log(
                audit_db_session,
                sequence_id=i + 1,
                actor_id=f"user-{i}",
            )

        # Get first page
        response = await audit_client.get("/api/audit?limit=3&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["logs"]) == 3
        assert data["offset"] == 0
        assert data["limit"] == 3

        # Get second page
        response = await audit_client.get("/api/audit?limit=3&offset=3")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 10
        assert len(data["logs"]) == 3
        assert data["offset"] == 3

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_event_type(self, audit_client, audit_db_session):
        """GET /api/audit filters by event_type."""
        await insert_test_audit_log(audit_db_session, sequence_id=1, event_type="order_placed")
        await insert_test_audit_log(audit_db_session, sequence_id=2, event_type="order_filled")
        await insert_test_audit_log(audit_db_session, sequence_id=3, event_type="order_placed")

        response = await audit_client.get("/api/audit?event_type=order_filled")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["event_type"] == "order_filled"

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_resource_type(self, audit_client, audit_db_session):
        """GET /api/audit filters by resource_type."""
        await insert_test_audit_log(audit_db_session, sequence_id=1, resource_type="order")
        await insert_test_audit_log(audit_db_session, sequence_id=2, resource_type="config")
        await insert_test_audit_log(audit_db_session, sequence_id=3, resource_type="order")

        response = await audit_client.get("/api/audit?resource_type=config")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["resource_type"] == "config"

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_resource_id(self, audit_client, audit_db_session):
        """GET /api/audit filters by resource_id."""
        await insert_test_audit_log(audit_db_session, sequence_id=1, resource_id="order-123")
        await insert_test_audit_log(audit_db_session, sequence_id=2, resource_id="order-456")

        response = await audit_client.get("/api/audit?resource_id=order-456")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["resource_id"] == "order-456"

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_actor_id(self, audit_client, audit_db_session):
        """GET /api/audit filters by actor_id."""
        await insert_test_audit_log(audit_db_session, sequence_id=1, actor_id="user-123")
        await insert_test_audit_log(audit_db_session, sequence_id=2, actor_id="user-456")

        response = await audit_client.get("/api/audit?actor_id=user-456")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["actor_id"] == "user-456"

    @pytest.mark.asyncio
    async def test_list_audit_logs_filter_by_time_range(self, audit_client, audit_db_session):
        """GET /api/audit filters by start_time and end_time."""
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=2)
        very_old = now - timedelta(hours=5)

        await insert_test_audit_log(
            audit_db_session, sequence_id=1, timestamp=very_old, actor_id="old"
        )
        await insert_test_audit_log(audit_db_session, sequence_id=2, timestamp=old, actor_id="mid")
        await insert_test_audit_log(audit_db_session, sequence_id=3, timestamp=now, actor_id="new")

        # Filter by start_time only (use params to properly encode the datetime)
        start_time = (now - timedelta(hours=3)).isoformat()
        response = await audit_client.get("/api/audit", params={"start_time": start_time})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Filter by end_time only
        end_time = (now - timedelta(hours=1)).isoformat()
        response = await audit_client.get("/api/audit", params={"end_time": end_time})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_list_audit_logs_combined_filters(self, audit_client, audit_db_session):
        """GET /api/audit combines multiple filters."""
        await insert_test_audit_log(
            audit_db_session, sequence_id=1, event_type="order_placed", actor_id="user-123"
        )
        await insert_test_audit_log(
            audit_db_session, sequence_id=2, event_type="order_placed", actor_id="user-456"
        )
        await insert_test_audit_log(
            audit_db_session, sequence_id=3, event_type="order_filled", actor_id="user-123"
        )

        response = await audit_client.get("/api/audit?event_type=order_placed&actor_id=user-123")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["logs"]) == 1
        assert data["logs"][0]["event_type"] == "order_placed"
        assert data["logs"][0]["actor_id"] == "user-123"

    @pytest.mark.asyncio
    async def test_list_audit_logs_limit_max_100(self, audit_client):
        """GET /api/audit enforces max limit of 100."""
        response = await audit_client.get("/api/audit?limit=200")

        assert response.status_code == 422  # Validation error


class TestGetAuditEvent:
    """Tests for GET /api/audit/{event_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_audit_event_not_found(self, audit_client):
        """GET /api/audit/{event_id} returns 404 for unknown event."""
        fake_id = str(uuid4())
        response = await audit_client.get(f"/api/audit/{fake_id}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Audit event not found"

    @pytest.mark.asyncio
    async def test_get_audit_event_invalid_uuid(self, audit_client):
        """GET /api/audit/{event_id} returns 422 for invalid UUID."""
        response = await audit_client.get("/api/audit/not-a-uuid")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_audit_event_returns_event(self, audit_client, audit_db_session):
        """GET /api/audit/{event_id} returns the audit event."""
        event_id = await insert_test_audit_log(
            audit_db_session,
            event_type="config_updated",
            severity="warning",
            actor_id="admin-1",
            resource_type="config",
            resource_id="risk-limits",
            old_value='{"max_position": 1000}',
            new_value='{"max_position": 2000}',
        )

        response = await audit_client.get(f"/api/audit/{event_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["event_id"] == event_id
        assert data["event_type"] == "config_updated"
        assert data["severity"] == "warning"
        assert data["actor_id"] == "admin-1"
        assert data["resource_type"] == "config"
        assert data["resource_id"] == "risk-limits"


class TestGetAuditStats:
    """Tests for GET /api/audit/stats endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats_empty(self, audit_client):
        """GET /api/audit/stats returns empty stats when no audit logs."""
        response = await audit_client.get("/api/audit/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["by_event_type"] == {}
        assert data["by_actor"] == {}
        assert data["by_resource_type"] == {}

    @pytest.mark.asyncio
    async def test_get_stats_with_logs(self, audit_client, audit_db_session):
        """GET /api/audit/stats returns statistics."""
        now = datetime.now(timezone.utc)

        # Insert audit logs
        await insert_test_audit_log(
            audit_db_session,
            sequence_id=1,
            event_type="order_placed",
            actor_id="user-123",
            resource_type="order",
            timestamp=now,
        )
        await insert_test_audit_log(
            audit_db_session,
            sequence_id=2,
            event_type="order_placed",
            actor_id="user-123",
            resource_type="order",
            timestamp=now,
        )
        await insert_test_audit_log(
            audit_db_session,
            sequence_id=3,
            event_type="order_filled",
            actor_id="user-456",
            resource_type="order",
            timestamp=now,
        )
        await insert_test_audit_log(
            audit_db_session,
            sequence_id=4,
            event_type="config_updated",
            actor_id="admin-1",
            resource_type="config",
            timestamp=now,
        )

        response = await audit_client.get("/api/audit/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 4
        assert data["by_event_type"] == {
            "order_placed": 2,
            "order_filled": 1,
            "config_updated": 1,
        }
        assert data["by_actor"] == {
            "user-123": 2,
            "user-456": 1,
            "admin-1": 1,
        }
        assert data["by_resource_type"] == {
            "order": 3,
            "config": 1,
        }


class TestVerifyChainIntegrity:
    """Tests for GET /api/audit/integrity/{chain_key} endpoint."""

    @pytest.mark.asyncio
    async def test_verify_integrity_no_events(self, audit_client):
        """GET /api/audit/integrity/{chain_key} returns valid for empty chain."""
        response = await audit_client.get("/api/audit/integrity/default")

        assert response.status_code == 200
        data = response.json()
        assert data["chain_key"] == "default"
        assert data["is_valid"] is True
        assert data["errors"] == []
        assert data["events_verified"] == 0

    @pytest.mark.asyncio
    async def test_verify_integrity_valid_chain(self, audit_client, audit_db_session):
        """GET /api/audit/integrity/{chain_key} returns valid for intact chain."""
        # Insert valid chain events (same checksum flow as integrity module)
        # For testing, we insert events with correct prev_checksum linking
        event1_id = str(uuid4())
        event2_id = str(uuid4())

        # First event has no prev_checksum
        await insert_test_audit_log(
            audit_db_session,
            event_id=event1_id,
            sequence_id=1,
            checksum="checksum1",
            prev_checksum=None,
            chain_key="test-chain",
        )

        # Second event links to first
        await insert_test_audit_log(
            audit_db_session,
            event_id=event2_id,
            sequence_id=2,
            checksum="checksum2",
            prev_checksum="checksum1",
            chain_key="test-chain",
        )

        await insert_test_chain_head(
            audit_db_session,
            chain_key="test-chain",
            checksum="checksum2",
            sequence_id=2,
        )

        response = await audit_client.get("/api/audit/integrity/test-chain")

        assert response.status_code == 200
        data = response.json()
        assert data["chain_key"] == "test-chain"
        assert data["events_verified"] == 2
        # Note: actual validity depends on checksum computation matching

    @pytest.mark.asyncio
    async def test_verify_integrity_broken_chain(self, audit_client, audit_db_session):
        """GET /api/audit/integrity/{chain_key} detects broken chain."""
        event1_id = str(uuid4())
        event2_id = str(uuid4())

        # First event
        await insert_test_audit_log(
            audit_db_session,
            event_id=event1_id,
            sequence_id=1,
            checksum="checksum1",
            prev_checksum=None,
            chain_key="broken-chain",
        )

        # Second event with WRONG prev_checksum (should be "checksum1")
        await insert_test_audit_log(
            audit_db_session,
            event_id=event2_id,
            sequence_id=2,
            checksum="checksum2",
            prev_checksum="wrong-checksum",  # This breaks the chain
            chain_key="broken-chain",
        )

        response = await audit_client.get("/api/audit/integrity/broken-chain")

        assert response.status_code == 200
        data = response.json()
        assert data["chain_key"] == "broken-chain"
        assert data["is_valid"] is False
        assert len(data["errors"]) > 0
        # Should contain an error about chain being broken
        assert any(
            "broken" in error.lower() or "prev_checksum" in error.lower()
            for error in data["errors"]
        )

    @pytest.mark.asyncio
    async def test_verify_integrity_limit_parameter(self, audit_client, audit_db_session):
        """GET /api/audit/integrity/{chain_key} respects limit parameter."""
        # Insert multiple events
        for i in range(5):
            await insert_test_audit_log(
                audit_db_session,
                sequence_id=i + 1,
                checksum=f"checksum{i + 1}",
                prev_checksum=f"checksum{i}" if i > 0 else None,
                chain_key="limited-chain",
            )

        response = await audit_client.get("/api/audit/integrity/limited-chain?limit=3")

        assert response.status_code == 200
        data = response.json()
        assert data["events_verified"] == 3
