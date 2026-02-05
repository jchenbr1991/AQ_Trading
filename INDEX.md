# INDEX.md — AQ Trading Codebase Navigation

> **Purpose**: Reduce token consumption for AI agents by providing a structured path index.
> **First Read**: All agents MUST read this file before exploring the codebase.
> **Note**: This index shows key directories only, not exhaustive listings. Use `ls` for complete contents.

---

## Quick Reference

| Need | Path |
|------|------|
| Project overview | `README.md` |
| Strategic roadmap | `STRATEGY.md` |
| Implementation backlog | `BACKLOG.md` |
| System architecture | `ARCHITECTURE.md` |
| Agent instructions | `CLAUDE.md`, `GEMINI.md`, `AGENTS.md` |
| Active specs | `specs/` |
| Design plans | `docs/plans/` |

---

## 1. Root Documentation

| File | Purpose |
|------|---------|
| `README.md` | Quick start, tech stack, API endpoints |
| `STRATEGY.md` | 4-phase roadmap, component scope, exit criteria |
| `BACKLOG.md` | Development progress by phase/slice |
| `ARCHITECTURE.md` | System design, core principles, air gap |
| `CLAUDE.md` | Claude Code system prompt, superpowers |
| `GEMINI.md` | Gemini reviewer contract |
| `AGENTS.md` | AI agent system documentation |

---

## 2. Backend (`/backend`)

### 2.1 Source Code (`backend/src/`) — Key directories

```
backend/src/
├── main.py              # FastAPI entry point
├── config.py            # App configuration
├── api/                 # REST endpoints (alerts, orders, risk, etc.)
│   └── routes/          # Route handlers
├── core/                # Business logic
│   └── portfolio.py     # Position tracking
├── orders/              # Order lifecycle
├── risk/                # Risk limits, kill switch
├── market_data/         # Quote subscription, caching
├── broker/              # Trading modes
│   ├── base.py          # Abstract interface
│   ├── live_broker.py   # Futu production
│   └── paper_broker.py  # Simulated trading
├── backtest/            # Backtesting engine
│   ├── engine.py        # Simulation loop
│   ├── models.py        # Bar, Trade, BacktestResult
│   ├── fill_engine.py   # Order filling
│   └── metrics.py       # Sharpe, drawdown, etc.
├── strategies/          # Strategy framework
│   ├── base.py          # BaseStrategy abstract
│   ├── engine.py        # Execution engine
│   ├── signals.py       # Signal generation
│   ├── factors/         # Factor components
│   └── indicators/      # Technical indicators
├── derivatives/         # Options/futures
├── greeks/              # Greeks monitoring
├── db/                  # Database layer, migrations
├── health/              # Component health checks
├── degradation/         # Circuit breakers
├── alerts/              # Alert generation
├── audit/               # Audit logging
├── reconciliation/      # Broker sync
├── workers/             # Background jobs
├── models/              # Pydantic models
├── schemas/             # API schemas
├── services/            # Business services
├── options/             # Options trading
└── universe/            # Trading universe
```

### 2.2 Configuration (`backend/config/`)

| File | Purpose |
|------|---------|
| `risk.yaml` | Position limits, loss limits |
| `strategies.yaml` | Strategy parameters |
| `derivatives.yaml` | Expiration settings |
| `universe.yaml` | Trading universe |

### 2.3 Tests (`backend/tests/`)

Mirrors `src/` structure. Key directories:
- `api/` — Endpoint tests
- `backtest/` — Engine tests
- `integration/` — E2E tests
- `performance/` — Benchmarks
- `strategies/` — Strategy tests

---

## 3. Frontend (`/frontend`)

### 3.1 Source Code (`frontend/src/`)

