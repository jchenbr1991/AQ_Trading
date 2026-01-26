"""Tests for alert repository module.

Following TDD: tests written FIRST, before implementation.
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity
from src.alerts.repository import AlertRepository


@pytest_asyncio.fixture
async def alert_db_session():
    """In-memory SQLite database with alerts tables for testing.

    Creates the alerts and alert_deliveries tables matching the migration schema.
    """
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


class TestAlertRepositoryInit:
    """Tests for AlertRepository initialization."""

    @pytest.mark.asyncio
    async def test_init_with_session(self, alert_db_session):
        """Repository should accept AsyncSession in constructor."""
        repo = AlertRepository(alert_db_session)
        assert repo.session is alert_db_session


class TestPersistAlert:
    """Tests for persist_alert method."""

    @pytest.mark.asyncio
    async def test_persist_alert_new_alert_returns_true_and_id(self, alert_db_session):
        """persist_alert should return (True, alert_id) for new alert."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected: insufficient funds",
            account_id="acc123",
            symbol="AAPL",
        )

        is_new, alert_id = await repo.persist_alert(alert)

        assert is_new is True
        assert alert_id == alert.alert_id

    @pytest.mark.asyncio
    async def test_persist_alert_duplicate_returns_false(self, alert_db_session):
        """persist_alert should return (False, alert_id) for duplicate dedupe_key."""
        repo = AlertRepository(alert_db_session)

        # Create two alerts with same fingerprint in same time bucket
        ts = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)

        alert1 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="First rejection",
            timestamp=ts,
            account_id="acc123",
            symbol="AAPL",
        )

        alert2 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Second rejection",
            timestamp=ts,
            account_id="acc123",
            symbol="AAPL",
        )

        # First persist should be new
        is_new1, id1 = await repo.persist_alert(alert1)
        assert is_new1 is True

        # Second persist with same dedupe_key should not be new
        is_new2, id2 = await repo.persist_alert(alert2)
        assert is_new2 is False
        # Should return the original alert's ID
        assert id2 == alert1.alert_id

    @pytest.mark.asyncio
    async def test_persist_alert_increments_suppressed_count(self, alert_db_session):
        """Duplicate alerts should increment suppressed_count."""
        repo = AlertRepository(alert_db_session)

        ts = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)

        # Persist same logical alert 3 times
        for i in range(3):
            alert = create_alert(
                type=AlertType.ORDER_REJECTED,
                severity=Severity.SEV2,
                summary=f"Rejection #{i+1}",
                timestamp=ts,
                account_id="acc123",
                symbol="AAPL",
            )
            await repo.persist_alert(alert)

        # Check suppressed_count in database
        result = await alert_db_session.execute(
            text("SELECT suppressed_count FROM alerts WHERE entity_symbol = 'AAPL'")
        )
        row = result.fetchone()
        # First insert = 0, then 2 more increments = 2
        assert row[0] == 2

    @pytest.mark.asyncio
    async def test_persist_alert_stores_all_fields(self, alert_db_session):
        """persist_alert should store all alert fields in database."""
        repo = AlertRepository(alert_db_session)

        ts = datetime(2026, 1, 25, 12, 30, 45, tzinfo=timezone.utc)
        alert_id = uuid4()

        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Emergency halt triggered",
            alert_id=alert_id,
            timestamp=ts,
            account_id="acc456",
            symbol="TSLA",
            strategy_id="strat789",
            details={"reason": "daily loss limit"},
        )

        await repo.persist_alert(alert)

        # Verify stored data
        result = await alert_db_session.execute(
            text("SELECT * FROM alerts WHERE id = :id"),
            {"id": str(alert_id)},
        )
        row = result.fetchone()

        assert row is not None
        assert row[1] == "kill_switch_activated"  # type
        assert row[2] == 1  # severity
        assert row[3] == alert.fingerprint  # fingerprint
        assert row[5] == "Emergency halt triggered"  # summary
        assert json.loads(row[6]) == {"reason": "daily loss limit"}  # details
        assert row[7] == "acc456"  # entity_account_id
        assert row[8] == "TSLA"  # entity_symbol
        assert row[9] == "strat789"  # entity_strategy_id

    @pytest.mark.asyncio
    async def test_persist_alert_different_buckets_both_new(self, alert_db_session):
        """Alerts in different time buckets should both be new."""
        repo = AlertRepository(alert_db_session)

        # 15 minutes apart = different buckets (10 min windows)
        ts1 = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 25, 12, 15, 0, tzinfo=timezone.utc)

        alert1 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="First rejection",
            timestamp=ts1,
            account_id="acc123",
        )

        alert2 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Later rejection",
            timestamp=ts2,
            account_id="acc123",
        )

        is_new1, _ = await repo.persist_alert(alert1)
        is_new2, _ = await repo.persist_alert(alert2)

        assert is_new1 is True
        assert is_new2 is True


