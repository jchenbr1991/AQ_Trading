"""Tests for SystemStateService.

The SystemStateService is the SINGLE SOURCE OF TRUTH for system mode.
Only this service can modify the system state.

Test cases:
- test_cold_start_is_recovering: System starts in RECOVERING mode with CONNECT_BROKER stage
- test_transition_to_safe_mode: On broker disconnect, transitions to SAFE_MODE_DISCONNECTED
- test_takes_most_severe: Conflict resolution takes the most severe mode
- test_cannot_downgrade_without_recovery: Cannot downgrade to less severe mode without recovery
- test_force_mode_with_ttl: Manual override with TTL
- test_force_override_blocks_auto_transitions: Force override blocks automatic transitions
"""

from __future__ import annotations

import asyncio

import pytest
from src.degradation.config import DegradationConfig
from src.degradation.event_bus import EventBus
from src.degradation.models import (
    MODE_PRIORITY,
    ComponentSource,
    EventType,
    ReasonCode,
    RecoveryStage,
    Severity,
    SystemEvent,
    SystemMode,
    create_event,
)
from src.degradation.state_service import (
    DECISION_MATRIX,
    SystemStateService,
)
from src.degradation.trading_gate import TradingGate


@pytest.fixture
def config() -> DegradationConfig:
    """Test configuration with shorter timeouts."""
    return DegradationConfig(
        min_safe_mode_seconds=1.0,  # Short for testing
        recovery_stable_seconds=0.5,
    )


@pytest.fixture
def trading_gate() -> TradingGate:
    """TradingGate fixture."""
    return TradingGate()


@pytest.fixture
def event_bus(config: DegradationConfig) -> EventBus:
    """EventBus fixture."""
    return EventBus(config)


@pytest.fixture
def state_service(
    config: DegradationConfig, trading_gate: TradingGate, event_bus: EventBus
) -> SystemStateService:
    """SystemStateService fixture."""
    return SystemStateService(config, trading_gate, event_bus)


class TestColdStart:
    """Tests for cold start behavior."""

    def test_cold_start_is_recovering(
        self,
        config: DegradationConfig,
        trading_gate: TradingGate,
        event_bus: EventBus,
    ) -> None:
        """System starts in RECOVERING mode with CONNECT_BROKER stage."""
        service = SystemStateService(config, trading_gate, event_bus)

        assert service.mode == SystemMode.RECOVERING
        assert service.stage == RecoveryStage.CONNECT_BROKER
        assert service.is_force_override is False

    def test_trading_gate_updated_on_init(
        self,
        config: DegradationConfig,
        trading_gate: TradingGate,
        event_bus: EventBus,
    ) -> None:
        """TradingGate is updated to match initial state."""
        service = SystemStateService(config, trading_gate, event_bus)

        assert trading_gate.mode == SystemMode.RECOVERING
        assert trading_gate.stage == RecoveryStage.CONNECT_BROKER


class TestDecisionMatrix:
    """Tests for the decision matrix mapping."""

    def test_decision_matrix_has_all_required_mappings(self) -> None:
        """Decision matrix maps all required ReasonCodes to target modes."""
        required_mappings = {
            ReasonCode.BROKER_DISCONNECT: SystemMode.SAFE_MODE_DISCONNECTED,
            ReasonCode.BROKER_RECONNECTED: SystemMode.RECOVERING,
            ReasonCode.BROKER_REPORT_MISMATCH: SystemMode.HALT,
            ReasonCode.MD_STALE: SystemMode.SAFE_MODE,
            ReasonCode.RISK_TIMEOUT: SystemMode.SAFE_MODE,
            ReasonCode.RISK_BREACH_HARD: SystemMode.HALT,
            ReasonCode.POSITION_TRUTH_UNKNOWN: SystemMode.HALT,
            ReasonCode.DB_WRITE_FAIL: SystemMode.DEGRADED,
            ReasonCode.DB_BUFFER_OVERFLOW: SystemMode.SAFE_MODE,
            ReasonCode.ALERTS_CHANNEL_DOWN: SystemMode.DEGRADED,
            ReasonCode.RECOVERY_FAILED: SystemMode.HALT,
            ReasonCode.ALL_HEALTHY: SystemMode.NORMAL,
        }

        for reason_code, expected_mode in required_mappings.items():
            assert (
                DECISION_MATRIX[reason_code] == expected_mode
            ), f"Expected {reason_code} -> {expected_mode}, got {DECISION_MATRIX.get(reason_code)}"


