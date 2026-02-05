"""Tests for regime-based position pacing (T072-T076).

TDD: Write tests FIRST, then implement to make them pass.

This module tests:
1. RegimeThresholds and RegimeConfig model validation (GovernanceBaseModel, extra=forbid)
2. RegimeDetector that evaluates market conditions against thresholds
3. Regime transitions: NORMAL -> TRANSITION -> STRESS and back
4. Position pacing multipliers per regime state
5. Edge cases: missing metrics, boundary thresholds
6. RegimeSnapshot model validation
7. API endpoint GET /governance/regime
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

# =============================================================================
# Model Tests - RegimeThresholds
# =============================================================================


class TestRegimeThresholds:
    """Tests for RegimeThresholds model."""

    def test_valid_thresholds(self):
        """RegimeThresholds accepts valid threshold values."""
        from src.governance.regime.models import RegimeThresholds

        thresholds = RegimeThresholds(
            volatility_transition=0.25,
            volatility_stress=0.40,
            drawdown_transition=0.10,
            drawdown_stress=0.20,
        )
        assert thresholds.volatility_transition == 0.25
        assert thresholds.volatility_stress == 0.40
        assert thresholds.drawdown_transition == 0.10
        assert thresholds.drawdown_stress == 0.20

    def test_forbids_extra_fields(self):
        """RegimeThresholds inherits GovernanceBaseModel extra=forbid."""
        from src.governance.regime.models import RegimeThresholds

        with pytest.raises(ValidationError) as exc_info:
            RegimeThresholds(
                volatility_transition=0.25,
                volatility_stress=0.40,
                drawdown_transition=0.10,
                drawdown_stress=0.20,
                unknown_field=0.5,
            )
        assert "unknown_field" in str(exc_info.value)

    def test_requires_all_fields(self):
        """RegimeThresholds requires all four threshold fields."""
        from src.governance.regime.models import RegimeThresholds

        with pytest.raises(ValidationError):
            RegimeThresholds(
                volatility_transition=0.25,
                # Missing volatility_stress, drawdown_transition, drawdown_stress
            )


# =============================================================================
# Model Tests - RegimeConfig
# =============================================================================


class TestRegimeConfig:
    """Tests for RegimeConfig model."""

    def test_valid_config(self):
        """RegimeConfig accepts valid threshold and pacing configuration."""
        from src.governance.regime.models import RegimeConfig, RegimeThresholds

        config = RegimeConfig(
            thresholds=RegimeThresholds(
                volatility_transition=0.25,
                volatility_stress=0.40,
                drawdown_transition=0.10,
                drawdown_stress=0.20,
            ),
            pacing_multipliers={
                "NORMAL": 1.0,
                "TRANSITION": 0.5,
                "STRESS": 0.1,
            },
        )
        assert config.pacing_multipliers["NORMAL"] == 1.0
        assert config.pacing_multipliers["TRANSITION"] == 0.5
        assert config.pacing_multipliers["STRESS"] == 0.1

    def test_forbids_extra_fields(self):
        """RegimeConfig inherits GovernanceBaseModel extra=forbid."""
        from src.governance.regime.models import RegimeConfig, RegimeThresholds

        with pytest.raises(ValidationError) as exc_info:
            RegimeConfig(
                thresholds=RegimeThresholds(
                    volatility_transition=0.25,
                    volatility_stress=0.40,
                    drawdown_transition=0.10,
                    drawdown_stress=0.20,
                ),
                pacing_multipliers={"NORMAL": 1.0},
                extra_field="bad",
            )
        assert "extra_field" in str(exc_info.value)


# =============================================================================
# Model Tests - RegimeSnapshot
# =============================================================================


class TestRegimeSnapshot:
    """Tests for RegimeSnapshot model."""

    def test_valid_snapshot(self):
        """RegimeSnapshot accepts valid state and metrics."""
        from src.governance.models import RegimeState
        from src.governance.regime.models import RegimeSnapshot

        now = datetime.utcnow()
        snapshot = RegimeSnapshot(
            state=RegimeState.NORMAL,
            previous_state=None,
            changed_at=now,
            metrics={"portfolio_volatility": 0.15, "max_drawdown": 0.05},
            pacing_multiplier=1.0,
        )
        assert snapshot.state == RegimeState.NORMAL
        assert snapshot.previous_state is None
        assert snapshot.pacing_multiplier == 1.0

    def test_snapshot_with_previous_state(self):
        """RegimeSnapshot tracks previous state for transitions."""
        from src.governance.models import RegimeState
        from src.governance.regime.models import RegimeSnapshot

        snapshot = RegimeSnapshot(
            state=RegimeState.STRESS,
            previous_state=RegimeState.TRANSITION,
            changed_at=datetime.utcnow(),
            metrics={"portfolio_volatility": 0.50, "max_drawdown": 0.25},
            pacing_multiplier=0.1,
        )
        assert snapshot.state == RegimeState.STRESS
        assert snapshot.previous_state == RegimeState.TRANSITION

    def test_forbids_extra_fields(self):
        """RegimeSnapshot inherits GovernanceBaseModel extra=forbid."""
        from src.governance.models import RegimeState
        from src.governance.regime.models import RegimeSnapshot

        with pytest.raises(ValidationError) as exc_info:
            RegimeSnapshot(
                state=RegimeState.NORMAL,
                previous_state=None,
                changed_at=datetime.utcnow(),
                metrics={},
                pacing_multiplier=1.0,
                extra="bad",
            )
        assert "extra" in str(exc_info.value)


# =============================================================================
# RegimeDetector Tests
# =============================================================================


class TestRegimeDetectorFixtures:
    """Shared fixtures for RegimeDetector tests."""

    @pytest.fixture
    def default_config(self):
        """Create default regime config for testing."""
        from src.governance.regime.models import RegimeConfig, RegimeThresholds

        return RegimeConfig(
            thresholds=RegimeThresholds(
                volatility_transition=0.25,
                volatility_stress=0.40,
                drawdown_transition=0.10,
                drawdown_stress=0.20,
            ),
            pacing_multipliers={
                "NORMAL": 1.0,
                "TRANSITION": 0.5,
                "STRESS": 0.1,
            },
        )

    @pytest.fixture
    def metric_registry(self):
        """Create a fresh MetricRegistry for testing."""
        from src.governance.monitoring.metrics import MetricRegistry

        return MetricRegistry()

    @pytest.fixture
    def detector(self, default_config, metric_registry):
        """Create a RegimeDetector with default config."""
        from src.governance.regime.detector import RegimeDetector

        return RegimeDetector(config=default_config, metric_registry=metric_registry)


class TestRegimeDetectorNormalState(TestRegimeDetectorFixtures):
    """Tests for NORMAL regime detection."""

    def test_normal_when_metrics_below_thresholds(self, detector, metric_registry):
        """Detector returns NORMAL when all metrics are below transition thresholds."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"
        assert snapshot.pacing_multiplier == 1.0

    def test_normal_pacing_multiplier(self, detector, metric_registry):
        """NORMAL regime should have pacing multiplier of 1.0."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.10)
        metric_registry.register("max_drawdown", lambda window=None: 0.02)

        snapshot = detector.detect()

        assert snapshot.pacing_multiplier == 1.0

    def test_normal_metrics_are_captured(self, detector, metric_registry):
        """Detected snapshot should capture current metric values."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.metrics["portfolio_volatility"] == 0.15
        assert snapshot.metrics["max_drawdown"] == 0.05


