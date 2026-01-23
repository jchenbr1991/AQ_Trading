# Strategy Engine Design

Date: 2026-01-23

## Overview

The Strategy Engine is a pluggable framework where each strategy is an independent Python class. Strategies receive market data, analyze it, and emit Signals (not Orders). The Risk Manager validates signals before they become orders.

## Design Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Market data delivery | Hybrid (push + pull) | Strategies receive `on_market_data()` callbacks; can also pull via `context.get_quote()` |
| Process model | Same process, async | Simpler, lower latency. Exception handling isolates strategy errors. |
| Strategy discovery | Explicit config file | Clear control, easy versioning, no magic auto-discovery |
| Signal processing | Sequential | Predictable order, each signal evaluated independently |

## File Structure

```
backend/src/strategies/
├── __init__.py
├── base.py          # Strategy ABC, MarketData, OrderFill
├── context.py       # StrategyContext (read-only portfolio view)
├── signals.py       # Signal dataclass
├── registry.py      # Load/manage strategies from config
├── engine.py        # StrategyEngine orchestrator
└── examples/
    └── momentum.py  # Example strategy

backend/config/
└── strategies.yaml  # Strategy configuration

backend/tests/
└── test_strategy_engine.py
```

## Core Interfaces

### Signal (`signals.py`)

```python
@dataclass
class Signal:
    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"] = "market"
    limit_price: Decimal | None = None
    reason: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
```

### MarketData (`base.py`)

```python
@dataclass
class MarketData:
    symbol: str
    price: Decimal
    bid: Decimal
    ask: Decimal
    volume: int
    timestamp: datetime
```

### OrderFill (`base.py`)

```python
@dataclass
class OrderFill:
    order_id: str
    strategy_id: str
    symbol: str
    action: Literal["buy", "sell"]
    quantity: int
    price: Decimal
    commission: Decimal
    timestamp: datetime
```

### Strategy ABC (`base.py`)

```python
class Strategy(ABC):
    name: str
    symbols: list[str]

    @abstractmethod
    async def on_market_data(self, data: MarketData, context: StrategyContext) -> list[Signal]:
        """React to price updates, return signals (can be empty)."""

    async def on_fill(self, fill: OrderFill) -> None:
        """Called when an order fills. Override if needed."""
        pass

    async def on_start(self) -> None:
        """Called when strategy starts. Override for initialization."""
        pass

    async def on_stop(self) -> None:
        """Called when strategy stops. Override for cleanup."""
        pass
```

### StrategyContext (`context.py`)

Read-only view of portfolio, filtered to the strategy's positions.

```python
class StrategyContext:
    def __init__(
        self,
        strategy_id: str,
        account_id: str,
        portfolio: PortfolioManager,
        quote_cache: dict[str, MarketData],
    ):
        self._strategy_id = strategy_id
        self._account_id = account_id
        self._portfolio = portfolio
        self._quote_cache = quote_cache

    async def get_my_positions(self) -> list[Position]:
        """Positions owned by this strategy only."""

    async def get_my_pnl(self) -> Decimal:
        """Unrealized P&L for this strategy's positions."""

    def get_quote(self, symbol: str) -> MarketData | None:
        """Get cached quote for any symbol."""

    async def get_position(self, symbol: str) -> Position | None:
        """Get this strategy's position in a symbol."""
```

### StrategyRegistry (`registry.py`)

Loads strategies from config file.

```python
class StrategyRegistry:
    def __init__(self, config_path: str, portfolio: PortfolioManager):
        self._strategies: dict[str, Strategy] = {}

    async def load_strategies(self) -> None:
        """Load enabled strategies from config."""

    def get_strategy(self, name: str) -> Strategy | None:
        """Get strategy by name."""

    def all_strategies(self) -> list[Strategy]:
        """Get all loaded strategies."""

    async def shutdown(self) -> None:
        """Stop all strategies gracefully."""
```

### StrategyEngine (`engine.py`)

Orchestrates market data dispatch and signal collection.

```python
class StrategyEngine:
    def __init__(
        self,
        registry: StrategyRegistry,
        portfolio: PortfolioManager,
        risk_manager: "RiskManager",
    ):
        self._registry = registry
        self._portfolio = portfolio
        self._risk_manager = risk_manager
        self._quote_cache: dict[str, MarketData] = {}
        self._running = False

    async def on_market_data(self, data: MarketData) -> None:
        """Dispatch market data to subscribed strategies."""

    async def on_fill(self, fill: OrderFill) -> None:
        """Notify strategy of fill."""

    async def start(self) -> None:
        """Load strategies and start engine."""

    async def stop(self) -> None:
        """Stop engine and shutdown strategies."""
```

## Configuration

`config/strategies.yaml`:

```yaml
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

## Data Flow

```
Market Data (from Futu/Redis)
       ↓
StrategyEngine.on_market_data()
       ↓
Strategy.on_market_data(data, context)
       ↓
list[Signal]
       ↓
RiskManager.evaluate(signal)  [sequential]
       ↓
OrderManager.submit(order)
       ↓
Broker execution
       ↓
StrategyEngine.on_fill()
       ↓
Strategy.on_fill(fill)
```

## Error Handling

- Each strategy's `on_market_data()` is wrapped in try/except
- One strategy's error does not affect others
- Errors are logged with strategy name and full traceback
- Engine continues processing other strategies

## Testing Strategy

1. **Unit tests for Signal dataclass** - Serialization, defaults
2. **Unit tests for MomentumStrategy** - Warmup period, buy/sell logic
3. **Unit tests for StrategyContext** - Position filtering, quote cache
4. **Unit tests for StrategyEngine** - Dispatch logic, error isolation
5. **Integration test** - Full flow from market data to signal emission

## Future Considerations (Phase 2+)

- Strategy warm-up with historical data (`warmup_bars` property)
- Trace system integration (capture context at signal time)
- Strategy pause/resume via dashboard
- Hot-reload of strategy parameters
