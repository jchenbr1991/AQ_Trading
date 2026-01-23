# Strategy Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a pluggable strategy framework where strategies receive market data, emit Signals, and get notified of fills.

**Architecture:** Strategies are Python classes implementing Strategy ABC. StrategyEngine dispatches market data to subscribed strategies, collects Signals, and forwards them to Risk Manager. StrategyContext provides read-only portfolio access.

**Tech Stack:** Python 3.11, asyncio, Pydantic, PyYAML, pytest-asyncio

---

## Task 1: Create Signal Dataclass

**Files:**
- Create: `backend/src/strategies/__init__.py`
- Create: `backend/src/strategies/signals.py`
- Create: `backend/tests/test_signals.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_signals.py
import pytest
from datetime import datetime
from decimal import Decimal

from src.strategies.signals import Signal


class TestSignal:
    def test_signal_creation_with_defaults(self):
        signal = Signal(
            strategy_id="momentum_v1",
            symbol="AAPL",
            action="buy",
            quantity=100,
        )

        assert signal.strategy_id == "momentum_v1"
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.quantity == 100
        assert signal.order_type == "market"
        assert signal.limit_price is None
        assert signal.reason == ""
        assert isinstance(signal.timestamp, datetime)

    def test_signal_with_limit_order(self):
        signal = Signal(
            strategy_id="mean_rev",
            symbol="TSLA",
            action="sell",
            quantity=50,
            order_type="limit",
            limit_price=Decimal("250.00"),
            reason="Mean reversion target hit",
        )

        assert signal.order_type == "limit"
        assert signal.limit_price == Decimal("250.00")
        assert signal.reason == "Mean reversion target hit"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_signals.py -v`
Expected: FAIL with "No module named 'src.strategies'"

**Step 3: Create package init and signals.py**

```python
# backend/src/strategies/__init__.py
from src.strategies.signals import Signal

__all__ = ["Signal"]
```

```python
# backend/src/strategies/signals.py
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass
class Signal:
    """
    A trading signal emitted by a strategy.

    Signals express intent (buy/sell), not orders. Risk Manager
    validates and Order Manager executes.
    """
    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_signals.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/strategies/ backend/tests/test_signals.py
git commit -m "feat: add Signal dataclass for strategy outputs"
```

---

## Task 2: Create MarketData and OrderFill Dataclasses

**Files:**
- Modify: `backend/src/strategies/__init__.py`
- Create: `backend/src/strategies/base.py`
- Create: `backend/tests/test_base.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_base.py
import pytest
from datetime import datetime
from decimal import Decimal

from src.strategies.base import MarketData, OrderFill


class TestMarketData:
    def test_market_data_creation(self):
        data = MarketData(
            symbol="AAPL",
            price=Decimal("185.50"),
            bid=Decimal("185.45"),
            ask=Decimal("185.55"),
            volume=1000000,
            timestamp=datetime(2026, 1, 23, 10, 30, 0),
        )

        assert data.symbol == "AAPL"
        assert data.price == Decimal("185.50")
        assert data.bid == Decimal("185.45")
        assert data.ask == Decimal("185.55")
        assert data.volume == 1000000


class TestOrderFill:
    def test_order_fill_creation(self):
        fill = OrderFill(
            order_id="ORD001",
            strategy_id="momentum_v1",
            symbol="AAPL",
            action="buy",
            quantity=100,
            price=Decimal("185.50"),
            commission=Decimal("1.00"),
            timestamp=datetime(2026, 1, 23, 10, 30, 0),
        )

        assert fill.order_id == "ORD001"
        assert fill.strategy_id == "momentum_v1"
        assert fill.action == "buy"
        assert fill.quantity == 100
        assert fill.price == Decimal("185.50")
        assert fill.commission == Decimal("1.00")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_base.py -v`
Expected: FAIL with "cannot import name 'MarketData'"

**Step 3: Create base.py with dataclasses**

