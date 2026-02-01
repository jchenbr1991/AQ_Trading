# ARCHITECTURE.md

System architecture for AQ Trading - a full-stack algorithmic trading system.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend (React)                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────────┐│
│  │ Dashboard   │ │ Backtest    │ │ Derivatives │ │ Agents Page             ││
│  │ - Positions │ │ - Strategy  │ │ - Expiring  │ │ - Invoke agents         ││
│  │ - P&L       │ │ - Benchmark │ │ - Roll      │ │ - View results          ││
│  │ - Kill SW   │ │ - Traces    │ │ - Assign    │ │ - Permission matrix     ││
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Backend (FastAPI)                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                           API Layer                                      ││
│  │  /api/portfolio  /api/risk  /api/greeks  /api/derivatives  /api/agents  ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│                                      │                                       │
│  ┌───────────────┐ ┌───────────────┐ │ ┌───────────────┐ ┌─────────────────┐│
│  │ Strategy      │ │ Risk Manager  │ │ │ Order Manager │ │ Reconciliation  ││
│  │ Engine        │ │ - Limits      │ │ │ - Lifecycle   │ │ Service         ││
│  │ - Signals     │ │ - Kill switch │ │ │ - Broker API  │ │ - Broker sync   ││
│  │ - Warm-up     │ │ - Greeks gate │ │ │ - Paper mode  │ │ - Discrepancy   ││
│  └───────────────┘ └───────────────┘ │ └───────────────┘ └─────────────────┘│
│                                      │                                       │
│  ┌───────────────┐ ┌───────────────┐ │ ┌───────────────┐ ┌─────────────────┐│
│  │ Portfolio     │ │ Market Data   │ │ │ Backtest      │ │ Derivatives     ││
│  │ Manager       │ │ Service       │ │ │ Engine        │ │ - Expiration    ││
│  │ - Positions   │ │ - Quotes      │ │ │ - Simulation  │ │ - Assignment    ││
│  │ - Account     │ │ - Caching     │ │ │ - Metrics     │ │ - Futures roll  ││
│  └───────────────┘ └───────────────┘ │ └───────────────┘ └─────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
┌─────────────────────────────────┐   ┌─────────────────────────────────────┐
│         PostgreSQL              │   │              Redis                   │
│  - Positions                    │   │  - Session cache                     │
│  - Orders                       │   │  - Market data cache                 │
│  - Agent results                │   │  - risk_bias (from agents)           │
│  - Greeks history (TimescaleDB) │   │  - sentiment:* (from agents)         │
│  - Derivative contracts         │   │  - events:* (from agents)            │
└─────────────────────────────────┘   └─────────────────────────────────────┘
                                                        ▲
                                                        │ Write (microseconds)
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AI Agent Sidecar System                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                        AgentDispatcher                                   ││
│  │  - Spawns subprocesses          - Captures results to DB                ││
│  │  - Permission validation         - Graceful degradation (FR-021)        ││
│  └─────────────────────────────────────────────────────────────────────────┘│
│         │                    │                    │                    │     │
│         ▼                    ▼                    ▼                    ▼     │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌───────────┐  │
│  │ Researcher  │     │ Analyst     │     │ Risk        │     │ Ops       │  │
│  │ Agent       │     │ Agent       │     │ Controller  │     │ Agent     │  │
│  │             │     │             │     │ Agent       │     │           │  │
│  │ Tools:      │     │ Tools:      │     │ Tools:      │     │ Tools:    │  │
│  │ - backtest  │     │ - market    │     │ - portfolio │     │ - recon   │  │
│  │ - portfolio │     │ - portfolio │     │ - redis     │     │ - compare │  │
│  └─────────────┘     └─────────────┘     └─────────────┘     └───────────┘  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                     Walk-Forward Validator                               ││
│  │  - 70/15/15 train/val/test split                                        ││
│  │  - <20% degradation threshold                                           ││
│  │  - Parameter stability tests (±10%, ±20%)                               ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles

### 1. Air Gap: Agents NEVER in Hot Path

**Critical Safety Constraint:** AI agents run as sidecar subprocesses, completely isolated from the trading hot path.

```
Trading Hot Path (microseconds):
  Signal → RiskManager → OrderManager → Broker

Agent Sidecar (seconds/minutes):
  Dispatcher → Subprocess → Redis write → [Trading reads Redis async]
```

**Rationale:**
- Agent latency unpredictable (LLM inference)
- Agent failures must not block trading
- System continues operating if agent subsystem fails (FR-021)

### 2. Graceful Degradation (FR-021)

Every external dependency has a fallback:

| Component | Fallback Behavior |
|-----------|-------------------|
| Redis unavailable | RiskManager uses default bias=1.0 |
| Agent subprocess fails | Result marked as error, trading continues |
| DB commit fails | Result returned, persistence logged as error |
| Greeks gate fails | Order proceeds with warning |

### 3. Permission Boundaries (FR-020)

Agents have strict RBAC permissions:

| Agent | Read | Write | Execute |
|-------|------|-------|---------|
| Researcher | market_data, portfolio, backtest | - | backtest runs |
| Analyst | market_data, portfolio | sentiment:*, events:* | - |
| Risk Controller | portfolio | risk_bias | - |
| Ops | reconciliation | - | - |

