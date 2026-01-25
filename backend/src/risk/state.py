"""Trading state management with state machine semantics.

Provides TradingStateManager to control trading system state transitions
between RUNNING, PAUSED, and HALTED states.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class StateValue(str, Enum):
    """Trading system state values."""

    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    HALTED = "HALTED"


@dataclass(frozen=True)
class TradingState:
    """Represents the current trading state.

    Attributes:
        state: Current state value (RUNNING, PAUSED, HALTED)
        since: Timestamp when this state was entered
        changed_by: Identifier of who/what made the state change
        reason: Optional reason for the state change
        can_resume: Whether resuming to RUNNING is allowed
    """

    state: StateValue
    since: datetime
    changed_by: str
    reason: str | None
    can_resume: bool


class TradingStateManager:
    """Manages trading system state with state machine semantics.

    The state machine has three states:
    - RUNNING: Normal operation, trading allowed
    - PAUSED: Temporarily stopped, can resume, close-only allowed
    - HALTED: Emergency stop, cannot resume until explicitly enabled

    State transitions:
    - RUNNING -> PAUSED: via pause()
    - RUNNING -> HALTED: via halt()
    - PAUSED -> RUNNING: via resume() (always allowed)
    - PAUSED -> HALTED: via halt()
    - HALTED -> RUNNING: via resume() (only if can_resume is True)
    """

    def __init__(self) -> None:
        """Initialize manager in RUNNING state."""
        self._state = TradingState(
            state=StateValue.RUNNING,
            since=datetime.now(tz=timezone.utc),
            changed_by="system",
            reason=None,
            can_resume=True,
        )

    def get_state(self) -> TradingState:
        """Get the current trading state.

        Returns:
            Current TradingState
        """
        return self._state

    def halt(self, changed_by: str, reason: str) -> None:
        """Halt trading - emergency stop.

        Sets state to HALTED with can_resume=False.
        Resume is not allowed until enable_resume() is called.

        Args:
            changed_by: Identifier of who/what triggered the halt
            reason: Reason for halting
        """
        self._state = TradingState(
            state=StateValue.HALTED,
            since=datetime.now(tz=timezone.utc),
            changed_by=changed_by,
            reason=reason,
            can_resume=False,
        )

    def pause(self, changed_by: str, reason: str | None = None) -> None:
        """Pause trading - temporary stop.

        Sets state to PAUSED with can_resume=True.
        Close operations are still allowed.

        Args:
            changed_by: Identifier of who/what triggered the pause
            reason: Optional reason for pausing
        """
        self._state = TradingState(
            state=StateValue.PAUSED,
            since=datetime.now(tz=timezone.utc),
            changed_by=changed_by,
            reason=reason,
            can_resume=True,
        )

    def enable_resume(self, changed_by: str) -> None:
        """Enable resume for HALTED state.

        Only affects HALTED state. Has no effect on other states.

        Args:
            changed_by: Identifier of who enabled resume
        """
        if self._state.state != StateValue.HALTED:
            return

        self._state = TradingState(
            state=StateValue.HALTED,
            since=self._state.since,
            changed_by=changed_by,
            reason=self._state.reason,
            can_resume=True,
        )

    def resume(self, changed_by: str) -> bool:
        """Resume trading to RUNNING state.

        Only succeeds if can_resume is True.

        Args:
            changed_by: Identifier of who triggered resume

        Returns:
            True if resume succeeded, False otherwise
        """
        if not self._state.can_resume:
            return False

        self._state = TradingState(
            state=StateValue.RUNNING,
            since=datetime.now(tz=timezone.utc),
            changed_by=changed_by,
            reason=None,
            can_resume=True,
        )
        return True

    def is_trading_allowed(self) -> bool:
        """Check if new trades are allowed.

        Returns:
            True only if state is RUNNING
        """
        return self._state.state == StateValue.RUNNING

    def is_close_allowed(self) -> bool:
        """Check if closing positions is allowed.

        Returns:
            True if state is RUNNING or PAUSED
        """
        return self._state.state in (StateValue.RUNNING, StateValue.PAUSED)
