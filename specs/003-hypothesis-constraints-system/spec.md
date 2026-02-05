# Feature Specification: L0 Hypothesis + L1 Constraints System

**Feature Branch**: `003-hypothesis-constraints-system`
**Created**: 2026-02-02
**Status**: Draft
**Input**: AQ Trading — Ambitious System Spec: Introduce an explicit, auditable L0 Hypothesis (assertions/propositions) + L1 Constraints (rules) layer on top of existing backtest/paper/live pipelines, with Pool/Filter, Feature/Factor, Regime/State, Strategy systems.

## Executive Summary

This feature introduces a governance layer that separates human "worldview" hypotheses from quantitative alpha generation. The system enforces a critical red line: **Hypotheses and Constraints must NEVER contribute to alpha (factor synthesis)**. They can only influence: enable/disable decisions, universe/pool selection, risk budgets, veto/tolerance rules, and position pacing.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Record and Manage Human Hypotheses (Priority: P1)

As a human trader/researcher, I want to explicitly record my long-term market beliefs (hypotheses) so they can be systematically tracked, audited, and revoked when evidence contradicts them.

**Why this priority**: This is the foundational capability. Without hypothesis registration, no constraints can be activated, and the entire governance system cannot function.

**Independent Test**: Can create a hypothesis YAML file with required fields, and the system correctly parses it and validates that falsifiers are present.

**Acceptance Scenarios**:

1. **Given** a hypothesis YAML file with all required fields including falsifiers, **When** the system loads the configuration, **Then** the hypothesis is registered and available for constraint activation
2. **Given** a hypothesis YAML file missing falsifiers, **When** the system validates the configuration, **Then** the hypothesis is rejected with a clear error indicating falsifiers are required
3. **Given** a hypothesis with status DRAFT, **When** a PR is merged changing status to ACTIVE, **Then** linked constraints become enforceable

---

### User Story 2 - Enforce Constraints Without Polluting Alpha (Priority: P1)

As a system operator, I want constraints derived from hypotheses to influence only risk/timing decisions (not alpha calculations) so that factor-based signals remain pure and backtestable.

**Why this priority**: This enforces the critical red line. If constraints leak into alpha paths, the entire system's integrity is compromised.

**Independent Test**: Can configure a constraint that modifies risk budget, and verify via lint/gate that no alpha computation code path reads hypothesis or constraint files.

**Acceptance Scenarios**:

1. **Given** an active constraint with `risk_budget_multiplier: 1.5`, **When** the strategy executes, **Then** the risk budget for affected symbols is scaled by 1.5x without changing factor weights
2. **Given** a code path that attempts to import hypothesis data into factor calculation, **When** lint runs, **Then** the build fails with `lint:no_hypothesis_in_alpha_path` error
3. **Given** a code path that attempts to import constraint data into factor calculation, **When** lint runs, **Then** the build fails with `lint:no_constraint_in_alpha_path` error
4. **Given** a constraint with an action field not in the allowlist, **When** lint runs, **Then** the build fails with `lint:constraint_actions_allowlist` error

---

### User Story 3 - Build Active Pool from Universe with Filters and Hypothesis Gating (Priority: P2)

As a portfolio manager, I want to derive an active trading pool from the base universe by applying structural filters and hypothesis-based gating so that position sizing respects both quantitative screens and qualitative views.

**Why this priority**: Pool building is essential for determining which symbols are tradeable, but the system can technically operate with a static pool for initial testing.

**Independent Test**: Can configure structural filters and hypothesis allowlist/denylist, run pool builder, and verify deterministic output with audit trail.

**Acceptance Scenarios**:

1. **Given** a base universe of 500 symbols and structural filters excluding low-volume stocks, **When** pool builder runs, **Then** output contains filtered symbols with version/timestamp and reasons for exclusions
2. **Given** an active hypothesis that denylists symbol "XYZ", **When** pool builder runs, **Then** "XYZ" is excluded with audit record linking to the hypothesis
3. **Given** identical inputs on different runs, **When** pool builder executes, **Then** outputs are identical (deterministic)
4. **Given** filters that exclude all symbols from base universe, **When** pool builder runs, **Then** system raises an error and prevents strategy execution

---

### User Story 4 - Detect Falsified Hypotheses and Trigger Review (Priority: P2)

As a researcher, I want the system to automatically check falsifier conditions and alert me when a hypothesis may be invalidated so I can make informed decisions about sunsetting or revising it.

**Why this priority**: Automatic falsification checking ensures hypotheses don't become stale beliefs that silently distort trading behavior.

**Independent Test**: Can configure a falsifier rule with a metric threshold, simulate metric data exceeding threshold, and verify review alert is generated.

**Acceptance Scenarios**:

1. **Given** a hypothesis with falsifier `metric: "rolling_ic_mean", operator: "<", threshold: 0, window: "6m"`, **When** the rolling IC mean drops below 0 for 6 months, **Then** a review report is generated recommending sunset
2. **Given** a constraint with `disabled_if_falsified: true` linked to a falsified hypothesis, **When** falsification is detected, **Then** the constraint is automatically disabled

