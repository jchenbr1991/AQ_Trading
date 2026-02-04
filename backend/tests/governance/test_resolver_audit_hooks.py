"""Tests for audit logging hooks in ConstraintResolver.

TDD: Tests for T063 - audit hooks integration with the constraint resolver.

These tests verify that the ConstraintResolver can optionally log audit events
when resolving constraints, including:
- CONSTRAINT_ACTIVATED for each active constraint
- VETO_DOWNGRADE when veto_downgrade_active is True
- RISK_BUDGET_ADJUSTED when risk_budget_multiplier != 1.0
"""

from datetime import date

import pytest
from src.governance.models import (
    ComparisonOperator,
    GovernanceAuditEventType,
    HypothesisStatus,
    TriggerAction,
)


class TestResolverAuditHooksFixtures:
    """Shared fixtures for resolver audit hook tests."""

    @pytest.fixture
    def audit_store(self):
        """Create a fresh InMemoryAuditStore."""
        from src.governance.audit.store import InMemoryAuditStore

        return InMemoryAuditStore()

    @pytest.fixture
    def active_hypothesis(self):
        """Create a sample ACTIVE hypothesis."""
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
                    window="4q",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def hypothesis_registry(self, active_hypothesis):
        """Create a HypothesisRegistry with sample hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(active_hypothesis)
        return registry

    @pytest.fixture
    def constraint_with_risk_budget(self):
        """Create a constraint with risk_budget_multiplier != 1.0."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="risk_budget_constraint",
            title="Risk Budget Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=2.0),
            priority=50,
        )

    @pytest.fixture
    def constraint_with_veto(self):
        """Create a constraint with veto_downgrade=True."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="veto_constraint",
            title="Veto Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(veto_downgrade=True),
            priority=60,
        )

    @pytest.fixture
    def simple_constraint(self):
        """Create a simple constraint (no risk adjustment, no veto)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="simple_constraint",
            title="Simple Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(pool_bias_multiplier=1.2),
            priority=100,
        )


class TestResolverAuditHookInit(TestResolverAuditHooksFixtures):
    """Tests for ConstraintResolver audit_store parameter."""

    def test_resolver_accepts_optional_audit_store(self, hypothesis_registry):
        """ConstraintResolver should accept an optional audit_store parameter."""
        from src.governance.audit.store import InMemoryAuditStore
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        store = InMemoryAuditStore()
        resolver = ConstraintResolver(
            constraint_registry=ConstraintRegistry(),
            hypothesis_registry=hypothesis_registry,
            audit_store=store,
        )

        assert resolver.audit_store is store

    def test_resolver_audit_store_defaults_to_none(self, hypothesis_registry):
        """ConstraintResolver audit_store should default to None."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        resolver = ConstraintResolver(
            constraint_registry=ConstraintRegistry(),
            hypothesis_registry=hypothesis_registry,
        )

        assert resolver.audit_store is None


class TestResolverLogsConstraintActivated(TestResolverAuditHooksFixtures):
    """Tests that resolver logs CONSTRAINT_ACTIVATED events."""

    def test_resolve_logs_constraint_activated_for_each_active(
        self, hypothesis_registry, simple_constraint, audit_store
    ):
        """resolve() should log CONSTRAINT_ACTIVATED for each active constraint."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(simple_constraint)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            audit_store=audit_store,
        )

        resolver.resolve("AAPL")

        entries = audit_store.query(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        assert len(entries) == 1
        assert entries[0].constraint_id == "simple_constraint"
        assert entries[0].symbol == "AAPL"

    def test_resolve_logs_multiple_constraints_activated(
        self, hypothesis_registry, simple_constraint, constraint_with_risk_budget, audit_store
    ):
        """resolve() should log one CONSTRAINT_ACTIVATED per active constraint."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(simple_constraint)
        registry.register(constraint_with_risk_budget)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            audit_store=audit_store,
        )

        resolver.resolve("AAPL")

        entries = audit_store.query(event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED)
        assert len(entries) == 2


class TestResolverLogsVetoDowngrade(TestResolverAuditHooksFixtures):
    """Tests that resolver logs VETO_DOWNGRADE events."""

    def test_resolve_logs_veto_downgrade_when_active(
        self, hypothesis_registry, constraint_with_veto, audit_store
    ):
        """resolve() should log VETO_DOWNGRADE when veto_downgrade_active is True."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(constraint_with_veto)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            audit_store=audit_store,
        )

        resolver.resolve("AAPL")

        entries = audit_store.query(event_type=GovernanceAuditEventType.VETO_DOWNGRADE)
        assert len(entries) == 1
        assert entries[0].symbol == "AAPL"

    def test_resolve_no_veto_downgrade_log_when_not_active(
        self, hypothesis_registry, simple_constraint, audit_store
    ):
        """resolve() should NOT log VETO_DOWNGRADE when veto_downgrade_active is False."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(simple_constraint)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            audit_store=audit_store,
        )

        resolver.resolve("AAPL")

        entries = audit_store.query(event_type=GovernanceAuditEventType.VETO_DOWNGRADE)
        assert len(entries) == 0


class TestResolverLogsRiskBudgetAdjusted(TestResolverAuditHooksFixtures):
    """Tests that resolver logs RISK_BUDGET_ADJUSTED events."""

    def test_resolve_logs_risk_budget_adjusted_when_not_1(
        self, hypothesis_registry, constraint_with_risk_budget, audit_store
    ):
        """resolve() should log RISK_BUDGET_ADJUSTED when multiplier != 1.0."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(constraint_with_risk_budget)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            audit_store=audit_store,
        )

        resolver.resolve("AAPL")

        entries = audit_store.query(event_type=GovernanceAuditEventType.RISK_BUDGET_ADJUSTED)
        assert len(entries) == 1
        assert entries[0].symbol == "AAPL"
        assert entries[0].action_details["effective_multiplier"] == 2.0

    def test_resolve_no_risk_budget_log_when_multiplier_is_1(
        self, hypothesis_registry, simple_constraint, audit_store
    ):
        """resolve() should NOT log RISK_BUDGET_ADJUSTED when multiplier is 1.0."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(simple_constraint)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            audit_store=audit_store,
        )

        resolver.resolve("AAPL")

        entries = audit_store.query(event_type=GovernanceAuditEventType.RISK_BUDGET_ADJUSTED)
        assert len(entries) == 0


class TestResolverNoAuditWhenStoreIsNone(TestResolverAuditHooksFixtures):
    """Tests that resolver works without audit store."""

    def test_resolve_works_without_audit_store(
        self, hypothesis_registry, constraint_with_risk_budget
    ):
        """resolve() should work normally when audit_store is None."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        registry = ConstraintRegistry()
        registry.register(constraint_with_risk_budget)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
            # No audit_store
        )

        result = resolver.resolve("AAPL")
        assert result.symbol == "AAPL"
        assert result.effective_risk_budget_multiplier == 2.0
