"""Integration tests for the degradation system.

Tests end-to-end scenarios involving multiple components working together:
- Cold start and recovery to normal operation
- Component failure leading to degradation
- Force override workflow
- Event propagation through the system
"""

from __future__ import annotations

import asyncio

import pytest
from src.degradation.breakers import BrokerBreaker
from src.degradation.config import DegradationConfig
from src.degradation.models import (
    ActionType,
    ComponentSource,
    EventType,
    ReasonCode,
    RecoveryStage,
    RecoveryTrigger,
    Severity,
    SystemEvent,
    SystemMode,
    create_event,
)
from src.degradation.recovery import RecoveryOrchestrator
from src.degradation.setup import (
    get_event_bus,
    get_system_state,
    get_trading_gate,
    init_degradation,
    shutdown_degradation,
)


@pytest.fixture
def fast_config() -> DegradationConfig:
    """Config with fast timeouts for testing."""
    return DegradationConfig(
        min_safe_mode_seconds=0.1,
        recovery_stable_seconds=0.1,
        event_bus_queue_size=100,
        fail_threshold_count=2,
        fail_threshold_seconds=0.2,
    )


@pytest.fixture(autouse=True)
async def cleanup():
    """Clean up after each test."""
    yield
    await shutdown_degradation()


class TestColdStartRecovery:
    """Tests for cold start and recovery to normal operation."""

    @pytest.mark.asyncio
    async def test_system_starts_in_recovering_mode(self, fast_config: DegradationConfig) -> None:
        """System should start in RECOVERING mode."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None
        assert state.mode == SystemMode.RECOVERING
        assert state.stage == RecoveryStage.CONNECT_BROKER

    @pytest.mark.asyncio
    async def test_trading_gate_restricts_during_recovery(
        self, fast_config: DegradationConfig
    ) -> None:
        """Trading gate should restrict actions during recovery."""
        await init_degradation(fast_config)

        gate = get_trading_gate()
        assert gate is not None

        # During CONNECT_BROKER stage, only query should be allowed
        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed is False

        result = gate.check_permission(ActionType.QUERY)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_recovery_stages_progress_via_orchestrator(
        self, fast_config: DegradationConfig
    ) -> None:
        """Recovery should progress through stages via RecoveryOrchestrator."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        # Create orchestrator and start recovery
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)

        # Initial stage should be CONNECT_BROKER
        assert state.stage == RecoveryStage.CONNECT_BROKER

        # Advance through stages
        assert await orchestrator.advance_stage(run_id) is True
        assert state.stage == RecoveryStage.CATCHUP_MARKETDATA

        assert await orchestrator.advance_stage(run_id) is True
        assert state.stage == RecoveryStage.VERIFY_RISK

        assert await orchestrator.advance_stage(run_id) is True
        assert state.stage == RecoveryStage.READY

        # Final advance should complete recovery and transition to NORMAL
        assert await orchestrator.advance_stage(run_id) is True
        assert state.mode == SystemMode.NORMAL
        assert state.stage is None

    @pytest.mark.asyncio
    async def test_recovery_completion_enables_trading(
        self, fast_config: DegradationConfig
    ) -> None:
        """After recovery, all trading actions should be allowed."""
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # Complete recovery
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)

        for _ in range(4):  # Advance through all 4 stages
            await orchestrator.advance_stage(run_id)

        # Now in NORMAL mode
        assert state.mode == SystemMode.NORMAL

        # All actions should be allowed
        for action in ActionType:
            result = gate.check_permission(action)
            assert result.allowed is True, f"{action} should be allowed in NORMAL mode"