```python
# backend/src/strategies/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategies.context import StrategyContext
    from src.strategies.signals import Signal


@dataclass
class MarketData:
    """Real-time market data for a symbol."""
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime


@dataclass
class OrderFill:
    """Notification of an executed order."""
    order_id: str
    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    price: Decimal
    commission: Decimal
    timestamp: datetime
```

**Step 4: Update __init__.py**

```python
# backend/src/strategies/__init__.py
from src.strategies.signals import Signal
from src.strategies.base import MarketData, OrderFill

__all__ = ["Signal", "MarketData", "OrderFill"]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_base.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/strategies/
git commit -m "feat: add MarketData and OrderFill dataclasses"
```

---

## Task 3: Create Strategy ABC

**Files:**
- Modify: `backend/src/strategies/base.py`
- Modify: `backend/src/strategies/__init__.py`
- Modify: `backend/tests/test_base.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/test_base.py
from src.strategies.base import Strategy, MarketData, OrderFill
from src.strategies.signals import Signal
from unittest.mock import MagicMock


class TestStrategy:
    def test_concrete_strategy_must_implement_on_market_data(self):
        """Strategy ABC requires on_market_data implementation."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            class IncompleteStrategy(Strategy):
                name = "incomplete"
                symbols = ["AAPL"]

            IncompleteStrategy()

    def test_concrete_strategy_can_be_instantiated(self):
        """A complete Strategy subclass can be instantiated."""
        class SimpleStrategy(Strategy):
            name = "simple"
            symbols = ["AAPL"]

            async def on_market_data(self, data: MarketData, context) -> list[Signal]:
                return []

        strategy = SimpleStrategy()
        assert strategy.name == "simple"
        assert strategy.symbols == ["AAPL"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_base.py::TestStrategy -v`
Expected: FAIL with "cannot import name 'Strategy'"

**Step 3: Add Strategy ABC to base.py**

```python
# Add to backend/src/strategies/base.py after OrderFill class

class Strategy(ABC):
    """
    Abstract base class for trading strategies.

    Strategies receive market data, analyze it, and emit Signals.
    They do not execute orders directly - Risk Manager validates
    and Order Manager executes.
    """
    name: str
    symbols: list[str]

    @abstractmethod
    async def on_market_data(
        self, data: "MarketData", context: "StrategyContext"
    ) -> list["Signal"]:
        """
        React to price updates.

        Args:
            data: New market data for a subscribed symbol
            context: Read-only view of portfolio and quotes

        Returns:
            List of signals (can be empty if no action needed)
        """
        pass

    async def on_fill(self, fill: "OrderFill") -> None:
        """
        Called when an order fills.

        Override to react to fill confirmations. Default does nothing.
        """
        pass

    async def on_start(self) -> None:
        """
        Called when strategy starts.

        Override for initialization logic. Default does nothing.
        """
        pass

    async def on_stop(self) -> None:
        """
        Called when strategy stops.

        Override for cleanup logic. Default does nothing.
        """
        pass
```

**Step 4: Update __init__.py**

```python
# backend/src/strategies/__init__.py
from src.strategies.signals import Signal
from src.strategies.base import MarketData, OrderFill, Strategy

__all__ = ["Signal", "MarketData", "OrderFill", "Strategy"]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_base.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/strategies/
git commit -m "feat: add Strategy ABC with lifecycle hooks"
```

---

## Task 4: Create StrategyContext

