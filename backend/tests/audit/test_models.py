"""Tests for audit models and enums.

TDD: Write tests FIRST, then implement models to make them pass.
"""

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from uuid import UUID, uuid4

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


class TestAuditEventType:
    """Tests for AuditEventType enum."""

    # Order events
    def test_order_placed_value(self):
        assert AuditEventType.ORDER_PLACED.value == "order_placed"

    def test_order_acknowledged_value(self):
        assert AuditEventType.ORDER_ACKNOWLEDGED.value == "order_acknowledged"

    def test_order_filled_value(self):
        assert AuditEventType.ORDER_FILLED.value == "order_filled"

    def test_order_cancelled_value(self):
        assert AuditEventType.ORDER_CANCELLED.value == "order_cancelled"

    def test_order_rejected_value(self):
        assert AuditEventType.ORDER_REJECTED.value == "order_rejected"

    # Config events
    def test_config_created_value(self):
        assert AuditEventType.CONFIG_CREATED.value == "config_created"

    def test_config_updated_value(self):
        assert AuditEventType.CONFIG_UPDATED.value == "config_updated"

    def test_config_deleted_value(self):
        assert AuditEventType.CONFIG_DELETED.value == "config_deleted"

    # Alert events
    def test_alert_emitted_value(self):
        assert AuditEventType.ALERT_EMITTED.value == "alert_emitted"

    def test_alert_acknowledged_value(self):
        assert AuditEventType.ALERT_ACKNOWLEDGED.value == "alert_acknowledged"

    def test_alert_resolved_value(self):
        assert AuditEventType.ALERT_RESOLVED.value == "alert_resolved"

    # System events
    def test_system_started_value(self):
        assert AuditEventType.SYSTEM_STARTED.value == "system_started"

    def test_system_stopped_value(self):
        assert AuditEventType.SYSTEM_STOPPED.value == "system_stopped"

    def test_health_changed_value(self):
        assert AuditEventType.HEALTH_CHANGED.value == "health_changed"

    # Security events
    def test_auth_login_value(self):
        assert AuditEventType.AUTH_LOGIN.value == "auth_login"

    def test_auth_logout_value(self):
        assert AuditEventType.AUTH_LOGOUT.value == "auth_logout"

    def test_auth_failed_value(self):
        assert AuditEventType.AUTH_FAILED.value == "auth_failed"

    def test_permission_changed_value(self):
        assert AuditEventType.PERMISSION_CHANGED.value == "permission_changed"

    def test_is_string_enum(self):
        """AuditEventType should be a string enum for JSON serialization."""
        assert isinstance(AuditEventType.ORDER_PLACED, str)
        assert AuditEventType.ORDER_PLACED == "order_placed"


class TestActorType:
    """Tests for ActorType enum."""

    def test_user_value(self):
        assert ActorType.USER.value == "user"

    def test_system_value(self):
        assert ActorType.SYSTEM.value == "system"

    def test_api_value(self):
        assert ActorType.API.value == "api"

    def test_scheduler_value(self):
        assert ActorType.SCHEDULER.value == "scheduler"

    def test_is_string_enum(self):
        """ActorType should be a string enum for JSON serialization."""
        assert isinstance(ActorType.USER, str)
        assert ActorType.USER == "user"


class TestAuditSeverity:
    """Tests for AuditSeverity enum."""

    def test_info_value(self):
        assert AuditSeverity.INFO.value == "info"

    def test_warning_value(self):
        assert AuditSeverity.WARNING.value == "warning"

    def test_critical_value(self):
        assert AuditSeverity.CRITICAL.value == "critical"

    def test_is_string_enum(self):
        """AuditSeverity should be a string enum for JSON serialization."""
        assert isinstance(AuditSeverity.INFO, str)
        assert AuditSeverity.INFO == "info"


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_order_value(self):
        assert ResourceType.ORDER.value == "order"

    def test_position_value(self):
        assert ResourceType.POSITION.value == "position"

    def test_config_value(self):
        assert ResourceType.CONFIG.value == "config"

    def test_alert_value(self):
        assert ResourceType.ALERT.value == "alert"

    def test_strategy_value(self):
        assert ResourceType.STRATEGY.value == "strategy"

    def test_account_value(self):
        assert ResourceType.ACCOUNT.value == "account"

    def test_permission_value(self):
        assert ResourceType.PERMISSION.value == "permission"

    def test_session_value(self):
        assert ResourceType.SESSION.value == "session"

    def test_is_string_enum(self):
        """ResourceType should be a string enum for JSON serialization."""
        assert isinstance(ResourceType.ORDER, str)
        assert ResourceType.ORDER == "order"


