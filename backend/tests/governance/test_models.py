"""Tests for governance base models and enums.

TDD: Write tests FIRST, then implement models to make them pass.
"""

import pytest
from pydantic import ValidationError


class TestGovernanceBaseModel:
    """Tests for GovernanceBaseModel base class."""

    def test_base_model_forbids_extra_fields(self):
        """GovernanceBaseModel should reject extra fields."""
        from src.governance.models import GovernanceBaseModel

        class TestModel(GovernanceBaseModel):
            name: str

        # Should work with expected field
        model = TestModel(name="test")
        assert model.name == "test"

        # Should fail with extra field
        with pytest.raises(ValidationError) as exc_info:
            TestModel(name="test", extra_field="should_fail")

        assert "extra_field" in str(exc_info.value)


class TestAuditEventType:
    """Tests for governance AuditEventType enum."""

    def test_constraint_activated_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.CONSTRAINT_ACTIVATED.value == "constraint_activated"

    def test_constraint_deactivated_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.CONSTRAINT_DEACTIVATED.value == "constraint_deactivated"

    def test_falsifier_check_pass_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.FALSIFIER_CHECK_PASS.value == "falsifier_check_pass"

    def test_falsifier_check_triggered_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert (
            GovernanceAuditEventType.FALSIFIER_CHECK_TRIGGERED.value == "falsifier_check_triggered"
        )

    def test_veto_downgrade_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.VETO_DOWNGRADE.value == "veto_downgrade"

    def test_risk_budget_adjusted_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.RISK_BUDGET_ADJUSTED.value == "risk_budget_adjusted"

    def test_position_cap_applied_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.POSITION_CAP_APPLIED.value == "position_cap_applied"

    def test_pool_built_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.POOL_BUILT.value == "pool_built"

    def test_regime_changed_value(self):
        from src.governance.models import GovernanceAuditEventType

        assert GovernanceAuditEventType.REGIME_CHANGED.value == "regime_changed"

    def test_is_string_enum(self):
        """GovernanceAuditEventType should be a string enum for JSON serialization."""
        from src.governance.models import GovernanceAuditEventType

        assert isinstance(GovernanceAuditEventType.POOL_BUILT, str)
        assert GovernanceAuditEventType.POOL_BUILT == "pool_built"


class TestAlertSeverity:
    """Tests for AlertSeverity enum."""

    def test_info_value(self):
        from src.governance.models import AlertSeverity

        assert AlertSeverity.INFO.value == "info"

    def test_warning_value(self):
        from src.governance.models import AlertSeverity

        assert AlertSeverity.WARNING.value == "warning"

    def test_critical_value(self):
        from src.governance.models import AlertSeverity

        assert AlertSeverity.CRITICAL.value == "critical"

    def test_is_string_enum(self):
        """AlertSeverity should be a string enum for JSON serialization."""
        from src.governance.models import AlertSeverity

        assert isinstance(AlertSeverity.INFO, str)
        assert AlertSeverity.INFO == "info"


class TestRegimeState:
    """Tests for RegimeState enum."""

    def test_normal_value(self):
        from src.governance.models import RegimeState

        assert RegimeState.NORMAL.value == "NORMAL"

    def test_transition_value(self):
        from src.governance.models import RegimeState

        assert RegimeState.TRANSITION.value == "TRANSITION"

    def test_stress_value(self):
        from src.governance.models import RegimeState

        assert RegimeState.STRESS.value == "STRESS"

    def test_is_string_enum(self):
        """RegimeState should be a string enum for JSON serialization."""
        from src.governance.models import RegimeState

        assert isinstance(RegimeState.NORMAL, str)
        assert RegimeState.NORMAL == "NORMAL"


class TestHypothesisStatus:
    """Tests for HypothesisStatus enum."""

    def test_draft_value(self):
        from src.governance.models import HypothesisStatus

        assert HypothesisStatus.DRAFT.value == "DRAFT"

    def test_active_value(self):
        from src.governance.models import HypothesisStatus

        assert HypothesisStatus.ACTIVE.value == "ACTIVE"

    def test_sunset_value(self):
        from src.governance.models import HypothesisStatus

        assert HypothesisStatus.SUNSET.value == "SUNSET"

    def test_rejected_value(self):
        from src.governance.models import HypothesisStatus

        assert HypothesisStatus.REJECTED.value == "REJECTED"

    def test_is_string_enum(self):
        """HypothesisStatus should be a string enum for JSON serialization."""
        from src.governance.models import HypothesisStatus

        assert isinstance(HypothesisStatus.ACTIVE, str)
        assert HypothesisStatus.ACTIVE == "ACTIVE"


class TestComparisonOperator:
    """Tests for ComparisonOperator enum."""

    def test_lt_value(self):
        from src.governance.models import ComparisonOperator

        assert ComparisonOperator.LT.value == "<"

    def test_lte_value(self):
        from src.governance.models import ComparisonOperator

        assert ComparisonOperator.LTE.value == "<="

    def test_gt_value(self):
        from src.governance.models import ComparisonOperator

        assert ComparisonOperator.GT.value == ">"

    def test_gte_value(self):
        from src.governance.models import ComparisonOperator

        assert ComparisonOperator.GTE.value == ">="

    def test_eq_value(self):
        from src.governance.models import ComparisonOperator

        assert ComparisonOperator.EQ.value == "=="

    def test_is_string_enum(self):
        """ComparisonOperator should be a string enum for JSON serialization."""
        from src.governance.models import ComparisonOperator

        assert isinstance(ComparisonOperator.LT, str)
        assert ComparisonOperator.LT == "<"


class TestTriggerAction:
    """Tests for TriggerAction enum."""

    def test_review_value(self):
        from src.governance.models import TriggerAction

        assert TriggerAction.REVIEW.value == "review"

    def test_sunset_value(self):
        from src.governance.models import TriggerAction

        assert TriggerAction.SUNSET.value == "sunset"

    def test_is_string_enum(self):
        """TriggerAction should be a string enum for JSON serialization."""
        from src.governance.models import TriggerAction

        assert isinstance(TriggerAction.REVIEW, str)
        assert TriggerAction.REVIEW == "review"


class TestStopMode:
    """Tests for StopMode enum."""

    def test_baseline_value(self):
        from src.governance.models import StopMode

        assert StopMode.BASELINE.value == "baseline"

    def test_wide_value(self):
        from src.governance.models import StopMode

        assert StopMode.WIDE.value == "wide"

    def test_fundamental_guarded_value(self):
        from src.governance.models import StopMode

        assert StopMode.FUNDAMENTAL_GUARDED.value == "fundamental_guarded"

    def test_is_string_enum(self):
        """StopMode should be a string enum for JSON serialization."""
        from src.governance.models import StopMode

        assert isinstance(StopMode.BASELINE, str)
        assert StopMode.BASELINE == "baseline"


class TestAllExports:
    """Test that all required types are exported from models module."""

    def test_all_exports_available(self):
        """All governance model types should be importable."""
        from src.governance.models import (
            AlertSeverity,
            ComparisonOperator,
            GovernanceAuditEventType,
            GovernanceBaseModel,
            HypothesisStatus,
            RegimeState,
            StopMode,
            TriggerAction,
        )

        # Just verify they're all importable
        assert GovernanceBaseModel is not None
        assert GovernanceAuditEventType is not None
        assert AlertSeverity is not None
        assert RegimeState is not None
        assert HypothesisStatus is not None
        assert ComparisonOperator is not None
        assert TriggerAction is not None
        assert StopMode is not None