class TestGetAlert:
    """Tests for get_alert method."""

    @pytest.mark.asyncio
    async def test_get_alert_returns_dict(self, alert_db_session):
        """get_alert should return a dict of the alert row."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
            account_id="acc123",
            symbol="AAPL",
        )

        await repo.persist_alert(alert)

        result = await repo.get_alert(alert.alert_id)

        assert result is not None
        assert isinstance(result, dict)
        assert result["id"] == str(alert.alert_id)
        assert result["type"] == "order_rejected"
        assert result["severity"] == 2
        assert result["summary"] == "Order rejected"
        assert result["entity_symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_get_alert_returns_none_for_missing(self, alert_db_session):
        """get_alert should return None if alert not found."""
        repo = AlertRepository(alert_db_session)

        result = await repo.get_alert(uuid4())

        assert result is None


class TestRecordDeliveryAttempt:
    """Tests for record_delivery_attempt method."""

    @pytest.mark.asyncio
    async def test_record_delivery_attempt_returns_uuid(self, alert_db_session):
        """record_delivery_attempt should return a delivery UUID."""
        repo = AlertRepository(alert_db_session)

        # First create an alert
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )
        await repo.persist_alert(alert)

        # Record delivery attempt
        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="email",
            destination_key="admin@example.com",
            attempt_number=1,
            status="pending",
        )

        assert isinstance(delivery_id, UUID)

    @pytest.mark.asyncio
    async def test_record_delivery_attempt_stores_fields(self, alert_db_session):
        """record_delivery_attempt should store all fields correctly."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Kill switch",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="webhook",
            destination_key="https://hooks.example.com/alert",
            attempt_number=2,
            status="pending",
        )

        # Verify in database
        result = await alert_db_session.execute(
            text("SELECT * FROM alert_deliveries WHERE id = :id"),
            {"id": str(delivery_id)},
        )
        row = result.fetchone()

        assert row is not None
        assert row[1] == str(alert.alert_id)  # alert_id
        assert row[2] == "webhook"  # channel
        assert row[3] == "https://hooks.example.com/alert"  # destination_key
        assert row[4] == 2  # attempt_number
        assert row[5] == "pending"  # status


class TestUpdateDeliveryStatus:
    """Tests for update_delivery_status method."""

    @pytest.mark.asyncio
    async def test_update_delivery_status_to_sent(self, alert_db_session):
        """update_delivery_status should update status and set sent_at for 'sent'."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="email",
            destination_key="admin@example.com",
            attempt_number=1,
            status="pending",
        )

        await repo.update_delivery_status(
            delivery_id=delivery_id,
            status="sent",
            response_code=200,
        )

        # Verify update
        result = await alert_db_session.execute(
            text("SELECT status, response_code, sent_at FROM alert_deliveries WHERE id = :id"),
            {"id": str(delivery_id)},
        )
        row = result.fetchone()

        assert row[0] == "sent"
        assert row[1] == 200
        assert row[2] is not None  # sent_at should be set

    @pytest.mark.asyncio
    async def test_update_delivery_status_to_failed(self, alert_db_session):
        """update_delivery_status should store error_message for failures."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="webhook",
            destination_key="https://hooks.example.com/alert",
            attempt_number=1,
            status="pending",
        )

        await repo.update_delivery_status(
            delivery_id=delivery_id,
            status="failed",
            response_code=500,
            error_message="Server error",
        )

        # Verify update
        result = await alert_db_session.execute(
            text(
                "SELECT status, response_code, error_message, sent_at FROM alert_deliveries WHERE id = :id"
            ),
            {"id": str(delivery_id)},
        )
        row = result.fetchone()

        assert row[0] == "failed"
        assert row[1] == 500
        assert row[2] == "Server error"
        assert row[3] is None  # sent_at not set for failed

    @pytest.mark.asyncio
    async def test_update_delivery_status_without_response_code(self, alert_db_session):
        """update_delivery_status should work without response_code."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="email",
            destination_key="admin@example.com",
            attempt_number=1,
            status="pending",
        )

        await repo.update_delivery_status(
            delivery_id=delivery_id,
            status="sent",
        )

        # Verify update
        result = await alert_db_session.execute(
            text("SELECT status, response_code FROM alert_deliveries WHERE id = :id"),
            {"id": str(delivery_id)},
        )
        row = result.fetchone()

        assert row[0] == "sent"
        assert row[1] is None


class TestGetDelivery:
    """Tests for get_delivery method."""

    @pytest.mark.asyncio
    async def test_get_delivery_returns_dict(self, alert_db_session):
        """get_delivery should return a dict of the delivery row."""
        repo = AlertRepository(alert_db_session)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="email",
            destination_key="admin@example.com",
            attempt_number=1,
            status="pending",
        )

        result = await repo.get_delivery(delivery_id)

        assert result is not None
        assert isinstance(result, dict)
        assert result["id"] == str(delivery_id)
        assert result["alert_id"] == str(alert.alert_id)
        assert result["channel"] == "email"
        assert result["destination_key"] == "admin@example.com"
        assert result["attempt_number"] == 1
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_delivery_returns_none_for_missing(self, alert_db_session):
        """get_delivery should return None if delivery not found."""
        repo = AlertRepository(alert_db_session)

        result = await repo.get_delivery(uuid4())

        assert result is None
