"""Tests for TradingStateManager with state machine semantics."""

from datetime import datetime

from src.risk.state import StateValue, TradingState, TradingStateManager


class TestStateValue:
    """Tests for StateValue enum."""

    def test_enum_values(self):
        """StateValue has RUNNING, PAUSED, HALTED values."""
        assert StateValue.RUNNING == "RUNNING"
        assert StateValue.PAUSED == "PAUSED"
        assert StateValue.HALTED == "HALTED"

    def test_enum_is_string(self):
        """StateValue members are strings."""
        assert isinstance(StateValue.RUNNING, str)
        assert isinstance(StateValue.PAUSED, str)
        assert isinstance(StateValue.HALTED, str)


class TestTradingState:
    """Tests for TradingState dataclass."""

    def test_create_trading_state(self):
        """Create TradingState with all fields."""
        now = datetime.now()
        state = TradingState(
            state=StateValue.RUNNING,
            since=now,
            changed_by="system",
            reason="Initial startup",
            can_resume=True,
        )

        assert state.state == StateValue.RUNNING
        assert state.since == now
        assert state.changed_by == "system"
        assert state.reason == "Initial startup"
        assert state.can_resume is True

    def test_create_trading_state_without_reason(self):
        """Create TradingState with optional reason as None."""
        now = datetime.now()
        state = TradingState(
            state=StateValue.PAUSED,
            since=now,
            changed_by="user",
            reason=None,
            can_resume=True,
        )

        assert state.reason is None


class TestTradingStateManagerInitialState:
    """Tests for TradingStateManager initial state."""

    def test_initial_state_is_running(self):
        """Manager starts in RUNNING state."""
        manager = TradingStateManager()
        state = manager.get_state()

        assert state.state == StateValue.RUNNING

    def test_initial_state_can_resume(self):
        """Initial state has can_resume=True."""
        manager = TradingStateManager()
        state = manager.get_state()

        assert state.can_resume is True

    def test_initial_state_changed_by_system(self):
        """Initial state is changed_by='system'."""
        manager = TradingStateManager()
        state = manager.get_state()

        assert state.changed_by == "system"

    def test_initial_state_has_since_timestamp(self):
        """Initial state has a since timestamp."""
        before = datetime.now()
        manager = TradingStateManager()
        after = datetime.now()
        state = manager.get_state()

        assert before <= state.since <= after


class TestTradingStateManagerHalt:
    """Tests for TradingStateManager.halt()."""

    def test_halt_sets_halted_state(self):
        """halt() sets state to HALTED."""
        manager = TradingStateManager()
        manager.halt(changed_by="risk_system", reason="Daily loss limit exceeded")
        state = manager.get_state()

        assert state.state == StateValue.HALTED

    def test_halt_sets_can_resume_false(self):
        """halt() sets can_resume=False."""
        manager = TradingStateManager()
        manager.halt(changed_by="risk_system", reason="Daily loss limit exceeded")
        state = manager.get_state()

        assert state.can_resume is False

    def test_halt_records_changed_by(self):
        """halt() records who made the change."""
        manager = TradingStateManager()
        manager.halt(changed_by="kill_switch", reason="Emergency stop")
        state = manager.get_state()

        assert state.changed_by == "kill_switch"

    def test_halt_records_reason(self):
        """halt() records the reason."""
        manager = TradingStateManager()
        manager.halt(changed_by="user", reason="Market volatility")
        state = manager.get_state()

        assert state.reason == "Market volatility"

    def test_halt_updates_since_timestamp(self):
        """halt() updates the since timestamp."""
        manager = TradingStateManager()
        initial_since = manager.get_state().since

        # Small delay to ensure timestamp difference
        manager.halt(changed_by="user", reason="Test")
        state = manager.get_state()

        assert state.since >= initial_since


class TestTradingStateManagerPause:
    """Tests for TradingStateManager.pause()."""

    def test_pause_sets_paused_state(self):
        """pause() sets state to PAUSED."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")
        state = manager.get_state()

        assert state.state == StateValue.PAUSED

    def test_pause_sets_can_resume_true(self):
        """pause() sets can_resume=True."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")
        state = manager.get_state()

        assert state.can_resume is True

    def test_pause_records_changed_by(self):
        """pause() records who made the change."""
        manager = TradingStateManager()
        manager.pause(changed_by="scheduler")
        state = manager.get_state()

        assert state.changed_by == "scheduler"

    def test_pause_with_reason(self):
        """pause() can include a reason."""
        manager = TradingStateManager()
        manager.pause(changed_by="user", reason="Lunch break")
        state = manager.get_state()

        assert state.reason == "Lunch break"

    def test_pause_without_reason(self):
        """pause() works without a reason (default None)."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")
        state = manager.get_state()

        assert state.reason is None


class TestTradingStateManagerEnableResume:
    """Tests for TradingStateManager.enable_resume()."""

    def test_enable_resume_on_halted_state(self):
        """enable_resume() sets can_resume=True on HALTED state."""
        manager = TradingStateManager()
        manager.halt(changed_by="system", reason="Daily loss")
        assert manager.get_state().can_resume is False

        manager.enable_resume(changed_by="admin")
        state = manager.get_state()

        assert state.can_resume is True
        assert state.state == StateValue.HALTED  # Still halted

    def test_enable_resume_updates_changed_by(self):
        """enable_resume() updates changed_by."""
        manager = TradingStateManager()
        manager.halt(changed_by="system", reason="Test")
        manager.enable_resume(changed_by="supervisor")
        state = manager.get_state()

        assert state.changed_by == "supervisor"

    def test_enable_resume_on_non_halted_state_is_noop(self):
        """enable_resume() on non-HALTED state does nothing."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")
        original_state = manager.get_state()

        manager.enable_resume(changed_by="admin")
        state = manager.get_state()

        # State should be unchanged (still PAUSED with original changed_by)
        assert state.state == StateValue.PAUSED
        assert state.changed_by == original_state.changed_by