class TestModeTransitions:
    """Tests for mode transitions."""

    @pytest.mark.asyncio
    async def test_transition_to_safe_mode_disconnected_on_broker_disconnect(
        self, state_service: SystemStateService
    ) -> None:
        """On broker disconnect, transitions to SAFE_MODE_DISCONNECTED."""
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )

        await state_service.handle_event(event)

        assert state_service.mode == SystemMode.SAFE_MODE_DISCONNECTED

    @pytest.mark.asyncio
    async def test_transition_to_safe_mode_on_md_stale(
        self, state_service: SystemStateService
    ) -> None:
        """On market data stale, transitions to SAFE_MODE."""
        # First move to NORMAL
        await state_service.handle_event(
            create_event(
                event_type=EventType.RECOVERED,
                source=ComponentSource.SYSTEM,
                severity=Severity.INFO,
                reason_code=ReasonCode.ALL_HEALTHY,
            )
        )
        assert state_service.mode == SystemMode.NORMAL

        # Now trigger MD_STALE
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.MARKET_DATA,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.MD_STALE,
        )

        await state_service.handle_event(event)

        assert state_service.mode == SystemMode.SAFE_MODE

    @pytest.mark.asyncio
    async def test_transition_to_halt_on_position_unknown(
        self, state_service: SystemStateService
    ) -> None:
        """On position truth unknown, transitions to HALT."""
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.RISK,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.POSITION_TRUTH_UNKNOWN,
        )

        await state_service.handle_event(event)

        assert state_service.mode == SystemMode.HALT

    @pytest.mark.asyncio
    async def test_transition_to_degraded_on_db_write_fail(
        self, state_service: SystemStateService
    ) -> None:
        """On DB write fail (buffered), transitions to DEGRADED."""
        # First move to NORMAL
        await state_service.handle_event(
            create_event(
                event_type=EventType.RECOVERED,
                source=ComponentSource.SYSTEM,
                severity=Severity.INFO,
                reason_code=ReasonCode.ALL_HEALTHY,
            )
        )

        event = create_event(
            event_type=EventType.FAIL_SUPP,
            source=ComponentSource.DB,
            severity=Severity.WARNING,
            reason_code=ReasonCode.DB_WRITE_FAIL,
        )

        await state_service.handle_event(event)

        assert state_service.mode == SystemMode.DEGRADED

    @pytest.mark.asyncio
    async def test_trading_gate_updated_on_mode_change(
        self, state_service: SystemStateService, trading_gate: TradingGate
    ) -> None:
        """TradingGate is updated when mode changes."""
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )

        await state_service.handle_event(event)

        assert trading_gate.mode == SystemMode.SAFE_MODE_DISCONNECTED


