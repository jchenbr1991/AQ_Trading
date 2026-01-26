"""Tests for TradingGate.

Tests the permission matrix for trading operations based on SystemMode
and RecoveryStage. Each mode has specific permissions for actions.
"""

from __future__ import annotations

import pytest
from src.degradation import ActionType, RecoveryStage, SystemMode
from src.degradation.trading_gate import PermissionResult, TradingGate


class TestTradingGateInit:
    """Test TradingGate initialization."""

    def test_cold_start_mode(self) -> None:
        """TradingGate starts in RECOVERING mode on cold start."""
        gate = TradingGate()
        assert gate.mode == SystemMode.RECOVERING
        assert gate.stage == RecoveryStage.CONNECT_BROKER

    def test_cold_start_permissions(self) -> None:
        """Cold start only allows query."""
        gate = TradingGate()
        # Only query is allowed during cold start
        assert gate.allows(ActionType.QUERY)
        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.CANCEL)


class TestNormalModeAllAllowed:
    """Test that NORMAL mode allows all actions."""

    def test_normal_mode_all_allowed(self) -> None:
        """All actions allowed in NORMAL mode."""
        gate = TradingGate()
        gate.update_mode(SystemMode.NORMAL)

        assert gate.allows(ActionType.OPEN)
        assert gate.allows(ActionType.SEND)
        assert gate.allows(ActionType.AMEND)
        assert gate.allows(ActionType.CANCEL)
        assert gate.allows(ActionType.REDUCE_ONLY)
        assert gate.allows(ActionType.QUERY)

    def test_normal_mode_no_warnings(self) -> None:
        """No warnings for any action in NORMAL mode."""
        gate = TradingGate()
        gate.update_mode(SystemMode.NORMAL)

        for action in ActionType:
            allowed, warning = gate.allows_with_warning(action)
            assert allowed
            assert warning is None

    def test_normal_mode_permission_result(self) -> None:
        """Permission result shows granted with no restrictions."""
        gate = TradingGate()
        gate.update_mode(SystemMode.NORMAL)

        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed
        assert result.warning is None
        assert not result.restricted


class TestDegradedModeLimited:
    """Test DEGRADED mode with limited operations."""

    def test_degraded_mode_limited(self) -> None:
        """DEGRADED mode allows all actions but OPEN is restricted."""
        gate = TradingGate()
        gate.update_mode(SystemMode.DEGRADED)

        # All actions still allowed
        assert gate.allows(ActionType.OPEN)
        assert gate.allows(ActionType.SEND)
        assert gate.allows(ActionType.AMEND)
        assert gate.allows(ActionType.CANCEL)
        assert gate.allows(ActionType.REDUCE_ONLY)
        assert gate.allows(ActionType.QUERY)

    def test_degraded_mode_open_restricted(self) -> None:
        """OPEN action is restricted (but allowed) in DEGRADED mode."""
        gate = TradingGate()
        gate.update_mode(SystemMode.DEGRADED)

        result = gate.check_permission(ActionType.OPEN)
        assert result.allowed
        assert result.restricted  # Marked as restricted

    def test_degraded_mode_other_actions_unrestricted(self) -> None:
        """Other actions are not restricted in DEGRADED mode."""
        gate = TradingGate()
        gate.update_mode(SystemMode.DEGRADED)

        for action in [
            ActionType.SEND,
            ActionType.AMEND,
            ActionType.CANCEL,
            ActionType.REDUCE_ONLY,
            ActionType.QUERY,
        ]:
            result = gate.check_permission(action)
            assert result.allowed
            assert not result.restricted


