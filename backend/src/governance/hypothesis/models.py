"""Pydantic models for L0 Hypothesis governance entities.

This module defines the data structures for human worldview assertions (hypotheses)
that drive the L1 Constraints layer. Hypotheses are immutable after activation
and can only be modified via PR process with human approval.

Classes:
    HypothesisScope: Defines what symbols/sectors the hypothesis applies to
    Evidence: Supporting evidence for the hypothesis
    Falsifier: Rule that can invalidate the hypothesis
    Hypothesis: L0 Human worldview assertion
"""

from datetime import date

from pydantic import Field

from src.governance.models import (
    ComparisonOperator,
    GovernanceBaseModel,
    HypothesisStatus,
    TriggerAction,
)


class HypothesisScope(GovernanceBaseModel):
    """Defines what symbols/sectors the hypothesis applies to.

    An empty list for either field means "all" - the hypothesis applies
    universally to that dimension.

    Attributes:
        symbols: List of ticker symbols. Empty = all symbols.
        sectors: List of sector names. Empty = all sectors.
    """

    symbols: list[str] = []
    sectors: list[str] = []


class Evidence(GovernanceBaseModel):
    """Supporting evidence for the hypothesis.

    Evidence provides traceability for why a hypothesis was created,
    supporting the "human in the loop" governance model.

    Attributes:
        sources: List of URLs, file references, or document identifiers.
        notes: Free-form notes explaining the evidence.
    """

    sources: list[str] = []
    notes: str = ""


class Falsifier(GovernanceBaseModel):
    """Rule that can invalidate the hypothesis.

    Falsifiers implement Popperian falsifiability - every hypothesis must
    have at least one measurable condition that would invalidate it.
    This prevents unfalsifiable "just so" stories from entering the system.

    Attributes:
        metric: Metric name that must be resolvable by MetricRegistry.
        operator: Comparison operator for the threshold check.
        threshold: Threshold value for the comparison.
        window: Lookback window for metric calculation (e.g., "4q", "6m", "90d").
        trigger: Action to take when falsifier fires (review or sunset).
    """

    metric: str
    operator: ComparisonOperator
    threshold: float
    window: str
    trigger: TriggerAction


class Hypothesis(GovernanceBaseModel):
    """L0 Human worldview assertion.

    Hypotheses are the foundation of the governance system. They represent
    human beliefs about market behavior that must be:
    1. Stated explicitly as natural language propositions
    2. Falsifiable via measurable metrics
    3. Immutable after activation (changes require new hypothesis)

    The hypothesis lifecycle is:
        DRAFT -> ACTIVE (via PR merge)
        ACTIVE -> SUNSET (via falsifier trigger)
        ACTIVE -> REJECTED (via manual rejection)
        SUNSET -> REJECTED (via final rejection)

    Attributes:
        id: Unique identifier (lowercase alphanumeric with underscores).
        title: Human-readable title for the hypothesis.
        statement: Natural language proposition describing the belief.
        scope: What symbols/sectors this hypothesis applies to.
        owner: Always "human" - hypotheses are human-owned.
        status: Current lifecycle state.
        review_cycle: How often to review (e.g., "30d", "quarterly").
        created_at: Date the hypothesis was created.
        evidence: Supporting evidence for the hypothesis.
        falsifiers: Rules that can invalidate this hypothesis (min 1 required).
        linked_constraints: List of L1 constraint IDs derived from this hypothesis.
    """

    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    title: str
    statement: str
    scope: HypothesisScope
    owner: str = Field(default="human", pattern=r"^human$")
    status: HypothesisStatus
    review_cycle: str
    created_at: date
    evidence: Evidence
    falsifiers: list[Falsifier] = Field(..., min_length=1)
    linked_constraints: list[str] = []

    @property
    def is_active(self) -> bool:
        """Check if the hypothesis is currently active.

        Returns:
            True if status is ACTIVE, False otherwise.
        """
        return self.status == HypothesisStatus.ACTIVE


__all__ = [
    "HypothesisScope",
    "Evidence",
    "Falsifier",
    "Hypothesis",
]
