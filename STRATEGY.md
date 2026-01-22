# STRATEGY.md

Strategic design document for AQ Trading - a full-stack algorithmic trading system.

## Overview

- **Markets**: US Equities + Futures/Options
- **Broker**: Futu (moomoo) via OpenAPI
- **Stack**: Python backend (FastAPI) + TypeScript frontend (React)
- **Database**: PostgreSQL (TimescaleDB) + Redis
- **Communication**: REST + WebSocket
- **Deployment**: Local first, Docker-ready for cloud

---

## Development Phases (MVP Roadmap)

### Phase 1: Minimum Viable Trading System (必须)

Core functionality to execute and track trades safely.

| Component | Scope | Deliverable |
|-----------|-------|-------------|
| **Portfolio Manager** | Position tracking, account sync, transaction ledger | `core/portfolio.py` |
| **Strategy Engine** | Base strategy interface, context, signals | `strategies/base.py`, `context.py` |
| **Risk Manager** | Position limits, portfolio limits, loss limits, kill switch | `core/risk_manager.py` |
| **Order Manager** | Order lifecycle, Futu API integration, fill handling | `core/order_manager.py` |
| **Reconciliation** | Periodic broker sync, discrepancy detection | `core/reconciliation.py` |
| **Trading Modes** | Live + Paper trading toggle | `broker/paper.py` |
| **Basic Dashboard** | Positions view, P&L, pause/resume controls | Frontend MVP |
| **Basic Market Data** | Quote subscription, Redis cache | `core/market_data.py` |

**Exit Criteria:** Can run a simple strategy in paper mode, track positions, and manually intervene via dashboard.

---

### Phase 2: Enhanced Analytics & Testing (增强)

Confidence-building before real capital deployment.

| Component | Scope | Deliverable |
|-----------|-------|-------------|
| **Backtesting Engine** | Historical simulation, same strategy code | `backtest/engine.py` |
| **Benchmark Comparison** | Alpha, beta, Sharpe vs SPY/HSI | `backtest/results.py` |
| **Trace Viewer** | Signal-to-fill audit trail, context snapshots | `api/routes/traces.py`, Dashboard |
| **Slippage Analysis** | Expected vs actual fill price tracking | Trace analytics |
| **Strategy Warm-up** | Historical indicator initialization | `strategies/base.py` |
| **Health Monitoring** | Multi-layer heartbeat, alerts | `core/health_monitor.py` |
| **Retention Policies** | Data archival, snapshot compression | `db/retention.py` |

**Exit Criteria:** Can backtest strategies with benchmark comparison, analyze trade execution quality, trust system health.

---

### Phase 3: Advanced Features (进阶)

Sophistication for complex instruments and automation.

| Component | Scope | Deliverable |
|-----------|-------|-------------|
| **Options Lifecycle** | Expiration tracking, assignment handling | `core/expiration_manager.py` |
| **Futures Roll-over** | Automatic contract rolling | `core/expiration_manager.py` |
| **Greeks Monitoring** | Portfolio delta/theta/vega tracking | Risk Manager extension |
| **CLI Agents** | Researcher, Analyst, Risk Controller, Ops | `agents/` |
| **Dynamic Risk Bias** | Agent-driven risk adjustment | Agent + Redis integration |
| **Sentiment Factors** | News/social media factor production | Analyst agent |
| **Auto-Tuning** | Parameter optimization with overfitting guards | Researcher agent |
| **Graceful Degradation** | Automatic failover policies | `core/health_monitor.py` |

**Exit Criteria:** Can trade options/futures with proper lifecycle management, leverage agents for optimization without manual intervention.

---

### Phase Summary

```
Phase 1 (MVP)          Phase 2 (Analytics)      Phase 3 (Advanced)
─────────────────      ──────────────────       ──────────────────
Portfolio Manager      Backtesting              Options Lifecycle
Strategy Engine        Benchmark Compare        Futures Roll-over
Risk Manager (basic)   Trace Viewer             Greeks Monitoring
Order Manager          Slippage Analysis        CLI Agents
Reconciliation         Strategy Warm-up         Dynamic Risk Bias
Live / Paper Mode      Health Monitoring        Sentiment Factors
Basic Dashboard        Retention Policies       Auto-Tuning
Basic Market Data                               Graceful Degradation

Timeline: 4-6 weeks    Timeline: 2-4 weeks      Timeline: Ongoing
```

**Rule:** Complete Phase N before starting Phase N+1. Resist feature creep.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     TypeScript Dashboard                        │
│              (React + WebSocket + REST client)                  │
└─────────────────────┬───────────────────────────────────────────┘
                      │ REST (commands) + WebSocket (streaming)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Python Backend                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ REST API    │  │ WebSocket   │  │ Strategy Engine         │  │
│  │ (FastAPI)   │  │ Server      │  │ (pluggable strategies)  │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Portfolio   │  │ Risk        │  │ Order Manager           │  │
│  │ Manager     │  │ Manager     │  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
┌─────────────┐ ┌───────────┐ ┌─────────────┐
│ PostgreSQL  │ │   Redis   │ │ Futu OpenAPI│
│ (persistent)│ │ (cache/   │ │ (broker)    │
│             │ │  pub-sub) │ │             │
└─────────────┘ └───────────┘ └─────────────┘
```

**Core flow:**
- Futu OpenAPI provides market data and order execution
- Python backend processes data, runs strategies, manages risk
- Redis caches live prices and broadcasts updates via pub/sub
- PostgreSQL stores positions, orders, trade history
- Dashboard subscribes to WebSocket for real-time updates, sends commands via REST

---

## Component Design

### 1. Portfolio Manager

The foundation - everything depends on accurate position tracking.

**Responsibilities:**
- Position tracking with cost basis and unrealized P&L
- Account sync with Futu on startup and periodically
- Transaction ledger for accurate cost basis
- Multi-asset support (stocks, options, futures)

**Data models:**

```
Account
├── account_id, broker, currency, buying_power, margin_used

Position
├── symbol, asset_type (stock/option/future), quantity
├── avg_cost, current_price, unrealized_pnl
├── strategy_id: str | None    # Which strategy owns this
├── option fields: strike, expiry, put_call (nullable for stocks)

Transaction
├── timestamp, symbol, action (buy/sell/dividend/fee)
├── quantity, price, commission, realized_pnl
├── strategy_id: str | None

DailySnapshot
├── date, total_equity, total_pnl, positions_json

StrategyPerformance (derived/cached)
├── strategy_id, date
├── positions_value, realized_pnl, unrealized_pnl
├── win_rate, sharpe_ratio, max_drawdown
```

**Key operations:**
- `sync_with_broker()` - Pull actual positions from Futu, reconcile differences
- `record_fill(order_fill)` - Update positions when orders execute
- `calculate_pnl()` - Real-time P&L using Redis-cached prices
- `get_exposure(symbol)` - Current exposure for risk checks
- `get_positions(strategy_id)` - Filter positions by strategy

The Portfolio Manager is intentionally passive - it tracks state but doesn't make decisions.

---

### 2. Strategy Engine

Pluggable framework where each strategy is an independent module.

**Strategy interface:**

```python
class Strategy(ABC):
    name: str
    symbols: list[str]

    @abstractmethod
    def on_market_data(self, data: MarketData, context: StrategyContext) -> list[Signal]:
        """React to price updates, return buy/sell signals"""

    @abstractmethod
    def on_fill(self, fill: OrderFill) -> None:
        """React to order executions"""

    def on_start(self) -> None: ...
    def on_stop(self) -> None: ...
```

**Strategy context (read-only view from Portfolio Manager):**

```python
class StrategyContext:
    my_positions: list[Position]    # Filtered by strategy_id
    my_orders: list[Order]          # Open orders for this strategy
    my_pnl: float                   # Strategy-specific P&L
    buying_power: float
    total_exposure: float
```

**Signal flow:**

```
Market Data (from Futu)
       ↓
Strategy.on_market_data(data, context)
       ↓
Signal(strategy_id, symbol, action, quantity, reason)
       ↓
Risk Manager (validates)
       ↓
Order Manager (executes)
       ↓
Portfolio Manager (updates positions)
       ↓