class TestSafeModeNoNewPositions:
    """Test SAFE_MODE blocks new positions."""

    def test_safe_mode_no_new_positions(self) -> None:
        """SAFE_MODE blocks OPEN, SEND, AMEND."""
        gate = TradingGate()
        gate.update_mode(SystemMode.SAFE_MODE)

        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.AMEND)

    def test_safe_mode_allows_protective_actions(self) -> None:
        """SAFE_MODE allows protective actions."""
        gate = TradingGate()
        gate.update_mode(SystemMode.SAFE_MODE)

        assert gate.allows(ActionType.CANCEL)
        assert gate.allows(ActionType.REDUCE_ONLY)
        assert gate.allows(ActionType.QUERY)


class TestSafeModeCancelBestEffort:
    """Test SAFE_MODE cancel with best-effort warning."""

    def test_safe_mode_cancel_best_effort(self) -> None:
        """Cancel in SAFE_MODE returns warning about best-effort delivery."""
        gate = TradingGate()
        gate.update_mode(SystemMode.SAFE_MODE)

        allowed, warning = gate.allows_with_warning(ActionType.CANCEL)
        assert allowed
        assert warning is not None
        assert "best-effort" in warning.lower()

    def test_safe_mode_cancel_permission_result(self) -> None:
        """Permission result includes best-effort warning for cancel."""
        gate = TradingGate()
        gate.update_mode(SystemMode.SAFE_MODE)

        result = gate.check_permission(ActionType.CANCEL)
        assert result.allowed
        assert result.warning is not None
        assert "best-effort" in result.warning.lower()


class TestSafeModeDisconnectedMinimal:
    """Test SAFE_MODE_DISCONNECTED has minimal permissions."""

    def test_safe_mode_disconnected_minimal(self) -> None:
        """SAFE_MODE_DISCONNECTED only allows local query."""
        gate = TradingGate()
        gate.update_mode(SystemMode.SAFE_MODE_DISCONNECTED)

        # Only query allowed
        assert gate.allows(ActionType.QUERY)

        # All other actions blocked
        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.AMEND)
        assert not gate.allows(ActionType.CANCEL)
        assert not gate.allows(ActionType.REDUCE_ONLY)

    def test_safe_mode_disconnected_query_local_only(self) -> None:
        """Query in SAFE_MODE_DISCONNECTED returns local-only warning."""
        gate = TradingGate()
        gate.update_mode(SystemMode.SAFE_MODE_DISCONNECTED)

        result = gate.check_permission(ActionType.QUERY)
        assert result.allowed
        assert result.local_only


class TestHaltModeQueryOnly:
    """Test HALT mode only allows query."""

    def test_halt_mode_query_only(self) -> None:
        """HALT mode only allows query."""
        gate = TradingGate()
        gate.update_mode(SystemMode.HALT)

        assert gate.allows(ActionType.QUERY)
        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.AMEND)
        assert not gate.allows(ActionType.CANCEL)
        assert not gate.allows(ActionType.REDUCE_ONLY)

    def test_halt_mode_no_warnings_for_query(self) -> None:
        """No warnings for query in HALT mode."""
        gate = TradingGate()
        gate.update_mode(SystemMode.HALT)

        allowed, warning = gate.allows_with_warning(ActionType.QUERY)
        assert allowed
        assert warning is None


class TestRecoveryConnectBrokerStage:
    """Test CONNECT_BROKER recovery stage permissions."""

    def test_recovery_connect_broker_stage(self) -> None:
        """CONNECT_BROKER stage only allows query."""
        gate = TradingGate()
        gate.update_mode(SystemMode.RECOVERING, RecoveryStage.CONNECT_BROKER)

        assert gate.allows(ActionType.QUERY)
        assert not gate.allows(ActionType.CANCEL)
        assert not gate.allows(ActionType.REDUCE_ONLY)
        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.AMEND)


class TestRecoveryCatchupMarketdataStage:
    """Test CATCHUP_MARKETDATA recovery stage permissions."""

    def test_recovery_catchup_marketdata_stage(self) -> None:
        """CATCHUP_MARKETDATA stage only allows query."""
        gate = TradingGate()
        gate.update_mode(SystemMode.RECOVERING, RecoveryStage.CATCHUP_MARKETDATA)

        assert gate.allows(ActionType.QUERY)
        assert not gate.allows(ActionType.CANCEL)
        assert not gate.allows(ActionType.REDUCE_ONLY)
        assert not gate.allows(ActionType.OPEN)


