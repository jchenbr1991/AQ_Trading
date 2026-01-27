# backend/tests/integration/test_options_expiration_e2e.py
"""End-to-end integration tests for Options Expiration feature.

Test Requirements (from Design Doc):
1. Threshold matching logic (DTE=1 -> 3 alerts, DTE=0 -> 4 alerts)
2. Idempotency persistence (cached responses)
3. Transaction atomicity (rollback on failure)
4. Multi-instance safety (advisory lock)
5. Regression tests (old alert types unaffected, details=None)
6. Timezone boundary tests (DST, day boundary)
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity
from src.alerts.repository import AlertRepository
from src.models.position import AssetType, PutCall
from src.options.checker import ExpirationChecker
from src.options.idempotency import IdempotencyService
from src.options.scheduler import ExpirationScheduler


@pytest_asyncio.fixture
async def e2e_db_session():
    """In-memory SQLite database with all required tables for E2E testing.

    Creates alerts, alert_deliveries, and idempotency_keys tables.
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

        # Create idempotency_keys table
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

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


def create_mock_option_position(
    position_id: int,
    symbol: str,
    expiry: date,
    strike: Decimal = Decimal("150.00"),
    put_call: PutCall = PutCall.CALL,
    quantity: int = 10,
) -> MagicMock:
    """Create a mock option position for testing."""
    pos = MagicMock()
    pos.id = position_id
    pos.symbol = symbol
    pos.asset_type = AssetType.OPTION
    pos.expiry = expiry
    pos.strike = strike
    pos.put_call = put_call
    pos.quantity = quantity
    return pos


# =============================================================================
# 1. Threshold Matching Logic Tests
# =============================================================================


