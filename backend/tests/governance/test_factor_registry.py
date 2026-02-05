"""Tests for Factor Registry with Failure Rules (T066-T071).

Tests cover:
- Factor and FactorFailureRule model validation (GovernanceBaseModel, extra=forbid)
- Factor loader from YAML with failure rule validation
- gate:factor_requires_failure_rule - reject factors without failure rules
- FactorRegistry with status tracking (enabled/disabled)
- Factor auto-disable when failure rule triggers
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError
from src.governance.factors.loader import FactorLoader
from src.governance.factors.models import Factor, FactorFailureRule, FactorStatus
from src.governance.factors.registry import DuplicateFactorError, FactorRegistry
from src.governance.models import ComparisonOperator
from src.governance.monitoring.metrics import MetricRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_failure_rule(**overrides) -> dict:
    """Return a valid FactorFailureRule dict with optional overrides."""
    defaults = {
        "metric": "rolling_ic_mean",
        "operator": "<",
        "threshold": 0.0,
        "window": "6m",
        "action": "disable",
    }
    defaults.update(overrides)
    return defaults


def _make_factor_dict(**overrides) -> dict:
    """Return a valid Factor dict with optional overrides."""
    defaults = {
        "id": "momentum_factor",
        "name": "Momentum Factor",
        "description": "Ranks stocks by recent return momentum",
        "hypothesis_ids": ["momentum_persistence"],
        "failure_rules": [_make_failure_rule()],
    }
    defaults.update(overrides)
    return defaults


def _make_factor(**overrides) -> Factor:
    """Create a validated Factor model."""
    return Factor.model_validate(_make_factor_dict(**overrides))


# ---------------------------------------------------------------------------
# T066 / T067: Model validation
# ---------------------------------------------------------------------------


class TestFactorFailureRuleModel:
    """Tests for FactorFailureRule Pydantic model."""

    def test_valid_failure_rule(self):
        rule = FactorFailureRule.model_validate(_make_failure_rule())
        assert rule.metric == "rolling_ic_mean"
        assert rule.operator == ComparisonOperator.LT
        assert rule.threshold == 0.0
        assert rule.window == "6m"
        assert rule.action == "disable"

    def test_review_action(self):
        rule = FactorFailureRule.model_validate(_make_failure_rule(action="review"))
        assert rule.action == "review"

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            FactorFailureRule.model_validate(_make_failure_rule(action="ignore"))

    def test_invalid_operator_rejected(self):
        with pytest.raises(ValidationError):
            FactorFailureRule.model_validate(_make_failure_rule(operator="!="))

    def test_extra_field_forbidden(self):
        """GovernanceBaseModel uses extra='forbid'."""
        with pytest.raises(ValidationError, match="extra"):
            FactorFailureRule.model_validate(_make_failure_rule(bogus="oops"))

    def test_missing_required_field(self):
        data = _make_failure_rule()
        del data["metric"]
        with pytest.raises(ValidationError):
            FactorFailureRule.model_validate(data)

    def test_all_comparison_operators(self):
        for op in ["<", "<=", ">", ">=", "=="]:
            rule = FactorFailureRule.model_validate(_make_failure_rule(operator=op))
            assert rule.operator.value == op


class TestFactorModel:
    """Tests for Factor Pydantic model."""

    def test_valid_factor(self):
        factor = _make_factor()
        assert factor.id == "momentum_factor"
        assert factor.name == "Momentum Factor"
        assert factor.status == FactorStatus.ENABLED
        assert factor.enabled is True
        assert len(factor.failure_rules) == 1

    def test_default_status_is_enabled(self):
        factor = _make_factor()
        assert factor.status == FactorStatus.ENABLED

    def test_default_enabled_is_true(self):
        factor = _make_factor()
        assert factor.enabled is True

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            _make_factor(secret_field="nope")

    def test_missing_id_rejected(self):
        data = _make_factor_dict()
        del data["id"]
        with pytest.raises(ValidationError):
            Factor.model_validate(data)

    def test_multiple_failure_rules(self):
        rules = [
            _make_failure_rule(metric="rolling_ic_mean", threshold=0.0),
            _make_failure_rule(metric="win_rate", operator="<", threshold=0.4),
        ]
        factor = _make_factor(failure_rules=rules)
        assert len(factor.failure_rules) == 2

    def test_multiple_hypothesis_ids(self):
        factor = _make_factor(hypothesis_ids=["h1", "h2", "h3"])
        assert factor.hypothesis_ids == ["h1", "h2", "h3"]

    def test_factor_status_enum_values(self):
        assert FactorStatus.ENABLED == "ENABLED"
        assert FactorStatus.DISABLED == "DISABLED"
        assert FactorStatus.REVIEW == "REVIEW"

    def test_factor_with_explicit_status(self):
        factor = _make_factor(status="DISABLED")
        assert factor.status == FactorStatus.DISABLED
        assert factor.enabled is True  # enabled is separate from status

    def test_factor_with_enabled_false(self):
        factor = _make_factor(enabled=False)
        assert factor.enabled is False


# ---------------------------------------------------------------------------
# T068 / T069: Loader and gate:factor_requires_failure_rule
# ---------------------------------------------------------------------------


class TestFactorLoader:
    """Tests for factor loading from YAML with failure rule validation."""

    def test_load_factor_from_dict(self):
        loader = FactorLoader()
        factor = loader.load_factor(_make_factor_dict())
        assert factor.id == "momentum_factor"
        assert len(factor.failure_rules) == 1

    def test_gate_factor_requires_failure_rule_empty_list(self):
        """gate:factor_requires_failure_rule - empty failure_rules raises ValueError."""
        loader = FactorLoader()
        data = _make_factor_dict(failure_rules=[])
        with pytest.raises(ValueError, match="factor_requires_failure_rule"):
            loader.load_factor(data)

    def test_gate_factor_requires_failure_rule_missing_key(self):
        """gate:factor_requires_failure_rule - missing failure_rules raises error."""
        loader = FactorLoader()
        data = _make_factor_dict()
        del data["failure_rules"]
        with pytest.raises((ValueError, ValidationError)):
            loader.load_factor(data)

    def test_load_factor_from_yaml_file(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            id: breakout_factor
            name: Breakout Factor
            description: Detects range breakouts
            hypothesis_ids:
              - range_breakout_theory
            failure_rules:
              - metric: win_rate
                operator: "<"
                threshold: 0.35
                window: 3m
                action: disable
        """)
        yaml_file = tmp_path / "breakout.yml"
        yaml_file.write_text(yaml_content)

        loader = FactorLoader()
        factors = loader.load_factors_from_yaml(str(yaml_file))
        assert len(factors) == 1
        assert factors[0].id == "breakout_factor"

    def test_load_factors_from_yaml_directory(self, tmp_path: Path):
        for name, fid in [("alpha.yml", "alpha_factor"), ("beta.yml", "beta_factor")]:
            content = textwrap.dedent(f"""\
                id: {fid}
                name: {fid.replace('_', ' ').title()}
                description: test factor
                hypothesis_ids: []
                failure_rules:
                  - metric: rolling_ic_mean
                    operator: "<"
                    threshold: 0.0
                    window: 6m
                    action: disable
            """)
            (tmp_path / name).write_text(content)

        loader = FactorLoader()
        factors = loader.load_factors_from_yaml(str(tmp_path))
        assert len(factors) == 2
        ids = {f.id for f in factors}
        assert ids == {"alpha_factor", "beta_factor"}

    def test_load_factors_skips_underscore_files(self, tmp_path: Path):
        content = textwrap.dedent("""\
            id: skip_me
            name: Skip Me
            description: should be skipped
            hypothesis_ids: []
            failure_rules:
              - metric: x
                operator: "<"
                threshold: 0.0
                window: 1m
                action: disable
        """)
        (tmp_path / "_example.yml").write_text(content)

        loader = FactorLoader()
        factors = loader.load_factors_from_yaml(str(tmp_path))
        assert len(factors) == 0

    def test_load_factor_yaml_with_no_failure_rules_raises(self, tmp_path: Path):
        yaml_content = textwrap.dedent("""\
            id: bad_factor
            name: Bad Factor
            description: Missing failure rules
            hypothesis_ids: []
            failure_rules: []
        """)
        yaml_file = tmp_path / "bad.yml"
        yaml_file.write_text(yaml_content)

        loader = FactorLoader()
        with pytest.raises(ValueError, match="factor_requires_failure_rule"):
            loader.load_factors_from_yaml(str(yaml_file))

    def test_load_nonexistent_file_raises(self):
        loader = FactorLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_factors_from_yaml("/nonexistent/path.yml")


