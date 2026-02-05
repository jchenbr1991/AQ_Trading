# backend/tests/integration/test_live_mode.py
"""Integration tests for live trading mode configuration and verification.

Implements T048: Integration test verifying mode-agnostic strategy behavior.

Tests:
- SC-002: Strategy produces identical signals in all modes
- SC-006: Live mode uses same strategy logic as backtest/paper
- Risk limit validation
- Broker connection verification
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from src.broker.live_broker import (
    BrokerConnectionError,
    LiveBroker,
    LiveTradingNotConfirmedError,
    RiskLimitExceededError,
    RiskLimits,
)
from src.broker.paper_broker import PaperBroker
from src.orders.models import Order, OrderStatus
from src.strategies.base import MarketData
from src.strategies.context import StrategyContext
from src.strategies.examples.trend_breakout import TrendBreakoutStrategy
from src.strategies.signals import Signal


def create_test_order(
    symbol: str = "AAPL",
    side: str = "buy",
    quantity: int = 100,
    order_type: str = "market",
    order_id: str = "TEST-001",
) -> Order:
    """Helper to create test orders with required fields."""
    return Order(
        order_id=order_id,
        broker_order_id=None,
        strategy_id="test",
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=None,
        status=OrderStatus.PENDING,
    )


@dataclass
class SimulatedBar:
    """Simulated OHLCV bar for testing."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class TestLiveBrokerRiskLimits:
    """Test LiveBroker pre-trade validation and risk limits (T047)."""

    @pytest.fixture
    def risk_limits(self) -> RiskLimits:
        """Standard risk limits for testing."""
        return RiskLimits(
            max_position_size=1000,
            max_order_value=Decimal("50000"),
            max_daily_loss=Decimal("5000"),
            max_open_orders=10,
        )

    @pytest.fixture
    def live_broker(self, risk_limits: RiskLimits) -> LiveBroker:
        """Create a live broker wrapping PaperBroker for testing."""
        return LiveBroker(
            inner_broker=PaperBroker(fill_delay=0.01),
            account_id="TEST001",
            risk_limits=risk_limits,
            require_confirmation=True,
        )

    @pytest.mark.asyncio
    async def test_broker_connection_required_for_orders(self, live_broker: LiveBroker):
        """Test that orders cannot be submitted without connection."""
        order = create_test_order(symbol="AAPL", side="buy", quantity=100)

        with pytest.raises(BrokerConnectionError):
            await live_broker.submit_order(order)

    @pytest.mark.asyncio
    async def test_confirmation_required_for_live_trading(self, live_broker: LiveBroker):
        """Test that live trading requires explicit confirmation."""
        await live_broker.connect()

        order = create_test_order(symbol="AAPL", side="buy", quantity=100)

        # Should fail without confirmation
        with pytest.raises(LiveTradingNotConfirmedError):
            await live_broker.submit_order(order)

        # Should succeed after confirmation
        live_broker.confirm_live_trading()
        broker_id = await live_broker.submit_order(order)
        assert broker_id.startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_position_size_limit(self, live_broker: LiveBroker):
        """Test that position size limit is enforced."""
        await live_broker.connect()
        live_broker.confirm_live_trading()

        # Order within limit should succeed
        small_order = create_test_order(quantity=500, order_id="SMALL-001")
        broker_id = await live_broker.submit_order(small_order)
        assert broker_id is not None

        # Order exceeding limit should fail
        large_order = create_test_order(quantity=2000, order_id="LARGE-001")  # Exceeds 1000 limit
        with pytest.raises(RiskLimitExceededError) as exc_info:
            await live_broker.submit_order(large_order)
        assert exc_info.value.limit_type == "max_position_size"

    @pytest.mark.asyncio
    async def test_order_value_limit(self, live_broker: LiveBroker):
        """Test that order value limit is enforced."""
        await live_broker.connect()
        live_broker.confirm_live_trading()

        order = create_test_order(quantity=500)

        # With price making order exceed value limit
        current_price = Decimal("200")  # 500 * 200 = 100,000 > 50,000
        validation = await live_broker.validate_order(order, current_price)
        assert not validation.checks["order_value_ok"]

        # With price within limit
        current_price = Decimal("50")  # 500 * 50 = 25,000 < 50,000
        validation = await live_broker.validate_order(order, current_price)
        assert validation.checks["order_value_ok"]

    @pytest.mark.asyncio
    async def test_open_orders_limit(self, risk_limits: RiskLimits):
        """Test that open orders limit is enforced."""
        # Create broker with very low limit
        broker = LiveBroker(
            inner_broker=PaperBroker(fill_delay=0.01),
            account_id="TEST001",
            risk_limits=RiskLimits(
                max_position_size=10000,
                max_order_value=Decimal("1000000"),
                max_daily_loss=Decimal("100000"),
                max_open_orders=2,  # Very low limit
            ),
            require_confirmation=False,
        )
        await broker.connect()

        # Submit orders up to limit
        for i in range(2):
            order = create_test_order(quantity=10, order_id=f"LIMIT-{i}")
            await broker.submit_order(order)

        # Third order should fail
        order = create_test_order(quantity=10, order_id="LIMIT-FAIL")
        with pytest.raises(RiskLimitExceededError) as exc_info:
            await broker.submit_order(order)
        assert exc_info.value.limit_type == "max_open_orders"

    @pytest.mark.asyncio
    async def test_daily_loss_limit(self, risk_limits: RiskLimits):
        """Test that daily loss limit is enforced."""
        broker = LiveBroker(
            inner_broker=PaperBroker(fill_delay=0.01),
            account_id="TEST001",
            risk_limits=risk_limits,
            require_confirmation=False,
        )
        await broker.connect()

        # Simulate daily loss exceeding limit
        broker.update_daily_pnl(Decimal("-6000"))  # Exceeds 5000 limit

        order = create_test_order(quantity=10)

        with pytest.raises(RiskLimitExceededError) as exc_info:
            await broker.submit_order(order)
        assert exc_info.value.limit_type == "max_daily_loss"

    @pytest.mark.asyncio
    async def test_connection_verification(self, live_broker: LiveBroker):
        """Test broker connection verification."""
        # Before connection
        verification = await live_broker.verify_connection()
        assert not verification.passed
        assert not verification.checks["connection_established"]

        # After connection
        await live_broker.connect()
        verification = await live_broker.verify_connection()
        assert verification.passed
        assert verification.checks["connection_established"]
        assert verification.checks["account_configured"]

    @pytest.mark.asyncio
    async def test_revoke_confirmation(self, live_broker: LiveBroker):
        """Test that confirmation can be revoked."""
        await live_broker.connect()
        live_broker.confirm_live_trading()
        assert live_broker.is_confirmed

        live_broker.revoke_confirmation()
        assert not live_broker.is_confirmed

        # Orders should fail after revocation
        order = create_test_order(quantity=10)
        with pytest.raises(LiveTradingNotConfirmedError):
            await live_broker.submit_order(order)