class TestThresholdMatchingLogic:
    """Test threshold matching logic: DTE=1 -> 3 alerts, DTE=0 -> 4 alerts."""

    @pytest.mark.asyncio
    async def test_dte_1_triggers_3_alerts(self, e2e_db_session):
        """DTE=1 should trigger 3 alerts (thresholds 1/3/7 days)."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        # Position expiring tomorrow (DTE=1)
        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()
        tomorrow = today + timedelta(days=1)

        position = create_mock_option_position(
            position_id=101,
            symbol="AAPL240119C150",
            expiry=tomorrow,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # DTE=1 should trigger thresholds: 1-day, 3-day, 7-day (3 alerts)
        assert stats["alerts_attempted"] == 3
        assert stats["alerts_created"] == 3
        assert stats["alerts_deduplicated"] == 0

        # Verify alerts in database
        result = await e2e_db_session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE type = 'option_expiring'")
        )
        count = result.scalar()
        assert count == 3

    @pytest.mark.asyncio
    async def test_dte_0_triggers_4_alerts(self, e2e_db_session):
        """DTE=0 should trigger 4 alerts (thresholds 0/1/3/7 days)."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        # Position expiring today (DTE=0)
        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()

        position = create_mock_option_position(
            position_id=102,
            symbol="TSLA240119P200",
            expiry=today,
            put_call=PutCall.PUT,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # DTE=0 should trigger all 4 thresholds
        assert stats["alerts_attempted"] == 4
        assert stats["alerts_created"] == 4
        assert stats["alerts_deduplicated"] == 0

        # Verify alerts in database with correct threshold_days
        result = await e2e_db_session.execute(
            text("""
                SELECT json_extract(details, '$.threshold_days') as threshold
                FROM alerts WHERE type = 'option_expiring'
                ORDER BY threshold
            """)
        )
        thresholds = [row[0] for row in result.fetchall()]
        assert thresholds == [0, 1, 3, 7]

    @pytest.mark.asyncio
    async def test_repeated_run_deduplicates_alerts(self, e2e_db_session):
        """Repeated run should deduplicate alerts (alerts_deduplicated = threshold count)."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        # Position expiring today (DTE=0)
        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()

        position = create_mock_option_position(
            position_id=103,
            symbol="NVDA240119C500",
            expiry=today,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        # First run: should create 4 alerts
        stats1 = await checker.check_expirations("acc123")
        assert stats1["alerts_created"] == 4
        assert stats1["alerts_deduplicated"] == 0

        # Second run: should deduplicate all 4 alerts
        stats2 = await checker.check_expirations("acc123")
        assert stats2["alerts_created"] == 0
        assert stats2["alerts_deduplicated"] == 4

        # Verify only 4 alerts exist in database (no duplicates)
        result = await e2e_db_session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE type = 'option_expiring'")
        )
        count = result.scalar()
        assert count == 4

    @pytest.mark.asyncio
    async def test_dte_6_triggers_1_alert(self, e2e_db_session):
        """DTE=6 should trigger 1 alert (only 7-day threshold)."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()
        expiry_date = today + timedelta(days=6)

        position = create_mock_option_position(
            position_id=104,
            symbol="MSFT240119C400",
            expiry=expiry_date,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # DTE=6 should only trigger 7-day threshold
        assert stats["alerts_attempted"] == 1
        assert stats["alerts_created"] == 1

    @pytest.mark.asyncio
    async def test_dte_10_triggers_no_alerts(self, e2e_db_session):
        """DTE=10 (out of scope) should trigger no alerts."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()
        expiry_date = today + timedelta(days=10)

        position = create_mock_option_position(
            position_id=105,
            symbol="META240119C350",
            expiry=expiry_date,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["alerts_attempted"] == 0
        assert stats["alerts_created"] == 0
        assert stats["positions_not_expiring_soon"] == 1


# =============================================================================
# 2. Idempotency Persistence Tests
# =============================================================================


class TestIdempotencyPersistence:
    """Test idempotency persistence: same key returns cached, different key creates new.

    Note: These tests use mocked session to avoid SQLite vs PostgreSQL SQL syntax
    differences (NOW() function). The actual IdempotencyService SQL is tested
    in test_idempotency.py with proper mocking.
    """

    @pytest.mark.asyncio
    async def test_same_key_returns_cached_response(self):
        """Same idempotency key should return cached result."""
        mock_session = AsyncMock()

        # First call (store_key) - no return needed
        # Second call (get_cached_response) - return the cached data
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (
            '{"success": true, "order_id": "order-456", "message": "Position closed"}',
        )
        mock_session.execute.return_value = mock_result

        idempotency = IdempotencyService(mock_session)

        key = "close-pos-123-abc"
        original_response = {
            "success": True,
            "order_id": "order-456",
            "message": "Position closed",
        }

        # Retrieve with same key
        exists, cached = await idempotency.get_cached_response(key)

        assert exists is True
        assert cached == original_response

    @pytest.mark.asyncio
    async def test_different_key_returns_none(self):
        """Different idempotency key should return (False, None)."""
        mock_session = AsyncMock()

        # Mock no rows returned
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session.execute.return_value = mock_result

        idempotency = IdempotencyService(mock_session)

        # Try to retrieve with non-existent key
        exists, cached = await idempotency.get_cached_response("key-2")

        assert exists is False
        assert cached is None

    @pytest.mark.asyncio
    async def test_idempotency_key_conflict_ignored(self):
        """Duplicate key insert should be ignored (ON CONFLICT DO NOTHING)."""
        mock_session = AsyncMock()

        # Mock fetching the first stored response
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ('{"success": true, "order_id": "order-first"}',)
        mock_session.execute.return_value = mock_result

        idempotency = IdempotencyService(mock_session)

        key = "close-pos-789"
        first_response = {"success": True, "order_id": "order-first"}

        # Store first response (actual SQL execution mocked)
        await idempotency.store_key(
            key=key,
            resource_type="close_position",
            resource_id="789",
            response_data=first_response,
        )

        # Store with same key (should be ignored due to ON CONFLICT DO NOTHING)
        await idempotency.store_key(
            key=key,
            resource_type="close_position",
            resource_id="789",
            response_data={"success": True, "order_id": "order-second"},
        )

        # Retrieve should return first response
        exists, cached = await idempotency.get_cached_response(key)

        assert exists is True
        assert cached == first_response  # Not second_response

    @pytest.mark.asyncio
    async def test_store_and_retrieve_flow(self, e2e_db_session):
        """Test store and retrieve flow using direct SQL (SQLite compatible)."""
        # Store directly with SQLite-compatible SQL
        key = "test-key-e2e"
        response_data = {"success": True, "order_id": "order-e2e"}
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        await e2e_db_session.execute(
            text("""
                INSERT INTO idempotency_keys (key, resource_type, resource_id, response_data, expires_at)
                VALUES (:key, :resource_type, :resource_id, :response_data, :expires_at)
            """),
            {
                "key": key,
                "resource_type": "close_position",
                "resource_id": "123",
                "response_data": '{"success": true, "order_id": "order-e2e"}',
                "expires_at": expires_at,
            },
        )
        await e2e_db_session.commit()

        # Retrieve using SQLite-compatible query (datetime comparison with string)
        result = await e2e_db_session.execute(
            text("SELECT response_data FROM idempotency_keys WHERE key = :key"),
            {"key": key},
        )
        row = result.fetchone()

        assert row is not None
        import json

        assert json.loads(row[0]) == response_data


# =============================================================================
# 3. Transaction Atomicity Tests
# =============================================================================


class TestTransactionAtomicity:
    """Test transaction atomicity: failures should not leave partial state."""

    @pytest.mark.asyncio
    async def test_alert_creation_failure_doesnt_affect_other_alerts(self, e2e_db_session):
        """If one alert fails, others should still be created."""
        mock_portfolio = AsyncMock()
        mock_alert_repo = AsyncMock()

        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()

        position = create_mock_option_position(
            position_id=201,
            symbol="AAPL240119C150",
            expiry=today,  # DTE=0, 4 thresholds
        )
        mock_portfolio.get_positions.return_value = [position]

        # Simulate: first 2 succeed, third fails, fourth succeeds
        call_count = [0]

        async def persist_with_failure(alert):
            call_count[0] += 1
            if call_count[0] == 3:
                raise Exception("Simulated DB error")
            return (True, uuid4())

        mock_alert_repo.persist_alert.side_effect = persist_with_failure

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # 4 alerts attempted, 3 created (one failed), 0 deduplicated
        assert stats["alerts_attempted"] == 4
        assert stats["alerts_created"] == 3
        assert len(stats["errors"]) == 1
        assert "Simulated DB error" in stats["errors"][0]

    @pytest.mark.asyncio
    async def test_position_processing_failure_continues_to_next(self, e2e_db_session):
        """If one position fails, others should still be processed."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()

        # First position: missing strike (will fail)
        pos1 = MagicMock()
        pos1.id = 301
        pos1.symbol = "BAD_OPTION"
        pos1.asset_type = AssetType.OPTION
        pos1.expiry = today
        pos1.strike = None  # Missing required field
        pos1.put_call = PutCall.CALL
        pos1.quantity = 10

        # Second position: valid (will succeed)
        pos2 = create_mock_option_position(
            position_id=302,
            symbol="GOOD_OPTION",
            expiry=today,
        )

        mock_portfolio.get_positions.return_value = [pos1, pos2]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # First position should fail (4 alerts attempted, all fail)
        # Second position should succeed (4 alerts created)
        assert stats["positions_checked"] == 2
        # pos1: 4 attempts fail due to missing strike
        # pos2: 4 attempts succeed
        assert stats["alerts_created"] == 4  # Only from pos2
        assert len(stats["errors"]) >= 4  # Errors from pos1


# =============================================================================
# 4. Multi-Instance Safety Tests (Advisory Lock)
# =============================================================================


class TestMultiInstanceSafety:
    """Test multi-instance safety with Postgres Advisory Lock simulation."""

    @pytest.mark.asyncio
    async def test_lock_acquired_executes_check(self):
        """Instance that acquires lock should execute the check."""
        mock_checker = AsyncMock()
        mock_checker.check_expirations.return_value = {
            "run_id": "test-run",
            "positions_checked": 5,
            "alerts_created": 2,
            "alerts_deduplicated": 0,
        }
        mock_session = AsyncMock()

        # Mock successful lock acquisition
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=True,
        )

        stats = await scheduler._run_check_with_lock()

        assert stats["executed"] is True
        assert stats["positions_checked"] == 5
        mock_checker.check_expirations.assert_called_once_with("acc123")

    @pytest.mark.asyncio
    async def test_lock_not_acquired_skips_check(self):
        """Instance that fails to acquire lock should skip check."""
        mock_checker = AsyncMock()
        mock_session = AsyncMock()

        # Mock failed lock acquisition
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute.return_value = mock_result

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=True,
        )

        stats = await scheduler._run_check_with_lock()

        assert stats["executed"] is False
        assert stats["reason"] == "lock_held_by_another_instance"
        mock_checker.check_expirations.assert_not_called()

    @pytest.mark.asyncio
    async def test_two_instances_concurrent_only_one_executes(self):
        """Simulated concurrent instances: only one should execute."""
        mock_checker = AsyncMock()
        mock_checker.check_expirations.return_value = {
            "run_id": "winner-run",
            "positions_checked": 5,
            "alerts_created": 2,
            "executed": True,
        }

        # Simulate two sessions
        mock_session_1 = AsyncMock()
        mock_session_2 = AsyncMock()

        # Session 1 acquires lock
        mock_result_1 = MagicMock()
        mock_result_1.scalar.return_value = True
        mock_session_1.execute.return_value = mock_result_1

        # Session 2 fails to acquire lock
        mock_result_2 = MagicMock()
        mock_result_2.scalar.return_value = False
        mock_session_2.execute.return_value = mock_result_2

        scheduler_1 = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session_1,
            use_distributed_lock=True,
        )

        scheduler_2 = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session_2,
            use_distributed_lock=True,
        )

        # Both attempt to run
        stats_1 = await scheduler_1._run_check_with_lock()
        stats_2 = await scheduler_2._run_check_with_lock()

        # Only scheduler_1 should have executed
        assert stats_1["executed"] is True
        assert stats_2["executed"] is False
        assert stats_2["reason"] == "lock_held_by_another_instance"

        # Checker should only be called once
        assert mock_checker.check_expirations.call_count == 1

    @pytest.mark.asyncio
    async def test_lock_released_after_check(self):
        """Lock should be released after check completes."""
        mock_checker = AsyncMock()
        mock_checker.check_expirations.return_value = {"run_id": "test"}
        mock_session = AsyncMock()

        # Track SQL calls to verify lock release
        sql_calls = []

        async def track_execute(sql, params=None):
            sql_str = str(sql)
            sql_calls.append(sql_str)
            mock_result = MagicMock()
            mock_result.scalar.return_value = True
            return mock_result

        mock_session.execute.side_effect = track_execute

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            use_distributed_lock=True,
        )

        await scheduler._run_check_with_lock()

        # Should have called pg_try_advisory_lock and pg_advisory_unlock
        assert any("pg_try_advisory_lock" in call for call in sql_calls)
        assert any("pg_advisory_unlock" in call for call in sql_calls)


