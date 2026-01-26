"""Tests for circuit breakers with hysteresis.

Circuit breakers provide component-level failure detection with hysteresis tracking.
They report events to the central SystemStateService but can also take local protective action.

Key concepts:
- SystemLevel states: HEALTHY, UNSTABLE, TRIPPED
- Hysteresis: Prevents flapping - need N failures or T seconds before UNSTABLE -> TRIPPED
- Local can only tighten: Component breakers can be more restrictive than central policy

Test cases:
- test_initial_state_healthy: Breaker starts in HEALTHY state
- test_single_failure_goes_unstable: Single failure transitions to UNSTABLE
- test_threshold_failures_trips: N failures trigger TRIPPED state
- test_success_resets_to_healthy: Success resets state to HEALTHY
- test_trip_time_threshold: Time-based trip threshold (T seconds in UNSTABLE)
- test_local_can_only_tighten: Local level can only be more restrictive than central
"""

from __future__ import annotations

import time

import pytest
from src.degradation.breakers import (
    BreakerState,
    BrokerBreaker,
    DBBreaker,
    MarketDataBreaker,
    RiskBreaker,
)
from src.degradation.config import DegradationConfig
from src.degradation.models import (
    ComponentSource,
    EventType,
    ReasonCode,
    SystemLevel,
)


@pytest.fixture
def config() -> DegradationConfig:
    """Test configuration with controllable thresholds."""
    return DegradationConfig(
        fail_threshold_count=3,
        fail_threshold_seconds=5.0,
        recovery_stable_seconds=1.0,
    )


@pytest.fixture
def broker_breaker(config: DegradationConfig) -> BrokerBreaker:
    """BrokerBreaker fixture."""
    return BrokerBreaker(config)


@pytest.fixture
def market_data_breaker(config: DegradationConfig) -> MarketDataBreaker:
    """MarketDataBreaker fixture."""
    return MarketDataBreaker(config)


@pytest.fixture
def risk_breaker(config: DegradationConfig) -> RiskBreaker:
    """RiskBreaker fixture."""
    return RiskBreaker(config)


@pytest.fixture
def db_breaker(config: DegradationConfig) -> DBBreaker:
    """DBBreaker fixture."""
    return DBBreaker(config)


class TestBreakerState:
    """Tests for BreakerState dataclass."""

    def test_default_state_is_healthy(self) -> None:
        """Default BreakerState is HEALTHY with zero failures."""
        state = BreakerState()
        assert state.level == SystemLevel.HEALTHY
        assert state.failure_count == 0
        assert state.first_failure_mono is None
        assert state.last_success_mono is None


class TestCircuitBreakerInitialState:
    """Tests for circuit breaker initial state."""

    def test_initial_state_healthy(self, broker_breaker: BrokerBreaker) -> None:
        """Breaker starts in HEALTHY state."""
        assert broker_breaker.level == SystemLevel.HEALTHY
        assert broker_breaker.is_tripped is False

    def test_initial_state_healthy_all_breakers(
        self,
        broker_breaker: BrokerBreaker,
        market_data_breaker: MarketDataBreaker,
        risk_breaker: RiskBreaker,
        db_breaker: DBBreaker,
    ) -> None:
        """All specialized breakers start in HEALTHY state."""
        for breaker in [broker_breaker, market_data_breaker, risk_breaker, db_breaker]:
            assert breaker.level == SystemLevel.HEALTHY
            assert breaker.is_tripped is False


class TestSingleFailure:
    """Tests for single failure behavior."""

    def test_single_failure_goes_unstable(self, broker_breaker: BrokerBreaker) -> None:
        """Single failure transitions to UNSTABLE state."""
        event = broker_breaker.record_failure()

        assert broker_breaker.level == SystemLevel.UNSTABLE
        assert broker_breaker.is_tripped is False
        assert event is not None
        assert event.event_type == EventType.QUALITY_DEGRADED
        assert event.source == ComponentSource.BROKER

    def test_single_failure_increments_count(self, broker_breaker: BrokerBreaker) -> None:
        """Single failure increments failure count to 1."""
        broker_breaker.record_failure()

        assert broker_breaker.failure_count == 1

    def test_single_failure_sets_first_failure_time(self, broker_breaker: BrokerBreaker) -> None:
        """First failure records the timestamp."""
        before = time.monotonic()
        broker_breaker.record_failure()
        after = time.monotonic()

        assert broker_breaker.first_failure_mono is not None
        assert before <= broker_breaker.first_failure_mono <= after