class TestRegimeDetectorTransitionState(TestRegimeDetectorFixtures):
    """Tests for TRANSITION regime detection."""

    def test_transition_on_high_volatility(self, detector, metric_registry):
        """Detector returns TRANSITION when volatility >= transition threshold."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.30)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "TRANSITION"
        assert snapshot.pacing_multiplier == 0.5

    def test_transition_on_high_drawdown(self, detector, metric_registry):
        """Detector returns TRANSITION when drawdown >= transition threshold."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.12)

        snapshot = detector.detect()

        assert snapshot.state.value == "TRANSITION"
        assert snapshot.pacing_multiplier == 0.5

    def test_transition_on_both_metrics(self, detector, metric_registry):
        """TRANSITION when both metrics at transition level (but not stress)."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.30)
        metric_registry.register("max_drawdown", lambda window=None: 0.15)

        snapshot = detector.detect()

        assert snapshot.state.value == "TRANSITION"


class TestRegimeDetectorStressState(TestRegimeDetectorFixtures):
    """Tests for STRESS regime detection."""

    def test_stress_on_high_volatility(self, detector, metric_registry):
        """Detector returns STRESS when volatility >= stress threshold."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.45)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "STRESS"
        assert snapshot.pacing_multiplier == 0.1

    def test_stress_on_high_drawdown(self, detector, metric_registry):
        """Detector returns STRESS when drawdown >= stress threshold."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.25)

        snapshot = detector.detect()

        assert snapshot.state.value == "STRESS"
        assert snapshot.pacing_multiplier == 0.1

    def test_stress_overrides_transition(self, detector, metric_registry):
        """STRESS takes priority over TRANSITION (volatility at stress, drawdown at transition)."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.45)
        metric_registry.register("max_drawdown", lambda window=None: 0.12)

        snapshot = detector.detect()

        assert snapshot.state.value == "STRESS"


