# Data Model: L0 Hypothesis + L1 Constraints System

**Feature**: 003-hypothesis-constraints-system
**Date**: 2026-02-02

## Entity Relationship Diagram

```
┌─────────────────────┐         ┌─────────────────────┐
│     Hypothesis      │ 1     n │     Constraint      │
│─────────────────────│◄────────│─────────────────────│
│ id (PK)             │         │ id (PK)             │
│ title               │         │ title               │
│ statement           │         │ applies_to          │
│ scope               │         │ activation          │
│ status              │         │ actions             │
│ falsifiers          │         │ guardrails          │
└─────────────────────┘         └─────────────────────┘
         │                               │
         │ 1                             │ n
         ▼ n                             ▼ 1
┌─────────────────────┐         ┌─────────────────────┐
│     Falsifier       │         │ ResolvedConstraints │
│─────────────────────│         │─────────────────────│
│ metric              │         │ symbol              │
│ operator            │         │ constraints[]       │
│ threshold           │         │ resolved_at         │
│ window              │         │ version             │
│ trigger             │         └─────────────────────┘
└─────────────────────┘
                                        │
┌─────────────────────┐                 │
│       Pool          │◄────────────────┘
│─────────────────────│         uses
│ symbols[]           │
│ version             │
│ audit_trail[]       │
│ built_at            │
└─────────────────────┘
         │
         │ feeds
         ▼
┌─────────────────────┐         ┌─────────────────────┐
│  StrategyContext    │         │      Regime         │
│─────────────────────│◄────────│─────────────────────│
│ pool                │         │ state               │
│ alpha               │         │ volatility          │
│ regime              │         │ drawdown            │
│ constraints         │         │ detected_at         │
└─────────────────────┘         └─────────────────────┘
         │
         │ logs
         ▼
┌─────────────────────┐
│    AuditLogEntry    │
│─────────────────────│
│ id                  │
│ timestamp           │
│ event_type          │
│ hypothesis_id       │
│ constraint_id       │
│ symbol              │
│ action_details      │
│ trace_id            │
└─────────────────────┘
```

## Entity Definitions

### 1. Hypothesis (L0)

**Purpose**: Human-proposed market belief with mandatory falsification criteria.

**Source**: YAML file in `config/hypotheses/`

```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date

class HypothesisScope(BaseModel):
    """Defines what symbols/sectors the hypothesis applies to."""
    symbols: list[str] = []  # Empty = all symbols
    sectors: list[str] = []  # Empty = all sectors

class Evidence(BaseModel):
    """Supporting evidence for the hypothesis."""
    sources: list[str] = []  # URLs, file references
    notes: str = ""

class Falsifier(BaseModel):
    """Rule that can invalidate the hypothesis."""
    metric: str  # Must be resolvable by MetricRegistry
    operator: Literal["<", "<=", ">", ">=", "=="]
    threshold: float
    window: str  # "4q", "6m", "90d"
    trigger: Literal["review", "sunset"]

class Hypothesis(BaseModel):
    """L0 Human worldview assertion."""
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    title: str
    statement: str  # Natural language proposition
    scope: HypothesisScope
    owner: Literal["human"] = "human"
    status: Literal["DRAFT", "ACTIVE", "SUNSET", "REJECTED"]
    review_cycle: str  # "30d", "quarterly"
    created_at: date
    evidence: Evidence
    falsifiers: list[Falsifier] = Field(..., min_length=1)  # REQUIRED
    linked_constraints: list[str] = []

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"
```

**Validation Rules**:
- `id` must be unique across all hypotheses
- `falsifiers` must have at least one entry (gate requirement)
- `status` can only transition DRAFT → ACTIVE via PR merge

---

### 2. Constraint (L1)

**Purpose**: System-executable rule derived from hypothesis; affects risk/timing only.

**Source**: YAML file in `config/constraints/`