```
frontend/src/
├── main.tsx             # React entry
├── App.tsx              # Main component
├── pages/               # Page components
│   ├── DashboardPage.tsx    # Portfolio, P&L, kill switch
│   ├── BacktestPage.tsx     # Backtest runner
│   ├── DerivativesPage.tsx  # Options/futures
│   ├── GreeksPage.tsx       # Greeks dashboard
│   ├── HealthPage.tsx       # System health
│   ├── AgentsPage.tsx       # AI agent interface
│   ├── AlertsPage.tsx       # Alert management
│   ├── AuditPage.tsx        # Audit log viewer
│   ├── SystemPage.tsx       # System configuration
│   ├── StoragePage.tsx      # Data storage/retention
│   └── OptionsExpiringPage.tsx  # Expiring options
├── components/          # Reusable UI
├── hooks/               # Data fetching hooks
├── contexts/            # Global state
├── api/                 # Backend client
└── types/               # TypeScript types
```

---

## 4. AI Agents (`/agents`)

```
agents/
├── base.py              # BaseAgent abstract
├── dispatcher.py        # Agent orchestration
├── runner.py            # Subprocess execution
├── prompts/             # Agent prompts
│   ├── researcher.py    # Strategy optimization
│   ├── analyst.py       # Sentiment analysis
│   ├── risk_controller.py  # Dynamic risk
│   └── ops.py           # Operations
├── tools/               # Agent capabilities
│   ├── backtest.py      # Run backtests
│   ├── market_data.py   # Market access
│   ├── portfolio.py     # Position queries
│   └── redis_writer.py  # State updates
├── validation/          # Walk-forward validation
└── tests/               # Agent tests
```

---

## 5. Specifications (`/specs`)

OpenSpec structure for each feature:

```
specs/
├── 001-product-overview/
│   ├── spec.md          # Product specification
│   ├── plan.md          # Development plan
│   ├── tasks.md         # Implementation tasks
│   └── data-model.md    # Entity relationships
└── 002-minimal-mvp-trading/
    └── (same structure)
```

---

## 6. Design Documents (`/docs/plans`)

Dated design documents by feature:

| Feature | Files |
|---------|-------|
| Portfolio Manager | `2026-01-22-portfolio-manager.md` |
| Market Data | `2026-01-23-market-data-*.md` |
| Order Manager | `2026-01-23-order-manager-*.md` |
| Risk Manager | `2026-01-23-risk-manager-*.md` |
| Strategy Engine | `2026-01-23-strategy-engine-*.md` |
| Backtest Engine | `2026-01-25-backtest-engine.md` |
| Dashboard | `2026-01-25-dashboard-*.md` |
| Greeks Monitoring | `2026-01-28-greeks-*.md`, `2026-01-31-greeks-v2-*.md` |

---

## 7. Infrastructure

| Path | Purpose |
|------|---------|
| `docker-compose.yml` | PostgreSQL, Redis |
| `backend/pyproject.toml` | Python dependencies |
| `frontend/package.json` | Node dependencies |
| `.pre-commit-config.yaml` | Git hooks |

---

## 8. Technology Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, TypeScript 5.3, TanStack Query, Tailwind, Vite |
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Pydantic |
| Database | PostgreSQL (TimescaleDB), Redis |
| Broker | Futu (moomoo) OpenAPI |

---

## 9. Development Phases

| Phase | Status | Focus |
|-------|--------|-------|
| Phase 1 (MVP) | ✅ COMPLETED | Core trading infrastructure |
| Phase 2 (Analytics) | ✅ COMPLETED | Backtesting, monitoring |
| Phase 3 (Advanced) | ✅ COMPLETED | Options, AI agents, degradation |
| Phase 4 (Strategy) | ✅ COMPLETED | First runnable trading strategy |
| Phase 5 (Governance) | ✅ COMPLETED | Hypothesis + Constraints system |

---

## Navigation Tips

1. **Finding code**: Start with `backend/src/` structure above
2. **Understanding a feature**: Check `docs/plans/` for design docs
3. **Current work**: Check `BACKLOG.md` for active items
4. **Test coverage**: Tests mirror source in `backend/tests/`
5. **API contracts**: Check `backend/src/api/routes/` and `frontend/src/types/`

---

*Last updated: 2026-02-05*
