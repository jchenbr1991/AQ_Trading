# Market Data Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Market Data Service that generates mock quotes, caches to Redis, and distributes via asyncio.Queue.

**Architecture:** MockDataSource generates random-walk quotes with configurable scenarios → QuoteProcessor injects faults and writes to Redis → MarketDataService orchestrates and distributes via queue → StrategyEngine consumes.

**Tech Stack:** Python 3.10+, asyncio, Redis, dataclasses, pytest

**Design Document:** `docs/plans/2026-01-23-market-data-design.md`

---

## Task 1: Models - QuoteSnapshot

**Files:**
- Create: `backend/src/market_data/__init__.py`
- Create: `backend/src/market_data/models.py`
- Create: `backend/tests/market_data/__init__.py`
- Create: `backend/tests/market_data/test_models.py`

**Step 1.1: Create package structure**

```bash
mkdir -p backend/src/market_data/sources
mkdir -p backend/tests/market_data
touch backend/src/market_data/__init__.py
touch backend/src/market_data/sources/__init__.py
touch backend/tests/market_data/__init__.py
```

**Step 1.2: Write failing test for QuoteSnapshot**

Create `backend/tests/market_data/test_models.py`:

```python
# backend/tests/market_data/test_models.py
"""Tests for market data models."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest


class TestQuoteSnapshot:
    def test_create_quote_snapshot(self):
        """QuoteSnapshot holds quote data with system metadata."""
        from src.market_data.models import QuoteSnapshot

        now = datetime.utcnow()
        snapshot = QuoteSnapshot(
            symbol="AAPL",
            price=Decimal("150.25"),
            bid=Decimal("150.20"),
            ask=Decimal("150.30"),
            volume=1000000,
            timestamp=now,
            cached_at=now,
        )

        assert snapshot.symbol == "AAPL"
        assert snapshot.price == Decimal("150.25")
        assert snapshot.bid == Decimal("150.20")
        assert snapshot.ask == Decimal("150.30")
        assert snapshot.volume == 1000000
        assert snapshot.timestamp == now
        assert snapshot.cached_at == now

    def test_is_stale_returns_false_for_fresh_quote(self):
        """Fresh quote is not stale."""
        from src.market_data.models import QuoteSnapshot

        now = datetime.utcnow()
        snapshot = QuoteSnapshot(
            symbol="AAPL",
            price=Decimal("150.00"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            volume=100,
            timestamp=now,
            cached_at=now,
        )

        assert snapshot.is_stale(threshold_ms=5000) is False

    def test_is_stale_returns_true_for_old_quote(self):
        """Old quote is stale based on event-time (timestamp), not cached_at."""
        from src.market_data.models import QuoteSnapshot

        old_time = datetime.utcnow() - timedelta(seconds=10)
        now = datetime.utcnow()
        snapshot = QuoteSnapshot(
            symbol="AAPL",
            price=Decimal("150.00"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            volume=100,
            timestamp=old_time,  # Event-time is old
            cached_at=now,  # Cached recently, but doesn't matter
        )

        assert snapshot.is_stale(threshold_ms=5000) is True

    def test_from_market_data(self):
        """Create QuoteSnapshot from MarketData."""
        from src.market_data.models import QuoteSnapshot
        from src.strategies.base import MarketData

        now = datetime.utcnow()
        market_data = MarketData(
            symbol="TSLA",
            price=Decimal("250.00"),
            bid=Decimal("249.90"),
            ask=Decimal("250.10"),
            volume=50000,
            timestamp=now,
        )

        snapshot = QuoteSnapshot.from_market_data(market_data)

        assert snapshot.symbol == "TSLA"
        assert snapshot.price == Decimal("250.00")
        assert snapshot.timestamp == now
        assert snapshot.cached_at is not None
```