Write operations are restricted to specific Redis key prefixes.

---

## Component Details

### Backend Services (`backend/src/`)

| Component | Path | Responsibility |
|-----------|------|----------------|
| Portfolio Manager | `core/portfolio.py` | Position tracking, account sync |
| Risk Manager | `risk/manager.py` | Limits, kill switch, Redis bias integration |
| Greeks Gate | `greeks/greeks_gate.py` | Pre-order Greeks limit checks |
| Order Manager | (Phase 1) | Order lifecycle, broker integration |
| Market Data | (Phase 1) | Quote subscription, caching |
| Derivatives | `derivatives/*.py` | Expiration, assignment, futures roll |

### AI Agent System (`agents/`)

| Component | Path | Responsibility |
|-----------|------|----------------|
| Dispatcher | `dispatcher.py` | Subprocess lifecycle, result capture |
| Runner | `runner.py` | Subprocess entry point, agent routing |
| Permissions | `permissions.py` | RBAC validation, tool access control |
| Base | `base.py` | Agent/Tool base classes |
| Prompts | `prompts/*.py` | Role-specific agent implementations |
| Tools | `tools/*.py` | Agent tool implementations |
| Validation | `validation/walk_forward.py` | Overfitting prevention |

### Data Flow: Agent → Trading

```
1. Agent invoked via POST /api/agents/invoke
2. Dispatcher spawns subprocess (agents.runner)
3. Agent executes task, writes to Redis
4. Result persisted to agent_results table
5. RiskManager reads risk_bias from Redis async
6. Trading uses bias in next position limit check
```

**Latency guarantee:** Redis reads are O(1), ensuring <1 minute propagation (SC-014).

---

## Database Schema

### PostgreSQL Tables

| Table | Purpose |
|-------|---------|
| positions | Current portfolio positions |
| orders | Order history |
| derivative_contracts | Option/future contract metadata |
| agent_results | Agent task execution history |
| greeks_snapshots | TimescaleDB hypertable for Greeks history |

### Redis Keys

| Key Pattern | Owner | Purpose |
|-------------|-------|---------|
| `risk_bias` | Risk Controller | Position limit multiplier |
| `sentiment:{symbol}` | Analyst | Symbol sentiment scores |
| `events:{type}` | Analyst | Market event tags |
| `session:*` | Backend | Session cache |
| `quote:*` | Market Data | Quote cache |

---

## Directory Structure

```
aq_trading/
├── backend/
│   ├── src/
│   │   ├── api/routes/        # FastAPI endpoints
│   │   ├── core/              # Portfolio manager
│   │   ├── risk/              # RiskManager, state machine
│   │   ├── greeks/            # Greeks calculation, V2 features
│   │   ├── derivatives/       # Expiration, assignment, roll
│   │   ├── models/            # SQLAlchemy models
│   │   └── db/                # Database, Redis config
│   ├── tests/                 # Unit + integration tests
│   └── alembic/               # Database migrations
├── agents/
│   ├── dispatcher.py          # Agent subprocess manager
│   ├── runner.py              # Subprocess entry point
│   ├── permissions.py         # RBAC system
│   ├── base.py                # Base classes
│   ├── prompts/               # Agent role implementations
│   ├── tools/                 # Agent tool implementations
│   ├── validation/            # Walk-forward validator
│   └── tests/                 # Agent tests (266 tests)
├── frontend/
│   ├── src/
│   │   ├── pages/             # React pages
│   │   ├── hooks/             # TanStack Query hooks
│   │   ├── components/        # Reusable components
│   │   └── types/             # TypeScript types
│   └── package.json
├── specs/                     # Feature specifications
├── docs/plans/                # Implementation plans
├── STRATEGY.md                # Strategic design document
├── BACKLOG.md                 # Implementation backlog
└── ARCHITECTURE.md            # This document
```

---

## Testing Strategy

| Level | Coverage | Location |
|-------|----------|----------|
| Unit | All services, models, validators | `backend/tests/unit/`, `agents/tests/` |
| Integration | API endpoints, DB operations | `backend/tests/integration/` |
| E2E | Frontend flows (manual) | - |

**Test counts:**
- Backend: ~200 tests
- Agents: 266 tests
- All passing with TDD discipline

---

## Deployment

```
┌─────────────────────────────────────────────┐
│              Docker Compose                  │
│  ┌─────────────┐  ┌─────────────┐           │
│  │ PostgreSQL  │  │ Redis       │           │
│  │ + Timescale │  │             │           │
│  └─────────────┘  └─────────────┘           │
│  ┌─────────────────────────────────────────┐│
│  │ Backend (FastAPI + Uvicorn)             ││
│  │ - API server                            ││
│  │ - Workers (expiration, health)          ││
│  └─────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────┐│
│  │ Frontend (Vite + React)                 ││
│  └─────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

---

## Security Considerations

1. **Agent isolation**: Subprocesses with restricted permissions
2. **Redis key validation**: Write operations only to allowed prefixes
3. **No credential embedding**: Broker credentials via environment
4. **Kill switch**: Emergency trading halt available via API and dashboard

---

## Future Considerations

- Multi-broker support
- Enhanced alert channels (Slack, email)
- Audit logging for compliance
- Real agent tool implementations (currently scaffolds)
