"""Tests for falsifier checker, metric registry, and scheduler.

TDD: Write tests FIRST, then implement to make them pass.

This module tests:
1. FalsifierCheckResult model (T052)
2. MetricRegistry for registering and querying metric providers (T054)
3. FalsifierChecker for evaluating falsifiers against metrics (T055)
4. FalsifierScheduler for running all checks and generating alerts (T057)

Spec Requirements:
- FR-025: Falsifier checks on configurable schedule
- US4 Scenario 1: When IC drops below 0 for 6 months, review report recommending sunset
- US4 Scenario 2: Constraint with disabled_if_falsified auto-disabled when falsified
"""

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

# =============================================================================
# Shared Fixtures
# =============================================================================


class TestFalsifierFixtures:
    """Shared fixtures for falsifier tests."""

    @pytest.fixture
    def sample_hypothesis_active(self):
        """Create a sample ACTIVE hypothesis with a falsifier."""
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
                    window="6m",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=["momentum_constraint"],
        )

    @pytest.fixture
    def sample_hypothesis_multi_falsifier(self):
        """Create a hypothesis with multiple falsifiers."""
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
            id="multi_falsifier_hyp",
            title="Multi Falsifier Hypothesis",
            statement="Hypothesis with multiple falsifiers.",
            scope=HypothesisScope(symbols=[], sectors=[]),
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
                Falsifier(
                    metric="win_rate",
                    operator=ComparisonOperator.LT,
                    threshold=0.45,
                    window="90d",
                    trigger=TriggerAction.REVIEW,
                ),
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def sample_hypothesis_draft(self):
        """Create a DRAFT hypothesis (should be skipped by check_all)."""
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
            id="draft_hypothesis",
            title="Draft Hypothesis",
            statement="A draft hypothesis.",
            scope=HypothesisScope(symbols=[], sectors=[]),
            owner="human",
            status=HypothesisStatus.DRAFT,
            review_cycle="yearly",
            created_at=date(2025, 2, 1),
            evidence=Evidence(sources=[], notes=""),
            falsifiers=[
                Falsifier(
                    metric="some_metric",
                    operator=ComparisonOperator.LT,
                    threshold=0.0,
                    window="1y",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def hypothesis_registry(self, sample_hypothesis_active, sample_hypothesis_multi_falsifier):
        """Create a HypothesisRegistry with sample hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_multi_falsifier)
        return registry

    @pytest.fixture
    def metric_registry(self):
        """Create a MetricRegistry with sample providers."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        # Register a provider that returns 0.05 (positive IC, should pass)
        registry.register("rolling_ic_mean", lambda window=None: 0.05)
        # Register a provider that returns 0.50 (win rate at threshold)
        registry.register("win_rate", lambda window=None: 0.50)
        return registry

    @pytest.fixture
    def metric_registry_negative_ic(self):
        """Create a MetricRegistry where IC is negative (should trigger)."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        # Negative IC - should trigger falsifier
        registry.register("rolling_ic_mean", lambda window=None: -0.03)
        # Win rate below threshold - should trigger
        registry.register("win_rate", lambda window=None: 0.40)
        return registry


# =============================================================================
# T052: FalsifierCheckResult Model Tests
# =============================================================================


class TestFalsifierCheckResultModel:
    """Tests for FalsifierCheckResult Pydantic model."""

    def test_falsifier_check_result_creation(self):
        """FalsifierCheckResult should be creatable with all required fields."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        result = FalsifierCheckResult(
            hypothesis_id="test_hyp",
            falsifier_index=0,
            metric="rolling_ic_mean",
            operator=ComparisonOperator.LT,
            threshold=0.0,
            window="6m",
            metric_value=0.05,
            triggered=False,
            trigger_action=TriggerAction.SUNSET,
            checked_at=datetime.now(timezone.utc),
            message="Falsifier check passed: rolling_ic_mean=0.05, threshold <0.0",
        )

        assert result.hypothesis_id == "test_hyp"
        assert result.falsifier_index == 0
        assert result.metric == "rolling_ic_mean"
        assert result.operator == ComparisonOperator.LT
        assert result.threshold == 0.0
        assert result.window == "6m"
        assert result.metric_value == 0.05
        assert result.triggered is False
        assert result.trigger_action == TriggerAction.SUNSET

    def test_falsifier_check_result_metric_value_none(self):
        """FalsifierCheckResult should allow None metric_value (data unavailable)."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        result = FalsifierCheckResult(
            hypothesis_id="test_hyp",
            falsifier_index=0,
            metric="missing_metric",
            operator=ComparisonOperator.LT,
            threshold=0.0,
            window="6m",
            metric_value=None,
            triggered=False,
            trigger_action=TriggerAction.SUNSET,
            checked_at=datetime.now(timezone.utc),
            message="Metric data unavailable",
        )

        assert result.metric_value is None
        assert result.triggered is False

    def test_falsifier_check_result_triggered(self):
        """FalsifierCheckResult should represent triggered state correctly."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        result = FalsifierCheckResult(
            hypothesis_id="test_hyp",
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

        assert result.triggered is True
        assert result.metric_value == -0.03

    def test_falsifier_check_result_forbids_extra_fields(self):
        """FalsifierCheckResult should reject extra fields (GovernanceBaseModel)."""
        from pydantic import ValidationError
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        with pytest.raises(ValidationError):
            FalsifierCheckResult(
                hypothesis_id="test_hyp",
                falsifier_index=0,
                metric="rolling_ic_mean",
                operator=ComparisonOperator.LT,
                threshold=0.0,
                window="6m",
                metric_value=0.05,
                triggered=False,
                trigger_action=TriggerAction.SUNSET,
                checked_at=datetime.now(timezone.utc),
                message="test",
                extra_field="should_fail",
            )

    def test_falsifier_check_result_serialization(self):
        """FalsifierCheckResult should serialize to dict/JSON correctly."""
        from src.governance.models import ComparisonOperator, TriggerAction
        from src.governance.monitoring.models import FalsifierCheckResult

        now = datetime.now(timezone.utc)
        result = FalsifierCheckResult(
            hypothesis_id="test_hyp",
            falsifier_index=0,
            metric="rolling_ic_mean",
            operator=ComparisonOperator.LT,
            threshold=0.0,
            window="6m",
            metric_value=-0.03,
            triggered=True,
            trigger_action=TriggerAction.SUNSET,
            checked_at=now,
            message="TRIGGERED",
        )

        data = result.model_dump()
        assert data["hypothesis_id"] == "test_hyp"
        assert data["triggered"] is True
        assert data["operator"] == "<"
        assert data["trigger_action"] == "sunset"


# =============================================================================
# T054: MetricRegistry Tests
# =============================================================================


class TestMetricRegistry:
    """Tests for MetricRegistry pattern."""

    def test_metric_registry_register_and_get(self):
        """MetricRegistry should register and retrieve metric providers."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        registry.register("rolling_ic_mean", lambda window=None: 0.05)

        value = registry.get_value("rolling_ic_mean")
        assert value == 0.05

    def test_metric_registry_get_with_window(self):
        """MetricRegistry should pass window parameter to provider."""
        from src.governance.monitoring.metrics import MetricRegistry

        def ic_provider(window=None):
            if window == "6m":
                return 0.03
            return 0.05

        registry = MetricRegistry()
        registry.register("rolling_ic_mean", ic_provider)

        assert registry.get_value("rolling_ic_mean", window="6m") == 0.03
        assert registry.get_value("rolling_ic_mean") == 0.05

    def test_metric_registry_get_unknown_metric(self):
        """MetricRegistry should return None for unknown metrics."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        value = registry.get_value("nonexistent_metric")
        assert value is None

    def test_metric_registry_has_metric(self):
        """MetricRegistry.has_metric should check if a metric is registered."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        registry.register("rolling_ic_mean", lambda window=None: 0.05)

        assert registry.has_metric("rolling_ic_mean") is True
        assert registry.has_metric("nonexistent") is False

    def test_metric_registry_register_overwrites(self):
        """Registering same metric name should overwrite previous provider."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        registry.register("rolling_ic_mean", lambda window=None: 0.05)
        registry.register("rolling_ic_mean", lambda window=None: 0.10)

        assert registry.get_value("rolling_ic_mean") == 0.10

    def test_metric_registry_provider_returns_none(self):
        """MetricRegistry should handle providers that return None (data unavailable)."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        registry.register("unavailable_metric", lambda window=None: None)

        assert registry.get_value("unavailable_metric") is None

    def test_metric_registry_provider_raises_returns_none(self):
        """MetricRegistry should return None if provider raises exception."""
        from src.governance.monitoring.metrics import MetricRegistry

        def broken_provider(window=None):
            raise RuntimeError("Data source unavailable")

        registry = MetricRegistry()
        registry.register("broken_metric", broken_provider)

        value = registry.get_value("broken_metric")
        assert value is None

    def test_metric_registry_multiple_metrics(self):
        """MetricRegistry should support multiple different metrics."""
        from src.governance.monitoring.metrics import MetricRegistry

        registry = MetricRegistry()
        registry.register("rolling_ic_mean", lambda window=None: 0.05)
        registry.register("win_rate", lambda window=None: 0.55)
        registry.register("sharpe_ratio", lambda window=None: 1.2)

        assert registry.get_value("rolling_ic_mean") == 0.05
        assert registry.get_value("win_rate") == 0.55
        assert registry.get_value("sharpe_ratio") == 1.2


# =============================================================================
# T055: FalsifierChecker Tests
# =============================================================================


class TestFalsifierCheckerCompare(TestFalsifierFixtures):
    """Tests for FalsifierChecker._compare method."""

    def test_compare_lt_true(self):
        """_compare should return True when value < threshold."""
        from src.governance.models import ComparisonOperator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        checker = FalsifierChecker(
            hypothesis_registry=MagicMock(),
            metric_registry=MetricRegistry(),
        )
        assert checker._compare(-0.01, ComparisonOperator.LT, 0.0) is True

    def test_compare_lt_false(self):
        """_compare should return False when value >= threshold."""
        from src.governance.models import ComparisonOperator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        checker = FalsifierChecker(
            hypothesis_registry=MagicMock(),
            metric_registry=MetricRegistry(),
        )
        assert checker._compare(0.0, ComparisonOperator.LT, 0.0) is False
        assert checker._compare(0.05, ComparisonOperator.LT, 0.0) is False

    def test_compare_lte(self):
        """_compare should handle <= operator."""
        from src.governance.models import ComparisonOperator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        checker = FalsifierChecker(
            hypothesis_registry=MagicMock(),
            metric_registry=MetricRegistry(),
        )
        assert checker._compare(0.0, ComparisonOperator.LTE, 0.0) is True
        assert checker._compare(-0.01, ComparisonOperator.LTE, 0.0) is True
        assert checker._compare(0.01, ComparisonOperator.LTE, 0.0) is False

    def test_compare_gt(self):
        """_compare should handle > operator."""
        from src.governance.models import ComparisonOperator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        checker = FalsifierChecker(
            hypothesis_registry=MagicMock(),
            metric_registry=MetricRegistry(),
        )
        assert checker._compare(0.05, ComparisonOperator.GT, 0.0) is True
        assert checker._compare(0.0, ComparisonOperator.GT, 0.0) is False

    def test_compare_gte(self):
        """_compare should handle >= operator."""
        from src.governance.models import ComparisonOperator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        checker = FalsifierChecker(
            hypothesis_registry=MagicMock(),
            metric_registry=MetricRegistry(),
        )
        assert checker._compare(0.0, ComparisonOperator.GTE, 0.0) is True
        assert checker._compare(0.05, ComparisonOperator.GTE, 0.0) is True
        assert checker._compare(-0.01, ComparisonOperator.GTE, 0.0) is False

    def test_compare_eq(self):
        """_compare should handle == operator."""
        from src.governance.models import ComparisonOperator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        checker = FalsifierChecker(
            hypothesis_registry=MagicMock(),
            metric_registry=MetricRegistry(),
        )
        assert checker._compare(0.0, ComparisonOperator.EQ, 0.0) is True
        assert checker._compare(0.01, ComparisonOperator.EQ, 0.0) is False


class TestFalsifierCheckerEvaluate(TestFalsifierFixtures):
    """Tests for FalsifierChecker.evaluate_falsifier method."""

    def test_evaluate_falsifier_not_triggered(
        self, sample_hypothesis_active, hypothesis_registry, metric_registry
    ):
        """evaluate_falsifier should return not triggered when metric is above threshold."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry,
        )

        falsifier = sample_hypothesis_active.falsifiers[0]
        result = checker.evaluate_falsifier("momentum_persistence", falsifier, 0)

        assert result.triggered is False
        assert result.hypothesis_id == "momentum_persistence"
        assert result.metric == "rolling_ic_mean"
        assert result.metric_value == 0.05
        assert result.falsifier_index == 0

    def test_evaluate_falsifier_triggered(
        self, sample_hypothesis_active, hypothesis_registry, metric_registry_negative_ic
    ):
        """evaluate_falsifier should return triggered when metric breaches threshold."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_negative_ic,
        )

        falsifier = sample_hypothesis_active.falsifiers[0]
        result = checker.evaluate_falsifier("momentum_persistence", falsifier, 0)

        assert result.triggered is True
        assert result.metric_value == -0.03
        assert result.trigger_action.value == "sunset"

    def test_evaluate_falsifier_metric_unavailable(
        self, sample_hypothesis_active, hypothesis_registry
    ):
        """evaluate_falsifier should handle unavailable metrics gracefully."""
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        # Empty metric registry - no providers
        empty_registry = MetricRegistry()
        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=empty_registry,
        )

        falsifier = sample_hypothesis_active.falsifiers[0]
        result = checker.evaluate_falsifier("momentum_persistence", falsifier, 0)

        assert result.triggered is False
        assert result.metric_value is None
        assert "unavailable" in result.message.lower() or "no data" in result.message.lower()


class TestFalsifierCheckerCheckHypothesis(TestFalsifierFixtures):
    """Tests for FalsifierChecker.check_hypothesis method."""

    def test_check_hypothesis_returns_results_per_falsifier(
        self,
        sample_hypothesis_multi_falsifier,
        hypothesis_registry,
        metric_registry,
    ):
        """check_hypothesis should return one result per falsifier."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry,
        )

        results = checker.check_hypothesis("multi_falsifier_hyp")

        assert len(results) == 2
        assert results[0].falsifier_index == 0
        assert results[1].falsifier_index == 1

    def test_check_hypothesis_not_found_raises(self, hypothesis_registry, metric_registry):
        """check_hypothesis should raise ValueError for unknown hypothesis."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry,
        )

        with pytest.raises(ValueError, match="not found"):
            checker.check_hypothesis("nonexistent_hyp")

    def test_check_hypothesis_single_falsifier_pass(
        self, sample_hypothesis_active, hypothesis_registry, metric_registry
    ):
        """check_hypothesis should return pass for single non-triggered falsifier."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry,
        )

        results = checker.check_hypothesis("momentum_persistence")

        assert len(results) == 1
        assert results[0].triggered is False

    def test_check_hypothesis_single_falsifier_triggered(
        self,
        sample_hypothesis_active,
        hypothesis_registry,
        metric_registry_negative_ic,
    ):
        """check_hypothesis should return triggered for falsifier with breached threshold."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_negative_ic,
        )

        results = checker.check_hypothesis("momentum_persistence")

        assert len(results) == 1
        assert results[0].triggered is True
        assert results[0].trigger_action.value == "sunset"


class TestFalsifierCheckerCheckAll(TestFalsifierFixtures):
    """Tests for FalsifierChecker.check_all method."""

    def test_check_all_checks_only_active_hypotheses(
        self,
        sample_hypothesis_active,
        sample_hypothesis_multi_falsifier,
        sample_hypothesis_draft,
        metric_registry,
    ):
        """check_all should only check ACTIVE hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.monitoring.falsifier import FalsifierChecker

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_multi_falsifier)
        registry.register(sample_hypothesis_draft)  # DRAFT - should be skipped

        checker = FalsifierChecker(
            hypothesis_registry=registry,
            metric_registry=metric_registry,
        )

        results = checker.check_all()

        # 1 falsifier from momentum_persistence + 2 from multi_falsifier_hyp = 3
        assert len(results) == 3
        hypothesis_ids = {r.hypothesis_id for r in results}
        assert "momentum_persistence" in hypothesis_ids
        assert "multi_falsifier_hyp" in hypothesis_ids
        assert "draft_hypothesis" not in hypothesis_ids

    def test_check_all_returns_empty_for_no_active_hypotheses(self, sample_hypothesis_draft):
        """check_all should return empty list when no active hypotheses exist."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_draft)

        checker = FalsifierChecker(
            hypothesis_registry=registry,
            metric_registry=MetricRegistry(),
        )

        results = checker.check_all()

        assert results == []


# =============================================================================
# US4 Acceptance Scenario 1: IC drops below 0 triggers sunset recommendation
# =============================================================================


class TestFalsifierAcceptanceScenario1(TestFalsifierFixtures):
    """US4 Scenario 1: IC below 0 for 6 months -> review report recommending sunset."""

    def test_ic_below_zero_triggers_sunset_action(self):
        """When IC drops below 0 for 6 months, falsifier should trigger with sunset action."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.metrics import MetricRegistry

        # Set up hypothesis with spec-defined falsifier
        hypothesis = Hypothesis(
            id="momentum_ic_test",
            title="Momentum IC Test",
            statement="Momentum factor has positive IC.",
            scope=HypothesisScope(symbols=[], sectors=[]),
            owner="human",
            status=HypothesisStatus.ACTIVE,
            review_cycle="quarterly",
            created_at=date(2025, 1, 1),
            evidence=Evidence(sources=[], notes=""),
            falsifiers=[
                Falsifier(
                    metric="rolling_ic_mean",
                    operator=ComparisonOperator.LT,
                    threshold=0,
                    window="6m",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=[],
        )

        hyp_registry = HypothesisRegistry()
        hyp_registry.register(hypothesis)

        # IC is negative - should trigger
        metric_registry = MetricRegistry()
        metric_registry.register("rolling_ic_mean", lambda window=None: -0.02)

        checker = FalsifierChecker(
            hypothesis_registry=hyp_registry,
            metric_registry=metric_registry,
        )

        results = checker.check_hypothesis("momentum_ic_test")

        assert len(results) == 1
        result = results[0]
        assert result.triggered is True
        assert result.trigger_action == TriggerAction.SUNSET
        assert result.metric_value == -0.02
        assert result.threshold == 0.0


# =============================================================================
# T057: FalsifierScheduler Tests
# =============================================================================


class TestFalsifierScheduler(TestFalsifierFixtures):
    """Tests for FalsifierScheduler."""

    def test_scheduler_run_checks_returns_results(self, hypothesis_registry, metric_registry):
        """run_checks should run all falsifier checks and return results."""
        from src.governance.monitoring.alerts import AlertGenerator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.scheduler import FalsifierScheduler

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry,
        )
        alert_generator = AlertGenerator()

        scheduler = FalsifierScheduler(
            checker=checker,
            alert_generator=alert_generator,
        )

        results = scheduler.run_checks()

        # Should have results for all active hypothesis falsifiers
        assert len(results) >= 1

    def test_scheduler_generates_alerts_for_triggered(
        self, hypothesis_registry, metric_registry_negative_ic
    ):
        """run_checks should generate alerts for triggered falsifiers."""
        from src.governance.monitoring.alerts import AlertGenerator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.scheduler import FalsifierScheduler

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_negative_ic,
        )
        alert_generator = AlertGenerator()

        scheduler = FalsifierScheduler(
            checker=checker,
            alert_generator=alert_generator,
        )

        results = scheduler.run_checks()

        # There should be triggered results
        triggered = [r for r in results if r.triggered]
        assert len(triggered) > 0

        # Alerts should have been generated
        alerts = alert_generator.get_alerts()
        assert len(alerts) > 0

    def test_scheduler_no_alerts_when_all_pass(self, hypothesis_registry, metric_registry):
        """run_checks should not generate alerts when all falsifiers pass."""
        from src.governance.monitoring.alerts import AlertGenerator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.scheduler import FalsifierScheduler

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry,
        )
        alert_generator = AlertGenerator()

        scheduler = FalsifierScheduler(
            checker=checker,
            alert_generator=alert_generator,
        )

        scheduler.run_checks()

        alerts = alert_generator.get_alerts()
        assert len(alerts) == 0

    def test_scheduler_calls_alert_delivery_handlers(
        self, hypothesis_registry, metric_registry_negative_ic
    ):
        """run_checks should deliver alerts through registered handlers."""
        from src.governance.monitoring.alerts import AlertGenerator
        from src.governance.monitoring.falsifier import FalsifierChecker
        from src.governance.monitoring.scheduler import FalsifierScheduler

        checker = FalsifierChecker(
            hypothesis_registry=hypothesis_registry,
            metric_registry=metric_registry_negative_ic,
        )
        alert_generator = AlertGenerator()

        delivered_alerts = []
        alert_generator.add_handler(lambda alert: delivered_alerts.append(alert))

        scheduler = FalsifierScheduler(
            checker=checker,
            alert_generator=alert_generator,
        )

        scheduler.run_checks()

        assert len(delivered_alerts) > 0


# =============================================================================
# Import/Export Tests
# =============================================================================


class TestMonitoringImports:
    """Tests for monitoring module imports."""

    def test_falsifier_check_result_importable(self):
        """FalsifierCheckResult should be importable from monitoring.models."""
        from src.governance.monitoring.models import FalsifierCheckResult

        assert FalsifierCheckResult is not None

    def test_metric_registry_importable(self):
        """MetricRegistry should be importable from monitoring.metrics."""
        from src.governance.monitoring.metrics import MetricRegistry

        assert MetricRegistry is not None

    def test_falsifier_checker_importable(self):
        """FalsifierChecker should be importable from monitoring.falsifier."""
        from src.governance.monitoring.falsifier import FalsifierChecker

        assert FalsifierChecker is not None

    def test_falsifier_scheduler_importable(self):
        """FalsifierScheduler should be importable from monitoring.scheduler."""
        from src.governance.monitoring.scheduler import FalsifierScheduler

        assert FalsifierScheduler is not None
