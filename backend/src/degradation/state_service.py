"""SystemStateService - Single Source of Truth for system mode.

CRITICAL: Only SystemStateService can modify system state.
No other component has permission to change the system mode.

Key responsibilities:
- Maintains SystemMode + RecoveryStage state machine
- Uses Decision Matrix for mode transitions
- Handles conflict resolution (takes most severe mode)
- Supports force override with TTL
- Records all transitions in history
- Publishes mode changes to EventBus
- Updates TradingGate on mode changes
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.degradation.config import DegradationConfig
from src.degradation.models import (
    MODE_PRIORITY,
    ComponentSource,
    EventType,
    ModeTransition,
    ReasonCode,
    RecoveryStage,
    Severity,
    SystemEvent,
    SystemMode,
    create_event,
)

if TYPE_CHECKING:
    from src.degradation.event_bus import EventBus
    from src.degradation.trading_gate import TradingGate

logger = logging.getLogger(__name__)


# Decision Matrix: ReasonCode -> target SystemMode
# All thresholds/logic comes from this matrix, not hardcoded elsewhere
DECISION_MATRIX: dict[ReasonCode, SystemMode] = {
    # Broker events
    ReasonCode.BROKER_DISCONNECT: SystemMode.SAFE_MODE_DISCONNECTED,
    ReasonCode.BROKER_RECONNECTED: SystemMode.RECOVERING,
    ReasonCode.BROKER_REPORT_MISMATCH: SystemMode.HALT,
    # Market Data events
    ReasonCode.MD_STALE: SystemMode.SAFE_MODE,
    ReasonCode.MD_QUALITY_DEGRADED: SystemMode.DEGRADED,
    # Risk events
    ReasonCode.RISK_TIMEOUT: SystemMode.SAFE_MODE,
    ReasonCode.RISK_BREACH_HARD: SystemMode.HALT,
    # Position events
    ReasonCode.POSITION_TRUTH_UNKNOWN: SystemMode.HALT,
    # Database events
    ReasonCode.DB_WRITE_FAIL: SystemMode.DEGRADED,
    ReasonCode.DB_BUFFER_OVERFLOW: SystemMode.SAFE_MODE,
    # Alerts events
    ReasonCode.ALERTS_CHANNEL_DOWN: SystemMode.DEGRADED,
    # Recovery events
    ReasonCode.COLD_START: SystemMode.RECOVERING,
    ReasonCode.RECOVERY_FAILED: SystemMode.HALT,
    ReasonCode.ALL_HEALTHY: SystemMode.NORMAL,
}


@dataclass
class ForceOverrideState:
    """State for force override mode."""

    mode: SystemMode
    ttl_seconds: int
    operator_id: str
    reason: str
    start_time_mono: float
    start_time_wall: datetime


class SystemStateService:
    """Central service for managing system state.

    The SystemStateService is the SINGLE SOURCE OF TRUTH for system mode.
    Only this service can modify the system state.

    Cold start: System starts in RECOVERING mode with CONNECT_BROKER stage.
    This ensures that all components are verified before trading begins.

    Attributes:
        mode: Current system mode (read-only property)
        stage: Current recovery stage or None if not recovering (read-only property)
        is_force_override: Whether force override is active (read-only property)
        transition_history: List of all mode transitions
    """

    def __init__(
        self,
        config: DegradationConfig,
        trading_gate: TradingGate,
        event_bus: EventBus,
    ) -> None:
        """Initialize SystemStateService in cold start state.

        Args:
            config: Degradation configuration
            trading_gate: TradingGate to update on mode changes
            event_bus: EventBus for publishing mode change events
        """
        self._config = config
        self._trading_gate = trading_gate
        self._event_bus = event_bus

        # Cold start: RECOVERING mode with CONNECT_BROKER stage
        self._mode = SystemMode.RECOVERING
        self._stage: RecoveryStage | None = RecoveryStage.CONNECT_BROKER
        self._force_override: ForceOverrideState | None = None

        # Transition history
        self._transition_history: list[ModeTransition] = []

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Update trading gate to match initial state
        self._trading_gate.update_mode(self._mode, self._stage)

        logger.info(
            f"SystemStateService initialized: mode={self._mode.value}, "
            f"stage={self._stage.value if self._stage else None}"
        )

    @property
    def mode(self) -> SystemMode:
        """Current system mode."""
        return self._mode

    @property
    def stage(self) -> RecoveryStage | None:
        """Current recovery stage (None if not in RECOVERING mode)."""
        return self._stage

    @property
    def is_force_override(self) -> bool:
        """Whether force override is currently active.

        Checks TTL expiry and clears override if expired.
        """
        if self._force_override is None:
            return False

        # Check if TTL has expired
        elapsed = time.monotonic() - self._force_override.start_time_mono
        if elapsed > self._force_override.ttl_seconds:
            logger.info(
                f"Force override expired after {elapsed:.1f}s "
                f"(TTL was {self._force_override.ttl_seconds}s)"
            )
            self._force_override = None
            return False

        return True

    @property
    def transition_history(self) -> list[ModeTransition]:
        """List of all mode transitions."""
        return list(self._transition_history)

    async def handle_event(self, event: SystemEvent) -> None:
        """Handle a system event and potentially transition modes.

        Uses the Decision Matrix to determine target mode.
        Applies conflict resolution: takes the most severe mode.
        Force override blocks automatic transitions.

        Args:
            event: The system event to handle
        """
        async with self._lock:
            # If force override is active, block automatic transitions
            if self.is_force_override:
                logger.debug(f"Force override active, ignoring event: {event.reason_code.value}")
                return

            # Look up target mode in decision matrix
            target_mode = DECISION_MATRIX.get(event.reason_code)
            if target_mode is None:
                logger.warning(
                    f"No decision matrix entry for reason code: {event.reason_code.value}"
                )
                return

            # Apply conflict resolution: can only escalate to more severe mode
            if not self._can_transition(self._mode, target_mode):
                logger.debug(
                    f"Transition blocked: {self._mode.value} -> {target_mode.value} "
                    f"(reason: {event.reason_code.value})"
                )
                return

            # Execute the transition
            await self._transition_to(
                target_mode=target_mode,
                reason_code=event.reason_code,
                source=event.source,
            )

    async def force_mode(
        self,
        mode: SystemMode,
        ttl_seconds: int,
        operator_id: str,
        reason: str,
    ) -> None:
        """Force system into specific mode, overriding automatic logic.

        Use this for manual intervention when the system needs human control.
        After TTL expires, automatic logic resumes.

        Args:
            mode: Target mode to force
            ttl_seconds: How long the override lasts (must be positive)
            operator_id: Who initiated the override (required, non-empty)
            reason: Human-readable reason for the override (required, non-empty)

        Raises:
            ValueError: If operator_id or reason is empty, or ttl_seconds <= 0
        """
        # Validate inputs
        if not operator_id or not operator_id.strip():
            raise ValueError("operator_id required for force mode")
        if not reason or not reason.strip():
            raise ValueError("reason required for force mode")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        async with self._lock:
            old_mode = self._mode
            now_mono = time.monotonic()
            now_wall = datetime.now(tz=timezone.utc)

            # Set force override state
            self._force_override = ForceOverrideState(
                mode=mode,
                ttl_seconds=ttl_seconds,
                operator_id=operator_id,
                reason=reason,
                start_time_mono=now_mono,
                start_time_wall=now_wall,
            )

            # Update mode
            self._mode = mode

            # Clear recovery stage if not in RECOVERING mode
            if mode != SystemMode.RECOVERING:
                self._stage = None

            # Update trading gate
            self._trading_gate.update_mode(mode, self._stage)

            # Record transition
            transition = ModeTransition(
                from_mode=old_mode,
                to_mode=mode,
                reason_code=ReasonCode.COLD_START,  # Use a generic code for force
                source=ComponentSource.SYSTEM,
                timestamp_wall=now_wall,
                timestamp_mono=now_mono,
                operator_id=operator_id,
                override_ttl=ttl_seconds,
            )
            self._transition_history.append(transition)

            logger.warning(
                f"Force mode activated: {old_mode.value} -> {mode.value} "
                f"by {operator_id} (TTL: {ttl_seconds}s, reason: {reason})"
            )

    def update_recovery_stage(self, stage: RecoveryStage) -> None:
        """Update the recovery stage during recovery process.

        Can only be called when in RECOVERING mode.

        Args:
            stage: The new recovery stage

        Raises:
            ValueError: If not currently in RECOVERING mode
        """
        if self._mode != SystemMode.RECOVERING:
            raise ValueError(
                f"Cannot update recovery stage: not in RECOVERING mode "
                f"(current mode: {self._mode.value})"
            )

        old_stage = self._stage
        self._stage = stage

        # Update trading gate
        self._trading_gate.update_mode(self._mode, self._stage)

        logger.info(
            f"Recovery stage updated: {old_stage.value if old_stage else None} " f"-> {stage.value}"
        )

    def _can_transition(self, current: SystemMode, target: SystemMode) -> bool:
        """Check if transition from current to target mode is allowed.

        Conflict resolution rule: can only escalate to more severe mode,
        or stay at the same severity. Cannot downgrade without recovery
        (i.e., ALL_HEALTHY event or BROKER_RECONNECTED).

        Args:
            current: Current system mode
            target: Target system mode

        Returns:
            True if transition is allowed, False otherwise
        """
        current_priority = MODE_PRIORITY[current]
        target_priority = MODE_PRIORITY[target]

        # Can always escalate or stay same
        if target_priority >= current_priority:
            return True

        # Can only downgrade to NORMAL (via ALL_HEALTHY) or RECOVERING (via BROKER_RECONNECTED)
        # Any other downgrade is blocked
        if target in (SystemMode.NORMAL, SystemMode.RECOVERING):
            return True

        # Block all other downgrades
        return False

    async def _transition_to(
        self,
        target_mode: SystemMode,
        reason_code: ReasonCode,
        source: ComponentSource,
    ) -> None:
        """Execute a mode transition.

        Updates internal state, trading gate, records history, and publishes event.

        Args:
            target_mode: The mode to transition to
            reason_code: Why the transition is happening
            source: Which component triggered it
        """
        old_mode = self._mode
        now_mono = time.monotonic()
        now_wall = datetime.now(tz=timezone.utc)

        # Update mode
        self._mode = target_mode

        # Handle recovery stage
        if target_mode == SystemMode.RECOVERING:
            # If transitioning to RECOVERING, start at CONNECT_BROKER
            if self._stage is None:
                self._stage = RecoveryStage.CONNECT_BROKER
        else:
            # Clear stage if not in RECOVERING mode
            self._stage = None

        # Update trading gate
        self._trading_gate.update_mode(target_mode, self._stage)

        # Record transition
        transition = ModeTransition(
            from_mode=old_mode,
            to_mode=target_mode,
            reason_code=reason_code,
            source=source,
            timestamp_wall=now_wall,
            timestamp_mono=now_mono,
        )
        self._transition_history.append(transition)

        logger.info(
            f"Mode transition: {old_mode.value} -> {target_mode.value} "
            f"(reason: {reason_code.value}, source: {source.value})"
        )

        # Publish mode change event to EventBus (non-blocking)
        await self._publish_mode_change(old_mode, target_mode, reason_code, source)

    async def _publish_mode_change(
        self,
        old_mode: SystemMode,
        new_mode: SystemMode,
        reason_code: ReasonCode,
        source: ComponentSource,
    ) -> None:
        """Publish a mode change event to the EventBus.

        Non-blocking: if the EventBus is full, the event is dropped
        but the mode change still takes effect.

        Args:
            old_mode: The previous mode
            new_mode: The new mode
            reason_code: Why the transition happened
            source: Which component triggered it
        """
        # Determine severity based on new mode
        if new_mode == SystemMode.HALT:
            severity = Severity.CRITICAL
        elif new_mode in (SystemMode.SAFE_MODE, SystemMode.SAFE_MODE_DISCONNECTED):
            severity = Severity.WARNING
        else:
            severity = Severity.INFO

        event = create_event(
            event_type=EventType.QUALITY_DEGRADED
            if new_mode != SystemMode.NORMAL
            else EventType.RECOVERED,
            source=source,
            severity=severity,
            reason_code=reason_code,
            details={
                "old_mode": old_mode.value,
                "new_mode": new_mode.value,
            },
        )

        success = await self._event_bus.publish(event)
        if not success:
            logger.warning(
                f"Failed to publish mode change event to EventBus "
                f"(dropped: {old_mode.value} -> {new_mode.value})"
            )