**Step 1.3: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_models.py::TestQuoteSnapshot -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'src.market_data.models'`

**Step 1.4: Write QuoteSnapshot implementation**

Create `backend/src/market_data/models.py`:

```python
# backend/src/market_data/models.py
"""Market data models."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.strategies.base import MarketData


@dataclass
class QuoteSnapshot:
    """
    Cached quote state with system metadata.

    Distinction from MarketData:
    - MarketData: Event flowing through queue
    - QuoteSnapshot: Cached state with staleness tracking
    """

    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime  # Event-time (from source)
    cached_at: datetime  # System-time (when cached, for debugging)

    def is_stale(self, threshold_ms: int) -> bool:
        """
        Check staleness using event-time, NOT cached_at.

        This ensures correct behavior with delayed/out-of-order data.
        """
        age_ms = (datetime.utcnow() - self.timestamp).total_seconds() * 1000
        return age_ms > threshold_ms

    @classmethod
    def from_market_data(cls, data: "MarketData") -> "QuoteSnapshot":
        """Create QuoteSnapshot from MarketData event."""
        return cls(
            symbol=data.symbol,
            price=data.price,
            bid=data.bid,
            ask=data.ask,
            volume=data.volume,
            timestamp=data.timestamp,
            cached_at=datetime.utcnow(),
        )
```

**Step 1.5: Run test to verify it passes**

```bash
cd backend && pytest tests/market_data/test_models.py::TestQuoteSnapshot -v
```

Expected: PASS (4 tests)

**Step 1.6: Commit**

```bash
git add backend/src/market_data backend/tests/market_data
git commit -m "feat(market_data): add QuoteSnapshot model with staleness detection"
```

---

## Task 2: Models - SymbolScenario and FaultConfig

**Files:**
- Modify: `backend/src/market_data/models.py`
- Modify: `backend/tests/market_data/test_models.py`

**Step 2.1: Write failing tests for SymbolScenario and FaultConfig**

Add to `backend/tests/market_data/test_models.py`:

```python
class TestSymbolScenario:
    def test_create_symbol_scenario(self):
        """SymbolScenario configures per-symbol behavior."""
        from src.market_data.models import SymbolScenario

        scenario = SymbolScenario(
            symbol="AAPL",
            scenario="volatile",
            base_price=Decimal("150.00"),
            tick_interval_ms=50,
        )

        assert scenario.symbol == "AAPL"
        assert scenario.scenario == "volatile"
        assert scenario.base_price == Decimal("150.00")
        assert scenario.tick_interval_ms == 50

    def test_default_tick_interval(self):
        """SymbolScenario has default tick interval."""
        from src.market_data.models import SymbolScenario

        scenario = SymbolScenario(
            symbol="SPY",
            scenario="flat",
            base_price=Decimal("450.00"),
        )

        assert scenario.tick_interval_ms == 100


class TestFaultConfig:
    def test_default_values(self):
        """FaultConfig has sensible defaults (disabled)."""
        from src.market_data.models import FaultConfig

        config = FaultConfig()

        assert config.enabled is False
        assert config.delay_probability == 0.0
        assert config.delay_ms_range == (100, 500)
        assert config.duplicate_probability == 0.0
        assert config.out_of_order_probability == 0.0
        assert config.out_of_order_offset_ms == 200
        assert config.stale_window_probability == 0.0
        assert config.stale_window_duration_ms == (2000, 5000)

    def test_custom_fault_config(self):
        """FaultConfig accepts custom values."""
        from src.market_data.models import FaultConfig

        config = FaultConfig(
            enabled=True,
            delay_probability=0.1,
            duplicate_probability=0.05,
        )

        assert config.enabled is True
        assert config.delay_probability == 0.1
        assert config.duplicate_probability == 0.05
```

**Step 2.2: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_models.py::TestSymbolScenario -v
cd backend && pytest tests/market_data/test_models.py::TestFaultConfig -v
```

Expected: FAIL with `ImportError`

**Step 2.3: Add SymbolScenario and FaultConfig to models.py**

Add to `backend/src/market_data/models.py`:

```python
ScenarioType = Literal["flat", "trend_up", "trend_down", "volatile", "jump", "stale"]


@dataclass
class SymbolScenario:
    """Configuration for per-symbol mock data generation."""

    symbol: str
    scenario: ScenarioType
    base_price: Decimal
    tick_interval_ms: int = 100


@dataclass
class FaultConfig:
    """Configuration for fault injection."""

    enabled: bool = False
    delay_probability: float = 0.0
    delay_ms_range: tuple[int, int] = (100, 500)
    duplicate_probability: float = 0.0
    out_of_order_probability: float = 0.0
    out_of_order_offset_ms: int = 200
    stale_window_probability: float = 0.0
    stale_window_duration_ms: tuple[int, int] = (2000, 5000)
```

**Step 2.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_models.py -v
```

Expected: PASS (all tests)

**Step 2.5: Commit**

```bash
git add backend/src/market_data/models.py backend/tests/market_data/test_models.py
git commit -m "feat(market_data): add SymbolScenario and FaultConfig models"
```

---

## Task 3: Models - MarketDataConfig with YAML loading

**Files:**
- Modify: `backend/src/market_data/models.py`
- Modify: `backend/tests/market_data/test_models.py`

**Step 3.1: Write failing test for MarketDataConfig**

Add to `backend/tests/market_data/test_models.py`:

```python
import tempfile


class TestMarketDataConfig:
    def test_default_values(self):
        """MarketDataConfig has sensible defaults."""
        from src.market_data.models import MarketDataConfig

        config = MarketDataConfig()

        assert config.queue_max_size == 1000
        assert config.default_tick_interval_ms == 100
        assert config.staleness_threshold_ms == 5000
        assert config.symbols == {}
        assert config.faults.enabled is False

    def test_from_yaml(self):
        """Load MarketDataConfig from YAML file."""
        from src.market_data.models import MarketDataConfig

        yaml_content = """
market_data:
  queue_max_size: 500
  default_tick_interval_ms: 50
  staleness_threshold_ms: 3000
  symbols:
    AAPL:
      scenario: "volatile"
      base_price: "150.00"
      tick_interval_ms: 25
    SPY:
      scenario: "flat"
      base_price: "450.00"
  faults:
    enabled: true
    delay_probability: 0.1
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = MarketDataConfig.from_yaml(f.name)

        assert config.queue_max_size == 500
        assert config.default_tick_interval_ms == 50
        assert config.staleness_threshold_ms == 3000
        assert len(config.symbols) == 2
        assert config.symbols["AAPL"].scenario == "volatile"
        assert config.symbols["AAPL"].base_price == Decimal("150.00")
        assert config.symbols["SPY"].scenario == "flat"
        assert config.faults.enabled is True
        assert config.faults.delay_probability == 0.1

    def test_from_yaml_missing_file(self):
        """Raise error for missing YAML file."""
        from src.market_data.models import MarketDataConfig

        with pytest.raises(FileNotFoundError):
            MarketDataConfig.from_yaml("/nonexistent/path.yaml")
```

**Step 3.2: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_models.py::TestMarketDataConfig -v
```

Expected: FAIL with `ImportError`

**Step 3.3: Add MarketDataConfig to models.py**

Add to `backend/src/market_data/models.py`:

```python
from dataclasses import field
from pathlib import Path

import yaml


@dataclass
class MarketDataConfig:
    """Configuration for MarketDataService."""

    queue_max_size: int = 1000
    default_tick_interval_ms: int = 100
    staleness_threshold_ms: int = 5000
    symbols: dict[str, SymbolScenario] = field(default_factory=dict)
    faults: FaultConfig = field(default_factory=FaultConfig)

    @classmethod
    def from_yaml(cls, path: str) -> "MarketDataConfig":
        """Load configuration from YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = yaml.safe_load(f)

        md_data = data.get("market_data", {})
        symbols_data = md_data.get("symbols", {})
        faults_data = md_data.get("faults", {})

        symbols = {}
        for symbol, cfg in symbols_data.items():
            symbols[symbol] = SymbolScenario(
                symbol=symbol,
                scenario=cfg["scenario"],
                base_price=Decimal(str(cfg["base_price"])),
                tick_interval_ms=cfg.get("tick_interval_ms", 100),
            )

        faults = FaultConfig(
            enabled=faults_data.get("enabled", False),
            delay_probability=faults_data.get("delay_probability", 0.0),
            delay_ms_range=tuple(faults_data.get("delay_ms_range", [100, 500])),
            duplicate_probability=faults_data.get("duplicate_probability", 0.0),
            out_of_order_probability=faults_data.get("out_of_order_probability", 0.0),
            out_of_order_offset_ms=faults_data.get("out_of_order_offset_ms", 200),
            stale_window_probability=faults_data.get("stale_window_probability", 0.0),
            stale_window_duration_ms=tuple(
                faults_data.get("stale_window_duration_ms", [2000, 5000])
            ),
        )

        return cls(
            queue_max_size=md_data.get("queue_max_size", 1000),
            default_tick_interval_ms=md_data.get("default_tick_interval_ms", 100),
            staleness_threshold_ms=md_data.get("staleness_threshold_ms", 5000),
            symbols=symbols,
            faults=faults,
        )
```

