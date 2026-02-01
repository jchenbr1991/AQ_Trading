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

---

### Slice 2.6: Greeks Monitoring [COMPLETED]

**Goal:** Real-time Greeks monitoring, alerts, scenario analysis, and pre-order limit checks.

| Task | Status | Description |
|------|--------|-------------|
| Greeks Calculator | Done | Delta, gamma, vega, theta calculation |
| Greeks Aggregator | Done | Account/strategy level aggregation |
| Threshold Alerts | Done | Warn/crit/hard level alerts |
| ROC Alerts | Done | Rate-of-change detection |
| Greeks Repository | Done | Snapshot persistence, history queries |
| WebSocket Updates | Done | Real-time Greeks push |
| Greeks API V1 | Done | `/api/greeks` endpoints |
| V2: Scenario Shock API | Done | ±1%/±2% PnL projections |
| V2: PUT /limits | Done | Dynamic limit configuration |
| V2: GET /history | Done | Time-bucket aggregation (1h/4h/1d/7d) |
| V2: Pre-order Gate | Done | RiskManager Greeks limit integration |
| V2 Tests | Done | 371 tests pass |

**Plan:** `docs/plans/2026-01-31-greeks-v2-design.md` | **PR:** #26, #27

---

**Phase 2 Exit Criteria Met:** Can backtest strategies with benchmark comparison, analyze trade execution quality, trust system health, monitor storage, track portfolio Greeks.

---

## Phase 3: Advanced Features [COMPLETED]

### User Story 4: Options & Futures Lifecycle [COMPLETED]

| Task | Status | Description |
|------|--------|-------------|
| T009: ExpirationManager | Done | Days to expiry monitoring, 5-day warning |
| T010: AssignmentHandler | Done | ITM/OTM calculation, exercise estimation |
| T011: FuturesRollManager | Done | Calendar spread / close-open strategies |
| T012: Derivatives API | Done | `/api/derivatives/expiring`, `/api/derivatives/roll` |
| T013: Expiration Worker | Done | Daily pre-market check, alert integration |
| T014: Config | Done | `derivatives.yaml` with warning_days, roll strategies |
| T015: DerivativesPage | Done | Frontend component with roll actions |
| T016: TypeScript Types | Done | Generated from OpenAPI spec |
| Greeks Monitoring | Done | See Slice 2.6 |

**Acceptance Criteria Met:**
- SC-011: User receives expiration warning at least 5 days before expiry ✅
- FR-016: System tracks derivative expiry dates ✅
- FR-017: System supports futures auto-roll ✅
- FR-018: System handles options assignment/exercise ✅

---

### User Story 6: AI Agent System [COMPLETED]

| Task | Status | Description |
|------|--------|-------------|
| T017: AgentDispatcher | Done | Subprocess lifecycle, result capture |
| T018: Permission Model | Done | RBAC matrix, tool validation |
| T019: Agent Base | Done | Common interface, tool registration |
| T020: Researcher Agent | Done | Strategy optimization with walk-forward |
| T021: Analyst Agent | Done | Sentiment scoring from news/social |
| T022: Risk Controller Agent | Done | Dynamic risk bias via Redis |
| T023: Ops Agent | Done | Reconciliation analysis |
| T024-T028: Agent Tools | Done | backtest, market_data, portfolio, redis_writer, reconciliation (scaffolds) |
| T029: WalkForwardValidator | Done | 70/15/15 split, <20% degradation check |
| T030: Agent API | Done | `/api/agents/invoke`, `/api/agents/results` |
| T031: RiskManager Integration | Done | Redis risk_bias with graceful degradation |
| T032: AgentsPage | Done | Frontend invocation + results UI |
| T033: TypeScript Types | Done | Generated from OpenAPI spec |

**Acceptance Criteria Met:**
- FR-019: AI agent subsystem support ✅
- FR-020: Permission boundaries (read-only, parameters only) ✅
- FR-021: Graceful degradation when components fail ✅
- FR-022: Analyst generates sentiment factors ✅ (scaffold)
- FR-023: Researcher with overfitting protection ✅
- SC-013: Out-of-sample validation via walk-forward ✅
- SC-014: Risk bias takes effect within 1 minute ✅

**Note:** Agent tools (T024-T028) and agent execute methods are scaffold implementations. Full implementation requires:
- LLM provider integration (Anthropic Claude, OpenAI, etc.)
- Tool execution framework for agent-tool calls
- Backend service integration for tool implementations

---

### Production Hardening

| Task | Status | Description |
|------|--------|-------------|
| Graceful Degradation | Done | Risk bias fallback, agent failure tolerance |
| Enhanced Alerts | Done | EmailChannel + WebhookChannel in backend/src/alerts/channels.py |
| Audit Logging | Done | AuditService with tiered write paths in backend/src/audit/service.py |
| Agent Tools Integration | Pending | Connect T024-T028 scaffolds to backend services |

---

**Phase 3 Exit Criteria Met:** Can trade options/futures with lifecycle management, leverage agents for optimization with walk-forward validation.

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
