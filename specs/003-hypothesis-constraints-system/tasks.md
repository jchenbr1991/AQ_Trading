# Tasks: L0 Hypothesis + L1 Constraints System

**Input**: Design documents from `/specs/003-hypothesis-constraints-system/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/openapi.yaml

**Tests**: TDD is required per plan.md - tests are written FIRST and must FAIL before implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `backend/src/governance/` for source code
- **Config**: `config/` for YAML configuration files
- **Tests**: `backend/tests/governance/` for test files
- **API**: `backend/src/api/routes/governance.py` for API endpoints

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and governance module structure

- [X] T001 Create governance module directory structure per plan.md in `backend/src/governance/`
- [X] T002 [P] Create `backend/src/governance/__init__.py` with module exports
- [X] T003 [P] Create config directory structure in `config/hypotheses/`, `config/constraints/`, `config/filters/`, `config/universe/`, `config/factors/`, `config/regimes/`
- [X] T004 [P] Add pydantic-yaml and APScheduler to `backend/pyproject.toml` dependencies
- [X] T005 [P] Create test directory structure in `backend/tests/governance/` with `__init__.py`
- [X] T006 Create PostgreSQL migration for `governance_audit_log` table in `backend/src/db/migrations/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T007 Implement base Pydantic models shared across governance in `backend/src/governance/models.py`
- [X] T008 [P] Implement Redis cache wrapper for constraint resolution in `backend/src/governance/cache.py`
- [X] T009 [P] Create YAML loader utility with pydantic-yaml integration in `backend/src/governance/utils/yaml_loader.py`
- [X] T010 [P] Implement audit logger base class in `backend/src/governance/audit/logger.py`
- [X] T011 Create governance API router skeleton in `backend/src/api/routes/governance.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Record and Manage Human Hypotheses (Priority: P1) 🎯 MVP

**Goal**: Enable human traders to record, validate, and manage hypothesis YAML files with mandatory falsifiers

**Independent Test**: Can create a hypothesis YAML file with required fields, and the system correctly parses it and validates that falsifiers are present.

### Tests for User Story 1 (TDD - write FIRST, ensure FAIL)

- [X] T012 [P] [US1] Write hypothesis loader tests in `backend/tests/governance/test_hypothesis_loader.py`
- [X] T013 [P] [US1] Write hypothesis registry tests in `backend/tests/governance/test_hypothesis_registry.py`

### Implementation for User Story 1

- [X] T014 [P] [US1] Create Hypothesis Pydantic models in `backend/src/governance/hypothesis/models.py`
- [X] T015 [P] [US1] Create Falsifier Pydantic model in `backend/src/governance/hypothesis/models.py`
- [X] T016 [P] [US1] Create HypothesisScope and Evidence models in `backend/src/governance/hypothesis/models.py`
- [X] T017 [US1] Implement hypothesis YAML loader with validation in `backend/src/governance/hypothesis/loader.py`
- [X] T018 [US1] Implement `gate:hypothesis_requires_falsifiers` validation in `backend/src/governance/hypothesis/loader.py`
- [X] T019 [US1] Implement HypothesisRegistry with status filtering in `backend/src/governance/hypothesis/registry.py`
- [X] T020 [US1] Create example hypothesis YAML in `config/hypotheses/_example.yml`
- [X] T021 [US1] Add hypothesis API endpoints (list, get) in `backend/src/api/routes/governance.py`

**Checkpoint**: User Story 1 complete - hypotheses can be loaded, validated, and queried

---

## Phase 4: User Story 2 - Enforce Constraints Without Polluting Alpha (Priority: P1) ✅ COMPLETED

**Goal**: Implement constraint loading and lint rules ensuring constraints NEVER affect alpha calculations

**Independent Test**: Can configure a constraint that modifies risk budget, and verify via lint/gate that no alpha computation code path reads hypothesis or constraint files.

### Tests for User Story 2 (TDD - write FIRST, ensure FAIL)

- [X] T022 [P] [US2] Write constraint loader tests in `backend/tests/governance/test_constraint_loader.py`
- [X] T023 [P] [US2] Write constraint resolver tests in `backend/tests/governance/test_constraint_resolver.py`
- [X] T024 [P] [US2] Write alpha path lint tests in `backend/tests/governance/lint/test_alpha_path_lint.py`
- [X] T025 [P] [US2] Write allowlist lint tests in `backend/tests/governance/lint/test_allowlist_lint.py`

### Implementation for User Story 2

- [X] T026 [P] [US2] Create Constraint Pydantic models in `backend/src/governance/constraints/models.py`
- [X] T027 [P] [US2] Create ConstraintActions model with allowlisted fields in `backend/src/governance/constraints/models.py`
- [X] T028 [P] [US2] Create ConstraintGuardrails model in `backend/src/governance/constraints/models.py`
- [X] T029 [US2] Implement constraint YAML loader in `backend/src/governance/constraints/loader.py`
- [X] T030 [US2] Implement ConstraintRegistry in `backend/src/governance/constraints/registry.py`
- [X] T031 [US2] Implement constraint resolver (activation logic) in `backend/src/governance/constraints/resolver.py`
- [X] T032 [US2] Implement ResolvedConstraints model in `backend/src/governance/constraints/models.py`
- [X] T033 [US2] Implement `lint:no_hypothesis_in_alpha_path` AST checker in `backend/src/governance/lint/alpha_path.py`
- [X] T034 [US2] Implement `lint:no_constraint_in_alpha_path` AST checker in `backend/src/governance/lint/alpha_path.py`
- [X] T035 [US2] Implement `lint:constraint_actions_allowlist` validator in `backend/src/governance/lint/allowlist.py`
- [X] T036 [US2] Create example constraint YAML in `config/constraints/_example.yml`
- [X] T037 [US2] Add constraint API endpoints (list, get, resolve) in `backend/src/api/routes/governance.py`
- [X] T038 [US2] Add lint API endpoints in `backend/src/api/routes/governance.py`

**Checkpoint**: User Story 2 complete - constraints work, lint rules enforce red line ✅

---

## Phase 5: User Story 3 - Build Active Pool from Universe (Priority: P2)

**Goal**: Create deterministic pool builder with structural filters and hypothesis gating

**Independent Test**: Can configure structural filters and hypothesis allowlist/denylist, run pool builder, and verify deterministic output with audit trail.

### Tests for User Story 3 (TDD - write FIRST, ensure FAIL)

- [x] T039 [P] [US3] Write pool builder tests in `backend/tests/governance/test_pool_builder.py`
- [x] T040 [P] [US3] Write structural filter tests in `backend/tests/governance/test_pool_filters.py`

### Implementation for User Story 3

- [x] T041 [P] [US3] Create Pool and PoolAuditEntry models in `backend/src/governance/pool/models.py`
- [x] T042 [P] [US3] Create StructuralFilters model in `backend/src/governance/pool/models.py`
- [x] T043 [US3] Implement structural filters in `backend/src/governance/pool/filters.py`
- [x] T044 [US3] Implement pool builder with hash-based versioning in `backend/src/governance/pool/builder.py`
- [x] T045 [US3] Implement empty pool error handling in `backend/src/governance/pool/builder.py`
- [x] T046 [US3] Implement hypothesis gating (allowlist/denylist) in `backend/src/governance/pool/builder.py`
- [x] T047 [US3] Create structural filters config in `config/filters/structural_filters.yml`
- [x] T048 [US3] Create base universe config in `config/universe/base_universe.yml`
- [x] T049 [US3] Add pool API endpoints (get, rebuild, audit) in `backend/src/api/routes/governance.py`

**Checkpoint**: User Story 3 complete - pool building works with audit trail

---

## Phase 6: User Story 4 - Detect Falsified Hypotheses (Priority: P2)

**Goal**: Implement automatic falsifier checking with scheduled monitoring and alerts

**Independent Test**: Can configure a falsifier rule with a metric threshold, simulate metric data exceeding threshold, and verify review alert is generated.

### Tests for User Story 4 (TDD - write FIRST, ensure FAIL)

- [x] T050 [P] [US4] Write falsifier checker tests in `backend/tests/governance/test_falsifier.py`
- [x] T051 [P] [US4] Write alert generation tests in `backend/tests/governance/test_alerts.py`

### Implementation for User Story 4

- [x] T052 [P] [US4] Create FalsifierCheckResult model in `backend/src/governance/monitoring/models.py`
- [x] T053 [P] [US4] Create Alert model in `backend/src/governance/monitoring/models.py`
- [x] T054 [US4] Implement MetricRegistry pattern for falsifier evaluation in `backend/src/governance/monitoring/metrics.py`
- [x] T055 [US4] Implement falsifier checker logic in `backend/src/governance/monitoring/falsifier.py`
- [x] T056 [US4] Implement alert generation in `backend/src/governance/monitoring/alerts.py`
- [x] T057 [US4] Implement scheduled falsifier check runner with APScheduler in `backend/src/governance/monitoring/scheduler.py`
- [x] T058 [US4] Implement `disabled_if_falsified` constraint deactivation in `backend/src/governance/constraints/resolver.py`
- [x] T059 [US4] Add falsifier check API endpoint in `backend/src/api/routes/governance.py`

**Checkpoint**: User Story 4 complete - falsifiers are monitored and alerts generated

---

## Phase 7: User Story 5 - Audit Constraint Effects (Priority: P3)

**Goal**: Complete audit logging for all governance effects on trading decisions

**Independent Test**: Can execute a strategy with active constraints, then query audit logs to see which constraints affected which decisions.

### Tests for User Story 5 (TDD - write FIRST, ensure FAIL)

- [x] T060 [P] [US5] Write audit logger tests in `backend/tests/governance/test_audit_logger.py`

### Implementation for User Story 5

- [x] T061 [P] [US5] Create AuditLogEntry and AuditEventType models in `backend/src/governance/audit/models.py`
- [x] T062 [US5] Implement audit log writer with PostgreSQL in `backend/src/governance/audit/logger.py`
- [x] T063 [US5] Add audit logging hooks to constraint resolver in `backend/src/governance/constraints/resolver.py`
- [x] T064 [US5] Add audit logging hooks to falsifier checker in `backend/src/governance/monitoring/falsifier.py`
- [x] T065 [US5] Add audit API endpoint with filtering in `backend/src/api/routes/governance.py`

**Checkpoint**: User Story 5 complete - all governance effects are auditable

---

## Phase 8: User Story 6 - Register Factors with Failure Rules (Priority: P2)

**Goal**: Factor registry with mandatory failure rules that auto-disable degraded factors

**Independent Test**: Can register a factor with failure rule, simulate IC degradation below threshold, and verify factor is disabled.

### Tests for User Story 6 (TDD - write FIRST, ensure FAIL)

- [x] T066 [P] [US6] Write factor registry tests in `backend/tests/governance/test_factor_registry.py`

### Implementation for User Story 6

- [x] T067 [P] [US6] Create Factor and FactorFailureRule models in `backend/src/governance/factors/models.py`
- [x] T068 [US6] Implement factor loader with failure rule validation in `backend/src/governance/factors/loader.py`
- [x] T069 [US6] Implement `gate:factor_requires_failure_rule` in `backend/src/governance/factors/loader.py`
- [x] T070 [US6] Implement FactorRegistry with status tracking in `backend/src/governance/factors/registry.py`
- [x] T071 [US6] Create example factor config in `config/factors/_example.yml`

**Checkpoint**: User Story 6 complete - factors have mandatory failure rules

---

## Phase 9: User Story 7 - Apply Regime-Based Position Pacing (Priority: P3)

**Goal**: Regime detection with automatic position limit adjustments based on market state

**Independent Test**: Can configure regime detector, simulate high volatility conditions, verify regime transitions to STRESS, and confirm position limits are tightened.

### Tests for User Story 7 (TDD - write FIRST, ensure FAIL)

- [x] T072 [P] [US7] Write regime detector tests in `backend/tests/governance/test_regime_detector.py`

### Implementation for User Story 7

- [x] T073 [P] [US7] Create Regime and RegimeThresholds models in `backend/src/governance/regime/models.py`
- [x] T074 [US7] Implement regime detector in `backend/src/governance/regime/detector.py`
- [x] T075 [US7] Create regime config in `config/regimes/regime_v1.yml`
- [x] T076 [US7] Add regime API endpoint in `backend/src/api/routes/governance.py`

**Checkpoint**: User Story 7 complete - regime affects position pacing

---

## Phase 10: Strategy Interface Integration

**Goal**: Integrate governance layer with existing strategy framework

### Tests

- [x] T077 [P] Write strategy interface integration tests in `backend/tests/integration/test_governance_integration.py`

### Implementation

- [x] T078 Update StrategyContext with pre-resolved governance inputs (pool, regime, risk/timing scalars) in `backend/src/governance/context.py`
- [x] T079 Ensure StrategyContext does NOT expose raw Constraint objects - only scalar values in `backend/src/governance/context.py`
- [x] T080 Add governance initialization to main application startup in `backend/src/api/routes/governance.py`

**Checkpoint**: Strategy receives governance inputs correctly

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T081 [P] Add CI lint rules for alpha path isolation in `.github/workflows/lint.yml`
- [x] T082 [P] Add all gate validations to CI pipeline in `.github/workflows/gates.yml`
- [x] T083 Validate quickstart.md scenarios work end-to-end in `specs/003-hypothesis-constraints-system/quickstart.md`
- [x] T084 [P] Add __all__ exports to all governance `__init__.py` files in `backend/src/governance/`
- [x] T085 Code cleanup and docstrings for public APIs in `backend/src/governance/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-9)**: All depend on Foundational phase completion
  - US1 and US2 (P1) should be completed first as they are foundational
  - US3, US4, US6 (P2) can proceed after US1/US2
  - US5, US7 (P3) can proceed after dependencies