class TestModeAgnosticStrategyBehavior:
    """Test that strategy logic is identical across all modes (SC-002, SC-006)."""

    @pytest.fixture
    def strategy_params(self) -> dict[str, Any]:
        """Common strategy parameters for all modes."""
        return {
            "name": "test-mode-agnostic",
            "symbols": ["AAPL"],
            "entry_threshold": 0.0,
            "exit_threshold": -0.02,
            "position_sizing": "equal_weight",
            "position_size": 100,
            "feature_weights": {
                "roc_20": 0.5,
                "price_vs_ma_20": 0.5,
                "price_vs_high_20": 0.5,
                "volume_zscore": 0.5,
            },
            "factor_weights": {
                "momentum_factor": 0.5,
                "breakout_factor": 0.5,
            },
        }

    @pytest.fixture
    def test_bars(self) -> list[SimulatedBar]:
        """Generate deterministic test data for mode comparison."""
        bars = []
        base_date = datetime(2024, 1, 1, 9, 30, tzinfo=timezone.utc)
        base_price = Decimal("150.00")

        # Create 40 bars with trend pattern
        for i in range(40):
            timestamp = base_date + timedelta(days=i)

            if i < 25:
                # Accumulation with slight uptrend
                price_change = Decimal(str(i * 0.3))
            else:
                # Pullback
                price_change = Decimal(str(7.5 - (i - 25) * 0.6))

            close_price = base_price + price_change
            volume = int(1000000 + i * 10000)

            bars.append(
                SimulatedBar(
                    symbol="AAPL",
                    timestamp=timestamp,
                    open=close_price - Decimal("0.25"),
                    high=close_price + Decimal("0.50"),
                    low=close_price - Decimal("0.50"),
                    close=close_price,
                    volume=volume,
                )
            )

        return bars

    def _create_context(self, has_position: bool, quantity: int = 0) -> StrategyContext:
        """Create mock strategy context."""

        @dataclass
        class MockPosition:
            quantity: int
            avg_cost: Decimal

        context = MagicMock(spec=StrategyContext)

        async def get_position(symbol: str):
            if has_position:
                return MockPosition(quantity=quantity, avg_cost=Decimal("150.00"))
            return None

        context.get_position = get_position
        return context

    def _bar_to_market_data(self, bar: SimulatedBar) -> MarketData:
        """Convert bar to MarketData."""
        return MarketData(
            symbol=bar.symbol,
            price=bar.close,
            bid=bar.close - Decimal("0.01"),
            ask=bar.close + Decimal("0.01"),
            volume=bar.volume,
            timestamp=bar.timestamp,
        )

    async def _run_strategy_simulation(
        self, strategy: TrendBreakoutStrategy, bars: list[SimulatedBar]
    ) -> list[Signal]:
        """Run strategy through bars and collect signals."""
        signals = []
        position_qty = 0

        for bar in bars:
            context = self._create_context(has_position=position_qty > 0, quantity=position_qty)
            market_data = self._bar_to_market_data(bar)

            new_signals = await strategy.on_market_data(market_data, context)

            for signal in new_signals:
                signals.append(signal)
                if signal.action == "buy":
                    position_qty += signal.quantity
                elif signal.action == "sell":
                    position_qty -= signal.quantity

        return signals

    @pytest.mark.asyncio
    async def test_live_mode_uses_same_strategy_logic(
        self, strategy_params: dict[str, Any], test_bars: list[SimulatedBar]
    ):
        """Test that live mode produces identical signals to backtest/paper.

        FR-021: Same logic for backtest/paper/live modes.
        SC-006: Live mode behavior verification.

        The strategy instance is identical across all modes - only the broker
        and execution path differ.
        """
        # Create three identical strategy instances (one per mode)
        backtest_strategy = TrendBreakoutStrategy(**strategy_params)
        paper_strategy = TrendBreakoutStrategy(**strategy_params)
        live_strategy = TrendBreakoutStrategy(**strategy_params)

        # Initialize all
        await backtest_strategy.on_start()
        await paper_strategy.on_start()
        await live_strategy.on_start()

        # Run simulations
        backtest_signals = await self._run_strategy_simulation(backtest_strategy, test_bars)
        paper_signals = await self._run_strategy_simulation(paper_strategy, test_bars)
        live_signals = await self._run_strategy_simulation(live_strategy, test_bars)

        # Cleanup
        await backtest_strategy.on_stop()
        await paper_strategy.on_stop()
        await live_strategy.on_stop()

        # All modes should produce identical signals
        assert len(backtest_signals) == len(paper_signals) == len(live_signals), (
            f"Signal count mismatch: backtest={len(backtest_signals)}, "
            f"paper={len(paper_signals)}, live={len(live_signals)}"
        )

        for i, (bt, paper, live) in enumerate(
            zip(backtest_signals, paper_signals, live_signals, strict=False)
        ):
            # Same action
            assert bt.action == paper.action == live.action, f"Signal {i} action mismatch"
            # Same symbol
            assert bt.symbol == paper.symbol == live.symbol, f"Signal {i} symbol mismatch"
            # Same quantity
            assert bt.quantity == paper.quantity == live.quantity, f"Signal {i} quantity mismatch"
            # Same factor scores (within floating point tolerance)
            for factor_name in bt.factor_scores:
                bt_score = float(bt.factor_scores.get(factor_name, 0))
                paper_score = float(paper.factor_scores.get(factor_name, 0))
                live_score = float(live.factor_scores.get(factor_name, 0))
                assert (
                    abs(bt_score - paper_score) < 1e-6
                ), f"Signal {i} factor {factor_name} backtest vs paper mismatch"
                assert (
                    abs(bt_score - live_score) < 1e-6
                ), f"Signal {i} factor {factor_name} backtest vs live mismatch"

        print("\nMode-agnostic test PASSED")
        print(f"  All {len(backtest_signals)} signals identical across modes")

    @pytest.mark.asyncio
    async def test_strategy_uses_abstract_interfaces(self, strategy_params: dict[str, Any]):
        """Test that strategy only depends on abstract interfaces.

        The strategy should not have any direct dependency on broker
        implementations - it only generates signals.
        """
        strategy = TrendBreakoutStrategy(**strategy_params)

        # Verify strategy doesn't reference any broker
        assert not hasattr(strategy, "_broker")
        assert not hasattr(strategy, "broker")

        # Verify strategy only uses documented interfaces
        # - MarketData for input
        # - StrategyContext for state queries
        # - Signal for output
        await strategy.on_start()

        # The on_market_data method signature requires only MarketData and Context
        import inspect

        sig = inspect.signature(strategy.on_market_data)
        params = list(sig.parameters.keys())
        assert "data" in params
        assert "context" in params
        # No broker parameter
        assert "broker" not in params

        await strategy.on_stop()
        print("\nAbstract interface test PASSED - strategy is broker-agnostic")


