# backend/tests/test_engine.py
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.strategies.engine import StrategyEngine
from src.strategies.base import Strategy, MarketData, OrderFill
from src.strategies.signals import Signal


class MockStrategy(Strategy):
    name = "mock"
    symbols = ["AAPL"]

    def __init__(self):
        self.received_data = []
        self.signals_to_return = []

    async def on_market_data(self, data: MarketData, context) -> list[Signal]:
        self.received_data.append(data)
        return self.signals_to_return


class TestStrategyEngine:
    @pytest.fixture
    def mock_registry(self):
        registry = MagicMock()
        registry.all_strategies.return_value = []
        registry.get_strategy.return_value = None
        registry.get_account_id.return_value = "ACC001"
        return registry

    @pytest.fixture
    def mock_portfolio(self):
        return AsyncMock()

    @pytest.fixture
    def mock_risk_manager(self):
        risk_manager = AsyncMock()
        risk_manager.evaluate.return_value = True
        return risk_manager

    async def test_dispatches_data_to_subscribed_strategy(
        self, mock_registry, mock_portfolio, mock_risk_manager
    ):
        strategy = MockStrategy()
        mock_registry.all_strategies.return_value = [strategy]

        engine = StrategyEngine(mock_registry, mock_portfolio, mock_risk_manager)
        engine._running = True

        data = MarketData(
            symbol="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
            volume=1000000,
            timestamp=datetime.utcnow(),
        )

        await engine.on_market_data(data)

        assert len(strategy.received_data) == 1
        assert strategy.received_data[0].symbol == "AAPL"

    async def test_does_not_dispatch_to_unsubscribed_strategy(
        self, mock_registry, mock_portfolio, mock_risk_manager
    ):
        strategy = MockStrategy()
        strategy.symbols = ["TSLA"]  # Not subscribed to AAPL
        mock_registry.all_strategies.return_value = [strategy]

        engine = StrategyEngine(mock_registry, mock_portfolio, mock_risk_manager)
        engine._running = True

        data = MarketData(
            symbol="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
            volume=1000000,
            timestamp=datetime.utcnow(),
        )

        await engine.on_market_data(data)

        assert len(strategy.received_data) == 0

    async def test_forwards_signals_to_risk_manager(
        self, mock_registry, mock_portfolio, mock_risk_manager
    ):
        strategy = MockStrategy()
        strategy.signals_to_return = [
            Signal(
                strategy_id="mock",
                symbol="AAPL",
                action="buy",
                quantity=100,
                reason="Test signal",
            )
        ]
        mock_registry.all_strategies.return_value = [strategy]

        engine = StrategyEngine(mock_registry, mock_portfolio, mock_risk_manager)
        engine._running = True

        data = MarketData(
            symbol="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
            volume=1000000,
            timestamp=datetime.utcnow(),
        )

        await engine.on_market_data(data)

        mock_risk_manager.evaluate.assert_called_once()
        call_signal = mock_risk_manager.evaluate.call_args[0][0]
        assert call_signal.symbol == "AAPL"
        assert call_signal.action == "buy"

    async def test_strategy_error_does_not_crash_engine(
        self, mock_registry, mock_portfolio, mock_risk_manager
    ):
        good_strategy = MockStrategy()
        good_strategy.name = "good"

        bad_strategy = MockStrategy()
        bad_strategy.name = "bad"
        bad_strategy.on_market_data = AsyncMock(side_effect=Exception("Strategy error"))

        mock_registry.all_strategies.return_value = [bad_strategy, good_strategy]

        engine = StrategyEngine(mock_registry, mock_portfolio, mock_risk_manager)
        engine._running = True

        data = MarketData(
            symbol="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
            volume=1000000,
            timestamp=datetime.utcnow(),
        )

        # Should not raise
        await engine.on_market_data(data)

        # Good strategy still received data
        assert len(good_strategy.received_data) == 1

    async def test_on_fill_notifies_strategy(
        self, mock_registry, mock_portfolio, mock_risk_manager
    ):
        strategy = MockStrategy()
        strategy.on_fill = AsyncMock()
        mock_registry.get_strategy.return_value = strategy

        engine = StrategyEngine(mock_registry, mock_portfolio, mock_risk_manager)

        fill = OrderFill(
            order_id="ORD001",
            strategy_id="mock",
            symbol="AAPL",
            action="buy",
            quantity=100,
            price=Decimal("185.50"),
            commission=Decimal("1.00"),
            timestamp=datetime.utcnow(),
        )

        await engine.on_fill(fill)

        strategy.on_fill.assert_called_once_with(fill)