Strategy.on_fill() ← fill confirmation
```

**Key principle:** Strategies emit Signals, not Orders. They express intent; Risk Manager and Order Manager handle execution details.

**Strategy position tagging:**
- Each position/order tagged with `strategy_id`
- Same symbol can be held by multiple strategies
- Manual trades from dashboard tagged as `strategy_id=None`
- Enables per-strategy P&L tracking and isolation

---

### 3. Risk Manager

Sits between strategies and order execution. Every signal must pass through.

**Risk checks (executed in order):**

```
Signal arrives
    ↓
1. Position Limits
   - Max shares per symbol
   - Max notional per symbol
   - Max positions count

2. Portfolio Limits
   - Max total exposure (% of equity)
   - Max sector concentration
   - Buying power check

3. Loss Limits
   - Daily loss limit ($ or %)
   - Max drawdown from peak
   - Per-strategy loss limit

4. Options Greeks (if applicable)
   - Max portfolio delta
   - Max portfolio theta
   - Max portfolio vega

5. Kill Switch Check
   - Global halt active?
   - Strategy paused?
    ↓
APPROVED → Order Manager
REJECTED → Log reason, notify dashboard
REDUCED  → Adjust quantity, proceed
```

**Risk configuration:**

```yaml
risk:
  position:
    max_shares_per_symbol: 1000
    max_notional_per_symbol: 50000
  portfolio:
    max_exposure_pct: 80
    max_positions: 20
  loss:
    daily_loss_limit: 2000
    max_drawdown_pct: 10
  greeks:
    max_portfolio_delta: 500
    max_portfolio_theta: -200
  kill_switch:
    auto_trigger_on_daily_loss: true
```

---

### 4. Order Manager

Handles order lifecycle from approved signals to executed fills.

**Order lifecycle:**

```
Signal (from Risk Manager)
    ↓
Order Creation
  - Map signal to order type
  - Set price (market/limit)
  - Attach strategy_id tag
  - Generate internal order_id
    ↓
Futu API Submission
  - Submit via futu-api SDK
  - Store broker_order_id mapping
  - Handle submission errors
    ↓
Order Tracking (async)
  - Subscribe to order updates
  - Handle partial fills
  - Detect rejections/cancellations
    ↓
On Fill:
  → portfolio.record_fill(fill)
  → strategy.on_fill(fill)
  → redis.publish("fills", fill)
  → Check if stop-loss needed
```

**Order types supported:**

```python
class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing"

class Order:
    order_id: str
    broker_order_id: str
    strategy_id: str
    symbol: str
    side: BUY | SELL
    quantity: int
    order_type: OrderType
    limit_price: float | None
    stop_price: float | None
    trailing_pct: float | None
    status: PENDING | SUBMITTED | PARTIAL | FILLED | CANCELLED | REJECTED
    filled_qty: int
    avg_fill_price: float
    created_at: datetime
    updated_at: datetime
```

**Automated stop-loss attachment:**

```python
signal = Signal(
    symbol="AAPL",
    action="buy",
    quantity=100,
    stop_loss_pct=2.0,      # Auto-create 2% stop
    trailing_stop_pct=5.0   # Or trailing 5% stop
)
# Order Manager creates linked parent + child stop orders
```

---

### 5. Backtesting Framework

Test strategies against historical data using the same code that runs live.

**Key principle: One strategy, two modes**

```python
# Same strategy class works in both modes
engine = LiveEngine(broker=FutuBroker())
engine.run(MomentumStrategy())

engine = BacktestEngine(data=historical_data, benchmark="SPY")
results = engine.run(MomentumStrategy())
```

**Backtest architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    BacktestEngine                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ DataFeed     │  │ Simulated    │  │ Simulated        │   │
│  │ (historical) │  │ Broker       │  │ Portfolio        │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
│                                                             │
│  Event Loop (simulated time):                               │
│    for each bar:                                            │
│      1. Update simulated prices                             │
│      2. Process pending orders (with slippage)              │
│      3. Call strategy.on_market_data()                      │
│      4. Process signals through risk manager                │
│      5. Record metrics                                      │
└─────────────────────────────────────────────────────────────┘
```

**Simulated broker features:**

```python
class SimulatedBroker:
    slippage_model: SlippageModel    # FixedSlippage, PctSlippage, VolumeSlippage
    commission_model: CommissionModel
    fill_delay_bars: int
    partial_fills: bool
```

**Backtest results with benchmark comparison:**

```python
@dataclass
class BacktestResult:
    # Strategy performance
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    max_drawdown_duration: timedelta

    # Benchmark comparison
    benchmark: str                    # "SPY", "HSI", "QQQ"
    benchmark_return: float
    benchmark_annualized: float
    benchmark_max_drawdown: float

    # Risk-adjusted vs benchmark
    alpha: float                      # Excess return vs benchmark
    beta: float                       # Correlation to benchmark
    information_ratio: float          # Alpha / tracking error
    tracking_error: float
    up_capture: float                 # Performance in up markets
    down_capture: float               # Performance in down markets

    # Trade stats
    total_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float

    # Series data (for charting)
    equity_curve: pd.Series
    benchmark_curve: pd.Series
    drawdown_curve: pd.Series
    trades: pd.DataFrame

    # Per-strategy breakdown
    strategy_results: dict[str, StrategyResult]
```

---

### 6. Market Data Component

Collects, stores, and distributes price data.

**Architecture:**

```
Futu OpenAPI (quotes, order book, K-line)
       ↓
MarketDataService
  ├── Subscriber (Futu WS)
  ├── Normalizer (clean data)
  └── Distributor (fan out)
       ↓
  ┌────┴────┬──────────────┐
  ↓         ↓              ↓
Redis    PostgreSQL    Redis PubSub
(cache)  (historical)  (to strategies)
```

**Data types:**

```python
@dataclass
class Quote:
    symbol: str
    timestamp: datetime
    price: float
    bid: float
    ask: float
    bid_size: int
    ask_size: int
    volume: int

@dataclass
class Bar:
    symbol: str
    timestamp: datetime
    timeframe: str  # 1m, 5m, 15m, 1h, 1d
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class OptionContract:
    symbol: str
    underlying: str
    strike: float
    expiry: date
    put_call: PUT | CALL
    bid: float
    ask: float
    volume: int
    open_interest: int
    iv: float
    delta: float
    gamma: float
    theta: float
    vega: float
```

**TimescaleDB for time-series:**

```python
class TimeSeriesRepository:
    async def get_bars(self, symbol, timeframe, start, end) -> list[Bar]:
        """Use time_bucket for efficient resampling"""

    async def get_latest_prices(self, symbols) -> dict[str, float]:
        """Get most recent price for each symbol"""
```

---

### 7. Dashboard

TypeScript frontend for monitoring and manual override.

**Tech stack:**
- React + TypeScript + Vite
- TanStack Query (data fetching)
- Zustand (state management)
- Recharts (charts)
- Tailwind CSS
- Socket.io-client (WebSocket)

**Pages:**

```
/                   Dashboard home - summary overview
/portfolio          Positions, P&L, exposure breakdown
/strategies         Strategy status, per-strategy P&L
/orders             Open orders, order history
/risk               Risk metrics, Greeks, limits status
/backtest           Run backtests, view results
/traces             Trade trace analysis & debugging
/health             System health, component status
/settings           Configuration, risk limits, alerts
```

**WebSocket events:**

```typescript
interface WSEvents {
  "quote:update": { symbol: string; price: number; change: number };
  "position:update": { positions: Position[] };
  "order:update": { order: Order };
  "order:fill": { fill: OrderFill };
  "alert:trigger": { alert: Alert; severity: "info" | "warning" | "critical" };
  "risk:breach": { rule: string; current: number; limit: number };
}
```

**Manual override controls:**
- Pause/resume individual strategies
- Global kill switch
- Emergency flatten all positions
- Manual close single position
- Adjust risk limits on the fly

---

## Project Structure

