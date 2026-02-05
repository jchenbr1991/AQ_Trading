"""Integration tests for GovernanceContext strategy interface (T077-T080).

Tests verify:
- GovernanceContext can be created with pool, regime, risk/timing scalars
- GovernanceContext does NOT expose raw Constraint objects (only scalar values)
- GovernanceContext provides: active_pool, pacing_multiplier, risk_budget_multiplier,
  veto_downgrade_active, stop_mode
- GovernanceContext is immutable (frozen=True)
- build_governance_context() assembles context from governance components
- GET /governance/context/{symbol} endpoint returns a GovernanceContext
"""

from __future__ import annotations

import types
from typing import get_type_hints

import pytest
from pydantic import ValidationError
from src.governance.constraints.models import (
    Constraint,
    ConstraintGuardrails,
    ResolvedAction,
    ResolvedConstraints,
)
from src.governance.context import GovernanceContext, build_governance_context
from src.governance.hypothesis.models import Hypothesis
from src.governance.models import GovernanceBaseModel

# =============================================================================
# T077: GovernanceContext creation and field tests
# =============================================================================


class TestGovernanceContextCreation:
    """Test GovernanceContext can be created with expected fields."""

    def test_create_with_all_fields(self):
        """GovernanceContext can be created with all fields specified."""
        ctx = GovernanceContext(
            active_pool=["AAPL", "NVDA", "AMD"],
            pacing_multiplier=0.5,
            risk_budget_multiplier=1.5,
            veto_downgrade_active=True,
            stop_mode="wide",
            pool_version="20260204_abc123",
            regime_state="TRANSITION",
        )

        assert ctx.active_pool == ["AAPL", "NVDA", "AMD"]
        assert ctx.pacing_multiplier == 0.5
        assert ctx.risk_budget_multiplier == 1.5
        assert ctx.veto_downgrade_active is True
        assert ctx.stop_mode == "wide"
        assert ctx.pool_version == "20260204_abc123"
        assert ctx.regime_state == "TRANSITION"

    def test_create_with_defaults(self):
        """GovernanceContext can be created with defaults for optional fields."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="20260204_000000000000",
            regime_state="NORMAL",
        )

        assert ctx.stop_mode == "baseline"
        assert ctx.veto_downgrade_active is False
        assert ctx.risk_budget_multiplier == 1.0
        assert ctx.pacing_multiplier == 1.0

    def test_create_empty_pool(self):
        """GovernanceContext can be created with empty pool."""
        ctx = GovernanceContext(
            active_pool=[],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="20260204_000000000000",
            regime_state="NORMAL",
        )

        assert ctx.active_pool == []

    def test_provides_active_pool(self):
        """GovernanceContext provides active_pool as list[str]."""
        ctx = GovernanceContext(
            active_pool=["AAPL", "NVDA"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="v1",
            regime_state="NORMAL",
        )
        assert isinstance(ctx.active_pool, list)
        assert all(isinstance(s, str) for s in ctx.active_pool)

    def test_provides_pacing_multiplier(self):
        """GovernanceContext provides pacing_multiplier as float."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=0.5,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="v1",
            regime_state="NORMAL",
        )
        assert isinstance(ctx.pacing_multiplier, float)

    def test_provides_risk_budget_multiplier(self):
        """GovernanceContext provides risk_budget_multiplier as float."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=2.0,
            veto_downgrade_active=False,
            pool_version="v1",
            regime_state="NORMAL",
        )
        assert isinstance(ctx.risk_budget_multiplier, float)

    def test_provides_veto_downgrade_active(self):
        """GovernanceContext provides veto_downgrade_active as bool."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=True,
            pool_version="v1",
            regime_state="NORMAL",
        )
        assert isinstance(ctx.veto_downgrade_active, bool)

    def test_provides_stop_mode(self):
        """GovernanceContext provides stop_mode as str."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            stop_mode="fundamental_guarded",
            pool_version="v1",
            regime_state="NORMAL",
        )
        assert isinstance(ctx.stop_mode, str)
        assert ctx.stop_mode == "fundamental_guarded"

    def test_provides_pool_version(self):
        """GovernanceContext provides pool_version as str."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="20260204_abcdef123456",
            regime_state="NORMAL",
        )
        assert isinstance(ctx.pool_version, str)

    def test_provides_regime_state(self):
        """GovernanceContext provides regime_state as str."""
        ctx = GovernanceContext(
            active_pool=["AAPL"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="v1",
            regime_state="STRESS",
        )
        assert isinstance(ctx.regime_state, str)
        assert ctx.regime_state == "STRESS"


# =============================================================================
# T077 + T079: Immutability tests
# =============================================================================


class TestGovernanceContextImmutability:
    """Test GovernanceContext is frozen (immutable)."""

    def _make_ctx(self) -> GovernanceContext:
        return GovernanceContext(
            active_pool=["AAPL", "NVDA"],
            pacing_multiplier=1.0,
            risk_budget_multiplier=1.0,
            veto_downgrade_active=False,
            pool_version="v1",
            regime_state="NORMAL",
        )

    def test_cannot_set_active_pool(self):
        """Cannot mutate active_pool after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.active_pool = ["NEW"]

    def test_cannot_set_pacing_multiplier(self):
        """Cannot mutate pacing_multiplier after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.pacing_multiplier = 0.1

    def test_cannot_set_risk_budget_multiplier(self):
        """Cannot mutate risk_budget_multiplier after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.risk_budget_multiplier = 2.0

    def test_cannot_set_veto_downgrade_active(self):
        """Cannot mutate veto_downgrade_active after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.veto_downgrade_active = True

    def test_cannot_set_stop_mode(self):
        """Cannot mutate stop_mode after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.stop_mode = "wide"

    def test_cannot_set_pool_version(self):
        """Cannot mutate pool_version after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.pool_version = "v2"

    def test_cannot_set_regime_state(self):
        """Cannot mutate regime_state after creation."""
        ctx = self._make_ctx()
        with pytest.raises(ValidationError):
            ctx.regime_state = "STRESS"

    def test_cannot_add_new_field(self):
        """Cannot add new fields to a frozen model (extra=forbid)."""
        with pytest.raises(ValidationError):
            GovernanceContext(
                active_pool=["AAPL"],
                pacing_multiplier=1.0,
                risk_budget_multiplier=1.0,
                veto_downgrade_active=False,
                pool_version="v1",
                regime_state="NORMAL",
                unknown_field="should_fail",
            )


# =============================================================================
# T079: No raw governance domain objects exposed
# =============================================================================


class TestGovernanceContextNoRawObjects:
    """Test GovernanceContext does NOT expose raw Constraint/Hypothesis objects."""

    def test_no_constraint_fields(self):
        """GovernanceContext has no Constraint type in its field annotations."""
        hints = get_type_hints(GovernanceContext)
        for field_name, field_type in hints.items():
            # Check that no field type is or contains Constraint
            assert not _type_contains(
                field_type, Constraint
            ), f"Field '{field_name}' exposes raw Constraint type"

    def test_no_hypothesis_fields(self):
        """GovernanceContext has no Hypothesis type in its field annotations."""
        hints = get_type_hints(GovernanceContext)
        for field_name, field_type in hints.items():
            assert not _type_contains(
                field_type, Hypothesis
            ), f"Field '{field_name}' exposes raw Hypothesis type"

    def test_no_resolved_constraints_fields(self):
        """GovernanceContext has no ResolvedConstraints type in its field annotations."""
        hints = get_type_hints(GovernanceContext)
        for field_name, field_type in hints.items():
            assert not _type_contains(
                field_type, ResolvedConstraints
            ), f"Field '{field_name}' exposes raw ResolvedConstraints type"

    def test_no_resolved_action_fields(self):
        """GovernanceContext has no ResolvedAction type in its field annotations."""
        hints = get_type_hints(GovernanceContext)
        for field_name, field_type in hints.items():
            assert not _type_contains(
                field_type, ResolvedAction
            ), f"Field '{field_name}' exposes raw ResolvedAction type"

    def test_no_constraint_guardrails_fields(self):
        """GovernanceContext has no ConstraintGuardrails type in its field annotations."""
        hints = get_type_hints(GovernanceContext)
        for field_name, field_type in hints.items():
            assert not _type_contains(
                field_type, ConstraintGuardrails
            ), f"Field '{field_name}' exposes raw ConstraintGuardrails type"

    def test_all_fields_are_scalars_or_simple_types(self):
        """All GovernanceContext field values are str, float, bool, or list[str]."""
        ctx = GovernanceContext(
            active_pool=["AAPL", "NVDA"],
            pacing_multiplier=0.5,
            risk_budget_multiplier=1.5,
            veto_downgrade_active=True,
            stop_mode="wide",
            pool_version="v1",
            regime_state="TRANSITION",
        )

        for field_name in GovernanceContext.model_fields:
            value = getattr(ctx, field_name)
            assert isinstance(
                value, str | float | int | bool | list
            ), f"Field '{field_name}' has non-scalar value type: {type(value)}"
            if isinstance(value, list):
                assert all(
                    isinstance(item, str) for item in value
                ), f"Field '{field_name}' list contains non-str items"

    def test_extends_governance_base_model(self):
        """GovernanceContext inherits from GovernanceBaseModel."""
        assert issubclass(GovernanceContext, GovernanceBaseModel)


# =============================================================================
# T080: build_governance_context() function tests
# =============================================================================


class TestBuildGovernanceContext:
    """Test build_governance_context() assembles context from components."""

    @pytest.fixture(autouse=True)
    def _reset_singletons(self):
        """Reset governance singletons before each test for isolation."""
        from src.api.routes.governance import (
            reset_constraint_registry,
            reset_hypothesis_registry,
            reset_metric_registry,
            reset_regime_detector,
        )

        reset_regime_detector()
        reset_metric_registry()
        reset_constraint_registry()
        reset_hypothesis_registry()
        yield
        reset_regime_detector()
        reset_metric_registry()
        reset_constraint_registry()
        reset_hypothesis_registry()

    def test_returns_governance_context(self):
        """build_governance_context returns a GovernanceContext instance."""
        ctx = build_governance_context(symbol="AAPL")
        assert isinstance(ctx, GovernanceContext)

    def test_returns_sensible_defaults_no_config(self):
        """build_governance_context returns sensible defaults when no components configured."""
        ctx = build_governance_context(symbol="AAPL")
        assert isinstance(ctx.active_pool, list)
        assert isinstance(ctx.pacing_multiplier, float)
        assert isinstance(ctx.risk_budget_multiplier, float)
        assert isinstance(ctx.veto_downgrade_active, bool)
        assert isinstance(ctx.stop_mode, str)
        assert isinstance(ctx.pool_version, str)
        assert isinstance(ctx.regime_state, str)

    def test_default_pacing_multiplier_is_one(self):
        """Default pacing_multiplier is 1.0 (NORMAL regime)."""
        ctx = build_governance_context(symbol="AAPL")
        assert ctx.pacing_multiplier == 1.0

    def test_default_risk_budget_multiplier_is_one(self):
        """Default risk_budget_multiplier is 1.0 (no constraints)."""
        ctx = build_governance_context(symbol="AAPL")
        assert ctx.risk_budget_multiplier == 1.0

    def test_default_veto_downgrade_is_false(self):
        """Default veto_downgrade_active is False."""
        ctx = build_governance_context(symbol="AAPL")
        assert ctx.veto_downgrade_active is False

    def test_default_stop_mode_is_baseline(self):
        """Default stop_mode is 'baseline'."""
        ctx = build_governance_context(symbol="AAPL")
        assert ctx.stop_mode == "baseline"

    def test_default_regime_state_is_normal(self):
        """Default regime_state is 'NORMAL'."""
        ctx = build_governance_context(symbol="AAPL")
        assert ctx.regime_state == "NORMAL"

    def test_context_is_immutable(self):
        """Returned context is immutable."""
        ctx = build_governance_context(symbol="AAPL")
        with pytest.raises(ValidationError):
            ctx.pacing_multiplier = 0.5

    def test_result_is_serializable(self):
        """GovernanceContext can be serialized to dict/JSON."""
        ctx = build_governance_context(symbol="AAPL")
        data = ctx.model_dump()
        assert isinstance(data, dict)
        assert "active_pool" in data
        assert "pacing_multiplier" in data
        assert "risk_budget_multiplier" in data
        assert "veto_downgrade_active" in data
        assert "stop_mode" in data
        assert "pool_version" in data
        assert "regime_state" in data


# =============================================================================
# T080: API endpoint test
# =============================================================================


class TestGovernanceContextEndpoint:
    """Test GET /governance/context/{symbol} endpoint."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        from fastapi.testclient import TestClient
        from src.main import app

        return TestClient(app)

    def test_get_context_returns_200(self, client):
        """GET /governance/context/{symbol} returns 200."""
        response = client.get("/api/governance/context/AAPL")
        assert response.status_code == 200

    def test_get_context_returns_valid_json(self, client):
        """GET /governance/context/{symbol} returns valid JSON with expected fields."""
        response = client.get("/api/governance/context/AAPL")
        data = response.json()
        assert "active_pool" in data
        assert "pacing_multiplier" in data
        assert "risk_budget_multiplier" in data
        assert "veto_downgrade_active" in data
        assert "stop_mode" in data
        assert "pool_version" in data
        assert "regime_state" in data

    def test_get_context_field_types(self, client):
        """GET /governance/context/{symbol} returns correct types."""
        response = client.get("/api/governance/context/NVDA")
        data = response.json()
        assert isinstance(data["active_pool"], list)
        assert isinstance(data["pacing_multiplier"], float)
        assert isinstance(data["risk_budget_multiplier"], float)
        assert isinstance(data["veto_downgrade_active"], bool)
        assert isinstance(data["stop_mode"], str)
        assert isinstance(data["pool_version"], str)
        assert isinstance(data["regime_state"], str)

    def test_get_context_different_symbols(self, client):
        """GET /governance/context works for different symbols."""
        for symbol in ["AAPL", "NVDA", "AMD", "NONEXISTENT"]:
            response = client.get(f"/api/governance/context/{symbol}")
            assert response.status_code == 200


# =============================================================================
# Helper: Check if a type annotation contains a given class
# =============================================================================


def _type_contains(type_hint, target_class: type) -> bool:
    """Check if a type hint contains a reference to the target class.

    Handles Optional, Union, list[], dict[], and other generic aliases.
    """
    # Direct match
    if type_hint is target_class:
        return True

    # Get origin and args for generic types (list[X], Optional[X], etc.)
    origin = getattr(type_hint, "__origin__", None)
    args = getattr(type_hint, "__args__", ())

    if origin is not None and args:
        for arg in args:
            if _type_contains(arg, target_class):
                return True

    # Handle Union (including Optional)
    if isinstance(type_hint, types.UnionType):
        for arg in type_hint.__args__:
            if _type_contains(arg, target_class):
                return True

    return False