**Step 3.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_models.py -v
```

Expected: PASS (all tests)

**Step 3.5: Commit**

```bash
git add backend/src/market_data/models.py backend/tests/market_data/test_models.py
git commit -m "feat(market_data): add MarketDataConfig with YAML loading"
```

---

## Task 4: DataSource Protocol

**Files:**
- Create: `backend/src/market_data/sources/base.py`
- Create: `backend/tests/market_data/test_sources.py`

**Step 4.1: Write failing test for DataSource protocol**

Create `backend/tests/market_data/test_sources.py`:

```python
# backend/tests/market_data/test_sources.py
"""Tests for data source protocol and implementations."""

from datetime import datetime
from decimal import Decimal
from typing import AsyncIterator

import pytest
from src.strategies.base import MarketData


class TestDataSourceProtocol:
    def test_protocol_is_runtime_checkable(self):
        """DataSource protocol can be checked at runtime."""
        from src.market_data.sources.base import DataSource

        class FakeSource:
            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

            async def subscribe(self, symbols: list[str]) -> None:
                pass

            def quotes(self) -> AsyncIterator[MarketData]:
                pass

        assert isinstance(FakeSource(), DataSource)

    def test_incomplete_implementation_not_instance(self):
        """Incomplete implementation is not a DataSource."""
        from src.market_data.sources.base import DataSource

        class IncompleteSource:
            async def start(self) -> None:
                pass
            # Missing other methods

        assert not isinstance(IncompleteSource(), DataSource)
```

**Step 4.2: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_sources.py::TestDataSourceProtocol -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 4.3: Write DataSource protocol**

Create `backend/src/market_data/sources/base.py`:

```python
# backend/src/market_data/sources/base.py
"""Abstract data source interface."""

from typing import AsyncIterator, Protocol, runtime_checkable

from src.strategies.base import MarketData


@runtime_checkable
class DataSource(Protocol):
    """
    Abstract interface for market data sources.

    Implementations:
    - MockDataSource: Random walk with scenarios (Phase 1)
    - FutuDataSource: Real Futu OpenD connection (Phase 2)
    - HistoricalReplaySource: Historical data replay (Phase 2)
    """

    async def start(self) -> None:
        """Start the data source."""
        ...

    async def stop(self) -> None:
        """Stop the data source and cleanup."""
        ...

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols. Idempotent."""
        ...

    def quotes(self) -> AsyncIterator[MarketData]:
        """Async iterator yielding MarketData events."""
        ...
```

Update `backend/src/market_data/sources/__init__.py`:

```python
# backend/src/market_data/sources/__init__.py
"""Data source implementations."""

from src.market_data.sources.base import DataSource

__all__ = ["DataSource"]
```

**Step 4.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_sources.py -v
```

Expected: PASS

**Step 4.5: Commit**

```bash
git add backend/src/market_data/sources backend/tests/market_data/test_sources.py
git commit -m "feat(market_data): add DataSource protocol"
```

---

## Task 5: MockDataSource - Basic Quote Generation

**Files:**
- Create: `backend/src/market_data/sources/mock.py`
- Modify: `backend/tests/market_data/test_sources.py`

**Step 5.1: Write failing test for MockDataSource basic functionality**

Add to `backend/tests/market_data/test_sources.py`:

```python
class TestMockDataSource:
    @pytest.mark.asyncio
    async def test_implements_datasource_protocol(self):
        """MockDataSource implements DataSource protocol."""
        from src.market_data.sources.base import DataSource
        from src.market_data.sources.mock import MockDataSource
        from src.market_data.models import MarketDataConfig, SymbolScenario

        config = MarketDataConfig(
            symbols={
                "AAPL": SymbolScenario(
                    symbol="AAPL",
                    scenario="flat",
                    base_price=Decimal("150.00"),
                )
            }
        )
        source = MockDataSource(config)

        assert isinstance(source, DataSource)

    @pytest.mark.asyncio
    async def test_generates_quotes_for_subscribed_symbols(self):
        """MockDataSource generates quotes for subscribed symbols."""
        from src.market_data.sources.mock import MockDataSource
        from src.market_data.models import MarketDataConfig, SymbolScenario

        config = MarketDataConfig(
            symbols={
                "AAPL": SymbolScenario(
                    symbol="AAPL",
                    scenario="flat",
                    base_price=Decimal("150.00"),
                    tick_interval_ms=10,  # Fast for testing
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["AAPL"])
        await source.start()

        quotes = []
        async for quote in source.quotes():
            quotes.append(quote)
            if len(quotes) >= 3:
                break

        await source.stop()

        assert len(quotes) == 3
        assert all(q.symbol == "AAPL" for q in quotes)
        assert all(q.price > 0 for q in quotes)

    @pytest.mark.asyncio
    async def test_quote_has_bid_ask_spread(self):
        """Generated quotes have bid < price < ask."""
        from src.market_data.sources.mock import MockDataSource
        from src.market_data.models import MarketDataConfig, SymbolScenario

        config = MarketDataConfig(
            symbols={
                "TEST": SymbolScenario(
                    symbol="TEST",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=10,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["TEST"])
        await source.start()

        async for quote in source.quotes():
            assert quote.bid < quote.price < quote.ask
            break

        await source.stop()
```

**Step 5.2: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_sources.py::TestMockDataSource -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 5.3: Write MockDataSource basic implementation**

Create `backend/src/market_data/sources/mock.py`:

```python
# backend/src/market_data/sources/mock.py
"""Mock data source with configurable scenarios."""

import asyncio
from datetime import datetime
from decimal import Decimal
from random import uniform
from typing import AsyncIterator

from src.market_data.models import MarketDataConfig, SymbolScenario
from src.strategies.base import MarketData


# Scenario parameters: (drift, volatility)
SCENARIO_PARAMS: dict[str, tuple[float, float]] = {
    "flat": (0.0, 0.0001),
    "trend_up": (0.0005, 0.001),
    "trend_down": (-0.0005, 0.001),
    "volatile": (0.0, 0.01),
    "jump": (0.0, 0.001),
    "stale": (0.0, 0.001),
}


class MockDataSource:
    """
    Mock data source generating random-walk quotes.

    Supports configurable scenarios per symbol for testing
    different market conditions.
    """

    def __init__(self, config: MarketDataConfig):
        self._config = config
        self._subscribed: set[str] = set()
        self._running = False
        self._prices: dict[str, Decimal] = {}
        self._spread_bps = 5  # 5 basis points spread

    async def start(self) -> None:
        """Start generating quotes."""
        self._running = True
        # Initialize prices from config
        for symbol in self._subscribed:
            if symbol in self._config.symbols:
                self._prices[symbol] = self._config.symbols[symbol].base_price
            else:
                self._prices[symbol] = Decimal("100.00")  # Default

    async def stop(self) -> None:
        """Stop generating quotes."""
        self._running = False

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols. Idempotent."""
        self._subscribed.update(symbols)

    async def quotes(self) -> AsyncIterator[MarketData]:
        """Generate quotes for subscribed symbols."""
        while self._running:
            for symbol in list(self._subscribed):
                if not self._running:
                    break

                scenario = self._get_scenario(symbol)
                quote = self._generate_quote(symbol, scenario)
                yield quote

                # Wait for tick interval
                interval_ms = scenario.tick_interval_ms if scenario else self._config.default_tick_interval_ms
                await asyncio.sleep(interval_ms / 1000)

    def _get_scenario(self, symbol: str) -> SymbolScenario | None:
        """Get scenario config for symbol."""
        return self._config.symbols.get(symbol)

    def _generate_quote(self, symbol: str, scenario: SymbolScenario | None) -> MarketData:
        """Generate a single quote using random walk."""
        current_price = self._prices.get(symbol, Decimal("100.00"))

        # Get scenario parameters
        scenario_type = scenario.scenario if scenario else "flat"
        drift, volatility = SCENARIO_PARAMS.get(scenario_type, (0.0, 0.001))

        # Random walk: new_price = old_price * (1 + drift + volatility * random(-1, 1))
        change = drift + volatility * uniform(-1, 1)
        new_price = current_price * Decimal(1 + change)
        new_price = new_price.quantize(Decimal("0.01"))

        # Update stored price
        self._prices[symbol] = new_price

        # Calculate bid/ask spread
        spread = new_price * Decimal(self._spread_bps) / Decimal(10000)
        bid = (new_price - spread / 2).quantize(Decimal("0.01"))
        ask = (new_price + spread / 2).quantize(Decimal("0.01"))

        return MarketData(
            symbol=symbol,
            price=new_price,
            bid=bid,
            ask=ask,
            volume=int(uniform(1000, 100000)),
            timestamp=datetime.utcnow(),
        )
