# Implementation Plan: Tiger Trading Broker Adapter

**Branch**: `004-tiger-broker-adapter` | **Date**: 2026-02-05 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/004-tiger-broker-adapter/spec.md`

## Summary

Implement a Tiger Trading broker adapter (`TigerBroker`) that conforms to the
existing `Broker` and `BrokerQuery` protocols, plus a `TigerDataSource` that
conforms to the `DataSource` protocol. This enables the system to execute orders,
receive fills, query positions/accounts, and stream real-time market data through
Tiger Trading's API. Broker and data source selection is driven by strategy YAML
config, allowing seamless switching between Paper, Futu, and Tiger.

The approach uses the `tigeropen` SDK (v3.3.3), wrapping its synchronous
`TradeClient` calls via `asyncio.to_thread()` and bridging its `PushClient`
callbacks (fills, quotes) into async queues using `call_soon_threadsafe`.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: tigeropen (3.3.3), FastAPI, Pydantic, asyncio
**Storage**: N/A (stateless adapter; Redis for quote caching via existing MarketDataService)
**Testing**: pytest (async), backend/tests/broker/, backend/tests/market_data/
**Target Platform**: Linux server
**Project Type**: Web application (backend only for this feature)
**Performance Goals**: Order submission <5s; quote latency <2s from Tiger feed to strategy
**Constraints**: Rate limits — 120 req/min (orders), 60 req/min (positions/quotes), 10 req/min (meta); retry with backoff up to 3 times on rate limit errors (spec edge case). Credentials MUST NOT appear in logs or VCS
**Scale/Scope**: Single trading account, ~50 symbols max for real-time quotes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Status |
|-----------|------|--------|
| I. Authority & Control | Feature scope approved by human (spec.md reviewed) | PASS |
| II. Immutable Assumptions | Capital safety: LiveBroker risk controls wrap TigerBroker; credentials secured with 0600 perms | PASS |
| III. Decision Boundaries | New class (TigerBroker) is additive, conforms to existing Protocol — no new abstractions | PASS |
| III. Decision Boundaries | LiveBroker refactor (FR-007) changes existing behavior — APPROVED in spec | PASS |
| IV. Change Discipline | All changes traceable to spec FR-001 through FR-013 | PASS |
| V. Failure & Uncertainty | SDK async support: confirmed synchronous-only, will use thread pool | PASS |
| VI. Scope of Autonomy | No irreversible decisions; adapter is config-driven and reversible | PASS |

## Project Structure

### Documentation (this feature)

```text
specs/004-tiger-broker-adapter/
├── plan.md              # This file
├── research.md          # Phase 0: SDK research, decision log
├── data-model.md        # Phase 1: Entity definitions
├── quickstart.md        # Phase 1: Developer setup guide
├── contracts/           # Phase 1: Interface contracts
│   ├── tiger-broker.md
│   └── tiger-datasource.md
└── tasks.md             # Phase 2: Implementation tasks (via /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── broker/
│   │   ├── base.py              # Existing Broker Protocol (unchanged)
│   │   ├── query.py             # Existing BrokerQuery Protocol (unchanged)
│   │   ├── config.py            # Extended: add tiger fields + load_broker case
│   │   ├── errors.py            # Existing errors (unchanged)
│   │   ├── paper_broker.py      # Existing (unchanged)
│   │   ├── live_broker.py       # Refactored: decorator pattern (FR-007)
│   │   └── tiger_broker.py      # NEW: TigerBroker adapter
│   └── market_data/
│       ├── sources/
│       │   ├── base.py          # Existing DataSource Protocol (unchanged)
│       │   ├── mock.py          # Existing MockDataSource (unchanged)
│       │   └── tiger.py         # NEW: TigerDataSource adapter
│       └── service.py           # Modified: configurable data source selection
├── tests/
│   ├── broker/
│   │   ├── test_tiger_broker.py # NEW: TigerBroker unit tests
│   │   ├── test_live_broker.py  # Updated: test decorator pattern
│   │   └── test_config.py       # Updated: test tiger config loading
│   └── market_data/
│       └── test_tiger_source.py # NEW: TigerDataSource unit tests
config/
└── brokers/
    └── tiger_openapi_config.properties  # Existing (untracked, .gitignored)
```

**Structure Decision**: Web application layout (backend only). All new code lives
in `backend/src/broker/` and `backend/src/market_data/sources/`. No frontend
changes needed. Config files in `config/brokers/` are already gitignored.

## Pre-Implementation State

> **Note**: The current codebase (`live_broker.py`, `config.py`) does NOT yet
> reflect FR-006/FR-007 requirements. This is expected — these files will be
> modified during implementation. The plan describes the target state, not the
> current state.

## Complexity Tracking

> No constitution violations. All changes are additive conforming to existing
> protocols, or explicitly approved behavioral changes (FR-007 LiveBroker refactor).
