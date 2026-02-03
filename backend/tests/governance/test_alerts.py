"""Tests for alert generation and delivery.

TDD: Write tests FIRST, then implement to make them pass.

This module tests:
1. Alert model (T053)
2. AlertGenerator for creating alerts from falsifier checks (T056)
3. Alert delivery via handlers (FR-027)

Spec Requirements:
- FR-026: Review alerts with hypothesis_id, triggered_falsifier, metric_value,
          threshold, recommended_action (review/sunset)
- FR-027: Notification delivery (configurable: log file, email, webhook)
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# =============================================================================
# T053: Alert Model Tests
# =============================================================================


class TestAlertModel:
    """Tests for Alert Pydantic model."""

    def test_alert_creation(self):
        """Alert should be creatable with all required fields."""
        from src.governance.models import AlertSeverity
        from src.governance.monitoring.models import Alert

        alert = Alert(
            id="alert-001",
            severity=AlertSeverity.CRITICAL,
            source="falsifier_checker",
            hypothesis_id="momentum_persistence",
            title="Falsifier Triggered",
            message="rolling_ic_mean dropped below 0",
            details={"metric_value": -0.03, "threshold": 0.0},
            created_at=datetime.now(timezone.utc),
        )

        assert alert.id == "alert-001"
        assert alert.severity == AlertSeverity.CRITICAL
        assert alert.source == "falsifier_checker"
        assert alert.hypothesis_id == "momentum_persistence"
        assert alert.delivered is False
        assert alert.delivery_channel is None

    def test_alert_optional_fields_default(self):
        """Alert optional fields should have correct defaults."""
        from src.governance.models import AlertSeverity
        from src.governance.monitoring.models import Alert

        alert = Alert(
            id="alert-002",
            severity=AlertSeverity.WARNING,
            source="falsifier_checker",
            title="Test Alert",
            message="Test message",
            created_at=datetime.now(timezone.utc),
        )

        assert alert.hypothesis_id is None
        assert alert.constraint_id is None
        assert alert.details == {}
        assert alert.delivered is False
        assert alert.delivery_channel is None

    def test_alert_with_constraint_id(self):
        """Alert should support constraint_id for constraint-related alerts."""
        from src.governance.models import AlertSeverity
        from src.governance.monitoring.models import Alert

        alert = Alert(
            id="alert-003",
            severity=AlertSeverity.INFO,
            source="constraint_resolver",
            constraint_id="growth_leverage_guard",
            title="Constraint Deactivated",
            message="Constraint deactivated due to falsified hypothesis",
            created_at=datetime.now(timezone.utc),
        )

        assert alert.constraint_id == "growth_leverage_guard"

    def test_alert_forbids_extra_fields(self):
        """Alert should reject extra fields (GovernanceBaseModel)."""
        from pydantic import ValidationError
        from src.governance.models import AlertSeverity
        from src.governance.monitoring.models import Alert

        with pytest.raises(ValidationError):
            Alert(
                id="alert-bad",
                severity=AlertSeverity.WARNING,
                source="test",
                title="Test",
                message="Test",
                created_at=datetime.now(timezone.utc),
                extra_field="should_fail",
            )

    def test_alert_serialization(self):
        """Alert should serialize to dict/JSON correctly."""
        from src.governance.models import AlertSeverity
        from src.governance.monitoring.models import Alert

        now = datetime.now(timezone.utc)
        alert = Alert(
            id="alert-004",
            severity=AlertSeverity.CRITICAL,
            source="falsifier_checker",
            hypothesis_id="test_hyp",
            title="Test",
            message="Test message",
            details={"key": "value"},
            created_at=now,
            delivered=True,
            delivery_channel="log",
        )

        data = alert.model_dump()
        assert data["id"] == "alert-004"
        assert data["severity"] == "critical"
        assert data["delivered"] is True
        assert data["delivery_channel"] == "log"
        assert data["details"] == {"key": "value"}

    def test_alert_severity_values(self):
        """AlertSeverity enum should have expected values."""
        from src.governance.models import AlertSeverity

        assert AlertSeverity.INFO == "info"
        assert AlertSeverity.WARNING == "warning"
        assert AlertSeverity.CRITICAL == "critical"


# =============================================================================
# T056: AlertGenerator Tests
# =============================================================================


class TestAlertGeneratorFixtures:
    """Shared fixtures for AlertGenerator tests."""

    @pytest.fixture
    def triggered_check_result(self):
        """Create a triggered FalsifierCheckResult."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        return FalsifierCheckResult(
            hypothesis_id="momentum_persistence",
            falsifier_index=0,
            metric="rolling_ic_mean",
            operator=ComparisonOperator.LT,
            threshold=0.0,
            window="6m",
            metric_value=-0.03,
            triggered=True,
            trigger_action=TriggerAction.SUNSET,
            checked_at=datetime.now(timezone.utc),
            message="TRIGGERED: rolling_ic_mean=-0.03 < 0.0",
        )

    @pytest.fixture
    def passed_check_result(self):
        """Create a passed (not triggered) FalsifierCheckResult."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        return FalsifierCheckResult(
            hypothesis_id="momentum_persistence",
            falsifier_index=0,
            metric="rolling_ic_mean",
            operator=ComparisonOperator.LT,
            threshold=0.0,
            window="6m",
            metric_value=0.05,
            triggered=False,
            trigger_action=TriggerAction.SUNSET,
            checked_at=datetime.now(timezone.utc),
            message="Passed: rolling_ic_mean=0.05, threshold <0.0",
        )

    @pytest.fixture
    def review_check_result(self):
        """Create a triggered FalsifierCheckResult with review action."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        return FalsifierCheckResult(
            hypothesis_id="quality_factor",
            falsifier_index=0,
            metric="win_rate",
            operator=ComparisonOperator.LT,
            threshold=0.45,
            window="90d",
            metric_value=0.40,
            triggered=True,
            trigger_action=TriggerAction.REVIEW,
            checked_at=datetime.now(timezone.utc),
            message="TRIGGERED: win_rate=0.40 < 0.45",
        )