```

Update `backend/src/market_data/sources/__init__.py`:

```python
# backend/src/market_data/sources/__init__.py
"""Data source implementations."""

from src.market_data.sources.base import DataSource
from src.market_data.sources.mock import MockDataSource

__all__ = ["DataSource", "MockDataSource"]
```

**Step 5.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_sources.py -v
```

Expected: PASS

**Step 5.5: Commit**

```bash
git add backend/src/market_data/sources backend/tests/market_data/test_sources.py
git commit -m "feat(market_data): add MockDataSource with basic quote generation"
```

---

## Task 6: MockDataSource - Scenario Behaviors

**Files:**
- Modify: `backend/src/market_data/sources/mock.py`
- Create: `backend/tests/market_data/test_mock_scenarios.py`

**Step 6.1: Write failing tests for scenario behaviors**

Create `backend/tests/market_data/test_mock_scenarios.py`:

```python
# backend/tests/market_data/test_mock_scenarios.py
"""Tests for MockDataSource scenario behaviors."""

from decimal import Decimal

import pytest
from src.market_data.models import MarketDataConfig, SymbolScenario
from src.market_data.sources.mock import MockDataSource


class TestFlatScenario:
    @pytest.mark.asyncio
    async def test_flat_minimal_movement(self):
        """Flat scenario has near-zero price movement."""
        config = MarketDataConfig(
            symbols={
                "FLAT": SymbolScenario(
                    symbol="FLAT",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["FLAT"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 50:
                break
        await source.stop()

        # Calculate variance - should be very low
        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        assert variance < 0.1  # Very low variance


class TestTrendScenarios:
    @pytest.mark.asyncio
    async def test_trend_up_positive_drift(self):
        """Trend up scenario shows upward bias."""
        config = MarketDataConfig(
            symbols={
                "UP": SymbolScenario(
                    symbol="UP",
                    scenario="trend_up",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["UP"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 100:
                break
        await source.stop()

        # End price should be higher than start (on average with drift)
        # Use first/last quartile averages to reduce noise
        first_quarter = sum(prices[:25]) / 25
        last_quarter = sum(prices[-25:]) / 25
        assert last_quarter > first_quarter

    @pytest.mark.asyncio
    async def test_trend_down_negative_drift(self):
        """Trend down scenario shows downward bias."""
        config = MarketDataConfig(
            symbols={
                "DOWN": SymbolScenario(
                    symbol="DOWN",
                    scenario="trend_down",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["DOWN"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 100:
                break
        await source.stop()

        first_quarter = sum(prices[:25]) / 25
        last_quarter = sum(prices[-25:]) / 25
        assert last_quarter < first_quarter


class TestVolatileScenario:
    @pytest.mark.asyncio
    async def test_volatile_high_variance(self):
        """Volatile scenario has high price variance."""
        config = MarketDataConfig(
            symbols={
                "VOL": SymbolScenario(
                    symbol="VOL",
                    scenario="volatile",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["VOL"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 50:
                break
        await source.stop()

        mean = sum(prices) / len(prices)
        variance = sum((p - mean) ** 2 for p in prices) / len(prices)
        # Volatile should have much higher variance than flat
        assert variance > 0.5


class TestJumpScenario:
    @pytest.mark.asyncio
    async def test_jump_occasional_large_moves(self):
        """Jump scenario has occasional large price moves."""
        config = MarketDataConfig(
            symbols={
                "JUMP": SymbolScenario(
                    symbol="JUMP",
                    scenario="jump",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        source = MockDataSource(config)
        await source.subscribe(["JUMP"])
        await source.start()

        prices = []
        async for quote in source.quotes():
            prices.append(float(quote.price))
            if len(prices) >= 200:
                break
        await source.stop()

        # Calculate tick-to-tick changes
        changes = [abs(prices[i] - prices[i-1]) / prices[i-1] for i in range(1, len(prices))]
        # Should have at least one large move (>3% is a jump)
        large_moves = [c for c in changes if c > 0.03]
        assert len(large_moves) >= 1  # At 2% probability, expect ~4 in 200 ticks
```

**Step 6.2: Run tests to verify they fail**

