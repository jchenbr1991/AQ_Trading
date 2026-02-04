"""Factor Registry with status tracking and health checks.

This module provides the FactorRegistry class for managing trading factors
in memory with status tracking, enable/disable operations, and automated
health checks that evaluate failure rules against live metric data.

Classes:
    DuplicateFactorError: Raised when registering a factor with duplicate ID
    FactorHealthCheckResult: Result of evaluating a single failure rule
    FactorRegistry: In-memory registry for factor management

Example:
    >>> from src.governance.factors.registry import FactorRegistry
    >>> from src.governance.monitoring.metrics import MetricRegistry
    >>> registry = FactorRegistry()
    >>> registry.register(factor)
    >>> results = registry.check_factor_health("momentum_factor", metric_registry)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.governance.factors.models import Factor, FactorStatus
from src.governance.models import ComparisonOperator, GovernanceBaseModel

if TYPE_CHECKING:
    from src.governance.monitoring.metrics import MetricRegistry

logger = logging.getLogger(__name__)


class DuplicateFactorError(Exception):
    """Raised when attempting to register a factor with a duplicate ID.

    Attributes:
        factor_id: The ID that caused the duplicate error.
    """

    def __init__(self, factor_id: str) -> None:
        """Initialize the error with the duplicate factor ID.

        Args:
            factor_id: The ID that already exists in the registry.
        """
        self.factor_id = factor_id
        super().__init__(f"Factor with ID '{factor_id}' already exists in registry")


class FactorHealthCheckResult(GovernanceBaseModel):
    """Result of evaluating a single failure rule against metric data.

    Attributes:
        factor_id: ID of the factor being checked.
        rule_index: Index of the failure rule in the factor's failure_rules list.
        metric: Name of the metric being evaluated.
        operator: Comparison operator for the threshold check.
        threshold: Threshold value for the comparison.
        window: Lookback window for metric calculation.
        metric_value: Current metric value, or None if data unavailable.
        triggered: Whether the failure rule condition was met.
        action: Action specified by the rule ("disable" or "review").
        checked_at: Timestamp when the check was performed.
        message: Human-readable summary of the check result.
    """

    factor_id: str
    rule_index: int
    metric: str
    operator: ComparisonOperator
    threshold: float
    window: str
    metric_value: float | None
    triggered: bool
    action: str
    checked_at: datetime
    message: str


class FactorRegistry:
    """In-memory registry for factor management with status tracking.

    Stores factors in memory and provides operations for registration,
    status management, and health checks. Health checks evaluate failure
    rules against the MetricRegistry and auto-disable or flag factors.

    Attributes:
        _factors: Internal dict storing factors by ID.

    Example:
        >>> registry = FactorRegistry()
        >>> registry.register(factor)
        >>> registry.check_factor_health("momentum_factor", metric_registry)
    """

    def __init__(self) -> None:
        """Initialize an empty FactorRegistry."""
        self._factors: dict[str, Factor] = {}

    def register(self, factor: Factor) -> None:
        """Register a factor in the registry.

        Args:
            factor: The Factor to register.

        Raises:
            DuplicateFactorError: If a factor with the same ID already exists.
        """
        if factor.id in self._factors:
            raise DuplicateFactorError(factor.id)
        self._factors[factor.id] = factor
        logger.debug(f"Registered factor: {factor.id}")

    def get(self, factor_id: str) -> Factor | None:
        """Get a factor by ID.

        Args:
            factor_id: The unique identifier of the factor.

        Returns:
            The Factor if found, None otherwise.
        """
        return self._factors.get(factor_id)

    def list_all(self) -> list[Factor]:
        """List all registered factors.

        Returns:
            List of all factors in the registry.
        """
        return list(self._factors.values())

    def get_enabled(self) -> list[Factor]:
        """Get all factors with ENABLED status.

        Returns:
            List of factors with status == ENABLED and enabled == True.
        """
        return [f for f in self._factors.values() if f.status == FactorStatus.ENABLED and f.enabled]

    def disable_factor(self, factor_id: str) -> None:
        """Disable a factor by setting status to DISABLED and enabled to False.

        Args:
            factor_id: The ID of the factor to disable.

        Raises:
            KeyError: If the factor is not found.
        """
        factor = self._factors.get(factor_id)
        if factor is None:
            raise KeyError(f"Factor '{factor_id}' not found in registry")

        # Create updated factor with new status (Pydantic models are immutable-ish)
        updated = factor.model_copy(
            update={
                "status": FactorStatus.DISABLED,
                "enabled": False,
            }
        )
        self._factors[factor_id] = updated
        logger.info(f"Disabled factor: {factor_id}")

    def enable_factor(self, factor_id: str) -> None:
        """Enable a factor by setting status to ENABLED and enabled to True.

        Args:
            factor_id: The ID of the factor to enable.

        Raises:
            KeyError: If the factor is not found.
        """
        factor = self._factors.get(factor_id)
        if factor is None:
            raise KeyError(f"Factor '{factor_id}' not found in registry")

        updated = factor.model_copy(
            update={
                "status": FactorStatus.ENABLED,
                "enabled": True,
            }
        )
        self._factors[factor_id] = updated
        logger.info(f"Enabled factor: {factor_id}")

    def set_review(self, factor_id: str) -> None:
        """Set a factor's status to REVIEW.

        Args:
            factor_id: The ID of the factor to set to review.

        Raises:
            KeyError: If the factor is not found.
        """
        factor = self._factors.get(factor_id)
        if factor is None:
            raise KeyError(f"Factor '{factor_id}' not found in registry")

        updated = factor.model_copy(
            update={
                "status": FactorStatus.REVIEW,
            }
        )
        self._factors[factor_id] = updated
        logger.info(f"Set factor to review: {factor_id}")

    def unregister(self, factor_id: str) -> bool:
        """Remove a factor from the registry.

        Args:
            factor_id: The ID of the factor to remove.

        Returns:
            True if the factor was removed, False if not found.
        """
        if factor_id in self._factors:
            del self._factors[factor_id]
            logger.debug(f"Unregistered factor: {factor_id}")
            return True
        return False

    def count(self) -> int:
        """Count total registered factors.

        Returns:
            The total number of factors in the registry.
        """
        return len(self._factors)

    def check_factor_health(
        self,
        factor_id: str,
        metric_registry: MetricRegistry,
    ) -> list[FactorHealthCheckResult]:
        """Evaluate failure rules for a factor against metric data.

        For each failure rule defined on the factor, retrieves the current
        metric value from the MetricRegistry and compares it against the
        threshold. If triggered:
        - action="disable": auto-disables the factor
        - action="review": sets factor to REVIEW status

        If multiple rules trigger, "disable" takes priority over "review".

        Args:
            factor_id: The ID of the factor to check.
            metric_registry: MetricRegistry for querying current metric values.

        Returns:
            List of FactorHealthCheckResult, one per failure rule.

        Raises:
            KeyError: If the factor is not found in the registry.
        """
        factor = self._factors.get(factor_id)
        if factor is None:
            raise KeyError(f"Factor '{factor_id}' not found in registry")

        now = datetime.now(timezone.utc)
        results: list[FactorHealthCheckResult] = []
        should_disable = False
        should_review = False

        for index, rule in enumerate(factor.failure_rules):
            metric_value = metric_registry.get_value(rule.metric, window=rule.window)

            # If metric data is unavailable, don't trigger
            if metric_value is None:
                result = FactorHealthCheckResult(
                    factor_id=factor_id,
                    rule_index=index,
                    metric=rule.metric,
                    operator=rule.operator,
                    threshold=rule.threshold,
                    window=rule.window,
                    metric_value=None,
                    triggered=False,
                    action=rule.action,
                    checked_at=now,
                    message=(
                        f"No data available for metric '{rule.metric}' " f"(window={rule.window})"
                    ),
                )
                results.append(result)
                continue

            triggered = self._compare(metric_value, rule.operator, rule.threshold)

            if triggered:
                message = (
                    f"TRIGGERED: {rule.metric}={metric_value} "
                    f"{rule.operator.value} {rule.threshold} "
                    f"(window={rule.window}). "
                    f"Action: {rule.action}"
                )
                logger.warning(f"Failure rule triggered for factor '{factor_id}': {message}")
                if rule.action == "disable":
                    should_disable = True
                elif rule.action == "review":
                    should_review = True
            else:
                message = (
                    f"Passed: {rule.metric}={metric_value}, "
                    f"threshold {rule.operator.value} {rule.threshold} "
                    f"not met (window={rule.window})"
                )

            result = FactorHealthCheckResult(
                factor_id=factor_id,
                rule_index=index,
                metric=rule.metric,
                operator=rule.operator,
                threshold=rule.threshold,
                window=rule.window,
                metric_value=metric_value,
                triggered=triggered,
                action=rule.action,
                checked_at=now,
                message=message,
            )
            results.append(result)

        # Apply status changes: disable takes priority over review
        if should_disable:
            self.disable_factor(factor_id)
        elif should_review:
            self.set_review(factor_id)

        return results

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


__all__ = [
    "DuplicateFactorError",
    "FactorHealthCheckResult",
    "FactorRegistry",
]
