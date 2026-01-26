"""Tests for audit factory and context manager.

TDD: Write tests FIRST, then implement factory.py to make them pass.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from src.audit.models import (
    ActorType,
    AuditEvent,
    AuditEventType,
    AuditSeverity,
    EventSource,
    ResourceType,
    ValueMode,
)


class TestCreateAuditEvent:
    """Tests for create_audit_event() factory function."""

    def test_create_audit_event_returns_audit_event(self):
        """create_audit_event should return an AuditEvent instance."""
        from src.audit.factory import create_audit_event

        event = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert isinstance(event, AuditEvent)

    def test_create_audit_event_generates_uuid(self):
        """create_audit_event should generate a unique UUID for event_id."""
        from src.audit.factory import create_audit_event

        event1 = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        event2 = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert isinstance(event1.event_id, UUID)
        assert isinstance(event2.event_id, UUID)
        assert event1.event_id != event2.event_id

    def test_create_audit_event_sets_utc_timestamp(self):
        """create_audit_event should set timestamp to current UTC time."""
        from src.audit.factory import create_audit_event

        before = datetime.now(tz=timezone.utc)

        event = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        after = datetime.now(tz=timezone.utc)

        assert event.timestamp.tzinfo is not None
        assert before <= event.timestamp <= after

    def test_create_audit_event_validates_required_fields(self):
        """create_audit_event should raise ValueError for missing required fields."""
        from src.audit.factory import create_audit_event

        with pytest.raises(ValueError, match="actor_id"):
            create_audit_event(
                event_type=AuditEventType.ORDER_PLACED,
                actor_id="",  # Empty actor_id
                actor_type=ActorType.USER,
                resource_type=ResourceType.ORDER,
                resource_id="order-456",
                request_id="req-789",
                source=EventSource.WEB,
                severity=AuditSeverity.INFO,
                environment="production",
                service="trading-api",
                version="1.0.0",
            )

    def test_create_audit_event_validates_resource_id(self):
        """create_audit_event should raise ValueError for empty resource_id."""
        from src.audit.factory import create_audit_event

        with pytest.raises(ValueError, match="resource_id"):
            create_audit_event(
                event_type=AuditEventType.ORDER_PLACED,
                actor_id="user-123",
                actor_type=ActorType.USER,
                resource_type=ResourceType.ORDER,
                resource_id="",  # Empty resource_id
                request_id="req-789",
                source=EventSource.WEB,
                severity=AuditSeverity.INFO,
                environment="production",
                service="trading-api",
                version="1.0.0",
            )

    def test_create_audit_event_validates_request_id(self):
        """create_audit_event should raise ValueError for empty request_id."""
        from src.audit.factory import create_audit_event

        with pytest.raises(ValueError, match="request_id"):
            create_audit_event(
                event_type=AuditEventType.ORDER_PLACED,
                actor_id="user-123",
                actor_type=ActorType.USER,
                resource_type=ResourceType.ORDER,
                resource_id="order-456",
                request_id="",  # Empty request_id
                source=EventSource.WEB,
                severity=AuditSeverity.INFO,
                environment="production",
                service="trading-api",
                version="1.0.0",
            )

    def test_create_audit_event_applies_value_mode_from_config(self):
        """create_audit_event should apply value_mode based on event_type using config."""
        from src.audit.factory import create_audit_event

        # ORDER_PLACED is configured to use SNAPSHOT mode
        event = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert event.value_mode == ValueMode.SNAPSHOT

    def test_create_audit_event_applies_diff_value_mode_for_config_updated(self):
        """create_audit_event should apply DIFF mode for CONFIG_UPDATED."""
        from src.audit.factory import create_audit_event

        # CONFIG_UPDATED is configured to use DIFF mode
        event = create_audit_event(
            event_type=AuditEventType.CONFIG_UPDATED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.CONFIG,
            resource_id="config-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert event.value_mode == ValueMode.DIFF

    def test_create_audit_event_defaults_to_diff_mode(self):
        """create_audit_event should default to DIFF mode for unconfigured event types."""
        from src.audit.factory import create_audit_event

        # ALERT_EMITTED is not in VALUE_MODE_CONFIG, should default to DIFF
        event = create_audit_event(
            event_type=AuditEventType.ALERT_EMITTED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ALERT,
            resource_id="alert-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert event.value_mode == ValueMode.DIFF

    def test_create_audit_event_sets_all_required_fields(self):
        """create_audit_event should set all required fields correctly."""
        from src.audit.factory import create_audit_event

        event = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert event.event_type == AuditEventType.ORDER_PLACED
        assert event.actor_id == "user-123"
        assert event.actor_type == ActorType.USER
        assert event.resource_type == ResourceType.ORDER
        assert event.resource_id == "order-456"
        assert event.request_id == "req-789"
        assert event.source == EventSource.WEB
        assert event.severity == AuditSeverity.INFO
        assert event.environment == "production"
        assert event.service == "trading-api"
        assert event.version == "1.0.0"

    def test_create_audit_event_accepts_optional_fields(self):
        """create_audit_event should accept optional fields."""
        from src.audit.factory import create_audit_event

        event = create_audit_event(
            event_type=AuditEventType.ORDER_PLACED,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            severity=AuditSeverity.INFO,
            environment="production",
            service="trading-api",
            version="1.0.0",
            old_value={"status": "pending"},
            new_value={"status": "filled"},
            metadata={"extra": "info"},
            correlation_id="corr-123",
            trace_id="trace-456",
            client_ip="192.168.1.1",
            user_agent="Mozilla/5.0",
            actor_display="John Doe",
            impersonator_id="admin-001",
        )

        assert event.old_value == {"status": "pending"}
        assert event.new_value == {"status": "filled"}
        assert event.metadata == {"extra": "info"}
        assert event.correlation_id == "corr-123"
        assert event.trace_id == "trace-456"
        assert event.client_ip == "192.168.1.1"
        assert event.user_agent == "Mozilla/5.0"
        assert event.actor_display == "John Doe"
        assert event.impersonator_id == "admin-001"


class TestAuditContextInit:
    """Tests for AuditContext initialization."""

    def test_audit_context_stores_request_context(self):
        """AuditContext should store request context."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        ctx = AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        )

        assert ctx.request_id == "req-123"
        assert ctx.actor_id == "user-456"
        assert ctx.actor_type == ActorType.USER
        assert ctx.source == EventSource.WEB
        assert ctx._service is mock_service

    def test_audit_context_accepts_optional_fields(self):
        """AuditContext should accept optional context fields."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        ctx = AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
            trace_id="trace-789",
            correlation_id="corr-012",
            client_ip="10.0.0.1",
            user_agent="TestAgent/1.0",
            actor_display="Test User",
            impersonator_id="admin-999",
        )

        assert ctx.trace_id == "trace-789"
        assert ctx.correlation_id == "corr-012"
        assert ctx.client_ip == "10.0.0.1"
        assert ctx.user_agent == "TestAgent/1.0"
        assert ctx.actor_display == "Test User"
        assert ctx.impersonator_id == "admin-999"


class TestAuditContextManager:
    """Tests for AuditContext as async context manager."""

    @pytest.mark.asyncio
    async def test_audit_context_async_enter_returns_self(self):
        """AuditContext should return self when entering async context."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        ctx = AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        )

        async with ctx as entered_ctx:
            assert entered_ctx is ctx

    @pytest.mark.asyncio
    async def test_audit_context_async_exit_no_errors(self):
        """AuditContext should exit cleanly without errors."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        ctx = AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        )

        async with ctx:
            pass  # Should exit without error


class TestAuditContextLog:
    """Tests for AuditContext.log() method."""

    @pytest.mark.asyncio
    async def test_audit_context_log_delegates_to_service(self):
        """AuditContext.log() should delegate to AuditService.log()."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            result = ctx.log(
                event_type=AuditEventType.ORDER_PLACED,
                resource_type=ResourceType.ORDER,
                resource_id="order-789",
                severity=AuditSeverity.INFO,
            )

        assert isinstance(result, UUID)
        mock_service.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_context_log_uses_stored_context(self):
        """AuditContext.log() should use stored request context."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            ctx.log(
                event_type=AuditEventType.ORDER_PLACED,
                resource_type=ResourceType.ORDER,
                resource_id="order-789",
                severity=AuditSeverity.INFO,
            )

        # Check that stored context was passed to service.log()
        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["request_id"] == "req-123"
        assert call_kwargs["actor_id"] == "user-456"
        assert call_kwargs["actor_type"] == ActorType.USER
        assert call_kwargs["source"] == EventSource.WEB

    @pytest.mark.asyncio
    async def test_audit_context_log_passes_event_specific_args(self):
        """AuditContext.log() should pass event-specific arguments."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            ctx.log(
                event_type=AuditEventType.ORDER_PLACED,
                resource_type=ResourceType.ORDER,
                resource_id="order-789",
                severity=AuditSeverity.INFO,
                old_value={"status": "pending"},
                new_value={"status": "filled"},
                metadata={"extra": "data"},
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["event_type"] == AuditEventType.ORDER_PLACED
        assert call_kwargs["resource_type"] == ResourceType.ORDER
        assert call_kwargs["resource_id"] == "order-789"
        assert call_kwargs["severity"] == AuditSeverity.INFO
        assert call_kwargs["old_value"] == {"status": "pending"}
        assert call_kwargs["new_value"] == {"status": "filled"}
        assert call_kwargs["metadata"] == {"extra": "data"}

    @pytest.mark.asyncio
    async def test_audit_context_log_passes_optional_context_fields(self):
        """AuditContext.log() should pass optional context fields to service."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
            trace_id="trace-789",
            correlation_id="corr-012",
            client_ip="10.0.0.1",
            user_agent="TestAgent/1.0",
            actor_display="Test User",
            impersonator_id="admin-999",
        ) as ctx:
            ctx.log(
                event_type=AuditEventType.ORDER_PLACED,
                resource_type=ResourceType.ORDER,
                resource_id="order-789",
                severity=AuditSeverity.INFO,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["trace_id"] == "trace-789"
        assert call_kwargs["correlation_id"] == "corr-012"
        assert call_kwargs["client_ip"] == "10.0.0.1"
        assert call_kwargs["user_agent"] == "TestAgent/1.0"
        assert call_kwargs["actor_display"] == "Test User"
        assert call_kwargs["impersonator_id"] == "admin-999"

    @pytest.mark.asyncio
    async def test_audit_context_log_multiple_events(self):
        """AuditContext should support logging multiple events."""
        from src.audit.factory import AuditContext

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            ctx.log(
                event_type=AuditEventType.ORDER_PLACED,
                resource_type=ResourceType.ORDER,
                resource_id="order-1",
                severity=AuditSeverity.INFO,
            )
            ctx.log(
                event_type=AuditEventType.ORDER_FILLED,
                resource_type=ResourceType.ORDER,
                resource_id="order-1",
                severity=AuditSeverity.INFO,
            )

        assert mock_service.log.call_count == 2


class TestAuditOrderEvent:
    """Tests for audit_order_event() helper function."""

    @pytest.mark.asyncio
    async def test_audit_order_event_creates_order_event(self):
        """audit_order_event should create an order audit event."""
        from src.audit.factory import AuditContext, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-123"
        order.symbol = "AAPL"
        order.quantity = 100
        order.side = "buy"

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            result = audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_PLACED,
                old_status=None,
                new_status="pending",
                ctx=ctx,
            )

        assert isinstance(result, UUID)
        mock_service.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_order_event_uses_order_id_as_resource_id(self):
        """audit_order_event should use order.id as resource_id."""
        from src.audit.factory import AuditContext, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-456"
        order.symbol = "AAPL"
        order.quantity = 100
        order.side = "buy"

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_PLACED,
                old_status=None,
                new_status="pending",
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["resource_id"] == "order-456"

    @pytest.mark.asyncio
    async def test_audit_order_event_sets_resource_type_to_order(self):
        """audit_order_event should set resource_type to ORDER."""
        from src.audit.factory import AuditContext, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-456"

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_PLACED,
                old_status=None,
                new_status="pending",
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["resource_type"] == ResourceType.ORDER

    @pytest.mark.asyncio
    async def test_audit_order_event_includes_status_in_values(self):
        """audit_order_event should include old/new status in values."""
        from src.audit.factory import AuditContext, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-456"

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_FILLED,
                old_status="pending",
                new_status="filled",
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["old_value"]["status"] == "pending"
        assert call_kwargs["new_value"]["status"] == "filled"

    @pytest.mark.asyncio
    async def test_audit_order_event_default_severity_is_info(self):
        """audit_order_event should default severity to INFO."""
        from src.audit.factory import AuditContext, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-456"

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_PLACED,
                old_status=None,
                new_status="pending",
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["severity"] == AuditSeverity.INFO

    @pytest.mark.asyncio
    async def test_audit_order_event_accepts_custom_severity(self):
        """audit_order_event should accept custom severity."""
        from src.audit.factory import AuditContext, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-456"

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_REJECTED,
                old_status="pending",
                new_status="rejected",
                ctx=ctx,
                severity=AuditSeverity.WARNING,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["severity"] == AuditSeverity.WARNING


class TestAuditConfigChange:
    """Tests for audit_config_change() helper function."""

    @pytest.mark.asyncio
    async def test_audit_config_change_creates_config_event(self):
        """audit_config_change should create a config audit event."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            result = audit_config_change(
                config_key="trading.max_position_size",
                old_value={"value": 1000},
                new_value={"value": 2000},
                ctx=ctx,
            )

        assert isinstance(result, UUID)
        mock_service.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_config_change_uses_config_key_as_resource_id(self):
        """audit_config_change should use config_key as resource_id."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_config_change(
                config_key="trading.max_position_size",
                old_value={"value": 1000},
                new_value={"value": 2000},
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["resource_id"] == "trading.max_position_size"

    @pytest.mark.asyncio
    async def test_audit_config_change_sets_resource_type_to_config(self):
        """audit_config_change should set resource_type to CONFIG."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_config_change(
                config_key="trading.max_position_size",
                old_value={"value": 1000},
                new_value={"value": 2000},
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["resource_type"] == ResourceType.CONFIG

    @pytest.mark.asyncio
    async def test_audit_config_change_sets_event_type_to_config_updated(self):
        """audit_config_change should set event_type to CONFIG_UPDATED."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_config_change(
                config_key="trading.max_position_size",
                old_value={"value": 1000},
                new_value={"value": 2000},
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["event_type"] == AuditEventType.CONFIG_UPDATED

    @pytest.mark.asyncio
    async def test_audit_config_change_passes_old_and_new_values(self):
        """audit_config_change should pass old_value and new_value."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_config_change(
                config_key="trading.max_position_size",
                old_value={"value": 1000, "unit": "shares"},
                new_value={"value": 2000, "unit": "shares"},
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["old_value"] == {"value": 1000, "unit": "shares"}
        assert call_kwargs["new_value"] == {"value": 2000, "unit": "shares"}

    @pytest.mark.asyncio
    async def test_audit_config_change_default_severity_is_warning(self):
        """audit_config_change should default severity to WARNING (config changes are important)."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_config_change(
                config_key="trading.max_position_size",
                old_value={"value": 1000},
                new_value={"value": 2000},
                ctx=ctx,
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["severity"] == AuditSeverity.WARNING

    @pytest.mark.asyncio
    async def test_audit_config_change_accepts_custom_severity(self):
        """audit_config_change should accept custom severity."""
        from src.audit.factory import AuditContext, audit_config_change

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        async with AuditContext(
            request_id="req-123",
            actor_id="user-456",
            actor_type=ActorType.USER,
            source=EventSource.WEB,
            service=mock_service,
        ) as ctx:
            audit_config_change(
                config_key="ui.theme",
                old_value={"value": "light"},
                new_value={"value": "dark"},
                ctx=ctx,
                severity=AuditSeverity.INFO,  # Less critical config
            )

        call_kwargs = mock_service.log.call_args.kwargs
        assert call_kwargs["severity"] == AuditSeverity.INFO


class TestIntegration:
    """Integration tests for factory components."""

    @pytest.mark.asyncio
    async def test_full_audit_context_workflow(self):
        """Test full workflow with AuditContext and helper functions."""
        from src.audit.factory import AuditContext, audit_config_change, audit_order_event

        mock_service = MagicMock()
        mock_service.log.return_value = UUID("12345678-1234-5678-1234-567812345678")

        order = MagicMock()
        order.id = "order-123"

        async with AuditContext(
            request_id="req-abc",
            actor_id="user-xyz",
            actor_type=ActorType.USER,
            source=EventSource.API,
            service=mock_service,
            correlation_id="corr-001",
        ) as ctx:
            # Log an order event
            audit_order_event(
                order=order,
                event_type=AuditEventType.ORDER_PLACED,
                old_status=None,
                new_status="pending",
                ctx=ctx,
            )

            # Log a direct event
            ctx.log(
                event_type=AuditEventType.ALERT_EMITTED,
                resource_type=ResourceType.ALERT,
                resource_id="alert-999",
                severity=AuditSeverity.INFO,
            )

            # Log a config change
            audit_config_change(
                config_key="risk.limit",
                old_value={"value": 100000},
                new_value={"value": 150000},
                ctx=ctx,
            )

        # All three events should have been logged
        assert mock_service.log.call_count == 3

        # All events should share the same request context
        for call in mock_service.log.call_args_list:
            kwargs = call.kwargs
            assert kwargs["request_id"] == "req-abc"
            assert kwargs["actor_id"] == "user-xyz"
            assert kwargs["actor_type"] == ActorType.USER
            assert kwargs["source"] == EventSource.API
            assert kwargs["correlation_id"] == "corr-001"