```bash
cd backend && pytest tests/market_data/test_mock_scenarios.py -v
```

Expected: Some tests may fail (especially jump scenario)

**Step 6.3: Update MockDataSource for jump scenario**

Modify `_generate_quote` in `backend/src/market_data/sources/mock.py`:

```python
from random import uniform, random, choice

def _generate_quote(self, symbol: str, scenario: SymbolScenario | None) -> MarketData:
    """Generate a single quote using random walk."""
    current_price = self._prices.get(symbol, Decimal("100.00"))

    # Get scenario parameters
    scenario_type = scenario.scenario if scenario else "flat"
    drift, volatility = SCENARIO_PARAMS.get(scenario_type, (0.0, 0.001))

    # Handle jump scenario specially
    if scenario_type == "jump" and random() < 0.02:
        # 2% chance of ±5% jump
        change = choice([-0.05, 0.05])
    else:
        # Random walk: new_price = old_price * (1 + drift + volatility * random(-1, 1))
        change = drift + volatility * uniform(-1, 1)

    new_price = current_price * Decimal(1 + change)
    new_price = max(new_price.quantize(Decimal("0.01")), Decimal("0.01"))  # Floor at $0.01

    # Update stored price
    self._prices[symbol] = new_price

    # Calculate bid/ask spread
    spread = new_price * Decimal(self._spread_bps) / Decimal(10000)
    bid = (new_price - spread / 2).quantize(Decimal("0.01"))
    ask = (new_price + spread / 2).quantize(Decimal("0.01"))

    return MarketData(
        symbol=symbol,
        price=new_price,
        bid=bid,
        ask=ask,
        volume=int(uniform(1000, 100000)),
        timestamp=datetime.utcnow(),
    )
```

**Step 6.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_mock_scenarios.py -v
```

Expected: PASS

**Step 6.5: Commit**

```bash
git add backend/src/market_data/sources/mock.py backend/tests/market_data/test_mock_scenarios.py
git commit -m "feat(market_data): add scenario behaviors (flat, trend, volatile, jump)"
```

---

## Task 7: MockDataSource - Stale Scenario

**Files:**
- Modify: `backend/src/market_data/sources/mock.py`
- Modify: `backend/tests/market_data/test_mock_scenarios.py`

**Step 7.1: Write failing test for stale scenario**

Add to `backend/tests/market_data/test_mock_scenarios.py`:

```python
import asyncio


class TestStaleScenario:
    @pytest.mark.asyncio
    async def test_stale_stops_emitting_periodically(self):
        """Stale scenario pauses emission periodically."""
        config = MarketDataConfig(
            symbols={
                "STALE": SymbolScenario(
                    symbol="STALE",
                    scenario="stale",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=10,
                )
            }
        )
        source = MockDataSource(config)
        # Configure short stale window for testing
        source._stale_pause_probability = 0.3  # 30% chance per tick
        source._stale_pause_duration_ms = (50, 100)

        await source.subscribe(["STALE"])
        await source.start()

        timestamps = []
        start = asyncio.get_event_loop().time()
        async for quote in source.quotes():
            timestamps.append(asyncio.get_event_loop().time() - start)
            if len(timestamps) >= 20:
                break
        await source.stop()

        # Calculate gaps between quotes
        gaps = [timestamps[i] - timestamps[i-1] for i in range(1, len(timestamps))]
        # Should have at least one gap > 40ms (stale pause)
        large_gaps = [g for g in gaps if g > 0.04]
        assert len(large_gaps) >= 1
```

**Step 7.2: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_mock_scenarios.py::TestStaleScenario -v
```

Expected: FAIL

**Step 7.3: Add stale scenario support to MockDataSource**

Update `backend/src/market_data/sources/mock.py`:

```python
class MockDataSource:
    def __init__(self, config: MarketDataConfig):
        self._config = config
        self._subscribed: set[str] = set()
        self._running = False
        self._prices: dict[str, Decimal] = {}
        self._spread_bps = 5
        # Stale scenario config
        self._stale_pause_probability = 0.1  # 10% chance per tick
        self._stale_pause_duration_ms = (5000, 10000)  # 5-10 seconds

    async def quotes(self) -> AsyncIterator[MarketData]:
        """Generate quotes for subscribed symbols."""
        while self._running:
            for symbol in list(self._subscribed):
                if not self._running:
                    break

                scenario = self._get_scenario(symbol)
                scenario_type = scenario.scenario if scenario else "flat"

                # Handle stale scenario - occasionally pause
                if scenario_type == "stale" and random() < self._stale_pause_probability:
                    pause_ms = uniform(*self._stale_pause_duration_ms)
                    await asyncio.sleep(pause_ms / 1000)
                    if not self._running:
                        break

                quote = self._generate_quote(symbol, scenario)
                yield quote

                interval_ms = scenario.tick_interval_ms if scenario else self._config.default_tick_interval_ms
                await asyncio.sleep(interval_ms / 1000)
```

**Step 7.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_mock_scenarios.py -v
```

Expected: PASS

**Step 7.5: Commit**

```bash
git add backend/src/market_data/sources/mock.py backend/tests/market_data/test_mock_scenarios.py
git commit -m "feat(market_data): add stale scenario with periodic emission pause"
```

---

## Task 8: QuoteProcessor - Redis Cache Write

**Files:**
- Create: `backend/src/market_data/processor.py`
- Create: `backend/tests/market_data/test_processor.py`

**Step 8.1: Write failing test for Redis cache write**

Create `backend/tests/market_data/test_processor.py`:

```python
# backend/tests/market_data/test_processor.py
"""Tests for QuoteProcessor."""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.market_data.models import FaultConfig, QuoteSnapshot
from src.strategies.base import MarketData


class TestQuoteProcessorRedisCache:
    @pytest.mark.asyncio
    async def test_writes_quote_to_redis(self):
        """QuoteProcessor writes quote to Redis."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        processor = QuoteProcessor(redis=mock_redis, faults=FaultConfig())

        quote = MarketData(
            symbol="AAPL",
            price=Decimal("150.25"),
            bid=Decimal("150.20"),
            ask=Decimal("150.30"),
            volume=1000,
            timestamp=datetime.utcnow(),
        )

        await processor.process(quote)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "quote:AAPL"

        # Verify JSON structure
        stored_json = call_args[0][1]
        stored = json.loads(stored_json)
        assert stored["symbol"] == "AAPL"
        assert stored["price"] == "150.25"
        assert "cached_at" in stored

    @pytest.mark.asyncio
    async def test_returns_processed_quote(self):
        """QuoteProcessor returns the processed quote."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        processor = QuoteProcessor(redis=mock_redis, faults=FaultConfig())

        quote = MarketData(
            symbol="TSLA",
            price=Decimal("250.00"),
            bid=Decimal("249.90"),
            ask=Decimal("250.10"),
            volume=500,
            timestamp=datetime.utcnow(),
        )

        result = await processor.process(quote)

        assert result is not None
        assert result.symbol == "TSLA"
        assert result.price == Decimal("250.00")