class TestConflictResolution:
    """Tests for conflict resolution (takes most severe mode)."""

    @pytest.mark.asyncio
    async def test_takes_most_severe_mode(self, state_service: SystemStateService) -> None:
        """When multiple events occur, take the most severe mode."""
        # First move to NORMAL
        await state_service.handle_event(
            create_event(
                event_type=EventType.RECOVERED,
                source=ComponentSource.SYSTEM,
                severity=Severity.INFO,
                reason_code=ReasonCode.ALL_HEALTHY,
            )
        )

        # Send DB_WRITE_FAIL (DEGRADED) first
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_SUPP,
                source=ComponentSource.DB,
                severity=Severity.WARNING,
                reason_code=ReasonCode.DB_WRITE_FAIL,
            )
        )
        assert state_service.mode == SystemMode.DEGRADED

        # Send MD_STALE (SAFE_MODE) - should escalate
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_CRIT,
                source=ComponentSource.MARKET_DATA,
                severity=Severity.CRITICAL,
                reason_code=ReasonCode.MD_STALE,
            )
        )
        assert state_service.mode == SystemMode.SAFE_MODE

        # Send BROKER_DISCONNECT (SAFE_MODE_DISCONNECTED) - should escalate
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_CRIT,
                source=ComponentSource.BROKER,
                severity=Severity.CRITICAL,
                reason_code=ReasonCode.BROKER_DISCONNECT,
            )
        )
        assert state_service.mode == SystemMode.SAFE_MODE_DISCONNECTED

        # Send POSITION_TRUTH_UNKNOWN (HALT) - should escalate
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_CRIT,
                source=ComponentSource.RISK,
                severity=Severity.CRITICAL,
                reason_code=ReasonCode.POSITION_TRUTH_UNKNOWN,
            )
        )
        assert state_service.mode == SystemMode.HALT

    @pytest.mark.asyncio
    async def test_cannot_downgrade_without_recovery(
        self, state_service: SystemStateService
    ) -> None:
        """Cannot downgrade to less severe mode without recovery."""
        # Escalate to SAFE_MODE
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_CRIT,
                source=ComponentSource.MARKET_DATA,
                severity=Severity.CRITICAL,
                reason_code=ReasonCode.MD_STALE,
            )
        )
        assert state_service.mode == SystemMode.SAFE_MODE

        # Try to downgrade via DB_WRITE_FAIL (DEGRADED) - should be ignored
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_SUPP,
                source=ComponentSource.DB,
                severity=Severity.WARNING,
                reason_code=ReasonCode.DB_WRITE_FAIL,
            )
        )
        # Should still be SAFE_MODE, not DEGRADED
        assert state_service.mode == SystemMode.SAFE_MODE

    @pytest.mark.asyncio
    async def test_cannot_go_to_normal_without_all_healthy(
        self, state_service: SystemStateService
    ) -> None:
        """Cannot transition to NORMAL without ALL_HEALTHY event."""
        # In RECOVERING mode
        assert state_service.mode == SystemMode.RECOVERING

        # Try to send a RECOVERED event for a single component
        await state_service.handle_event(
            create_event(
                event_type=EventType.RECOVERED,
                source=ComponentSource.BROKER,
                severity=Severity.INFO,
                reason_code=ReasonCode.BROKER_RECONNECTED,
            )
        )

        # Should still not be NORMAL - BROKER_RECONNECTED -> RECOVERING
        assert state_service.mode == SystemMode.RECOVERING


class TestRecoveryStageProgression:
    """Tests for recovery stage progression."""

    def test_update_recovery_stage(self, state_service: SystemStateService) -> None:
        """Can update recovery stage when in RECOVERING mode."""
        assert state_service.stage == RecoveryStage.CONNECT_BROKER

        state_service.update_recovery_stage(RecoveryStage.CATCHUP_MARKETDATA)
        assert state_service.stage == RecoveryStage.CATCHUP_MARKETDATA

        state_service.update_recovery_stage(RecoveryStage.VERIFY_RISK)
        assert state_service.stage == RecoveryStage.VERIFY_RISK

        state_service.update_recovery_stage(RecoveryStage.READY)
        assert state_service.stage == RecoveryStage.READY

    def test_update_recovery_stage_updates_trading_gate(
        self, state_service: SystemStateService, trading_gate: TradingGate
    ) -> None:
        """Updating recovery stage also updates TradingGate."""
        state_service.update_recovery_stage(RecoveryStage.VERIFY_RISK)

        assert trading_gate.stage == RecoveryStage.VERIFY_RISK

    def test_update_recovery_stage_fails_when_not_recovering(
        self, state_service: SystemStateService
    ) -> None:
        """Cannot update recovery stage when not in RECOVERING mode."""
        # Force transition to a non-recovering mode
        state_service._mode = SystemMode.NORMAL
        state_service._stage = None

        with pytest.raises(ValueError, match="not in RECOVERING mode"):
            state_service.update_recovery_stage(RecoveryStage.READY)


