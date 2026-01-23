from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.risk.manager import RiskManager
from src.risk.models import RiskConfig
from src.strategies.signals import Signal


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(
        return_value=MagicMock(total_equity=Decimal("100000"), buying_power=Decimal("50000"))
    )
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


class TestSymbolRestrictions:
    @pytest.mark.asyncio
    async def test_blocked_symbol_rejected(self, mock_portfolio):
        """Signals for blocked symbols are rejected."""
        config = RiskConfig(account_id="ACC001", blocked_symbols=["BANNED", "RESTRICTED"])
        manager = RiskManager(config, mock_portfolio)

        signal = Signal(strategy_id="test", symbol="BANNED", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "symbol_allowed" in result.checks_failed

    @pytest.mark.asyncio
    async def test_allowed_symbol_passes(self, mock_portfolio):
        """Non-blocked symbols pass the check."""
        config = RiskConfig(account_id="ACC001", blocked_symbols=["BANNED"])
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert "symbol_allowed" in result.checks_passed

    @pytest.mark.asyncio
    async def test_allowed_list_only(self, mock_portfolio):
        """When allowed_symbols set, only those symbols pass."""
        config = RiskConfig(account_id="ACC001", allowed_symbols=["AAPL", "GOOGL", "MSFT"])
        manager = RiskManager(config, mock_portfolio)

        signal = Signal(strategy_id="test", symbol="TSLA", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "symbol_allowed" in result.checks_failed

    @pytest.mark.asyncio
    async def test_allowed_list_passes(self, mock_portfolio):
        """Symbols in allowed_symbols list pass."""
        config = RiskConfig(account_id="ACC001", allowed_symbols=["AAPL", "GOOGL"])
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert "symbol_allowed" in result.checks_passed

    @pytest.mark.asyncio
    async def test_blocked_takes_precedence(self, mock_portfolio):
        """Blocked list takes precedence over allowed list."""
        config = RiskConfig(
            account_id="ACC001", blocked_symbols=["AAPL"], allowed_symbols=["AAPL", "GOOGL"]
        )
        manager = RiskManager(config, mock_portfolio)

        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=10)
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "symbol_allowed" in result.checks_failed