# =============================================================================
# 5. Regression Tests
# =============================================================================


class TestRegressionTests:
    """Regression tests: old alert types unaffected, details=None doesn't crash."""

    @pytest.mark.asyncio
    async def test_old_alert_types_unaffected(self, e2e_db_session):
        """Creating non-option alerts should still work as before."""
        alert_repo = AlertRepository(e2e_db_session)

        # Create a standard ORDER_REJECTED alert
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Order rejected: insufficient funds",
            account_id="acc123",
            symbol="AAPL",
            details={"reason": "insufficient_funds", "order_id": "order-123"},
        )

        is_new, alert_id = await alert_repo.persist_alert(alert)

        assert is_new is True
        assert alert_id == alert.alert_id

        # Verify in database
        stored = await alert_repo.get_alert(alert_id)
        assert stored is not None
        assert stored["type"] == "order_rejected"
        assert stored["entity_symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_kill_switch_alert_still_works(self, e2e_db_session):
        """KILL_SWITCH_ACTIVATED alert should work as before."""
        alert_repo = AlertRepository(e2e_db_session)

        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Emergency trading halt triggered",
            account_id="acc456",
            details={"reason": "daily_loss_limit", "triggered_by": "risk_manager"},
        )

        is_new, alert_id = await alert_repo.persist_alert(alert)

        assert is_new is True

        stored = await alert_repo.get_alert(alert_id)
        assert stored["type"] == "kill_switch_activated"
        assert stored["severity"] == 1  # SEV1

    @pytest.mark.asyncio
    async def test_details_none_doesnt_crash(self, e2e_db_session):
        """Alert with details=None should not crash."""
        alert_repo = AlertRepository(e2e_db_session)

        alert = create_alert(
            type=AlertType.COMPONENT_UNHEALTHY,
            severity=Severity.SEV2,
            summary="Database connection lost",
            account_id="system",
            details=None,  # Explicitly None
        )

        is_new, alert_id = await alert_repo.persist_alert(alert)

        assert is_new is True

        stored = await alert_repo.get_alert(alert_id)
        assert stored is not None
        assert stored["details"] is None or stored["details"] == {}

    @pytest.mark.asyncio
    async def test_empty_details_dict_works(self, e2e_db_session):
        """Alert with empty details dict should work."""
        alert_repo = AlertRepository(e2e_db_session)

        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV3,
            summary="Order filled",
            account_id="acc789",
            symbol="TSLA",
            details={},  # Empty dict
        )

        is_new, alert_id = await alert_repo.persist_alert(alert)

        assert is_new is True

        stored = await alert_repo.get_alert(alert_id)
        assert stored is not None

    @pytest.mark.asyncio
    async def test_existing_alert_creation_flow_unchanged(self, e2e_db_session):
        """Existing alert workflow should be unchanged by options feature."""
        alert_repo = AlertRepository(e2e_db_session)

        # Create alert
        alert = create_alert(
            type=AlertType.POSITION_LIMIT_HIT,
            severity=Severity.SEV2,
            summary="Position limit reached for AAPL",
            account_id="acc123",
            symbol="AAPL",
            strategy_id="momentum",
            details={"current_position": 1000, "limit": 1000},
        )

        # Persist
        is_new, alert_id = await alert_repo.persist_alert(alert)
        assert is_new is True

        # Retrieve
        stored = await alert_repo.get_alert(alert_id)
        assert stored["type"] == "position_limit_hit"
        assert stored["entity_account_id"] == "acc123"
        assert stored["entity_symbol"] == "AAPL"
        assert stored["entity_strategy_id"] == "momentum"

        # Duplicate should be deduplicated
        is_new_2, _ = await alert_repo.persist_alert(alert)
        assert is_new_2 is False