---

### User Story 5 - Audit Constraint Effects on Trading Decisions (Priority: P3)

As a compliance officer, I want complete audit logs showing when constraints affected trading decisions so I can trace any position change back to its governance origins.

**Why this priority**: Audit capability is important for compliance and post-mortem analysis but doesn't affect core trading functionality.

**Independent Test**: Can execute a strategy with active constraints, then query audit logs to see which constraints affected which decisions.

**Acceptance Scenarios**:

1. **Given** an active constraint that triggers veto downgrade, **When** a trading decision is made, **Then** the audit log records the constraint ID, timestamp, affected symbol, and action taken
2. **Given** audit logs from a trading period, **When** queried by symbol and date range, **Then** all constraint effects are retrievable with full context

---

### User Story 6 - Register Factors with Failure Rules (Priority: P2)

As a quant researcher, I want all factors to have mandatory failure rules so that degraded factors are automatically disabled or flagged for review.

**Why this priority**: Factor failure rules prevent stale or broken factors from continuing to generate signals, protecting portfolio quality.

**Independent Test**: Can register a factor with failure rule, simulate IC degradation below threshold, and verify factor is disabled.

**Acceptance Scenarios**:

1. **Given** a factor registration missing `failure_rule`, **When** gate validation runs, **Then** registration is rejected with `gate:factor_requires_failure_rule` error
2. **Given** a factor with `failure_rule: {metric: "rolling_ic_mean", operator: "<", threshold: 0, action: "disable"}`, **When** rolling IC mean is negative for the window, **Then** factor is automatically disabled from alpha synthesis

---

### User Story 7 - Apply Regime-Based Position Pacing (Priority: P3)

As a risk manager, I want market regime (NORMAL/TRANSITION/STRESS) to automatically adjust position entry thresholds and sizing limits so the system is more defensive in volatile conditions.

**Why this priority**: Regime detection adds sophistication but the system can operate with a default "NORMAL" regime initially.

**Independent Test**: Can configure regime detector, simulate high volatility conditions, verify regime transitions to STRESS, and confirm position limits are tightened.

**Acceptance Scenarios**:

1. **Given** regime detector configured with volatility thresholds, **When** volatility exceeds STRESS threshold, **Then** regime state changes to STRESS and new position entries are frozen
2. **Given** regime state is TRANSITION, **When** strategy generates buy signal, **Then** entry threshold is elevated per TRANSITION rules

---

### Edge Cases