```
aq_trading/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   │
│   ├── src/
│   │   ├── main.py
│   │   ├── config.py
│   │   │
│   │   ├── api/
│   │   │   ├── routes/             # REST endpoints
│   │   │   │   ├── portfolio.py
│   │   │   │   ├── orders.py
│   │   │   │   ├── strategies.py
│   │   │   │   ├── risk.py
│   │   │   │   ├── backtest.py
│   │   │   │   ├── traces.py       # Trade trace analysis
│   │   │   │   └── health.py       # System health status
│   │   │   ├── websocket.py
│   │   │   └── openapi.py          # Generate OpenAPI schema
│   │   │
│   │   ├── core/                   # Core business logic
│   │   │   ├── portfolio.py
│   │   │   ├── order_manager.py
│   │   │   ├── risk_manager.py
│   │   │   ├── market_data.py
│   │   │   ├── health_monitor.py       # System health & heartbeats
│   │   │   ├── reconciliation.py       # Broker ↔ local sync
│   │   │   ├── expiration_manager.py   # Derivative lifecycle
│   │   │   └── tracing.py              # Structured trace context
│   │   │
│   │   ├── strategies/
│   │   │   ├── base.py             # Strategy ABC
│   │   │   ├── context.py          # StrategyContext
│   │   │   ├── signals.py          # Signal types
│   │   │   ├── registry.py         # Strategy discovery
│   │   │   ├── examples/           # Reference implementations (safe to modify)
│   │   │   │   ├── covered_call.py
│   │   │   │   ├── momentum.py
│   │   │   │   └── mean_reversion.py
│   │   │   └── live/               # PRODUCTION (do not modify without review)
│   │   │       └── .protected
│   │   │
│   │   ├── backtest/
│   │   │   ├── engine.py
│   │   │   ├── simulated_broker.py
│   │   │   ├── slippage.py
│   │   │   └── results.py
│   │   │
│   │   ├── broker/
│   │   │   ├── base.py
│   │   │   ├── paper.py                # Paper trading (simulated execution)
│   │   │   └── futu/
│   │   │       ├── client.py
│   │   │       ├── quotes.py
│   │   │       └── trading.py
│   │   │
│   │   ├── models/                 # Pydantic models (source of truth)
│   │   │   ├── account.py
│   │   │   ├── position.py
│   │   │   ├── order.py
│   │   │   ├── transaction.py
│   │   │   └── market_data.py
│   │   │
│   │   ├── db/
│   │   │   ├── database.py
│   │   │   ├── redis.py
│   │   │   ├── timescale.py        # TimescaleDB utilities
│   │   │   └── repositories/
│   │   │       ├── portfolio_repo.py
│   │   │       ├── order_repo.py
│   │   │       ├── timeseries_repo.py
│   │   │       ├── trace_repo.py       # Signal trace storage
│   │   │       └── wal_repo.py         # Write-ahead log
│   │   │
│   │   └── utils/
│   │       ├── indicators.py
│   │       ├── options.py
│   │       └── logging.py
│   │
│   └── tests/
│
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── orval.config.ts             # OpenAPI → TypeScript generator
│   │
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   └── generated/          # Auto-generated (do not edit)
│   │   ├── stores/
│   │   └── types/
│   │
│   ├── scripts/
│   │   └── generate-types.sh
│   └── tests/
│
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   ├── docker-compose.yml
│   └── futu-opend/                 # FutuOpenD container (VNC-based)
│       ├── Dockerfile
│       └── supervisord.conf
│
├── config/
│   ├── default.yaml
│   ├── development.yaml
│   ├── production.yaml
│   ├── degradation.yaml            # Fault tolerance policies
│   ├── reconciliation.yaml         # Sync schedule & tolerances
│   └── strategies/                 # Per-strategy configs
│       ├── covered_call.yaml
│       └── momentum.yaml
│
├── scripts/
│   ├── start_dev.sh
│   ├── backfill_data.py
│   ├── migrate.sh
│   └── generate_openapi.py
│
├── agents/                         # CLI Agent system
│   ├── dispatcher.py               # AgentDispatcher implementation
│   ├── permissions.py              # Agent permission model
│   ├── prompts/                    # Role-specific system prompts
│   │   ├── researcher.md
│   │   ├── analyst.md
│   │   ├── risk_controller.md
│   │   └── ops.md
│   ├── tools/                      # CLI tools agents can invoke
│   │   ├── backtest_cli.py
│   │   ├── risk_bias_cli.py
│   │   └── reconcile_cli.py
│   └── outputs/                    # Agent-generated artifacts
│       ├── reports/
│       ├── candidates/
│       └── patches/
│
├── docs/plans/
├── .env.example
├── CLAUDE.md
├── STRATEGY.md
└── README.md
```

---

## Development Guidelines

### Strategy Development Workflow

1. Create new strategy in `strategies/examples/`
2. Implement `Strategy` ABC from `strategies/base.py`
3. Add config in `config/strategies/{name}.yaml`
4. Backtest thoroughly with benchmark comparison
5. Only after validation, copy to `strategies/live/`

### Type Safety Across Stack

1. Backend Pydantic models are source of truth (`models/`)
2. Run `scripts/generate_openapi.py` after model changes
3. Run `frontend/scripts/generate-types.sh` to sync frontend
4. Never manually edit `frontend/src/api/generated/`

### Protected Paths

| Path | Rule |
|------|------|
| `strategies/live/` | DO NOT modify without explicit confirmation |
| `frontend/src/api/generated/` | Auto-generated, never edit manually |
| `core/risk_manager.py` | Safety-critical, review thoroughly |

### Adding New Components

- **API endpoint**: Add to `api/routes/`, use models from `models/`
- **Risk rule**: Add to `core/risk_manager.py`, add config to YAML
- **Strategy**: Start in `examples/`, test, then promote to `live/`
- **Data model**: Edit `models/`, run migrations, regenerate types

---

## Production Systems

### 1. Environment Isolation & Trading Modes

Three distinct execution environments with graduated risk:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Backtest   │ →   │   Paper     │ →   │    Live     │
│  (历史数据)  │     │  (模拟盘)    │     │   (实盘)    │
└─────────────┘     └─────────────┘     └─────────────┘
  Historical          Real-time           Real-time
  data only           quotes              quotes
  Simulated           Simulated           Real
  broker              execution           execution
```

**Paper Trading (模拟盘) Mode:**

```python
class PaperBroker(Broker):
    """
    Uses real-time market data but simulated execution.
    Discovers issues that backtest cannot: network latency,
    API rate limits, market hours, quote staleness.
    """
    def __init__(self, market_data: MarketDataService):
        self.market_data = market_data  # Real quotes from Futu
        self.virtual_portfolio = {}      # Local position tracking
        self.virtual_orders = []         # Simulated order book
        self.slippage_model = RealisticSlippage()

    async def submit_order(self, order: Order) -> str:
        # Simulate fill against real bid/ask spread
        quote = await self.market_data.get_quote(order.symbol)
        fill_price = self._simulate_fill(order, quote)
        # ... update virtual portfolio
```

**Engine mode configuration:**

```python
class TradingEngine:
    def __init__(self, mode: Literal["backtest", "paper", "live"]):
        self.mode = mode
        self.broker = self._create_broker(mode)

    def _create_broker(self, mode: str) -> Broker:
        if mode == "backtest":
            return SimulatedBroker(historical_data)
        elif mode == "paper":
            return PaperBroker(MarketDataService())  # Real quotes, fake execution
        else:
            return FutuBroker()  # Real everything
```

**Strategy Warm-up (策略预热):**

Many strategies depend on historical indicators (moving averages, RSI, etc.). On startup, automatically backfill historical data to initialize internal state.

```python
class Strategy(ABC):
    warmup_bars: int = 0  # Override in subclass

    async def initialize(self, engine: TradingEngine):
        """Called before strategy starts receiving live data"""
        if self.warmup_bars > 0:
            historical = await engine.market_data.get_history(
                symbols=self.symbols,
                bars=self.warmup_bars
            )
            for bar in historical:
                # Feed historical data to initialize indicators
                self.on_market_data(bar, context=None, is_warmup=True)

        self._warmed_up = True

class MomentumStrategy(Strategy):
    warmup_bars = 200  # Need 200 bars for 200-day MA

    def on_market_data(self, data, context, is_warmup=False):
        self.ma_200.update(data.close)

        if is_warmup:
            return []  # Don't emit signals during warmup

        # Normal signal logic
        ...