class TestForceOverride:
    """Tests for force override (manual mode control)."""

    @pytest.mark.asyncio
    async def test_force_mode_with_ttl(self, state_service: SystemStateService) -> None:
        """Force mode sets the mode with TTL and marks as override."""
        await state_service.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=60,
            operator_id="test_operator",
            reason="Testing force mode",
        )

        assert state_service.mode == SystemMode.HALT
        assert state_service.is_force_override is True

    @pytest.mark.asyncio
    async def test_force_override_blocks_auto_transitions(
        self, state_service: SystemStateService
    ) -> None:
        """Force override blocks automatic transitions."""
        # Force to HALT
        await state_service.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=60,
            operator_id="test_operator",
            reason="Testing force mode",
        )
        assert state_service.mode == SystemMode.HALT

        # Try to transition via event - should be blocked
        await state_service.handle_event(
            create_event(
                event_type=EventType.RECOVERED,
                source=ComponentSource.SYSTEM,
                severity=Severity.INFO,
                reason_code=ReasonCode.ALL_HEALTHY,
            )
        )

        # Should still be HALT due to override
        assert state_service.mode == SystemMode.HALT
        assert state_service.is_force_override is True

    @pytest.mark.asyncio
    async def test_force_override_expires_after_ttl(
        self, state_service: SystemStateService
    ) -> None:
        """Force override expires after TTL and resumes auto logic."""
        # Force to SAFE_MODE with very short TTL
        await state_service.force_mode(
            mode=SystemMode.SAFE_MODE,
            ttl_seconds=1,  # 1 second TTL
            operator_id="test_operator",
            reason="Testing TTL expiry",
        )
        assert state_service.mode == SystemMode.SAFE_MODE
        assert state_service.is_force_override is True

        # Wait for TTL to expire
        await asyncio.sleep(1.1)

        # Override should be expired
        assert state_service.is_force_override is False

        # Now auto transitions should work
        await state_service.handle_event(
            create_event(
                event_type=EventType.RECOVERED,
                source=ComponentSource.SYSTEM,
                severity=Severity.INFO,
                reason_code=ReasonCode.ALL_HEALTHY,
            )
        )
        assert state_service.mode == SystemMode.NORMAL

    @pytest.mark.asyncio
    async def test_force_mode_updates_trading_gate(
        self, state_service: SystemStateService, trading_gate: TradingGate
    ) -> None:
        """Force mode updates the TradingGate."""
        await state_service.force_mode(
            mode=SystemMode.SAFE_MODE,
            ttl_seconds=60,
            operator_id="test_operator",
            reason="Testing gate update",
        )

        assert trading_gate.mode == SystemMode.SAFE_MODE

    @pytest.mark.asyncio
    async def test_force_mode_requires_operator_id(self, state_service: SystemStateService) -> None:
        """Force mode requires operator ID."""
        with pytest.raises(ValueError, match="operator_id required"):
            await state_service.force_mode(
                mode=SystemMode.HALT,
                ttl_seconds=60,
                operator_id="",  # Empty operator ID
                reason="Testing",
            )

    @pytest.mark.asyncio
    async def test_force_mode_requires_reason(self, state_service: SystemStateService) -> None:
        """Force mode requires reason."""
        with pytest.raises(ValueError, match="reason required"):
            await state_service.force_mode(
                mode=SystemMode.HALT,
                ttl_seconds=60,
                operator_id="test_operator",
                reason="",  # Empty reason
            )

    @pytest.mark.asyncio
    async def test_force_mode_positive_ttl(self, state_service: SystemStateService) -> None:
        """Force mode requires positive TTL."""
        with pytest.raises(ValueError, match="ttl_seconds must be positive"):
            await state_service.force_mode(
                mode=SystemMode.HALT,
                ttl_seconds=0,  # Invalid TTL
                operator_id="test_operator",
                reason="Testing",
            )