```

**Step 8.2: Run test to verify it fails**

```bash
cd backend && pytest tests/market_data/test_processor.py::TestQuoteProcessorRedisCache -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 8.3: Write QuoteProcessor with Redis cache**

Create `backend/src/market_data/processor.py`:

```python
# backend/src/market_data/processor.py
"""Quote processor with fault injection and Redis caching."""

import json
import logging
from datetime import datetime
from typing import Protocol

from src.market_data.models import FaultConfig, QuoteSnapshot
from src.strategies.base import MarketData

logger = logging.getLogger(__name__)


class RedisClient(Protocol):
    """Protocol for Redis client."""

    async def set(self, key: str, value: str) -> None:
        ...

    async def get(self, key: str) -> str | None:
        ...


class QuoteProcessor:
    """
    Processes quotes: caches to Redis and applies fault injection.
    """

    def __init__(self, redis: RedisClient, faults: FaultConfig):
        self._redis = redis
        self._faults = faults

    async def process(self, quote: MarketData) -> MarketData | None:
        """
        Process a quote: cache to Redis and return.

        Returns None if quote should be dropped (fault injection).
        """
        # Create snapshot with cached_at timestamp
        snapshot = QuoteSnapshot.from_market_data(quote)

        # Write to Redis
        await self._write_to_redis(snapshot)

        return quote

    async def _write_to_redis(self, snapshot: QuoteSnapshot) -> None:
        """Write quote snapshot to Redis."""
        key = f"quote:{snapshot.symbol}"
        value = json.dumps({
            "symbol": snapshot.symbol,
            "price": str(snapshot.price),
            "bid": str(snapshot.bid),
            "ask": str(snapshot.ask),
            "volume": snapshot.volume,
            "timestamp": snapshot.timestamp.isoformat(),
            "cached_at": snapshot.cached_at.isoformat(),
        })
        await self._redis.set(key, value)
```

**Step 8.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_processor.py -v
```

Expected: PASS

**Step 8.5: Commit**

```bash
git add backend/src/market_data/processor.py backend/tests/market_data/test_processor.py
git commit -m "feat(market_data): add QuoteProcessor with Redis cache write"
```

---

## Task 9: QuoteProcessor - Fault Injection

**Files:**
- Modify: `backend/src/market_data/processor.py`
- Modify: `backend/tests/market_data/test_processor.py`

**Step 9.1: Write failing tests for fault injection**

Add to `backend/tests/market_data/test_processor.py`:

```python
import asyncio
from datetime import timedelta


class TestFaultInjectionDelay:
    @pytest.mark.asyncio
    async def test_delay_adds_latency(self):
        """Delay fault adds latency before processing."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=True,
            delay_probability=1.0,  # Always delay
            delay_ms_range=(50, 50),  # Fixed 50ms delay
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        quote = MarketData(
            symbol="TEST",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=datetime.utcnow(),
        )

        start = asyncio.get_event_loop().time()
        await processor.process(quote)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed >= 0.045  # Allow some tolerance

    @pytest.mark.asyncio
    async def test_faults_disabled_no_delay(self):
        """No delay when faults disabled."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=False,
            delay_probability=1.0,
            delay_ms_range=(100, 100),
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        quote = MarketData(
            symbol="TEST",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=datetime.utcnow(),
        )

        start = asyncio.get_event_loop().time()
        await processor.process(quote)
        elapsed = asyncio.get_event_loop().time() - start

        assert elapsed < 0.05  # Should be fast


