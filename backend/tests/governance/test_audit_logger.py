"""Tests for governance audit logger.

TDD: Write tests FIRST, then implement logger to make them pass.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.governance.models import GovernanceAuditEventType


class TestGovernanceAuditLogger:
    """Tests for GovernanceAuditLogger class."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async SQLAlchemy session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        return session

    @pytest.fixture
    def logger(self, mock_session):
        """Create a GovernanceAuditLogger instance."""
        from src.governance.audit.logger import GovernanceAuditLogger

        return GovernanceAuditLogger(session=mock_session)

    @pytest.mark.asyncio
    async def test_log_creates_audit_entry(self, logger, mock_session):
        """log() should create an audit entry in the database."""
        # Configure mock to return an ID
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_session.execute.return_value = mock_result

        event_id = await logger.log(
            event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
            constraint_id="growth_leverage_guard",
        )

        assert event_id == 1
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_log_with_all_fields(self, logger, mock_session):
        """log() should accept all optional fields."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute.return_value = mock_result

        event_id = await logger.log(
            event_type=GovernanceAuditEventType.FALSIFIER_CHECK_TRIGGERED,
            hypothesis_id="memory_demand_2027",
            constraint_id="tech_sector_guard",
            symbol="AAPL",
            strategy_id="momentum_strategy",
            action_details={"metric": "rolling_ic", "value": -0.05, "threshold": 0},
            trace_id="trace-123-456",
        )

        assert event_id == 42
        # Verify the execute was called with the right parameters
        call_args = mock_session.execute.call_args
        assert call_args is not None

    @pytest.mark.asyncio
    async def test_log_pool_built_event(self, logger, mock_session):
        """log() should handle POOL_BUILT event type."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_session.execute.return_value = mock_result

        event_id = await logger.log(
            event_type=GovernanceAuditEventType.POOL_BUILT,
            action_details={
                "symbol_count": 50,
                "version": "20260203_abc123",
            },
        )

        assert event_id == 10

    @pytest.mark.asyncio
    async def test_log_regime_changed_event(self, logger, mock_session):
        """log() should handle REGIME_CHANGED event type."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 15
        mock_session.execute.return_value = mock_result

        event_id = await logger.log(
            event_type=GovernanceAuditEventType.REGIME_CHANGED,
            action_details={
                "old_state": "NORMAL",
                "new_state": "STRESS",
                "volatility": 0.35,
            },
        )

        assert event_id == 15

    @pytest.mark.asyncio
    async def test_query_with_time_filter(self, logger, mock_session):
        """query() should filter by time range."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        end = datetime(2026, 12, 31, tzinfo=timezone.utc)

        results = await logger.query(start_time=start, end_time=end)

        assert results == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_with_event_type_filter(self, logger, mock_session):
        """query() should filter by event type."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        results = await logger.query(event_type=GovernanceAuditEventType.POOL_BUILT)

        assert results == []

    @pytest.mark.asyncio
    async def test_query_with_symbol_filter(self, logger, mock_session):
        """query() should filter by symbol."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        results = await logger.query(symbol="AAPL")

        assert results == []

    @pytest.mark.asyncio
    async def test_query_with_constraint_id_filter(self, logger, mock_session):
        """query() should filter by constraint_id."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        results = await logger.query(constraint_id="growth_leverage_guard")

        assert results == []

    @pytest.mark.asyncio
    async def test_query_returns_list_of_dicts(self, logger, mock_session):
        """query() should return list of dicts."""
        mock_row = MagicMock()
        mock_row._mapping = {
            "id": 1,
            "timestamp": datetime(2026, 2, 3, tzinfo=timezone.utc),
            "event_type": "pool_built",
            "hypothesis_id": None,
            "constraint_id": None,
            "symbol": None,
            "strategy_id": None,
            "action_details": {"symbol_count": 50},
            "trace_id": None,
        }
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        results = await logger.query(limit=10)

        assert len(results) == 1
        assert results[0]["id"] == 1
        assert results[0]["event_type"] == "pool_built"

    @pytest.mark.asyncio
    async def test_query_respects_limit(self, logger, mock_session):
        """query() should respect the limit parameter."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await logger.query(limit=50)

        # Check that limit was in the SQL query
        call_args = mock_session.execute.call_args
        assert call_args is not None
        # The limit should be in the params
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
        assert params.get("limit") == 50

    @pytest.mark.asyncio
    async def test_query_default_limit(self, logger, mock_session):
        """query() should default to limit of 100."""
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result

        await logger.query()

        call_args = mock_session.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
        assert params.get("limit") == 100


class TestGovernanceAuditLoggerInitialization:
    """Tests for GovernanceAuditLogger initialization."""

    def test_init_with_session(self):
        """Should initialize with a session."""
        from src.governance.audit.logger import GovernanceAuditLogger

        mock_session = AsyncMock()
        logger = GovernanceAuditLogger(session=mock_session)

        assert logger.session == mock_session