```

---

### 2. Fault Tolerance & Self-Healing

**Multi-layer heartbeat monitoring:**

```
┌─────────────────────────────────────────────────────────┐
│                    HealthMonitor                        │
│                                                         │
│  Component          │ Check Method      │ Interval     │
│  ─────────────────────────────────────────────────────  │
│  FutuOpenD          │ TCP ping          │ 5s           │
│  Redis              │ PING command      │ 3s           │
│  PostgreSQL         │ SELECT 1          │ 10s          │
│  MarketDataService  │ Quote freshness   │ 1s           │
│  OrderManager       │ Internal heartbeat│ 5s           │
│  Each Strategy      │ Last activity     │ 30s          │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│  Health Status: HEALTHY | DEGRADED | CRITICAL          │
│                                                         │
│  On state change → trigger appropriate response         │
└─────────────────────────────────────────────────────────┘
```

**Graceful degradation (降级策略):**

```python
class SystemState(Enum):
    HEALTHY = "healthy"           # Normal operation
    DEGRADED = "degraded"         # Reduced functionality
    CRITICAL = "critical"         # Emergency mode
    OFFLINE = "offline"           # Complete shutdown

class DegradationPolicy:
    """Automatic responses to system failures"""

    rules = {
        # Condition → Action
        "market_data_stale > 30s": Action.PAUSE_NEW_SIGNALS,
        "redis_down": Action.SWITCH_TO_POSTGRES_CACHE,
        "futu_disconnected": Action.CANCEL_ALL_PENDING_ORDERS,
        "daily_loss_exceeded": Action.CLOSE_ALL_POSITIONS,
        "critical_error": Action.FULL_SHUTDOWN,
    }

    async def on_health_change(self, component: str, status: str):
        if status == "down":
            await self._execute_degradation(component)

    async def _execute_degradation(self, component: str):
        if component == "market_data":
            # Stale quotes - stop opening new positions
            await self.risk_manager.set_mode("reduce_only")
            await self.alert("Market data stale - reduce-only mode")

        elif component == "futu":
            # Broker connection lost - cancel all pending
            await self.order_manager.cancel_all_pending()
            await self.alert("Futu disconnected - orders cancelled", severity="critical")
```

**Automatic recovery:**

```python
class ConnectionManager:
    async def maintain_connection(self):
        while True:
            try:
                await self.futu_client.connect()
                self.health.mark_healthy("futu")
                await self._run_until_disconnect()
            except ConnectionLost:
                self.health.mark_down("futu")
                await self._exponential_backoff_reconnect()

    async def _exponential_backoff_reconnect(self):
        for attempt in range(self.max_retries):
            wait_time = min(2 ** attempt, 60)  # Cap at 60s
            await asyncio.sleep(wait_time)
            try:
                await self.futu_client.connect()
                await self.alert(f"Futu reconnected after {attempt + 1} attempts")
                return
            except Exception:
                continue

        # Failed all retries
        await self.degradation.trigger("futu_connection_failed")
```

---

### 3. Data Consistency & Reconciliation

**Forced reconciliation pipeline (强制对账):**

```python
class ReconciliationService:
    """
    Periodically verify local state matches broker state.
    Detect and alert on discrepancies.
    """

    async def run_reconciliation(self):
        """Run every 15 minutes during market hours"""

        # 1. Fetch authoritative state from Futu
        broker_account = await self.futu.get_account()
        broker_positions = await self.futu.get_positions()

        # 2. Fetch local state from PostgreSQL
        local_account = await self.portfolio.get_account()
        local_positions = await self.portfolio.get_positions()

        # 3. Compare and detect discrepancies
        discrepancies = self._compare(
            broker_positions,
            local_positions,
            tolerance=0.01  # Allow 1% variance for timing
        )

        if discrepancies:
            await self._handle_discrepancies(discrepancies)

    async def _handle_discrepancies(self, discrepancies: list[Discrepancy]):
        for d in discrepancies:
            if d.type == "missing_local":
                # Position exists at broker but not locally
                await self.portfolio.force_sync_position(d.broker_position)
                await self.alert(f"Synced missing position: {d.symbol}")

            elif d.type == "quantity_mismatch":
                # Quantities don't match - likely missed fill
                await self.alert(
                    f"Position mismatch: {d.symbol} "
                    f"local={d.local_qty} broker={d.broker_qty}",
                    severity="critical"
                )

            elif d.type == "phantom_local":
                # Position in local DB but not at broker
                await self.alert(
                    f"Phantom position detected: {d.symbol}",
                    severity="critical"
                )

# Schedule
reconciliation_schedule:
  market_hours: "*/15 * * * *"  # Every 15 min
  after_hours: "0 * * * *"       # Every hour
  on_startup: true               # Always on boot
```

**Atomic operation chain (原子性操作):**

```python
class OrderExecutionPipeline:
    """
    Ensure Signal → Risk → Order → Persist is atomic.
    Prevent "order sent but not recorded" scenarios.
    """

    async def execute_signal(self, signal: Signal) -> OrderResult:
        # Start database transaction
        async with self.db.transaction() as tx:
            try:
                # 1. Create order record FIRST (status=PENDING)
                order = Order.from_signal(signal)
                order.status = OrderStatus.PENDING
                await tx.orders.insert(order)

                # 2. Risk check
                risk_result = await self.risk_manager.check(signal)
                if not risk_result.approved:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = risk_result.reason
                    await tx.orders.update(order)
                    await tx.commit()
                    return OrderResult.rejected(risk_result.reason)

                # 3. Submit to broker
                order.status = OrderStatus.SUBMITTED
                await tx.orders.update(order)
                await tx.commit()  # Persist before broker call

                # 4. Broker submission (outside transaction)
                broker_order_id = await self.broker.submit(order)

                # 5. Update with broker ID
                async with self.db.transaction() as tx2:
                    order.broker_order_id = broker_order_id
                    await tx2.orders.update(order)
                    await tx2.commit()

                return OrderResult.submitted(order)

            except Exception as e:
                await tx.rollback()
                # Order was persisted as PENDING, mark as ERROR
                await self._mark_order_error(order.order_id, str(e))
                raise
```

**Write-ahead logging for critical operations:**

```python
class WriteAheadLog:
    """
    Log intent before action. On crash recovery,
    replay incomplete operations.
    """

    async def log_intent(self, operation: str, data: dict) -> str:
        """Returns wal_id for later completion/rollback"""
        entry = WALEntry(
            id=uuid4(),
            operation=operation,
            data=data,
            status="pending",
            created_at=utcnow()
        )
        await self.wal_table.insert(entry)
        return entry.id

    async def mark_complete(self, wal_id: str):
        await self.wal_table.update(wal_id, status="complete")

    async def recover_on_startup(self):
        """Called on system startup to handle incomplete operations"""
        pending = await self.wal_table.get_pending()
        for entry in pending:
            await self._replay_or_rollback(entry)
```

---

### 4. Derivative Lifecycle Management

**Contract expiration tracking:**

```python
@dataclass
class DerivativeContract:
    symbol: str
    underlying: str
    contract_type: Literal["option", "future"]
    expiry: date
    strike: float | None        # Options only
    put_call: str | None        # Options only

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry - date.today()).days

    @property
    def is_expiring_soon(self) -> bool:
        return self.days_to_expiry <= 5

class ExpirationManager:
    """Monitor and manage expiring derivatives"""

    async def check_expirations(self):
        """Run daily before market open"""
        positions = await self.portfolio.get_derivative_positions()

        for pos in positions:
            if pos.contract.days_to_expiry <= 0:
                await self._handle_expired(pos)
            elif pos.contract.days_to_expiry <= self.warning_days:
                await self._handle_expiring_soon(pos)

    async def _handle_expiring_soon(self, position: Position):
        # Alert user/strategy about upcoming expiration
        await self.alert(
            f"{position.symbol} expires in {position.contract.days_to_expiry} days",
            data={"position": position, "action_required": True}
        )

        # Notify owning strategy
        strategy = self.strategy_registry.get(position.strategy_id)
        if strategy and hasattr(strategy, "on_expiration_warning"):
            await strategy.on_expiration_warning(position)
