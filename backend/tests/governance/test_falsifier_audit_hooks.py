"""Tests for audit logging hooks in FalsifierChecker.

TDD: Tests for T064 - audit hooks integration with the falsifier checker.

These tests verify that the FalsifierChecker can optionally log audit events
when checking falsifiers, including:
- FALSIFIER_CHECK_PASS for passed checks
- FALSIFIER_CHECK_TRIGGERED for triggered checks
"""

from datetime import date

import pytest
from src.governance.models import (
    ComparisonOperator,
    GovernanceAuditEventType,
    HypothesisStatus,
    TriggerAction,
)


class TestFalsifierAuditHooksFixtures:
    """Shared fixtures for falsifier audit hook tests."""

    @pytest.fixture
    def audit_store(self):
        """Create a fresh InMemoryAuditStore."""
        from src.governance.audit.store import InMemoryAuditStore

        return InMemoryAuditStore()

    @pytest.fixture
    def hypothesis_with_falsifiers(self):
        """Create a hypothesis with falsifiers that can pass or trigger."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )

        return Hypothesis(
            id="momentum_persistence",
            title="Momentum Persistence",
            statement="Strong price momentum persists.",
            scope=HypothesisScope(symbols=[], sectors=["technology"]),
            owner="human",
            status=HypothesisStatus.ACTIVE,
            review_cycle="quarterly",
            created_at=date(2025, 1, 15),
            evidence=Evidence(sources=[], notes=""),
            falsifiers=[
                Falsifier(
                    metric="rolling_ic_mean",
                    operator=ComparisonOperator.LT,
                    threshold=0.0,
                    window="6m",
                    trigger=TriggerAction.SUNSET,
                ),
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def hypothesis_registry(self, hypothesis_with_falsifiers):
        """Create a HypothesisRegistry."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(hypothesis_with_falsifiers)
        return registry

    @pytest.fixture
    def metric_registry_pass(self):
        """Create a MetricRegistry where the metric does NOT trigger."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        # rolling_ic_mean = 0.05 (NOT < 0), so falsifier should pass
        registry.register("rolling_ic_mean", lambda window=None: 0.05)
        return registry

    @pytest.fixture
    def metric_registry_trigger(self):
        """Create a MetricRegistry where the metric DOES trigger."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        # rolling_ic_mean = -0.05 (< 0), so falsifier should trigger
        registry.register("rolling_ic_mean", lambda window=None: -0.05)
        return registry


class TestFalsifierCheckerAuditInit(TestFalsifierAuditHooksFixtures):
    """Tests for FalsifierChecker audit_store parameter."""

    def test_checker_accepts_optional_audit_store(self, hypothesis_registry, metric_registry_pass):
        """FalsifierChecker should accept an optional audit_store parameter."""
        from src.governance.audit.store import InMemoryAuditStore
        from src.governance.monitoring.falsifier import FalsifierChecker

        store = InMemoryAuditStore()
        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_pass,
            audit_store=store,
        )

        assert checker.audit_store is store

    def test_checker_audit_store_defaults_to_none(self, hypothesis_registry, metric_registry_pass):
        """FalsifierChecker audit_store should default to None."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_pass,
        )

        assert checker.audit_store is None


class TestFalsifierLogsPassedChecks(TestFalsifierAuditHooksFixtures):
    """Tests that falsifier logs FALSIFIER_CHECK_PASS events."""

    def test_check_hypothesis_logs_pass_when_not_triggered(
        self, hypothesis_registry, metric_registry_pass, audit_store
    ):
        """check_hypothesis() should log FALSIFIER_CHECK_PASS when check passes."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_pass,
            audit_store=audit_store,
        )

        checker.check_hypothesis("momentum_persistence")

        entries = audit_store.query(event_type=GovernanceAuditEventType.FALSIFIER_CHECK_PASS)
        assert len(entries) == 1
        assert entries[0].hypothesis_id == "momentum_persistence"
        assert entries[0].action_details["metric"] == "rolling_ic_mean"
        assert entries[0].action_details["triggered"] is False


class TestFalsifierLogsTriggeredChecks(TestFalsifierAuditHooksFixtures):
    """Tests that falsifier logs FALSIFIER_CHECK_TRIGGERED events."""

    def test_check_hypothesis_logs_triggered_when_triggered(
        self, hypothesis_registry, metric_registry_trigger, audit_store
    ):
        """check_hypothesis() should log FALSIFIER_CHECK_TRIGGERED when check triggers."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_trigger,
            audit_store=audit_store,
        )

        checker.check_hypothesis("momentum_persistence")

        entries = audit_store.query(event_type=GovernanceAuditEventType.FALSIFIER_CHECK_TRIGGERED)
        assert len(entries) == 1
        assert entries[0].hypothesis_id == "momentum_persistence"
        assert entries[0].action_details["metric"] == "rolling_ic_mean"
        assert entries[0].action_details["triggered"] is True
        assert entries[0].action_details["metric_value"] == -0.05


class TestFalsifierNoAuditWhenStoreIsNone(TestFalsifierAuditHooksFixtures):
    """Tests that falsifier works without audit store."""

    def test_check_hypothesis_works_without_audit_store(
        self, hypothesis_registry, metric_registry_pass
    ):
        """check_hypothesis() should work normally when audit_store is None."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_pass,
            # No audit_store
        )

        results = checker.check_hypothesis("momentum_persistence")
        assert len(results) == 1
        assert results[0].triggered is False

    def test_check_all_works_without_audit_store(self, hypothesis_registry, metric_registry_pass):
        """check_all() should work normally when audit_store is None."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_pass,
        )

        results = checker.check_all()
        assert len(results) == 1


class TestFalsifierCheckAllWithAudit(TestFalsifierAuditHooksFixtures):
    """Tests that check_all() also logs audit events."""

    def test_check_all_logs_audit_events(
        self, hypothesis_registry, metric_registry_pass, audit_store
    ):
        """check_all() should log audit events for each falsifier check."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_pass,
            audit_store=audit_store,
        )

        checker.check_all()

        # Should have logged at least one pass event
        entries = audit_store.query(event_type=GovernanceAuditEventType.FALSIFIER_CHECK_PASS)
        assert len(entries) >= 1