**Files:**
- Create: `backend/src/strategies/context.py`
- Modify: `backend/src/strategies/__init__.py`
- Create: `backend/tests/test_context.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_context.py
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.strategies.context import StrategyContext
from src.strategies.base import MarketData


class TestStrategyContext:
    @pytest.fixture
    def mock_portfolio(self):
        portfolio = AsyncMock()
        return portfolio

    @pytest.fixture
    def quote_cache(self):
        return {
            "AAPL": MarketData(
                symbol="AAPL",
                price=Decimal("185.50"),
                bid=Decimal("185.45"),
                ask=Decimal("185.55"),
                volume=1000000,
                timestamp=datetime.utcnow(),
            ),
            "TSLA": MarketData(
                symbol="TSLA",
                price=Decimal("250.00"),
                bid=Decimal("249.90"),
                ask=Decimal("250.10"),
                volume=500000,
                timestamp=datetime.utcnow(),
            ),
        }

    def test_get_quote_returns_cached_data(self, mock_portfolio, quote_cache):
        context = StrategyContext(
            strategy_id="test_strat",
            account_id="ACC001",
            portfolio=mock_portfolio,
            quote_cache=quote_cache,
        )

        quote = context.get_quote("AAPL")

        assert quote is not None
        assert quote.symbol == "AAPL"
        assert quote.price == Decimal("185.50")

    def test_get_quote_returns_none_for_unknown_symbol(self, mock_portfolio, quote_cache):
        context = StrategyContext(
            strategy_id="test_strat",
            account_id="ACC001",
            portfolio=mock_portfolio,
            quote_cache=quote_cache,
        )

        quote = context.get_quote("UNKNOWN")

        assert quote is None

    async def test_get_position_filters_by_strategy(self, mock_portfolio, quote_cache):
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.quantity = 100
        mock_portfolio.get_position.return_value = mock_position

        context = StrategyContext(
            strategy_id="test_strat",
            account_id="ACC001",
            portfolio=mock_portfolio,
            quote_cache=quote_cache,
        )

        position = await context.get_position("AAPL")

        assert position.symbol == "AAPL"
        mock_portfolio.get_position.assert_called_once_with(
            "ACC001", "AAPL", "test_strat"
        )
```

**Step 2: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_context.py -v`
Expected: FAIL with "No module named 'src.strategies.context'"

**Step 3: Create context.py**

```python
# backend/src/strategies/context.py
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategies.base import MarketData
    from src.core.portfolio import PortfolioManager
    from src.models import Position


class StrategyContext:
    """
    Read-only view of portfolio for a specific strategy.

    Provides access to:
    - This strategy's positions only (filtered by strategy_id)
    - Cached market quotes (on-demand pull)
    - P&L calculations for this strategy
    """

    def __init__(
        self,
        strategy_id: str,
        account_id: str,
        portfolio: "PortfolioManager",
        quote_cache: dict[str, "MarketData"],
    ):
        self._strategy_id = strategy_id
        self._account_id = account_id
        self._portfolio = portfolio
        self._quote_cache = quote_cache

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def account_id(self) -> str:
        return self._account_id

    def get_quote(self, symbol: str) -> "MarketData | None":
        """Get cached quote for any symbol."""
        return self._quote_cache.get(symbol)

    async def get_position(self, symbol: str) -> "Position | None":
        """Get this strategy's position in a symbol."""
        return await self._portfolio.get_position(
            self._account_id, symbol, self._strategy_id
        )

    async def get_my_positions(self) -> list["Position"]:
        """Get all positions owned by this strategy."""
        return await self._portfolio.get_positions(
            account_id=self._account_id,
            strategy_id=self._strategy_id,
        )

    async def get_my_pnl(self) -> Decimal:
        """Get unrealized P&L for this strategy's positions."""
        return await self._portfolio.calculate_unrealized_pnl(
            account_id=self._account_id,
            strategy_id=self._strategy_id,
        )
```

**Step 4: Update __init__.py**

```python
# backend/src/strategies/__init__.py
from src.strategies.signals import Signal
from src.strategies.base import MarketData, OrderFill, Strategy
from src.strategies.context import StrategyContext

