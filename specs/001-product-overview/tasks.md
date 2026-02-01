# Tasks: AQ Trading Phase 3 Implementation

**Input**: Design documents from `/specs/001-product-overview/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Scope**: Phase 3 implementation only. User Stories 1, 2, 3, 5 are already completed (Phases 1-2).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US4, US6)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory structure for Phase 3 features

- [x] T001 [US6] Create agents/ directory structure: `agents/{prompts,tools,outputs}/`
- [x] T002 [P] [US4] Create derivatives/ module directory: `backend/src/derivatives/`
- [x] T003 [P] [US4/US6] Add Phase 3 dependencies to `backend/pyproject.toml` (if needed)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 [US4] Create DerivativeContract model in `backend/src/models/derivative_contract.py`
- [x] T005 [P] [US6] Create AgentResult model in `backend/src/models/agent_result.py`
- [x] T006 [US4] Create database migration for derivative_contracts table in `backend/alembic/versions/`
- [x] T007 [P] [US6] Create database migration for agent_results table in `backend/alembic/versions/`
- [x] T008 [US6] Add Redis keys schema for agent outputs in `backend/src/db/redis_keys.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 4 - 管理衍生品生命周期 (Priority: P3)

**Goal**: Auto-track derivative expirations, alert before expiry, handle assignment/roll-over

**Independent Test**: Hold a near-expiry option position, verify expiration warnings and suggested actions

**Acceptance Criteria**:
- SC-011: User receives expiration warning at least 5 days before expiry
- FR-016: System tracks derivative expiry dates
- FR-017: System supports futures auto-roll
- FR-018: System handles options assignment/exercise

### Implementation for User Story 4

- [x] T009 [US4] Implement ExpirationManager service in `backend/src/derivatives/expiration_manager.py`
  - Daily expiration check (configurable warning_days=5)
  - Query derivative positions by expiry date
  - Emit expiration alerts
- [x] T010 [US4] Implement AssignmentHandler in `backend/src/derivatives/assignment_handler.py`
  - Calculate ITM/OTM status on expiry day
  - Estimate resulting stock position from options exercise
  - Pre-create placeholder positions
- [x] T011 [US4] Implement FuturesRollManager in `backend/src/derivatives/futures_roll.py`
  - Support calendar_spread and close_open strategies
  - Configurable per-underlying roll strategy
  - days_before_expiry configuration
- [x] T012 [P] [US4] Create expiration API routes in `backend/src/api/routes/derivatives.py`
  - GET /api/derivatives/expiring - List expiring positions
  - GET /api/derivatives/expiring/{days} - Positions expiring within N days
  - POST /api/derivatives/roll/{symbol} - Trigger manual roll
- [x] T013 [P] [US4] Add expiration worker to `backend/src/workers/expiration_worker.py`
  - Schedule daily check before market open
  - Integrate with existing alerting system
- [x] T014 [US4] Add derivatives config to `backend/config/derivatives.yaml`
  - warning_days: 5
  - futures_roll strategies per underlying
- [x] T015 [P] [US4] Add Derivatives page component in `frontend/src/pages/DerivativesPage.tsx`
  - Display expiring positions table
  - Show assignment estimates for ITM options
  - Roll action buttons
- [x] T016 [US4] Generate TypeScript types for derivatives API in `frontend/src/api/generated/`

**Checkpoint**: User Story 4 complete - derivative lifecycle management functional

---

## Phase 4: User Story 6 - AI 代理辅助优化 (Priority: P4)

**Goal**: AI agents analyze trading performance, suggest optimizations, adjust risk parameters

**Independent Test**: Trigger strategy optimization analysis, verify agent report and parameter suggestions

**Acceptance Criteria**:
- SC-013: Agent suggestions include out-of-sample validation
- SC-014: Risk bias adjustments take effect within 1 minute
- FR-019: Support AI agent subsystem
- FR-020: Agents have clear permission boundaries (read-only, parameters only)
- FR-021: Graceful degradation when components fail
- FR-022: Analyst agent generates sentiment factors
- FR-023: Researcher agent auto-tunes with overfitting protection

### Implementation for User Story 6

#### Agent Core Infrastructure

- [x] T017 [US6] Implement AgentDispatcher in `agents/dispatcher.py`
  - Manage agent lifecycle (spawn, monitor, terminate)
  - Route tasks to appropriate agent roles
  - Capture results to AgentResult table
- [x] T018 [US6] Implement Permission model in `agents/permissions.py`
  - Role-based access control matrix
  - Validate tool calls against permissions
  - Block unauthorized operations
- [x] T019 [P] [US6] Create base Agent class in `agents/base.py`
  - Common agent interface
  - Tool registration and validation

#### Agent Roles

- [x] T020 [P] [US6] Create Researcher agent prompt in `agents/prompts/researcher.py`
  - Strategy analysis and optimization
  - Parameter sensitivity testing
  - Walk-forward validation requirements
- [x] T021 [P] [US6] Create Analyst agent prompt in `agents/prompts/analyst.py`
  - Market data analysis
  - Sentiment factor generation
  - News/social media processing
