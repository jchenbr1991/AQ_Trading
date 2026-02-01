# Implementation Plan: AQ Trading - 算法交易系统产品全景

**Branch**: `001-product-overview` | **Date**: 2026-01-31 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-product-overview/spec.md`

**Note**: For implementation, use OpenSpec commands (`/opsx:new`, `/opsx:continue`, `/opsx:apply`).

## Summary

This is a **documentation/overview specification** for the existing AQ Trading system, not a new feature implementation. The spec captures the complete product vision across 3 phases:

- **Phase 1 (Completed)**: Core trading execution - Portfolio Manager, Strategy Engine, Risk Manager, Order Manager, Reconciliation, Paper Trading, Dashboard
- **Phase 2 (Completed)**: Analytics & Testing - Health Monitoring, Backtesting, Benchmark Comparison, Trace Viewer, Retention Policies, Greeks Monitoring
- **Phase 3 (Pending)**: Advanced Features - Derivatives Lifecycle (Expiration/Assignment/Roll), CLI Agents (Researcher/Analyst/Risk Controller/Ops), Dynamic Risk Bias, Sentiment Factors, Auto-Tuning, Graceful Degradation

**Document Purpose**: This is a **retrospective documentation** of the existing AQ Trading system (Phases 1-2) plus a high-level overview of Phase 3 scope as defined in STRATEGY.md. This plan does NOT propose new designs - Phase 3 detailed design will be done when that phase starts via OpenSpec workflow.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.3+ (frontend)
**Primary Dependencies**:
- Backend: FastAPI 0.109+, Pydantic 2.5+, SQLAlchemy 2.0+, Redis 5.0+, moomoo 2.0+
- Frontend: React 18.2+, TanStack Query 5.17+, Recharts 3.7+, Vite 5.0+, Tailwind CSS 3.4+
**Storage**: PostgreSQL (TimescaleDB) + Redis (cache/pub-sub)
**Testing**: pytest 7.4+ with pytest-asyncio (backend), vitest (frontend)
**Target Platform**: Linux server (local first, Docker-ready)
**Project Type**: Web application (backend + frontend)
**Performance Goals**:
- Signal-to-order latency <500ms (SC-002)
- Backtest 1 year data in <30 seconds (SC-005)
- Health check updates every 10 seconds, fault detection <30 seconds (SC-008)
**Constraints**:
- Single user (no multi-tenancy)
- Kill switch must trigger flat in <3 seconds (SC-004)
- Greeks calculation deviation <5% from market models (SC-012)
**Scale/Scope**:
- 10 concurrent strategies, 100 positions (SC-003)
- 6 User Stories, 23 Functional Requirements
- 14 Success Criteria

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Gates (from constitution.md v1.0.0)

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Superpower-First Development** | ✅ PASS | Using planning workflow |
| **II. Human Sovereignty** | ✅ PASS | This plan requires human approval before proceeding |
| **III. Intellectual Honesty** | ✅ PASS | Spec clearly marks Phases 1-2 as COMPLETED, Phase 3 as PENDING |
| **IV. Proactive Guidance** | ✅ PASS | Plan provides actionable next steps for Phase 3 implementation |
| **V. External AI Review Gate** | ✅ PASS | Codex + Gemini review passed (2026-01-31) |

### Technology Stack Compliance (from constitution.md)

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Backend: Python 3.11+ FastAPI | ✅ COMPLIANT | pyproject.toml: `requires-python = ">=3.11"` |
| Frontend: TypeScript React | ✅ COMPLIANT | package.json: React 18.2+, TypeScript 5.3+ |
| Database: PostgreSQL + Redis | ✅ COMPLIANT | asyncpg, redis in dependencies |
| Broker API: Futu OpenAPI | ✅ COMPLIANT | moomoo 2.0+ in dependencies |
| Type Safety Chain | ✅ COMPLIANT | Pydantic models → OpenAPI → TypeScript |

### Protected Paths (from constitution.md)

| Path | Protection | Status |
|------|------------|--------|
| `strategies/live/` | Requires explicit confirmation | N/A (no changes planned) |
| `core/risk_manager.py` | Safety-critical review | N/A (Phase 3 extends, not modifies) |
| `frontend/src/api/generated/` | Auto-generated, never edit | ✅ Respected |

### Development Workflow Compliance

| Requirement | Status |
|-------------|--------|
| TDD: Tests before implementation | ✅ Project standard (BACKLOG.md) |
| External Review: Codex + Gemini PASS | ✅ PASS (2026-01-31) |
| Vertical Slices: E2E features | ✅ Project standard (BACKLOG.md) |

## Project Structure

### Documentation (this feature)

```text
specs/001-product-overview/
├── plan.md              # This file (current)
├── research.md          # Architecture decisions, existing patterns
├── data-model.md        # Entity definitions from existing models
├── quickstart.md        # Setup and usage guide
├── contracts/           # OpenAPI specification
│   └── openapi.yaml
└── checklists/          # Feature checklists
```

**Note**: `tasks.md` is generated separately via OpenSpec (`/opsx:continue`) when implementation starts.

### Source Code (repository root)

```text
# Web Application Structure (existing)
backend/
├── src/
│   ├── api/                  # REST endpoints
│   │   └── routes/           # Portfolio, orders, strategies, risk, backtest, traces, health, greeks
│   ├── backtest/             # Backtesting engine
│   ├── broker/               # Futu broker integration, paper trading
│   ├── core/                 # Portfolio, order manager, risk manager, market data
│   ├── db/                   # Database, Redis, TimescaleDB
│   ├── greeks/               # Greeks calculator, aggregator, alerts
│   ├── health/               # Health monitoring
│   ├── models/               # Pydantic models (source of truth)
│   ├── risk/                 # Risk management
│   ├── schemas/              # API schemas
│   ├── services/             # Business services
│   ├── strategies/           # Strategy framework
│   │   ├── examples/         # Reference implementations
│   │   └── live/             # Production strategies (protected)
│   └── workers/              # Background workers
├── tests/                    # pytest test suite (371+ tests)
├── alembic/                  # Database migrations
└── config/                   # Configuration files