__all__ = ["Signal", "MarketData", "OrderFill", "Strategy", "StrategyContext"]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_context.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/strategies/ backend/tests/test_context.py
git commit -m "feat: add StrategyContext for read-only portfolio access"
```

---

## Task 5: Create StrategyRegistry

**Files:**
- Create: `backend/src/strategies/registry.py`
- Create: `backend/config/strategies.yaml`
- Modify: `backend/src/strategies/__init__.py`
- Create: `backend/tests/test_registry.py`

**Step 1: Add PyYAML to dependencies**

```bash
cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/pip install pyyaml
```

Also add to `backend/pyproject.toml` dependencies:
```toml
"pyyaml>=6.0",
```

**Step 2: Write the failing test**

```python
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
```

**Step 3: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL with "No module named 'src.strategies.registry'"

**Step 4: Create registry.py**

```python
# backend/src/strategies/registry.py
import importlib
import logging
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.strategies.base import Strategy
    from src.core.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class StrategyRegistry:
    """
    Loads and manages strategy instances from config file.

    Config format (strategies.yaml):
        strategies:
          - name: momentum_v1
            class: src.strategies.examples.momentum.MomentumStrategy
            account_id: "ACC001"
            symbols: ["AAPL", "TSLA"]
            params:
              lookback_period: 20
            enabled: true
    """

    def __init__(self, config_path: str, portfolio: "PortfolioManager"):
        self._config_path = config_path
        self._portfolio = portfolio
        self._strategies: dict[str, "Strategy"] = {}
        self._account_ids: dict[str, str] = {}  # strategy_name -> account_id

    async def load_strategies(self) -> None:
        """Load enabled strategies from config file."""
        with open(self._config_path, "r") as f:
            config = yaml.safe_load(f)

        for entry in config.get("strategies", []):
            if not entry.get("enabled", True):
                logger.info(f"Skipping disabled strategy: {entry['name']}")
                continue

            try:
                strategy = self._instantiate_strategy(entry)
                self._strategies[entry["name"]] = strategy
                self._account_ids[entry["name"]] = entry["account_id"]
                await strategy.on_start()
                logger.info(f"Loaded strategy: {entry['name']}")
            except Exception as e:
                logger.error(f"Failed to load strategy {entry['name']}: {e}")
                raise

    def _instantiate_strategy(self, entry: dict) -> "Strategy":
        """Import class and instantiate with params."""
        class_path = entry["class"]
        module_path, class_name = class_path.rsplit(".", 1)

        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)

        params = entry.get("params", {})
        return cls(
            name=entry["name"],
            symbols=entry["symbols"],
            **params,
        )

    def get_strategy(self, name: str) -> "Strategy | None":
        """Get strategy by name."""
        return self._strategies.get(name)

    def get_account_id(self, strategy_name: str) -> str | None:
        """Get account ID for a strategy."""
        return self._account_ids.get(strategy_name)

    def all_strategies(self) -> list["Strategy"]:
        """Get all loaded strategies."""
        return list(self._strategies.values())

    async def shutdown(self) -> None:
        """Stop all strategies gracefully."""
        for name, strategy in self._strategies.items():
            try:
                await strategy.on_stop()
                logger.info(f"Stopped strategy: {name}")
            except Exception as e:
                logger.error(f"Error stopping strategy {name}: {e}")
```

**Step 5: Create example config file**

```yaml
# backend/config/strategies.yaml
strategies:
  - name: momentum_v1
    class: src.strategies.examples.momentum.MomentumStrategy
    account_id: "ACC001"
    symbols: ["AAPL", "TSLA", "NVDA"]
    params:
      lookback_period: 20
      threshold: 0.02
      position_size: 100
    enabled: false  # Disabled until strategy is implemented
```

**Step 6: Update __init__.py**

```python
# backend/src/strategies/__init__.py
from src.strategies.signals import Signal
from src.strategies.base import MarketData, OrderFill, Strategy
from src.strategies.context import StrategyContext
from src.strategies.registry import StrategyRegistry

__all__ = [
    "Signal",
    "MarketData",
    "OrderFill",
    "Strategy",
    "StrategyContext",
    "StrategyRegistry",
]
```

**Step 7: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS

**Step 8: Commit**

```bash
git add backend/src/strategies/ backend/tests/test_registry.py backend/config/ backend/pyproject.toml
git commit -m "feat: add StrategyRegistry for config-based strategy loading"
```

---

## Task 6: Create StrategyEngine

**Files:**
- Create: `backend/src/strategies/engine.py`
- Modify: `backend/src/strategies/__init__.py`
- Create: `backend/tests/test_engine.py`

**Step 1: Write the failing test**

```python
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_engine.py -v`
Expected: FAIL with "No module named 'src.strategies.engine'"

**Step 3: Create engine.py**

```python
# backend/src/strategies/engine.py
import logging
from typing import TYPE_CHECKING, Protocol

