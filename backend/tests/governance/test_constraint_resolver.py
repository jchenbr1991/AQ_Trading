"""Tests for constraint resolver.

TDD: Write tests FIRST, then implement resolver to make them pass.

This module tests the ConstraintResolver class which:
1. Takes a symbol and returns all applicable constraints for that symbol
2. Checks activation conditions (requires_hypotheses_active, disabled_if_falsified)
3. Produces a ResolvedConstraints object with merged action values
4. Has Redis caching support
"""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest


class TestConstraintResolverFixtures:
    """Pytest fixtures for ConstraintResolver tests."""

    @pytest.fixture
    def sample_hypothesis_active(self):
        """Create a sample ACTIVE hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="momentum_persistence",
            title="Momentum Persistence Hypothesis",
            statement="Strong price momentum tends to persist over 3-6 month horizons.",
            scope=HypothesisScope(symbols=[], sectors=["technology"]),
            owner="human",
            status=HypothesisStatus.ACTIVE,
            review_cycle="quarterly",
            created_at=date(2025, 1, 15),
            evidence=Evidence(sources=["https://example.com/paper"], notes="Research paper."),
            falsifiers=[
                Falsifier(
                    metric="rolling_ic_mean",
                    operator=ComparisonOperator.LT,
                    threshold=0.0,
                    window="4q",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=["momentum_constraint"],
        )

    @pytest.fixture
    def sample_hypothesis_draft(self):
        """Create a sample DRAFT hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="value_reversion",
            title="Value Reversion Hypothesis",
            statement="High P/E stocks underperform over long horizons.",
            scope=HypothesisScope(symbols=[], sectors=[]),
            owner="human",
            status=HypothesisStatus.DRAFT,
            review_cycle="yearly",
            created_at=date(2025, 2, 1),
            evidence=Evidence(sources=[], notes=""),
            falsifiers=[
                Falsifier(
                    metric="long_term_alpha",
                    operator=ComparisonOperator.LT,
                    threshold=-0.02,
                    window="5y",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def sample_hypothesis_sunset(self):
        """Create a sample SUNSET hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="mean_reversion_short",
            title="Short-term Mean Reversion",
            statement="Prices revert to mean within 5 days.",
            scope=HypothesisScope(symbols=["AAPL", "MSFT"], sectors=[]),
            owner="human",
            status=HypothesisStatus.SUNSET,
            review_cycle="30d",
            created_at=date(2024, 12, 1),
            evidence=Evidence(sources=[], notes="Failed falsifier check."),
            falsifiers=[
                Falsifier(
                    metric="win_rate",
                    operator=ComparisonOperator.LT,
                    threshold=0.5,
                    window="90d",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=["mean_reversion_constraint"],
        )

    @pytest.fixture
    def sample_hypothesis_second_active(self):
        """Create another ACTIVE hypothesis for testing multiple active hypotheses."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="quality_factor",
            title="Quality Factor Hypothesis",
            statement="High quality companies outperform over long horizons.",
            scope=HypothesisScope(symbols=[], sectors=["financials", "industrials"]),
            owner="human",
            status=HypothesisStatus.ACTIVE,
            review_cycle="quarterly",
            created_at=date(2025, 1, 20),
            evidence=Evidence(sources=["https://example.com/quality"], notes="Quality research."),
            falsifiers=[
                Falsifier(
                    metric="quality_ic",
                    operator=ComparisonOperator.LT,
                    threshold=0.0,
                    window="1y",
                    trigger=TriggerAction.REVIEW,
                )
            ],
            linked_constraints=["quality_constraint"],
        )

    @pytest.fixture
    def sample_constraint_aapl(self):
        """Create a sample constraint that applies to AAPL."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
            ConstraintGuardrails,
        )
        from src.governance.models import StopMode

        return Constraint(
            id="momentum_constraint_aapl",
            title="Momentum Constraint for AAPL",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL"],
                strategies=["momentum_strategy"],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=["momentum_persistence"],
                disabled_if_falsified=True,
            ),
            actions=ConstraintActions(
                enable_strategy=True,
                pool_bias_multiplier=1.5,
                risk_budget_multiplier=2.0,
                veto_downgrade=False,
                stop_mode=StopMode.WIDE,
            ),
            guardrails=ConstraintGuardrails(
                max_position_pct=0.05,
                max_gross_exposure_delta=0.1,
            ),
            priority=50,
        )

    @pytest.fixture
    def sample_constraint_all_symbols(self):
        """Create a sample constraint that applies to all symbols (empty symbols list)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
            ConstraintGuardrails,
        )
        from src.governance.models import StopMode

        return Constraint(
            id="universal_risk_constraint",
            title="Universal Risk Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=[],  # Empty = applies to all
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(
                risk_budget_multiplier=1.2,
                veto_downgrade=True,
                stop_mode=StopMode.BASELINE,
            ),
            guardrails=ConstraintGuardrails(
                max_position_pct=0.10,
            ),
            priority=100,
        )

    @pytest.fixture
    def sample_constraint_requires_active_hypothesis(self):
        """Create a constraint that requires an active hypothesis."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="hypothesis_dependent_constraint",
            title="Hypothesis Dependent Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL", "MSFT"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=["momentum_persistence"],
                disabled_if_falsified=True,
            ),
            actions=ConstraintActions(
                pool_bias_multiplier=1.3,
            ),
            priority=75,
        )

    @pytest.fixture
    def sample_constraint_requires_inactive_hypothesis(self):
        """Create a constraint that requires a hypothesis that is NOT active (DRAFT)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="inactive_hypothesis_constraint",
            title="Inactive Hypothesis Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=["value_reversion"],  # DRAFT status
                disabled_if_falsified=True,
            ),
            actions=ConstraintActions(
                pool_bias_multiplier=2.0,
            ),
            priority=60,
        )

    @pytest.fixture
    def sample_constraint_disabled_if_falsified(self):
        """Create a constraint linked to a SUNSET hypothesis (should be disabled)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="sunset_linked_constraint",
            title="Sunset Linked Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL", "MSFT"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=["mean_reversion_short"],  # SUNSET status
                disabled_if_falsified=True,
            ),
            actions=ConstraintActions(
                risk_budget_multiplier=1.5,
            ),
            priority=80,
        )

    @pytest.fixture
    def sample_constraint_high_priority(self):
        """Create a high priority constraint."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.models import StopMode

        return Constraint(
            id="high_priority_constraint",
            title="High Priority Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(
                risk_budget_multiplier=3.0,
                stop_mode=StopMode.FUNDAMENTAL_GUARDED,
            ),
            priority=10,  # Lower number = higher priority
        )

    @pytest.fixture
    def sample_constraint_low_priority(self):
        """Create a low priority constraint."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.models import StopMode

        return Constraint(
            id="low_priority_constraint",
            title="Low Priority Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(
                risk_budget_multiplier=1.5,
                stop_mode=StopMode.BASELINE,
            ),
            priority=200,  # Higher number = lower priority
        )

    @pytest.fixture
    def sample_constraint_with_veto(self):
        """Create a constraint with veto_downgrade=True."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="veto_constraint",
            title="Veto Downgrade Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(
                veto_downgrade=True,
                pool_bias_multiplier=1.1,
            ),
            priority=90,
        )

    @pytest.fixture
    def sample_constraint_without_veto(self):
        """Create a constraint with veto_downgrade=False."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )

        return Constraint(
            id="no_veto_constraint",
            title="No Veto Constraint",
            applies_to=ConstraintAppliesTo(
                symbols=["AAPL"],
                strategies=[],
            ),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(
                veto_downgrade=False,
                pool_bias_multiplier=1.2,
            ),
            priority=95,
        )

    @pytest.fixture
    def hypothesis_registry(
        self,
        sample_hypothesis_active,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
        sample_hypothesis_second_active,
    ):
        """Create a HypothesisRegistry with sample hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)
        registry.register(sample_hypothesis_second_active)
        return registry

    @pytest.fixture
    def constraint_registry(
        self,
        sample_constraint_aapl,
        sample_constraint_all_symbols,
    ):
        """Create a ConstraintRegistry with sample constraints."""
        from src.governance.constraints.registry import ConstraintRegistry

        registry = ConstraintRegistry()
        registry.register(sample_constraint_aapl)
        registry.register(sample_constraint_all_symbols)
        return registry

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client for testing cache operations."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        redis.scan = AsyncMock(return_value=(0, []))
        return redis