```python
class ConstraintAppliesTo(BaseModel):
    """Specifies what symbols/strategies the constraint applies to."""
    symbols: list[str] = []  # Empty = all symbols
    strategies: list[str] = []  # Empty = all strategies

class ConstraintActivation(BaseModel):
    """Defines when the constraint becomes active."""
    requires_hypotheses_active: list[str] = []  # Must be ACTIVE
    disabled_if_falsified: bool = True

class ConstraintActions(BaseModel):
    """Allowlisted actions - these are the ONLY permitted fields."""
    enable_strategy: bool | None = None
    pool_bias_multiplier: float | None = Field(None, gt=0)
    veto_downgrade: bool | None = None
    risk_budget_multiplier: float | None = Field(None, ge=1)
    holding_extension_days: int | None = Field(None, ge=0)
    add_position_cap_multiplier: float | None = Field(None, gt=0)
    stop_mode: Literal["baseline", "wide", "fundamental_guarded"] | None = None

class ConstraintGuardrails(BaseModel):
    """Hard limits that override actions."""
    max_position_pct: float | None = Field(None, ge=0, le=1)
    max_gross_exposure_delta: float | None = None
    max_drawdown_addon: float | None = None

class Constraint(BaseModel):
    """L1 System-executable rule - NEVER affects alpha."""
    id: str = Field(..., pattern=r"^[a-z0-9_]+$")
    title: str
    applies_to: ConstraintAppliesTo
    activation: ConstraintActivation
    actions: ConstraintActions
    guardrails: ConstraintGuardrails = ConstraintGuardrails()
    priority: int = Field(default=100, ge=1)  # Lower = higher priority

    def is_active(self, hypothesis_registry: "HypothesisRegistry") -> bool:
        """Check if all required hypotheses are ACTIVE."""
        for h_id in self.activation.requires_hypotheses_active:
            h = hypothesis_registry.get(h_id)
            if not h or not h.is_active:
                return False
        return True
```

**Validation Rules**:
- `actions` fields must only use allowlisted fields (lint rule enforces)
- `priority` determines order when multiple constraints apply

---

### 3. ResolvedConstraints

**Purpose**: Pre-computed constraint effects for a specific symbol, cached for hot path.

```python
from datetime import datetime

class ResolvedAction(BaseModel):
    """Single resolved action from one constraint."""
    constraint_id: str
    action_type: str  # e.g., "risk_budget_multiplier"
    value: float | bool | str

class ResolvedConstraints(BaseModel):
    """All active constraints resolved for a single symbol."""
    symbol: str
    constraints: list[ResolvedAction]
    resolved_at: datetime
    version: str  # Config version hash

    # Pre-computed aggregate effects
    effective_risk_budget_multiplier: float = 1.0
    effective_pool_bias_multiplier: float = 1.0
    effective_stop_mode: str = "baseline"
    veto_downgrade_active: bool = False
    guardrails: ConstraintGuardrails = ConstraintGuardrails()
```

**Storage**: Redis (cached), regenerated on config change

---

### 4. StructuralFilter

**Purpose**: Long-term quantitative screen for pool building, independent of hypotheses.

**Source**: YAML file in `config/filters/structural_filters.yml`

```python
class StructuralFilters(BaseModel):
    """Filters applied before hypothesis gating."""
    exclude_state_owned_ratio_gte: float | None = None
    exclude_dividend_yield_gte: float | None = None
    min_avg_dollar_volume: float | None = None
    exclude_sectors: list[str] = []
    min_market_cap: float | None = None
    max_price: float | None = None
    min_price: float | None = None
```

---

### 5. Pool

**Purpose**: Active trading universe with full audit trail.

```python
class PoolAuditEntry(BaseModel):
    """Records why a symbol was included/excluded."""
    symbol: str
    action: Literal["included", "excluded", "prioritized"]
    reason: str  # e.g., "structural_filter:min_volume", "hypothesis:memory_demand_2027"
    source: str  # Filter/hypothesis ID

class Pool(BaseModel):
    """Deterministic active trading universe."""
    symbols: list[str]  # Sorted for determinism
    weights: dict[str, float] = {}  # Optional priority weights
    version: str  # "{timestamp}_{config_hash}"
    built_at: datetime
    audit_trail: list[PoolAuditEntry]

    @property
    def is_empty(self) -> bool:
        return len(self.symbols) == 0
```

**Validation Rules**:
- Empty pool raises error and prevents strategy execution

---

### 6. Regime

**Purpose**: Market state classification affecting position pacing.

```python
class RegimeState(str, Enum):
    NORMAL = "NORMAL"
    TRANSITION = "TRANSITION"
    STRESS = "STRESS"

class RegimeThresholds(BaseModel):
    """Configurable thresholds for regime detection."""
    volatility_normal_max: float = 0.15
    volatility_stress_min: float = 0.25
    drawdown_stress_min: float = 0.10
    dispersion_stress_min: float = 0.30

class Regime(BaseModel):
    """Current market regime state."""
    state: RegimeState
    volatility: float
    drawdown: float
    dispersion: float
    detected_at: datetime
    thresholds: RegimeThresholds
```

