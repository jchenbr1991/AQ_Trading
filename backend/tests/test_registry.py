# backend/tests/test_registry.py
import pytest
import tempfile
import os
from unittest.mock import AsyncMock

from src.strategies.registry import StrategyRegistry
from src.strategies.base import Strategy, MarketData
from src.strategies.signals import Signal


# Test strategy for registry tests
class DummyStrategy(Strategy):
    name = "dummy"
    symbols = ["TEST"]

    def __init__(self, name: str, symbols: list[str], param_a: int = 10):
        self.name = name
        self.symbols = symbols
        self.param_a = param_a

    async def on_market_data(self, data: MarketData, context) -> list[Signal]:
        return []


class TestStrategyRegistry:
    @pytest.fixture
    def config_file(self, tmp_path):
        config_content = """
strategies:
  - name: test_strategy
    class: tests.test_registry.DummyStrategy
    account_id: "ACC001"
    symbols: ["AAPL", "TSLA"]
    params:
      param_a: 20
    enabled: true
  - name: disabled_strategy
    class: tests.test_registry.DummyStrategy
    account_id: "ACC001"
    symbols: ["SPY"]
    params: {}
    enabled: false
"""
        config_path = tmp_path / "strategies.yaml"
        config_path.write_text(config_content)
        return str(config_path)

    @pytest.fixture
    def mock_portfolio(self):
        return AsyncMock()

    async def test_load_enabled_strategies(self, config_file, mock_portfolio):
        registry = StrategyRegistry(config_file, mock_portfolio)

        await registry.load_strategies()

        strategies = registry.all_strategies()
        assert len(strategies) == 1
        assert strategies[0].name == "test_strategy"
        assert strategies[0].symbols == ["AAPL", "TSLA"]
        assert strategies[0].param_a == 20

    async def test_get_strategy_by_name(self, config_file, mock_portfolio):
        registry = StrategyRegistry(config_file, mock_portfolio)
        await registry.load_strategies()

        strategy = registry.get_strategy("test_strategy")

        assert strategy is not None
        assert strategy.name == "test_strategy"

    async def test_get_nonexistent_strategy_returns_none(self, config_file, mock_portfolio):
        registry = StrategyRegistry(config_file, mock_portfolio)
        await registry.load_strategies()

        strategy = registry.get_strategy("nonexistent")

        assert strategy is None

    async def test_shutdown_calls_on_stop(self, config_file, mock_portfolio):
        registry = StrategyRegistry(config_file, mock_portfolio)
        await registry.load_strategies()

        strategy = registry.get_strategy("test_strategy")
        strategy.on_stop = AsyncMock()

        await registry.shutdown()

        strategy.on_stop.assert_called_once()
