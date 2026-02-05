"""Pydantic models for the Factor governance layer.

This module defines the data structures for trading factors with mandatory
failure rules that auto-disable degraded factors within the L0 Hypothesis +
L1 Constraints governance system.

Classes:
    FactorFailureRule: Rule defining when a factor should be disabled or reviewed
    FactorStatus: Factor lifecycle states (ENABLED, DISABLED, REVIEW)
    Factor: A trading factor with failure rules and status tracking
"""

from enum import Enum
from typing import Literal

from pydantic import Field

from src.governance.models import ComparisonOperator, GovernanceBaseModel


class FactorFailureRule(GovernanceBaseModel):
    """Rule defining when a factor should be disabled or reviewed.

    Each factor must have at least one failure rule (enforced by the loader
    gate:factor_requires_failure_rule). Failure rules are evaluated against
    live metric data from the MetricRegistry.

    Attributes:
        metric: Metric name that must be resolvable by MetricRegistry.
        operator: Comparison operator for the threshold check.
        threshold: Threshold value for the comparison.
        window: Lookback window for metric calculation (e.g., "6m", "3m", "90d").
        action: Action to take when rule triggers ("disable" or "review").
    """

    metric: str
    operator: ComparisonOperator
    threshold: float
    window: str
    action: Literal["disable", "review"]


class FactorStatus(str, Enum):
    """Factor lifecycle states.

    ENABLED: Factor is active and contributing to trading signals.
    DISABLED: Factor has been disabled (manually or by failure rule).
    REVIEW: Factor needs human review (triggered by failure rule with action="review").
    """

    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    REVIEW = "REVIEW"


class Factor(GovernanceBaseModel):
    """A trading factor with failure rules and status tracking.

    Factors implement quantitative alpha strategies linked to human hypotheses.
    Each factor must have at least one failure rule to ensure degraded factors
    are automatically detected and handled.

    Attributes:
        id: Unique identifier for the factor.
        name: Human-readable name for the factor.
        description: Description of what the factor measures/does.
        hypothesis_ids: List of hypothesis IDs this factor is linked to.
        failure_rules: Rules that can disable or flag the factor for review.
        status: Current lifecycle state (default: ENABLED).
        enabled: Whether the factor is enabled for trading (default: True).
    """

    id: str
    name: str
    description: str
    hypothesis_ids: list[str] = []
    failure_rules: list[FactorFailureRule] = Field(default_factory=list)
    status: FactorStatus = FactorStatus.ENABLED
    enabled: bool = True


__all__ = [
    "FactorFailureRule",
    "FactorStatus",
    "Factor",
]