class TestAllExports:
    """Test that all required types are exported."""

    def test_all_exports_available(self):
        """GovernanceAuditLogger should be importable."""
        from src.governance.audit.logger import GovernanceAuditLogger

        assert GovernanceAuditLogger is not None

    def test_audit_log_entry_importable(self):
        """AuditLogEntry should be importable from audit.models."""
        from src.governance.audit.models import AuditLogEntry

        assert AuditLogEntry is not None

    def test_in_memory_audit_store_importable(self):
        """InMemoryAuditStore should be importable from audit.store."""
        from src.governance.audit.store import InMemoryAuditStore

        assert InMemoryAuditStore is not None

    def test_audit_module_exports(self):
        """Audit __init__ should export GovernanceAuditLogger, AuditLogEntry, InMemoryAuditStore."""
        from src.governance.audit import (
            AuditLogEntry,
            GovernanceAuditLogger,
            InMemoryAuditStore,
        )

        assert GovernanceAuditLogger is not None
        assert AuditLogEntry is not None
        assert InMemoryAuditStore is not None


# =============================================================================
# AuditLogEntry Model Tests (T061)
# =============================================================================


class TestAuditLogEntryModel:
    """Tests for AuditLogEntry Pydantic model."""

    def test_create_audit_log_entry_with_required_fields(self):
        """AuditLogEntry should be created with required fields."""
        from src.governance.audit.models import AuditLogEntry

        entry = AuditLogEntry(
            id=1,
            timestamp=datetime(2026, 2, 3, tzinfo=timezone.utc),
            event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
        )

        assert entry.id == 1
        assert entry.event_type == GovernanceAuditEventType.CONSTRAINT_ACTIVATED
        assert entry.hypothesis_id is None
        assert entry.constraint_id is None
        assert entry.symbol is None
        assert entry.strategy_id is None
        assert entry.action_details == {}
        assert entry.trace_id is None

    def test_create_audit_log_entry_with_all_fields(self):
        """AuditLogEntry should accept all optional fields."""
        from src.governance.audit.models import AuditLogEntry

        entry = AuditLogEntry(
            id=42,
            timestamp=datetime(2026, 2, 3, 10, 0, 0, tzinfo=timezone.utc),
            event_type=GovernanceAuditEventType.FALSIFIER_CHECK_TRIGGERED,
            hypothesis_id="momentum_persistence",
            constraint_id="growth_leverage_guard",
            symbol="AAPL",
            strategy_id="momentum_strategy",
            action_details={"metric": "rolling_ic", "value": -0.05},
            trace_id="trace-abc-123",
        )

        assert entry.id == 42
        assert entry.hypothesis_id == "momentum_persistence"
        assert entry.constraint_id == "growth_leverage_guard"
        assert entry.symbol == "AAPL"
        assert entry.strategy_id == "momentum_strategy"
        assert entry.action_details == {"metric": "rolling_ic", "value": -0.05}
        assert entry.trace_id == "trace-abc-123"

    def test_audit_log_entry_extends_governance_base_model(self):
        """AuditLogEntry should extend GovernanceBaseModel (extra='forbid')."""
        from pydantic import ValidationError
        from src.governance.audit.models import AuditLogEntry

        with pytest.raises(ValidationError):
            AuditLogEntry(
                id=1,
                timestamp=datetime(2026, 2, 3, tzinfo=timezone.utc),
                event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
                unknown_field="should_fail",
            )

    def test_audit_log_entry_validates_event_type(self):
        """AuditLogEntry should validate event_type is a GovernanceAuditEventType."""

        from src.governance.audit.models import AuditLogEntry

        # Valid enum value string should work
        entry = AuditLogEntry(
            id=1,
            timestamp=datetime(2026, 2, 3, tzinfo=timezone.utc),
            event_type="constraint_activated",
        )
        assert entry.event_type == GovernanceAuditEventType.CONSTRAINT_ACTIVATED

    def test_audit_log_entry_serialization(self):
        """AuditLogEntry should serialize to dict properly."""
        from src.governance.audit.models import AuditLogEntry

        entry = AuditLogEntry(
            id=1,
            timestamp=datetime(2026, 2, 3, 10, 0, 0, tzinfo=timezone.utc),
            event_type=GovernanceAuditEventType.POOL_BUILT,
            action_details={"symbol_count": 50},
        )

        data = entry.model_dump()
        assert data["id"] == 1
        assert data["event_type"] == GovernanceAuditEventType.POOL_BUILT
        assert data["action_details"] == {"symbol_count": 50}

    def test_audit_log_entry_all_event_types(self):
        """AuditLogEntry should accept all GovernanceAuditEventType values."""
        from src.governance.audit.models import AuditLogEntry

        for event_type in GovernanceAuditEventType:
            entry = AuditLogEntry(
                id=1,
                timestamp=datetime(2026, 2, 3, tzinfo=timezone.utc),
                event_type=event_type,
            )
            assert entry.event_type == event_type


# =============================================================================
# InMemoryAuditStore Tests (T062/T065)
# =============================================================================