class TestAlertGeneratorGenerateFromCheck(TestAlertGeneratorFixtures):
    """Tests for AlertGenerator.generate_from_check method."""

    def test_generate_alert_from_triggered_check(self, triggered_check_result):
        """generate_from_check should create alert for triggered falsifier."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        alert = generator.generate_from_check(triggered_check_result)

        assert alert is not None
        assert alert.hypothesis_id == "momentum_persistence"
        assert alert.source == "falsifier_checker"
        assert alert.severity.value == "critical"  # sunset action = critical
        assert "rolling_ic_mean" in alert.message or "rolling_ic_mean" in alert.title
        assert alert.id is not None and len(alert.id) > 0

    def test_generate_no_alert_from_passed_check(self, passed_check_result):
        """generate_from_check should return None for non-triggered falsifier."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        alert = generator.generate_from_check(passed_check_result)

        assert alert is None

    def test_generate_alert_includes_fr026_details(self, triggered_check_result):
        """Alert should include FR-026 required fields in details."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        alert = generator.generate_from_check(triggered_check_result)

        assert alert is not None
        # FR-026: hypothesis_id, triggered_falsifier, metric_value, threshold, recommended_action
        assert alert.hypothesis_id == "momentum_persistence"
        assert "metric_value" in alert.details or alert.details.get("metric_value") is not None
        assert "threshold" in alert.details
        assert "recommended_action" in alert.details

    def test_generate_alert_review_severity(self, review_check_result):
        """generate_from_check should set WARNING severity for review action."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        alert = generator.generate_from_check(review_check_result)

        assert alert is not None
        assert alert.severity.value == "warning"  # review action = warning

    def test_generate_alert_sunset_severity(self, triggered_check_result):
        """generate_from_check should set CRITICAL severity for sunset action."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        alert = generator.generate_from_check(triggered_check_result)

        assert alert is not None
        assert alert.severity.value == "critical"

    def test_generate_alert_stores_in_list(self, triggered_check_result):
        """generate_from_check should store the generated alert internally."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        alert = generator.generate_from_check(triggered_check_result)

        alerts = generator.get_alerts()
        assert len(alerts) == 1
        assert alerts[0].id == alert.id