from src.strategies.context import StrategyContext
from src.strategies.base import MarketData, OrderFill

if TYPE_CHECKING:
    from src.strategies.registry import StrategyRegistry
    from src.strategies.signals import Signal
    from src.core.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class RiskManagerProtocol(Protocol):
    """Protocol for Risk Manager dependency."""
    async def evaluate(self, signal: "Signal") -> bool: ...


class StrategyEngine:
    """
    Orchestrates strategy execution.

    - Receives market data from Market Data component
    - Dispatches to subscribed strategies
    - Collects signals and forwards to Risk Manager
    - Notifies strategies of fills
    """

    def __init__(
        self,
        registry: "StrategyRegistry",
        portfolio: "PortfolioManager",
        risk_manager: RiskManagerProtocol,
    ):
        self._registry = registry
        self._portfolio = portfolio
        self._risk_manager = risk_manager
        self._quote_cache: dict[str, MarketData] = {}
        self._running = False

    async def on_market_data(self, data: MarketData) -> None:
        """
        Called by Market Data component when new quote arrives.

        Dispatches to all strategies subscribed to this symbol.
        """
        if not self._running:
            return

        # Update cache
        self._quote_cache[data.symbol] = data

        # Dispatch to subscribed strategies
        for strategy in self._registry.all_strategies():
            if data.symbol not in strategy.symbols:
                continue

            account_id = self._registry.get_account_id(strategy.name)

            # Build context for this strategy
            context = StrategyContext(
                strategy_id=strategy.name,
                account_id=account_id,
                portfolio=self._portfolio,
                quote_cache=self._quote_cache,
            )

            # Get signals with error handling
            try:
                signals = await strategy.on_market_data(data, context)
            except Exception as e:
                logger.error(
                    f"Strategy {strategy.name} error on {data.symbol}: {e}",
                    exc_info=True,
                )
                continue

            # Process signals sequentially through Risk Manager
            for signal in signals:
                try:
                    await self._risk_manager.evaluate(signal)
                except Exception as e:
                    logger.error(
                        f"Risk Manager error for signal from {strategy.name}: {e}",
                        exc_info=True,
                    )

    async def on_fill(self, fill: OrderFill) -> None:
        """
        Called by Order Manager when fill occurs.

        Notifies the strategy that generated the order.
        """
        strategy = self._registry.get_strategy(fill.strategy_id)
        if strategy:
            try:
                await strategy.on_fill(fill)
            except Exception as e:
                logger.error(
                    f"Strategy {fill.strategy_id} on_fill error: {e}",
                    exc_info=True,
                )

    def get_quote(self, symbol: str) -> MarketData | None:
        """Get cached quote for a symbol."""
        return self._quote_cache.get(symbol)

    async def start(self) -> None:
        """Load strategies and start engine."""
        await self._registry.load_strategies()
        self._running = True
        logger.info("Strategy engine started")

    async def stop(self) -> None:
        """Stop engine and shutdown strategies."""
        self._running = False
        await self._registry.shutdown()
        logger.info("Strategy engine stopped")
```

**Step 4: Update __init__.py**

```python
# backend/src/strategies/__init__.py
from src.strategies.signals import Signal
from src.strategies.base import MarketData, OrderFill, Strategy
from src.strategies.context import StrategyContext
from src.strategies.registry import StrategyRegistry
from src.strategies.engine import StrategyEngine