class TestTransitionHistory:
    """Tests for transition history tracking."""

    @pytest.mark.asyncio
    async def test_transitions_are_recorded(self, state_service: SystemStateService) -> None:
        """Mode transitions are recorded in history."""
        # Initial state is RECOVERING
        assert len(state_service.transition_history) == 0

        # Trigger a transition
        await state_service.handle_event(
            create_event(
                event_type=EventType.FAIL_CRIT,
                source=ComponentSource.BROKER,
                severity=Severity.CRITICAL,
                reason_code=ReasonCode.BROKER_DISCONNECT,
            )
        )

        assert len(state_service.transition_history) == 1
        transition = state_service.transition_history[0]
        assert transition.from_mode == SystemMode.RECOVERING
        assert transition.to_mode == SystemMode.SAFE_MODE_DISCONNECTED
        assert transition.reason_code == ReasonCode.BROKER_DISCONNECT

    @pytest.mark.asyncio
    async def test_force_mode_recorded_in_history(self, state_service: SystemStateService) -> None:
        """Force mode transitions are recorded with operator ID."""
        await state_service.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=60,
            operator_id="admin@example.com",
            reason="Emergency halt",
        )

        assert len(state_service.transition_history) == 1
        transition = state_service.transition_history[0]
        assert transition.to_mode == SystemMode.HALT
        assert transition.operator_id == "admin@example.com"
        assert transition.override_ttl == 60


class TestModePriority:
    """Tests for mode priority ordering."""

    def test_mode_priority_ordering(self) -> None:
        """MODE_PRIORITY has correct ordering."""
        # Higher number = more severe
        assert MODE_PRIORITY[SystemMode.NORMAL] < MODE_PRIORITY[SystemMode.RECOVERING]
        assert MODE_PRIORITY[SystemMode.RECOVERING] < MODE_PRIORITY[SystemMode.DEGRADED]
        assert MODE_PRIORITY[SystemMode.DEGRADED] < MODE_PRIORITY[SystemMode.SAFE_MODE]
        assert (
            MODE_PRIORITY[SystemMode.SAFE_MODE] < MODE_PRIORITY[SystemMode.SAFE_MODE_DISCONNECTED]
        )
        assert MODE_PRIORITY[SystemMode.SAFE_MODE_DISCONNECTED] < MODE_PRIORITY[SystemMode.HALT]


class TestEventBusIntegration:
    """Tests for EventBus integration."""

    @pytest.mark.asyncio
    async def test_mode_change_published_to_event_bus(
        self, state_service: SystemStateService, event_bus: EventBus
    ) -> None:
        """Mode changes are published to the EventBus."""
        received_events: list[SystemEvent] = []

        async def handler(event: SystemEvent) -> None:
            received_events.append(event)

        event_bus.subscribe(handler)
        await event_bus.start()

        try:
            # Trigger a mode change
            await state_service.handle_event(
                create_event(
                    event_type=EventType.FAIL_CRIT,
                    source=ComponentSource.BROKER,
                    severity=Severity.CRITICAL,
                    reason_code=ReasonCode.BROKER_DISCONNECT,
                )
            )

            # Give time for event to be processed
            await asyncio.sleep(0.2)

            # Check that a mode change event was published
            # The state service should publish the triggering event
            assert len(received_events) >= 1
        finally:
            await event_bus.stop()