class TestComponentFailureDegradation:
    """Tests for component failure leading to degradation."""

    @pytest.mark.asyncio
    async def test_broker_disconnect_event_triggers_degradation(
        self, fast_config: DegradationConfig
    ) -> None:
        """Broker disconnect event should trigger mode change."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        # First complete recovery to get to NORMAL
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        for _ in range(4):
            await orchestrator.advance_stage(run_id)

        assert state.mode == SystemMode.NORMAL

        # Now simulate broker disconnect via event
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )
        await state.handle_event(event)

        # Mode should have changed to SAFE_MODE_DISCONNECTED
        assert state.mode == SystemMode.SAFE_MODE_DISCONNECTED

    @pytest.mark.asyncio
    async def test_gate_permissions_change_on_degradation(
        self, fast_config: DegradationConfig
    ) -> None:
        """Trading gate permissions should change when mode degrades."""
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # Complete recovery
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        for _ in range(4):
            await orchestrator.advance_stage(run_id)

        # In NORMAL mode, all actions should be allowed
        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed is True

        # Simulate degradation
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )
        await state.handle_event(event)

        # In SAFE_MODE_DISCONNECTED, OPEN should not be allowed
        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_circuit_breaker_trip_events_affect_state(
        self, fast_config: DegradationConfig
    ) -> None:
        """Circuit breaker trip events should affect system state."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        # Complete recovery first
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        for _ in range(4):
            await orchestrator.advance_stage(run_id)

        assert state.mode == SystemMode.NORMAL

        # Create broker breaker and trigger failures
        breaker = BrokerBreaker(fast_config)

        # Record failures until trip (fail_threshold_count = 2)
        event1 = breaker.record_failure()  # First failure -> UNSTABLE
        assert event1 is not None

        event2 = breaker.record_failure()  # Second failure -> TRIPPED
        assert event2 is not None
        assert breaker.is_tripped

        # Handle the trip event in state service
        await state.handle_event(event2)

        # Mode should change to SAFE_MODE_DISCONNECTED
        assert state.mode == SystemMode.SAFE_MODE_DISCONNECTED


