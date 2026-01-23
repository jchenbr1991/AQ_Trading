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
        max_position_value=Decimal("10000"),
        max_position_pct=Decimal("5"),
        max_quantity_per_order=100,
        max_positions=10,
        max_exposure_pct=Decimal("50"),
        daily_loss_limit=Decimal("1000"),
        max_drawdown_pct=Decimal("10"),
        blocked_symbols=["BANNED"],
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


class TestFullEvaluateFlow:
    @pytest.mark.asyncio
    async def test_all_checks_pass(self, config, mock_portfolio):
        """Signal passes when all checks succeed."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10,  # 10 * 100 = 1000, well within limits
        )
        result = await manager.evaluate(signal)

        assert result.approved is True
        assert result.rejection_reason is None
        assert "symbol_allowed" in result.checks_passed
        assert "position_limits" in result.checks_passed
        assert "portfolio_limits" in result.checks_passed
        assert "loss_limits" in result.checks_passed
        assert len(result.checks_failed) == 0

    @pytest.mark.asyncio
    async def test_first_failure_recorded(self, config, mock_portfolio):
        """First failed check is recorded as rejection reason."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="BANNED",  # Blocked symbol
            action="buy",
            quantity=10,
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert result.rejection_reason == "symbol_allowed"

    @pytest.mark.asyncio
    async def test_multiple_failures(self, config, mock_portfolio):
        """Multiple failures are all recorded."""
        # Make portfolio return high exposure
        mock_portfolio.get_positions = AsyncMock(
            return_value=[MagicMock(market_value=Decimal("45000"))]
        )

        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("1000"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=200,  # Exceeds quantity AND would exceed exposure
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        # Should fail position_limits first (quantity), then portfolio_limits (exposure)
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_kill_switch_short_circuits(self, config, mock_portfolio):
        """Kill switch bypasses all other checks."""
        manager = RiskManager(config, mock_portfolio)
        manager.activate_kill_switch("Emergency")

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=1)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "kill_switch" in result.checks_failed
        # Other checks not run
        assert "symbol_allowed" not in result.checks_passed
        assert "symbol_allowed" not in result.checks_failed

    @pytest.mark.asyncio
    async def test_strategy_pause_short_circuits(self, config, mock_portfolio):
        """Strategy pause bypasses other checks for that strategy."""
        manager = RiskManager(config, mock_portfolio)
        manager.pause_strategy("momentum")

        signal = Signal(strategy_id="momentum", symbol="AAPL", action="buy", quantity=1)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "strategy_paused" in result.checks_failed
