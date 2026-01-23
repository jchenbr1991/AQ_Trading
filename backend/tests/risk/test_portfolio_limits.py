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
        max_positions=3,
        max_exposure_pct=Decimal("50"),
        # Set high enough to not interfere with portfolio limit tests
        max_position_value=Decimal("100000"),
        max_position_pct=Decimal("100"),
        max_quantity_per_order=10000,
    )


def make_position(symbol: str, market_value: Decimal):
    pos = MagicMock()
    pos.symbol = symbol
    pos.market_value = market_value
    return pos


class TestPortfolioLimits:
    @pytest.mark.asyncio
    async def test_max_positions_exceeded(self, config):
        """Reject new position when at max_positions."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(
            return_value=MagicMock(total_equity=Decimal("100000"), buying_power=Decimal("50000"))
        )
        portfolio.get_positions = AsyncMock(
            return_value=[
                make_position("AAPL", Decimal("10000")),
                make_position("GOOGL", Decimal("10000")),
                make_position("MSFT", Decimal("10000")),
            ]
        )
        portfolio.get_position = AsyncMock(return_value=None)  # New position

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="TSLA",  # New position
            action="buy",
            quantity=10,
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "portfolio_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_adding_to_existing_position_ok(self, config):
        """Can add to existing position even at max_positions."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(
            return_value=MagicMock(total_equity=Decimal("100000"), buying_power=Decimal("50000"))
        )
        portfolio.get_positions = AsyncMock(
            return_value=[
                make_position("AAPL", Decimal("10000")),
                make_position("GOOGL", Decimal("10000")),
                make_position("MSFT", Decimal("10000")),
            ]
        )
        existing = MagicMock()
        existing.symbol = "AAPL"
        portfolio.get_position = AsyncMock(return_value=existing)

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",  # Existing position
            action="buy",
            quantity=10,
        )
        result = await manager.evaluate(signal)

        assert "portfolio_limits" in result.checks_passed

    @pytest.mark.asyncio
    async def test_exposure_exceeded(self, config):
        """Reject when new exposure would exceed max_exposure_pct."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(
            return_value=MagicMock(total_equity=Decimal("100000"), buying_power=Decimal("50000"))
        )
        portfolio.get_positions = AsyncMock(
            return_value=[
                make_position("AAPL", Decimal("45000")),  # Already at 45%
            ]
        )
        portfolio.get_position = AsyncMock(return_value=None)

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="GOOGL",
            action="buy",
            quantity=100,  # 100 * 100 = 10000 -> 55% total > 50%
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "portfolio_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_insufficient_buying_power(self, config):
        """Reject when insufficient buying power."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(
            return_value=MagicMock(
                total_equity=Decimal("100000"),
                buying_power=Decimal("1000"),  # Low buying power
            )
        )
        portfolio.get_positions = AsyncMock(return_value=[])
        portfolio.get_position = AsyncMock(return_value=None)

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=50,  # 50 * 100 = 5000 > 1000 buying power
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "portfolio_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_sell_ignores_exposure(self, config):
        """Sell orders don't add exposure."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(
            return_value=MagicMock(
                total_equity=Decimal("100000"),
                buying_power=Decimal("0"),  # No buying power
            )
        )
        portfolio.get_positions = AsyncMock(
            return_value=[
                make_position("AAPL", Decimal("50000")),  # At 50% exposure
            ]
        )
        portfolio.get_position = AsyncMock(return_value=MagicMock())

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(strategy_id="test", symbol="AAPL", action="sell", quantity=100)
        result = await manager.evaluate(signal)

        assert "portfolio_limits" in result.checks_passed
