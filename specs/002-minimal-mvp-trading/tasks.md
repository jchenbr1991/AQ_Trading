# Tasks: Minimal Runnable Trading System

**Input**: Design documents from `/specs/002-minimal-mvp-trading/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as part of the implementation tasks where appropriate (strategy tests, attribution tests).

**Organization**: Tasks are grouped by user story. Each story depends on prior stories per the dependency graph but is testable once its dependencies are complete.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Web app**: `backend/src/`, `frontend/src/`
- Paths based on plan.md structure

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, configuration files, and basic structure

**Note**: Setup and Foundational phase tasks have no [Story] marker as they are shared infrastructure.

- [X] [T001] [P] Create universe configuration file at backend/config/universe.yaml with MU, GLD, GOOG symbols
- [X] [T002] [P] Create strategy configuration file at backend/config/strategies/trend_breakout.yaml with default thresholds and weights
- [X] [T003] [P] Create indicators package structure with __init__.py at backend/src/strategies/indicators/__init__.py
- [X] [T004] [P] Create factors package structure with __init__.py at backend/src/strategies/factors/__init__.py
- [X] [T005] [P] Create universe package structure with __init__.py at backend/src/universe/__init__.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

### Indicator Base Classes

- [X] [T006] [P] Implement base indicator class with warmup handling and lagged calculation to prevent lookahead bias (FR-008) in backend/src/strategies/indicators/base.py
- [X] [T007] [P] Implement momentum indicators (roc_n, price_vs_ma_n) with proper lag (FR-003, FR-004, FR-008) in backend/src/strategies/indicators/momentum.py
- [X] [T008] [P] Implement breakout indicator (price_vs_high_n) with proper lag (FR-005, FR-008) in backend/src/strategies/indicators/breakout.py
- [X] [T009] [P] Implement volume indicators (volume_zscore, volatility_n) with proper lag (FR-006, FR-007, FR-008) in backend/src/strategies/indicators/volume.py

### Factor Composition

- [X] [T010] [P] Implement base factor class with weighted combination in backend/src/strategies/factors/base.py
- [X] [T011] [P] Implement momentum_factor combining roc_20 and price_vs_ma_20 in backend/src/strategies/factors/momentum.py (FR-010)
- [X] [T012] [P] Implement breakout_factor combining price_vs_high_20 and volume_zscore in backend/src/strategies/factors/breakout.py (FR-011)
- [X] [T013] [P] Implement composite factor combining momentum_factor and breakout_factor in backend/src/strategies/factors/composite.py (FR-012)

### Universe Management

- [X] [T014] [P] Implement static universe loader from YAML config in backend/src/universe/static.py (FR-001, FR-002)

### Extended Signal Model

- [X] [T015] [P] Extend Signal dataclass with factor_scores field in backend/src/strategies/signals.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Run Backtest on Historical Data (Priority: P1)

**Goal**: Run backtest on MU, GLD, GOOG using trend/breakout strategy with trade log, performance metrics, and basic factor attribution

**Independent Test**: Run backtest engine with historical daily bars, verify trades generated, positions tracked, metrics calculated, and basic factor attribution displayed

### Strategy Implementation for User Story 1

- [X] [T016] [US1] Implement TrendBreakoutStrategy extending base Strategy with on_market_data in backend/src/strategies/examples/trend_breakout.py (FR-013, FR-014, FR-017, FR-021)
- [X] [T017] [US1] Implement equal-weight position sizing in backend/src/strategies/examples/trend_breakout.py (FR-015)
- [X] [T018] [US1] Implement fixed-risk position sizing as alternative in backend/src/strategies/examples/trend_breakout.py (FR-016)
- [X] [T019] [US1] Add indicator buffer management (price/volume history) in backend/src/strategies/examples/trend_breakout.py per research.md Q3 pattern
- [X] [T020] [US1] Add warmup_bars property returning max lookback (20 bars) in backend/src/strategies/examples/trend_breakout.py
- [X] [T021] [US1] Populate factor_scores on signals in TrendBreakoutStrategy.on_market_data to capture factor values at signal generation (FR-023, FR-025) in backend/src/strategies/examples/trend_breakout.py
- [X] [T022] [US1] Register TrendBreakoutStrategy in strategy registry in backend/src/strategies/registry.py

### Attribution for User Story 1 (required by US1 acceptance scenario 3)

- [X] [T023] [US1] Extend Trade dataclass with entry_factors, exit_factors, and attribution fields in backend/src/backtest/models.py
- [X] [T024] [US1] Persist factor_scores from signals into Trade records during fill processing in backend/src/backtest/engine.py (FR-025)
- [X] [T025] [US1] Implement attribution calculator in backend/src/backtest/attribution.py (FR-023)
- [X] [T026] [US1] Implement attribution normalization to satisfy SC-003 (sum equals total PnL within 0.1%) in backend/src/backtest/attribution.py
- [X] [T027] [US1] Extend BacktestResult with attribution_summary field in backend/src/backtest/models.py
- [X] [T028] [US1] Integrate attribution calculation into BacktestEngine at trade close in backend/src/backtest/engine.py

### Verification for User Story 1

- [X] [T029] [US1] Verify performance metrics output (total return, Sharpe ratio, max drawdown, win rate) from BacktestEngine in backend/tests/backtest/test_metrics.py (FR-024)
- [X] [T030] [US1] Verify complete trade log includes timestamps, prices, quantities, and factor scores at entry/exit in backend/tests/backtest/test_trade_log.py (FR-025)
- [X] [T031] [P] [US1] Create unit tests for TrendBreakoutStrategy in backend/tests/strategies/test_trend_breakout.py
- [X] [T032] [P] [US1] Create unit tests for indicators in backend/tests/strategies/indicators/test_indicators.py
- [X] [T033] [P] [US1] Create unit tests for factors in backend/tests/strategies/factors/test_factors.py
- [X] [T034] [P] [US1] Create unit tests for attribution in backend/tests/backtest/test_attribution.py
- [X] [T035] [US1] Verify lookahead bias prevention with future-only test data in backend/tests/strategies/test_lookahead_bias.py (SC-007)

**Checkpoint**: User Story 1 complete - backtest can run end-to-end with TrendBreakout strategy, including factor attribution

---

## Phase 4: User Story 4 - Factor Attribution API (Priority: P2)

**Goal**: Expose factor attribution via REST API endpoints for programmatic access

**Independent Test**: Call attribution API endpoints and verify response matches BacktestResult attribution data

### Implementation for User Story 4

- [X] [T036] [US4] Implement POST /api/backtest endpoint in backend/src/api/backtest.py per contracts/backtest-api.yaml
- [X] [T037] [US4] Implement GET /api/backtest/{backtest_id}/attribution endpoint in backend/src/api/backtest.py
- [X] [T038] [P] [US4] Create API integration tests for backtest endpoints in backend/tests/api/test_backtest_api.py

**Checkpoint**: User Story 4 complete - attribution accessible via API

---

## Phase 5: User Story 2 - Execute Paper Trading (Priority: P2)

**Goal**: Run same strategy in paper trading mode with live market data and simulated execution

**Independent Test**: Run paper trading for one or more sessions, verify signals match backtest for same data

### Implementation for User Story 2

- [X] [T039] [US2] Verify TrendBreakoutStrategy works with PaperBroker (same logic as backtest per FR-021) in backend/src/strategies/examples/trend_breakout.py
- [X] [T040] [US2] Add paper trading configuration to strategy YAML in backend/config/strategies/trend_breakout.yaml
- [X] [T041] [US2] Implement strategy start/stop API endpoints for paper mode in backend/src/api/strategies.py
- [X] [T042] [US2] Add signal generation timing validation (< 5 seconds per SC-005) in backend/tests/integration/test_paper_timing.py
- [X] [T043] [US2] Create integration test verifying signal consistency between backtest and paper modes (SC-002) in backend/tests/integration/test_mode_consistency.py

**Checkpoint**: User Story 2 complete - paper trading works with identical strategy logic

---

## Phase 6: User Story 3 - Execute Live Trading (Priority: P3)

**Goal**: Execute strategy with real orders through broker adapter

**Independent Test**: Execute one complete trade cycle (entry and exit) on one symbol with minimal position size

### Implementation for User Story 3

- [X] [T044] [US3] Verify TrendBreakoutStrategy works with live broker adapter (same logic as backtest/paper per FR-021, FR-022) in backend/src/strategies/examples/trend_breakout.py
- [X] [T045] [US3] Add live trading configuration to strategy YAML in backend/config/strategies/trend_breakout.yaml
- [X] [T046] [US3] Extend strategy start/stop API to support live mode with broker connection verification in backend/src/api/strategies.py
- [X] [T047] [US3] Add pre-trade validation checks (broker connection, risk limits) before order submission in backend/src/broker/live_broker.py
- [X] [T048] [US3] Create integration test verifying mode-agnostic strategy behavior (SC-002, SC-006) in backend/tests/integration/test_live_mode.py

**Checkpoint**: User Story 3 complete - live trading executes with same strategy logic as backtest/paper

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Performance validation, code cleanup, and documentation

- [X] [T049] [P] Verify backtest performance (1 year x 3 symbols < 30 seconds per SC-004) in backend/tests/performance/test_backtest_timing.py
- [X] [T050] [P] Verify all symbols process identically without symbol-specific branches (SC-001) in backend/tests/strategies/test_trend_breakout.py
- [X] [T051] [P] Update quickstart.md with actual tested commands and expected outputs in specs/002-minimal-mvp-trading/quickstart.md
- [X] [T052] [P] Add logging for strategy operations (signal generation, position changes, attribution) in backend/src/strategies/examples/trend_breakout.py
- [X] [T053] [P] Run full integration test: backtest -> paper -> verify signal consistency in backend/tests/integration/test_full_flow.py
- [X] [T054] [P] Validate attribution sums match portfolio PnL across all test runs (SC-003) in backend/tests/backtest/test_attribution.py

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational - core backtest + attribution functionality
- **User Story 4 (Phase 4)**: Depends on US1 - API endpoints for existing attribution
- **User Story 2 (Phase 5)**: Depends on US1 - paper trading uses same strategy
- **User Story 3 (Phase 6)**: Depends on US1 and US2 - live requires validated paper
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

```
Setup -> Foundation -> US1 (Backtest+Attribution, P1) -> US4 (Attribution API, P2)
                                                      -> US2 (Paper, P2) -> US3 (Live, P3) -> Polish