- **Integration (Phase 10)**: Depends on US1-US4 completion
- **Polish (Phase 11)**: Depends on all user stories being complete

### User Story Dependencies

```
US1 (Hypothesis Registry) ─────────────────────────────────┐
                                                            ├─► Integration
US2 (Constraints/Lint) ────► US4 (Falsifier Monitoring) ───┤
        │                                                   │
        └──────────────────► US5 (Audit Logging) ──────────┤
                                                            │
US3 (Pool Builder) ─────────────────────────────────────────┤
                                                            │
US6 (Factor Registry) ──────────────────────────────────────┤
                                                            │
US7 (Regime Detection) ─────────────────────────────────────┘
```

### Within Each User Story

1. Tests (TDD) MUST be written and FAIL before implementation
2. Models before loaders
3. Loaders before registries
4. Registries before resolvers
5. Core implementation before API endpoints
6. Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (within Phase 2)
- Once Foundational phase completes, US1 and US2 can start in parallel
- Within each story, all tests marked [P] can run in parallel
- Models within a story marked [P] can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Write hypothesis loader tests in backend/tests/governance/test_hypothesis_loader.py"
Task: "Write hypothesis registry tests in backend/tests/governance/test_hypothesis_registry.py"

# Launch all models for User Story 1 together:
Task: "Create Hypothesis Pydantic models in backend/src/governance/hypothesis/models.py"
Task: "Create Falsifier Pydantic model in backend/src/governance/hypothesis/models.py"
Task: "Create HypothesisScope and Evidence models in backend/src/governance/hypothesis/models.py"
```

---

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Write constraint loader tests"
Task: "Write constraint resolver tests"
Task: "Write alpha path lint tests"
Task: "Write allowlist lint tests"

# Launch all models together:
Task: "Create Constraint Pydantic models"
Task: "Create ConstraintActions model"
Task: "Create ConstraintGuardrails model"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Hypothesis Registry)
4. Complete Phase 4: User Story 2 (Constraints + Lint)
5. **STOP and VALIDATE**: Test US1 + US2 independently
6. Deploy/demo - red line enforcement is now active

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add US1 + US2 → Test independently → MVP (governance core!)
3. Add US3 (Pool Builder) → Test independently → Enhanced universe control
4. Add US4 (Falsifier Monitoring) → Test independently → Auto-invalidation
5. Add US5 (Audit) → Test independently → Compliance ready
6. Add US6 + US7 → Test independently → Full governance

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 + 2 (P1 - critical path)
   - Developer B: User Story 3 (Pool Builder)
   - Developer C: User Story 6 (Factor Registry)
3. After P1 stories complete:
   - Developer A: User Story 4 (depends on US2)
   - Developer B: User Story 5 (depends on US2)
   - Developer C: User Story 7 (independent)

---

## Task Summary

| Phase | Story | Task Count | Parallel Tasks |
|-------|-------|------------|----------------|
| 1. Setup | - | 6 | 4 |
| 2. Foundational | - | 5 | 3 |
| 3. US1 (P1) | Record Hypotheses | 10 | 5 |
| 4. US2 (P1) | Enforce Constraints | 17 | 7 |
| 5. US3 (P2) | Build Pool | 11 | 4 |
| 6. US4 (P2) | Falsifier Monitoring | 10 | 4 |
| 7. US5 (P3) | Audit Logging | 6 | 2 |
| 8. US6 (P2) | Factor Registry | 6 | 2 |
| 9. US7 (P3) | Regime Detection | 5 | 2 |
| 10. Integration | - | 4 | 1 |
| 11. Polish | - | 5 | 3 |
| **TOTAL** | | **85** | **37** |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- TDD: Verify tests FAIL before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Red Line: NEVER allow hypothesis/constraint imports in alpha paths
