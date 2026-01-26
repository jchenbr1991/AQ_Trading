"""TradingGate - unified gate for all trading operations.

All trading calls (send_order, cancel_order, etc.) must pass through this gate.
It provides O(1) permission checks based on current SystemMode and RecoveryStage.

Permission Matrix:
| Mode                     | open | send | amend | cancel          | reduce_only | query      |
|--------------------------|------|------|-------|-----------------|-------------|------------|
| NORMAL                   | Y    | Y    | Y     | Y               | Y           | Y          |
| DEGRADED                 | Y*   | Y    | Y     | Y               | Y           | Y          |
| SAFE_MODE                | N    | N    | N     | Y (best-effort) | Y           | Y          |
| SAFE_MODE_DISCONNECTED   | N    | N    | N     | N               | N           | Y (local)  |
| HALT                     | N    | N    | N     | N               | N           | Y          |

* DEGRADED mode: open is restricted but allowed

Recovery Stage Permissions (when mode is RECOVERING):
| Stage              | query | cancel | reduce_only | open |
|--------------------|-------|--------|-------------|------|
| CONNECT_BROKER     | Y     | N      | N           | N    |
| CATCHUP_MARKETDATA | Y     | N      | N           | N    |
| VERIFY_RISK        | Y     | Y      | N           | N    |
| READY              | Y     | Y      | Y           | N    |
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import ClassVar

from src.degradation.models import ActionType, RecoveryStage, SystemMode


@dataclass
class PermissionResult:
    """Result of a permission check.

    Attributes:
        allowed: Whether the action is permitted.
        warning: Optional warning message (e.g., best-effort delivery).
        restricted: Whether the action is allowed but restricted.
        local_only: Whether the result is from local cache only.
    """

    allowed: bool
    warning: str | None = None
    restricted: bool = False
    local_only: bool = False


class TradingGate:
    """Unified gate for all trading operations.

    Provides O(1) permission checks based on current SystemMode and RecoveryStage.
    Thread-safe for concurrent access.

    On cold start, the gate is in RECOVERING mode with CONNECT_BROKER stage,
    allowing only query operations until the system is ready.
    """

    # Permission matrix for each mode
    # Maps (SystemMode, ActionType) -> (allowed, restricted, warning, local_only)
    _MODE_PERMISSIONS: ClassVar[
        dict[SystemMode, dict[ActionType, tuple[bool, bool, str | None, bool]]]
    ] = {
        SystemMode.NORMAL: {
            ActionType.OPEN: (True, False, None, False),
            ActionType.SEND: (True, False, None, False),
            ActionType.AMEND: (True, False, None, False),
            ActionType.CANCEL: (True, False, None, False),
            ActionType.REDUCE_ONLY: (True, False, None, False),
            ActionType.QUERY: (True, False, None, False),
        },
        SystemMode.DEGRADED: {
            ActionType.OPEN: (True, True, None, False),  # restricted
            ActionType.SEND: (True, False, None, False),
            ActionType.AMEND: (True, False, None, False),
            ActionType.CANCEL: (True, False, None, False),
            ActionType.REDUCE_ONLY: (True, False, None, False),
            ActionType.QUERY: (True, False, None, False),
        },
        SystemMode.SAFE_MODE: {
            ActionType.OPEN: (False, False, None, False),
            ActionType.SEND: (False, False, None, False),
            ActionType.AMEND: (False, False, None, False),
            ActionType.CANCEL: (
                True,
                False,
                "Cancel is best-effort; broker connection may be unstable",
                False,
            ),
            ActionType.REDUCE_ONLY: (True, False, None, False),
            ActionType.QUERY: (True, False, None, False),
        },
        SystemMode.SAFE_MODE_DISCONNECTED: {
            ActionType.OPEN: (False, False, None, False),
            ActionType.SEND: (False, False, None, False),
            ActionType.AMEND: (False, False, None, False),
            ActionType.CANCEL: (False, False, None, False),
            ActionType.REDUCE_ONLY: (False, False, None, False),
            ActionType.QUERY: (True, False, None, True),  # local only
        },
        SystemMode.HALT: {
            ActionType.OPEN: (False, False, None, False),
            ActionType.SEND: (False, False, None, False),
            ActionType.AMEND: (False, False, None, False),
            ActionType.CANCEL: (False, False, None, False),
            ActionType.REDUCE_ONLY: (False, False, None, False),
            ActionType.QUERY: (True, False, None, False),
        },
    }

    # Recovery stage permissions
    # Maps RecoveryStage -> set of allowed actions
    _RECOVERY_STAGE_PERMISSIONS: ClassVar[dict[RecoveryStage, set[ActionType]]] = {
        RecoveryStage.CONNECT_BROKER: {ActionType.QUERY},
        RecoveryStage.CATCHUP_MARKETDATA: {ActionType.QUERY},
        RecoveryStage.VERIFY_RISK: {ActionType.QUERY, ActionType.CANCEL},
        RecoveryStage.READY: {ActionType.QUERY, ActionType.CANCEL, ActionType.REDUCE_ONLY},
    }

    def __init__(self) -> None:
        """Initialize TradingGate in cold start state.

        Cold start: RECOVERING mode with CONNECT_BROKER stage.
        """
        self._mode: SystemMode = SystemMode.RECOVERING
        self._stage: RecoveryStage | None = RecoveryStage.CONNECT_BROKER
        self._lock = Lock()

    @property
    def mode(self) -> SystemMode:
        """Current system mode."""
        with self._lock:
            return self._mode

    @property
    def stage(self) -> RecoveryStage | None:
        """Current recovery stage (None if not in RECOVERING mode)."""
        with self._lock:
            return self._stage

    def update_mode(self, mode: SystemMode, stage: RecoveryStage | None = None) -> None:
        """Update the current system mode and optionally the recovery stage.

        Args:
            mode: The new system mode.
            stage: The recovery stage (required if mode is RECOVERING).

        Raises:
            ValueError: If mode is RECOVERING but no stage is provided.
        """
        with self._lock:
            if mode == SystemMode.RECOVERING and stage is None:
                raise ValueError("RecoveryStage required when transitioning to RECOVERING mode")

            self._mode = mode
            # Clear stage if not in recovering mode
            if mode != SystemMode.RECOVERING:
                self._stage = None
            else:
                self._stage = stage

    def allows(self, action: ActionType) -> bool:
        """Check if an action is allowed in the current mode.

        This is the fast path for permission checks. O(1) lookup.

        Args:
            action: The trading action to check.

        Returns:
            True if the action is allowed, False otherwise.
        """
        return self.check_permission(action).allowed

    def allows_with_warning(self, action: ActionType) -> tuple[bool, str | None]:
        """Check if an action is allowed and get any associated warning.

        Args:
            action: The trading action to check.

        Returns:
            Tuple of (allowed, warning). Warning is None if no warning.
        """
        result = self.check_permission(action)
        return result.allowed, result.warning

    def check_permission(self, action: ActionType) -> PermissionResult:
        """Full permission check with all result details.

        Args:
            action: The trading action to check.

        Returns:
            PermissionResult with allowed, warning, restricted, and local_only flags.
        """
        with self._lock:
            mode = self._mode
            stage = self._stage

        # Handle RECOVERING mode separately using stage permissions
        if mode == SystemMode.RECOVERING:
            if stage is None:
                # Should not happen, but be defensive
                return PermissionResult(allowed=False)

            allowed_actions = self._RECOVERY_STAGE_PERMISSIONS.get(stage, set())
            allowed = action in allowed_actions
            return PermissionResult(allowed=allowed)

        # Look up in mode permission matrix
        mode_perms = self._MODE_PERMISSIONS.get(mode)
        if mode_perms is None:
            # Unknown mode - deny by default
            return PermissionResult(allowed=False)

        perm = mode_perms.get(action)
        if perm is None:
            # Unknown action - deny by default
            return PermissionResult(allowed=False)

        allowed, restricted, warning, local_only = perm
        return PermissionResult(
            allowed=allowed,
            warning=warning,
            restricted=restricted,
            local_only=local_only,
        )
