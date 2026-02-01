# Research: AQ Trading Product Overview

**Branch**: `001-product-overview` | **Date**: 2026-01-31

## Overview

This research document captures design decisions for the AQ Trading system. This is **retrospective documentation** of existing patterns:

1. Documenting existing architectural decisions (Phases 1-2)
2. Summarizing Phase 3 scope as defined in STRATEGY.md
3. Recording best practices already established in the codebase

**Note**: Phase 3 detailed design will be done when that phase starts. This document only references what's already in STRATEGY.md.

---

## 1. Existing Architecture Decisions (Phases 1-2)

### 1.1 Trading Core Architecture

**Decision**: Event-driven signal flow with clear separation of concerns

**Rationale**:
- Strategies emit Signals, not Orders (intent vs execution)
- Risk Manager validates all signals before Order Manager
- Portfolio Manager is passive (tracks state, doesn't make decisions)
- Clear audit trail from signal to fill

**Alternatives Considered**:
- Direct order submission from strategies → Rejected: bypasses risk controls
- Monolithic trading loop → Rejected: harder to test and maintain

### 1.2 Strategy Tagging

**Decision**: Every position/order tagged with `strategy_id`

**Rationale**:
- Same symbol can be held by multiple strategies
- Enables per-strategy P&L tracking and isolation
- Manual trades tagged as `strategy_id=None`
- Dashboard can show strategy-level performance

**Alternatives Considered**:
- Single portfolio view only → Rejected: can't attribute performance to strategies

### 1.3 Data Storage

**Decision**: PostgreSQL (TimescaleDB) + Redis

**Rationale**:
- TimescaleDB: Optimized for time-series data (quotes, bars, traces)
- PostgreSQL: ACID transactions for positions, orders, accounts
- Redis: Low-latency cache for live quotes, pub/sub for real-time updates
- Separation allows independent scaling

**Alternatives Considered**:
- InfluxDB for time-series → Rejected: less mature SQL support
- MongoDB → Rejected: weaker transaction guarantees

### 1.4 Type Safety Chain

**Decision**: Pydantic → OpenAPI → TypeScript auto-generation

**Rationale**:
- Single source of truth (backend Pydantic models)
- Frontend types always in sync
- Eliminates type mismatch bugs between frontend/backend

**Implementation**:
- `scripts/generate_openapi.py` generates OpenAPI schema
- `frontend/scripts/generate-types.sh` generates TypeScript
- `frontend/src/api/generated/` is never manually edited

---

## 2. Phase 3 Scope Reference: Derivatives Lifecycle

> **Note**: The following sections summarize Phase 3 scope from STRATEGY.md. Detailed implementation design will be done when Phase 3 starts via OpenSpec workflow.

### 2.1 Expiration Tracking

**Decision**: Daily expiration check before market open

**Rationale**:
- Derivatives have fixed expiry dates
- User Story 4 requires 5-day warning (SC-011)
- Must handle options assignment and futures roll-over

**Implementation Approach**:
```python
class ExpirationManager:
    warning_days: int = 5  # Configurable

    async def check_expirations(self):
        # Run daily before market open
        positions = await portfolio.get_derivative_positions()
        for pos in positions:
            if pos.days_to_expiry <= warning_days:
                await alert(f"{pos.symbol} expires in {pos.days_to_expiry} days")
```

**Alternatives Considered**:
- Real-time expiry monitoring → Rejected: overkill, daily check sufficient

### 2.2 Options Assignment Handling

**Decision**: Pre-calculate ITM/OTM status, alert before expiration

**Rationale**:
- ITM options will be exercised/assigned automatically
- User needs advance warning to take action
- System should estimate resulting stock position

**Implementation Approach**:
- Check underlying price vs strike on expiration day
- Alert user about expected assignment
- Pre-create placeholder for resulting stock position

### 2.3 Futures Roll-over

**Decision**: Support both calendar spread and close/open strategies

**Rationale**:
- Different underlying contracts have different liquidity
- Calendar spread: better execution for liquid contracts
- Close/open: simpler for illiquid contracts

**Configuration**:
```yaml
futures_roll:
  ES: calendar_spread  # Liquid, use spread
  NQ: close_open       # Fallback strategy
  default: close_open
  days_before_expiry: 5
```

---

## 3. Phase 3 Scope Reference: CLI Agent System

> **Note**: Agent architecture is defined in STRATEGY.md "CLI Agent Integration" section. The patterns below are from that document.

### 3.1 Agent Architecture

**Decision**: Sidecar subprocess architecture (agents never in trading hot path)

**Rationale**:
- LLM inference takes seconds (unacceptable in trading loop)
- Agents run on schedules, write to Redis
- Trading path reads Redis (microseconds)
- Complete isolation prevents agent failures from affecting trading

**Critical Rule**: Trading main loop has NO `await agent.*` calls. Ever.

**Implementation Pattern**:
```python
# WRONG: Agent in trading path
async def check_signal(signal):
    risk_analysis = await agent.analyze(signal)  # BLOCKS TRADING!

# CORRECT: Agent writes to Redis on schedule
async def agent_loop():
    while True:
        result = await agent.analyze_market()
        await redis.set("risk_bias", result.bias)
        await asyncio.sleep(900)  # 15 minutes

async def check_signal(signal):
    bias = float(await redis.get("risk_bias") or "1.0")  # Instant
```

### 3.2 Agent Permission Model

**Decision**: Role-based permissions with hard boundaries

**Rationale**:
- Prevent agent hallucinations from causing trading disasters
- Read-only DB access (except log tables)
- Parameters, not commands (agents output data, never call trading APIs)
- Code changes require human review

**Permission Matrix**:

| Role | Can Read | Can Write | Cannot Touch |
|------|----------|-----------|--------------|
| Researcher | strategies/*, backtest/* | strategies/examples/* | strategies/live/*, broker/* |
| Analyst | market_data/*, news/* | redis:sentiment:* | strategies/*, orders/* |
| Risk Controller | portfolio/*, risk/* | redis:risk_bias | strategies/*, broker/* |
| Ops | * | logs/*, outputs/* | strategies/live/*, broker/* |

### 3.3 Agent Overfitting Prevention

**Decision**: Mandatory walk-forward validation with stability checks

**Rationale**:
- Auto-tuning agents will overfit without guardrails
- Historical optimization doesn't guarantee live performance
- Parameters must be stable (work across small variations)

**Required Validation**:
1. Walk-forward: 70% train / 15% validation / 15% test
2. Performance degradation test → test < 20% worse than validation
3. Parameter stability: ±10%, ±20% must not cause sharp drops
4. Regime testing: bull, bear, high-vol, low-vol

### 3.4 Agent Context Snapshots

**Decision**: Full context capture at signal time, tiered retention

**Rationale**:
- Agents need rich context for post-trade analysis
- Full snapshots are storage-intensive
- Tiered retention balances analysis needs vs storage costs

**Retention Policy**:
- Full snapshot: 24 hours
- Compressed summary: 90 days
- Filled orders: permanent (audit requirement)
- Rejected signals: 7 days

---

## 4. Best Practices Summary

### 4.1 Trading System Best Practices (Implemented)

| Practice | Status | Evidence |
|----------|--------|----------|
| Signals, not Orders | ✅ | Strategy ABC emits Signal, Risk Manager converts to Order |
| Multi-layer risk checks | ✅ | Position → Portfolio → Loss → Greeks → Kill Switch |
| Atomic operation chain | ✅ | DB transaction → Risk check → Broker submit → Update |
| Write-ahead logging | ✅ | WAL for crash recovery |
| Reconciliation | ✅ | Periodic broker sync, discrepancy detection |
| Paper trading mode | ✅ | PaperBroker with real quotes, simulated fills |
| Strategy warm-up | ✅ | Historical data to initialize indicators |

### 4.2 Observability Best Practices (Implemented)

| Practice | Status | Evidence |
|----------|--------|----------|
| Structured logging | ✅ | trace_id propagation throughout |
| Health monitoring | ✅ | Component heartbeats, degradation policies |
| Trace viewer | ✅ | Signal-to-fill audit trail with context |
| Slippage analysis | ✅ | Expected vs actual fill tracking |

### 4.3 Phase 3 Best Practices (To Implement)

| Practice | Priority | Rationale |
|----------|----------|-----------|
| Agent isolation | P0 | Prevent agent failures from affecting trading |
| Permission boundaries | P0 | Agents can't directly trade |
| Overfitting guards | P0 | Validation before applying optimizations |
| Expiration alerts | P1 | User Story 4 requirement |
| Tiered data retention | P1 | Prevent storage bloat from agent snapshots |

---

## 5. Technology Choices Validation

### 5.1 Backend (Validated)

| Choice | Validation |
|--------|------------|
| Python 3.11+ | ✅ Modern async/await, type hints, performance |
| FastAPI | ✅ High performance, automatic OpenAPI docs |
| Pydantic 2.x | ✅ 5-50x faster than v1, better validation |
| SQLAlchemy 2.x | ✅ Native async, improved typing |
| asyncpg | ✅ Fastest PostgreSQL driver for async Python |
| moomoo SDK | ✅ Official Futu broker SDK |

### 5.2 Frontend (Validated)

| Choice | Validation |
|--------|------------|
| React 18+ | ✅ Concurrent features, hooks ecosystem |
| TanStack Query | ✅ Best-in-class data fetching, caching |
| Vite | ✅ Fast dev server, optimized builds |
| Tailwind CSS | ✅ Utility-first, no CSS conflicts |
| Recharts | ✅ React-native charting, composable |

### 5.3 Infrastructure (Validated)

| Choice | Validation |
|--------|------------|
| TimescaleDB | ✅ Time-series optimized, full SQL support |
| Redis | ✅ Sub-millisecond latency, pub/sub |
| Docker | ✅ Consistent environments, easy deployment |

---

## 6. Conclusion

All "NEEDS CLARIFICATION" items have been resolved:

- **No unknowns in Technical Context**: Existing codebase fully documents all technology choices
- **Phase 3 design decisions documented**: Agent architecture, permissions, overfitting prevention
- **Best practices validated**: Both implemented (Phases 1-2) and planned (Phase 3)

Ready to proceed to Phase 1: Design & Contracts.
