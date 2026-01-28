"""Greeks Alert Engine for threshold breach and rate-of-change detection.

This module provides the AlertEngine that detects threshold breaches and rate-of-change
alerts for Greeks monitoring.

Dataclasses:
    - AlertState: Tracks current alert state for a scope/metric combination
    - GreeksAlert: A generated alert for threshold breach or ROC detection

Classes:
    - AlertEngine: Detects threshold breaches and rate-of-change alerts
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from src.greeks.models import (
    AggregatedGreeks,
    GreeksLevel,
    GreeksLimitsConfig,
    GreeksThresholdConfig,
    RiskMetric,
    ThresholdDirection,
)


def _format_metric_value(metric: RiskMetric, value: Decimal) -> str:
    """Format a metric value with appropriate unit suffix.

    V1.5: Added to clarify Theta is per trading day (not calendar day).
    Avoids user confusion about time decay calculations.

    Args:
        metric: The RiskMetric type
        value: The value to format

    Returns:
        Formatted string with value and unit suffix

    Examples:
        >>> _format_metric_value(RiskMetric.DELTA, Decimal("5000"))
        "$5000"
        >>> _format_metric_value(RiskMetric.THETA, Decimal("-150"))
        "$-150/trading day"
        >>> _format_metric_value(RiskMetric.VEGA, Decimal("200"))
        "$200/1% IV"
    """
    # Unit suffixes by metric type
    unit_map = {
        RiskMetric.DELTA: "",  # $ per $1 underlying move (implicit)
        RiskMetric.GAMMA: "",  # $ per ($1 move)^2 (implicit)
        RiskMetric.VEGA: "/1% IV",
        RiskMetric.THETA: "/trading day",  # V1.5: Clarify not calendar day
        RiskMetric.IMPLIED_VOLATILITY: "",
        RiskMetric.COVERAGE: "%",
    }

    suffix = unit_map.get(metric, "")
    return f"${value}{suffix}"


@dataclass
class AlertState:
    """Tracks current alert state for a scope/metric combination.

    This dataclass maintains the current state of alerts for a particular
    scope (ACCOUNT or STRATEGY) and metric combination. It tracks the current
    alert level, when the level was entered, and when the last alert was sent.

    Hysteresis:
        Alert states use hysteresis to prevent alert flapping. Once an alert
        level is entered, the value must drop below a recovery threshold
        (not just the trigger threshold) to clear the alert.

    TTL:
        States have a time-to-live to allow cleanup of stale entries that
        are no longer being monitored.

    Attributes:
        scope: "ACCOUNT" or "STRATEGY"
        scope_id: Account or strategy identifier
        metric: The RiskMetric being tracked
        current_level: Current GreeksLevel (NORMAL, WARN, CRIT, HARD)
        current_value: Current absolute value
        threshold_config: The GreeksThresholdConfig for this metric
        entered_at: When this level was entered
        last_alert_at: When last alert was sent (for deduplication)
        ttl_seconds: Time-to-live for state cleanup (default 86400 = 24h)
    """

    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    metric: RiskMetric
    current_level: GreeksLevel
    current_value: Decimal
    threshold_config: GreeksThresholdConfig
    entered_at: datetime
    last_alert_at: datetime | None = None
    ttl_seconds: int = 86400  # 24 hours default

    def is_expired(self) -> bool:
        """Check if state exceeded TTL.

        Returns:
            True if the state has been in the current level for longer
            than ttl_seconds, False otherwise.
        """
        now = datetime.now(timezone.utc)
        elapsed = (now - self.entered_at).total_seconds()
        return elapsed > self.ttl_seconds

    def can_send_alert(self, dedupe_window: int) -> bool:
        """Check if enough time passed since last alert.

        Args:
            dedupe_window: Minimum seconds between alerts for deduplication

        Returns:
            True if no previous alert was sent or enough time has passed,
            False if within the deduplication window.
        """
        if self.last_alert_at is None:
            return True
        now = datetime.now(timezone.utc)
        elapsed = (now - self.last_alert_at).total_seconds()
        return elapsed >= dedupe_window


@dataclass
class GreeksAlert:
    """A generated alert for a Greeks threshold breach or ROC detection.

    This dataclass represents an alert that should be sent to notification
    systems when a threshold is breached or rapid rate of change is detected.

    Alert Types:
        - THRESHOLD: Value crossed a threshold level (WARN, CRIT, HARD)
        - ROC: Rapid rate of change detected

    Attributes:
        alert_id: UUID string for unique identification
        alert_type: "THRESHOLD" or "ROC" (rate of change)
        scope: "ACCOUNT" or "STRATEGY"
        scope_id: Account or strategy identifier
        metric: The RiskMetric that triggered
        level: GreeksLevel (WARN, CRIT, HARD)
        current_value: Current metric value
        threshold_value: The threshold that was breached
        prev_value: Previous value (for ROC alerts)
        change_pct: Percentage change (for ROC alerts)
        message: Human-readable alert message
        created_at: When alert was created
    """

    alert_id: str
    alert_type: Literal["THRESHOLD", "ROC"]
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str
    metric: RiskMetric
    level: GreeksLevel
    current_value: Decimal
    threshold_value: Decimal
    message: str
    created_at: datetime
    prev_value: Decimal | None = None
    change_pct: Decimal | None = None


class AlertEngine:
    """Detects threshold breaches and rate-of-change alerts.

    Maintains AlertState for each scope/metric combination.
    Uses hysteresis to prevent alert flapping.

    Attributes:
        _states: Dict mapping (scope, scope_id, metric) -> AlertState
        _state_ttl_seconds: TTL for state cleanup (default 86400)
    """

    def __init__(self, state_ttl_seconds: int = 86400):
        """Initialize the AlertEngine.

        Args:
            state_ttl_seconds: TTL for state cleanup (default 86400 = 24 hours)
        """
        self._states: dict[tuple[str, str, RiskMetric], AlertState] = {}
        self._state_ttl_seconds = state_ttl_seconds

    def _get_effective_value(self, value: Decimal, direction: ThresholdDirection) -> Decimal:
        """Get the effective value based on threshold direction.

        Args:
            value: The raw metric value
            direction: The threshold direction (ABS, MAX, MIN)

        Returns:
            The effective value for comparison:
            - ABS: abs(value)
            - MAX: value directly
            - MIN: -value (breach if value < threshold means -value > threshold)
        """
        if direction == ThresholdDirection.ABS:
            return abs(value)
        elif direction == ThresholdDirection.MAX:
            return value
        else:  # MIN direction
            return -value

    def _check_threshold(
        self,
        metric: RiskMetric,
        value: Decimal,
        config: GreeksThresholdConfig,
        current_state: AlertState | None,
    ) -> GreeksLevel:
        """Determine alert level based on value and thresholds.

        Uses hysteresis: must drop below recovery threshold to clear alert.
        Direction handling:
        - ABS: use abs(value)
        - MAX: use value directly (breach if value > threshold)
        - MIN: use -value (breach if value < threshold)

        Args:
            metric: The RiskMetric being checked
            value: The current value
            config: The threshold configuration
            current_state: The current AlertState, if any

        Returns:
            The appropriate GreeksLevel based on value and hysteresis.
        """
        effective_value = self._get_effective_value(value, config.direction)

        # Get threshold values
        warn_threshold = config.warn_threshold
        crit_threshold = config.crit_threshold
        hard_threshold = config.hard_threshold

        # Calculate recovery thresholds
        warn_recover = config.limit * config.warn_recover_pct
        crit_recover = config.limit * config.crit_recover_pct

        # Determine base level from current value
        if effective_value >= hard_threshold:
            base_level = GreeksLevel.HARD
        elif effective_value >= crit_threshold:
            base_level = GreeksLevel.CRIT
        elif effective_value >= warn_threshold:
            base_level = GreeksLevel.WARN
        else:
            base_level = GreeksLevel.NORMAL

        # Apply hysteresis if we have a current state
        if current_state is not None:
            current_level = current_state.current_level

            # If we're at a higher level than base would indicate,
            # check if we should stay at current level due to hysteresis
            if current_level == GreeksLevel.HARD:
                # HARD can only recover to CRIT if below hard threshold
                if effective_value >= hard_threshold:
                    return GreeksLevel.HARD
                elif effective_value >= crit_recover:
                    return GreeksLevel.CRIT
                elif effective_value >= warn_recover:
                    return GreeksLevel.WARN
                else:
                    return GreeksLevel.NORMAL

            elif current_level == GreeksLevel.CRIT:
                # CRIT stays CRIT unless below crit_recover
                if effective_value >= hard_threshold:
                    return GreeksLevel.HARD
                elif effective_value >= crit_recover:
                    return GreeksLevel.CRIT
                elif effective_value >= warn_recover:
                    return GreeksLevel.WARN
                else:
                    return GreeksLevel.NORMAL

            elif current_level == GreeksLevel.WARN:
                # WARN stays WARN unless below warn_recover
                if effective_value >= hard_threshold:
                    return GreeksLevel.HARD
                elif effective_value >= crit_threshold:
                    return GreeksLevel.CRIT
                elif effective_value >= warn_recover:
                    return GreeksLevel.WARN
                else:
                    return GreeksLevel.NORMAL

        return base_level

    def _check_rate_of_change(
        self,
        metric: RiskMetric,
        current_value: Decimal,
        prev_value: Decimal,
        config: GreeksThresholdConfig,
    ) -> GreeksAlert | None:
        """Check for rapid rate of change.

        Triggers ROC alert if:
        - abs(current - prev) > rate_change_abs, OR
        - abs(current - prev) / limit > rate_change_pct

        Note: prev_value comes from snapshot store, NOT memory state.

        Args:
            metric: The RiskMetric being checked
            current_value: Current metric value
            prev_value: Previous metric value from snapshot
            config: The threshold configuration

        Returns:
            GreeksAlert if rate of change threshold exceeded, None otherwise.
        """
        change = abs(current_value - prev_value)

        # Check absolute change threshold (if configured)
        abs_threshold_breached = (
            config.rate_change_abs > Decimal("0") and change > config.rate_change_abs
        )

        # Check percentage change threshold
        pct_change = Decimal("0")
        if config.limit > Decimal("0"):
            pct_change = change / config.limit
        pct_threshold_breached = pct_change > config.rate_change_pct

        if abs_threshold_breached or pct_threshold_breached:
            change_pct_display = pct_change * Decimal("100")
            threshold_pct_display = config.rate_change_pct * Decimal("100")

            current_fmt = _format_metric_value(metric, current_value)
            prev_fmt = _format_metric_value(metric, prev_value)
            message = (
                f"{metric.value.upper()} changed from {prev_fmt} to {current_fmt} "
                f"({change_pct_display:+.1f}%, threshold: {threshold_pct_display:.0f}%)"
            )

            return GreeksAlert(
                alert_id=str(uuid4()),
                alert_type="ROC",
                scope="ACCOUNT",  # Will be set by caller
                scope_id="",  # Will be set by caller
                metric=metric,
                level=GreeksLevel.WARN,  # ROC alerts are always WARN level
                current_value=current_value,
                threshold_value=config.rate_change_abs
                if abs_threshold_breached
                else config.limit * config.rate_change_pct,
                prev_value=prev_value,
                change_pct=change_pct_display,
                message=message,
                created_at=datetime.now(timezone.utc),
            )

        return None

    def _get_metric_value(self, aggregated: AggregatedGreeks, metric: RiskMetric) -> Decimal | None:
        """Get the value for a metric from aggregated Greeks.

        Args:
            aggregated: The AggregatedGreeks to extract value from
            metric: The RiskMetric to get

        Returns:
            The metric value, or None if metric is not applicable.
        """
        metric_map = {
            RiskMetric.DELTA: aggregated.dollar_delta,
            RiskMetric.GAMMA: aggregated.gamma_dollar,
            RiskMetric.VEGA: aggregated.vega_per_1pct,
            RiskMetric.THETA: aggregated.theta_per_day,
            # IV and COVERAGE would need different handling
        }
        return metric_map.get(metric)

    def check_alerts(
        self,
        aggregated: AggregatedGreeks,
        config: GreeksLimitsConfig,
        prev_greeks: AggregatedGreeks | None = None,
    ) -> list[GreeksAlert]:
        """Check aggregated Greeks against limits and generate alerts.

        Args:
            aggregated: Current AggregatedGreeks
            config: GreeksLimitsConfig with thresholds
            prev_greeks: Previous snapshot for ROC detection (from persistent store)

        Returns:
            List of GreeksAlert for any breaches
        """
        alerts: list[GreeksAlert] = []
        now = datetime.now(timezone.utc)

        for metric, threshold_config in config.thresholds.items():
            current_value = self._get_metric_value(aggregated, metric)
            if current_value is None:
                continue

            state_key = (aggregated.scope, aggregated.scope_id, metric)
            current_state = self._states.get(state_key)

            # Check threshold level
            new_level = self._check_threshold(
                metric=metric,
                value=current_value,
                config=threshold_config,
                current_state=current_state,
            )

            # Determine if we need to generate an alert
            should_alert = False
            level_changed = False

            if current_state is None:
                # No previous state - alert if level is not NORMAL
                if new_level != GreeksLevel.NORMAL:
                    should_alert = True
                    level_changed = True
            else:
                # Have previous state - check for level change or dedupe
                if new_level != current_state.current_level:
                    level_changed = True
                    # Alert on escalation (new level is worse)
                    level_order = {
                        GreeksLevel.NORMAL: 0,
                        GreeksLevel.WARN: 1,
                        GreeksLevel.CRIT: 2,
                        GreeksLevel.HARD: 3,
                    }
                    if level_order[new_level] > level_order[current_state.current_level]:
                        should_alert = True
                elif new_level != GreeksLevel.NORMAL:
                    # Same level (not NORMAL) - check deduplication
                    dedupe_window = config.dedupe_window_seconds_by_level.get(new_level, 900)
                    if current_state.can_send_alert(dedupe_window):
                        should_alert = True

            # Generate threshold alert if needed
            if should_alert and new_level != GreeksLevel.NORMAL:
                # Get the threshold value for this level
                threshold_value = threshold_config.warn_threshold
                if new_level == GreeksLevel.CRIT:
                    threshold_value = threshold_config.crit_threshold
                elif new_level == GreeksLevel.HARD:
                    threshold_value = threshold_config.hard_threshold

                current_fmt = _format_metric_value(metric, current_value)
                threshold_fmt = _format_metric_value(metric, threshold_value)
                message = (
                    f"{metric.value.upper()} exceeded {new_level.value.upper()} "
                    f"threshold: {current_fmt} > {threshold_fmt}"
                )

                alert = GreeksAlert(
                    alert_id=str(uuid4()),
                    alert_type="THRESHOLD",
                    scope=aggregated.scope,
                    scope_id=aggregated.scope_id,
                    metric=metric,
                    level=new_level,
                    current_value=current_value,
                    threshold_value=threshold_value,
                    message=message,
                    created_at=now,
                )
                alerts.append(alert)

            # Update state
            if current_state is None or level_changed:
                # Create new state
                self._states[state_key] = AlertState(
                    scope=aggregated.scope,
                    scope_id=aggregated.scope_id,
                    metric=metric,
                    current_level=new_level,
                    current_value=current_value,
                    threshold_config=threshold_config,
                    entered_at=now,
                    last_alert_at=now if should_alert else None,
                    ttl_seconds=self._state_ttl_seconds,
                )
            else:
                # Update existing state
                current_state.current_value = current_value
                if should_alert:
                    current_state.last_alert_at = now

            # Check rate of change if we have previous Greeks
            if prev_greeks is not None:
                prev_value = self._get_metric_value(prev_greeks, metric)
                if prev_value is not None:
                    roc_alert = self._check_rate_of_change(
                        metric=metric,
                        current_value=current_value,
                        prev_value=prev_value,
                        config=threshold_config,
                    )
                    if roc_alert is not None:
                        # Set the scope from aggregated
                        roc_alert.scope = aggregated.scope
                        roc_alert.scope_id = aggregated.scope_id
                        alerts.append(roc_alert)

        return alerts

    def cleanup_expired_states(self) -> int:
        """Remove expired AlertState entries.

        Returns:
            Count of removed entries.
        """
        expired_keys = [key for key, state in self._states.items() if state.is_expired()]
        for key in expired_keys:
            del self._states[key]
        return len(expired_keys)

    def get_state(self, scope: str, scope_id: str, metric: RiskMetric) -> AlertState | None:
        """Get current AlertState for a scope/metric.

        Args:
            scope: "ACCOUNT" or "STRATEGY"
            scope_id: Account or strategy identifier
            metric: The RiskMetric to get state for

        Returns:
            The AlertState if it exists, None otherwise.
        """
        return self._states.get((scope, scope_id, metric))
