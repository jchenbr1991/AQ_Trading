"""Pydantic models for governance monitoring.

This module defines data structures for falsifier check results and alerts
used by the monitoring subsystem.

Classes:
    FalsifierCheckResult: Result of evaluating a single falsifier against metrics
    Alert: Governance alert for notification delivery

Spec Requirements:
    FR-025: Falsifier checks on configurable schedule
    FR-026: Review alerts with hypothesis_id, triggered_falsifier, metric_value,
            threshold, recommended_action
    FR-027: Notification delivery (log, email, webhook)
"""

from datetime import datetime

from src.governance.models import (
    AlertSeverity,
    ComparisonOperator,
    GovernanceBaseModel,
    TriggerAction,
)


class FalsifierCheckResult(GovernanceBaseModel):
    """Result of evaluating a single falsifier against metric data.

    Captures the outcome of checking one falsifier rule for a hypothesis.
    When triggered=True, the metric has breached the threshold according
    to the operator, indicating the hypothesis may be falsified.

    Attributes:
        hypothesis_id: ID of the hypothesis being checked.
        falsifier_index: Index of the falsifier in the hypothesis's falsifiers list.
        metric: Name of the metric being evaluated.
        operator: Comparison operator for the threshold check.
        threshold: Threshold value for the comparison.
        window: Lookback window for metric calculation.
        metric_value: Current metric value, or None if data unavailable.
        triggered: Whether the falsifier condition was met (threshold breached).
        trigger_action: Action to take if triggered (review or sunset).
        checked_at: Timestamp when the check was performed.
        message: Human-readable summary of the check result.
    """

    hypothesis_id: str
    falsifier_index: int
    metric: str
    operator: ComparisonOperator
    threshold: float
    window: str
    metric_value: float | None
    triggered: bool
    trigger_action: TriggerAction
    checked_at: datetime
    message: str


class Alert(GovernanceBaseModel):
    """Governance alert for notification delivery.

    Alerts are generated when falsifier checks trigger or other governance
    events require human attention. They can be delivered through multiple
    channels (log, email, webhook) via registered handlers.

    Attributes:
        id: Unique alert identifier (UUID string).
        severity: Alert severity level (info, warning, critical).
        source: Source of the alert (e.g., "falsifier_checker").
        hypothesis_id: Optional hypothesis ID related to the alert.
        constraint_id: Optional constraint ID related to the alert.
        title: Short title for the alert.
        message: Detailed alert message.
        details: Additional structured data (metric_value, threshold, etc.).
        created_at: Timestamp when the alert was created.
        delivered: Whether the alert has been delivered to handlers.
        delivery_channel: Channel used for delivery (log, email, webhook).
    """

    id: str
    severity: AlertSeverity
    source: str
    hypothesis_id: str | None = None
    constraint_id: str | None = None
    title: str
    message: str
    details: dict = {}
    created_at: datetime
    delivered: bool = False
    delivery_channel: str | None = None


__all__ = [
    "FalsifierCheckResult",
    "Alert",
]
