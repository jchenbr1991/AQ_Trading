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

## Phase 2: Enhanced Analytics & Testing [IN PROGRESS]

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

### Slice 2.2: Backtest Engine + Strategy Warm-up [CURRENT]

**Goal:** Run strategies against historical data with warm-up for indicator initialization.

| Task | Status | Description |
|------|--------|-------------|
| Strategy Warm-up | Pending | `warmup_bars` property, historical backfill |
| SimulatedBroker | Pending | Order execution with slippage models |
| BacktestEngine | Pending | Event-based replay loop |
| BacktestResult Model | Pending | Performance metrics dataclass |
| Backtest API | Pending | Trigger and retrieve results |
| Frontend Backtest Page | Pending | Run backtests, view results |

**Plan:** Not yet created

---

### Slice 2.3: Benchmark Comparison

**Goal:** Compare strategy performance against SPY/HSI benchmarks.

| Task | Status | Description |
|------|--------|-------------|
| Benchmark Data | Pending | Fetch SPY/HSI historical data |
| Alpha/Beta | Pending | Excess return, correlation |
| Sharpe/Sortino | Pending | Risk-adjusted returns |
| Information Ratio | Pending | Alpha / tracking error |
| Up/Down Capture | Pending | Performance in market regimes |
| Chart Overlay | Pending | Strategy vs benchmark curves |
| Metrics Table | Pending | Side-by-side comparison |

**Plan:** Not yet created

---

### Slice 2.4: Trace Viewer + Slippage Analysis

**Goal:** Signal-to-fill audit trail with execution quality analysis.

| Task | Status | Description |
|------|--------|-------------|
| SignalTrace Model | Pending | Full context capture at signal time |
| ContextSnapshot | Pending | Market, indicators, portfolio state |
| TraceRepository | Pending | Storage and query interface |
| Slippage Calculation | Pending | Expected vs actual fill price |
| Trace API | Pending | Query traces by order, strategy, time |
| Trace Timeline UI | Pending | Visual signal → fill journey |
| Slippage Dashboard | Pending | Execution quality metrics |

**Plan:** Not yet created

---

### Slice 2.5: Retention Policies

**Goal:** Manage data lifecycle to prevent storage bloat.

| Task | Status | Description |
|------|--------|-------------|
| Compression Policy | Pending | TimescaleDB compression for old data |
| Tiered Retention | Pending | Permanent (fills), 7d (rejected), 24h (full snapshots) |
| Archival Jobs | Pending | Scheduled full → summary compression |
| Storage Monitoring | Pending | Alert on growth thresholds |

**Plan:** Not yet created

---

**Phase 2 Exit Criteria:** Can backtest strategies with benchmark comparison, analyze trade execution quality, trust system health.

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
