from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.risk.manager import RiskManager
from src.risk.models import RiskConfig
from src.strategies.signals import Signal


@pytest.fixture
def config():
    return RiskConfig(account_id="ACC001")


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(
        return_value=MagicMock(total_equity=Decimal("100000"), buying_power=Decimal("50000"))
    )
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


@pytest.fixture
def risk_manager(config, mock_portfolio):
    return RiskManager(config, mock_portfolio)


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_blocks_all_signals(self, risk_manager):
        """When kill switch is active, all signals are rejected."""
        risk_manager.activate_kill_switch("Manual stop")

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await risk_manager.evaluate(signal)

        assert result.approved is False
        assert "kill_switch" in result.checks_failed
        assert "Manual stop" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_deactivate_kill_switch(self, risk_manager):
        """Deactivating kill switch allows signals again."""
        risk_manager.activate_kill_switch("Test")
        risk_manager.deactivate_kill_switch()

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        risk_manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        result = await risk_manager.evaluate(signal)

        assert result.approved is True

    def test_is_killed_property(self, risk_manager):
        """is_killed reflects kill switch state."""
        assert risk_manager.is_killed() is False

        risk_manager.activate_kill_switch("Test")
        assert risk_manager.is_killed() is True

        risk_manager.deactivate_kill_switch()
        assert risk_manager.is_killed() is False


class TestStrategyPause:
    @pytest.mark.asyncio
    async def test_paused_strategy_signals_rejected(self, risk_manager):
        """Signals from paused strategy are rejected."""
        risk_manager.pause_strategy("momentum")

        signal = Signal(strategy_id="momentum", symbol="AAPL", action="buy", quantity=10)
        result = await risk_manager.evaluate(signal)

        assert result.approved is False
        assert "strategy_paused" in result.checks_failed

    @pytest.mark.asyncio
    async def test_other_strategies_not_affected(self, risk_manager):
        """Other strategies work when one is paused."""
        risk_manager.pause_strategy("momentum")
        risk_manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(strategy_id="mean_reversion", symbol="AAPL", action="buy", quantity=10)
        result = await risk_manager.evaluate(signal)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_resume_strategy(self, risk_manager):
        """Resumed strategy can trade again."""
        risk_manager.pause_strategy("momentum")
        risk_manager.resume_strategy("momentum")
        risk_manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(strategy_id="momentum", symbol="AAPL", action="buy", quantity=10)
        result = await risk_manager.evaluate(signal)

        assert result.approved is True

    def test_is_strategy_paused(self, risk_manager):
        """is_strategy_paused reflects pause state."""
        assert risk_manager.is_strategy_paused("test") is False

        risk_manager.pause_strategy("test")
        assert risk_manager.is_strategy_paused("test") is True

        risk_manager.resume_strategy("test")
        assert risk_manager.is_strategy_paused("test") is False