- [x] T022 [P] [US6] Create RiskController agent prompt in `agents/prompts/risk_controller.py`
  - Portfolio risk assessment
  - Dynamic risk bias adjustment
  - VIX-based scaling
- [x] T023 [P] [US6] Create Ops agent prompt in `agents/prompts/ops.py`
  - Reconciliation analysis (local vs broker positions)
  - Discrepancy investigation and fix suggestions
  - System health monitoring

#### Agent Tools

- [x] T024 [P] [US6] Implement backtest tool in `agents/tools/backtest.py`
  - Run backtest with specified parameters
  - Return performance metrics
- [x] T025 [P] [US6] Implement market_data tool in `agents/tools/market_data.py`
  - Query historical and live market data
  - VIX and volatility metrics
- [x] T026 [P] [US6] Implement portfolio tool in `agents/tools/portfolio.py`
  - Read-only portfolio and position access
  - Greeks exposure data
- [x] T027 [P] [US6] Implement redis_writer tool in `agents/tools/redis_writer.py`
  - Write to allowed Redis keys only (risk_bias, sentiment)
  - Enforce key prefix restrictions
- [x] T028 [P] [US6] Implement reconciliation tool in `agents/tools/reconciliation.py`
  - Query broker positions via existing reconciliation service
  - Compare local vs broker positions
  - Return discrepancy analysis for Ops agent

#### Overfitting Prevention

- [x] T029 [US6] Implement WalkForwardValidator in `agents/validation/walk_forward.py`
  - 70% train / 15% validation / 15% test split
  - Performance degradation check (<20% drop)
  - Parameter stability tests (±10%, ±20%)

#### Agent API and Integration

- [x] T030 [P] [US6] Create agent API routes in `backend/src/api/routes/agents.py`
  - POST /api/agents/invoke - Invoke agent task
  - GET /api/agents/results - List agent results
  - GET /api/agents/results/{id} - Get specific result
- [x] T031 [US6] Integrate risk_bias from Redis into RiskManager in `backend/src/risk/manager.py`
  - Read redis:risk_bias at signal validation
  - Apply bias multiplier to position limits
  - **Graceful degradation**: Fallback to default bias=1.0 if Redis unavailable
  - Continue trading if agent subsystem fails (FR-021)
- [x] T032 [P] [US6] Add Agents page component in `frontend/src/pages/AgentsPage.tsx`
  - Agent invocation interface
  - Results history table
  - Permission matrix display
- [x] T033 [US6] Generate TypeScript types for agents API in `frontend/src/api/generated/`

**Checkpoint**: User Story 6 complete - AI agent system functional

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T034 [P] [US4/US6] Update OpenAPI spec with derivatives and agents endpoints in `backend/scripts/generate_openapi.py`
- [x] T035 [P] [US4/US6] Regenerate frontend types via `frontend/scripts/generate-types.sh`
- [x] T036 [P] [US4] Add integration tests for derivatives in `backend/tests/integration/test_derivatives.py`
- [x] T037 [P] [US6] Add integration tests for agents in `backend/tests/integration/test_agents.py`
- [x] T038 [US4/US6] Run quickstart.md validation - verify setup still works (2362 tests pass)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Story 4 (Phase 3)**: Depends on Foundational (T004-T008)
- **User Story 6 (Phase 4)**: Depends on Foundational (T004-T008)
- **Polish (Phase 5)**: Depends on User Stories 4 and 6 completion

### User Story Dependencies

- **User Story 4 (P3)**: Can start after Foundational - No dependencies on US6
- **User Story 6 (P4)**: Can start after Foundational - No dependencies on US4
- US4 and US6 can be implemented in parallel if team capacity allows

### Within Each User Story

- Models before services
- Services before API routes
- Backend before frontend
- Core implementation before integration

### Parallel Opportunities

- T001, T002, T003 can run in parallel (Setup)
- T004/T006 and T005/T007 can run in parallel (Foundational)
- T020, T021, T022, T023 can run in parallel (Agent prompts)
- T024, T025, T026, T027, T028 can run in parallel (Agent tools)
- T036, T037 can run in parallel (Tests)
- US4 and US6 can be worked on in parallel by different team members

---

## Implementation Strategy

### MVP First (User Story 4 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: User Story 4 (Derivatives Lifecycle)
4. **STOP and VALIDATE**: Test derivative expiration warnings
5. Deploy/demo if ready

### Full Phase 3 Delivery

1. Complete Setup + Foundational
2. Complete User Story 4 (P3) - Derivatives
3. Complete User Story 6 (P4) - AI Agents
4. Complete Polish phase
5. Run full integration tests

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently testable
- Agent architecture: sidecar subprocess - NEVER in trading hot path
- Redis integration: agents write to Redis, trading reads (microseconds)
- Commit after each task or logical group
- **TDD Compliance**: Unit tests written alongside each implementation task (per project standard). Phase 5 tests (T035, T036) are integration tests that verify complete features.