```

**Futures roll-over (期货换月):**

```python
class FuturesRollManager:
    """
    Automate futures contract rolling before expiration.
    """

    # Configuration
    roll_days_before_expiry: int = 5
    roll_strategies: dict[str, RollStrategy] = {
        "ES": RollStrategy.CALENDAR_SPREAD,  # Roll via spread
        "NQ": RollStrategy.CLOSE_OPEN,       # Close old, open new
    }

    async def check_rolls_needed(self):
        """Run daily"""
        futures_positions = await self.portfolio.get_futures_positions()

        for pos in futures_positions:
            if pos.contract.days_to_expiry <= self.roll_days_before_expiry:
                await self._initiate_roll(pos)

    async def _initiate_roll(self, position: Position):
        underlying = position.contract.underlying
        strategy = self.roll_strategies.get(underlying, RollStrategy.CLOSE_OPEN)

        # Find next contract
        next_contract = await self._find_next_contract(position.contract)

        if strategy == RollStrategy.CALENDAR_SPREAD:
            # Execute as calendar spread for better execution
            await self._roll_via_spread(position, next_contract)
        else:
            # Simple close and open
            await self._roll_close_open(position, next_contract)

        await self.alert(
            f"Rolled {position.symbol} → {next_contract.symbol}",
            severity="info"
        )

class OptionsExpirationHandler:
    """Handle options at expiration"""

    async def handle_expiration(self, position: Position):
        contract = position.contract
        current_price = await self.market_data.get_price(contract.underlying)

        if contract.put_call == "CALL":
            itm = current_price > contract.strike
        else:
            itm = current_price < contract.strike

        if itm:
            # In-the-money: will be exercised/assigned
            await self.alert(
                f"{position.symbol} expiring ITM - expect assignment",
                severity="warning"
            )
            # Pre-create expected stock position
            await self._prepare_for_assignment(position)
        else:
            # Out-of-the-money: expires worthless
            await self.portfolio.expire_position(position)
            await self.alert(f"{position.symbol} expired worthless")
```

**Strategy interface for derivative events:**

```python
class Strategy(ABC):
    # ... existing methods ...

    def on_expiration_warning(self, position: Position, days_remaining: int):
        """
        Called when a derivative position is approaching expiration.
        Override to implement custom handling (roll, close, etc.)
        """
        pass

    def on_assignment(self, option_position: Position, stock_position: Position):
        """
        Called when an option position is assigned.
        Override to handle the resulting stock position.
        """
        pass
```

---

### 5. Structured Tracing & Observability

**Trace ID propagation:**

Every signal-to-fill chain gets a unique `trace_id` for complete audit trail.

```python
@dataclass
class TraceContext:
    trace_id: str           # Unique ID for entire flow
    parent_span_id: str     # Parent operation
    span_id: str            # Current operation
    strategy_id: str
    started_at: datetime

    @classmethod
    def new(cls, strategy_id: str) -> "TraceContext":
        trace_id = f"trc_{uuid4().hex[:16]}"
        return cls(
            trace_id=trace_id,
            parent_span_id=None,
            span_id=f"spn_{uuid4().hex[:8]}",
            strategy_id=strategy_id,
            started_at=utcnow()
        )

    def child_span(self, operation: str) -> "TraceContext":
        return TraceContext(
            trace_id=self.trace_id,
            parent_span_id=self.span_id,
            span_id=f"spn_{uuid4().hex[:8]}",
            strategy_id=self.strategy_id,
            started_at=utcnow()
        )
```

**Full context capture:**

```python
@dataclass
class SignalTrace:
    """Complete record of a signal's journey through the system"""

    trace_id: str
    timestamp: datetime

    # Signal origin
    strategy_id: str
    strategy_state: dict        # Strategy's internal state at signal time

    # Market context
    symbol: str
    quote_at_signal: Quote      # Exact quote when signal generated

    # Signal details
    signal: Signal
    signal_reason: str          # Why strategy generated this signal

    # Risk evaluation
    risk_checks: list[RiskCheckResult]
    risk_approved: bool
    risk_adjustments: dict      # Any quantity/price adjustments

    # Order execution
    order: Order | None
    broker_response: dict

    # Fill details
    fills: list[OrderFill]
    final_fill_price: float
    slippage: float             # Difference from quote_at_signal

    # Timing
    signal_to_submit_ms: int
    submit_to_fill_ms: int

class TraceRepository:
    """Store and query traces for analysis"""

    async def save_trace(self, trace: SignalTrace):
        await self.db.traces.insert(trace)

    async def get_trace(self, trace_id: str) -> SignalTrace:
        """Retrieve complete trace by ID"""
        return await self.db.traces.get(trace_id)

    async def get_traces_for_order(self, order_id: str) -> SignalTrace:
        """Find trace that generated an order"""
        return await self.db.traces.find_one(order__order_id=order_id)

    async def analyze_slippage(
        self,
        strategy_id: str,
        start: datetime,
        end: datetime
    ) -> SlippageAnalysis:
        """Aggregate slippage analysis for a strategy"""
        traces = await self.db.traces.find(
            strategy_id=strategy_id,
            timestamp__between=(start, end)
        )
        return SlippageAnalysis.from_traces(traces)
```

**API endpoint for trace retrieval:**

```python
# For AI agent analysis: "Why did this trade lose money?"

@router.get("/api/traces/{trace_id}")
async def get_full_trace(trace_id: str) -> SignalTrace:
    """
    Returns complete context of a trade:
    - Market conditions at signal time
    - Strategy state and reasoning
    - Risk checks performed
    - Execution details and slippage
    """
    return await trace_repo.get_trace(trace_id)

@router.get("/api/orders/{order_id}/trace")
async def get_order_trace(order_id: str) -> SignalTrace:
    """Get trace that generated this order"""
    return await trace_repo.get_traces_for_order(order_id)

@router.get("/api/strategies/{strategy_id}/traces")
async def get_strategy_traces(
    strategy_id: str,
    start: datetime,
    end: datetime,
    only_losses: bool = False
) -> list[SignalTrace]:
    """Get all traces for strategy analysis"""
    traces = await trace_repo.query(strategy_id, start, end)
    if only_losses:
        traces = [t for t in traces if t.realized_pnl < 0]
    return traces
```

**Structured logging format:**

```python
# All logs include trace context for correlation

import structlog

logger = structlog.get_logger()

async def process_signal(signal: Signal, trace: TraceContext):
    logger.info(
        "signal_received",
        trace_id=trace.trace_id,
        span_id=trace.span_id,
        strategy_id=signal.strategy_id,
        symbol=signal.symbol,
        action=signal.action,
        quantity=signal.quantity
    )

    # ... processing ...

    logger.info(
        "order_submitted",
        trace_id=trace.trace_id,
        span_id=trace.span_id,
        order_id=order.order_id,
        broker_order_id=order.broker_order_id
    )

# Log output (JSON for machine parsing):
# {"event": "signal_received", "trace_id": "trc_abc123", "strategy_id": "momentum", ...}
# {"event": "order_submitted", "trace_id": "trc_abc123", "order_id": "ord_xyz", ...}
```

**Dashboard trace viewer:**

```typescript
// Frontend component for viewing trade traces

interface TraceViewerProps {
  traceId: string;
}

function TraceViewer({ traceId }: TraceViewerProps) {
  const { data: trace } = useQuery(['trace', traceId], () =>
    api.get(`/traces/${traceId}`)
  );

  return (
    <div>
      <Timeline>
        <TimelineItem time={trace.timestamp} label="Signal Generated">
          <QuoteSnapshot quote={trace.quote_at_signal} />
          <StrategyState state={trace.strategy_state} />
          <SignalReason reason={trace.signal_reason} />
        </TimelineItem>

        <TimelineItem label="Risk Checks">
          {trace.risk_checks.map(check => (
            <RiskCheckResult key={check.rule} result={check} />
          ))}
        </TimelineItem>

        <TimelineItem label="Order Execution">
          <OrderDetails order={trace.order} />
          <SlippageIndicator
            expected={trace.quote_at_signal.price}
            actual={trace.final_fill_price}
          />
        </TimelineItem>
      </Timeline>
    </div>
  );
}
```

---

## CLI Agent Integration

**Core Principle: Python handles deterministic execution, CLI Agents handle fuzzy cognition and optimization.**

Agents do NOT directly issue atomic trading commands. Think of the system as a modern hedge fund where Agents serve as specialized departments, not traders.

### Agent Roles

#### 1. Researcher (研究员) — Strategy Evolution

Generates Alpha through offline analysis and optimization.

**Auto-Tuning:**
```
Scenario: MomentumStrategy has high drawdown in recent choppy market
Task:     Agent runs backtest CLI, sweeps window_size (10~60) and entry_threshold
Output:   Generates momentum_v2_candidate.py with backtest report
          (Sharpe improved by 0.2), awaits human merge