__all__ = [
    "Signal",
    "MarketData",
    "OrderFill",
    "Strategy",
    "StrategyContext",
    "StrategyRegistry",
    "StrategyEngine",
]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_engine.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/strategies/ backend/tests/test_engine.py
git commit -m "feat: add StrategyEngine orchestrator"
```

---

## Task 7: Create Example Momentum Strategy

**Files:**
- Create: `backend/src/strategies/examples/__init__.py`
- Create: `backend/src/strategies/examples/momentum.py`
- Create: `backend/tests/test_momentum_strategy.py`

**Step 1: Write the failing test**

```python
# backend/tests/test_momentum_strategy.py
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.strategies.examples.momentum import MomentumStrategy
from src.strategies.base import MarketData
from src.strategies.context import StrategyContext


def make_data(symbol: str, price: float) -> MarketData:
    return MarketData(
        symbol=symbol,
        price=Decimal(str(price)),
        bid=Decimal(str(price - 0.05)),
        ask=Decimal(str(price + 0.05)),
        volume=100000,
        timestamp=datetime.utcnow(),
    )


class TestMomentumStrategy:
    @pytest.fixture
    def strategy(self):
        return MomentumStrategy(
            name="test_momentum",
            symbols=["AAPL"],
            lookback_period=5,
            threshold=0.05,
            position_size=100,
        )

    @pytest.fixture
    def mock_context(self):
        context = MagicMock(spec=StrategyContext)
        context.get_position = AsyncMock(return_value=None)
        return context

    async def test_no_signal_during_warmup(self, strategy, mock_context):
        """No signals until lookback period is filled."""
        # First 4 data points (need 5 for lookback)
        for price in [100, 101, 102, 103]:
            signals = await strategy.on_market_data(
                make_data("AAPL", price), mock_context
            )
            assert signals == []

    async def test_buy_signal_on_momentum_up(self, strategy, mock_context):
        """Buy signal when momentum exceeds threshold."""
        # Fill lookback period with price 100
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price jumps 10% (above 5% threshold)
        signals = await strategy.on_market_data(make_data("AAPL", 110), mock_context)

        assert len(signals) == 1
        assert signals[0].action == "buy"
        assert signals[0].quantity == 100
        assert "10.00%" in signals[0].reason

    async def test_no_signal_when_below_threshold(self, strategy, mock_context):
        """No signal when momentum is below threshold."""
        # Fill lookback period
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price rises only 2% (below 5% threshold)
        signals = await strategy.on_market_data(make_data("AAPL", 102), mock_context)

        assert signals == []

    async def test_sell_signal_on_momentum_down(self, strategy, mock_context):
        """Sell signal when holding and momentum reverses."""
        # Setup: have a position
        mock_position = MagicMock()
        mock_position.quantity = 100
        mock_context.get_position = AsyncMock(return_value=mock_position)

        # Fill lookback period
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price drops 10%
        signals = await strategy.on_market_data(make_data("AAPL", 90), mock_context)

        assert len(signals) == 1
        assert signals[0].action == "sell"
        assert signals[0].quantity == 100

    async def test_no_buy_when_already_holding(self, strategy, mock_context):
        """No buy signal when already holding a position."""
        # Setup: have a position
        mock_position = MagicMock()
        mock_position.quantity = 100
        mock_context.get_position = AsyncMock(return_value=mock_position)

        # Fill lookback period
        for _ in range(5):
            await strategy.on_market_data(make_data("AAPL", 100), mock_context)

        # Price rises 10% but we already hold
        signals = await strategy.on_market_data(make_data("AAPL", 110), mock_context)

        assert signals == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_momentum_strategy.py -v`
Expected: FAIL with "No module named 'src.strategies.examples'"

**Step 3: Create momentum strategy**

```python
# backend/src/strategies/examples/__init__.py
from src.strategies.examples.momentum import MomentumStrategy

__all__ = ["MomentumStrategy"]
```

```python
# backend/src/strategies/examples/momentum.py
import logging
from collections import defaultdict
from decimal import Decimal

from src.strategies.base import Strategy, MarketData, OrderFill
from src.strategies.context import StrategyContext
from src.strategies.signals import Signal

logger = logging.getLogger(__name__)


