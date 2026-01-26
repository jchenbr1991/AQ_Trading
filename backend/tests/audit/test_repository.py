"""Tests for audit repository with chain integrity.

TDD: Write tests FIRST, then implement repository.py to make them pass.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
)


def create_mock_row(data: dict):
    """Create a mock row object that supports both dict and index access."""
    mock_row = MagicMock()
    mock_row._mapping = data

    # Support index access - use side_effect for proper index handling
    values_list = list(data.values())

    def getitem(idx):
        if isinstance(idx, int):
            return values_list[idx]
        return data[idx]

    mock_row.__getitem__ = MagicMock(side_effect=getitem)
    return mock_row


def create_test_event(
    event_id=None,
    timestamp=None,
    event_type=AuditEventType.ORDER_PLACED,
    actor_id="user-123",
    resource_type=ResourceType.ORDER,
    resource_id="order-456",
    old_value=None,
    new_value=None,
) -> AuditEvent:
    """Helper to create test audit events."""
    return AuditEvent(
        event_id=event_id or uuid4(),
        timestamp=timestamp or datetime.now(tz=timezone.utc),
        event_type=event_type,
        severity=AuditSeverity.INFO,
        actor_id=actor_id,
        actor_type=ActorType.USER,
        resource_type=resource_type,
        resource_id=resource_id,
        old_value=old_value,
        new_value=new_value,
        request_id="req-789",
        source=EventSource.WEB,
        environment="production",
        service="trading-api",
        version="1.0.0",
    )


class TestAuditQueryFilters:
    """Tests for AuditQueryFilters dataclass."""

    def test_audit_query_filters_has_expected_fields(self):
        """AuditQueryFilters should have expected filter fields."""
        from src.audit.repository import AuditQueryFilters

        filters = AuditQueryFilters()

        # Check all expected fields exist with None defaults
        assert hasattr(filters, "event_type")
        assert hasattr(filters, "resource_type")
        assert hasattr(filters, "resource_id")
        assert hasattr(filters, "actor_id")
        assert hasattr(filters, "start_time")
        assert hasattr(filters, "end_time")
        assert hasattr(filters, "offset")
        assert hasattr(filters, "limit")

    def test_audit_query_filters_defaults(self):
        """AuditQueryFilters should have sensible defaults."""
        from src.audit.repository import AuditQueryFilters

        filters = AuditQueryFilters()

        assert filters.event_type is None
        assert filters.resource_type is None
        assert filters.resource_id is None
        assert filters.actor_id is None
        assert filters.start_time is None
        assert filters.end_time is None
        assert filters.offset == 0
        assert filters.limit == 100

    def test_audit_query_filters_accepts_values(self):
        """AuditQueryFilters should accept filter values."""
        from src.audit.repository import AuditQueryFilters

        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        end = datetime(2024, 1, 31, tzinfo=timezone.utc)

        filters = AuditQueryFilters(
            event_type=AuditEventType.ORDER_PLACED,
            resource_type=ResourceType.ORDER,
            resource_id="order-123",
            actor_id="user-456",
            start_time=start,
            end_time=end,
            offset=10,
            limit=50,
        )

        assert filters.event_type == AuditEventType.ORDER_PLACED
        assert filters.resource_type == ResourceType.ORDER
        assert filters.resource_id == "order-123"
        assert filters.actor_id == "user-456"
        assert filters.start_time == start
        assert filters.end_time == end
        assert filters.offset == 10
        assert filters.limit == 50


class TestAuditRepository:
    """Tests for AuditRepository class."""

    def test_repository_accepts_session(self):
        """AuditRepository should accept an async session."""
        from src.audit.repository import AuditRepository

        mock_session = MagicMock()
        repo = AuditRepository(mock_session)

        assert repo._session is mock_session


def create_persist_mock_session(
    chain_head_checksum: str | None = None,
    chain_head_sequence: int | None = None,
    next_sequence: int = 1,
):
    """Create a mock session for persist_audit_event tests.

    Args:
        chain_head_checksum: Existing chain head checksum (None for new chain)
        chain_head_sequence: Existing chain head sequence_id
        next_sequence: Next sequence ID to return

    Returns:
        Configured AsyncMock session
    """
    mock_session = AsyncMock()

    # Mock chain_head SELECT FOR UPDATE result
    chain_head_result = MagicMock()
    if chain_head_checksum is not None:
        chain_head_result.fetchone.return_value = create_mock_row(
            {
                "chain_key": "default",
                "checksum": chain_head_checksum,
                "sequence_id": chain_head_sequence,
            }
        )
    else:
        chain_head_result.fetchone.return_value = None

    # Mock sequence nextval result
    sequence_result = MagicMock()
    sequence_result.scalar.return_value = next_sequence

    # Mock INSERT and upsert results (don't need return values)
    insert_result = MagicMock()
    upsert_result = MagicMock()

    # Configure execute to return different results for each call
    mock_session.execute = AsyncMock(
        side_effect=[chain_head_result, sequence_result, insert_result, upsert_result]
    )

    return mock_session


class TestPersistAuditEvent:
    """Tests for persist_audit_event method."""

    @pytest.mark.asyncio
    async def test_persist_audit_event_returns_sequence_id_and_checksum(self):
        """persist_audit_event should return (sequence_id, checksum) tuple."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session(next_sequence=1)

        repo = AuditRepository(mock_session)
        event = create_test_event()

        sequence_id, checksum = await repo.persist_audit_event(event)

        assert isinstance(sequence_id, int)
        assert sequence_id == 1
        assert isinstance(checksum, str)
        assert len(checksum) == 64  # SHA256 hex digest

    @pytest.mark.asyncio
    async def test_persist_audit_event_locks_chain_head_for_update(self):
        """persist_audit_event should lock chain_head row FOR UPDATE."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session()

        repo = AuditRepository(mock_session)
        event = create_test_event()

        await repo.persist_audit_event(event)

        # First call should be SELECT ... FOR UPDATE on audit_chain_head
        first_call = mock_session.execute.call_args_list[0]
        query = str(first_call[0][0])
        assert "audit_chain_head" in query.lower()
        assert "for update" in query.lower()

    @pytest.mark.asyncio
    async def test_persist_audit_event_gets_sequence_from_sequence(self):
        """persist_audit_event should get next value from audit_sequence."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session(next_sequence=42)

        repo = AuditRepository(mock_session)
        event = create_test_event()

        sequence_id, _ = await repo.persist_audit_event(event)

        assert sequence_id == 42
        # Second call should be SELECT nextval
        second_call = mock_session.execute.call_args_list[1]
        query = str(second_call[0][0])
        assert "nextval" in query.lower()
        assert "audit_sequence" in query.lower()

    @pytest.mark.asyncio
    async def test_persist_audit_event_computes_checksum(self):
        """persist_audit_event should compute checksum using integrity module."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session()

        repo = AuditRepository(mock_session)
        event = create_test_event()

        with patch("src.audit.repository.compute_checksum") as mock_checksum:
            mock_checksum.return_value = "a" * 64

            _, checksum = await repo.persist_audit_event(event)

            mock_checksum.assert_called_once()
            assert checksum == "a" * 64

    @pytest.mark.asyncio
    async def test_persist_audit_event_uses_prev_checksum_from_chain_head(self):
        """persist_audit_event should use prev_checksum from existing chain_head."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session(
            chain_head_checksum="prev_checksum_value",
            chain_head_sequence=5,
            next_sequence=6,
        )

        repo = AuditRepository(mock_session)
        event = create_test_event()

        with patch("src.audit.repository.compute_checksum") as mock_checksum:
            mock_checksum.return_value = "b" * 64

            await repo.persist_audit_event(event)

            # Verify compute_checksum was called with prev_checksum
            call_args = mock_checksum.call_args
            assert (
                call_args[1].get("prev_checksum") == "prev_checksum_value"
                or call_args[0][2] == "prev_checksum_value"
            )

    @pytest.mark.asyncio
    async def test_persist_audit_event_inserts_into_audit_logs(self):
        """persist_audit_event should INSERT into audit_logs table."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session()

        repo = AuditRepository(mock_session)
        event = create_test_event()

        await repo.persist_audit_event(event)

        # Should have calls for: chain_head SELECT, sequence nextval, INSERT, chain_head upsert
        assert mock_session.execute.call_count >= 3

        # Find the INSERT call
        insert_call_found = False
        for call in mock_session.execute.call_args_list:
            query = str(call[0][0]).lower()
            if "insert" in query and "audit_logs" in query:
                insert_call_found = True
                break

        assert insert_call_found, "INSERT into audit_logs not found"

    @pytest.mark.asyncio
    async def test_persist_audit_event_upserts_chain_head(self):
        """persist_audit_event should upsert audit_chain_head."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session()

        repo = AuditRepository(mock_session)
        event = create_test_event()

        await repo.persist_audit_event(event)

        # Find the chain_head upsert call (INSERT ... ON CONFLICT)
        upsert_call_found = False
        for call in mock_session.execute.call_args_list:
            query = str(call[0][0]).lower()
            if "audit_chain_head" in query and ("on conflict" in query or "update" in query):
                upsert_call_found = True
                break

        assert upsert_call_found, "Upsert on audit_chain_head not found"

    @pytest.mark.asyncio
    async def test_persist_audit_event_with_custom_chain_key(self):
        """persist_audit_event should support custom chain_key."""
        from src.audit.repository import AuditRepository

        mock_session = create_persist_mock_session()

        repo = AuditRepository(mock_session)
        event = create_test_event()

        await repo.persist_audit_event(event, chain_key="orders")

        # Verify chain_key was used in the query
        first_call = mock_session.execute.call_args_list[0]
        # The chain_key should be in the parameters
        assert "orders" in str(first_call)