class TestThresholdFailures:
    """Tests for failure threshold behavior."""

    def test_threshold_failures_trips(self, config: DegradationConfig) -> None:
        """N failures trigger TRIPPED state."""
        breaker = BrokerBreaker(config)
        # fail_threshold_count is 3

        # First failure -> UNSTABLE
        breaker.record_failure()
        assert breaker.level == SystemLevel.UNSTABLE

        # Second failure -> still UNSTABLE
        breaker.record_failure()
        assert breaker.level == SystemLevel.UNSTABLE

        # Third failure -> TRIPPED
        event = breaker.record_failure()
        assert breaker.level == SystemLevel.TRIPPED
        assert breaker.is_tripped is True
        assert event is not None
        assert event.event_type == EventType.FAIL_CRIT

    def test_failures_below_threshold_stay_unstable(self, config: DegradationConfig) -> None:
        """Failures below threshold stay UNSTABLE."""
        breaker = BrokerBreaker(config)
        # fail_threshold_count is 3, so 2 failures should stay UNSTABLE

        breaker.record_failure()
        breaker.record_failure()

        assert breaker.level == SystemLevel.UNSTABLE
        assert breaker.failure_count == 2
        assert breaker.is_tripped is False

    def test_already_tripped_stays_tripped_on_more_failures(
        self, config: DegradationConfig
    ) -> None:
        """Once tripped, additional failures keep it tripped."""
        breaker = BrokerBreaker(config)

        # Trip the breaker
        for _ in range(config.fail_threshold_count):
            breaker.record_failure()
        assert breaker.level == SystemLevel.TRIPPED

        # Additional failures should keep it TRIPPED
        event = breaker.record_failure()
        assert breaker.level == SystemLevel.TRIPPED
        # No state change event when already TRIPPED
        assert event is None


class TestSuccessResets:
    """Tests for success reset behavior."""

    def test_success_resets_to_healthy_from_unstable(self, broker_breaker: BrokerBreaker) -> None:
        """Success resets state from UNSTABLE to HEALTHY."""
        # Go to UNSTABLE
        broker_breaker.record_failure()
        assert broker_breaker.level == SystemLevel.UNSTABLE

        # Record success
        event = broker_breaker.record_success()

        assert broker_breaker.level == SystemLevel.HEALTHY
        assert broker_breaker.failure_count == 0
        assert event is not None
        assert event.event_type == EventType.RECOVERED

    def test_success_resets_to_healthy_from_tripped(self, config: DegradationConfig) -> None:
        """Success resets state from TRIPPED to HEALTHY."""
        breaker = BrokerBreaker(config)

        # Trip the breaker
        for _ in range(config.fail_threshold_count):
            breaker.record_failure()
        assert breaker.level == SystemLevel.TRIPPED

        # Record success
        event = breaker.record_success()

        assert breaker.level == SystemLevel.HEALTHY
        assert breaker.failure_count == 0
        assert breaker.first_failure_mono is None
        assert event is not None
        assert event.event_type == EventType.RECOVERED

    def test_success_on_healthy_no_event(self, broker_breaker: BrokerBreaker) -> None:
        """Success when already HEALTHY produces no event."""
        event = broker_breaker.record_success()

        assert broker_breaker.level == SystemLevel.HEALTHY
        assert event is None

    def test_success_clears_failure_time(self, broker_breaker: BrokerBreaker) -> None:
        """Success clears the first failure timestamp."""
        broker_breaker.record_failure()
        assert broker_breaker.first_failure_mono is not None

        broker_breaker.record_success()

        assert broker_breaker.first_failure_mono is None


