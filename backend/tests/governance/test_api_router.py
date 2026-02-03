"""Tests for governance API router skeleton.

TDD: Write tests FIRST, then implement router to make them pass.

Tests cover all endpoints defined in the OpenAPI spec:
specs/003-hypothesis-constraints-system/contracts/openapi.yaml
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    """Create a FastAPI app with the governance router."""
    from src.api.routes.governance import (
        reset_constraint_registry,
        reset_hypothesis_registry,
        reset_pool_builder,
        router,
    )

    # Reset the singleton registries before each test
    reset_hypothesis_registry()
    reset_constraint_registry()
    reset_pool_builder()

    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create a test client for the app."""
    return TestClient(app)


class TestGovernanceRouter:
    """Tests for governance router registration."""

    def test_router_has_governance_prefix(self):
        """Router should have /governance prefix."""
        from src.api.routes.governance import router

        assert router.prefix == "/governance"

    def test_router_has_governance_tag(self):
        """Router should have 'governance' tag."""
        from src.api.routes.governance import router

        assert "governance" in router.tags


# =============================================================================
# Hypotheses Endpoints Tests
# =============================================================================


class TestHypothesesEndpoint:
    """Tests for /governance/hypotheses endpoint."""

    def test_list_hypotheses_returns_200(self, client):
        """GET /governance/hypotheses should return 200 with list of hypotheses."""
        response = client.get("/governance/hypotheses")

        assert response.status_code == 200
        # Response should be a list (may be empty if no hypotheses loaded)
        assert isinstance(response.json(), list)

    def test_list_hypotheses_with_status_filter(self, client):
        """GET /governance/hypotheses?status=ACTIVE should filter by status."""
        response = client.get("/governance/hypotheses?status=ACTIVE")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_hypotheses_with_invalid_status(self, client):
        """GET /governance/hypotheses?status=INVALID should return 422."""
        response = client.get("/governance/hypotheses?status=INVALID")

        assert response.status_code == 422  # Validation error


class TestGetHypothesisEndpoint:
    """Tests for /governance/hypotheses/{hypothesis_id} endpoint."""

    def test_get_hypothesis_returns_404_when_not_found(self, client):
        """GET /governance/hypotheses/{id} should return 404 if not found."""
        response = client.get("/governance/hypotheses/nonexistent_hypothesis")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_hypothesis_includes_id_in_404_message(self, client):
        """404 response should reference the hypothesis ID."""
        response = client.get("/governance/hypotheses/memory_demand_2027")

        assert response.status_code == 404
        assert "memory_demand_2027" in response.json()["detail"]


class TestCheckFalsifiersEndpoint:
    """Tests for /governance/hypotheses/{hypothesis_id}/falsifiers/check endpoint."""

    def test_check_falsifiers_returns_404_for_unknown(self, client):
        """POST /governance/hypotheses/{id}/falsifiers/check should return 404 for unknown hypothesis."""
        response = client.post("/governance/hypotheses/test_hypothesis/falsifiers/check")

        assert response.status_code == 404
        assert "test_hypothesis" in response.json()["detail"]

    def test_check_falsifiers_returns_404_includes_id(self, client):
        """Response should reference the hypothesis ID in the 404 error."""
        response = client.post("/governance/hypotheses/memory_demand_2027/falsifiers/check")

        assert response.status_code == 404
        assert "memory_demand_2027" in response.json()["detail"]


# =============================================================================
# Constraints Endpoints Tests (IMPLEMENTED - Phase 4)
# =============================================================================


class TestConstraintsEndpoint:
    """Tests for /governance/constraints endpoint."""

    def test_list_constraints_returns_200(self, client):
        """GET /governance/constraints should return 200 with list of constraints."""
        response = client.get("/governance/constraints")

        assert response.status_code == 200
        # Response should be a list (may be empty if no constraints loaded)
        assert isinstance(response.json(), list)

    def test_list_constraints_with_symbol_filter(self, client):
        """GET /governance/constraints?symbol=AAPL should filter by symbol."""
        response = client.get("/governance/constraints?symbol=AAPL")

        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_constraints_with_active_only_filter(self, client):
        """GET /governance/constraints?active_only=true should filter active constraints."""
        response = client.get("/governance/constraints?active_only=true")

        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestGetConstraintEndpoint:
    """Tests for /governance/constraints/{constraint_id} endpoint."""

    def test_get_constraint_returns_404_when_not_found(self, client):
        """GET /governance/constraints/{id} should return 404 if not found."""
        response = client.get("/governance/constraints/nonexistent_constraint")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_get_constraint_includes_id_in_404_message(self, client):
        """404 response should reference the constraint ID."""
        response = client.get("/governance/constraints/growth_leverage_guard")

        assert response.status_code == 404
        assert "growth_leverage_guard" in response.json()["detail"]


class TestResolveConstraintsEndpoint:
    """Tests for /governance/constraints/resolve/{symbol} endpoint."""

    def test_resolve_constraints_returns_200(self, client):
        """GET /governance/constraints/resolve/{symbol} should return 200."""
        response = client.get("/governance/constraints/resolve/AAPL")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "AAPL"
        assert "constraints" in data
        assert "resolved_at" in data
        assert "version" in data
        assert "effective_risk_budget_multiplier" in data
        assert "effective_pool_bias_multiplier" in data
        assert "effective_stop_mode" in data
        assert "veto_downgrade_active" in data

    def test_resolve_constraints_with_different_symbol(self, client):
        """GET /governance/constraints/resolve/{symbol} should work for any symbol."""
        response = client.get("/governance/constraints/resolve/NVDA")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "NVDA"