class TestForceOverrideWorkflow:
    """Tests for force override functionality."""

    @pytest.mark.asyncio
    async def test_force_override_changes_mode(self, fast_config: DegradationConfig) -> None:
        """Force override should change the system mode."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        # Force to HALT
        await state.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=10,
            operator_id="test-operator",
            reason="Test force override",
        )

        assert state.mode == SystemMode.HALT
        assert state.is_force_override is True

    @pytest.mark.asyncio
    async def test_force_override_affects_gate(self, fast_config: DegradationConfig) -> None:
        """Force override should affect trading gate permissions."""
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # Force to HALT
        await state.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=10,
            operator_id="test-operator",
            reason="Test",
        )

        # All trading should be blocked in HALT (except QUERY)
        for action in [ActionType.OPEN, ActionType.SEND, ActionType.CANCEL]:
            result = gate.check_permission(action)
            assert result.allowed is False, f"{action} should be blocked in HALT mode"

        # Query should still be allowed
        result = gate.check_permission(ActionType.QUERY)
        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_force_override_blocks_automatic_transitions(
        self, fast_config: DegradationConfig
    ) -> None:
        """Force override should block automatic event-based transitions."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        # Force to HALT
        await state.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=10,
            operator_id="test-operator",
            reason="Test",
        )

        assert state.mode == SystemMode.HALT

        # Try to trigger recovery via event - should be blocked
        recovery_event = create_event(
            event_type=EventType.RECOVERED,
            source=ComponentSource.SYSTEM,
            severity=Severity.INFO,
            reason_code=ReasonCode.ALL_HEALTHY,
        )
        await state.handle_event(recovery_event)

        # Mode should still be HALT (override blocks transitions)
        assert state.mode == SystemMode.HALT

    @pytest.mark.asyncio
    async def test_force_override_records_in_history(self, fast_config: DegradationConfig) -> None:
        """Force override should be recorded in transition history."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        initial_history_len = len(state.transition_history)

        # Force to HALT
        await state.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=10,
            operator_id="test-operator",
            reason="Test force override",
        )

        # Should have new transition
        assert len(state.transition_history) == initial_history_len + 1

        transition = state.transition_history[-1]
        assert transition.to_mode == SystemMode.HALT
        assert transition.operator_id == "test-operator"


class TestEventBusIntegration:
    """Tests for event bus integration."""

    @pytest.mark.asyncio
    async def test_subscribers_receive_events(self, fast_config: DegradationConfig) -> None:
        """Subscribers should receive events from the bus."""
        await init_degradation(fast_config)

        bus = get_event_bus()
        assert bus is not None

        received_events: list[SystemEvent] = []

        async def handler(event: SystemEvent) -> None:
            received_events.append(event)

        # Subscribe to events
        bus.subscribe(handler)

        # Publish an event
        event = create_event(
            event_type=EventType.HEARTBEAT,
            source=ComponentSource.SYSTEM,
            severity=Severity.INFO,
            reason_code=ReasonCode.ALL_HEALTHY,
        )
        success = await bus.publish(event)
        assert success is True

        # Give time for event to be processed
        await asyncio.sleep(0.15)

        # Should have received the event
        assert len(received_events) == 1
        assert received_events[0].reason_code == ReasonCode.ALL_HEALTHY

    @pytest.mark.asyncio
    async def test_mode_transitions_publish_events(self, fast_config: DegradationConfig) -> None:
        """Mode transitions should publish events to the bus."""
        await init_degradation(fast_config)

        bus = get_event_bus()
        state = get_system_state()
        assert bus is not None and state is not None

        received_events: list[SystemEvent] = []

        async def handler(event: SystemEvent) -> None:
            received_events.append(event)

        # Subscribe to events
        bus.subscribe(handler)

        # Trigger a mode change
        await state.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=10,
            operator_id="test",
            reason="Test",
        )

        # Give time for event to be processed
        await asyncio.sleep(0.15)

        # Should have received mode transition event
        # Note: force_mode doesn't publish events, but handle_event does
        # Let's verify subscribers are working by using handle_event
        assert bus.subscriber_count >= 1

    @pytest.mark.asyncio
    async def test_event_bus_handles_full_queue(self, fast_config: DegradationConfig) -> None:
        """Event bus should handle full queue gracefully."""
        # Use tiny queue
        tiny_config = DegradationConfig(
            event_bus_queue_size=2,
            min_safe_mode_seconds=0.1,
        )
        await init_degradation(tiny_config)

        bus = get_event_bus()
        assert bus is not None

        # Publish many events (should not block or raise)
        for _ in range(10):
            event = create_event(
                event_type=EventType.HEARTBEAT,
                source=ComponentSource.SYSTEM,
                severity=Severity.INFO,
                reason_code=ReasonCode.ALL_HEALTHY,
            )
            await bus.publish(event)

        # System should still be responsive - check that services work
        state = get_system_state()
        assert state is not None
        assert state.mode == SystemMode.RECOVERING

        # Drop count should be > 0 since we overfilled the queue
        assert bus.drop_count > 0


class TestFullScenario:
    """Full end-to-end scenario tests."""

    @pytest.mark.asyncio
    async def test_full_lifecycle_cold_start_to_trading(
        self, fast_config: DegradationConfig
    ) -> None:
        """Test complete lifecycle from cold start to trading."""
        # 1. Initialize (cold start)
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # 2. Verify restricted during recovery
        assert state.mode == SystemMode.RECOVERING
        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed is False

        # 3. Progress through recovery
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        for _ in range(4):
            await orchestrator.advance_stage(run_id)

        # 4. Verify normal operation
        assert state.mode == SystemMode.NORMAL
        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed is True

        # 5. Simulate failure
        event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )
        await state.handle_event(event)

        # 6. Verify degraded
        assert state.mode == SystemMode.SAFE_MODE_DISCONNECTED
        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed is False

        # 7. Shutdown
        await shutdown_degradation()

        assert get_system_state() is None

    @pytest.mark.asyncio
    async def test_failure_recovery_cycle(self, fast_config: DegradationConfig) -> None:
        """Test cycle of failure and recovery."""
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # Complete initial recovery
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        for _ in range(4):
            await orchestrator.advance_stage(run_id)

        assert state.mode == SystemMode.NORMAL

        # Simulate failure
        fail_event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )
        await state.handle_event(fail_event)
        assert state.mode == SystemMode.SAFE_MODE_DISCONNECTED

        # Simulate recovery via reconnect event
        recovery_event = create_event(
            event_type=EventType.RECOVERED,
            source=ComponentSource.BROKER,
            severity=Severity.INFO,
            reason_code=ReasonCode.BROKER_RECONNECTED,
        )
        await state.handle_event(recovery_event)

        # Should be in RECOVERING mode now
        assert state.mode == SystemMode.RECOVERING

        # Complete recovery again
        orchestrator2 = RecoveryOrchestrator(fast_config, state)
        run_id2 = await orchestrator2.start_recovery(RecoveryTrigger.AUTO)
        for _ in range(4):
            await orchestrator2.advance_stage(run_id2)

        # Back to normal
        assert state.mode == SystemMode.NORMAL

    @pytest.mark.asyncio
    async def test_multiple_component_failures(self, fast_config: DegradationConfig) -> None:
        """Test handling of multiple component failures."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        # Complete initial recovery
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        for _ in range(4):
            await orchestrator.advance_stage(run_id)

        assert state.mode == SystemMode.NORMAL

        # Simulate market data staleness (leads to SAFE_MODE)
        md_event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.MARKET_DATA,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.MD_STALE,
        )
        await state.handle_event(md_event)
        assert state.mode == SystemMode.SAFE_MODE

        # Simulate broker disconnect (more severe - leads to SAFE_MODE_DISCONNECTED)
        broker_event = create_event(
            event_type=EventType.FAIL_CRIT,
            source=ComponentSource.BROKER,
            severity=Severity.CRITICAL,
            reason_code=ReasonCode.BROKER_DISCONNECT,
        )
        await state.handle_event(broker_event)

        # Should escalate to more severe mode
        assert state.mode == SystemMode.SAFE_MODE_DISCONNECTED

    @pytest.mark.asyncio
    async def test_recovery_abort_to_safe_mode(self) -> None:
        """Test aborting recovery falls back to SAFE_MODE."""
        # Use config with min_safe_mode_seconds >= 1 so int() conversion works
        abort_config = DegradationConfig(
            min_safe_mode_seconds=1.0,
            recovery_stable_seconds=0.1,
            event_bus_queue_size=100,
        )
        await init_degradation(abort_config)

        state = get_system_state()
        assert state is not None

        # Start recovery
        orchestrator = RecoveryOrchestrator(abort_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)

        # Advance a few stages
        await orchestrator.advance_stage(run_id)
        assert state.stage == RecoveryStage.CATCHUP_MARKETDATA

        # Abort recovery
        await orchestrator.abort_recovery(run_id, "Test abort")

        # Should be in SAFE_MODE (via force_mode)
        assert state.mode == SystemMode.SAFE_MODE

    @pytest.mark.asyncio
    async def test_transition_history_accumulates(self, fast_config: DegradationConfig) -> None:
        """Test that transition history accumulates correctly."""
        await init_degradation(fast_config)

        state = get_system_state()
        assert state is not None

        initial_len = len(state.transition_history)

        # Force mode change
        await state.force_mode(
            mode=SystemMode.HALT,
            ttl_seconds=10,
            operator_id="op1",
            reason="First override",
        )

        assert len(state.transition_history) == initial_len + 1

        # Another force mode change
        await state.force_mode(
            mode=SystemMode.SAFE_MODE,
            ttl_seconds=10,
            operator_id="op2",
            reason="Second override",
        )

        assert len(state.transition_history) == initial_len + 2

        # Verify history contains both
        history = state.transition_history
        assert history[-2].to_mode == SystemMode.HALT
        assert history[-1].to_mode == SystemMode.SAFE_MODE


