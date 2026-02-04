"""Base Pydantic models shared across the governance module.

This module defines the core data structures and enums for the L0 Hypothesis +
L1 Constraints governance system.

Classes:
    GovernanceBaseModel: Base model with strict validation for all governance entities
    GovernanceAuditEventType: Types of governance-specific audit events
    AlertSeverity: Alert severity levels (INFO, WARNING, CRITICAL)
    RegimeState: Market regime states (NORMAL, TRANSITION, STRESS)
    HypothesisStatus: Hypothesis lifecycle states (DRAFT, ACTIVE, SUNSET, REJECTED)
    ComparisonOperator: Operators for falsifier threshold comparisons
    TriggerAction: Actions when a falsifier is triggered (review, sunset)
    StopMode: Stop loss modes (baseline, wide, fundamental_guarded)
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict


class GovernanceBaseModel(BaseModel):
    """Base model for all governance entities.

    Uses strict validation with extra='forbid' to ensure no unexpected fields
    are passed during YAML loading or API requests. This helps catch
    configuration errors early.
    """

    model_config = ConfigDict(extra="forbid")


class GovernanceAuditEventType(str, Enum):
    """Types of governance-specific audit events.

    These event types capture the key governance actions that need to be
    logged for compliance and debugging purposes.

    Constraint events:
        CONSTRAINT_ACTIVATED: A constraint became active
        CONSTRAINT_DEACTIVATED: A constraint was deactivated

    Falsifier events:
        FALSIFIER_CHECK_PASS: Falsifier check passed successfully
        FALSIFIER_CHECK_TRIGGERED: Falsifier threshold was breached

    Action events:
        VETO_DOWNGRADE: A veto downgrade was applied
        RISK_BUDGET_ADJUSTED: Risk budget was adjusted by constraint
        POSITION_CAP_APPLIED: Position cap was applied to a symbol

    System events:
        POOL_BUILT: Trading pool was rebuilt
        REGIME_CHANGED: Market regime state changed
    """

    # Constraint events
    CONSTRAINT_ACTIVATED = "constraint_activated"
    CONSTRAINT_DEACTIVATED = "constraint_deactivated"

    # Falsifier events
    FALSIFIER_CHECK_PASS = "falsifier_check_pass"  # noqa: S105 — not a password
    FALSIFIER_CHECK_TRIGGERED = "falsifier_check_triggered"

    # Action events
    VETO_DOWNGRADE = "veto_downgrade"
    RISK_BUDGET_ADJUSTED = "risk_budget_adjusted"
    POSITION_CAP_APPLIED = "position_cap_applied"

    # System events
    POOL_BUILT = "pool_built"
    REGIME_CHANGED = "regime_changed"


class AlertSeverity(str, Enum):
    """Alert severity levels for governance notifications.

    INFO: Routine informational event (e.g., pool rebuilt)
    WARNING: Potential issue requiring attention (e.g., falsifier near threshold)
    CRITICAL: Serious issue requiring immediate action (e.g., falsifier triggered)
    """

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RegimeState(str, Enum):
    """Market regime states affecting position pacing.

    Note: Regime NEVER contributes to alpha; only affects position sizing/pacing.

    NORMAL: Standard market conditions, normal position sizes
    TRANSITION: Market transitioning between states, reduced position sizes
    STRESS: High volatility/drawdown, minimal new positions
    """

    NORMAL = "NORMAL"
    TRANSITION = "TRANSITION"
    STRESS = "STRESS"


class HypothesisStatus(str, Enum):
    """Hypothesis lifecycle states.

    State transitions:
        DRAFT -> ACTIVE: Via PR merge (human approval required)
        ACTIVE -> SUNSET: Via falsifier trigger
        ACTIVE -> REJECTED: Via manual rejection
        SUNSET -> REJECTED: Via final rejection

    DRAFT: Hypothesis is being developed, not yet active
    ACTIVE: Hypothesis is approved and driving constraints
    SUNSET: Hypothesis failed falsification, pending review
    REJECTED: Hypothesis was rejected and is inactive
    """

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUNSET = "SUNSET"
    REJECTED = "REJECTED"


class ComparisonOperator(str, Enum):
    """Comparison operators for falsifier threshold checks.

    Used to define when a metric value triggers a falsifier.
    Example: "rolling_ic_mean" >= 0 means IC must stay non-negative.

    LT: Less than (<)
    LTE: Less than or equal (<=)
    GT: Greater than (>)
    GTE: Greater than or equal (>=)
    EQ: Equal (==)
    """

    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    EQ = "=="


class TriggerAction(str, Enum):
    """Actions to take when a falsifier is triggered.

    REVIEW: Alert human for review but keep hypothesis active
    SUNSET: Automatically sunset the hypothesis
    """

    REVIEW = "review"
    SUNSET = "sunset"


class StopMode(str, Enum):
    """Stop loss modes for position management.

    BASELINE: Standard stop loss (e.g., 2% from entry)
    WIDE: Extended stop loss (e.g., 5% from entry) for volatile positions
    FUNDAMENTAL_GUARDED: Fundamental-based stop with additional protection
    """

    BASELINE = "baseline"
    WIDE = "wide"
    FUNDAMENTAL_GUARDED = "fundamental_guarded"


__all__ = [
    "GovernanceBaseModel",
    "GovernanceAuditEventType",
    "AlertSeverity",
    "RegimeState",
    "HypothesisStatus",
    "ComparisonOperator",
    "TriggerAction",
    "StopMode",
]