# =============================================================================
# Regime Transition Tracking Tests
# =============================================================================


class TestRegimeTransitions(TestRegimeDetectorFixtures):
    """Tests for regime state transitions and history tracking."""

    def test_initial_detect_has_no_previous_state(self, detector, metric_registry):
        """First detection should have previous_state=None."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.previous_state is None

    def test_transition_from_normal_to_stress(self, detector, metric_registry):
        """Transition from NORMAL to STRESS tracks previous state."""
        # First: NORMAL
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)
        detector.detect()

        # Then: STRESS
        metric_registry.register("portfolio_volatility", lambda window=None: 0.50)
        metric_registry.register("max_drawdown", lambda window=None: 0.25)
        snapshot = detector.detect()

        assert snapshot.state.value == "STRESS"
        assert snapshot.previous_state is not None
        assert snapshot.previous_state.value == "NORMAL"

    def test_transition_from_stress_back_to_normal(self, detector, metric_registry):
        """Recovery: STRESS -> NORMAL tracks previous state."""
        # First: STRESS
        metric_registry.register("portfolio_volatility", lambda window=None: 0.50)
        metric_registry.register("max_drawdown", lambda window=None: 0.25)
        detector.detect()

        # Then: NORMAL
        metric_registry.register("portfolio_volatility", lambda window=None: 0.10)
        metric_registry.register("max_drawdown", lambda window=None: 0.03)
        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"
        assert snapshot.previous_state.value == "STRESS"

    def test_no_change_keeps_previous_state(self, detector, metric_registry):
        """When state doesn't change, previous_state reflects prior state."""
        # First: NORMAL
        metric_registry.register("portfolio_volatility", lambda window=None: 0.10)
        metric_registry.register("max_drawdown", lambda window=None: 0.03)
        detector.detect()

        # Second: still NORMAL
        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"
        assert snapshot.previous_state.value == "NORMAL"

    def test_changed_at_is_set(self, detector, metric_registry):
        """Snapshot should have a valid changed_at timestamp."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        before = datetime.utcnow()
        snapshot = detector.detect()
        after = datetime.utcnow()

        assert before <= snapshot.changed_at <= after


# =============================================================================
# Edge Cases
# =============================================================================


class TestRegimeDetectorEdgeCases(TestRegimeDetectorFixtures):
    """Tests for edge cases in regime detection."""

    def test_missing_volatility_metric_defaults_normal(self, detector, metric_registry):
        """When portfolio_volatility metric is missing, treat as 0 (NORMAL)."""
        # Only register drawdown, not volatility
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"
        assert snapshot.pacing_multiplier == 1.0

    def test_missing_drawdown_metric_defaults_normal(self, detector, metric_registry):
        """When max_drawdown metric is missing, treat as 0 (NORMAL)."""
        # Only register volatility, not drawdown
        metric_registry.register("portfolio_volatility", lambda window=None: 0.15)

        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"

    def test_no_metrics_registered_defaults_normal(self, detector):
        """When no metrics are registered, default to NORMAL."""
        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"
        assert snapshot.pacing_multiplier == 1.0

    def test_boundary_exactly_at_transition_threshold(self, detector, metric_registry):
        """Exactly at transition threshold should be TRANSITION."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.25)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "TRANSITION"

    def test_boundary_exactly_at_stress_threshold(self, detector, metric_registry):
        """Exactly at stress threshold should be STRESS."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.40)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "STRESS"

    def test_boundary_drawdown_at_stress(self, detector, metric_registry):
        """Drawdown exactly at stress threshold should be STRESS."""
        metric_registry.register("portfolio_volatility", lambda window=None: 0.10)
        metric_registry.register("max_drawdown", lambda window=None: 0.20)

        snapshot = detector.detect()

        assert snapshot.state.value == "STRESS"

    def test_metric_returns_none_defaults_zero(self, detector, metric_registry):
        """If a metric provider returns None, treat as 0."""
        metric_registry.register("portfolio_volatility", lambda window=None: None)
        metric_registry.register("max_drawdown", lambda window=None: 0.05)

        snapshot = detector.detect()

        assert snapshot.state.value == "NORMAL"


# =============================================================================
# API Endpoint Tests
# =============================================================================


class TestRegimeAPIEndpoint:
    """Tests for GET /governance/regime endpoint."""

    @pytest.fixture
    def app(self):
        """Create a FastAPI app with the governance router."""
        from fastapi import FastAPI
        from src.api.routes.governance import (
            reset_audit_store,
            reset_constraint_registry,
            reset_hypothesis_registry,
            reset_metric_registry,
            reset_pool_builder,
            reset_regime_detector,
            router,
        )

        reset_hypothesis_registry()
        reset_constraint_registry()
        reset_pool_builder()
        reset_audit_store()
        reset_metric_registry()
        reset_regime_detector()

        app = FastAPI()
        app.include_router(router)
        return app

    @pytest.fixture
    def client(self, app):
        """Create a test client for the app."""
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_regime_endpoint_returns_200(self, client):
        """GET /governance/regime should return 200 with regime state."""
        response = client.get("/governance/regime")

        assert response.status_code == 200

    def test_regime_endpoint_default_normal(self, client):
        """With no metrics registered, regime should default to NORMAL."""
        response = client.get("/governance/regime")

        data = response.json()
        assert data["state"] == "NORMAL"
        assert data["pacing_multiplier"] == 1.0

    def test_regime_endpoint_returns_snapshot_fields(self, client):
        """Response should contain all RegimeSnapshot fields."""
        response = client.get("/governance/regime")

        data = response.json()
        assert "state" in data
        assert "previous_state" in data
        assert "changed_at" in data
        assert "metrics" in data
        assert "pacing_multiplier" in data

    def test_regime_endpoint_with_metrics(self, client):
        """Regime endpoint should detect state from registered metrics."""
        from src.api.routes.governance import get_metric_registry

        registry = get_metric_registry()
        registry.register("portfolio_volatility", lambda window=None: 0.50)
        registry.register("max_drawdown", lambda window=None: 0.25)

        response = client.get("/governance/regime")

        data = response.json()
        assert data["state"] == "STRESS"
        assert data["pacing_multiplier"] == 0.1
