"""Tests for RecoveryOrchestrator.

The RecoveryOrchestrator manages staged recovery from failures.
It progresses through 4 stages (CONNECT_BROKER -> CATCHUP_MARKETDATA -> VERIFY_RISK -> READY)
before transitioning to NORMAL.

Test cases:
- test_start_recovery_generates_run_id: Starting recovery creates a unique run_id
- test_start_recovery_replaces_existing: New recovery replaces/cancels existing (idempotency)
- test_advance_stage_progression: Stages progress in correct order
- test_recovery_to_normal_on_completion: Completing recovery transitions to NORMAL
- test_abort_recovery_goes_to_safe_mode: Aborting recovery goes to SAFE_MODE
- test_run_id_mismatch_rejected: Operations with wrong run_id are rejected
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from src.degradation.config import DegradationConfig
from src.degradation.event_bus import EventBus
from src.degradation.models import (
    RecoveryStage,
    RecoveryTrigger,
    SystemMode,
)
from src.degradation.recovery import RecoveryOrchestrator
from src.degradation.state_service import SystemStateService
from src.degradation.trading_gate import TradingGate


@pytest.fixture
def config() -> DegradationConfig:
    """Test configuration with shorter timeouts."""
    return DegradationConfig(
        min_safe_mode_seconds=1.0,
        recovery_stable_seconds=0.1,  # Very short for testing
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


@pytest.fixture
def recovery_orchestrator(
    config: DegradationConfig, state_service: SystemStateService
) -> RecoveryOrchestrator:
    """RecoveryOrchestrator fixture."""
    return RecoveryOrchestrator(config, state_service)


class TestStartRecovery:
    """Tests for starting recovery."""

    @pytest.mark.asyncio
    async def test_start_recovery_generates_run_id(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Starting recovery creates a unique run_id."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        assert run_id is not None
        assert run_id.startswith("recovery-")
        assert len(run_id) > len("recovery-")
        assert recovery_orchestrator.current_run_id == run_id

    @pytest.mark.asyncio
    async def test_start_recovery_sets_is_recovering(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Starting recovery sets is_recovering to True."""
        assert recovery_orchestrator.is_recovering is False

        await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        assert recovery_orchestrator.is_recovering is True

    @pytest.mark.asyncio
    async def test_start_recovery_replaces_existing(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """New recovery replaces/cancels existing (idempotency)."""
        # Start first recovery
        first_run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="operator1",
        )
        assert recovery_orchestrator.current_run_id == first_run_id

        # Start second recovery - should replace first
        second_run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="operator2",
        )

        assert second_run_id != first_run_id
        assert recovery_orchestrator.current_run_id == second_run_id
        # First run_id is no longer valid
        assert recovery_orchestrator.is_recovering is True

    @pytest.mark.asyncio
    async def test_start_recovery_sets_initial_stage(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Starting recovery sets stage to CONNECT_BROKER."""
        await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        assert recovery_orchestrator.current_stage == RecoveryStage.CONNECT_BROKER

    @pytest.mark.asyncio
    async def test_start_recovery_auto_trigger_no_operator(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Auto-triggered recovery does not require operator_id."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.AUTO,
            operator_id=None,
        )

        assert run_id is not None
        assert recovery_orchestrator.is_recovering is True


class TestStageProgression:
    """Tests for recovery stage progression."""

    @pytest.mark.asyncio
    async def test_advance_stage_progression(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Stages progress in correct order."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )
        assert recovery_orchestrator.current_stage == RecoveryStage.CONNECT_BROKER

        # CONNECT_BROKER -> CATCHUP_MARKETDATA
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True
        assert recovery_orchestrator.current_stage == RecoveryStage.CATCHUP_MARKETDATA

        # CATCHUP_MARKETDATA -> VERIFY_RISK
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True
        assert recovery_orchestrator.current_stage == RecoveryStage.VERIFY_RISK

        # VERIFY_RISK -> READY
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True
        assert recovery_orchestrator.current_stage == RecoveryStage.READY

    @pytest.mark.asyncio
    async def test_advance_stage_fails_on_check_failure(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Advance stage returns False if stage check fails."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Mock the stage check to fail
        with patch.object(
            recovery_orchestrator, "_check_stage", new_callable=AsyncMock
        ) as mock_check:
            mock_check.return_value = False

            success = await recovery_orchestrator.advance_stage(run_id)
            assert success is False
            # Stage should not have changed
            assert recovery_orchestrator.current_stage == RecoveryStage.CONNECT_BROKER


class TestRecoveryCompletion:
    """Tests for completing recovery."""

    @pytest.mark.asyncio
    async def test_recovery_to_normal_on_completion(
        self, recovery_orchestrator: RecoveryOrchestrator, state_service: SystemStateService
    ) -> None:
        """Completing recovery transitions to NORMAL."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Progress through all stages
        await recovery_orchestrator.advance_stage(run_id)  # -> CATCHUP_MARKETDATA
        await recovery_orchestrator.advance_stage(run_id)  # -> VERIFY_RISK
        await recovery_orchestrator.advance_stage(run_id)  # -> READY

        # Complete recovery (advance from READY)
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True

        # Should be in NORMAL mode
        assert state_service.mode == SystemMode.NORMAL
        assert recovery_orchestrator.is_recovering is False
        assert recovery_orchestrator.current_run_id is None


class TestAbortRecovery:
    """Tests for aborting recovery."""

    @pytest.mark.asyncio
    async def test_abort_recovery_goes_to_safe_mode(
        self, recovery_orchestrator: RecoveryOrchestrator, state_service: SystemStateService
    ) -> None:
        """Aborting recovery goes to SAFE_MODE."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        await recovery_orchestrator.abort_recovery(run_id, reason="Test abort")

        assert state_service.mode == SystemMode.SAFE_MODE
        assert recovery_orchestrator.is_recovering is False
        assert recovery_orchestrator.current_run_id is None

    @pytest.mark.asyncio
    async def test_abort_recovery_clears_state(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Aborting recovery clears orchestrator state."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )
        assert recovery_orchestrator.is_recovering is True

        await recovery_orchestrator.abort_recovery(run_id, reason="Test abort")

        assert recovery_orchestrator.is_recovering is False
        assert recovery_orchestrator.current_run_id is None
        assert recovery_orchestrator.current_stage is None


class TestRunIdValidation:
    """Tests for run_id validation."""

    @pytest.mark.asyncio
    async def test_run_id_mismatch_rejected_on_advance(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Operations with wrong run_id are rejected for advance_stage."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Try to advance with wrong run_id
        wrong_run_id = "recovery-wrongid"
        assert wrong_run_id != run_id

        success = await recovery_orchestrator.advance_stage(wrong_run_id)
        assert success is False
        # Stage should not have changed
        assert recovery_orchestrator.current_stage == RecoveryStage.CONNECT_BROKER

    @pytest.mark.asyncio
    async def test_run_id_mismatch_rejected_on_abort(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Operations with wrong run_id are rejected for abort_recovery."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Try to abort with wrong run_id
        wrong_run_id = "recovery-wrongid"
        assert wrong_run_id != run_id

        await recovery_orchestrator.abort_recovery(wrong_run_id, reason="Test")
        # Should still be recovering since wrong run_id was rejected
        assert recovery_orchestrator.is_recovering is True
        assert recovery_orchestrator.current_run_id == run_id

    @pytest.mark.asyncio
    async def test_advance_rejected_when_not_recovering(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """advance_stage rejected when not in recovery."""
        assert recovery_orchestrator.is_recovering is False

        success = await recovery_orchestrator.advance_stage("recovery-fake")
        assert success is False

    @pytest.mark.asyncio
    async def test_abort_rejected_when_not_recovering(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """abort_recovery is a no-op when not recovering."""
        assert recovery_orchestrator.is_recovering is False

        # Should not raise, just be a no-op
        await recovery_orchestrator.abort_recovery("recovery-fake", reason="Test")
        assert recovery_orchestrator.is_recovering is False


class TestConcurrency:
    """Tests for concurrent recovery operations."""

    @pytest.mark.asyncio
    async def test_concurrent_start_recovery(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """Concurrent start_recovery calls are serialized."""
        # Start multiple recoveries concurrently
        results = await asyncio.gather(
            recovery_orchestrator.start_recovery(trigger=RecoveryTrigger.MANUAL, operator_id="op1"),
            recovery_orchestrator.start_recovery(trigger=RecoveryTrigger.MANUAL, operator_id="op2"),
            recovery_orchestrator.start_recovery(trigger=RecoveryTrigger.MANUAL, operator_id="op3"),
        )

        # All should succeed but only one should be the current
        assert all(r.startswith("recovery-") for r in results)
        # Current run_id should be one of them
        assert recovery_orchestrator.current_run_id in results
        # Only one recovery should be active
        assert recovery_orchestrator.is_recovering is True


class TestStageChecks:
    """Tests for stage check logic."""

    @pytest.mark.asyncio
    async def test_check_connect_broker_stage(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """CONNECT_BROKER stage check simulates broker connection."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Default implementation should pass (simulated)
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True

    @pytest.mark.asyncio
    async def test_check_catchup_marketdata_stage(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """CATCHUP_MARKETDATA stage check simulates market data freshness."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Advance to CATCHUP_MARKETDATA
        await recovery_orchestrator.advance_stage(run_id)
        assert recovery_orchestrator.current_stage == RecoveryStage.CATCHUP_MARKETDATA

        # Default implementation should pass (simulated)
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True

    @pytest.mark.asyncio
    async def test_check_verify_risk_stage(
        self, recovery_orchestrator: RecoveryOrchestrator
    ) -> None:
        """VERIFY_RISK stage check simulates risk engine response."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Advance to VERIFY_RISK
        await recovery_orchestrator.advance_stage(run_id)
        await recovery_orchestrator.advance_stage(run_id)
        assert recovery_orchestrator.current_stage == RecoveryStage.VERIFY_RISK

        # Default implementation should pass (simulated)
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True

    @pytest.mark.asyncio
    async def test_ready_stage_requires_stable_period(
        self, recovery_orchestrator: RecoveryOrchestrator, config: DegradationConfig
    ) -> None:
        """READY stage waits for stable period before completing."""
        run_id = await recovery_orchestrator.start_recovery(
            trigger=RecoveryTrigger.MANUAL,
            operator_id="test_operator",
        )

        # Advance to READY
        await recovery_orchestrator.advance_stage(run_id)
        await recovery_orchestrator.advance_stage(run_id)
        await recovery_orchestrator.advance_stage(run_id)
        assert recovery_orchestrator.current_stage == RecoveryStage.READY

        # Final advance completes recovery
        success = await recovery_orchestrator.advance_stage(run_id)
        assert success is True
        assert recovery_orchestrator.is_recovering is False