# ---------------------------------------------------------------------------
# T070: FactorRegistry with status tracking
# ---------------------------------------------------------------------------


class TestFactorRegistry:
    """Tests for FactorRegistry with status tracking."""

    def test_register_and_get(self):
        registry = FactorRegistry()
        factor = _make_factor()
        registry.register(factor)
        result = registry.get(factor.id)
        assert result is not None
        assert result.id == factor.id

    def test_get_nonexistent_returns_none(self):
        registry = FactorRegistry()
        assert registry.get("nonexistent") is None

    def test_list_all(self):
        registry = FactorRegistry()
        f1 = _make_factor(id="f1", name="F1")
        f2 = _make_factor(id="f2", name="F2")
        registry.register(f1)
        registry.register(f2)
        all_factors = registry.list_all()
        assert len(all_factors) == 2

    def test_duplicate_registration_raises(self):
        registry = FactorRegistry()
        factor = _make_factor()
        registry.register(factor)
        with pytest.raises(DuplicateFactorError):
            registry.register(factor)

    def test_enable_disable(self):
        registry = FactorRegistry()
        factor = _make_factor()
        registry.register(factor)

        registry.disable_factor(factor.id)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.DISABLED
        assert f.enabled is False

        registry.enable_factor(factor.id)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.ENABLED
        assert f.enabled is True

    def test_disable_nonexistent_raises(self):
        registry = FactorRegistry()
        with pytest.raises(KeyError):
            registry.disable_factor("ghost")

    def test_enable_nonexistent_raises(self):
        registry = FactorRegistry()
        with pytest.raises(KeyError):
            registry.enable_factor("ghost")

    def test_set_review_status(self):
        registry = FactorRegistry()
        factor = _make_factor()
        registry.register(factor)
        registry.set_review(factor.id)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.REVIEW

    def test_get_enabled_factors(self):
        registry = FactorRegistry()
        f1 = _make_factor(id="f1", name="F1")
        f2 = _make_factor(id="f2", name="F2")
        registry.register(f1)
        registry.register(f2)
        registry.disable_factor("f2")

        enabled = registry.get_enabled()
        assert len(enabled) == 1
        assert enabled[0].id == "f1"

    def test_count(self):
        registry = FactorRegistry()
        assert registry.count() == 0
        registry.register(_make_factor(id="f1", name="F1"))
        assert registry.count() == 1

    def test_unregister(self):
        registry = FactorRegistry()
        factor = _make_factor()
        registry.register(factor)
        assert registry.unregister(factor.id) is True
        assert registry.get(factor.id) is None
        assert registry.unregister(factor.id) is False


