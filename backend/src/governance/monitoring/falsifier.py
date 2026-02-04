"""Falsifier checker for evaluating hypothesis falsifiers against metrics.

This module provides the FalsifierChecker class that evaluates falsifier
rules defined on hypotheses against current metric data from the MetricRegistry.

Classes:
    FalsifierChecker: Evaluates falsifiers and produces check results

Spec Requirements:
    FR-025: Falsifier checks on configurable schedule
    US4 Scenario 1: IC below 0 for 6 months triggers sunset recommendation

Example:
    >>> from src.governance.monitoring.falsifier import FalsifierChecker
    >>> checker = FalsifierChecker(
    ...     hypothesis_registry=hyp_registry,
    ...     metric_registry=metric_registry,
    ... )
    >>> results = checker.check_hypothesis("momentum_persistence")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.governance.models import ComparisonOperator, GovernanceAuditEventType
from src.governance.monitoring.models import FalsifierCheckResult

if TYPE_CHECKING:
    from src.governance.audit.store import InMemoryAuditStore
    from src.governance.hypothesis.models import Falsifier
    from src.governance.hypothesis.registry import HypothesisRegistry
    from src.governance.monitoring.metrics import MetricRegistry

logger = logging.getLogger(__name__)


class FalsifierChecker:
    """Evaluates falsifier rules for hypotheses against metric data.

    For each falsifier defined on a hypothesis, the checker retrieves
    the current metric value from the MetricRegistry and compares it
    against the threshold using the specified operator. If the condition
    is met, the falsifier is considered triggered.

    Attributes:
        hypothesis_registry: Registry for looking up hypotheses.
        metric_registry: Registry for querying metric values.

    Example:
        >>> checker = FalsifierChecker(hyp_registry, metric_registry)
        >>> results = checker.check_all()
        >>> triggered = [r for r in results if r.triggered]
    """

    def __init__(
        self,
        hypothesis_registry: HypothesisRegistry,
        metric_registry: MetricRegistry,
        audit_store: InMemoryAuditStore | None = None,
    ) -> None:
        """Initialize FalsifierChecker with registries and optional audit store.

        Args:
            hypothesis_registry: Registry for looking up hypotheses by ID.
            metric_registry: Registry for querying current metric values.
            audit_store: Optional InMemoryAuditStore for logging audit events.
        """
        self.hypothesis_registry = hypothesis_registry
        self.metric_registry = metric_registry
        self.audit_store = audit_store

    def check_hypothesis(self, hypothesis_id: str) -> list[FalsifierCheckResult]:
        """Check all falsifiers for a hypothesis.

        Evaluates each falsifier defined on the hypothesis against the
        current metric data.

        Args:
            hypothesis_id: The ID of the hypothesis to check.

        Returns:
            List of FalsifierCheckResult, one per falsifier.

        Raises:
            ValueError: If the hypothesis is not found in the registry.
        """
        hypothesis = self.hypothesis_registry.get(hypothesis_id)
        if hypothesis is None:
            raise ValueError(f"Hypothesis '{hypothesis_id}' not found in registry")

        results = []
        for index, falsifier in enumerate(hypothesis.falsifiers):
            result = self.evaluate_falsifier(hypothesis_id, falsifier, index)
            results.append(result)

        return results

    def check_all(self) -> list[FalsifierCheckResult]:
        """Check all falsifiers for all active hypotheses.

        Only evaluates hypotheses with ACTIVE status.

        Returns:
            List of FalsifierCheckResult for all active hypotheses.
        """
        results = []
        active_hypotheses = self.hypothesis_registry.get_active()

        for hypothesis in active_hypotheses:
            try:
                hyp_results = self.check_hypothesis(hypothesis.id)
                results.extend(hyp_results)
            except Exception:
                logger.exception(f"Error checking falsifiers for hypothesis: {hypothesis.id}")

        return results

    def evaluate_falsifier(
        self,
        hypothesis_id: str,
        falsifier: Falsifier,
        falsifier_index: int,
    ) -> FalsifierCheckResult:
        """Evaluate a single falsifier against metric data.

        Retrieves the metric value from the MetricRegistry and compares
        it against the falsifier's threshold using the specified operator.

        If the metric is unavailable (None), the falsifier is not triggered
        and the result includes a message indicating data unavailability.

        Args:
            hypothesis_id: The ID of the hypothesis owning this falsifier.
            falsifier: The Falsifier object to evaluate.
            falsifier_index: Index of this falsifier in the hypothesis.

        Returns:
            FalsifierCheckResult with the evaluation outcome.
        """
        now = datetime.now(timezone.utc)

        # Get metric value
        metric_value = self.metric_registry.get_value(falsifier.metric, window=falsifier.window)

        # If metric data is unavailable, don't trigger
        if metric_value is None:
            return FalsifierCheckResult(
                hypothesis_id=hypothesis_id,
                falsifier_index=falsifier_index,
                metric=falsifier.metric,
                operator=falsifier.operator,
                threshold=falsifier.threshold,
                window=falsifier.window,
                metric_value=None,
                triggered=False,
                trigger_action=falsifier.trigger,
                checked_at=now,
                message=(
                    f"No data available for metric '{falsifier.metric}' "
                    f"(window={falsifier.window})"
                ),
            )

        # Compare metric value against threshold
        triggered = self._compare(metric_value, falsifier.operator, falsifier.threshold)

        if triggered:
            message = (
                f"TRIGGERED: {falsifier.metric}={metric_value} "
                f"{falsifier.operator.value} {falsifier.threshold} "
                f"(window={falsifier.window}). "
                f"Recommended action: {falsifier.trigger.value}"
            )
            logger.warning(f"Falsifier triggered for hypothesis '{hypothesis_id}': {message}")
        else:
            message = (
                f"Passed: {falsifier.metric}={metric_value}, "
                f"threshold {falsifier.operator.value} {falsifier.threshold} "
                f"not met (window={falsifier.window})"
            )
            logger.debug(f"Falsifier passed for hypothesis '{hypothesis_id}': {message}")

        result = FalsifierCheckResult(
            hypothesis_id=hypothesis_id,
            falsifier_index=falsifier_index,
            metric=falsifier.metric,
            operator=falsifier.operator,
            threshold=falsifier.threshold,
            window=falsifier.window,
            metric_value=metric_value,
            triggered=triggered,
            trigger_action=falsifier.trigger,
            checked_at=now,
            message=message,
        )

        # Log audit event if audit store is configured
        self._log_falsifier_check(result)

        return result

    def _log_falsifier_check(self, result: FalsifierCheckResult) -> None:
        """Log an audit event for a falsifier check result.

        Logs FALSIFIER_CHECK_PASS for passed checks and
        FALSIFIER_CHECK_TRIGGERED for triggered checks.

        Args:
            result: The falsifier check result to log.
        """
        if self.audit_store is None:
            return

        event_type = (
            GovernanceAuditEventType.FALSIFIER_CHECK_TRIGGERED
            if result.triggered
            else GovernanceAuditEventType.FALSIFIER_CHECK_PASS
        )

        self.audit_store.log(
            event_type=event_type,
            hypothesis_id=result.hypothesis_id,
            action_details={
                "metric": result.metric,
                "metric_value": result.metric_value,
                "threshold": result.threshold,
                "operator": result.operator.value,
                "window": result.window,
                "triggered": result.triggered,
                "trigger_action": result.trigger_action.value,
                "falsifier_index": result.falsifier_index,
            },
        )

    def _compare(
        self,
        value: float,
        operator: ComparisonOperator,
        threshold: float,
    ) -> bool:
        """Compare a value against a threshold using the given operator.

        Args:
            value: The metric value to compare.
            operator: The comparison operator.
            threshold: The threshold value.

        Returns:
            True if the comparison condition is met, False otherwise.
        """
        if operator == ComparisonOperator.LT:
            return value < threshold
        elif operator == ComparisonOperator.LTE:
            return value <= threshold
        elif operator == ComparisonOperator.GT:
            return value > threshold
        elif operator == ComparisonOperator.GTE:
            return value >= threshold
        elif operator == ComparisonOperator.EQ:
            return value == threshold
        else:
            logger.error(f"Unknown comparison operator: {operator}")
            return False


__all__ = ["FalsifierChecker"]
