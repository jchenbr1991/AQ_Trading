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


class TestPositionLimits:
    @pytest.mark.asyncio
    async def test_quantity_exceeds_max(self, config, mock_portfolio):
        """Reject when quantity exceeds max_quantity_per_order."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("50"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=150,  # Exceeds 100 limit
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_value_exceeds_max(self, config, mock_portfolio):
        """Reject when position value exceeds max_position_value."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("200"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=60,  # 60 * 200 = 12000 > 10000 limit
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_pct_exceeds_max(self, config, mock_portfolio):
        """Reject when position % exceeds max_position_pct."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=60,  # 60 * 100 = 6000 = 6% > 5% limit
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_within_all_limits(self, config, mock_portfolio):
        """Accept when within all position limits."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=40,  # 40 * 100 = 4000 = 4% (all within limits)
        )
        result = await manager.evaluate(signal)

        assert "position_limits" in result.checks_passed

    @pytest.mark.asyncio
    async def test_sell_always_passes(self, config, mock_portfolio):
        """Sell orders always pass position limits."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="sell",
            quantity=1000,  # Way over limits, but sell
        )
        result = await manager.evaluate(signal)

        assert "position_limits" in result.checks_passed