class TestRecoveryVerifyRiskStage:
    """Test VERIFY_RISK recovery stage permissions."""

    def test_recovery_verify_risk_stage(self) -> None:
        """VERIFY_RISK stage allows query and cancel."""
        gate = TradingGate()
        gate.update_mode(SystemMode.RECOVERING, RecoveryStage.VERIFY_RISK)

        assert gate.allows(ActionType.QUERY)
        assert gate.allows(ActionType.CANCEL)
        assert not gate.allows(ActionType.REDUCE_ONLY)
        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.AMEND)


class TestRecoveryReadyStage:
    """Test READY recovery stage permissions."""

    def test_recovery_ready_stage(self) -> None:
        """READY stage allows query, cancel, and reduce_only."""
        gate = TradingGate()
        gate.update_mode(SystemMode.RECOVERING, RecoveryStage.READY)

        assert gate.allows(ActionType.QUERY)
        assert gate.allows(ActionType.CANCEL)
        assert gate.allows(ActionType.REDUCE_ONLY)
        assert not gate.allows(ActionType.OPEN)
        assert not gate.allows(ActionType.SEND)
        assert not gate.allows(ActionType.AMEND)


class TestUpdateMode:
    """Test update_mode behavior."""

    def test_update_mode_clears_stage_for_non_recovering(self) -> None:
        """Transitioning to non-RECOVERING mode clears recovery stage."""
        gate = TradingGate()
        # Start in recovering
        assert gate.stage == RecoveryStage.CONNECT_BROKER

        # Transition to normal
        gate.update_mode(SystemMode.NORMAL)
        assert gate.mode == SystemMode.NORMAL
        assert gate.stage is None

    def test_update_mode_requires_stage_for_recovering(self) -> None:
        """Transitioning to RECOVERING without stage raises error."""
        gate = TradingGate()
        gate.update_mode(SystemMode.NORMAL)

        with pytest.raises(ValueError, match="RecoveryStage required"):
            gate.update_mode(SystemMode.RECOVERING)

    def test_update_mode_with_stage(self) -> None:
        """Can update recovery stage."""
        gate = TradingGate()
        gate.update_mode(SystemMode.RECOVERING, RecoveryStage.VERIFY_RISK)
        assert gate.mode == SystemMode.RECOVERING
        assert gate.stage == RecoveryStage.VERIFY_RISK


class TestPermissionResultDataclass:
    """Test PermissionResult dataclass."""

    def test_permission_result_defaults(self) -> None:
        """PermissionResult has sensible defaults."""
        result = PermissionResult(allowed=True)
        assert result.allowed
        assert result.warning is None
        assert not result.restricted
        assert not result.local_only

    def test_permission_result_with_warning(self) -> None:
        """PermissionResult can have warning."""
        result = PermissionResult(allowed=True, warning="Best-effort delivery")
        assert result.allowed
        assert result.warning == "Best-effort delivery"

    def test_permission_result_restricted(self) -> None:
        """PermissionResult can be marked as restricted."""
        result = PermissionResult(allowed=True, restricted=True)
        assert result.allowed
        assert result.restricted

    def test_permission_result_local_only(self) -> None:
        """PermissionResult can be marked as local_only."""
        result = PermissionResult(allowed=True, local_only=True)
        assert result.allowed
        assert result.local_only


class TestConcurrentAccess:
    """Test thread-safety of TradingGate."""

    def test_mode_property_atomic(self) -> None:
        """Mode property returns consistent value."""
        gate = TradingGate()
        gate.update_mode(SystemMode.NORMAL)

        # Multiple reads should be consistent
        modes = [gate.mode for _ in range(100)]
        assert all(m == SystemMode.NORMAL for m in modes)