class TestConstraintResolverInitialization(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver initialization."""

    def test_resolver_initialization_with_registries(self, hypothesis_registry):
        """ConstraintResolver should initialize with HypothesisRegistry and ConstraintRegistry."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        assert resolver is not None
        assert resolver.constraint_registry is constraint_registry
        assert resolver.hypothesis_registry is hypothesis_registry

    def test_resolver_initialization_with_cache(self, hypothesis_registry, mock_redis):
        """ConstraintResolver should accept optional GovernanceCache."""
        from src.governance.cache import GovernanceCache
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        cache = GovernanceCache(redis=mock_redis)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=cache,
        )

        assert resolver.cache is cache

    def test_resolver_initialization_without_cache(self, hypothesis_registry):
        """ConstraintResolver should work without cache (cache is optional)."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        assert resolver.cache is None


class TestConstraintResolverResolveForSymbol(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver.resolve() method - basic symbol resolution."""

    def test_resolve_returns_constraints_for_symbol(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        sample_constraint_all_symbols,
    ):
        """resolve() should return ResolvedConstraints for a symbol with applicable constraints."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)
        constraint_registry.register(sample_constraint_all_symbols)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        assert result is not None
        assert result.symbol == "AAPL"
        assert isinstance(result.resolved_at, datetime)
        assert result.version is not None

    def test_resolve_returns_applicable_constraints_only(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        sample_constraint_all_symbols,
    ):
        """resolve() should only include constraints that apply to the symbol."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)  # Applies to AAPL
        constraint_registry.register(sample_constraint_all_symbols)  # Applies to all

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Both constraints should apply to AAPL
        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "momentum_constraint_aapl" in constraint_ids
        assert "universal_risk_constraint" in constraint_ids

    def test_resolve_excludes_constraints_for_other_symbols(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        sample_constraint_all_symbols,
    ):
        """resolve() should exclude constraints that don't apply to the symbol."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)  # Only AAPL
        constraint_registry.register(sample_constraint_all_symbols)  # All symbols

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        # GOOGL doesn't have AAPL-specific constraint
        result = resolver.resolve("GOOGL")

        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "momentum_constraint_aapl" not in constraint_ids
        assert "universal_risk_constraint" in constraint_ids  # Universal applies

    def test_resolve_for_symbol_with_no_constraints(self, hypothesis_registry):
        """resolve() should return empty constraints list for symbol with no applicable constraints."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Create constraint that only applies to specific symbol
        specific_constraint = Constraint(
            id="msft_only",
            title="MSFT Only Constraint",
            applies_to=ConstraintAppliesTo(symbols=["MSFT"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=1.5),
            priority=100,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(specific_constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        # AAPL has no applicable constraints
        result = resolver.resolve("AAPL")

        assert result.symbol == "AAPL"
        assert len(result.constraints) == 0


class TestConstraintResolverActivationLogic(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver activation logic."""

    def test_resolve_includes_constraint_when_required_hypothesis_is_active(
        self,
        hypothesis_registry,
        sample_constraint_requires_active_hypothesis,
    ):
        """resolve() should include constraint when its requires_hypotheses_active are all ACTIVE."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_requires_active_hypothesis)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # hypothesis_dependent_constraint requires momentum_persistence which is ACTIVE
        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "hypothesis_dependent_constraint" in constraint_ids

    def test_resolve_excludes_constraint_when_required_hypothesis_not_active(
        self,
        hypothesis_registry,
        sample_constraint_requires_inactive_hypothesis,
    ):
        """resolve() should exclude constraint when its requires_hypotheses_active are NOT ACTIVE."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_requires_inactive_hypothesis)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # inactive_hypothesis_constraint requires value_reversion which is DRAFT (not ACTIVE)
        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "inactive_hypothesis_constraint" not in constraint_ids

    def test_resolve_excludes_constraint_when_linked_hypothesis_is_sunset(
        self,
        hypothesis_registry,
        sample_constraint_disabled_if_falsified,
    ):
        """resolve() should skip constraint if disabled_if_falsified=True and linked hypothesis is SUNSET."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_disabled_if_falsified)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # sunset_linked_constraint requires mean_reversion_short which is SUNSET
        # and disabled_if_falsified=True, so it should be excluded
        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "sunset_linked_constraint" not in constraint_ids

    def test_resolve_includes_constraint_with_no_hypothesis_requirements(
        self,
        hypothesis_registry,
        sample_constraint_all_symbols,
    ):
        """resolve() should include constraint with empty requires_hypotheses_active."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_all_symbols)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # universal_risk_constraint has empty requires_hypotheses_active
        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "universal_risk_constraint" in constraint_ids

    def test_resolve_requires_all_hypotheses_to_be_active(self, hypothesis_registry):
        """resolve() should exclude constraint if ANY required hypothesis is not ACTIVE."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Constraint requiring both active and draft hypotheses
        multi_requirement_constraint = Constraint(
            id="multi_requirement",
            title="Multi Requirement Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[
                    "momentum_persistence",  # ACTIVE
                    "value_reversion",  # DRAFT
                ],
                disabled_if_falsified=True,
            ),
            actions=ConstraintActions(risk_budget_multiplier=1.5),
            priority=100,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(multi_requirement_constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Should be excluded because value_reversion is not ACTIVE
        constraint_ids = [c.constraint_id for c in result.constraints]
        assert "multi_requirement" not in constraint_ids


class TestConstraintResolverPriorityOrdering(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver priority ordering."""

    def test_resolve_orders_constraints_by_priority_ascending(
        self,
        hypothesis_registry,
        sample_constraint_high_priority,
        sample_constraint_low_priority,
    ):
        """resolve() should list higher priority constraints first (lower priority number = higher priority)."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        # Register in reverse priority order
        constraint_registry.register(sample_constraint_low_priority)  # priority=200
        constraint_registry.register(sample_constraint_high_priority)  # priority=10

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        constraint_ids = [c.constraint_id for c in result.constraints]
        # High priority (10) should come before low priority (200)
        high_idx = constraint_ids.index("high_priority_constraint")
        low_idx = constraint_ids.index("low_priority_constraint")
        assert high_idx < low_idx

    def test_resolve_maintains_stable_order_for_same_priority(self, hypothesis_registry):
        """resolve() should maintain stable ordering for constraints with same priority."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Create multiple constraints with same priority
        constraints = [
            Constraint(
                id=f"same_priority_{i}",
                title=f"Same Priority Constraint {i}",
                applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
                activation=ConstraintActivation(
                    requires_hypotheses_active=[],
                    disabled_if_falsified=False,
                ),
                actions=ConstraintActions(pool_bias_multiplier=1.0 + i * 0.1),
                priority=50,  # Same priority
            )
            for i in range(3)
        ]

        constraint_registry = ConstraintRegistry()
        for c in constraints:
            constraint_registry.register(c)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        # Resolve multiple times and check consistency
        result1 = resolver.resolve("AAPL")
        result2 = resolver.resolve("AAPL")

        ids1 = [c.constraint_id for c in result1.constraints]
        ids2 = [c.constraint_id for c in result2.constraints]

        assert ids1 == ids2  # Order should be stable


class TestConstraintResolverMergedEffectiveValues(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver merged effective values."""

    def test_resolve_calculates_effective_risk_budget_multiplier(
        self,
        hypothesis_registry,
        sample_constraint_high_priority,
        sample_constraint_low_priority,
    ):
        """effective_risk_budget_multiplier should be product of all risk_budget_multiplier values."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        # high_priority: risk_budget_multiplier=3.0
        # low_priority: risk_budget_multiplier=1.5
        constraint_registry.register(sample_constraint_high_priority)
        constraint_registry.register(sample_constraint_low_priority)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Product: 3.0 * 1.5 = 4.5
        assert result.effective_risk_budget_multiplier == pytest.approx(4.5)

    def test_resolve_calculates_effective_pool_bias_multiplier(
        self,
        hypothesis_registry,
        sample_constraint_with_veto,
        sample_constraint_without_veto,
    ):
        """effective_pool_bias_multiplier should be product of all pool_bias_multiplier values."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        # with_veto: pool_bias_multiplier=1.1
        # without_veto: pool_bias_multiplier=1.2
        constraint_registry.register(sample_constraint_with_veto)
        constraint_registry.register(sample_constraint_without_veto)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Product: 1.1 * 1.2 = 1.32
        assert result.effective_pool_bias_multiplier == pytest.approx(1.32)

    def test_resolve_defaults_effective_risk_budget_multiplier_to_1(
        self,
        hypothesis_registry,
    ):
        """effective_risk_budget_multiplier should default to 1.0 when no constraints specify it."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Constraint without risk_budget_multiplier
        constraint = Constraint(
            id="no_risk_budget",
            title="No Risk Budget Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(pool_bias_multiplier=1.5),  # No risk_budget_multiplier
            priority=100,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        assert result.effective_risk_budget_multiplier == 1.0

    def test_resolve_calculates_effective_stop_mode_most_restrictive(
        self,
        hypothesis_registry,
    ):
        """effective_stop_mode should use most restrictive (fundamental_guarded > wide > baseline)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver
        from src.governance.models import StopMode

        # Multiple constraints with different stop modes
        baseline_constraint = Constraint(
            id="baseline_stop",
            title="Baseline Stop",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(stop_mode=StopMode.BASELINE),
            priority=100,
        )

        wide_constraint = Constraint(
            id="wide_stop",
            title="Wide Stop",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(stop_mode=StopMode.WIDE),
            priority=90,
        )

        fundamental_constraint = Constraint(
            id="fundamental_stop",
            title="Fundamental Stop",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(stop_mode=StopMode.FUNDAMENTAL_GUARDED),
            priority=80,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(baseline_constraint)
        constraint_registry.register(wide_constraint)
        constraint_registry.register(fundamental_constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Most restrictive: fundamental_guarded
        assert result.effective_stop_mode == "fundamental_guarded"

    def test_resolve_effective_stop_mode_wide_over_baseline(self, hypothesis_registry):
        """effective_stop_mode: wide is more restrictive than baseline."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver
        from src.governance.models import StopMode

        baseline_constraint = Constraint(
            id="baseline_stop",
            title="Baseline Stop",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(stop_mode=StopMode.BASELINE),
            priority=100,
        )

        wide_constraint = Constraint(
            id="wide_stop",
            title="Wide Stop",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(stop_mode=StopMode.WIDE),
            priority=90,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(baseline_constraint)
        constraint_registry.register(wide_constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        assert result.effective_stop_mode == "wide"

    def test_resolve_defaults_effective_stop_mode_to_baseline(self, hypothesis_registry):
        """effective_stop_mode should default to 'baseline' when no constraints specify it."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Constraint without stop_mode
        constraint = Constraint(
            id="no_stop_mode",
            title="No Stop Mode Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=1.5),  # No stop_mode
            priority=100,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        assert result.effective_stop_mode == "baseline"

    def test_resolve_calculates_veto_downgrade_active_with_or(
        self,
        hypothesis_registry,
        sample_constraint_with_veto,
        sample_constraint_without_veto,
    ):
        """veto_downgrade_active should be OR of all veto_downgrade values."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        # with_veto: veto_downgrade=True
        # without_veto: veto_downgrade=False
        constraint_registry.register(sample_constraint_with_veto)
        constraint_registry.register(sample_constraint_without_veto)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # OR: True OR False = True
        assert result.veto_downgrade_active is True

    def test_resolve_veto_downgrade_active_false_when_all_false(self, hypothesis_registry):
        """veto_downgrade_active should be False when all constraints have veto_downgrade=False."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint1 = Constraint(
            id="no_veto_1",
            title="No Veto 1",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(veto_downgrade=False),
            priority=100,
        )

        constraint2 = Constraint(
            id="no_veto_2",
            title="No Veto 2",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(veto_downgrade=False),
            priority=90,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint1)
        constraint_registry.register(constraint2)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # OR: False OR False = False
        assert result.veto_downgrade_active is False

    def test_resolve_defaults_veto_downgrade_active_to_false(self, hypothesis_registry):
        """veto_downgrade_active should default to False when no constraints specify it."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Constraint without veto_downgrade
        constraint = Constraint(
            id="no_veto",
            title="No Veto Constraint",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=1.5),  # No veto_downgrade
            priority=100,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        assert result.veto_downgrade_active is False


class TestConstraintResolverGuardrailsMerging(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver guardrails merging."""

    def test_resolve_merges_guardrails_using_most_restrictive(self, hypothesis_registry):
        """guardrails should use most restrictive values (minimum for caps, maximum for addons)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
            ConstraintGuardrails,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint1 = Constraint(
            id="guardrails_1",
            title="Guardrails 1",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(),
            guardrails=ConstraintGuardrails(
                max_position_pct=0.10,
                max_gross_exposure_delta=0.15,
                max_drawdown_addon=0.05,
            ),
            priority=100,
        )

        constraint2 = Constraint(
            id="guardrails_2",
            title="Guardrails 2",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(),
            guardrails=ConstraintGuardrails(
                max_position_pct=0.05,  # More restrictive (lower)
                max_gross_exposure_delta=0.20,  # Less restrictive
                max_drawdown_addon=0.03,  # More restrictive (lower addon means less tolerance)
            ),
            priority=90,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint1)
        constraint_registry.register(constraint2)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Most restrictive: min(0.10, 0.05) = 0.05
        assert result.guardrails.max_position_pct == pytest.approx(0.05)
        # Most restrictive: min(0.15, 0.20) = 0.15
        assert result.guardrails.max_gross_exposure_delta == pytest.approx(0.15)
        # Most restrictive for addon: min(0.05, 0.03) = 0.03
        assert result.guardrails.max_drawdown_addon == pytest.approx(0.03)

    def test_resolve_guardrails_handles_partial_definitions(self, hypothesis_registry):
        """guardrails merging should handle constraints with partial guardrails definitions."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
            ConstraintGuardrails,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint1 = Constraint(
            id="partial_guardrails",
            title="Partial Guardrails",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(),
            guardrails=ConstraintGuardrails(
                max_position_pct=0.05,
                # max_gross_exposure_delta not set
                # max_drawdown_addon not set
            ),
            priority=100,
        )

        constraint2 = Constraint(
            id="other_guardrails",
            title="Other Guardrails",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(),
            guardrails=ConstraintGuardrails(
                max_gross_exposure_delta=0.10,
                # max_position_pct not set
            ),
            priority=90,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint1)
        constraint_registry.register(constraint2)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Only defined values should be used
        assert result.guardrails.max_position_pct == pytest.approx(0.05)
        assert result.guardrails.max_gross_exposure_delta == pytest.approx(0.10)

    def test_resolve_guardrails_none_when_no_constraints_define_guardrails(
        self, hypothesis_registry
    ):
        """guardrails should be None or have None fields when no constraints define guardrails."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint = Constraint(
            id="no_guardrails",
            title="No Guardrails",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=1.5),
            # guardrails not set
            priority=100,
        )

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(constraint)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Either guardrails is None or all fields are None
        if result.guardrails is not None:
            assert result.guardrails.max_position_pct is None
            assert result.guardrails.max_gross_exposure_delta is None
            assert result.guardrails.max_drawdown_addon is None


class TestConstraintResolverVersionHash(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver version hash generation."""

    def test_resolve_generates_version_hash(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
    ):
        """resolve() should generate a version hash for the resolved constraints."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        assert result.version is not None
        assert isinstance(result.version, str)
        assert len(result.version) > 0

    def test_resolve_version_hash_is_deterministic(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        sample_constraint_all_symbols,
    ):
        """resolve() should generate the same version hash for the same constraints."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)
        constraint_registry.register(sample_constraint_all_symbols)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result1 = resolver.resolve("AAPL")
        result2 = resolver.resolve("AAPL")

        assert result1.version == result2.version

    def test_resolve_version_hash_changes_with_different_constraints(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        sample_constraint_all_symbols,
    ):
        """resolve() should generate different version hashes for different constraint sets."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # First resolver with one constraint
        registry1 = ConstraintRegistry()
        registry1.register(sample_constraint_aapl)

        resolver1 = ConstraintResolver(
            constraint_registry=registry1,
            hypothesis_registry=hypothesis_registry,
        )

        # Second resolver with different constraint
        registry2 = ConstraintRegistry()
        registry2.register(sample_constraint_all_symbols)

        resolver2 = ConstraintResolver(
            constraint_registry=registry2,
            hypothesis_registry=hypothesis_registry,
        )

        result1 = resolver1.resolve("AAPL")
        result2 = resolver2.resolve("AAPL")

        assert result1.version != result2.version

    def test_resolve_version_hash_based_on_constraint_ids_and_versions(
        self,
        hypothesis_registry,
    ):
        """Version hash should be based on constraint IDs (and versions if constraints have versions)."""
        from src.governance.constraints.models import (
            Constraint,
            ConstraintActions,
            ConstraintActivation,
            ConstraintAppliesTo,
        )
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint1 = Constraint(
            id="constraint_a",
            title="Constraint A",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=1.5),
            priority=100,
        )

        constraint2 = Constraint(
            id="constraint_b",
            title="Constraint B",
            applies_to=ConstraintAppliesTo(symbols=["AAPL"], strategies=[]),
            activation=ConstraintActivation(
                requires_hypotheses_active=[],
                disabled_if_falsified=False,
            ),
            actions=ConstraintActions(risk_budget_multiplier=2.0),
            priority=90,
        )

        registry = ConstraintRegistry()
        registry.register(constraint1)
        registry.register(constraint2)

        resolver = ConstraintResolver(
            constraint_registry=registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Version should be a hash string (e.g., SHA256 hex digest or similar)
        assert len(result.version) >= 8  # At least 8 chars for a meaningful hash


class TestConstraintResolverCacheIntegration(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver Redis cache integration."""

    @pytest.mark.asyncio
    async def test_resolve_async_uses_cache_when_available(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        mock_redis,
    ):
        """resolve_async() should check cache first and return cached value if found."""
        from src.governance.cache import GovernanceCache
        from src.governance.constraints.models import ResolvedConstraints
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        # Set up cached value
        cached_result = ResolvedConstraints(
            symbol="AAPL",
            constraints=[],
            resolved_at=datetime.now(timezone.utc),
            version="cached_version",
            effective_risk_budget_multiplier=1.0,
            effective_pool_bias_multiplier=1.0,
            effective_stop_mode="baseline",
            veto_downgrade_active=False,
        )

        mock_redis.get = AsyncMock(return_value=cached_result.model_dump_json().encode("utf-8"))

        cache = GovernanceCache(redis=mock_redis)

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=cache,
        )

        result = await resolver.resolve_async("AAPL")

        # Should return cached value
        assert result.version == "cached_version"

    @pytest.mark.asyncio
    async def test_resolve_async_caches_result_on_miss(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        mock_redis,
    ):
        """resolve_async() should cache the result on cache miss."""
        from src.governance.cache import GovernanceCache
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        mock_redis.get = AsyncMock(return_value=None)  # Cache miss
        mock_redis.set = AsyncMock()

        cache = GovernanceCache(redis=mock_redis)

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=cache,
        )

        result = await resolver.resolve_async("AAPL")

        # Should have called set to cache the result
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        # Verify the key contains the symbol
        assert "AAPL" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_resolve_async_works_without_cache(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
    ):
        """resolve_async() should work without cache configured."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=None,
        )

        result = await resolver.resolve_async("AAPL")

        assert result is not None
        assert result.symbol == "AAPL"


class TestConstraintResolverCacheInvalidation(TestConstraintResolverFixtures):
    """Tests for ConstraintResolver cache invalidation."""

    @pytest.mark.asyncio
    async def test_invalidate_cache_for_symbol(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        mock_redis,
    ):
        """invalidate_cache() should delete cached constraints for a symbol."""
        from src.governance.cache import GovernanceCache
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        mock_redis.delete = AsyncMock()

        cache = GovernanceCache(redis=mock_redis)

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=cache,
        )

        await resolver.invalidate_cache("AAPL")

        mock_redis.delete.assert_called_once()
        call_args = mock_redis.delete.call_args
        assert "AAPL" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_invalidate_all_cache(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
        mock_redis,
    ):
        """invalidate_all_cache() should invalidate all cached constraints."""
        from src.governance.cache import GovernanceCache
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        mock_redis.scan = AsyncMock(return_value=(0, [b"key1", b"key2"]))
        mock_redis.delete = AsyncMock(return_value=2)

        cache = GovernanceCache(redis=mock_redis)

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=cache,
        )

        count = await resolver.invalidate_all_cache()

        # Should have invalidated the constraint namespace
        mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_invalidate_cache_no_op_without_cache(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
    ):
        """invalidate_cache() should be no-op when cache is not configured."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
            cache=None,
        )

        # Should not raise
        await resolver.invalidate_cache("AAPL")


class TestConstraintResolverResolvedAction(TestConstraintResolverFixtures):
    """Tests for ResolvedAction model."""

    def test_resolved_action_structure(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
    ):
        """ResolvedAction should have constraint_id, action_type, and value."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # Should have resolved actions
        assert len(result.constraints) > 0

        for action in result.constraints:
            assert hasattr(action, "constraint_id")
            assert hasattr(action, "action_type")
            assert hasattr(action, "value")
            assert action.constraint_id is not None
            assert action.action_type is not None

    def test_resolved_action_includes_all_action_types(
        self,
        hypothesis_registry,
        sample_constraint_aapl,
    ):
        """ResolvedAction should include entries for each action type defined in constraint."""
        from src.governance.constraints.registry import ConstraintRegistry
        from src.governance.constraints.resolver import ConstraintResolver

        constraint_registry = ConstraintRegistry()
        constraint_registry.register(sample_constraint_aapl)

        resolver = ConstraintResolver(
            constraint_registry=constraint_registry,
            hypothesis_registry=hypothesis_registry,
        )

        result = resolver.resolve("AAPL")

        # sample_constraint_aapl has: enable_strategy, pool_bias_multiplier,
        # risk_budget_multiplier, veto_downgrade, stop_mode
        action_types = {
            action.action_type
            for action in result.constraints
            if action.constraint_id == "momentum_constraint_aapl"
        }

        # Should have multiple action types from the constraint
        assert len(action_types) >= 1


class TestConstraintResolverModelsImport:
    """Tests for model imports from constraints.models."""

    def test_resolved_constraints_importable(self):
        """ResolvedConstraints should be importable from constraints.models."""
        from src.governance.constraints.models import ResolvedConstraints

        assert ResolvedConstraints is not None

    def test_resolved_action_importable(self):
        """ResolvedAction should be importable from constraints.models."""
        from src.governance.constraints.models import ResolvedAction

        assert ResolvedAction is not None

    def test_constraint_resolver_importable(self):
        """ConstraintResolver should be importable from constraints.resolver."""
        from src.governance.constraints.resolver import ConstraintResolver

        assert ConstraintResolver is not None


class TestResolvedConstraintsModel:
    """Tests for ResolvedConstraints Pydantic model."""

    def test_resolved_constraints_required_fields(self):
        """ResolvedConstraints should require symbol, constraints, resolved_at, version."""
        from datetime import datetime, timezone

        from pydantic import ValidationError
        from src.governance.constraints.models import ResolvedConstraints

        # Valid minimal ResolvedConstraints
        valid = ResolvedConstraints(
            symbol="AAPL",
            constraints=[],
            resolved_at=datetime.now(timezone.utc),
            version="abc123",
        )
        assert valid.symbol == "AAPL"

        # Missing required field should raise
        with pytest.raises(ValidationError):
            ResolvedConstraints(
                constraints=[],
                resolved_at=datetime.now(timezone.utc),
                version="abc123",
                # symbol missing
            )

    def test_resolved_constraints_default_values(self):
        """ResolvedConstraints should have correct default values."""
        from datetime import datetime, timezone

        from src.governance.constraints.models import ResolvedConstraints

        result = ResolvedConstraints(
            symbol="AAPL",
            constraints=[],
            resolved_at=datetime.now(timezone.utc),
            version="abc123",
        )

        assert result.effective_risk_budget_multiplier == 1.0
        assert result.effective_pool_bias_multiplier == 1.0
        assert result.effective_stop_mode == "baseline"
        assert result.veto_downgrade_active is False


class TestResolvedActionModel:
    """Tests for ResolvedAction Pydantic model."""

    def test_resolved_action_required_fields(self):
        """ResolvedAction should require constraint_id, action_type, value."""
        from pydantic import ValidationError
        from src.governance.constraints.models import ResolvedAction

        # Valid ResolvedAction with number value
        valid_number = ResolvedAction(
            constraint_id="test_constraint",
            action_type="risk_budget_multiplier",
            value=1.5,
        )
        assert valid_number.value == 1.5

        # Valid ResolvedAction with boolean value
        valid_bool = ResolvedAction(
            constraint_id="test_constraint",
            action_type="veto_downgrade",
            value=True,
        )
        assert valid_bool.value is True

        # Valid ResolvedAction with string value
        valid_str = ResolvedAction(
            constraint_id="test_constraint",
            action_type="stop_mode",
            value="wide",
        )
        assert valid_str.value == "wide"

        # Missing required field should raise
        with pytest.raises(ValidationError):
            ResolvedAction(
                action_type="risk_budget_multiplier",
                value=1.5,
                # constraint_id missing
            )