class TestTripTimeThreshold:
    """Tests for time-based trip threshold."""

    def test_trip_time_threshold(self) -> None:
        """Time-based trip threshold (T seconds in UNSTABLE)."""
        # Use very short time threshold for testing
        config = DegradationConfig(
            fail_threshold_count=100,  # High count so time triggers first
            fail_threshold_seconds=0.1,  # 100ms threshold
        )
        breaker = BrokerBreaker(config)

        # First failure -> UNSTABLE
        breaker.record_failure()
        assert breaker.level == SystemLevel.UNSTABLE

        # Wait for time threshold to expire
        time.sleep(0.15)

        # Next failure should trigger TRIPPED due to time threshold
        event = breaker.record_failure()
        assert breaker.level == SystemLevel.TRIPPED
        assert event is not None
        assert event.event_type == EventType.FAIL_CRIT

    def test_trip_conditions_check_both_count_and_time(self) -> None:
        """Trip conditions can be triggered by either count OR time."""
        # Time threshold is high, count threshold is low
        config = DegradationConfig(
            fail_threshold_count=2,
            fail_threshold_seconds=100.0,  # Very long time
        )
        breaker = BrokerBreaker(config)

        # Two failures should trip by count
        breaker.record_failure()
        event = breaker.record_failure()

        assert breaker.level == SystemLevel.TRIPPED
        assert event is not None


class TestLocalCanOnlyTighten:
    """Tests for local-can-only-tighten policy."""

    def test_local_can_only_tighten_tighter_allowed(self, broker_breaker: BrokerBreaker) -> None:
        """Local breaker can be more restrictive than central."""
        # Central says HEALTHY, but local is UNSTABLE
        central_level = SystemLevel.HEALTHY

        # Record a failure locally
        broker_breaker.record_failure()

        # Local level (UNSTABLE) is tighter than central (HEALTHY)
        effective = broker_breaker.effective_level(central_level)
        assert effective == SystemLevel.UNSTABLE

    def test_local_can_only_tighten_looser_blocked(self, broker_breaker: BrokerBreaker) -> None:
        """Local breaker cannot be less restrictive than central."""
        # Central says TRIPPED, but local is HEALTHY
        central_level = SystemLevel.TRIPPED

        # Local is HEALTHY
        assert broker_breaker.level == SystemLevel.HEALTHY

        # Effective level should be TRIPPED (central takes precedence)
        effective = broker_breaker.effective_level(central_level)
        assert effective == SystemLevel.TRIPPED

    def test_local_can_only_tighten_same_level(self, config: DegradationConfig) -> None:
        """When local and central are same, effective is that level."""
        breaker = BrokerBreaker(config)

        # Trip the breaker locally
        for _ in range(config.fail_threshold_count):
            breaker.record_failure()
        assert breaker.level == SystemLevel.TRIPPED

        # Central is also TRIPPED
        central_level = SystemLevel.TRIPPED

        # Effective should be TRIPPED
        effective = breaker.effective_level(central_level)
        assert effective == SystemLevel.TRIPPED


class TestSpecializedBreakers:
    """Tests for specialized breaker implementations."""

    def test_broker_breaker_source(self, broker_breaker: BrokerBreaker) -> None:
        """BrokerBreaker uses BROKER source."""
        event = broker_breaker.record_failure()
        assert event is not None
        assert event.source == ComponentSource.BROKER

    def test_market_data_breaker_source(self, market_data_breaker: MarketDataBreaker) -> None:
        """MarketDataBreaker uses MARKET_DATA source."""
        event = market_data_breaker.record_failure()
        assert event is not None
        assert event.source == ComponentSource.MARKET_DATA

    def test_risk_breaker_source(self, risk_breaker: RiskBreaker) -> None:
        """RiskBreaker uses RISK source."""
        event = risk_breaker.record_failure()
        assert event is not None
        assert event.source == ComponentSource.RISK

    def test_db_breaker_source(self, db_breaker: DBBreaker) -> None:
        """DBBreaker uses DB source."""
        event = db_breaker.record_failure()
        assert event is not None
        assert event.source == ComponentSource.DB