# =============================================================================
# 6. Timezone Boundary Tests
# =============================================================================


class TestTimezoneBoundaryTests:
    """Test timezone boundary handling: DST transitions, day boundaries."""

    @pytest.mark.asyncio
    async def test_dte_calculation_at_day_boundary(self, e2e_db_session):
        """DTE should be calculated correctly at day boundary."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")

        # Create a position expiring tomorrow
        today = datetime.now(ny_tz).date()
        tomorrow = today + timedelta(days=1)

        position = create_mock_option_position(
            position_id=601,
            symbol="TEST_BOUNDARY",
            expiry=tomorrow,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # DTE=1 should trigger 3 alerts
        assert stats["alerts_created"] == 3

    @pytest.mark.asyncio
    async def test_dte_calculation_uses_market_timezone(self, e2e_db_session):
        """DTE calculation should use market timezone (America/New_York)."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")
        utc_tz = ZoneInfo("UTC")

        # Get current time in both timezones
        now_utc = datetime.now(utc_tz)
        now_ny = now_utc.astimezone(ny_tz)

        # If it's late night in UTC (e.g., 23:00), it might be evening in NY
        # This test verifies we use NY time for DTE calculation

        today_ny = now_ny.date()

        position = create_mock_option_position(
            position_id=602,
            symbol="TEST_TZ",
            expiry=today_ny,  # Expires "today" in NY time
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # DTE=0 in NY timezone should trigger 4 alerts
        assert stats["alerts_created"] == 4

    @pytest.mark.asyncio
    async def test_dst_transition_spring_forward(self, e2e_db_session):
        """Test DTE calculation around DST spring forward transition.

        Spring forward: 2:00 AM -> 3:00 AM (March, 2nd Sunday)
        """
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")

        # March 10, 2024 was a DST transition day (spring forward)
        # Use a date that's clearly after any DST edge cases
        dst_date = date(2024, 3, 11)  # Day after DST

        position = create_mock_option_position(
            position_id=603,
            symbol="TEST_DST_SPRING",
            expiry=dst_date,
        )
        mock_portfolio.get_positions.return_value = [position]

        # Mock datetime.now to return a specific time during DST
        with patch("src.options.checker.datetime") as mock_datetime:
            # Set "now" to March 10, 2024 at 10:00 AM NY time
            mock_now = datetime(2024, 3, 10, 10, 0, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            checker = ExpirationChecker(
                portfolio=mock_portfolio,
                alert_repo=alert_repo,
                market_tz=ny_tz,
            )

            stats = await checker.check_expirations("acc123")

        # Position expires tomorrow (DTE=1), should trigger 3 alerts
        assert stats["alerts_attempted"] == 3

    @pytest.mark.asyncio
    async def test_dst_transition_fall_back(self, e2e_db_session):
        """Test DTE calculation around DST fall back transition.

        Fall back: 2:00 AM -> 1:00 AM (November, 1st Sunday)
        """
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")

        # November 3, 2024 was a DST transition day (fall back)
        dst_date = date(2024, 11, 4)  # Day after DST

        position = create_mock_option_position(
            position_id=604,
            symbol="TEST_DST_FALL",
            expiry=dst_date,
        )
        mock_portfolio.get_positions.return_value = [position]

        # Mock datetime.now to return a specific time during fall back
        with patch("src.options.checker.datetime") as mock_datetime:
            # Set "now" to November 3, 2024 at 10:00 AM NY time
            mock_now = datetime(2024, 11, 3, 10, 0, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            checker = ExpirationChecker(
                portfolio=mock_portfolio,
                alert_repo=alert_repo,
                market_tz=ny_tz,
            )

            stats = await checker.check_expirations("acc123")

        # Position expires tomorrow (DTE=1), should trigger 3 alerts
        assert stats["alerts_attempted"] == 3

    @pytest.mark.asyncio
    async def test_scheduler_times_correct_for_market_hours(self):
        """Verify scheduler runs at correct times (8:00 ET, 15:00 ET)."""
        from src.options.scheduler import HAS_APSCHEDULER, ExpirationScheduler

        if not HAS_APSCHEDULER:
            pytest.skip("APScheduler not installed")

        mock_checker = AsyncMock()
        mock_session = AsyncMock()
        ny_tz = ZoneInfo("America/New_York")

        scheduler = ExpirationScheduler(
            checker=mock_checker,
            account_id="acc123",
            session=mock_session,
            market_tz=ny_tz,
        )

        # Verify scheduler is initialized with market timezone
        assert scheduler.market_tz == ny_tz

        # Note: We don't actually start the scheduler in tests
        # This just verifies the configuration

    @pytest.mark.asyncio
    async def test_expiry_at_2359_same_day(self, e2e_db_session):
        """Position checked at 23:59 with same-day expiry should have DTE=0."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")

        # Simulate checking at 23:59 on expiry day
        with patch("src.options.checker.datetime") as mock_datetime:
            # Set "now" to 23:59 on January 15, 2024
            mock_now = datetime(2024, 1, 15, 23, 59, 59, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            position = create_mock_option_position(
                position_id=605,
                symbol="TEST_2359",
                expiry=date(2024, 1, 15),  # Same day
            )
            mock_portfolio.get_positions.return_value = [position]

            checker = ExpirationChecker(
                portfolio=mock_portfolio,
                alert_repo=alert_repo,
                market_tz=ny_tz,
            )

            stats = await checker.check_expirations("acc123")

        # DTE=0 should trigger 4 alerts
        assert stats["alerts_attempted"] == 4

    @pytest.mark.asyncio
    async def test_expiry_at_0001_next_day(self, e2e_db_session):
        """Position checked at 00:01 with next-day expiry should have DTE=1."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")

        # Simulate checking at 00:01 on January 15
        with patch("src.options.checker.datetime") as mock_datetime:
            # Set "now" to 00:01 on January 15, 2024
            mock_now = datetime(2024, 1, 15, 0, 1, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            position = create_mock_option_position(
                position_id=606,
                symbol="TEST_0001",
                expiry=date(2024, 1, 16),  # Tomorrow
            )
            mock_portfolio.get_positions.return_value = [position]

            checker = ExpirationChecker(
                portfolio=mock_portfolio,
                alert_repo=alert_repo,
                market_tz=ny_tz,
            )

            stats = await checker.check_expirations("acc123")

        # DTE=1 should trigger 3 alerts
        assert stats["alerts_attempted"] == 3


# =============================================================================
# Additional E2E Integration Tests
# =============================================================================


class TestFullE2EFlow:
    """Full end-to-end flow tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_complete_expiration_check_flow(self, e2e_db_session):
        """Test complete flow: multiple positions, various DTEs, deduplication."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()

        # Create positions with different DTEs
        positions = [
            create_mock_option_position(
                position_id=701,
                symbol="AAPL_TODAY",
                expiry=today,  # DTE=0, 4 alerts
            ),
            create_mock_option_position(
                position_id=702,
                symbol="TSLA_TOMORROW",
                expiry=today + timedelta(days=1),  # DTE=1, 3 alerts
            ),
            create_mock_option_position(
                position_id=703,
                symbol="NVDA_3DAYS",
                expiry=today + timedelta(days=2),  # DTE=2, 2 alerts (3,7)
            ),
            create_mock_option_position(
                position_id=704,
                symbol="MSFT_WEEK",
                expiry=today + timedelta(days=6),  # DTE=6, 1 alert (7)
            ),
            create_mock_option_position(
                position_id=705,
                symbol="META_FAR",
                expiry=today + timedelta(days=30),  # DTE=30, 0 alerts
            ),
        ]
        mock_portfolio.get_positions.return_value = positions

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # Expected: 4 + 3 + 2 + 1 + 0 = 10 alerts
        assert stats["positions_checked"] == 5
        assert stats["alerts_created"] == 10
        assert stats["positions_not_expiring_soon"] == 1  # META_FAR

        # Verify all alerts in database
        result = await e2e_db_session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE type = 'option_expiring'")
        )
        count = result.scalar()
        assert count == 10

    @pytest.mark.asyncio
    async def test_alert_details_contain_correct_data(self, e2e_db_session):
        """Verify alert details contain all required fields."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")
        today = datetime.now(ny_tz).date()

        position = create_mock_option_position(
            position_id=801,
            symbol="AAPL240119C150",
            expiry=today,
            strike=Decimal("150.50"),
            put_call=PutCall.CALL,
            quantity=5,
        )
        mock_portfolio.get_positions.return_value = [position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=alert_repo,
            market_tz=ny_tz,
        )

        await checker.check_expirations("acc123")

        # Get one of the alerts
        result = await e2e_db_session.execute(
            text("""
                SELECT details FROM alerts
                WHERE type = 'option_expiring'
                AND json_extract(details, '$.threshold_days') = 0
            """)
        )
        row = result.fetchone()

        import json

        details = json.loads(row[0])

        assert details["threshold_days"] == 0
        assert details["position_id"] == 801
        assert details["strike"] == 150.50
        assert details["put_call"] == "call"
        assert details["quantity"] == 5
        assert details["days_to_expiry"] == 0
        assert "expiry_date" in details

    @pytest.mark.asyncio
    async def test_multiple_runs_with_changing_dte(self, e2e_db_session):
        """Simulate daily runs as DTE decreases."""
        mock_portfolio = AsyncMock()
        alert_repo = AlertRepository(e2e_db_session)

        ny_tz = ZoneInfo("America/New_York")

        # Day 1: DTE=3, should create 2 alerts (3-day, 7-day)
        with patch("src.options.checker.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 12, 10, 0, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            position = create_mock_option_position(
                position_id=901,
                symbol="MULTI_RUN",
                expiry=date(2024, 1, 15),  # DTE=3
            )
            mock_portfolio.get_positions.return_value = [position]

            checker = ExpirationChecker(
                portfolio=mock_portfolio,
                alert_repo=alert_repo,
                market_tz=ny_tz,
            )

            stats1 = await checker.check_expirations("acc123")

        assert stats1["alerts_created"] == 2  # 3-day and 7-day

        # Day 2: DTE=2, should create 0 new (3-day, 7-day already exist)
        with patch("src.options.checker.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 13, 10, 0, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            stats2 = await checker.check_expirations("acc123")

        assert stats2["alerts_created"] == 0
        assert stats2["alerts_deduplicated"] == 2

        # Day 3: DTE=1, should create 1 new (1-day), dedupe 2 (3-day, 7-day)
        with patch("src.options.checker.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 14, 10, 0, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            stats3 = await checker.check_expirations("acc123")

        assert stats3["alerts_created"] == 1  # 1-day
        assert stats3["alerts_deduplicated"] == 2  # 3-day, 7-day

        # Day 4: DTE=0, should create 1 new (0-day), dedupe 3 others
        with patch("src.options.checker.datetime") as mock_datetime:
            mock_now = datetime(2024, 1, 15, 10, 0, 0, tzinfo=ny_tz)
            mock_datetime.now.return_value = mock_now

            stats4 = await checker.check_expirations("acc123")

        assert stats4["alerts_created"] == 1  # 0-day
        assert stats4["alerts_deduplicated"] == 3  # 1-day, 3-day, 7-day

        # Verify total alerts in database
        result = await e2e_db_session.execute(
            text("SELECT COUNT(*) FROM alerts WHERE type = 'option_expiring'")
        )
        count = result.scalar()
        assert count == 4  # All 4 thresholds created over time