```

- **User Story 1 (P1)**: Can start after Foundational - Includes attribution per spec.md acceptance scenario 3: "Given factors are calculated during backtest, When I request PnL attribution, Then the system shows which factor contributed"
- **User Story 4 (P2)**: Depends on US1 - Exposes existing attribution via REST API endpoints for programmatic access
- **User Story 2 (P2)**: Depends on US1 (uses same strategy class)
- **User Story 3 (P3)**: Depends on US1 and US2 (requires validated paper trading first)

**Note on Independence**: Each story is testable once its dependencies complete. Stories are sequential (P1 -> P2 -> P3) per spec.md priorities, not parallel.

### Within Each User Story

- Models before services
- Services before endpoints
- Core implementation before integration
- Tests alongside implementation

### Parallel Opportunities

**Phase 2 (Foundational):**
```bash
# Launch all indicator implementations in parallel:
Task: T007 "Implement momentum indicators in backend/src/strategies/indicators/momentum.py"
Task: T008 "Implement breakout indicator in backend/src/strategies/indicators/breakout.py"
Task: T009 "Implement volume indicators in backend/src/strategies/indicators/volume.py"

# Launch all factor implementations in parallel:
Task: T011 "Implement momentum_factor in backend/src/strategies/factors/momentum.py"
Task: T012 "Implement breakout_factor in backend/src/strategies/factors/breakout.py"
```

**Phase 3 (User Story 1):**
```bash
# Launch tests in parallel:
Task: T031 "Create unit tests for TrendBreakoutStrategy"
Task: T032 "Create unit tests for indicators"
Task: T033 "Create unit tests for factors"
Task: T034 "Create unit tests for attribution"
```

**Phase 7 (Polish):**
```bash
# Launch all performance validations in parallel:
Task: T049 "Verify backtest performance"
Task: T050 "Verify all symbols process identically"
Task: T051 "Update quickstart.md"
Task: T052 "Add logging for strategy operations"
Task: T053 "Run full integration test"
Task: T054 "Validate attribution sums"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T005)
2. Complete Phase 2: Foundational (T006-T015) - CRITICAL blocks all stories
3. Complete Phase 3: User Story 1 (T016-T035) - includes attribution per acceptance scenario 3
4. **STOP and VALIDATE**: Run backtest with TrendBreakout strategy, verify attribution works
5. Deploy/demo if ready - this is the MVP!