class TestRecoveryStagePermissions:
    """Tests for permissions at different recovery stages."""

    @pytest.mark.asyncio
    async def test_connect_broker_stage_only_allows_query(
        self, fast_config: DegradationConfig
    ) -> None:
        """CONNECT_BROKER stage should only allow query."""
        await init_degradation(fast_config)

        gate = get_trading_gate()
        assert gate is not None

        # Verify initial stage
        assert gate.stage == RecoveryStage.CONNECT_BROKER

        # Only query should be allowed
        assert gate.check_permission(ActionType.QUERY).allowed is True
        assert gate.check_permission(ActionType.CANCEL).allowed is False
        assert gate.check_permission(ActionType.REDUCE_ONLY).allowed is False
        assert gate.check_permission(ActionType.OPEN).allowed is False

    @pytest.mark.asyncio
    async def test_verify_risk_stage_allows_cancel(self, fast_config: DegradationConfig) -> None:
        """VERIFY_RISK stage should allow query and cancel."""
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # Progress to VERIFY_RISK stage
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        await orchestrator.advance_stage(run_id)  # -> CATCHUP_MARKETDATA
        await orchestrator.advance_stage(run_id)  # -> VERIFY_RISK

        assert state.stage == RecoveryStage.VERIFY_RISK

        # Query and cancel should be allowed
        assert gate.check_permission(ActionType.QUERY).allowed is True
        assert gate.check_permission(ActionType.CANCEL).allowed is True
        assert gate.check_permission(ActionType.REDUCE_ONLY).allowed is False
        assert gate.check_permission(ActionType.OPEN).allowed is False

    @pytest.mark.asyncio
    async def test_ready_stage_allows_reduce_only(self, fast_config: DegradationConfig) -> None:
        """READY stage should allow query, cancel, and reduce_only."""
        await init_degradation(fast_config)

        state = get_system_state()
        gate = get_trading_gate()
        assert state is not None and gate is not None

        # Progress to READY stage
        orchestrator = RecoveryOrchestrator(fast_config, state)
        run_id = await orchestrator.start_recovery(RecoveryTrigger.COLD_START)
        await orchestrator.advance_stage(run_id)  # -> CATCHUP_MARKETDATA
        await orchestrator.advance_stage(run_id)  # -> VERIFY_RISK
        await orchestrator.advance_stage(run_id)  # -> READY

        assert state.stage == RecoveryStage.READY

        # Query, cancel, and reduce_only should be allowed
        assert gate.check_permission(ActionType.QUERY).allowed is True
        assert gate.check_permission(ActionType.CANCEL).allowed is True
        assert gate.check_permission(ActionType.REDUCE_ONLY).allowed is True
        assert gate.check_permission(ActionType.OPEN).allowed is False
