# Quickstart: L0 Hypothesis + L1 Constraints System

**Feature**: 003-hypothesis-constraints-system

## Overview

This guide shows how to set up and use the governance layer for AQ Trading.

## Prerequisites

- Python 3.11+
- Running AQ Trading backend
- Access to `config/` directory

## 1. Create Your First Hypothesis

Create a YAML file in `config/hypotheses/`:

```yaml
# config/hypotheses/memory_demand_2027.yml
id: memory_demand_2027
title: AI Memory Demand Strong Through 2027
statement: >
  AI-related memory demand will remain strong through 2027,
  creating favorable conditions for memory semiconductor stocks.
scope:
  symbols:
    - MU
    - SSNLF
  sectors:
    - semiconductors
owner: human
status: DRAFT  # Start as DRAFT, change to ACTIVE via PR
review_cycle: quarterly
created_at: 2026-02-02
evidence:
  sources:
    - https://example.com/ai-memory-forecast
  notes: Based on datacenter expansion plans from major cloud providers
falsifiers:  # REQUIRED - at least one
  - metric: industry_asp_qoq
    operator: "<"
    threshold: 0
    window: "4q"
    trigger: review
  - metric: mu_gm_vs_peers
    operator: "<"
    threshold: -0.05
    window: "2q"
    trigger: sunset
linked_constraints:
  - mu_memory_overlay
```

**Key Points**:
- `falsifiers` are **mandatory** - hypothesis won't pass validation without them
- Start with `status: DRAFT`, change to `ACTIVE` only via PR merge
- `review_cycle` determines when to re-evaluate the hypothesis

## 2. Create Linked Constraint

Create a YAML file in `config/constraints/`:

```yaml
# config/constraints/mu_memory_overlay.yml
id: mu_memory_overlay
title: MU Memory Demand Overlay
applies_to:
  symbols:
    - MU
  strategies: []  # Empty = all strategies
activation:
  requires_hypotheses_active:
    - memory_demand_2027
  disabled_if_falsified: true
actions:
  risk_budget_multiplier: 1.5
  veto_downgrade: true
  stop_mode: fundamental_guarded
guardrails:
  max_position_pct: 0.25
  max_drawdown_addon: 0.05
priority: 50  # Lower = higher priority
```

**Allowlisted Actions** (ONLY these are permitted):
- `enable_strategy`
- `pool_bias_multiplier`
- `veto_downgrade`
- `risk_budget_multiplier`
- `holding_extension_days`
- `add_position_cap_multiplier`
- `stop_mode`

**Red Line**: Constraints NEVER affect alpha/factor calculations.

## 3. Configure Structural Filters

Edit `config/filters/structural_filters.yml`:

```yaml
# config/filters/structural_filters.yml
exclude_state_owned_ratio_gte: 0.5
exclude_dividend_yield_gte: 0.08
min_avg_dollar_volume: 1000000
exclude_sectors:
  - utilities
  - real_estate
min_market_cap: 1000000000
```

These filters apply **before** hypothesis gating.

## 4. Define Base Universe

Edit `config/universe/base_universe.yml`:

```yaml
# config/universe/base_universe.yml
symbols:
  - AAPL
  - MSFT
  - GOOGL
  - AMZN
  - MU
  - NVDA
  # ... more symbols
source: manual  # or "index:SP500", "screen:high_volume"
```

## 5. Configure Regime Detection

Edit `config/regimes/regime_v1.yml`:

```yaml
# config/regimes/regime_v1.yml
thresholds:
  volatility_normal_max: 0.15
  volatility_stress_min: 0.25
  drawdown_stress_min: 0.10
  dispersion_stress_min: 0.30

actions:
  NORMAL:
    allow_new_positions: true
    entry_threshold_multiplier: 1.0
  TRANSITION:
    allow_new_positions: true
    entry_threshold_multiplier: 1.5
  STRESS:
    allow_new_positions: false
    force_reduce: true
```

## 6. Validate Configuration

Run lint and gate checks:

```bash
# Check alpha path isolation
python -m governance.lint.alpha_path

# Check constraint allowlist
python -m governance.lint.allowlist

# Run all gates
python -m governance.gates.validate
```

Expected output:
```
lint:no_hypothesis_in_alpha_path: PASS (checked 45 files)
lint:no_constraint_in_alpha_path: PASS (checked 45 files)
lint:constraint_actions_allowlist: PASS (checked 3 constraints)
gate:hypothesis_requires_falsifiers: PASS (2 hypotheses)
gate:factor_requires_failure_rule: PASS (5 factors)
```

