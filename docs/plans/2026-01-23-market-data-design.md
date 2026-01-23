# Market Data Service Design

Phase 1 implementation plan for the Market Data component.

## Overview

The Market Data Service generates, caches, and distributes market quotes for the trading system. Phase 1 uses mock data with configurable scenarios for testing; real Futu integration deferred to Phase 2.

**Key Decisions:**
- Data source: Mock (random walk + scenarios)
- Subscription: Static via `ensure_subscribed()`, idempotent
- Distribution: `asyncio.Queue` with backpressure
- Caching: Redis `quote:{symbol}` with staleness metadata
- Fault injection: First-class citizen for resilience testing

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MarketDataService                         │
│  ┌─────────────────┐    ┌─────────────────┐                 │
│  │  MockDataSource │───▶│  QuoteProcessor │───▶ asyncio.Queue
│  │  (random walk + │    │  (normalize,    │        │
│  │   scenarios)    │    │   fault inject) │        ▼
│  └─────────────────┘    └────────┬────────┘   StrategyEngine
│                                  │
│                                  ▼
│                         ┌───────────────┐
│                         │  Redis Cache  │
│                         │ quote:{symbol}│◀─── PortfolioManager
│                         └───────────────┘      (reads for P&L)
└─────────────────────────────────────────────────────────────┘
```

**Components:**
1. **MockDataSource** - Generates quotes via random walk with configurable scenarios
2. **QuoteProcessor** - Normalizes data, injects faults, writes to Redis cache
3. **asyncio.Queue** - Distributes to StrategyEngine with backpressure
4. **Redis Cache** - Cross-module state reference (NOT a data source for indicators)

## Data Models

### MarketData (existing)

Already defined in `strategies/base.py`:

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

### Redis Cache Schema

```
Key: quote:{symbol}
Value: JSON
{
    "symbol": "AAPL",
    "price": "150.25",
    "bid": "150.20",
    "ask": "150.30",
    "volume": 1000000,
    "timestamp": "2024-01-15T10:30:00.123Z",
    "cached_at": "2024-01-15T10:30:00.150Z"
}
```

**Staleness detection:**
- `timestamp` = quote's original timestamp from source
- `cached_at` = when written to Redis
- Consumer checks: `now - cached_at > threshold` → stale
- No TTL expiry; stale quotes remain visible with staleness flag

### SymbolScenario

```python
@dataclass
class SymbolScenario:
    symbol: str
    scenario: Literal["flat", "trend_up", "trend_down", "volatile", "jump", "stale"]
    base_price: Decimal
    tick_interval_ms: int = 100
```

### FaultConfig

```python
@dataclass
class FaultConfig:
    enabled: bool = False
    delay_probability: float = 0.0
    delay_ms_range: tuple[int, int] = (100, 500)
    duplicate_probability: float = 0.0
    out_of_order_probability: float = 0.0
    out_of_order_offset_ms: int = 200
    stale_window_probability: float = 0.0
    stale_window_duration_ms: tuple[int, int] = (2000, 5000)
```

## Scenario Implementation

**Random walk base formula:**
```
new_price = old_price * (1 + drift + volatility * random(-1, 1))
```

**Scenario parameters:**

| Scenario | Drift | Volatility | Special Behavior |
|----------|-------|------------|------------------|
| `flat` | 0 | 0.0001 | Near-zero movement |
| `trend_up` | +0.0005 | 0.001 | Steady upward bias |
| `trend_down` | -0.0005 | 0.001 | Steady downward bias |
| `volatile` | 0 | 0.01 | 10x normal volatility |
| `jump` | 0 | 0.001 | 2% chance of ±5% jump per tick |
| `stale` | 0 | 0.001 | Stops emitting for 5-10s periodically |

## Fault Injection

Faults are applied globally (all symbols). Per-symbol fault config deferred to Phase 2.

| Fault | Implementation |
|-------|----------------|
| `delay` | `await asyncio.sleep(random_ms)` before emitting |
| `duplicate` | Emit same quote twice with same timestamp |
| `out_of_order` | Emit quote with `timestamp - offset` (appears older) |
| `stale_window` | Skip emitting for N seconds, then resume |

## Public Interface

```python
class MarketDataService:
    """
    Market data distribution service.

    Generates mock quotes, caches to Redis, distributes via queue.
    """

    def __init__(
        self,
        redis: RedisClient,
        config: MarketDataConfig,
    ):
        ...

    async def start(self) -> None:
        """Start generating quotes for subscribed symbols."""

    async def stop(self) -> None:
        """Stop generation, drain queue."""

    def ensure_subscribed(self, symbols: list[str]) -> None:
        """
        Ensure symbols are subscribed. Idempotent.
        Can be called before or after start().
        """

    def get_quote(self, symbol: str) -> MarketData | None:
        """
        Get latest cached quote. Sync, non-blocking.
        Returns None if no quote available.
        """

    def get_stream(self) -> asyncio.Queue[MarketData]:
        """
        Get the distribution queue.
        Consumer (StrategyEngine) reads from this.
        """