class TestInMemoryAuditStore:
    """Tests for InMemoryAuditStore."""

    @pytest.fixture
    def store(self):
        """Create a fresh InMemoryAuditStore."""
        from src.governance.audit.store import InMemoryAuditStore

        return InMemoryAuditStore()

    def test_log_returns_auto_increment_id(self, store):
        """log() should return auto-incrementing IDs starting from 1."""
        id1 = store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        id2 = store.log(event_type=GovernanceAuditEventType.POOL_BUILT)
        id3 = store.log(event_type=GovernanceAuditEventType.REGIME_CHANGED)

        assert id1 == 1
        assert id2 == 2
        assert id3 == 3

    def test_log_stores_entry(self, store):
        """log() should store the entry in the internal list."""
        store.log(
            event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
            constraint_id="test_constraint",
        )

        assert store.count() == 1

    def test_log_with_all_fields(self, store):
        """log() should store entries with all optional fields."""
        store.log(
            event_type=GovernanceAuditEventType.FALSIFIER_CHECK_TRIGGERED,
            hypothesis_id="momentum_persistence",
            constraint_id="growth_guard",
            symbol="AAPL",
            strategy_id="momentum",
            action_details={"metric": "ic", "value": -0.05},
            trace_id="trace-123",
        )

        entries = store.query()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.hypothesis_id == "momentum_persistence"
        assert entry.constraint_id == "growth_guard"
        assert entry.symbol == "AAPL"
        assert entry.strategy_id == "momentum"
        assert entry.action_details == {"metric": "ic", "value": -0.05}
        assert entry.trace_id == "trace-123"

    def test_query_returns_all_entries_by_default(self, store):
        """query() should return all entries when no filters applied."""
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        store.log(event_type=GovernanceAuditEventType.POOL_BUILT)

        results = store.query()
        assert len(results) == 2

    def test_query_filters_by_event_type(self, store):
        """query() should filter by event_type."""
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        store.log(event_type=GovernanceAuditEventType.POOL_BUILT)
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)

        results = store.query(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        assert len(results) == 2
        for entry in results:
            assert entry.event_type == GovernanceAuditEventType.CONSTRAINT_ACTIVATED

    def test_query_filters_by_symbol(self, store):
        """query() should filter by symbol."""
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED, symbol="AAPL")
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED, symbol="NVDA")

        results = store.query(symbol="AAPL")
        assert len(results) == 1
        assert results[0].symbol == "AAPL"

    def test_query_filters_by_constraint_id(self, store):
        """query() should filter by constraint_id."""
        store.log(
            event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
            constraint_id="guard_a",
        )
        store.log(
            event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
            constraint_id="guard_b",
        )

        results = store.query(constraint_id="guard_a")
        assert len(results) == 1
        assert results[0].constraint_id == "guard_a"

    def test_query_respects_limit(self, store):
        """query() should respect the limit parameter."""
        for _i in range(10):
            store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)

        results = store.query(limit=3)
        assert len(results) == 3

    def test_query_default_limit_is_100(self, store):
        """query() should default to a limit of 100."""
        for _i in range(150):
            store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)

        results = store.query()
        assert len(results) == 100

    def test_query_orders_by_timestamp_descending(self, store):
        """query() should return results ordered by timestamp descending."""
        store.log(
            event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
            constraint_id="first",
        )
        store.log(
            event_type=GovernanceAuditEventType.POOL_BUILT,
            constraint_id="second",
        )

        results = store.query()
        # Newest (second) should come first
        assert results[0].constraint_id == "second"
        assert results[1].constraint_id == "first"

    def test_query_filters_by_time_range(self, store):
        """query() should filter by start_time and end_time."""
        # We need to directly test the time filter logic
        import time

        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        time.sleep(0.01)
        mid_time = datetime.now(timezone.utc)
        time.sleep(0.01)
        store.log(event_type=GovernanceAuditEventType.POOL_BUILT)

        # Only entries after mid_time
        results = store.query(start_time=mid_time)
        assert len(results) == 1
        assert results[0].event_type == GovernanceAuditEventType.POOL_BUILT

    def test_count_returns_total_entries(self, store):
        """count() should return the total number of entries."""
        assert store.count() == 0
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        assert store.count() == 1
        store.log(event_type=GovernanceAuditEventType.POOL_BUILT)
        assert store.count() == 2

    def test_clear_removes_all_entries(self, store):
        """clear() should remove all entries and reset ID counter."""
        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        store.log(event_type=GovernanceAuditEventType.POOL_BUILT)
        assert store.count() == 2

        store.clear()
        assert store.count() == 0

        # ID counter should reset
        new_id = store.log(event_type=GovernanceAuditEventType.REGIME_CHANGED)
        assert new_id == 1

    def test_entries_are_audit_log_entry_type(self, store):
        """query() should return AuditLogEntry instances."""
        from src.governance.audit.models import AuditLogEntry

        store.log(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        results = store.query()
        assert isinstance(results[0], AuditLogEntry)