class MomentumStrategy(Strategy):
    """
    Simple momentum strategy.

    - Buy when price rises above threshold% from lookback period
    - Sell when price drops below threshold% while holding

    This is an example strategy for testing. Not for live trading.
    """

    def __init__(
        self,
        name: str,
        symbols: list[str],
        lookback_period: int = 20,
        threshold: float = 0.02,
        position_size: int = 100,
    ):
        self.name = name
        self.symbols = symbols
        self.lookback_period = lookback_period
        self.threshold = Decimal(str(threshold))
        self.position_size = position_size
        self._price_history: dict[str, list[Decimal]] = defaultdict(list)

    async def on_market_data(
        self, data: MarketData, context: StrategyContext
    ) -> list[Signal]:
        signals = []

        # Update price history
        history = self._price_history[data.symbol]
        history.append(data.price)
        if len(history) > self.lookback_period:
            history.pop(0)

        # Need full lookback period
        if len(history) < self.lookback_period:
            return []

        # Calculate momentum
        old_price = history[0]
        momentum = (data.price - old_price) / old_price

        # Check current position
        position = await context.get_position(data.symbol)
        has_position = position is not None and position.quantity > 0

        if not has_position and momentum > self.threshold:
            # No position, momentum up -> buy
            signals.append(Signal(
                strategy_id=self.name,
                symbol=data.symbol,
                action="buy",
                quantity=self.position_size,
                reason=f"Momentum {momentum:.2%} > {self.threshold:.2%}",
            ))
        elif has_position and momentum < -self.threshold:
            # Have position, momentum down -> sell
            signals.append(Signal(
                strategy_id=self.name,
                symbol=data.symbol,
                action="sell",
                quantity=position.quantity,
                reason=f"Momentum {momentum:.2%} < -{self.threshold:.2%}",
            ))

        return signals

    async def on_fill(self, fill: OrderFill) -> None:
        logger.info(
            f"[{self.name}] Fill: {fill.action} {fill.quantity} "
            f"{fill.symbol} @ {fill.price}"
        )

    async def on_start(self) -> None:
        logger.info(f"[{self.name}] Starting with symbols: {self.symbols}")
        self._price_history.clear()

    async def on_stop(self) -> None:
        logger.info(f"[{self.name}] Stopping")
```

**Step 4: Run test to verify it passes**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest tests/test_momentum_strategy.py -v`
Expected: PASS

**Step 5: Update config to enable momentum strategy**

```yaml
# backend/config/strategies.yaml
strategies:
  - name: momentum_v1
    class: src.strategies.examples.momentum.MomentumStrategy
    account_id: "ACC001"
    symbols: ["AAPL", "TSLA", "NVDA"]
    params:
      lookback_period: 20
      threshold: 0.02
      position_size: 100
    enabled: true
```

**Step 6: Commit**

```bash
git add backend/src/strategies/examples/ backend/tests/test_momentum_strategy.py backend/config/strategies.yaml
git commit -m "feat: add MomentumStrategy example with tests"
```

---

## Task 8: Run Full Test Suite and Final Commit

**Step 1: Run all tests**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -m pytest -v`
Expected: All tests PASS

**Step 2: Verify import from package**

Run: `cd backend && /home/tochat/anaconda3/envs/aq_trading/bin/python -c "from src.strategies import Signal, Strategy, StrategyEngine, MomentumStrategy; print('All imports successful')"`
Expected: "All imports successful"

**Step 3: Final commit if any uncommitted changes**

```bash
git status
# If any changes, commit them
```

---

## Summary

After completing all tasks, you will have:

| File | Purpose |
|------|---------|
| `src/strategies/__init__.py` | Package exports |
| `src/strategies/signals.py` | Signal dataclass |
| `src/strategies/base.py` | MarketData, OrderFill, Strategy ABC |
| `src/strategies/context.py` | StrategyContext |
| `src/strategies/registry.py` | StrategyRegistry |
| `src/strategies/engine.py` | StrategyEngine |
| `src/strategies/examples/momentum.py` | Example strategy |
| `config/strategies.yaml` | Strategy configuration |
| `tests/test_*.py` | Unit tests for all components |

**Test count:** ~25 new tests
