# BACKLOG.md

Implementation backlog for AQ Trading. Track development phases and progress.

---

## Phase 1: Minimum Viable Trading System [COMPLETED]

| Component | Status | PR | Notes |
|-----------|--------|-----|-------|
| Infrastructure Setup | Done | - | FastAPI, React, configs |
| Portfolio Manager | Done | #1 | Position tracking, account sync |
| Strategy Engine | Done | #2 | Base strategy, context, signals |
| Risk Manager | Done | #3 | Position/portfolio limits, loss limits |
| Order Manager | Done | #4 | Order lifecycle, broker integration |
| Market Data Service | Done | #4 | Quote subscription, caching |
| Reconciliation Service | Done | #4 | Broker sync, discrepancy detection |
| Paper Trading | Done | #4 | PaperBroker with simulated execution |
| Basic Dashboard | Done | #5 | Positions, P&L, kill switch, alerts |

**Exit Criteria Met:** Can run a simple strategy in paper mode, track positions, and manually intervene via dashboard.

---

## Phase 2: Enhanced Analytics & Testing [COMPLETED]

**Development Approach:** Vertical slices - end-to-end features delivering working functionality incrementally.

### Slice 2.1: Health Monitoring [COMPLETED]

**Goal:** Track component health (Redis, PostgreSQL, MarketData) and display on dashboard.

| Task | Status | Description |
|------|--------|-------------|
| Health Models | Done | ComponentStatus, HealthStatus, SystemHealth |
| Health Checkers | Done | Redis, MarketData health checkers |
| HealthMonitor Service | Done | Aggregate concurrent health checks |
| Health API Endpoints | Done | `/api/health/detailed`, `/api/health/component/{name}` |
| Frontend Health Types | Done | TypeScript types |
| useHealth Hook | Done | TanStack Query hook with 10s refetch |
| HealthStatusBadge | Done | Color-coded status indicator |
| ComponentHealthCard | Done | Individual component display |
| HealthPage | Done | `/health` route with navigation |
| Backend Initialization | Done | Wire checkers on startup |
| Integration Tests | Done | E2E health tests |

**Plan:** `docs/plans/2026-01-25-health-monitoring.md` | **PR:** #6

---

### Slice 2.2: Backtest Engine + Strategy Warm-up [COMPLETED]

**Goal:** Run strategies against historical data with warm-up for indicator initialization.

| Task | Status | Description |
|------|--------|-------------|
| Bar Model | Done | Frozen dataclass with timezone-aware timestamp |
| Trade Model | Done | Trade tracking with slippage/commission breakdown |
| BacktestConfig | Done | Configuration with fill/slippage/commission models |
| BacktestResult | Done | Performance metrics, equity curve, warm-up tracking |
| BacktestPortfolio | Done | Long-only, no-leverage position tracking |
| SimulatedFillEngine | Done | Next-bar-open fill with fixed BPS slippage |
| MetricsCalculator | Done | Sharpe, max drawdown, win rate with edge cases |
| CSVBarLoader | Done | Protocol-based bar loading from CSV |
| Strategy Warm-up | Done | `warmup_bars` property on BaseStrategy |
| BacktestEngine | Done | Event loop with no-lookahead-bias guarantee |
| Backtest API | Done | POST `/api/backtest` endpoint |
| Frontend Types | Done | TypeScript types for backtest |
| useBacktest Hook | Done | TanStack Query mutation hook |
| BacktestForm | Done | Configuration form with validation |
| BacktestResults | Done | Metrics display with equity chart (Recharts) |
| BacktestPage | Done | `/backtest` route with form + results |
| Backend Exports | Done | Clean module exports |

**Plan:** `docs/plans/2026-01-25-backtest-engine.md` | **PR:** #8

---

### Slice 2.3: Benchmark Comparison [COMPLETED]

**Goal:** Compare strategy performance against SPY/HSI benchmarks.