class TestLiveModeIntegration:
    """Integration tests for live mode with API endpoints."""

    @pytest.mark.asyncio
    async def test_live_broker_with_risk_validation_workflow(self):
        """Test complete workflow: connect -> validate -> submit -> cancel."""
        broker = LiveBroker(
            inner_broker=PaperBroker(fill_delay=0.01),
            account_id="INTEGRATION_TEST",
            risk_limits=RiskLimits(
                max_position_size=500,
                max_order_value=Decimal("25000"),
                max_daily_loss=Decimal("2500"),
                max_open_orders=5,
            ),
            require_confirmation=True,
        )

        # Step 1: Connect
        await broker.connect()
        assert broker.is_connected

        # Step 2: Verify connection
        verification = await broker.verify_connection()
        assert verification.passed

        # Step 3: Confirm live trading
        broker.confirm_live_trading()
        assert broker.is_confirmed

        # Step 4: Submit valid order
        order = create_test_order(quantity=100, order_id="WORKFLOW-001")
        broker_id = await broker.submit_order(order)
        assert broker_id.startswith("PAPER-")

        # Step 5: Check order status
        status = await broker.get_order_status(broker_id)
        assert status == OrderStatus.SUBMITTED

        # Step 6: Cancel order
        cancelled = await broker.cancel_order(broker_id)
        assert cancelled
        status = await broker.get_order_status(broker_id)
        assert status == OrderStatus.CANCELLED

        # Step 7: Disconnect
        await broker.disconnect()
        assert not broker.is_connected

        print("\nLive mode integration workflow PASSED")

    @pytest.mark.asyncio
    async def test_risk_limits_from_config(self):
        """Test RiskLimits creation from config dictionary."""
        config = {
            "max_position_size": 2000,
            "max_order_value": 100000,
            "max_daily_loss": 10000,
            "max_open_orders": 20,
        }

        limits = RiskLimits.from_dict(config)

        assert limits.max_position_size == 2000
        assert limits.max_order_value == Decimal("100000")
        assert limits.max_daily_loss == Decimal("10000")
        assert limits.max_open_orders == 20

    @pytest.mark.asyncio
    async def test_validation_result_details(self):
        """Test that validation provides detailed check results."""
        broker = LiveBroker(
            inner_broker=PaperBroker(fill_delay=0.01),
            account_id="TEST",
            risk_limits=RiskLimits(),
            require_confirmation=True,
        )

        # Before connection - multiple checks should fail
        order = create_test_order(quantity=100)
        validation = await broker.validate_order(order)

        assert not validation.passed
        assert "broker_connected" in validation.checks
        assert not validation.checks["broker_connected"]
        assert "live_confirmed" in validation.checks
        assert not validation.checks["live_confirmed"]

        # After full setup - all checks should pass
        await broker.connect()
        broker.confirm_live_trading()
        validation = await broker.validate_order(order)

        assert validation.passed
        assert all(validation.checks.values())

        print("\nValidation details test PASSED")