## 7. Build Pool

```bash
# Build pool with current config
python -m governance.pool.builder --output pool.json

# View pool audit trail
python -m governance.pool.audit MU
```

Output:
```json
{
  "symbols": ["AAPL", "AMZN", "GOOGL", "MU", "MSFT", "NVDA"],
  "version": "2026-02-02T10:00:00_abc123",
  "audit_trail": [
    {"symbol": "XYZ", "action": "excluded", "reason": "structural_filter:min_volume", "source": "structural_filters"},
    {"symbol": "MU", "action": "prioritized", "reason": "hypothesis:memory_demand_2027", "source": "mu_memory_overlay"}
  ]
}
```

## 8. Query Resolved Constraints

Via API:
```bash
curl http://localhost:8000/api/governance/constraints/resolve/MU
```

Response:
```json
{
  "symbol": "MU",
  "constraints": [
    {"constraint_id": "mu_memory_overlay", "action_type": "risk_budget_multiplier", "value": 1.5},
    {"constraint_id": "mu_memory_overlay", "action_type": "veto_downgrade", "value": true},
    {"constraint_id": "mu_memory_overlay", "action_type": "stop_mode", "value": "fundamental_guarded"}
  ],
  "effective_risk_budget_multiplier": 1.5,
  "effective_stop_mode": "fundamental_guarded",
  "veto_downgrade_active": true,
  "guardrails": {
    "max_position_pct": 0.25,
    "max_drawdown_addon": 0.05
  }
}
```

## 9. Strategy Integration

In your strategy, governance inputs are now available:

```python
class MyStrategy(Strategy):
    def on_market_data(self, data: MarketData, context: StrategyContext) -> list[Signal]:
        # Governance inputs are automatically provided
        pool = context.pool  # Active symbols
        constraints = context.constraints  # Resolved constraints for each symbol
        regime = context.regime  # Current market regime

        # Check if symbol is in pool
        if data.symbol not in pool.symbols:
            return []

        # Check regime
        if regime.state == RegimeState.STRESS:
            return []  # No new positions in stress

        # Apply constraint guardrails
        symbol_constraints = constraints.get(data.symbol)
        if symbol_constraints:
            max_position = symbol_constraints.guardrails.max_position_pct
            # ... apply position limit
```

**Note**: Strategy receives `constraints` (resolved actions), NOT raw `hypothesis` data.

## 10. Monitor Falsifiers

Set up falsifier monitoring:

```bash
# Run manual check
python -m governance.monitoring.falsifier --hypothesis memory_demand_2027

# View falsifier status
curl http://localhost:8000/api/governance/hypotheses/memory_demand_2027/falsifiers/check
```

When falsifier triggers:
1. Alert is generated (log + configured channels)
2. If `disabled_if_falsified: true`, linked constraints are deactivated
3. Audit log records the event

## 11. Query Audit Logs

```bash
# Query recent constraint effects
curl "http://localhost:8000/api/governance/audit?symbol=MU&limit=10"

# Query by time range
curl "http://localhost:8000/api/governance/audit?start_time=2026-02-01T00:00:00Z&end_time=2026-02-02T00:00:00Z"
```

## Workflow Summary

```
1. Human writes Hypothesis (YAML) with falsifiers
2. Human writes Constraint (YAML) with allowlisted actions
3. PR merge activates hypothesis (DRAFT → ACTIVE)
4. Pool builder applies filters + hypothesis gating
5. Strategy receives: pool + alpha + regime + constraints
6. Falsifier monitor checks hypothesis validity
7. Audit log tracks all governance effects
```

## Common Issues

| Issue | Solution |
|-------|----------|
| Hypothesis validation fails | Ensure `falsifiers` has at least one entry |
| Constraint validation fails | Check that actions use only allowlisted fields |
| Lint fails in CI | Remove hypothesis/constraint imports from factor code |
| Empty pool error | Check filters aren't too restrictive |
| Constraint not applying | Verify linked hypothesis is ACTIVE |

## Files Reference

```
config/
├── hypotheses/
│   └── *.yml           # Hypothesis definitions
├── constraints/
│   └── *.yml           # Constraint definitions
├── filters/
│   └── structural_filters.yml
├── universe/
│   └── base_universe.yml
├── factors/
│   └── *.yml           # Factor definitions with failure rules
└── regimes/
    └── regime_v1.yml
```
