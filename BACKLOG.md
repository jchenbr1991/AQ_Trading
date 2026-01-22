# BACKLOG.md

Implementation backlog for AQ Trading. Check items as completed.

---

## Phase 1: Minimum Viable Trading System

### Infrastructure Setup
- [ ] Initialize Python backend (`backend/pyproject.toml`, FastAPI app)
- [ ] Initialize TypeScript frontend (`frontend/package.json`, Vite + React)
- [ ] Docker Compose for Postgres, Redis, FutuOpenD
- [ ] Alembic migration setup
- [ ] Environment config (`config/default.yaml`, `.env.example`)

### Portfolio Manager (`core/portfolio.py`)
- [ ] Account model and sync with Futu
- [ ] Position model with strategy tagging
- [ ] Transaction ledger
- [ ] `sync_with_broker()` implementation
- [ ] `record_fill()` implementation
- [ ] `get_positions(strategy_id)` filtering

### Strategy Engine (`strategies/`)
- [ ] Strategy ABC (`base.py`)
- [ ] StrategyContext with read-only portfolio view (`context.py`)
- [ ] Signal dataclass (`signals.py`)
- [ ] Strategy registry and discovery (`registry.py`)
- [ ] One example strategy (`examples/momentum.py`)

### Risk Manager (`core/risk_manager.py`)
- [ ] Position limits check
- [ ] Portfolio limits check
- [ ] Daily loss limit check
- [ ] Kill switch mechanism
- [ ] Risk config loading from YAML

### Order Manager (`core/order_manager.py`)
- [ ] Order model and lifecycle states
- [ ] Signal → Order conversion
- [ ] Futu API submission (`broker/futu/trading.py`)
- [ ] Order tracking and fill handling
- [ ] Portfolio update on fill
- [ ] Strategy callback on fill

### Market Data (`core/market_data.py`)
- [ ] Futu quote subscription (`broker/futu/quotes.py`)
- [ ] Redis caching for live quotes
- [ ] Quote distribution to strategies

### Reconciliation (`core/reconciliation.py`)
- [ ] Periodic broker position fetch
- [ ] Local vs broker comparison
- [ ] Discrepancy detection and alerting

### Paper Trading (`broker/paper.py`)
- [ ] Paper broker with simulated execution
- [ ] Uses real quotes, virtual portfolio
- [ ] Trading mode toggle (live/paper)

### Basic Dashboard
- [ ] Frontend scaffold (React + Tailwind)
- [ ] REST API routes (`api/routes/portfolio.py`, `orders.py`, `strategies.py`)
- [ ] WebSocket server (`api/websocket.py`)
- [ ] Positions table view
- [ ] P&L display
- [ ] Strategy pause/resume controls
- [ ] Kill switch button

### DevOps
- [ ] `Makefile` with start/stop/status targets
- [ ] `scripts/start_dev.sh`
- [ ] Health check endpoint (`/health`)

---

## Phase 2: Enhanced Analytics & Testing

### Backtesting Engine (`backtest/`)
- [ ] BacktestEngine with event loop (`engine.py`)
- [ ] SimulatedBroker with slippage models (`simulated_broker.py`)
- [ ] BacktestResult with performance metrics (`results.py`)
- [ ] Benchmark comparison (alpha, beta, Sharpe vs SPY)
- [ ] Equity curve and drawdown series

### Strategy Warm-up
- [ ] `warmup_bars` property on Strategy ABC
- [ ] Historical data backfill on strategy start
- [ ] `is_warmup` flag to suppress signals during init

### Trace System (`core/tracing.py`)
- [ ] TraceContext with trace_id propagation
- [ ] SignalTrace dataclass with full context
- [ ] ContextSnapshot capture at signal time
- [ ] Trace repository (`db/repositories/trace_repo.py`)
- [ ] API endpoint for trace retrieval (`api/routes/traces.py`)

### Health Monitoring (`core/health_monitor.py`)
- [ ] Heartbeat checks for Futu, Redis, Postgres
- [ ] Component health status aggregation
- [ ] Alert on health degradation
- [ ] Dashboard health page

### Retention Policies (`db/retention.py`)
- [ ] TimescaleDB compression policy setup
- [ ] Tiered retention (permanent for fills, 7d for rejected)
- [ ] Snapshot compression job (full → summary)

### Dashboard Enhancements
- [ ] Backtest runner page
- [ ] Backtest results visualization (equity curve chart)
- [ ] Trace viewer component
- [ ] Slippage analysis display
- [ ] Health status page

### Type Generation
- [ ] OpenAPI schema export (`scripts/generate_openapi.py`)
- [ ] Frontend type generation with Orval (`frontend/scripts/generate-types.sh`)

---

## Phase 3: Advanced Features

### Options Lifecycle (`core/expiration_manager.py`)
- [ ] Contract expiration tracking
- [ ] Expiration warning alerts
- [ ] Assignment/exercise handling
- [ ] Strategy `on_expiration_warning()` callback

### Futures Roll-over
- [ ] Next contract identification
- [ ] Roll-over strategies (spread vs close/open)
- [ ] Automatic roll execution

### Greeks Monitoring
- [ ] Portfolio delta/theta/vega calculation
- [ ] Greeks limits in Risk Manager
- [ ] Dashboard Greeks display

### CLI Agent System (`agents/`)
- [ ] AgentDispatcher implementation (`dispatcher.py`)
- [ ] Permission model (`permissions.py`)
- [ ] Agent prompts (`prompts/researcher.md`, etc.)
- [ ] Agent scheduling (background loops)
- [ ] Redis integration for agent outputs

### Risk Controller Agent
- [ ] Risk bias calculation task
- [ ] VIX + macro calendar analysis
- [ ] `global_risk_bias` Redis updates
- [ ] Risk Manager reads agent bias

### Researcher Agent
- [ ] Parameter optimization task
- [ ] Walk-forward validation enforcement
- [ ] Stability testing
- [ ] Candidate file generation
- [ ] Overfitting prevention validation

### Analyst Agent
- [ ] Sentiment scoring from news
- [ ] Event tagging (FOMC, NFP, etc.)
- [ ] Redis factor updates (`sentiment:*`)

### Ops Agent
- [ ] Intelligent reconciliation analysis
- [ ] Auto-restart on failures
- [ ] Markdown report generation

### Graceful Degradation
- [ ] Degradation policy config (`config/degradation.yaml`)
- [ ] Automatic mode switching on failures
- [ ] "Reduce-only" mode implementation

---

## Ongoing / Maintenance

- [ ] Additional example strategies
- [ ] Performance optimization
- [ ] Documentation improvements
- [ ] Test coverage expansion
- [ ] Security audit

---

## Notes

- Complete Phase N before starting Phase N+1
- Mark items with `[x]` when done
- Add sub-items as needed during implementation
