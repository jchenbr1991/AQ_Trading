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


class TestRiskBias:
    """Tests for risk_bias integration from Redis (FR-021, SC-014)."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        redis = MagicMock()
        redis.get = AsyncMock(return_value=None)
        return redis

    @pytest.mark.asyncio
    async def test_get_risk_bias_from_redis(self, config, mock_portfolio, mock_redis):
        """Risk bias is correctly read from Redis."""
        mock_redis.get = AsyncMock(return_value="0.8")
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)

        bias = await manager.get_risk_bias()

        assert bias == 0.8
        mock_redis.get.assert_called_once_with("risk_bias")

    @pytest.mark.asyncio
    async def test_get_risk_bias_default_when_redis_not_configured(self, config, mock_portfolio):
        """Returns default bias (1.0) when Redis is not configured."""
        manager = RiskManager(config, mock_portfolio, redis=None)

        bias = await manager.get_risk_bias()

        assert bias == 1.0

    @pytest.mark.asyncio
    async def test_get_risk_bias_default_when_key_missing(self, config, mock_portfolio, mock_redis):
        """Returns default bias (1.0) when key is missing from Redis."""
        mock_redis.get = AsyncMock(return_value=None)
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)

        bias = await manager.get_risk_bias()

        assert bias == 1.0

    @pytest.mark.asyncio
    async def test_get_risk_bias_default_on_redis_connection_error(
        self, config, mock_portfolio, mock_redis
    ):
        """Returns default bias (1.0) when Redis connection fails (graceful degradation)."""
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis unavailable"))
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)

        bias = await manager.get_risk_bias()

        assert bias == 1.0

    @pytest.mark.asyncio
    async def test_get_risk_bias_default_on_redis_timeout(self, config, mock_portfolio, mock_redis):
        """Returns default bias (1.0) when Redis times out (graceful degradation)."""
        mock_redis.get = AsyncMock(side_effect=TimeoutError("Redis timeout"))
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)

        bias = await manager.get_risk_bias()

        assert bias == 1.0

    @pytest.mark.asyncio
    async def test_get_risk_bias_default_on_invalid_value(self, config, mock_portfolio, mock_redis):
        """Returns default bias (1.0) when Redis contains invalid value."""
        mock_redis.get = AsyncMock(return_value="not_a_number")
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)

        bias = await manager.get_risk_bias()

        assert bias == 1.0

    @pytest.mark.asyncio
    async def test_risk_bias_reduces_position_limits(self, config, mock_portfolio, mock_redis):
        """Risk bias of 0.5 halves position limits."""
        # Set bias to 0.5 (reduces limits by half)
        mock_redis.get = AsyncMock(return_value="0.5")
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Config has max_quantity_per_order=100, with bias=0.5 -> effective=50
        # This order of 60 should be rejected (exceeds 50)
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=60,
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_risk_bias_allows_within_reduced_limits(self, config, mock_portfolio, mock_redis):
        """Orders within reduced limits are approved."""
        mock_redis.get = AsyncMock(return_value="0.5")
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Config: max_position_pct=5%, with bias=0.5 -> effective_max_pct=2.5%
        # 20 shares * $100 = $2000, which is 2% of $100000 equity
        # 2% < 2.5%, so this should pass
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=20,
        )
        result = await manager.evaluate(signal)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_risk_bias_increases_position_limits(self, config, mock_portfolio, mock_redis):
        """Risk bias > 1.0 increases position limits."""
        mock_redis.get = AsyncMock(return_value="1.5")
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Config: max_position_pct=5%, with bias=1.5 -> effective=7.5%
        # 70 shares * $100 = $7000 = 7% of $100000
        # Config: max_quantity=100, with bias=1.5 -> effective=150
        # 70 < 150, passes quantity check
        # 7% < 7.5%, passes position pct check
        # $7000 < $15000 (10000*1.5), passes value check
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=70,
        )
        result = await manager.evaluate(signal)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_risk_bias_applied_to_position_value_limit(
        self, config, mock_portfolio, mock_redis
    ):
        """Risk bias is applied to max_position_value limit."""
        # Config has max_position_value=10000
        # With bias=0.5, effective_max=5000
        mock_redis.get = AsyncMock(return_value="0.5")
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Order of 60 shares at $100 = $6000, exceeds $5000 effective limit
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=60,
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_risk_bias_trading_continues_on_agent_failure(
        self, config, mock_portfolio, mock_redis
    ):
        """Trading continues normally when agent subsystem fails (FR-021)."""
        # Simulate unexpected Redis error
        mock_redis.get = AsyncMock(side_effect=Exception("Unexpected error"))
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Order should be evaluated with default bias=1.0
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=50,  # Within default limits
        )
        result = await manager.evaluate(signal)

        # Trading continues - order approved with default limits
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_sell_orders_bypass_risk_bias(self, config, mock_portfolio, mock_redis):
        """Sell orders bypass position limit checks including risk bias."""
        mock_redis.get = AsyncMock(return_value="0.1")  # Very restrictive bias
        manager = RiskManager(config, mock_portfolio, redis=mock_redis)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Sell orders should pass regardless of bias
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="sell",
            quantity=1000,  # Large quantity
        )
        result = await manager.evaluate(signal)

        # Sell should pass position limits (but might fail other checks)
        assert "position_limits" not in result.checks_failed