| Task | Status | Description |
|------|--------|-------------|
| Math Utilities | Done | calculate_returns, OLS regression, covariance |
| BenchmarkComparison | Done | Frozen dataclass for all metrics |
| BenchmarkBuilder | Done | buy_and_hold equity curve from bars |
| BenchmarkMetrics | Done | OLS alpha/beta, IR, sortino, capture ratios |
| BacktestConfig | Done | Optional benchmark_symbol field |
| BacktestResult | Done | Nested benchmark comparison |
| Engine Integration | Done | Load benchmark, compute metrics |
| API Schema | Done | Request/response with benchmark |
| Frontend Types | Done | TypeScript interfaces |
| BacktestForm | Done | Benchmark symbol input (default SPY) |
| BacktestResults | Done | Benchmark metrics display section |
| EquityChart | Done | Benchmark overlay support |
| Module Exports | Done | Clean exports |

**Plan:** `docs/plans/2026-01-25-benchmark-comparison.md` | **PR:** #11

---

### Slice 2.4: Trace Viewer + Slippage Analysis [COMPLETED]

**Goal:** Signal-to-fill audit trail with execution quality analysis.

| Task | Status | Description |
|------|--------|-------------|
| Trace Data Models | Done | BarSnapshot, PortfolioSnapshot, StrategySnapshot, SignalTrace |
| TraceBuilder | Done | Factory for creating/completing traces |
| BacktestResult.traces | Done | Traces field added to result |
| Engine Integration | Done | Capture traces during backtest |
| API Schemas | Done | Trace response schemas |
| Frontend Types | Done | TypeScript interfaces |
| TraceTable | Done | Display traces in table |
| SlippageStats | Done | Aggregate slippage statistics |
| BacktestResults Integration | Done | Trace display in results |
| Module Exports | Done | Clean exports |

**Plan:** `docs/plans/2026-01-25-trace-viewer.md` | **PR:** #13

---

### Slice 2.5: Retention Policies [COMPLETED]

**Goal:** Manage data lifecycle to prevent storage bloat.

| Task | Status | Description |
|------|--------|-------------|
| TimescaleDB Setup | Done | Extension + hypertable migration |
| Data Migration Scripts | Done | Maintenance window SQL/Python scripts |
| Validation Checklist | Done | Post-migration verification script |
| Cleanup Migration | Done | Drop old table after validation |
| StorageMonitor Service | Done | Table stats, compression info |
| Storage API | Done | `/api/storage` endpoints |
| Storage Dashboard | Done | Frontend `/storage` page |
| Module Exports | Done | Clean exports |

**Plan:** `docs/plans/2026-01-25-retention-policies.md` | **PR:** #14

---

**Phase 2 Exit Criteria Met:** Can backtest strategies with benchmark comparison, analyze trade execution quality, trust system health, monitor storage.

---

## Phase 3: Advanced Features [NOT STARTED]

### Options & Futures Lifecycle

| Task | Status | Description |
|------|--------|-------------|
| Expiration Tracking | Pending | Days to expiry monitoring |
| Expiration Alerts | Pending | Warning before expiration |
| Assignment Handling | Pending | ITM option exercise |
| Futures Roll-over | Pending | Automatic contract rolling |
| Greeks Monitoring | Pending | Portfolio delta/theta/vega |

---

### CLI Agent System

| Task | Status | Description |
|------|--------|-------------|
| AgentDispatcher | Pending | Subprocess agent invocation |
| Permission Model | Pending | Read/write/execute boundaries |
| Risk Controller Agent | Pending | Dynamic risk bias |
| Researcher Agent | Pending | Parameter optimization |
| Analyst Agent | Pending | Sentiment scoring |
| Ops Agent | Pending | Intelligent reconciliation |

---

### Production Hardening

| Task | Status | Description |
|------|--------|-------------|
| Graceful Degradation | Pending | Auto failover policies |
| Enhanced Alerts | Pending | Multi-channel notifications |
| Audit Logging | Pending | Compliance trail |

---

**Phase 3 Exit Criteria:** Can trade options/futures with lifecycle management, leverage agents for optimization without manual intervention.

---

## Legend

| Status | Meaning |
|--------|---------|
| Pending | Not started |
| In Progress | Currently being worked on |
| Done | Completed and merged |
| Blocked | Waiting on dependency |

---

## Notes

- **Vertical slices:** Each slice delivers end-to-end working functionality
- **TDD:** All code written test-first
- **Complete Phase N before starting Phase N+1**
- **Mark items as done when code is merged**
