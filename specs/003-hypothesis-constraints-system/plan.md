# Implementation Plan: L0 Hypothesis + L1 Constraints System

**Branch**: `003-hypothesis-constraints-system` | **Date**: 2026-02-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-hypothesis-constraints-system/spec.md`

## Summary

Implement a governance layer that separates human "worldview" hypotheses (L0) from quantitative alpha generation. The system introduces:
1. **Hypothesis Registry** - YAML-based human beliefs with mandatory falsifiers
2. **Constraints Registry** - Allowlisted actions that affect risk/timing, never alpha
3. **Pool Builder** - Deterministic universe filtering with audit trail
4. **Red Line Enforcement** - Lint/gate rules preventing hypothesis/constraint data in alpha paths
5. **Falsifier Monitoring** - Scheduled checks with alerts
6. **Audit Logging** - Complete traceability of constraint effects

**Critical Red Line**: Hypotheses and Constraints NEVER contribute to alpha (factor synthesis). They only influence enable/disable, universe/pool, risk budgets, veto rules, and position pacing.

## Technical Context

**Language/Version**: Python 3.11+ (backend governance layer)
**Primary Dependencies**: FastAPI, Pydantic, pydantic-yaml, existing Strategy framework (`backend/src/strategies/`)
**Storage**: PostgreSQL (audit logs), YAML files (config), Redis (resolved constraints cache)
**Testing**: pytest with TDD discipline
**Target Platform**: Linux server (Docker-ready)
**Project Type**: Web application (existing backend/frontend structure)
**Performance Goals**: Config parsing <100ms, constraint resolution <10ms per symbol
**Constraints**: No impact on trading hot path latency
**Scale/Scope**: ~50-100 hypotheses/constraints, 500+ symbol universe

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| Air Gap (Agents not in hot path) | PASS | Governance layer follows same pattern - configs read async, resolved constraints cached in Redis |
| Graceful Degradation | PASS | Missing configs → use defaults, falsifier check failure → log warning and continue |
| Test-First (TDD) | REQUIRED | All lint/gate rules must have tests before implementation |
| Red Line Enforcement | PASS | Core feature - lint rules enforce alpha path isolation |

## Project Structure

### Documentation (this feature)

```text
specs/003-hypothesis-constraints-system/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
backend/
├── src/
│   ├── governance/                    # NEW: Core governance module
│   │   ├── __init__.py
│   │   ├── hypothesis/
│   │   │   ├── __init__.py
│   │   │   ├── models.py              # Hypothesis Pydantic models
│   │   │   ├── loader.py              # YAML loading and validation
│   │   │   └── registry.py            # Hypothesis registry
│   │   ├── constraints/
│   │   │   ├── __init__.py
│   │   │   ├── models.py              # Constraint Pydantic models
│   │   │   ├── loader.py              # YAML loading and validation
│   │   │   ├── resolver.py            # Constraint resolution logic
│   │   │   └── registry.py            # Constraint registry
│   │   ├── pool/
│   │   │   ├── __init__.py
│   │   │   ├── builder.py             # Pool builder (filters + gating)
│   │   │   ├── filters.py             # Structural filters
│   │   │   └── models.py              # Pool output models
│   │   ├── regime/
│   │   │   ├── __init__.py
│   │   │   ├── detector.py            # Regime state detection
│   │   │   └── models.py              # Regime models
│   │   ├── factors/
│   │   │   ├── __init__.py
│   │   │   ├── registry.py            # Factor registry with failure rules
│   │   │   └── models.py              # Factor config models
│   │   ├── monitoring/
│   │   │   ├── __init__.py
│   │   │   ├── falsifier.py           # Falsifier check scheduler
│   │   │   └── alerts.py              # Alert generation
│   │   ├── audit/
│   │   │   ├── __init__.py
│   │   │   ├── logger.py              # Audit log writer
│   │   │   └── models.py              # Audit log models
│   │   └── lint/
│   │       ├── __init__.py
│   │       ├── alpha_path.py          # no_hypothesis/constraint_in_alpha_path
│   │       └── allowlist.py           # constraint_actions_allowlist
│   ├── api/
│   │   └── routes/
│   │       └── governance.py          # NEW: Governance API endpoints
│   └── strategies/
│       └── interface.py               # MODIFIED: Add governance inputs

config/                                # NEW: Configuration directory
├── hypotheses/                        # Hypothesis YAML files
│   └── _example.yml
├── constraints/                       # Constraint YAML files
│   └── _example.yml
├── filters/
│   └── structural_filters.yml         # Structural filter config
├── universe/
│   └── base_universe.yml              # Base universe definition
├── factors/                           # Factor registry configs
│   └── _example.yml
└── regimes/
    └── regime_v1.yml                  # Regime detection config

backend/tests/
├── governance/                        # NEW: Governance tests
│   ├── test_hypothesis_loader.py
│   ├── test_constraint_resolver.py
│   ├── test_pool_builder.py
│   ├── test_falsifier.py
│   ├── test_regime_detector.py
│   ├── test_factor_registry.py
│   ├── test_alerts.py
│   ├── test_audit_logger.py
│   └── lint/
│       ├── test_alpha_path_lint.py
│       └── test_allowlist_lint.py
└── integration/
    └── test_governance_integration.py
