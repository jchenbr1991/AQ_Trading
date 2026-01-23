from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.risk.manager import RiskManager
from src.risk.models import RiskConfig
from src.strategies.signals import Signal


@pytest.fixture
def config():
    return RiskConfig(
        account_id="ACC001",
        daily_loss_limit=Decimal("1000"),
        max_drawdown_pct=Decimal("10"),
        # Set high enough to not interfere with loss limit tests
        max_position_value=Decimal("100000"),
        max_position_pct=Decimal("100"),
        max_quantity_per_order=10000,
        max_exposure_pct=Decimal("100"),
    )


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(
        return_value=MagicMock(total_equity=Decimal("100000"), buying_power=Decimal("50000"))
    )
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


class TestLossLimits:
    @pytest.mark.asyncio
    async def test_daily_loss_triggers_kill_switch(self, config, mock_portfolio):
        """Kill switch activates when daily loss exceeded."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Simulate losses
        manager.update_daily_pnl(Decimal("-1100"))  # Exceeds 1000 limit

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert manager.is_killed() is True
        assert "Daily loss limit" in manager._kill_reason

    @pytest.mark.asyncio
    async def test_within_daily_loss_ok(self, config, mock_portfolio):
        """Trading allowed when within daily loss limit."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        manager.update_daily_pnl(Decimal("-500"))  # Within limit

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert "loss_limits" in result.checks_passed
        assert manager.is_killed() is False

    @pytest.mark.asyncio
    async def test_drawdown_triggers_kill_switch(self, config, mock_portfolio):
        """Kill switch activates when drawdown exceeded."""
        # Peak was 100k, now 89k = 11% drawdown > 10%
        mock_portfolio.get_account = AsyncMock(
            return_value=MagicMock(total_equity=Decimal("89000"), buying_power=Decimal("50000"))
        )

        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))
        manager._peak_equity = Decimal("100000")

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert manager.is_killed() is True
        assert "Drawdown" in manager._kill_reason

    @pytest.mark.asyncio
    async def test_peak_equity_updates(self, config, mock_portfolio):
        """Peak equity updates when equity increases."""
        mock_portfolio.get_account = AsyncMock(
            return_value=MagicMock(
                total_equity=Decimal("110000"),  # New high
                buying_power=Decimal("50000"),
            )
        )

        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))
        manager._peak_equity = Decimal("100000")

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        await manager.evaluate(signal)

        assert manager._peak_equity == Decimal("110000")

    def test_reset_daily_stats(self, config, mock_portfolio):
        """Daily stats reset at start of day."""
        manager = RiskManager(config, mock_portfolio)
        manager._daily_pnl = Decimal("-500")

        manager.reset_daily_stats()

        assert manager._daily_pnl == Decimal("0")

    def test_update_daily_pnl(self, config, mock_portfolio):
        """update_daily_pnl accumulates P&L."""
        manager = RiskManager(config, mock_portfolio)

        manager.update_daily_pnl(Decimal("100"))
        manager.update_daily_pnl(Decimal("-50"))
        manager.update_daily_pnl(Decimal("25"))

        assert manager._daily_pnl == Decimal("75")