### Incremental Delivery

1. Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently -> Deploy/Demo (MVP!)
3. Add User Story 4 -> Test attribution -> Deploy/Demo
4. Add User Story 2 -> Test paper trading -> Deploy/Demo
5. Add User Story 3 -> Test live (carefully!) -> Deploy/Demo
6. Each story adds value without breaking previous stories

### Suggested MVP Scope

**MVP = User Story 1 (Backtest with Attribution) only**
- Total tasks for MVP: T001-T035 (35 tasks)
- Delivers working backtest with TrendBreakout strategy
- Performance metrics (FR-024), complete trade log with factor scores (FR-025), and factor attribution (FR-023)
- Satisfies all 3 US1 acceptance scenarios including attribution
- Foundation for all subsequent stories

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence

## Task Summary

| Phase | Tasks | Description |
|-------|-------|-------------|
| Phase 1: Setup | T001-T005 (5) | Configuration and package structure |
| Phase 2: Foundational | T006-T015 (10) | Indicators, factors, universe, signal extension |
| Phase 3: US1 Backtest | T016-T035 (20) | TrendBreakoutStrategy, attribution, metrics, tests |
| Phase 4: US4 Attribution API | T036-T038 (3) | API endpoints for attribution |
| Phase 5: US2 Paper | T039-T043 (5) | Paper trading mode validation |
| Phase 6: US3 Live | T044-T048 (5) | Live trading mode |
| Phase 7: Polish | T049-T054 (6) | Performance validation and cleanup |
| **Total** | **54 tasks** | |

### Tasks by User Story

| User Story | Tasks | Priority |
|------------|-------|----------|
| US1: Backtest + Attribution | T016-T035 (20) | P1 |
| US2: Paper Trading | T039-T043 (5) | P2 |
| US3: Live Trading | T044-T048 (5) | P3 |
| US4: Attribution API | T036-T038 (3) | P2 |

### Parallel Opportunities Identified

- Phase 1: All 5 tasks (T001-T005) are [P] marked for parallel execution
- Phase 2: All 10 tasks (T006-T015) are [P] marked for parallel execution
- Phase 3: 4 parallel test tasks (T031-T034)
- Phase 7: All 6 tasks (T049-T054) are [P] marked for parallel execution

### Independent Test Criteria

| Story | Test Criteria |
|-------|---------------|
| US1 | Run backtest engine with historical bars, verify trades generated, metrics calculated, attribution displayed |
| US2 | Run paper trading, verify signals match backtest for same data |
| US3 | Execute one complete trade cycle with minimal position |
| US4 | Call attribution API endpoints, verify response matches BacktestResult data |