class TestEventSource:
    """Tests for EventSource enum."""

    def test_web_value(self):
        assert EventSource.WEB.value == "web"

    def test_api_value(self):
        assert EventSource.API.value == "api"

    def test_worker_value(self):
        assert EventSource.WORKER.value == "worker"

    def test_scheduler_value(self):
        assert EventSource.SCHEDULER.value == "scheduler"

    def test_system_value(self):
        assert EventSource.SYSTEM.value == "system"

    def test_cli_value(self):
        assert EventSource.CLI.value == "cli"

    def test_is_string_enum(self):
        """EventSource should be a string enum for JSON serialization."""
        assert isinstance(EventSource.WEB, str)
        assert EventSource.WEB == "web"


class TestValueMode:
    """Tests for ValueMode enum."""

    def test_diff_value(self):
        assert ValueMode.DIFF.value == "diff"

    def test_snapshot_value(self):
        assert ValueMode.SNAPSHOT.value == "snapshot"

    def test_reference_value(self):
        assert ValueMode.REFERENCE.value == "reference"

    def test_is_string_enum(self):
        """ValueMode should be a string enum for JSON serialization."""
        assert isinstance(ValueMode.DIFF, str)
        assert ValueMode.DIFF == "diff"


class TestAuditEvent:
    """Tests for AuditEvent dataclass."""

    def test_create_audit_event_with_required_fields(self):
        """AuditEvent should be creatable with all required fields."""
        event_id = uuid4()
        timestamp = datetime.now(tz=timezone.utc)

        event = AuditEvent(
            event_id=event_id,
            timestamp=timestamp,
            event_type=AuditEventType.ORDER_PLACED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert event.event_id == event_id
        assert event.timestamp == timestamp
        assert event.event_type == AuditEventType.ORDER_PLACED
        assert event.severity == AuditSeverity.INFO
        assert event.actor_id == "user-123"
        assert event.actor_type == ActorType.USER
        assert event.resource_type == ResourceType.ORDER
        assert event.resource_id == "order-456"
        assert event.request_id == "req-789"
        assert event.source == EventSource.WEB
        assert event.environment == "production"
        assert event.service == "trading-api"
        assert event.version == "1.0.0"

    def test_audit_event_optional_fields_defaults(self):
        """AuditEvent optional fields should have correct defaults."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ORDER_FILLED,
            severity=AuditSeverity.INFO,
            actor_id="system",
            actor_type=ActorType.SYSTEM,
            resource_type=ResourceType.ORDER,
            resource_id="order-123",
            request_id="req-456",
            source=EventSource.SYSTEM,
            environment="dev",
            service="order-service",
            version="1.0.0",
        )

        # Optional fields with default None
        assert event.actor_display is None
        assert event.impersonator_id is None
        assert event.old_value is None
        assert event.new_value is None
        assert event.value_hash is None
        assert event.trace_id is None
        assert event.correlation_id is None
        assert event.client_ip is None
        assert event.user_agent is None
        assert event.metadata is None

        # Optional fields with default values
        assert event.value_mode == ValueMode.DIFF
        assert event.schema_version == 1

    def test_audit_event_with_all_optional_fields(self):
        """AuditEvent should accept all optional fields."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.CONFIG_UPDATED,
            severity=AuditSeverity.WARNING,
            actor_id="user-123",
            actor_type=ActorType.USER,
            actor_display="John Doe",
            impersonator_id="admin-456",
            resource_type=ResourceType.CONFIG,
            resource_id="config-789",
            value_mode=ValueMode.SNAPSHOT,
            old_value={"key": "old_value"},
            new_value={"key": "new_value"},
            value_hash="abc123def456",
            request_id="req-111",
            trace_id="trace-222",
            correlation_id="corr-333",
            source=EventSource.API,
            client_ip="192.168.1.1",
            user_agent="Mozilla/5.0",
            environment="staging",
            service="config-service",
            version="2.0.0",
            schema_version=2,
            metadata={"extra": "data"},
        )

        assert event.actor_display == "John Doe"
        assert event.impersonator_id == "admin-456"
        assert event.value_mode == ValueMode.SNAPSHOT
        assert event.old_value == {"key": "old_value"}
        assert event.new_value == {"key": "new_value"}
        assert event.value_hash == "abc123def456"
        assert event.trace_id == "trace-222"
        assert event.correlation_id == "corr-333"
        assert event.client_ip == "192.168.1.1"
        assert event.user_agent == "Mozilla/5.0"
        assert event.schema_version == 2
        assert event.metadata == {"extra": "data"}

    def test_audit_event_is_frozen(self):
        """AuditEvent should be immutable (frozen dataclass)."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ORDER_PLACED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        with pytest.raises(FrozenInstanceError):
            event.actor_id = "user-999"

    def test_audit_event_event_id_is_uuid(self):
        """event_id should be a UUID type."""
        event_id = uuid4()
        event = AuditEvent(
            event_id=event_id,
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ORDER_PLACED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert isinstance(event.event_id, UUID)

    def test_audit_event_timestamp_is_datetime(self):
        """timestamp should be a datetime type."""
        timestamp = datetime.now(tz=timezone.utc)
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=timestamp,
            event_type=AuditEventType.ORDER_PLACED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            request_id="req-789",
            source=EventSource.WEB,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert isinstance(event.timestamp, datetime)

    def test_audit_event_security_event(self):
        """AuditEvent should support security event types."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.AUTH_LOGIN,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.SESSION,
            resource_id="session-456",
            request_id="req-789",
            source=EventSource.WEB,
            client_ip="10.0.0.1",
            user_agent="Chrome/120.0",
            environment="production",
            service="auth-service",
            version="1.0.0",
        )

        assert event.event_type == AuditEventType.AUTH_LOGIN
        assert event.resource_type == ResourceType.SESSION
        assert event.client_ip == "10.0.0.1"

    def test_audit_event_system_event(self):
        """AuditEvent should support system event types."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.SYSTEM_STARTED,
            severity=AuditSeverity.INFO,
            actor_id="system",
            actor_type=ActorType.SYSTEM,
            resource_type=ResourceType.STRATEGY,
            resource_id="momentum-strategy",
            request_id="startup-001",
            source=EventSource.SYSTEM,
            environment="production",
            service="trading-engine",
            version="1.0.0",
        )

        assert event.event_type == AuditEventType.SYSTEM_STARTED
        assert event.actor_type == ActorType.SYSTEM
        assert event.source == EventSource.SYSTEM

    def test_audit_event_critical_severity(self):
        """AuditEvent should support CRITICAL severity."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.AUTH_FAILED,
            severity=AuditSeverity.CRITICAL,
            actor_id="unknown",
            actor_type=ActorType.USER,
            resource_type=ResourceType.SESSION,
            resource_id="session-attempt-123",
            request_id="req-789",
            source=EventSource.WEB,
            client_ip="192.168.1.100",
            environment="production",
            service="auth-service",
            version="1.0.0",
            metadata={"failed_attempts": 5},
        )

        assert event.severity == AuditSeverity.CRITICAL
        assert event.metadata == {"failed_attempts": 5}

    def test_audit_event_scheduler_actor(self):
        """AuditEvent should support SCHEDULER actor type."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.HEALTH_CHANGED,
            severity=AuditSeverity.WARNING,
            actor_id="health-check-job",
            actor_type=ActorType.SCHEDULER,
            resource_type=ResourceType.STRATEGY,
            resource_id="momentum-strategy",
            request_id="scheduled-health-001",
            source=EventSource.SCHEDULER,
            environment="production",
            service="health-monitor",
            version="1.0.0",
        )

        assert event.actor_type == ActorType.SCHEDULER
        assert event.source == EventSource.SCHEDULER

    def test_audit_event_reference_mode(self):
        """AuditEvent should support REFERENCE value mode."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ORDER_PLACED,
            severity=AuditSeverity.INFO,
            actor_id="user-123",
            actor_type=ActorType.USER,
            resource_type=ResourceType.ORDER,
            resource_id="order-456",
            value_mode=ValueMode.REFERENCE,
            new_value={"order_ref": "external-order-789"},
            request_id="req-001",
            source=EventSource.API,
            environment="production",
            service="trading-api",
            version="1.0.0",
        )

        assert event.value_mode == ValueMode.REFERENCE

    def test_audit_event_cli_source(self):
        """AuditEvent should support CLI event source."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.CONFIG_UPDATED,
            severity=AuditSeverity.INFO,
            actor_id="admin-user",
            actor_type=ActorType.USER,
            resource_type=ResourceType.CONFIG,
            resource_id="risk-limits",
            request_id="cli-001",
            source=EventSource.CLI,
            environment="production",
            service="admin-cli",
            version="1.0.0",
        )

        assert event.source == EventSource.CLI

    def test_audit_event_worker_source(self):
        """AuditEvent should support WORKER event source."""
        event = AuditEvent(
            event_id=uuid4(),
            timestamp=datetime.now(tz=timezone.utc),
            event_type=AuditEventType.ORDER_FILLED,
            severity=AuditSeverity.INFO,
            actor_id="fill-processor",
            actor_type=ActorType.SYSTEM,
            resource_type=ResourceType.ORDER,
            resource_id="order-789",
            request_id="worker-001",
            source=EventSource.WORKER,
            environment="production",
            service="fill-worker",
            version="1.0.0",
        )

        assert event.source == EventSource.WORKER