class TestFaultInjectionDuplicate:
    @pytest.mark.asyncio
    async def test_duplicate_emits_twice(self):
        """Duplicate fault causes quote to be processed twice."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=True,
            duplicate_probability=1.0,  # Always duplicate
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        quote = MarketData(
            symbol="DUP",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=datetime.utcnow(),
        )

        results = await processor.process(quote)

        # Should return list with 2 quotes for duplicate
        assert isinstance(results, list)
        assert len(results) == 2


class TestFaultInjectionOutOfOrder:
    @pytest.mark.asyncio
    async def test_out_of_order_older_timestamp(self):
        """Out of order fault modifies timestamp to appear older."""
        from src.market_data.processor import QuoteProcessor

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        faults = FaultConfig(
            enabled=True,
            out_of_order_probability=1.0,
            out_of_order_offset_ms=500,
        )
        processor = QuoteProcessor(redis=mock_redis, faults=faults)

        original_time = datetime.utcnow()
        quote = MarketData(
            symbol="OOO",
            price=Decimal("100.00"),
            bid=Decimal("99.90"),
            ask=Decimal("100.10"),
            volume=100,
            timestamp=original_time,
        )

        result = await processor.process(quote)

        # Timestamp should be older
        assert result.timestamp < original_time
        time_diff = original_time - result.timestamp
        assert time_diff >= timedelta(milliseconds=400)  # Allow tolerance
```

**Step 9.2: Run tests to verify they fail**

```bash
cd backend && pytest tests/market_data/test_processor.py -v
```

Expected: FAIL

**Step 9.3: Add fault injection to QuoteProcessor**

Update `backend/src/market_data/processor.py`:

```python
import asyncio
from random import random, uniform
from datetime import timedelta


class QuoteProcessor:
    """
    Processes quotes: caches to Redis and applies fault injection.
    """

    def __init__(self, redis: RedisClient, faults: FaultConfig):
        self._redis = redis
        self._faults = faults

    async def process(self, quote: MarketData) -> MarketData | list[MarketData]:
        """
        Process a quote: apply faults, cache to Redis, return.

        Returns:
            - Single MarketData normally
            - List of 2 MarketData for duplicate fault
            - None if dropped (stale window - handled at source level)
        """
        if not self._faults.enabled:
            snapshot = QuoteSnapshot.from_market_data(quote)
            await self._write_to_redis(snapshot)
            return quote

        # Apply delay fault
        if random() < self._faults.delay_probability:
            delay_ms = uniform(*self._faults.delay_ms_range)
            await asyncio.sleep(delay_ms / 1000)

        # Apply out-of-order fault (modify timestamp)
        if random() < self._faults.out_of_order_probability:
            offset = timedelta(milliseconds=self._faults.out_of_order_offset_ms)
            quote = MarketData(
                symbol=quote.symbol,
                price=quote.price,
                bid=quote.bid,
                ask=quote.ask,
                volume=quote.volume,
                timestamp=quote.timestamp - offset,
            )

        # Write to Redis
        snapshot = QuoteSnapshot.from_market_data(quote)
        await self._write_to_redis(snapshot)

        # Apply duplicate fault
        if random() < self._faults.duplicate_probability:
            return [quote, quote]

        return quote

    async def _write_to_redis(self, snapshot: QuoteSnapshot) -> None:
        """Write quote snapshot to Redis."""
        key = f"quote:{snapshot.symbol}"
        value = json.dumps({
            "symbol": snapshot.symbol,
            "price": str(snapshot.price),
            "bid": str(snapshot.bid),
            "ask": str(snapshot.ask),
            "volume": snapshot.volume,
            "timestamp": snapshot.timestamp.isoformat(),
            "cached_at": snapshot.cached_at.isoformat(),
        })
        await self._redis.set(key, value)
```

**Step 9.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_processor.py -v
```

Expected: PASS

**Step 9.5: Commit**

```bash
git add backend/src/market_data/processor.py backend/tests/market_data/test_processor.py
git commit -m "feat(market_data): add fault injection (delay, duplicate, out-of-order)"
```

---

## Task 10: MarketDataService - Core Implementation

**Files:**
- Create: `backend/src/market_data/service.py`
- Create: `backend/tests/market_data/test_service.py`

**Step 10.1: Write failing tests for MarketDataService**

Create `backend/tests/market_data/test_service.py`:

```python
# backend/tests/market_data/test_service.py
"""Tests for MarketDataService."""

import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.market_data.models import MarketDataConfig, SymbolScenario, FaultConfig


class TestMarketDataServiceSubscription:
    @pytest.mark.asyncio
    async def test_ensure_subscribed_idempotent(self):
        """ensure_subscribed is idempotent."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        config = MarketDataConfig(
            symbols={
                "AAPL": SymbolScenario(
                    symbol="AAPL", scenario="flat", base_price=Decimal("150.00")
                )
            }
        )
        service = MarketDataService(redis=mock_redis, config=config)

        service.ensure_subscribed(["AAPL", "TSLA"])
        service.ensure_subscribed(["AAPL", "SPY"])  # AAPL again

        # Should have 3 unique symbols
        assert len(service._subscribed) == 3


class TestMarketDataServiceStream:
    @pytest.mark.asyncio
    async def test_get_stream_returns_queue(self):
        """get_stream returns asyncio.Queue."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        config = MarketDataConfig()
        service = MarketDataService(redis=mock_redis, config=config)

        stream = service.get_stream()

        assert isinstance(stream, asyncio.Queue)

    @pytest.mark.asyncio
    async def test_stream_receives_quotes(self):
        """Started service puts quotes on stream."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        config = MarketDataConfig(
            symbols={
                "TEST": SymbolScenario(
                    symbol="TEST",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=10,
                )
            }
        )
        service = MarketDataService(redis=mock_redis, config=config)
        service.ensure_subscribed(["TEST"])

        stream = service.get_stream()
        await service.start()

        # Collect a few quotes
        quotes = []
        for _ in range(3):
            quote = await asyncio.wait_for(stream.get(), timeout=1.0)
            quotes.append(quote)

        await service.stop()

        assert len(quotes) == 3
        assert all(q.symbol == "TEST" for q in quotes)