class TestGetAuditEvent:
    """Tests for get_audit_event method."""

    @pytest.mark.asyncio
    async def test_get_audit_event_returns_dict_when_found(self):
        """get_audit_event should return dict when event exists."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()
        event_id = uuid4()

        # Create a proper mock row with all expected columns
        row_data = {
            "id": event_id,
            "sequence_id": 1,
            "timestamp": datetime.now(tz=timezone.utc),
            "event_type": "order_placed",
            "severity": "info",
            "actor_id": "user-123",
            "actor_type": "user",
            "resource_type": "order",
            "resource_id": "order-456",
            "request_id": "req-789",
            "source": "web",
            "environment": "production",
            "service": "trading-api",
            "version": "1.0.0",
            "correlation_id": None,
            "value_mode": "diff",
            "old_value": None,
            "new_value": None,
            "metadata": None,
            "checksum": "a" * 64,
            "prev_checksum": None,
            "chain_key": "default",
        }

        mock_result = MagicMock()
        mock_result.fetchone.return_value = create_mock_row(row_data)

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        result = await repo.get_audit_event(event_id)

        assert result is not None
        assert isinstance(result, dict)
        assert result["id"] == event_id

    @pytest.mark.asyncio
    async def test_get_audit_event_returns_none_when_not_found(self):
        """get_audit_event should return None when event doesn't exist."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()
        event_id = uuid4()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        result = await repo.get_audit_event(event_id)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_audit_event_queries_by_id(self):
        """get_audit_event should query by event id."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()
        event_id = uuid4()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        await repo.get_audit_event(event_id)

        # Verify SELECT query with id filter
        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "select" in query
        assert "audit_logs" in query


def create_full_audit_row(event_id=None, event_type="order_placed"):
    """Create a full audit row dict with all columns."""
    return {
        "id": event_id or uuid4(),
        "sequence_id": 1,
        "timestamp": datetime.now(tz=timezone.utc),
        "event_type": event_type,
        "severity": "info",
        "actor_id": "user-123",
        "actor_type": "user",
        "resource_type": "order",
        "resource_id": "order-456",
        "request_id": "req-789",
        "source": "web",
        "environment": "production",
        "service": "trading-api",
        "version": "1.0.0",
        "correlation_id": None,
        "value_mode": "diff",
        "old_value": None,
        "new_value": None,
        "metadata": None,
        "checksum": "a" * 64,
        "prev_checksum": None,
        "chain_key": "default",
    }


class TestQueryAuditLogs:
    """Tests for query_audit_logs method."""

    @pytest.mark.asyncio
    async def test_query_audit_logs_returns_list(self):
        """query_audit_logs should return list of dicts."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            create_mock_row(create_full_audit_row(event_type="order_placed")),
            create_mock_row(create_full_audit_row(event_type="order_filled")),
        ]

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters()

        results = await repo.query_audit_logs(filters)

        assert isinstance(results, list)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_query_audit_logs_returns_empty_list(self):
        """query_audit_logs should return empty list when no results."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters()

        results = await repo.query_audit_logs(filters)

        assert results == []

    @pytest.mark.asyncio
    async def test_query_audit_logs_filters_by_event_type(self):
        """query_audit_logs should filter by event_type."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters(event_type=AuditEventType.ORDER_PLACED)

        await repo.query_audit_logs(filters)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "event_type" in query

    @pytest.mark.asyncio
    async def test_query_audit_logs_filters_by_resource_type(self):
        """query_audit_logs should filter by resource_type."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters(resource_type=ResourceType.ORDER)

        await repo.query_audit_logs(filters)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "resource_type" in query

    @pytest.mark.asyncio
    async def test_query_audit_logs_filters_by_resource_id(self):
        """query_audit_logs should filter by resource_id."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters(resource_id="order-123")

        await repo.query_audit_logs(filters)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "resource_id" in query

    @pytest.mark.asyncio
    async def test_query_audit_logs_filters_by_actor_id(self):
        """query_audit_logs should filter by actor_id."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters(actor_id="user-456")

        await repo.query_audit_logs(filters)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "actor_id" in query

    @pytest.mark.asyncio
    async def test_query_audit_logs_filters_by_time_range(self):
        """query_audit_logs should filter by start_time and end_time."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters(
            start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
            end_time=datetime(2024, 1, 31, tzinfo=timezone.utc),
        )

        await repo.query_audit_logs(filters)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "timestamp" in query

    @pytest.mark.asyncio
    async def test_query_audit_logs_applies_pagination(self):
        """query_audit_logs should apply offset and limit."""
        from src.audit.repository import AuditQueryFilters, AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        filters = AuditQueryFilters(offset=20, limit=10)

        await repo.query_audit_logs(filters)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "limit" in query
        assert "offset" in query