class TestTradingStateManagerResume:
    """Tests for TradingStateManager.resume()."""

    def test_resume_from_paused_returns_true(self):
        """resume() from PAUSED state returns True."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")

        result = manager.resume(changed_by="user")

        assert result is True

    def test_resume_from_paused_sets_running(self):
        """resume() from PAUSED sets state to RUNNING."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")

        manager.resume(changed_by="user")
        state = manager.get_state()

        assert state.state == StateValue.RUNNING

    def test_resume_from_halted_with_can_resume_true(self):
        """resume() from HALTED with can_resume=True returns True."""
        manager = TradingStateManager()
        manager.halt(changed_by="system", reason="Test")
        manager.enable_resume(changed_by="admin")

        result = manager.resume(changed_by="admin")

        assert result is True
        assert manager.get_state().state == StateValue.RUNNING

    def test_resume_from_halted_without_can_resume_returns_false(self):
        """resume() from HALTED with can_resume=False returns False."""
        manager = TradingStateManager()
        manager.halt(changed_by="system", reason="Test")

        result = manager.resume(changed_by="user")

        assert result is False
        assert manager.get_state().state == StateValue.HALTED

    def test_resume_records_changed_by(self):
        """resume() records who resumed."""
        manager = TradingStateManager()
        manager.pause(changed_by="scheduler")

        manager.resume(changed_by="trader")
        state = manager.get_state()

        assert state.changed_by == "trader"

    def test_resume_from_running_returns_true(self):
        """resume() from RUNNING state returns True (already running)."""
        manager = TradingStateManager()

        result = manager.resume(changed_by="user")

        assert result is True
        assert manager.get_state().state == StateValue.RUNNING


class TestTradingStateManagerIsTradingAllowed:
    """Tests for TradingStateManager.is_trading_allowed()."""

    def test_trading_allowed_when_running(self):
        """is_trading_allowed() returns True when RUNNING."""
        manager = TradingStateManager()

        assert manager.is_trading_allowed() is True

    def test_trading_not_allowed_when_paused(self):
        """is_trading_allowed() returns False when PAUSED."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")

        assert manager.is_trading_allowed() is False

    def test_trading_not_allowed_when_halted(self):
        """is_trading_allowed() returns False when HALTED."""
        manager = TradingStateManager()
        manager.halt(changed_by="system", reason="Test")

        assert manager.is_trading_allowed() is False


class TestTradingStateManagerIsCloseAllowed:
    """Tests for TradingStateManager.is_close_allowed()."""

    def test_close_allowed_when_running(self):
        """is_close_allowed() returns True when RUNNING."""
        manager = TradingStateManager()

        assert manager.is_close_allowed() is True

    def test_close_allowed_when_paused(self):
        """is_close_allowed() returns True when PAUSED."""
        manager = TradingStateManager()
        manager.pause(changed_by="user")

        assert manager.is_close_allowed() is True

    def test_close_not_allowed_when_halted(self):
        """is_close_allowed() returns False when HALTED."""
        manager = TradingStateManager()
        manager.halt(changed_by="system", reason="Test")

        assert manager.is_close_allowed() is False


class TestTradingStateManagerStateTransitions:
    """Integration tests for state transitions."""

    def test_full_pause_resume_cycle(self):
        """Test pause -> resume cycle."""
        manager = TradingStateManager()

        # Start RUNNING
        assert manager.get_state().state == StateValue.RUNNING
        assert manager.is_trading_allowed() is True

        # Pause
        manager.pause(changed_by="user", reason="Break")
        assert manager.get_state().state == StateValue.PAUSED
        assert manager.is_trading_allowed() is False
        assert manager.is_close_allowed() is True

        # Resume
        result = manager.resume(changed_by="user")
        assert result is True
        assert manager.get_state().state == StateValue.RUNNING
        assert manager.is_trading_allowed() is True

    def test_halt_enable_resume_cycle(self):
        """Test halt -> enable_resume -> resume cycle."""
        manager = TradingStateManager()

        # Halt (cannot resume)
        manager.halt(changed_by="risk", reason="Loss limit")
        assert manager.get_state().state == StateValue.HALTED
        assert manager.get_state().can_resume is False
        assert manager.is_trading_allowed() is False
        assert manager.is_close_allowed() is False

        # Try to resume (should fail)
        result = manager.resume(changed_by="user")
        assert result is False
        assert manager.get_state().state == StateValue.HALTED

        # Enable resume
        manager.enable_resume(changed_by="admin")
        assert manager.get_state().can_resume is True
        assert manager.get_state().state == StateValue.HALTED

        # Now resume should work
        result = manager.resume(changed_by="admin")
        assert result is True
        assert manager.get_state().state == StateValue.RUNNING
        assert manager.is_trading_allowed() is True

    def test_pause_then_halt(self):
        """Test pause -> halt transition."""
        manager = TradingStateManager()

        manager.pause(changed_by="user")
        assert manager.get_state().state == StateValue.PAUSED

        manager.halt(changed_by="system", reason="Critical error")
        assert manager.get_state().state == StateValue.HALTED
        assert manager.get_state().can_resume is False
