"""Tests for RiskManager Greeks integration.

Tests cover V2 Pre-order Greeks Check integration:
- RiskManager._check_greeks_limits calls GreeksGate
- RiskManager.evaluate includes greeks_limits check
- Greeks check is skipped if no GreeksGate configured
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.greeks.v2_models import GreeksCheckResult
from src.risk.models import RiskConfig
from src.strategies.signals import Signal


def _make_signal(
    symbol: str = "AAPL240119C00150000",
    action: str = "buy",
    quantity: int = 10,
    strategy_id: str = "strat_001",
) -> Signal:
    """Factory function to create Signal for testing."""
    return Signal(
        symbol=symbol,
        action=action,
        quantity=quantity,
        strategy_id=strategy_id,
        reason="test signal",
    )


def _make_mock_portfolio():
    """Create a mock portfolio for testing."""
    mock = MagicMock()
    mock.get_account = AsyncMock(
        return_value=MagicMock(
            total_equity=Decimal("100000"),
            buying_power=Decimal("50000"),
        )
    )
    mock.get_positions = AsyncMock(return_value=[])
    mock.get_position = AsyncMock(return_value=None)
    return mock


class TestRiskManagerGreeksLimits:
    """Tests for RiskManager Greeks limit checking."""

    @pytest.mark.asyncio
    async def test_check_greeks_limits_calls_gate(self):
        """_check_greeks_limits should call GreeksGate.check_order."""
        from src.risk.manager import RiskManager

        config = RiskConfig(account_id="acc_001")
        portfolio = _make_mock_portfolio()

        mock_gate = MagicMock()
        mock_gate.check_order = AsyncMock(
            return_value=GreeksCheckResult(
                ok=True,
                reason_code="APPROVED",
                details=None,
            )
        )

        manager = RiskManager(
            config=config,
            portfolio=portfolio,
            greeks_gate=mock_gate,
        )

        signal = _make_signal()
        result = await manager._check_greeks_limits(signal)

        assert result is True
        mock_gate.check_order.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_greeks_limits_blocks_on_breach(self):
        """_check_greeks_limits should return False on HARD_BREACH."""
        from src.risk.manager import RiskManager

        config = RiskConfig(account_id="acc_001")
        portfolio = _make_mock_portfolio()

        mock_gate = MagicMock()
        mock_gate.check_order = AsyncMock(
            return_value=GreeksCheckResult(
                ok=False,
                reason_code="HARD_BREACH",
                details=None,
            )
        )

        manager = RiskManager(
            config=config,
            portfolio=portfolio,
            greeks_gate=mock_gate,
        )

        signal = _make_signal()
        result = await manager._check_greeks_limits(signal)

        assert result is False

    @pytest.mark.asyncio
    async def test_check_greeks_limits_skipped_if_no_gate(self):
        """_check_greeks_limits should return True if no gate configured."""
        from src.risk.manager import RiskManager

        config = RiskConfig(account_id="acc_001")
        portfolio = _make_mock_portfolio()

        manager = RiskManager(
            config=config,
            portfolio=portfolio,
            greeks_gate=None,
        )

        signal = _make_signal()
        result = await manager._check_greeks_limits(signal)

        assert result is True  # Skipped, passes by default

    @pytest.mark.asyncio
    async def test_evaluate_includes_greeks_check(self):
        """RiskManager.evaluate should include greeks_limits check."""
        from src.risk.manager import RiskManager

        config = RiskConfig(account_id="acc_001")
        portfolio = _make_mock_portfolio()

        mock_gate = MagicMock()
        mock_gate.check_order = AsyncMock(
            return_value=GreeksCheckResult(
                ok=False,
                reason_code="HARD_BREACH",
                details=None,
            )
        )

        manager = RiskManager(
            config=config,
            portfolio=portfolio,
            greeks_gate=mock_gate,
        )

        signal = _make_signal()
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "greeks_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_evaluate_passes_when_greeks_approved(self):
        """RiskManager.evaluate should pass when Greeks check approves."""
        from src.risk.manager import RiskManager

        config = RiskConfig(account_id="acc_001")
        portfolio = _make_mock_portfolio()

        mock_gate = MagicMock()
        mock_gate.check_order = AsyncMock(
            return_value=GreeksCheckResult(
                ok=True,
                reason_code="APPROVED",
                details=None,
            )
        )

        manager = RiskManager(
            config=config,
            portfolio=portfolio,
            greeks_gate=mock_gate,
        )

        signal = _make_signal()
        result = await manager.evaluate(signal)

        assert result.approved is True
        assert "greeks_limits" in result.checks_passed

    @pytest.mark.asyncio
    async def test_greeks_check_stores_result_on_signal(self):
        """Greeks check result should be accessible for audit."""
        from src.risk.manager import RiskManager

        config = RiskConfig(account_id="acc_001")
        portfolio = _make_mock_portfolio()

        mock_gate = MagicMock()
        mock_gate.check_order = AsyncMock(
            return_value=GreeksCheckResult(
                ok=True,
                reason_code="APPROVED",
                details=None,
            )
        )

        manager = RiskManager(
            config=config,
            portfolio=portfolio,
            greeks_gate=mock_gate,
        )

        signal = _make_signal()
        result = await manager.evaluate(signal)

        # Greeks check result should be stored
        assert result.greeks_check_result is not None
        assert result.greeks_check_result.reason_code == "APPROVED"