```

**Logic Repair:**
```
Scenario: Backtest logs show ZeroDivisionError
Task:     Agent reads stack trace and source code, locates bug
Output:   Applies code patch directly (for non-live code)
```

#### 2. Analyst (分析师) — Factor Production

Converts unstructured data into structured factors for Python strategies.

**Sentiment Stream:**
```
Scenario: Real-time news/social media monitoring
Task:     Read TSLA news, score sentiment (-1 to +1)
Output:   Write to Redis key `sentiment:TSLA`
          Python strategy reads this as a filter condition
```

**Event Tagging:**
```
Scenario: Identify high-risk periods (NFP release, FOMC meetings)
Output:   Write `MarketState: HIGH_VOLATILITY` to database
          Strategies automatically reduce position sizes
```

#### 3. Risk Controller (风控官) — Dynamic Constraints

Agents don't touch the brake pedal; they adjust the speed limit sign.

**Dynamic Risk Bias:**
```python
# Risk Manager has a configurable coefficient
class RiskManager:
    def __init__(self):
        self.agent_bias = 1.0  # Default, can be adjusted by agent

    async def check_signal(self, signal: Signal) -> RiskResult:
        # Agent's bias affects all position limits
        adjusted_limit = self.base_limit * self.agent_bias
        ...

# Agent analyzes VIX, macro calendar, recent drawdown
# If environment is hostile, agent executes:
#   $ aq set-bias 0.5
# Result: All position limits instantly halved
```

#### 4. Ops Engineer (运维工程师) — System Health

Handles tedious maintenance that frustrates developers.

**Intelligent Reconciliation:**
```
Scenario: Local positions don't match broker
Task:     Agent analyzes order history and settlement records
Output:   Generates SQL fix, or explains in plain language:
          "Difference is due to stock split last night,
           recommend running fix_split.py"
```

**Self-Healing:**
```
Scenario: Docker container memory overflow detected
Output:   Auto-restart service, send notification
```

---

### Sidecar Architecture

Agents run as **independent subprocesses**, not part of the trading main process.

```
┌─────────────────────────────────────────────────────────────────┐
│                    Python Trading Core                          │
│  (FastAPI, Strategy Engine, Order Manager - millisecond loop)   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            │ subprocess / async
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                     AgentDispatcher                             │
│                                                                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Researcher  │  │  Analyst    │  │ Risk Controller         │  │
│  │ Agent       │  │  Agent      │  │ Agent                   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
│                                                                 │
│  Each agent: Claude CLI subprocess with specific tools          │
└─────────────────────────────────────────────────────────────────┘
```

**AgentDispatcher implementation:**

```python
# backend/src/agents/dispatcher.py

import asyncio
import subprocess
import json

class AgentDispatcher:
    """
    Coordinates CLI agent invocations.
    Agents run in isolated subprocesses, never in the trading hot path.
    """

    def __init__(self, config: AgentConfig):
        self.config = config
        self.agent_dir = Path("agents/")

    async def invoke_agent(
        self,
        role: Literal["researcher", "analyst", "risk_controller", "ops"],
        task: str,
        context: dict,
        timeout: int = 300
    ) -> AgentResult:
        """
        Invoke a CLI agent with specific task and context.
        Returns structured result, never raw trading commands.
        """

        # Prepare context file for agent
        context_file = self._write_context(context)

        # Build CLI command
        cmd = [
            "claude",
            "--prompt", self._build_prompt(role, task),
            "--context", str(context_file),
            "--output-format", "json"
        ]

        # Run in subprocess (isolated from trading loop)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout
            )
            return self._parse_result(stdout, role)
        except asyncio.TimeoutError:
            proc.kill()
            return AgentResult(success=False, error="Agent timeout")

    def _build_prompt(self, role: str, task: str) -> str:
        """Load role-specific system prompt + task"""
        role_prompt = (self.agent_dir / f"{role}_prompt.md").read_text()
        return f"{role_prompt}\n\n## Current Task\n{task}"

    async def schedule_periodic(
        self,
        role: str,
        task: str,
        interval_seconds: int
    ):
        """Run agent task on schedule (e.g., hourly risk assessment)"""
        while True:
            context = await self._gather_context(role)
            result = await self.invoke_agent(role, task, context)
            await self._apply_result(result)
            await asyncio.sleep(interval_seconds)
```

---

### Enhanced Context Snapshots

Agents need rich context to understand what happened. Extend `SignalTrace` with full snapshots.

**Database schema addition:**

```sql
ALTER TABLE signal_traces ADD COLUMN context_snapshot JSONB;
```

**Snapshot contents:**

```python
@dataclass
class ContextSnapshot:
    """Full context captured at signal time for agent analysis"""

    # Market snapshot
    market: MarketSnapshot
    #   bid, ask, spread, volume, order_book_depth

    # News snapshot (last 1 hour)
    news: list[NewsItem]
    #   headline, source, sentiment_score, timestamp

    # Strategy internal state
    indicators: dict[str, float]
    #   e.g., {"RSI": 85, "MA20": 150.5, "MACD_hist": 0.23}

    # Portfolio context
    portfolio: PortfolioSnapshot
    #   current positions, exposure, unrealized P&L

    # Risk state
    risk: RiskSnapshot
    #   current bias, breached limits, margin usage

# Capture on every signal
async def capture_context(signal: Signal) -> ContextSnapshot:
    return ContextSnapshot(
        market=await market_data.get_snapshot(signal.symbol),
        news=await news_service.get_recent(signal.symbol, hours=1),
        indicators=signal.strategy.get_indicator_state(),
        portfolio=await portfolio.get_snapshot(),
        risk=await risk_manager.get_snapshot()
    )
```

---

### Integration Points

#### A. Pre-Trade: Risk Bias Adjustment

```python
# Cron: Every hour during market hours

async def update_risk_bias():
    context = {
        "vix": await market_data.get_quote("VIX"),
        "macro_calendar": await calendar.get_upcoming_events(days=3),
        "recent_drawdown": await portfolio.get_drawdown(days=5),
        "current_exposure": await portfolio.get_exposure()
    }

    result = await dispatcher.invoke_agent(
        role="risk_controller",
        task="Analyze current market conditions and recommend risk bias (0.0-1.0)",
        context=context
    )

    if result.success and 0.0 <= result.bias <= 1.0:
        await redis.set("global_risk_bias", result.bias)
        logger.info(f"Risk bias updated to {result.bias}: {result.reasoning}")

# Risk Manager reads this before every check
class RiskManager:
    async def get_agent_bias(self) -> float:
        bias = await redis.get("global_risk_bias")
        return float(bias) if bias else 1.0
```

#### B. Post-Trade: Loss Analysis

```python
# Triggered on significant losses or rejected orders

async def analyze_loss(trace: SignalTrace):
    if trace.realized_pnl > -LOSS_THRESHOLD:
        return

    result = await dispatcher.invoke_agent(
        role="researcher",
        task="Analyze why this trade lost money and suggest improvements",
        context={
            "trace": trace.to_dict(),
            "context_snapshot": trace.context_snapshot,
            "similar_trades": await find_similar_traces(trace, limit=10)
        }
    )

    # Generate markdown report
    report = AgentReport(
        trace_id=trace.trace_id,
        analysis=result.analysis,
        suggestions=result.suggestions,
        generated_at=utcnow()
    )

    await report_repo.save(report)
    await notify.send_to_dashboard(report)
    await notify.send_to_telegram(report.summary)
```

#### C. Offline: Strategy Optimization

```python
# Triggered: Weekends or after market close