- What happens when a hypothesis has no linked constraints? (System should allow it but log a warning)
- What happens when conflicting constraints apply to the same symbol? (System should use priority ordering and log resolution)
- How does system handle missing metric data for falsifier evaluation? (Skip evaluation for that period, log warning, don't falsify)
- What happens when pool builder produces an empty pool? (System should raise error and prevent strategy execution)
- How does system behave when regime detector receives stale data? (Use last known regime, log warning)

## Requirements *(mandatory)*

### Functional Requirements

**L0 Hypothesis Registry**

- **FR-001**: System MUST accept hypothesis definitions in YAML format with fields: id, title, statement, scope (symbols/sectors), owner, status, review_cycle, created_at, evidence, falsifiers, linked_constraints
- **FR-002**: System MUST reject hypotheses that lack falsifier rules with clear error messages
- **FR-003**: System MUST enforce that status transitions from DRAFT to ACTIVE require explicit PR merge (human approval)
- **FR-004**: System MUST support hypothesis statuses: DRAFT, ACTIVE, SUNSET, REJECTED

**L1 Constraints Registry**

- **FR-005**: System MUST accept constraint definitions with fields: id, title, applies_to, activation, actions, guardrails
- **FR-006**: System MUST validate that constraint actions only use allowlisted fields: enable_strategy, pool_bias_multiplier, veto_downgrade, risk_budget_multiplier, holding_extension_days, add_position_cap_multiplier, stop_mode, guardrails (max_position_pct, max_gross_exposure_delta, max_drawdown_addon)
- **FR-007**: System MUST support `disabled_if_falsified` flag to auto-disable constraints when linked hypothesis is falsified

**Red Line Enforcement (Lint/Gate)**

- **FR-008**: System MUST implement `lint:no_hypothesis_in_alpha_path` that fails if hypothesis files are imported by factor/alpha code
- **FR-008a**: System MUST implement `lint:no_constraint_in_alpha_path` that fails if constraint files are imported by factor/alpha code
- **FR-009**: System MUST implement `lint:constraint_actions_allowlist` that fails if constraint uses non-allowlisted action fields
- **FR-010**: System MUST implement `gate:hypothesis_requires_falsifiers` that rejects hypotheses without falsifiers
- **FR-011**: System MUST implement `gate:factor_requires_failure_rule` that rejects factor registrations without failure rules

**Pool Builder**

- **FR-012**: System MUST build active pool from: base universe + structural filters + hypothesis gating (allowlist/denylist/bias)
- **FR-013**: System MUST produce deterministic pool output given identical inputs
- **FR-014**: System MUST output pool with version/timestamp and per-symbol audit trail (why included/excluded/prioritized)
- **FR-015**: System MUST raise an error and prevent strategy execution when pool builder produces an empty pool

**Structural Filters**

- **FR-016**: System MUST support structural filters independent of hypotheses: exclude_state_owned_ratio_gte, exclude_dividend_yield_gte, min_avg_dollar_volume, exclude_sectors

**Factor Registry**

- **FR-017**: System MUST accept factor definitions with fields: name, inputs, transform, evaluation (ic_method, horizons, window), failure_rule
- **FR-018**: System MUST enforce that factors are the ONLY source of alpha (no hypothesis or constraint data in factor computation)

**Regime/State**

- **FR-019**: System MUST support discrete regime states: NORMAL, TRANSITION, STRESS
- **FR-020**: System MUST configure regime based on quantifiable metrics (volatility, drawdown, dispersion)
- **FR-021**: Regime MUST NOT contribute to alpha; regime only affects position pacing and risk controls

**Strategy Interface**

- **FR-022**: Strategy MUST receive explicitly separated inputs: pool, alpha (factor scores), regime, constraints (resolved L1 actions)
- **FR-023**: Strategy MUST NOT read hypothesis text directly; only resolved constraints
- **FR-024**: Strategy MUST output orders_intent (target positions/order intentions)

**Falsifier Monitoring**

- **FR-025**: System MUST run falsifier checks on a configurable schedule (default: daily for market data metrics, weekly for fundamental metrics)
- **FR-026**: System MUST generate review alerts when falsifier conditions are triggered, including: hypothesis_id, triggered_falsifier, metric_value, threshold, recommended_action (review/sunset)
- **FR-027**: System MUST support notification delivery for falsifier alerts (configurable: log file, email, webhook)

**Audit Logging**

- **FR-028**: System MUST log all constraint activations with: constraint_id, timestamp, affected symbols/strategies, actions applied
- **FR-029**: System MUST log all falsifier check results and triggered events
- **FR-030**: System MUST log veto downgrades, risk budget changes, position cap modifications

### Key Entities

- **Hypothesis**: A human-proposed, unfalsifiable-by-backtest assertion with scope, status, evidence, falsifiers, and linked constraints
- **Constraint**: A system-executable rule derived from hypothesis; affects risk/timing but never alpha; has allowlisted actions and guardrails
- **Structural Filter**: Long-term quantitative screen for pool building; independent of hypotheses
- **Pool**: Active trading universe derived from base universe via filters and hypothesis gating; versioned and auditable
- **Factor**: Quantitative alpha source with inputs, evaluation config, and mandatory failure rule
- **Regime**: Market state classification (NORMAL/TRANSITION/STRESS) affecting position pacing; never contributes to alpha
- **Audit Log**: Immutable record of constraint effects, falsifier checks, and governance decisions

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of hypothesis files pass `gate:hypothesis_requires_falsifiers` validation (no hypothesis can be ACTIVE without falsifiers)
- **SC-002**: 100% of factor registrations pass `gate:factor_requires_failure_rule` validation
- **SC-003**: Lint checks `no_hypothesis_in_alpha_path` and `constraint_actions_allowlist` run in CI with zero tolerance for failures
- **SC-004**: Pool builder produces identical output on repeated runs with same inputs (deterministic guarantee)
- **SC-005**: Any constraint effect on a trading decision is traceable via audit log within 1 query
- **SC-006**: Falsifier checks run on configured schedule and generate review reports within 24 hours of threshold breach
- **SC-007**: Strategy receives all four input categories (pool, alpha, regime, constraints) as separate data structures
- **SC-008**: Zero instances of hypothesis or constraint data appearing in factor computation code paths (verified by lint)

## Assumptions

- The existing AQ Trading backtest/paper/live pipeline provides a working strategy execution framework
- YAML is the preferred configuration format for human-readable hypothesis/constraint definitions
- PR-based workflow (GitHub) is used for hypothesis status transitions requiring human approval
- Factor IC calculation and evaluation infrastructure exists or will be extended
- Metric data for falsifier evaluation is available from the existing data pipeline

## Out of Scope

- Complex NLP event extraction and event-driven trading
- Adaptive learning / large language model for trading decisions
- Fully automatic hypothesis generation and activation (human approval always required)

## Milestones

### M1: Configuration and Parsing Pipeline (No Alpha Changes)
- Read and parse hypotheses/constraints YAML
- Implement gating logic to resolve constraints
- Pool builder supports structural filters
- Strategy interface receives constraints (affects only risk/timing)

### M2: Audit and Invalidation Mechanisms
- Periodic falsifier checking
- Automatic constraint disabling (`disabled_if_falsified`)
- Factor failure rule enforcement (auto-disable/review)
- Audit report generation and artifacts output