class TestGetChainHead:
    """Tests for get_chain_head method."""

    @pytest.mark.asyncio
    async def test_get_chain_head_returns_dict_when_found(self):
        """get_chain_head should return dict when chain exists."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        # Create a mock row that supports index access
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, i: ["default", "abc123", 42, None][i]

        mock_result.fetchone.return_value = mock_row

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        result = await repo.get_chain_head("default")

        assert result is not None
        assert result["chain_key"] == "default"
        assert result["checksum"] == "abc123"
        assert result["sequence_id"] == 42

    @pytest.mark.asyncio
    async def test_get_chain_head_returns_none_when_not_found(self):
        """get_chain_head should return None when chain doesn't exist."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchone.return_value = None

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        result = await repo.get_chain_head("nonexistent")

        assert result is None


class TestVerifyChainIntegrity:
    """Tests for verify_chain_integrity method."""

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_returns_tuple(self):
        """verify_chain_integrity should return (is_valid, errors) tuple."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        is_valid, errors = await repo.verify_chain_integrity("default")

        assert isinstance(is_valid, bool)
        assert isinstance(errors, list)

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_valid_empty_chain(self):
        """verify_chain_integrity should return valid for empty chain."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        is_valid, errors = await repo.verify_chain_integrity("default")

        assert is_valid is True
        assert errors == []

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_uses_integrity_module(self):
        """verify_chain_integrity should use integrity.verify_chain."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [create_mock_row(create_full_audit_row())]

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)

        with patch("src.audit.repository.verify_chain") as mock_verify:
            mock_verify.return_value = (True, [])

            await repo.verify_chain_integrity("default")

            mock_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_respects_limit(self):
        """verify_chain_integrity should respect the limit parameter."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        await repo.verify_chain_integrity("default", limit=50)

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "limit" in query

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_orders_by_sequence_id(self):
        """verify_chain_integrity should order events by sequence_id ASC."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)
        await repo.verify_chain_integrity("default")

        call = mock_session.execute.call_args
        query = str(call[0][0]).lower()
        assert "order by" in query
        assert "sequence_id" in query

    @pytest.mark.asyncio
    async def test_verify_chain_integrity_returns_errors_on_failure(self):
        """verify_chain_integrity should return errors from verify_chain."""
        from src.audit.repository import AuditRepository

        mock_session = AsyncMock()

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [create_mock_row(create_full_audit_row())]

        mock_session.execute = AsyncMock(return_value=mock_result)

        repo = AuditRepository(mock_session)

        with patch("src.audit.repository.verify_chain") as mock_verify:
            mock_verify.return_value = (False, ["Error 1", "Error 2"])

            is_valid, errors = await repo.verify_chain_integrity("default")

            assert is_valid is False
            assert errors == ["Error 1", "Error 2"]