async def optimize_strategy(strategy_id: str):
    # Get recent performance
    performance = await backtest.run(
        strategy_id=strategy_id,
        period="last_30_days"
    )

    if performance.sharpe_ratio >= TARGET_SHARPE:
        return  # No optimization needed

    result = await dispatcher.invoke_agent(
        role="researcher",
        task=f"""
        Strategy {strategy_id} underperforming (Sharpe: {performance.sharpe_ratio}).
        Analyze and suggest parameter improvements.
        Test suggestions via backtesting CLI.
        If improvement found, create candidate file.
        """,
        context={
            "strategy_code": read_strategy_file(strategy_id),
            "performance": performance.to_dict(),
            "market_regime": await analyze_market_regime("last_30_days")
        },
        timeout=1800  # 30 min for thorough analysis
    )

    if result.candidate_file:
        # Agent created new strategy file, notify for review
        await notify.send(
            f"Strategy optimization complete for {strategy_id}. "
            f"Candidate file: {result.candidate_file}. "
            f"Expected Sharpe improvement: {result.expected_improvement}. "
            f"Please review and merge."
        )
```

---

### Safety Red Lines (Air Gap)

**Hard isolation to prevent agent hallucination disasters:**

| Rule | Implementation |
|------|----------------|
| **Read-only DB access** | Agent subprocess connects with read-only credentials (except log tables) |
| **Parameters, not commands** | Agent outputs `{"bias": 0.8}` or code patches, NEVER `futu.place_order()` |
| **Human-in-the-loop** | Code modifications → Git PR or new file, requires human merge |
| **Sandboxed execution** | Agent runs in container with no network access to broker API |
| **Audit trail** | All agent invocations logged with full input/output |

**Permission model:**

```python
class AgentPermissions:
    """Define what each agent role can do"""

    RESEARCHER = AgentPerms(
        can_read=["strategies/*", "backtest/*", "logs/*"],
        can_write=["strategies/examples/*", "agents/outputs/*"],
        can_execute=["backtest", "pytest"],
        cannot=["strategies/live/*", "broker/*", "core/*"]
    )

    ANALYST = AgentPerms(
        can_read=["market_data/*", "news/*"],
        can_write=["redis:sentiment:*", "redis:events:*"],
        can_execute=[],
        cannot=["strategies/*", "orders/*"]
    )

    RISK_CONTROLLER = AgentPerms(
        can_read=["portfolio/*", "risk/*", "market_data/*"],
        can_write=["redis:global_risk_bias"],
        can_execute=[],
        cannot=["strategies/*", "orders/*", "broker/*"]
    )

    OPS = AgentPerms(
        can_read=["*"],
        can_write=["logs/*", "agents/outputs/*"],
        can_execute=["docker", "systemctl"],
        cannot=["strategies/live/*", "broker/*"]
    )
```

---

### Project Structure Additions

```
aq_trading/
├── agents/
│   ├── dispatcher.py           # AgentDispatcher implementation
│   ├── permissions.py          # Permission model
│   ├── prompts/
│   │   ├── researcher.md       # System prompt for researcher role
│   │   ├── analyst.md          # System prompt for analyst role
│   │   ├── risk_controller.md  # System prompt for risk controller
│   │   └── ops.md              # System prompt for ops engineer
│   ├── tools/                  # CLI tools agents can invoke
│   │   ├── backtest_cli.py
│   │   ├── risk_bias_cli.py
│   │   └── reconcile_cli.py
│   └── outputs/                # Agent-generated artifacts
│       ├── reports/
│       ├── candidates/
│       └── patches/
```

---

## Operational Concerns & Mitigations

### 1. Data Bloat Prevention

**Problem:** ContextSnapshot with OrderBook depth and JSONB is storage-intensive. High-frequency strategies generating signals per second will bloat PostgreSQL rapidly.

**Mitigation: Tiered Retention Policy**

```python
# config/retention.yaml

retention:
  signal_traces:
    # Executed trades: keep forever (audit requirement)
    filled_orders: "permanent"

    # Rejected signals: short retention
    rejected_signals: "7 days"

    # Unfilled/cancelled: medium retention
    cancelled_orders: "30 days"

  context_snapshots:
    # Full snapshot: expensive, short retention
    full_snapshot: "24 hours"

    # Compressed summary: longer retention
    summary_snapshot: "90 days"

  historical_prices:
    # 1-minute bars: 1 year
    ohlcv_1m: "365 days"

    # Daily bars: permanent
    ohlcv_1d: "permanent"

# TimescaleDB compression + retention
class RetentionManager:
    async def setup_policies(self):
        # Enable compression for older data
        await self.db.execute("""
            SELECT add_compression_policy('signal_traces', INTERVAL '7 days');
        """)

        # Auto-drop old rejected signals
        await self.db.execute("""
            SELECT add_retention_policy('signal_traces',
                INTERVAL '7 days',
                if_not_exists => true
            ) WHERE status = 'rejected';
        """)

    async def archive_full_snapshots(self):
        """
        Daily job: compress full snapshots to summaries
        """
        old_snapshots = await self.db.query("""
            SELECT * FROM context_snapshots
            WHERE created_at < NOW() - INTERVAL '24 hours'
            AND archived = false
        """)

        for snapshot in old_snapshots:
            summary = self._compress_to_summary(snapshot)
            await self.db.update_snapshot(snapshot.id, summary, archived=True)
```

**Snapshot compression:**

```python
def compress_snapshot(full: ContextSnapshot) -> SummarySnapshot:
    """Reduce storage by keeping only essential data"""
    return SummarySnapshot(
        # Keep: critical price info
        bid=full.market.bid,
        ask=full.market.ask,
        price=full.market.price,

        # Keep: key indicators only
        indicators={
            k: v for k, v in full.indicators.items()
            if k in ["RSI", "MACD", "MA20"]  # Top 3 only
        },

        # Discard: full order book depth
        # Discard: full news list (keep count only)
        news_count=len(full.news),

        # Discard: full portfolio snapshot
        # Keep: just exposure at signal time
        exposure=full.portfolio.total_exposure
    )
```

---

### 2. Agent Latency Isolation

**Problem:** CLI agent calls (subprocess spawn + LLM inference) take seconds. If trading path waits for agent, it's unusable.

**Wrong pattern:**
```
Signal → Wait for Agent risk check → Submit order (seconds delay!)
```

**Correct pattern:**
```
Agent loop (async) → Updates Redis every N minutes
Signal → Read Redis (microseconds) → Submit order
```

**Implementation:**

```python
class AgentScheduler:
    """
    Agents run on their own schedules, NEVER blocking trading.
    Results are written to Redis for instant access.
    """

    async def start(self):
        # Risk controller: runs every 15 minutes
        asyncio.create_task(self._risk_loop())

        # Analyst: runs every 5 minutes
        asyncio.create_task(self._sentiment_loop())

    async def _risk_loop(self):
        while True:
            try:
                # This takes 10-30 seconds, but runs in background
                result = await self.dispatcher.invoke_agent(
                    role="risk_controller",
                    task="Calculate current risk bias"
                )

                # Write to Redis (instant)
                await redis.set("global_risk_bias", result.bias)
                await redis.set("risk_bias_updated_at", utcnow().isoformat())

            except Exception as e:
                logger.error(f"Risk agent failed: {e}")
                # On failure, use conservative default
                await redis.set("global_risk_bias", 0.5)

            await asyncio.sleep(900)  # 15 minutes

# Trading path: NEVER waits for agent
class RiskManager:
    async def check_signal(self, signal: Signal) -> RiskResult:
        # Microsecond Redis read, never blocks
        bias = float(await redis.get("global_risk_bias") or "1.0")

        # Check staleness
        updated_at = await redis.get("risk_bias_updated_at")
        if self._is_stale(updated_at, max_age_minutes=30):
            # Stale bias → use conservative default
            bias = 0.5
            await self.alert("Risk bias stale, using default 0.5")

        # Apply bias to limits
        adjusted_limit = self.base_limit * bias
        ...
```

**Critical rule:** Trading main loop has NO `await agent.*` calls. Ever.

---

### 3. DevOps Robustness

**Problem:** Too many services - FastAPI, React, Postgres, Redis, TimescaleDB, FutuOpenD (VNC), multiple Agent subprocesses. Docker Compose becomes unwieldy.

**Mitigation: Layered startup with health gates**

```makefile
# Makefile

.PHONY: start stop status logs