**Note**: Regime NEVER contributes to alpha; only affects position pacing.

---

### 7. Factor (Registry Entry)

**Purpose**: Alpha source with mandatory failure rule.

**Source**: YAML file in `config/factors/`

```python
class FactorEvaluation(BaseModel):
    """IC evaluation configuration."""
    ic_method: Literal["rank_ic", "pearson"]
    horizons: list[int]  # [1, 5, 20]
    window: str  # "6m"

class FactorFailureRule(BaseModel):
    """Rule that disables factor when violated."""
    metric: str  # e.g., "rolling_ic_mean"
    operator: Literal["<", "<=", ">", ">=", "=="]
    threshold: float
    window: str
    action: Literal["disable", "review"]

class Factor(BaseModel):
    """Registered factor with mandatory failure rule."""
    name: str
    inputs: list[str]  # Feature names
    transform: str | None = None
    evaluation: FactorEvaluation
    failure_rule: FactorFailureRule  # REQUIRED (gate)
    enabled: bool = True
```

**Validation Rules**:
- `failure_rule` is required (gate requirement)

---

### 8. AuditLogEntry

**Purpose**: Immutable record of governance effects.

**Storage**: PostgreSQL table

```python
class AuditEventType(str, Enum):
    CONSTRAINT_ACTIVATED = "constraint_activated"
    CONSTRAINT_DEACTIVATED = "constraint_deactivated"
    FALSIFIER_CHECK_PASS = "falsifier_check_pass"
    FALSIFIER_CHECK_TRIGGERED = "falsifier_check_triggered"
    VETO_DOWNGRADE = "veto_downgrade"
    RISK_BUDGET_ADJUSTED = "risk_budget_adjusted"
    POSITION_CAP_APPLIED = "position_cap_applied"
    POOL_BUILT = "pool_built"
    REGIME_CHANGED = "regime_changed"

class AuditLogEntry(BaseModel):
    """Single audit log entry."""
    id: int | None = None  # Auto-generated
    timestamp: datetime
    event_type: AuditEventType
    hypothesis_id: str | None = None
    constraint_id: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    action_details: dict  # JSONB
    trace_id: str | None = None  # Links to signal traces
```

**SQL Schema**:
```sql
CREATE TABLE governance_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,
    hypothesis_id VARCHAR(100),
    constraint_id VARCHAR(100),
    symbol VARCHAR(20),
    strategy_id VARCHAR(100),
    action_details JSONB NOT NULL,
    trace_id VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_timestamp ON governance_audit_log(timestamp);
CREATE INDEX idx_audit_symbol ON governance_audit_log(symbol);
CREATE INDEX idx_audit_constraint ON governance_audit_log(constraint_id);
CREATE INDEX idx_audit_event_type ON governance_audit_log(event_type);
```

---

### 9. FalsifierCheckResult

**Purpose**: Result of a falsifier evaluation.

```python
class FalsifierCheckResult(BaseModel):
    """Result of checking one falsifier rule."""
    hypothesis_id: str
    falsifier_index: int
    metric: str
    expected: str  # e.g., ">= 0"
    actual: float | None
    triggered: bool
    trigger_action: Literal["review", "sunset"]
    checked_at: datetime
    error: str | None = None  # If metric unavailable
```

---

### 10. Alert

**Purpose**: Notification for falsifier triggers or system events.

```python
class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class Alert(BaseModel):
    """Alert generated by governance system."""
    id: str
    timestamp: datetime
    severity: AlertSeverity
    title: str
    message: str
    hypothesis_id: str | None = None
    constraint_id: str | None = None
    recommended_action: str | None = None
    delivered_to: list[str] = []  # ["log", "email", "webhook"]
```

---

## State Transitions

### Hypothesis Status

```
DRAFT ──(PR merge)──► ACTIVE ──(falsifier triggered)──► SUNSET
                         │                                  │
                         └──(manual rejection)──► REJECTED ◄┘
```

### Constraint Activation

```
Inactive ◄──────────────────────────────────────────────────┐
    │                                                        │
    ▼ (linked hypothesis becomes ACTIVE)                     │
 Active ────(linked hypothesis falsified + disabled_if_falsified)──┘
```

### Regime State

```
NORMAL ◄──(volatility decreases)──┐
   │                               │
   ▼ (volatility increases)        │
TRANSITION ◄──(volatility decreases)──┤
   │                               │
   ▼ (volatility spike)            │
STRESS ────(volatility normalizes)──┘
```