frontend/
├── src/
│   ├── components/           # Reusable UI components
│   ├── pages/                # Route pages (dashboard, portfolio, strategies, etc.)
│   ├── hooks/                # Custom React hooks
│   ├── api/                  # API client
│   │   └── generated/        # Auto-generated types (do not edit)
│   ├── stores/               # State management
│   └── types/                # TypeScript types
└── tests/                    # vitest test suite

# Phase 3 additions (planned)
agents/                       # CLI Agent system (not yet implemented)
├── dispatcher.py             # AgentDispatcher
├── permissions.py            # Permission model
├── prompts/                  # Role-specific system prompts
├── tools/                    # CLI tools agents can invoke
└── outputs/                  # Agent-generated artifacts
```

**Structure Decision**: Web application with Python FastAPI backend and TypeScript React frontend. Backend structure follows domain-driven organization with separate modules for each concern. Frontend follows standard React patterns with hooks-based state management.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | No violations detected | All gates pass |

**Note**: This is a product overview spec documenting existing implementation. No new complexity introduced.

---

## Post-Design Constitution Re-Check

*Re-evaluated after Phase 1 design artifacts generated.*

### Design Artifacts Generated

| Artifact | Status | Description |
|----------|--------|-------------|
| `research.md` | ✅ Complete | Architectural decisions, Phase 3 research |
| `data-model.md` | ✅ Complete | Entity definitions, relationships, validations |
| `contracts/openapi.yaml` | ✅ Complete | REST API specification |
| `quickstart.md` | ✅ Complete | Setup and usage guide |

### Post-Design Gate Evaluation

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Superpower-First Development** | ✅ PASS | Completed using planning workflow |
| **II. Human Sovereignty** | ✅ PASS | Plan ready for human review |
| **III. Intellectual Honesty** | ✅ PASS | Design documents existing system accurately |
| **IV. Proactive Guidance** | ✅ PASS | Quickstart provides actionable setup steps |
| **V. External AI Review Gate** | ✅ PASS | Codex + Gemini review passed (2026-01-31) |

### Design Consistency Check

| Check | Status |
|-------|--------|
| Data model matches spec entities | ✅ All 8 key entities documented |
| API contracts cover spec requirements | ✅ All functional requirements have endpoints |
| Research resolves all unknowns | ✅ No NEEDS CLARIFICATION remaining |
| Phase 3 design decisions documented | ✅ Agent architecture, permissions, overfitting guards |

### Next Steps

1. **External AI Review**: Run Codex + Gemini review on this plan
2. **Human Approval**: Present plan for human review
3. **Tasks Generation**: Use OpenSpec (`/opsx:continue`) to generate implementation tasks
4. **Implementation**: Execute Phase 3 features using generated tasks

---

## Approval

| Gate | Status | Date |
|------|--------|------|
| External AI Review (Codex) | ✅ PASS | 2026-01-31 |
| External AI Review (Gemini) | ✅ PASS | 2026-01-31 |
| Human Approval | ✅ APPROVED | 2026-01-31 |

**Plan Status**: ✅ **APPROVED** - Ready for implementation