# Start infrastructure first, then services
start:
	@echo "Starting infrastructure..."
	docker-compose up -d postgres redis
	@$(MAKE) wait-for-infra

	@echo "Starting FutuOpenD..."
	docker-compose up -d futu-opend
	@$(MAKE) wait-for-futu

	@echo "Starting backend..."
	docker-compose up -d backend
	@$(MAKE) wait-for-backend

	@echo "Starting frontend..."
	docker-compose up -d frontend

	@echo "All services started. Dashboard: http://localhost:3000"

wait-for-infra:
	@echo "Waiting for Postgres..."
	@until docker-compose exec -T postgres pg_isready; do sleep 1; done
	@echo "Waiting for Redis..."
	@until docker-compose exec -T redis redis-cli ping | grep PONG; do sleep 1; done

wait-for-futu:
	@echo "Waiting for FutuOpenD API..."
	@timeout 60 bash -c 'until nc -z localhost 11111; do sleep 2; done' || \
		(echo "ERROR: FutuOpenD not responding. Check VNC at http://localhost:6080" && exit 1)

wait-for-backend:
	@echo "Waiting for backend health..."
	@until curl -sf http://localhost:8000/health; do sleep 2; done

# Health check all services
status:
	@echo "=== Service Status ==="
	@docker-compose ps
	@echo ""
	@echo "=== Health Checks ==="
	@curl -sf http://localhost:8000/health | jq . || echo "Backend: DOWN"
	@docker-compose exec -T redis redis-cli ping || echo "Redis: DOWN"
	@docker-compose exec -T postgres pg_isready || echo "Postgres: DOWN"
	@nc -z localhost 11111 && echo "FutuOpenD: UP" || echo "FutuOpenD: DOWN"

# Tail all logs
logs:
	docker-compose logs -f --tail=100

# FutuOpenD manual intervention helper
futu-vnc:
	@echo "Opening FutuOpenD VNC in browser..."
	@echo "Use this when FutuOpenD needs manual login/verification"
	open http://localhost:6080 || xdg-open http://localhost:6080
```

**FutuOpenD monitoring & alerts:**

```python
# backend/src/core/futu_monitor.py

class FutuOpenDMonitor:
    """
    FutuOpenD requires special monitoring because:
    - It needs manual verification code sometimes
    - Network issues cause disconnects
    - Upgrades require re-login
    """

    async def monitor_loop(self):
        while True:
            status = await self._check_futu_status()

            if status == FutuStatus.DISCONNECTED:
                await self._handle_disconnect()

            elif status == FutuStatus.NEEDS_VERIFICATION:
                await self._alert_manual_intervention()

            await asyncio.sleep(30)

    async def _alert_manual_intervention(self):
        """Send urgent alert when human action required"""
        message = (
            "🚨 FutuOpenD requires manual verification!\n"
            "Open VNC: http://your-server:6080\n"
            "Enter verification code to resume trading."
        )

        # Multiple channels for reliability
        await asyncio.gather(
            self.telegram.send(message, priority="urgent"),
            self.email.send("FutuOpenD Alert", message),
            self.dashboard.push_alert(message, severity="critical")
        )

        # Trigger degradation
        await self.degradation.enter_mode("futu_unavailable")
```

**Startup validation script:**

```bash
#!/bin/bash
# scripts/validate_startup.sh

set -e

echo "=== Pre-flight Checks ==="

# 1. Check disk space
DISK_USAGE=$(df -h / | awk 'NR==2 {print $5}' | tr -d '%')
if [ "$DISK_USAGE" -gt 85 ]; then
    echo "WARNING: Disk usage at ${DISK_USAGE}%"
fi

# 2. Check required ports are free
for port in 3000 8000 5432 6379 11111 6080; do
    if lsof -i:$port > /dev/null 2>&1; then
        echo "ERROR: Port $port already in use"
        exit 1
    fi
done

# 3. Check .env file exists
if [ ! -f .env ]; then
    echo "ERROR: .env file missing. Copy from .env.example"
    exit 1
fi

# 4. Validate required env vars
source .env
for var in FUTU_HOST POSTGRES_URL REDIS_URL; do
    if [ -z "${!var}" ]; then
        echo "ERROR: $var not set in .env"
        exit 1
    fi
done

echo "=== All checks passed ==="
```

---

### 4. Overfitting Prevention

**Problem:** Auto-tuning agent optimizing for Sharpe ratio will overfit to historical data. Parameters that look great in backtest fail in live trading.

**Mitigation: Mandatory out-of-sample testing + reasoning requirements**

**Researcher agent prompt additions:**

```markdown
# agents/prompts/researcher.md

## CRITICAL: Overfitting Prevention Rules

You MUST follow these rules when optimizing strategy parameters:

### 1. Walk-Forward Validation (必须使用向前验证)

Never test on full historical data. Always use walk-forward:

```
Training period: 70% of data
Validation period: 15% of data (tune here)
Test period: 15% of data (final check, NEVER tune on this)
```

If performance degrades >20% from validation to test, REJECT the optimization.

### 2. Parameter Stability Check (参数稳定性检验)

Before recommending a parameter change, verify it's not a local optimum:

- Test parameter ± 10% and ± 20%
- If performance drops sharply with small changes, the parameter is UNSTABLE
- Only recommend STABLE parameters that work across a range

### 3. Regime Awareness (市场环境意识)

Test parameters across different market regimes:
- Bull market periods
- Bear market periods
- High volatility (VIX > 25)
- Low volatility (VIX < 15)

If parameters only work in one regime, WARN about this limitation.

### 4. Explain the "Why" (必须解释原因)

For every parameter change, you MUST explain:
- WHY this parameter value makes sense (logic, not just numbers)
- WHAT market behavior it's trying to capture
- WHEN this parameter might fail

Bad: "Changed window from 20 to 35 because Sharpe improved by 0.3"
Good: "Changed window from 20 to 35 because recent market shows longer
       trend persistence. 35-day window captures quarterly earnings cycles.
       This may underperform in rapid reversal environments."

### 5. Mandatory Fields in Optimization Report

```json
{
  "recommendation": "change window_size from 20 to 35",
  "sharpe_improvement": 0.3,

  "validation": {
    "training_sharpe": 1.8,
    "validation_sharpe": 1.6,
    "test_sharpe": 1.5,
    "performance_degradation": "6% (acceptable)"
  },

  "stability": {
    "param_minus_20pct": {"sharpe": 1.4},
    "param_minus_10pct": {"sharpe": 1.55},
    "param_plus_10pct": {"sharpe": 1.52},
    "param_plus_20pct": {"sharpe": 1.45},
    "stability_verdict": "STABLE"
  },

  "regime_analysis": {
    "bull_market": {"sharpe": 1.8, "note": "strong"},
    "bear_market": {"sharpe": 0.9, "note": "underperforms"},
    "high_vol": {"sharpe": 1.2},
    "low_vol": {"sharpe": 1.6}
  },

  "reasoning": "Longer window captures quarterly cycles...",

  "risk_disclosure": "May underperform in rapid reversal environments.
                      Consider reducing allocation during bear markets."
}
```

If you cannot fill all these fields, DO NOT recommend the optimization.
```

**Backend validation:**

```python
class OptimizationValidator:
    """Validate agent optimization recommendations before applying"""

    def validate(self, report: OptimizationReport) -> ValidationResult:
        errors = []

        # 1. Check out-of-sample degradation
        degradation = (
            report.validation.training_sharpe -
            report.validation.test_sharpe
        ) / report.validation.training_sharpe

        if degradation > 0.20:
            errors.append(
                f"Excessive degradation: {degradation:.1%} from training to test. "
                "Likely overfitting."
            )

        # 2. Check parameter stability
        if report.stability.stability_verdict != "STABLE":
            errors.append("Parameter is unstable. Small changes cause large performance swings.")

        # 3. Check regime coverage
        min_regime_sharpe = min(
            report.regime_analysis.bull_market.sharpe,
            report.regime_analysis.bear_market.sharpe
        )
        if min_regime_sharpe < 0.5:
            errors.append(
                f"Poor performance in some regimes (min Sharpe: {min_regime_sharpe}). "
                "Parameter may not generalize."
            )

        # 4. Check reasoning exists
        if len(report.reasoning) < 100:
            errors.append("Insufficient reasoning provided. Explain the 'why'.")

        if errors:
            return ValidationResult(
                approved=False,
                errors=errors,
                recommendation="Manual review required before applying."
            )

        return ValidationResult(approved=True)
```
