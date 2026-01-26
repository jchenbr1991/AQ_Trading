"""Circuit breakers with hysteresis for component health tracking.

Circuit breakers provide component-level failure detection with hysteresis tracking.
They report events to the central SystemStateService but can also take local
protective action.

Key concepts:
- SystemLevel states: HEALTHY, UNSTABLE, TRIPPED
- Hysteresis: Prevents flapping - need N failures or T seconds before UNSTABLE -> TRIPPED
- Local can only tighten: Component breakers can be more restrictive than central policy

Specialized breakers:
- BrokerBreaker: For broker connection failures
- MarketDataBreaker: For market data staleness
- RiskBreaker: For risk engine timeouts
- DBBreaker: For database connection failures
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.degradation.config import DegradationConfig
from src.degradation.models import (
    ComponentSource,
    EventType,
    ReasonCode,
    Severity,
    SystemEvent,
    SystemLevel,
    create_event,
)

# Level priority for "tighten only" logic (higher = more restrictive)
_LEVEL_PRIORITY: dict[SystemLevel, int] = {
    SystemLevel.HEALTHY: 0,
    SystemLevel.UNSTABLE: 1,
    SystemLevel.TRIPPED: 2,
}


@dataclass
class BreakerState:
    """Internal state for a circuit breaker.

    Tracks the current level, failure count, and timing information
    for hysteresis-based trip decisions.
    """

    level: SystemLevel = SystemLevel.HEALTHY
    failure_count: int = 0
    first_failure_mono: float | None = None
    last_success_mono: float | None = None


class CircuitBreaker:
    """Base circuit breaker for component health tracking.

    Circuit breakers track component health with hysteresis to prevent
    mode flapping. They transition through states:
    - HEALTHY: Normal operation
    - UNSTABLE: Failures detected but not yet tripped
    - TRIPPED: Degradation triggered

    Hysteresis is implemented using two thresholds:
    1. Count threshold: N consecutive failures
    2. Time threshold: T seconds since first failure while UNSTABLE

    Either threshold being met triggers a trip from UNSTABLE to TRIPPED.
    """

    def __init__(
        self,
        source: ComponentSource,
        config: DegradationConfig,
        trip_reason_code: ReasonCode,
        recovery_reason_code: ReasonCode,
    ) -> None:
        """Initialize a circuit breaker.

        Args:
            source: The component this breaker monitors
            config: Degradation configuration with thresholds
            trip_reason_code: ReasonCode to use when tripping
            recovery_reason_code: ReasonCode to use when recovering
        """
        self._source = source
        self._config = config
        self._trip_reason_code = trip_reason_code
        self._recovery_reason_code = recovery_reason_code
        self._state = BreakerState()

    @property
    def level(self) -> SystemLevel:
        """Current system level of this breaker."""
        return self._state.level

    @property
    def is_tripped(self) -> bool:
        """Whether this breaker is currently tripped."""
        return self._state.level == SystemLevel.TRIPPED

    @property
    def source(self) -> ComponentSource:
        """The component source this breaker monitors."""
        return self._source

    @property
    def failure_count(self) -> int:
        """Current consecutive failure count."""
        return self._state.failure_count

    @property
    def first_failure_mono(self) -> float | None:
        """Monotonic timestamp of first failure in current failure window."""
        return self._state.first_failure_mono

    def record_failure(self) -> SystemEvent | None:
        """Record a failure. Returns event if state changed.

        Failure handling:
        1. If HEALTHY: Transition to UNSTABLE
        2. If UNSTABLE: Check trip conditions, maybe trip
        3. If TRIPPED: Stay tripped, no event

        Returns:
            SystemEvent if state changed, None otherwise
        """
        now_mono = time.monotonic()
        old_level = self._state.level

        # Increment failure count
        self._state.failure_count += 1

        # Record first failure timestamp if not set
        if self._state.first_failure_mono is None:
            self._state.first_failure_mono = now_mono

        # State transitions based on current level
        if old_level == SystemLevel.HEALTHY:
            # First failure: go to UNSTABLE
            self._state.level = SystemLevel.UNSTABLE
            return self._create_degraded_event()

        elif old_level == SystemLevel.UNSTABLE:
            # Check if we should trip
            if self._check_trip_conditions(now_mono):
                self._state.level = SystemLevel.TRIPPED
                return self._create_trip_event()
            # Still UNSTABLE, no state change event
            return None

        else:  # TRIPPED
            # Already tripped, no state change
            return None

    def record_success(self) -> SystemEvent | None:
        """Record success. Returns event if recovered.

        Success handling:
        - Reset to HEALTHY regardless of current state
        - Clear failure count and timestamps
        - Only emit event if recovering from non-HEALTHY state

        Returns:
            SystemEvent if recovered from non-HEALTHY, None otherwise
        """
        old_level = self._state.level

        # Reset state
        self._state.level = SystemLevel.HEALTHY
        self._state.failure_count = 0
        self._state.first_failure_mono = None
        self._state.last_success_mono = time.monotonic()

        # Only emit event if we actually recovered
        if old_level != SystemLevel.HEALTHY:
            return self._create_recovery_event()

        return None

    def effective_level(self, central_level: SystemLevel) -> SystemLevel:
        """Get the effective level considering central policy.

        Local can only tighten: the effective level is the MORE restrictive
        of local and central levels.

        Args:
            central_level: The level from the central SystemStateService

        Returns:
            The more restrictive of local and central levels
        """
        local_priority = _LEVEL_PRIORITY[self._state.level]
        central_priority = _LEVEL_PRIORITY[central_level]

        # Take the more restrictive (higher priority)
        if local_priority >= central_priority:
            return self._state.level
        return central_level

    def _check_trip_conditions(self, now_mono: float) -> bool:
        """Check if trip conditions are met using config thresholds.

        Trip conditions (either triggers trip):
        1. Failure count >= fail_threshold_count
        2. Time since first failure >= fail_threshold_seconds

        Args:
            now_mono: Current monotonic timestamp

        Returns:
            True if trip conditions are met, False otherwise
        """
        # Check count threshold
        if self._state.failure_count >= self._config.fail_threshold_count:
            return True

        # Check time threshold
        if self._state.first_failure_mono is not None:
            elapsed = now_mono - self._state.first_failure_mono
            if elapsed >= self._config.fail_threshold_seconds:
                return True

        return False

    def _create_degraded_event(self) -> SystemEvent:
        """Create an event for entering UNSTABLE state."""
        return create_event(
            event_type=EventType.QUALITY_DEGRADED,
            source=self._source,
            severity=Severity.WARNING,
            reason_code=self._trip_reason_code,
            details={
                "level": SystemLevel.UNSTABLE.value,
                "failure_count": self._state.failure_count,
            },
        )

    def _create_trip_event(self) -> SystemEvent:
        """Create an event for entering TRIPPED state."""
        return create_event(
            event_type=EventType.FAIL_CRIT,
            source=self._source,
            severity=Severity.CRITICAL,
            reason_code=self._trip_reason_code,
            details={
                "level": SystemLevel.TRIPPED.value,
                "failure_count": self._state.failure_count,
            },
        )

    def _create_recovery_event(self) -> SystemEvent:
        """Create an event for recovering to HEALTHY state."""
        return create_event(
            event_type=EventType.RECOVERED,
            source=self._source,
            severity=Severity.INFO,
            reason_code=self._recovery_reason_code,
            details={
                "level": SystemLevel.HEALTHY.value,
            },
        )


class BrokerBreaker(CircuitBreaker):
    """Circuit breaker for broker connection failures.

    Monitors broker connectivity and emits BROKER_DISCONNECT on trip
    and BROKER_RECONNECTED on recovery.
    """

    def __init__(self, config: DegradationConfig) -> None:
        """Initialize BrokerBreaker.

        Args:
            config: Degradation configuration with thresholds
        """
        super().__init__(
            source=ComponentSource.BROKER,
            config=config,
            trip_reason_code=ReasonCode.BROKER_DISCONNECT,
            recovery_reason_code=ReasonCode.BROKER_RECONNECTED,
        )


class MarketDataBreaker(CircuitBreaker):
    """Circuit breaker for market data staleness.

    Monitors market data feed health and emits MD_STALE on trip.
    Uses MD_QUALITY_DEGRADED for unstable state events.
    """

    def __init__(self, config: DegradationConfig) -> None:
        """Initialize MarketDataBreaker.

        Args:
            config: Degradation configuration with thresholds
        """
        super().__init__(
            source=ComponentSource.MARKET_DATA,
            config=config,
            trip_reason_code=ReasonCode.MD_STALE,
            recovery_reason_code=ReasonCode.ALL_HEALTHY,
        )


class RiskBreaker(CircuitBreaker):
    """Circuit breaker for risk engine timeouts.

    Monitors risk engine responsiveness and emits RISK_TIMEOUT on trip.
    """

    def __init__(self, config: DegradationConfig) -> None:
        """Initialize RiskBreaker.

        Args:
            config: Degradation configuration with thresholds
        """
        super().__init__(
            source=ComponentSource.RISK,
            config=config,
            trip_reason_code=ReasonCode.RISK_TIMEOUT,
            recovery_reason_code=ReasonCode.ALL_HEALTHY,
        )


class DBBreaker(CircuitBreaker):
    """Circuit breaker for database connection failures.

    Monitors database connectivity and emits DB_WRITE_FAIL on trip.
    """

    def __init__(self, config: DegradationConfig) -> None:
        """Initialize DBBreaker.

        Args:
            config: Degradation configuration with thresholds
        """
        super().__init__(
            source=ComponentSource.DB,
            config=config,
            trip_reason_code=ReasonCode.DB_WRITE_FAIL,
            recovery_reason_code=ReasonCode.ALL_HEALTHY,
        )
