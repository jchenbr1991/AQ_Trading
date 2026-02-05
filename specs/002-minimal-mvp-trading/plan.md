# Implementation Plan: Minimal Runnable Trading System

**Branch**: `002-minimal-mvp-trading` | **Date**: 2026-02-01 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-minimal-mvp-trading/spec.md`

## Summary

Build the **first runnable trading system** on AQ_Trading by adding Feature/Factor/Universe layers + TrendBreakout strategy that exercises the existing infrastructure (Strategy framework, BacktestEngine, PaperBroker, RiskManager) end-to-end.

**Primary Requirements:**
- Complete backtest → paper → live trading loop for MU/GLD/GOOG
- Feature calculation: ROC, price_vs_ma, price_vs_high, volume_zscore, volatility
- Factor composition: momentum_factor, breakout_factor with configurable weights
- Position sizing: equal-weight (FR-015) and fixed-risk per position (FR-016)
- PnL attribution by factor (FR-023)
- Same strategy logic across all execution modes

**Technical Approach:**
- Extend existing Strategy base class with TrendBreakoutStrategy
- Create indicators module for feature calculations
- Create factors module for factor composition
- Implement position sizing: equal-weight and fixed-risk modes
- Add attribution tracking to trade records
- Leverage existing BacktestEngine, PaperBroker, and order pipeline

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.3+ (frontend if needed)
**Primary Dependencies**: FastAPI, existing Strategy framework (`backend/src/strategies/`), numpy/pandas for calculations
**Storage**: PostgreSQL (TimescaleDB) + Redis (per constitution)
**Testing**: pytest with existing test infrastructure
**Target Platform**: Linux server (local first, Docker-ready)
**Project Type**: Web application (backend focus - frontend dashboard exists)
**Performance Goals**:
- Backtest 1 year × 3 symbols < 30 seconds (SC-004)
- Paper trading signal generation < 5 seconds (SC-005)
**Constraints**:
- Zero lookahead bias (SC-007)
- Mode-agnostic strategy logic (SC-002)
**Scale/Scope**:
- 3 symbols (MU, GLD, GOOG)
- Daily bars only
- ~250 trading days/year × 3 symbols = ~750 bars for 1-year backtest

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| **I. Superpower-First Development** | ✅ COMPLIANT | `/speckit.specify` and `/speckit.plan` skills invoked |
| **II. Human Sovereignty** | ✅ COMPLIANT | Spec human-approved 2026-02-01; plan requires approval |
| **III. Intellectual Honesty** | ✅ COMPLIANT | Assumptions documented in spec; unknowns resolved in research.md |
| **IV. Proactive Guidance** | ✅ COMPLIANT | Plan provides concrete next steps and quickstart.md |
| **V. External AI Review Gate** | ✅ COMPLIANT | Spec reviewed: Codex PASS, Gemini PASS (2026-02-01) |

**Skill Invocations:**
- `/speckit.specify` - Created spec with 5 review iterations
- `/speckit.plan` - Created this implementation plan

**External Review Log:**
| Artifact | Codex | Gemini | Date |
|----------|-------|--------|------|
| spec.md | PASS | PASS | 2026-02-01 |
| plan.md | PASS | PASS | 2026-02-01 |

**Technology Stack Compliance:**
- [x] Backend: Python 3.11+ with FastAPI
- [x] Database: PostgreSQL (TimescaleDB) + Redis
- [x] Type Safety: Pydantic models as source of truth
- [x] Protected Paths: No modifications to `strategies/live/` or `core/risk_manager.py`

**No violations requiring justification.**

## Project Structure

### Documentation (this feature)

```text
specs/002-minimal-mvp-trading/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output (API contracts)
├── checklists/          # Quality checklists
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── strategies/
│   │   ├── base.py              # Existing - Strategy ABC
│   │   ├── context.py           # Existing - StrategyContext
│   │   ├── signals.py           # Existing - Signal dataclass
│   │   ├── registry.py          # Existing - Strategy registry
│   │   ├── engine.py            # Existing - Strategy engine
│   │   ├── indicators/          # NEW - Feature calculations
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Indicator base class
│   │   │   ├── momentum.py      # ROC, price_vs_ma
│   │   │   ├── breakout.py      # price_vs_high
│   │   │   └── volume.py        # volume_zscore, volatility
│   │   ├── factors/             # NEW - Factor composition
│   │   │   ├── __init__.py
│   │   │   ├── base.py          # Factor base class
│   │   │   ├── momentum.py      # momentum_factor
│   │   │   └── breakout.py      # breakout_factor
│   │   └── examples/
│   │       ├── momentum.py      # Existing - MomentumStrategy
│   │       └── trend_breakout.py # NEW - TrendBreakoutStrategy
│   ├── backtest/
│   │   ├── engine.py            # Existing - BacktestEngine
│   │   ├── metrics.py           # Existing - Metrics calculator
│   │   └── attribution.py       # NEW - Factor PnL attribution
│   └── universe/                # NEW - Universe management
│       ├── __init__.py
│       └── static.py            # Hardcoded universe config
└── tests/
    ├── strategies/
    │   ├── indicators/          # NEW - Indicator tests
    │   ├── factors/             # NEW - Factor tests
    │   └── test_trend_breakout.py # NEW - Strategy tests
    └── backtest/
        └── test_attribution.py  # NEW - Attribution tests
```

**Structure Decision**: Extends existing `backend/src/strategies/` with new `indicators/` and `factors/` subpackages. Creates minimal `universe/` module. Adds `attribution.py` to existing `backtest/` module.

## Complexity Tracking

> No violations requiring justification. Design follows existing patterns.

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Indicator storage | In-memory (pandas) | Daily bars only, < 1000 data points per symbol |
| Factor caching | None (recompute) | Fast enough for MVP; can optimize later |
| Universe config | YAML file | Simple, human-readable, no database needed |
| Attribution | Per-trade tracking | Stored in Trade record, not separate table |

## Implementation Phases

### Phase 0: Research (This Plan)
- [x] Understand existing Strategy framework
- [x] Understand existing BacktestEngine
- [ ] Research indicator calculation patterns
- [ ] Research factor composition patterns

### Phase 1: Design (This Plan)
- [ ] Data model for indicators/factors
- [ ] API contracts for backtest with attribution
- [ ] Quickstart guide

### Phase 2: Tasks (via /speckit.tasks)
- Task breakdown for implementation
- TDD test definitions
- Integration plan

## Dependencies on Existing Code

| Component | Location | How Used |
|-----------|----------|----------|
| Strategy ABC | `backend/src/strategies/base.py` | Inherit for TrendBreakoutStrategy |
| Signal | `backend/src/strategies/signals.py` | Generate buy/sell signals |
| StrategyContext | `backend/src/strategies/context.py` | Access portfolio state |
| BacktestEngine | `backend/src/backtest/engine.py` | Run historical simulation |
| MetricsCalculator | `backend/src/backtest/metrics.py` | Calculate Sharpe, drawdown, etc. |
| PaperBroker | `backend/src/broker/paper_broker.py` | Simulated execution |
| BarLoader | `backend/src/backtest/bar_loader.py` | Load CSV historical data |

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Lookahead bias in features | Medium | High | Strict testing with future-only validation (SC-007) |
| Mode divergence (backtest vs paper) | Low | High | Single strategy class, mode-agnostic logic (FR-021) |
| Performance bottleneck | Low | Medium | Vectorized numpy operations; profile if slow |
| Missing historical data | Medium | Medium | Document data requirements; provide sample CSV |