class TestBreakerReasonCodes:
    """Tests for breaker reason codes in events."""

    def test_broker_breaker_reason_code_on_trip(self, config: DegradationConfig) -> None:
        """BrokerBreaker emits BROKER_DISCONNECT reason code on trip."""
        breaker = BrokerBreaker(config)

        # Trip the breaker
        for _ in range(config.fail_threshold_count - 1):
            breaker.record_failure()
        event = breaker.record_failure()

        assert event is not None
        assert event.reason_code == ReasonCode.BROKER_DISCONNECT

    def test_market_data_breaker_reason_code_on_trip(self, config: DegradationConfig) -> None:
        """MarketDataBreaker emits MD_STALE reason code on trip."""
        breaker = MarketDataBreaker(config)

        # Trip the breaker
        for _ in range(config.fail_threshold_count - 1):
            breaker.record_failure()
        event = breaker.record_failure()

        assert event is not None
        assert event.reason_code == ReasonCode.MD_STALE

    def test_risk_breaker_reason_code_on_trip(self, config: DegradationConfig) -> None:
        """RiskBreaker emits RISK_TIMEOUT reason code on trip."""
        breaker = RiskBreaker(config)

        # Trip the breaker
        for _ in range(config.fail_threshold_count - 1):
            breaker.record_failure()
        event = breaker.record_failure()

        assert event is not None
        assert event.reason_code == ReasonCode.RISK_TIMEOUT

    def test_db_breaker_reason_code_on_trip(self, config: DegradationConfig) -> None:
        """DBBreaker emits DB_WRITE_FAIL reason code on trip."""
        breaker = DBBreaker(config)

        # Trip the breaker
        for _ in range(config.fail_threshold_count - 1):
            breaker.record_failure()
        event = breaker.record_failure()

        assert event is not None
        assert event.reason_code == ReasonCode.DB_WRITE_FAIL


class TestBreakerRecoveryReasonCodes:
    """Tests for recovery reason codes in events."""

    def test_broker_breaker_recovery_reason_code(self, config: DegradationConfig) -> None:
        """BrokerBreaker emits BROKER_RECONNECTED reason code on recovery."""
        breaker = BrokerBreaker(config)

        # Trip and recover
        for _ in range(config.fail_threshold_count):
            breaker.record_failure()
        event = breaker.record_success()

        assert event is not None
        assert event.reason_code == ReasonCode.BROKER_RECONNECTED

    def test_db_breaker_recovery_reason_code(self, config: DegradationConfig) -> None:
        """DBBreaker emits ALL_HEALTHY reason code on recovery (no specific code)."""
        breaker = DBBreaker(config)

        # Trip and recover
        for _ in range(config.fail_threshold_count):
            breaker.record_failure()
        event = breaker.record_success()

        assert event is not None
        # DB doesn't have a specific reconnected code, uses generic
        assert event.reason_code == ReasonCode.ALL_HEALTHY


class TestBreakerProperties:
    """Tests for breaker property accessors."""

    def test_failure_count_property(self, broker_breaker: BrokerBreaker) -> None:
        """failure_count property returns current failure count."""
        assert broker_breaker.failure_count == 0

        broker_breaker.record_failure()
        assert broker_breaker.failure_count == 1

        broker_breaker.record_failure()
        assert broker_breaker.failure_count == 2

    def test_first_failure_mono_property(self, broker_breaker: BrokerBreaker) -> None:
        """first_failure_mono property returns first failure timestamp."""
        assert broker_breaker.first_failure_mono is None

        broker_breaker.record_failure()
        mono1 = broker_breaker.first_failure_mono
        assert mono1 is not None

        # Second failure should not change first_failure_mono
        time.sleep(0.01)
        broker_breaker.record_failure()
        assert broker_breaker.first_failure_mono == mono1

    def test_source_property(
        self,
        broker_breaker: BrokerBreaker,
        market_data_breaker: MarketDataBreaker,
        risk_breaker: RiskBreaker,
        db_breaker: DBBreaker,
    ) -> None:
        """source property returns the component source."""
        assert broker_breaker.source == ComponentSource.BROKER
        assert market_data_breaker.source == ComponentSource.MARKET_DATA
        assert risk_breaker.source == ComponentSource.RISK
        assert db_breaker.source == ComponentSource.DB