class TestAlertGeneratorHandlers(TestAlertGeneratorFixtures):
    """Tests for AlertGenerator handler/delivery system."""

    def test_add_handler(self):
        """add_handler should register a delivery handler."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        handler = MagicMock()

        generator.add_handler(handler)

        # No error means success

    def test_deliver_calls_all_handlers(self, triggered_check_result):
        """deliver should call all registered handlers with the alert."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        handler1 = MagicMock()
        handler2 = MagicMock()

        generator.add_handler(handler1)
        generator.add_handler(handler2)

        alert = generator.generate_from_check(triggered_check_result)

        handler1.assert_called_once_with(alert)
        handler2.assert_called_once_with(alert)

    def test_deliver_marks_alert_as_delivered(self, triggered_check_result):
        """deliver should mark the alert as delivered."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        handler = MagicMock()
        generator.add_handler(handler)

        alert = generator.generate_from_check(triggered_check_result)

        assert alert.delivered is True

    def test_no_handlers_no_delivery(self, triggered_check_result):
        """Alert should not be marked delivered when no handlers are registered."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        # No handlers registered

        alert = generator.generate_from_check(triggered_check_result)

        assert alert.delivered is False

    def test_handler_exception_does_not_prevent_other_handlers(self, triggered_check_result):
        """If one handler raises, other handlers should still be called."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()

        def bad_handler(alert):
            raise RuntimeError("Handler failed")

        good_handler = MagicMock()

        generator.add_handler(bad_handler)
        generator.add_handler(good_handler)

        alert = generator.generate_from_check(triggered_check_result)

        # Good handler should still have been called
        good_handler.assert_called_once_with(alert)


class TestAlertGeneratorGetAlerts(TestAlertGeneratorFixtures):
    """Tests for AlertGenerator.get_alerts method."""

    def test_get_alerts_empty(self):
        """get_alerts should return empty list initially."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        assert generator.get_alerts() == []

    def test_get_alerts_multiple(self, triggered_check_result, review_check_result):
        """get_alerts should return all generated alerts."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        generator.generate_from_check(triggered_check_result)
        generator.generate_from_check(review_check_result)

        alerts = generator.get_alerts()
        assert len(alerts) == 2

    def test_get_alerts_does_not_include_non_triggered(
        self, triggered_check_result, passed_check_result
    ):
        """get_alerts should not include alerts from non-triggered checks (they return None)."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        generator.generate_from_check(triggered_check_result)
        generator.generate_from_check(passed_check_result)  # Returns None

        alerts = generator.get_alerts()
        assert len(alerts) == 1


# =============================================================================
# FR-027: Notification Delivery Tests
# =============================================================================


class TestAlertDeliveryChannels(TestAlertGeneratorFixtures):
    """Tests for alert delivery via different channels (FR-027)."""

    def test_log_handler_delivery(self, triggered_check_result):
        """Log handler should be callable and receive alerts."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        logged_messages = []

        def log_handler(alert):
            logged_messages.append(
                f"[{alert.severity.value.upper()}] {alert.title}: {alert.message}"
            )

        generator.add_handler(log_handler)
        generator.generate_from_check(triggered_check_result)

        assert len(logged_messages) == 1
        assert "CRITICAL" in logged_messages[0]

    def test_webhook_handler_delivery(self, triggered_check_result):
        """Webhook handler should receive alert data for posting."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        webhook_payloads = []

        def webhook_handler(alert):
            webhook_payloads.append(alert.model_dump())

        generator.add_handler(webhook_handler)
        generator.generate_from_check(triggered_check_result)

        assert len(webhook_payloads) == 1
        assert webhook_payloads[0]["hypothesis_id"] == "momentum_persistence"

    def test_multiple_delivery_channels(self, triggered_check_result):
        """Multiple delivery channels should all receive alerts."""
        from src.governance.monitoring.alerts import AlertGenerator

        generator = AlertGenerator()
        log_output = []
        webhook_output = []
        email_output = []

        generator.add_handler(lambda a: log_output.append(a))
        generator.add_handler(lambda a: webhook_output.append(a))
        generator.add_handler(lambda a: email_output.append(a))

        generator.generate_from_check(triggered_check_result)

        assert len(log_output) == 1
        assert len(webhook_output) == 1
        assert len(email_output) == 1


# =============================================================================
# Import/Export Tests
# =============================================================================


class TestAlertImports:
    """Tests for alert module imports."""

    def test_alert_importable(self):
        """Alert should be importable from monitoring.models."""
        from src.governance.monitoring.models import Alert

        assert Alert is not None

    def test_alert_generator_importable(self):
        """AlertGenerator should be importable from monitoring.alerts."""
        from src.governance.monitoring.alerts import AlertGenerator

        assert AlertGenerator is not None