# ---------------------------------------------------------------------------
# T070 continued: Factor auto-disable when failure rule triggers
# ---------------------------------------------------------------------------


class TestFactorHealthCheck:
    """Tests for factor health check and auto-disable."""

    def _setup_registry_and_metrics(self):
        registry = FactorRegistry()
        metric_registry = MetricRegistry()
        return registry, metric_registry

    def test_healthy_factor_stays_enabled(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(
            failure_rules=[
                _make_failure_rule(metric="rolling_ic_mean", operator="<", threshold=0.0)
            ]
        )
        registry.register(factor)
        # IC is positive -> not triggered
        metrics.register("rolling_ic_mean", lambda window=None: 0.05)

        results = registry.check_factor_health(factor.id, metrics)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.ENABLED
        assert all(not r.triggered for r in results)

    def test_auto_disable_on_failure_rule_trigger(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(
            failure_rules=[
                _make_failure_rule(
                    metric="rolling_ic_mean",
                    operator="<",
                    threshold=0.0,
                    action="disable",
                )
            ]
        )
        registry.register(factor)
        # IC is negative -> triggered
        metrics.register("rolling_ic_mean", lambda window=None: -0.05)

        results = registry.check_factor_health(factor.id, metrics)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.DISABLED
        assert f.enabled is False
        assert any(r.triggered for r in results)

    def test_review_action_sets_review_status(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(
            failure_rules=[
                _make_failure_rule(
                    metric="win_rate",
                    operator="<",
                    threshold=0.4,
                    action="review",
                )
            ]
        )
        registry.register(factor)
        metrics.register("win_rate", lambda window=None: 0.3)

        registry.check_factor_health(factor.id, metrics)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.REVIEW

    def test_missing_metric_does_not_trigger(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(failure_rules=[_make_failure_rule(metric="nonexistent_metric")])
        registry.register(factor)
        # No metric registered -> should not trigger

        results = registry.check_factor_health(factor.id, metrics)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.ENABLED
        assert all(not r.triggered for r in results)

    def test_multiple_rules_first_disable_wins(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(
            failure_rules=[
                _make_failure_rule(
                    metric="rolling_ic_mean", operator="<", threshold=0.0, action="review"
                ),
                _make_failure_rule(
                    metric="win_rate", operator="<", threshold=0.4, action="disable"
                ),
            ]
        )
        registry.register(factor)
        metrics.register("rolling_ic_mean", lambda window=None: -0.05)
        metrics.register("win_rate", lambda window=None: 0.3)

        registry.check_factor_health(factor.id, metrics)
        f = registry.get(factor.id)
        assert f is not None
        # disable is stronger than review
        assert f.status == FactorStatus.DISABLED
        assert f.enabled is False

    def test_check_nonexistent_factor_raises(self):
        registry, metrics = self._setup_registry_and_metrics()
        with pytest.raises(KeyError):
            registry.check_factor_health("ghost", metrics)

    def test_health_check_returns_results(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(
            failure_rules=[
                _make_failure_rule(metric="rolling_ic_mean", operator="<", threshold=0.0),
                _make_failure_rule(metric="win_rate", operator="<", threshold=0.4),
            ]
        )
        registry.register(factor)
        metrics.register("rolling_ic_mean", lambda window=None: 0.05)
        metrics.register("win_rate", lambda window=None: 0.5)

        results = registry.check_factor_health(factor.id, metrics)
        assert len(results) == 2
        assert all(not r.triggered for r in results)

    def test_gte_operator_triggers_correctly(self):
        registry, metrics = self._setup_registry_and_metrics()
        factor = _make_factor(
            failure_rules=[
                _make_failure_rule(
                    metric="max_drawdown", operator=">=", threshold=0.2, action="disable"
                )
            ]
        )
        registry.register(factor)
        metrics.register("max_drawdown", lambda window=None: 0.25)

        registry.check_factor_health(factor.id, metrics)
        f = registry.get(factor.id)
        assert f is not None
        assert f.status == FactorStatus.DISABLED