# =============================================================================
# Pool Endpoints Tests
# =============================================================================


class TestPoolEndpoint:
    """Tests for /governance/pool endpoint."""

    def test_get_pool_returns_404_when_no_pool_built(self, client):
        """GET /governance/pool should return 404 when no pool has been built."""
        response = client.get("/governance/pool")

        assert response.status_code == 404
        assert "no pool" in response.json()["detail"].lower()


class TestRebuildPoolEndpoint:
    """Tests for POST /governance/pool endpoint."""

    def test_rebuild_pool_returns_400_with_empty_universe(self, client):
        """POST /governance/pool should return 400 when base universe is empty."""
        response = client.post("/governance/pool")

        assert response.status_code == 400
        assert (
            "universe" in response.json()["detail"].lower()
            or "empty" in response.json()["detail"].lower()
        )


class TestSymbolAuditEndpoint:
    """Tests for /governance/pool/{symbol}/audit endpoint."""

    def test_get_symbol_audit_returns_404_when_no_pool(self, client):
        """GET /governance/pool/{symbol}/audit should return 404 when no pool built."""
        response = client.get("/governance/pool/AAPL/audit")

        assert response.status_code == 404
        assert "no pool" in response.json()["detail"].lower()

    def test_get_symbol_audit_returns_404_message(self, client):
        """Response should indicate no pool has been built."""
        response = client.get("/governance/pool/MSFT/audit")

        assert response.status_code == 404
        assert "pool" in response.json()["detail"].lower()


# =============================================================================
# Regime Endpoints Tests
# =============================================================================


class TestRegimeEndpoint:
    """Tests for /governance/regime endpoint."""

    def test_get_regime_returns_501(self, client):
        """GET /governance/regime should return 501 Not Implemented."""
        response = client.get("/governance/regime")

        assert response.status_code == 501
        assert "implemented" in response.json()["detail"].lower()


# =============================================================================
# Audit Endpoints Tests
# =============================================================================


class TestAuditEndpoint:
    """Tests for /governance/audit endpoint."""

    def test_query_audit_returns_501(self, client):
        """GET /governance/audit should return 501 Not Implemented."""
        response = client.get("/governance/audit")

        assert response.status_code == 501
        assert "implemented" in response.json()["detail"].lower()


# =============================================================================
# Lint/Gate Endpoints Tests (IMPLEMENTED - Phase 4)
# =============================================================================


class TestLintEndpoint:
    """Tests for /governance/lint/alpha-path endpoint."""

    def test_run_alpha_path_lint_returns_200(self, client):
        """POST /governance/lint/alpha-path should return 200 with LintResult."""
        response = client.post("/governance/lint/alpha-path")

        assert response.status_code == 200
        data = response.json()
        assert "passed" in data
        assert "violations" in data
        assert isinstance(data["violations"], list)

    def test_run_alpha_path_lint_has_passed_field(self, client):
        """Response should have a passed boolean field."""
        response = client.post("/governance/lint/alpha-path")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["passed"], bool)


class TestConstraintAllowlistLintEndpoint:
    """Tests for /governance/lint/constraint-allowlist endpoint."""

    def test_run_constraint_allowlist_lint_returns_200(self, client):
        """POST /governance/lint/constraint-allowlist should return 200."""
        response = client.post("/governance/lint/constraint-allowlist")

        assert response.status_code == 200
        data = response.json()
        assert "passed" in data
        assert "violations" in data
        assert isinstance(data["violations"], list)

    def test_run_constraint_allowlist_lint_has_passed_field(self, client):
        """Response should have a passed boolean field."""
        response = client.post("/governance/lint/constraint-allowlist")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["passed"], bool)


class TestGatesValidateEndpoint:
    """Tests for /governance/gates/validate endpoint."""

    def test_run_gates_returns_200(self, client):
        """POST /governance/gates/validate should return 200 with GateResult."""
        response = client.post("/governance/gates/validate")

        assert response.status_code == 200
        data = response.json()
        assert "passed" in data
        assert "gates" in data
        assert isinstance(data["gates"], list)

    def test_run_gates_has_gate_check_results(self, client):
        """Response should have gate check results with proper structure."""
        response = client.post("/governance/gates/validate")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["passed"], bool)

        for gate in data["gates"]:
            assert "gate_name" in gate
            assert "passed" in gate
            assert "violations" in gate
            assert isinstance(gate["violations"], list)


# =============================================================================
# Export Tests
# =============================================================================


class TestAllExports:
    """Test that router and helpers are exported."""

    def test_router_is_exported(self):
        """Router should be importable."""
        from src.api.routes.governance import router

        assert router is not None

    def test_hypothesis_registry_helpers_exported(self):
        """Hypothesis registry helpers should be importable."""
        from src.api.routes.governance import (
            get_hypothesis_registry,
            reset_hypothesis_registry,
        )

        assert get_hypothesis_registry is not None
        assert reset_hypothesis_registry is not None

    def test_constraint_registry_helpers_exported(self):
        """Constraint registry helpers should be importable."""
        from src.api.routes.governance import (
            get_constraint_registry,
            get_constraint_resolver,
            reset_constraint_registry,
        )

        assert get_constraint_registry is not None
        assert get_constraint_resolver is not None
        assert reset_constraint_registry is not None