class TestMarketDataServiceOverflow:
    @pytest.mark.asyncio
    async def test_queue_overflow_drops_oldest(self):
        """Queue overflow drops oldest quotes."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()

        config = MarketDataConfig(
            queue_max_size=3,
            symbols={
                "FAST": SymbolScenario(
                    symbol="FAST",
                    scenario="flat",
                    base_price=Decimal("100.00"),
                    tick_interval_ms=1,
                )
            }
        )
        service = MarketDataService(redis=mock_redis, config=config)
        service.ensure_subscribed(["FAST"])

        stream = service.get_stream()
        await service.start()

        # Let it generate many quotes without consuming
        await asyncio.sleep(0.05)

        await service.stop()

        # Queue should have at most max_size items
        assert stream.qsize() <= 3
        # Overflow counter should be > 0
        assert service._overflow_count > 0


class TestMarketDataServiceGetQuote:
    @pytest.mark.asyncio
    async def test_get_quote_returns_cached(self):
        """get_quote returns cached QuoteSnapshot."""
        from src.market_data.service import MarketDataService
        from src.market_data.models import QuoteSnapshot

        cached_json = '{"symbol": "AAPL", "price": "150.00", "bid": "149.90", "ask": "150.10", "volume": 1000, "timestamp": "2024-01-15T10:00:00", "cached_at": "2024-01-15T10:00:01"}'
        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=cached_json)

        config = MarketDataConfig()
        service = MarketDataService(redis=mock_redis, config=config)

        quote = await service.get_quote("AAPL")

        assert quote is not None
        assert isinstance(quote, QuoteSnapshot)
        assert quote.symbol == "AAPL"
        assert quote.price == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_get_quote_returns_none_if_not_cached(self):
        """get_quote returns None if not in Redis."""
        from src.market_data.service import MarketDataService

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        config = MarketDataConfig()
        service = MarketDataService(redis=mock_redis, config=config)

        quote = await service.get_quote("UNKNOWN")

        assert quote is None
```

**Step 10.2: Run tests to verify they fail**

```bash
cd backend && pytest tests/market_data/test_service.py -v
```

Expected: FAIL with `ModuleNotFoundError`

**Step 10.3: Write MarketDataService implementation**

Create `backend/src/market_data/service.py`:

```python
# backend/src/market_data/service.py
"""Market data distribution service."""

import asyncio
import json
import logging
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from src.market_data.models import MarketDataConfig, QuoteSnapshot
from src.market_data.processor import QuoteProcessor
from src.market_data.sources.mock import MockDataSource
from src.strategies.base import MarketData

logger = logging.getLogger(__name__)


class RedisClient(Protocol):
    """Protocol for Redis client."""

    async def set(self, key: str, value: str) -> None:
        ...

    async def get(self, key: str) -> str | None:
        ...


class MarketDataService:
    """
    Market data distribution service.

    Generates mock quotes, caches to Redis, distributes via queue.
    """

    def __init__(self, redis: RedisClient, config: MarketDataConfig):
        self._redis = redis
        self._config = config
        self._subscribed: set[str] = set()
        self._stream: asyncio.Queue[MarketData] = asyncio.Queue(
            maxsize=config.queue_max_size
        )
        self._running = False
        self._overflow_count = 0
        self._task: asyncio.Task | None = None

        # Initialize components
        self._source = MockDataSource(config)
        self._processor = QuoteProcessor(redis=redis, faults=config.faults)

    async def start(self) -> None:
        """Start generating quotes for subscribed symbols."""
        if self._running:
            return

        self._running = True
        await self._source.subscribe(list(self._subscribed))
        await self._source.start()

        # Start background task to pump quotes
        self._task = asyncio.create_task(self._pump_quotes())
        logger.info(f"MarketDataService started for {len(self._subscribed)} symbols")

    async def stop(self) -> None:
        """Stop generation, cleanup."""
        self._running = False
        await self._source.stop()

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(f"MarketDataService stopped. Overflow count: {self._overflow_count}")

    def ensure_subscribed(self, symbols: list[str]) -> None:
        """
        Ensure symbols are subscribed. Idempotent.
        Can be called before or after start().
        """
        self._subscribed.update(symbols)

    async def get_quote(self, symbol: str) -> QuoteSnapshot | None:
        """
        Get latest cached quote snapshot. Async (reads Redis).
        Returns QuoteSnapshot or None if unavailable.
        """
        key = f"quote:{symbol}"
        data = await self._redis.get(key)
        if not data:
            return None

        parsed = json.loads(data)
        return QuoteSnapshot(
            symbol=parsed["symbol"],
            price=Decimal(parsed["price"]),
            bid=Decimal(parsed["bid"]),
            ask=Decimal(parsed["ask"]),
            volume=parsed["volume"],
            timestamp=datetime.fromisoformat(parsed["timestamp"]),
            cached_at=datetime.fromisoformat(parsed["cached_at"]),
        )

    def get_stream(self) -> asyncio.Queue[MarketData]:
        """
        Get the distribution queue.
        Consumer (StrategyEngine) reads from this.
        """
        return self._stream

    async def _pump_quotes(self) -> None:
        """Background task: read from source, process, enqueue."""
        try:
            async for quote in self._source.quotes():
                if not self._running:
                    break

                result = await self._processor.process(quote)

                # Handle duplicate fault (returns list)
                if isinstance(result, list):
                    for q in result:
                        await self._enqueue(q)
                elif result:
                    await self._enqueue(result)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in quote pump: {e}", exc_info=True)

    async def _enqueue(self, quote: MarketData) -> None:
        """Enqueue quote with drop-oldest overflow policy."""
        if self._stream.full():
            try:
                self._stream.get_nowait()  # Drop oldest
                self._overflow_count += 1
                if self._overflow_count % 100 == 1:  # Log every 100th drop
                    logger.warning(
                        f"Queue overflow, dropped oldest. Total drops: {self._overflow_count}"
                    )
            except asyncio.QueueEmpty:
                pass
        await self._stream.put(quote)
```

**Step 10.4: Run tests to verify they pass**

```bash
cd backend && pytest tests/market_data/test_service.py -v
```

Expected: PASS

**Step 10.5: Commit**

```bash
git add backend/src/market_data/service.py backend/tests/market_data/test_service.py
git commit -m "feat(market_data): add MarketDataService with queue distribution"
```

---

## Task 11: Package Exports

**Files:**
- Modify: `backend/src/market_data/__init__.py`

**Step 11.1: Write package exports**

Update `backend/src/market_data/__init__.py`:

```python
# backend/src/market_data/__init__.py
"""Market data module."""

from src.market_data.models import (
    FaultConfig,
    MarketDataConfig,
    QuoteSnapshot,
    SymbolScenario,
)
from src.market_data.processor import QuoteProcessor
from src.market_data.service import MarketDataService
from src.market_data.sources.base import DataSource
from src.market_data.sources.mock import MockDataSource

__all__ = [
    "DataSource",
    "FaultConfig",
    "MarketDataConfig",
    "MarketDataService",
    "MockDataSource",
    "QuoteProcessor",
    "QuoteSnapshot",
    "SymbolScenario",
]
```

**Step 11.2: Verify imports work**

```bash
cd backend && python -c "from src.market_data import MarketDataService, QuoteSnapshot, MockDataSource; print('OK')"
```

Expected: `OK`

**Step 11.3: Run all market_data tests**

```bash
cd backend && pytest tests/market_data -v
```

Expected: All tests PASS

**Step 11.4: Commit**

```bash
git add backend/src/market_data/__init__.py
git commit -m "feat(market_data): add package exports"
```

---

## Task 12: Full Test Suite Verification

**Step 12.1: Run full backend test suite**

```bash
cd backend && pytest -v
```

Expected: All tests PASS (122 existing + new market_data tests)

**Step 12.2: Verify no circular imports**

```bash
cd backend && python -c "from src.market_data import MarketDataService; from src.strategies.engine import StrategyEngine; print('No circular imports')"
```

Expected: `No circular imports`

**Step 12.3: Final commit if any loose ends**

```bash
git status
# If clean, done. Otherwise add and commit remaining changes.
```

---

## Summary

**Files created:**
- `backend/src/market_data/__init__.py`
- `backend/src/market_data/models.py`
- `backend/src/market_data/processor.py`
- `backend/src/market_data/service.py`
- `backend/src/market_data/sources/__init__.py`
- `backend/src/market_data/sources/base.py`
- `backend/src/market_data/sources/mock.py`
- `backend/tests/market_data/__init__.py`
- `backend/tests/market_data/test_models.py`
- `backend/tests/market_data/test_sources.py`
- `backend/tests/market_data/test_mock_scenarios.py`
- `backend/tests/market_data/test_processor.py`
- `backend/tests/market_data/test_service.py`

**Key features:**
- `QuoteSnapshot` with event-time staleness detection
- `MockDataSource` with 6 scenarios (flat, trend_up, trend_down, volatile, jump, stale)
- `QuoteProcessor` with fault injection (delay, duplicate, out-of-order)
- `MarketDataService` with drop-oldest queue overflow policy
- YAML configuration loading
- Full TDD coverage