```

**Structure Decision**: Extend existing `backend/src/` with new `governance/` module. Configuration lives in new `config/` directory at repo root. This follows the existing pattern (strategies, risk, etc.) while keeping governance concerns isolated.

## Complexity Tracking

> No constitution violations requiring justification.

## Module Boundaries

### M1: Configuration and Parsing Pipeline

| Module | Responsibility | Dependencies | Outputs |
|--------|---------------|--------------|---------|
| `governance.hypothesis.loader` | Parse and validate hypothesis YAML | pydantic-yaml | `Hypothesis` objects |
| `governance.hypothesis.registry` | Store and query hypotheses | loader | Active hypotheses by status |
| `governance.constraints.loader` | Parse and validate constraint YAML | pydantic-yaml | `Constraint` objects |
| `governance.constraints.resolver` | Resolve active constraints for symbols | registry, hypothesis.registry | `ResolvedConstraints` |
| `governance.pool.filters` | Apply structural filters | Pydantic | Filtered symbol list |
| `governance.pool.builder` | Build active pool with audit | filters, constraints.resolver | `Pool` with audit trail |
| `governance.lint.alpha_path` | Check hypothesis/constraint imports | AST analysis | Pass/fail |
| `governance.lint.allowlist` | Check constraint action fields | Pydantic validation | Pass/fail |

### M2: Audit and Invalidation

| Module | Responsibility | Dependencies | Outputs |
|--------|---------------|--------------|---------|
| `governance.monitoring.falsifier` | Schedule and run falsifier checks | hypothesis.registry, data pipeline | `FalsifierResult` |
| `governance.monitoring.alerts` | Generate and deliver alerts | falsifier | Alert notifications |
| `governance.audit.logger` | Log constraint effects | SQLAlchemy | Audit records |
| `governance.factors.registry` | Factor registry with failure rules | Pydantic | Factor status |
| `governance.regime.detector` | Detect market regime | market data | Regime state |

## Test Strategy

### Unit Tests (TDD - tests first)

| Test File | Coverage Target |
|-----------|----------------|
| `test_hypothesis_loader.py` | YAML parsing, validation, falsifier requirements |
| `test_constraint_resolver.py` | Activation logic, disabled_if_falsified |
| `test_pool_builder.py` | Filter application, determinism, empty pool error |
| `test_falsifier.py` | Metric evaluation, threshold comparison |
| `test_regime_detector.py` | Regime state transitions, threshold detection |
| `test_factor_registry.py` | Factor loading, failure rule validation |
| `test_alerts.py` | Alert generation, notification delivery |
| `test_audit_logger.py` | Audit log entry creation, query filtering |
| `test_alpha_path_lint.py` | Import detection in alpha code |
| `test_allowlist_lint.py` | Action field validation |

### Integration Tests

| Test File | Coverage Target |
|-----------|----------------|
| `test_governance_integration.py` | End-to-end: config → pool → strategy interface |
| `test_lint_ci.py` | Lint rules run in CI context |

### Gate Tests (CI/CD)

- `gate:hypothesis_requires_falsifiers` - Reject hypothesis without falsifiers
- `gate:factor_requires_failure_rule` - Reject factor without failure rule
- `lint:no_hypothesis_in_alpha_path` - Fail if hypothesis imported in factors
- `lint:no_constraint_in_alpha_path` - Fail if constraint imported in factors
- `lint:constraint_actions_allowlist` - Fail if unknown action field

## Implementation Phases

### Phase 1: Core Config Pipeline (M1 scope)

1. **Hypothesis Registry** (FR-001 to FR-004)
   - Pydantic models with all required fields
   - YAML loader with validation
   - Gate: falsifiers required for ACTIVE status

2. **Constraints Registry** (FR-005 to FR-007)
   - Pydantic models with allowlisted actions
   - YAML loader with validation
   - Resolver: activate based on linked hypothesis status

3. **Lint Rules** (FR-008, FR-008a, FR-009)
   - AST-based import checker for alpha paths
   - Action field allowlist validator

4. **Pool Builder** (FR-012 to FR-015)
   - Structural filters implementation
   - Hypothesis gating (allowlist/denylist)
   - Deterministic output with audit trail
   - Empty pool error handling

5. **Strategy Interface Update** (FR-022 to FR-024)
   - Extend StrategyContext with: pool, alpha, regime
   - Pass only pre-resolved risk/timing parameters (risk_budget_multiplier, stop_mode, veto_downgrade, etc.) via dedicated fields—NOT raw Constraint objects
   - Strategy receives scalar values (e.g., `risk_budget_multiplier: float = 1.0`), preventing any runtime access to constraint logic or hypothesis data
   - Ensure strategy cannot read hypothesis directly

### Phase 2: Monitoring and Audit (M2 scope)

1. **Falsifier Monitoring** (FR-025 to FR-027)
   - Scheduled check runner
   - Metric evaluation against thresholds
   - Alert generation and notification

2. **Audit Logging** (FR-028 to FR-030)
   - Constraint activation logging
   - Falsifier check result logging
   - Risk adjustment logging

3. **Factor Registry** (FR-017, FR-018)
   - Factor config models
   - Failure rule validation gate

4. **Regime Detection** (FR-019 to FR-021)
   - Regime state model (NORMAL/TRANSITION/STRESS)
   - Configurable threshold detection

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Constraint leaks into alpha | Lint rules in CI with zero tolerance |
| Stale hypothesis affects trading | Falsifier monitoring with scheduled checks |
| Empty pool halts trading | Explicit error handling (FR-015) |
| Config parsing errors | Strict Pydantic validation, fail-fast on invalid config |
| Performance impact on hot path | Redis caching of resolved constraints |

## Dependencies

### External
- pydantic-yaml (type-safe YAML parsing with Pydantic integration)
- Pydantic (validation)
- APScheduler or similar (falsifier scheduling)

### Internal
- `backend/src/strategies/` - Strategy interface integration
- `backend/src/db/` - Audit log storage
- `backend/src/db/redis.py` - Constraint cache