```

**Usage by StrategyEngine:**
```python
# At startup
symbols = registry.collect_all_symbols()
market_data.ensure_subscribed(symbols)
stream = market_data.get_stream()

# In run loop
while running:
    quote = await stream.get()
    await engine.on_market_data(quote)
```

## File Structure

```
backend/src/
├── market_data/
│   ├── __init__.py         # Exports
│   ├── service.py          # MarketDataService
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py         # DataSource protocol (for future Futu)
│   │   └── mock.py         # MockDataSource with scenarios
│   ├── models.py           # SymbolScenario, FaultConfig, MarketDataConfig
│   └── processor.py        # QuoteProcessor (fault injection, Redis write)

backend/tests/
├── market_data/
│   ├── __init__.py
│   ├── test_mock_source.py     # Scenario generation tests
│   ├── test_processor.py       # Fault injection tests
│   ├── test_service.py         # Integration tests
│   └── test_redis_cache.py     # Cache read/write/staleness tests
```

## Configuration

**`config/default.yaml`:**
```yaml
market_data:
  queue_max_size: 1000
  default_tick_interval_ms: 100
  staleness_threshold_ms: 5000

  symbols:
    AAPL:
      scenario: "volatile"
      base_price: "150.00"
      tick_interval_ms: 50

    TSLA:
      scenario: "trend_up"
      base_price: "250.00"

    SPY:
      scenario: "flat"
      base_price: "450.00"

  faults:
    enabled: false
    delay_probability: 0.05
    delay_ms_range: [100, 500]
    duplicate_probability: 0.02
    out_of_order_probability: 0.01
    out_of_order_offset_ms: 200
    stale_window_probability: 0.01
    stale_window_duration_ms: [2000, 5000]
```

## Testing Strategy

| Category | Tests | Purpose |
|----------|-------|---------|
| **MockDataSource** | Scenario price generation | Verify drift/volatility/jumps |
| **QuoteProcessor** | Fault injection | Verify delays, duplicates, out-of-order |
| **Redis Cache** | Write/read/staleness | Verify cache schema, staleness detection |
| **Service Integration** | End-to-end flow | Subscribe → generate → queue → consume |

**Key test cases:**

```python
# test_mock_source.py
class TestScenarios:
    def test_flat_scenario_minimal_movement(self)
    def test_trend_up_positive_drift(self)
    def test_volatile_high_variance(self)
    def test_jump_occasional_large_moves(self)
    def test_stale_stops_emitting_periodically(self)

# test_processor.py
class TestFaultInjection:
    async def test_delay_adds_latency(self)
    async def test_duplicate_emits_twice(self)
    async def test_out_of_order_older_timestamp(self)
    async def test_stale_window_pauses_emission(self)
    async def test_faults_disabled_no_injection(self)

# test_redis_cache.py
class TestRedisCache:
    async def test_quote_written_to_redis(self)
    async def test_cached_at_timestamp_set(self)
    async def test_staleness_detection(self)
    async def test_get_quote_returns_cached(self)

# test_service.py
class TestMarketDataService:
    async def test_ensure_subscribed_idempotent(self)
    async def test_start_generates_quotes(self)
    async def test_stop_drains_queue(self)
    async def test_stream_receives_quotes(self)
    async def test_multiple_symbols_interleaved(self)
```

## Implementation Tasks (TDD Order)

1. **Models** - `SymbolScenario`, `FaultConfig`, `MarketDataConfig`
2. **DataSource protocol** - Base interface for future Futu integration
3. **MockDataSource** - Random walk with scenario parameters
4. **QuoteProcessor** - Fault injection, Redis cache write
5. **MarketDataService** - Orchestration, queue management
6. **Config loading** - YAML parsing
7. **StrategyEngine integration** - Wire up queue consumption
8. **Package exports** - `__init__.py`

## Future Considerations (Not Phase 1)

- **Phase 2**: Real Futu integration via `FutuDataSource` implementing same protocol
- **Phase 2**: Per-symbol fault configuration
- **Phase 2**: Historical data replay (`HistoricalReplaySource`)
- **Phase 2**: Dynamic subscription at runtime
