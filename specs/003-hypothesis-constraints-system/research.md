# Research: L0 Hypothesis + L1 Constraints System

**Feature**: 003-hypothesis-constraints-system
**Date**: 2026-02-02

## Research Questions Addressed

### 1. YAML Configuration Schema Design

**Question**: What is the best approach for YAML-based hypothesis/constraint configuration?

**Decision**: Use Pydantic models with `pydantic-yaml` for type-safe YAML loading

**Rationale**:
- Pydantic provides runtime validation with clear error messages
- Native integration with FastAPI for API responses
- `pydantic-yaml` allows direct YAML → Pydantic model conversion
- Strong typing catches configuration errors at load time

**Alternatives Considered**:
- Raw PyYAML + manual validation: More code, less type safety
- JSON Schema: Less human-friendly for config files
- TOML: Less widespread, YAML more common in trading configs

**Example Schema**:
```python
from pydantic import BaseModel, Field
from typing import Literal
from datetime import date

class Falsifier(BaseModel):
    metric: str
    operator: Literal["<", "<=", ">", ">=", "=="]
    threshold: float
    window: str  # e.g., "6m", "4q", "90d"
    trigger: Literal["review", "sunset"]

class Hypothesis(BaseModel):
    id: str
    title: str
    statement: str
    scope: dict[str, list[str]]  # symbols, sectors
    owner: Literal["human"] = "human"
    status: Literal["DRAFT", "ACTIVE", "SUNSET", "REJECTED"]
    review_cycle: str
    created_at: date
    evidence: dict
    falsifiers: list[Falsifier] = Field(min_length=1)  # At least one required
    linked_constraints: list[str]
```

---

### 2. Lint Rule Implementation for Alpha Path Isolation

**Question**: How to implement lint rules that detect hypothesis/constraint imports in alpha code?

**Decision**: AST-based static analysis with configurable path patterns

**Rationale**:
- Python's `ast` module provides reliable import detection
- Static analysis catches issues before runtime
- Configurable patterns allow flexible path definitions
- Can integrate with existing CI/pre-commit hooks

**Implementation Approach**:
```python
import ast
from pathlib import Path

ALPHA_PATHS = [
    "backend/src/strategies/factors/",
    "backend/src/backtest/",
]

FORBIDDEN_MODULES = [
    "governance.hypothesis",
    "governance.constraints",
]

def check_alpha_path_imports(file_path: Path) -> list[str]:
    """Return list of forbidden imports found."""
    violations = []
    tree = ast.parse(file_path.read_text())

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name.startswith(m) for m in FORBIDDEN_MODULES):
                    violations.append(f"{file_path}:{node.lineno}: imports {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and any(node.module.startswith(m) for m in FORBIDDEN_MODULES):
                violations.append(f"{file_path}:{node.lineno}: imports from {node.module}")

    return violations
```

**Alternatives Considered**:
- Runtime import hooks: Too late, violations already in code
- Grep-based: Misses complex import patterns
- Third-party linters (ruff, pylint): Overkill for specific rule

---

### 3. Pool Builder Determinism

**Question**: How to ensure pool builder produces identical output for identical inputs?

**Decision**: Hash-based versioning with sorted outputs and reproducible filtering

**Rationale**:
- Sorted symbol lists ensure consistent ordering
- SHA256 hash of input config provides version identifier
- Reproducible random seed if any randomization needed (not expected)
- Timestamp + hash = unique pool version

**Implementation Approach**:
```python
import hashlib
from datetime import datetime

class PoolBuilder:
    def build(self, base_universe: list[str], filters: dict, hypothesis_gating: dict) -> Pool:
        # 1. Sort inputs for determinism
        sorted_universe = sorted(base_universe)

        # 2. Apply filters in consistent order
        filtered = self._apply_filters(sorted_universe, filters)

        # 3. Apply hypothesis gating
        gated = self._apply_gating(filtered, hypothesis_gating)

        # 4. Generate version hash
        config_str = json.dumps({
            "universe": sorted_universe,
            "filters": filters,
            "gating": hypothesis_gating
        }, sort_keys=True)
        version_hash = hashlib.sha256(config_str.encode()).hexdigest()[:12]

        return Pool(
            symbols=sorted(gated),
            version=f"{datetime.utcnow().isoformat()}_{version_hash}",
            audit_trail=self._build_audit_trail()
        )
```

**Alternatives Considered**:
- UUID versioning: Not reproducible from inputs
- Timestamp only: Doesn't capture config state

---

### 4. Constraint Resolution Caching

**Question**: How to cache resolved constraints for hot path performance?

**Decision**: Redis-backed cache with TTL and invalidation on config change

**Rationale**:
- Redis already used in system (risk_bias, sentiment)
- TTL ensures eventual consistency without manual invalidation
- Hot path reads O(1) from Redis
- Config changes trigger immediate cache invalidation

**Cache Structure**:
```python
# Redis keys
"governance:constraints:resolved:{symbol}" -> JSON(ResolvedConstraints)
"governance:constraints:version" -> "2026-02-02T10:00:00_abc123"

# TTL: 5 minutes (configurable)
# Invalidation: on any hypothesis/constraint file change
```

**Implementation**:
```python
class ConstraintCache:
    def __init__(self, redis: Redis, ttl: int = 300):
        self.redis = redis
        self.ttl = ttl

    async def get_resolved(self, symbol: str) -> ResolvedConstraints | None:
        data = await self.redis.get(f"governance:constraints:resolved:{symbol}")
        if data:
            return ResolvedConstraints.model_validate_json(data)
        return None

    async def set_resolved(self, symbol: str, constraints: ResolvedConstraints):
        await self.redis.setex(
            f"governance:constraints:resolved:{symbol}",
            self.ttl,
            constraints.model_dump_json()
        )

    async def invalidate_all(self):
        keys = await self.redis.keys("governance:constraints:resolved:*")
        if keys:
            await self.redis.delete(*keys)
```

**Alternatives Considered**:
- In-memory cache: Lost on restart, not shared across workers
- No caching: Too slow for hot path with 500+ symbols
- Database caching: Slower than Redis

---

### 5. Falsifier Metric Integration

**Question**: How to connect falsifier rules with existing data pipelines?

**Decision**: Metric registry pattern with pluggable data sources

**Rationale**:
- Existing market data and backtest infrastructure provides metrics
- Registry pattern allows adding new metrics without code changes
- Clear separation between metric definition and data source

**Metric Registry**:
```python
class MetricRegistry:
    def __init__(self):
        self._providers: dict[str, MetricProvider] = {}

    def register(self, name: str, provider: MetricProvider):
        self._providers[name] = provider

    async def get_value(self, metric_name: str, symbol: str, window: str) -> float | None:
        if metric_name not in self._providers:
            return None
        return await self._providers[metric_name].get_value(symbol, window)

# Example providers
class RollingICProvider(MetricProvider):
    async def get_value(self, symbol: str, window: str) -> float:
        # Query IC calculation from backtest/evaluation module
        pass

class ASPProvider(MetricProvider):
    async def get_value(self, symbol: str, window: str) -> float:
        # Query ASP data from market data service
        pass
```

**Alternatives Considered**:
- Direct SQL queries: Less flexible, tighter coupling
- External metrics service: Overkill for initial implementation

---

### 6. Audit Log Schema

**Question**: What audit log schema supports all traceability requirements?

**Decision**: PostgreSQL table with JSONB for flexible action details

**Rationale**:
- PostgreSQL already in stack
- JSONB allows flexible action payload without schema migrations
- Indexed columns for common queries (timestamp, symbol, constraint_id)
- TimescaleDB hypertable if volume grows

**Schema**:
```sql
CREATE TABLE governance_audit_log (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type VARCHAR(50) NOT NULL,  -- 'constraint_activated', 'falsifier_triggered', etc.
    hypothesis_id VARCHAR(100),
    constraint_id VARCHAR(100),
    symbol VARCHAR(20),
    strategy_id VARCHAR(100),
    action_details JSONB NOT NULL,
    trace_id VARCHAR(100),  -- Links to signal traces
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_timestamp ON governance_audit_log(timestamp);
CREATE INDEX idx_audit_symbol ON governance_audit_log(symbol);
CREATE INDEX idx_audit_constraint ON governance_audit_log(constraint_id);
```

**Alternatives Considered**:
- Separate tables per event type: More complex, unnecessary initially
- Log files: Not queryable, harder to correlate

---

## Technology Decisions Summary

| Component | Technology | Rationale |
|-----------|------------|-----------|
| YAML parsing | pydantic-yaml | Type-safe, FastAPI integration |
| Lint rules | Python ast module | Native, reliable, lightweight |
| Constraint cache | Redis | Already in stack, O(1) reads |
| Audit logs | PostgreSQL + JSONB | Flexible, queryable |
| Falsifier scheduling | APScheduler | Battle-tested, async support |
| Config watching | watchdog | Detect config file changes |

## Open Questions (for implementation phase)

1. **Notification channels**: Which channels for falsifier alerts? (Start with: log file + webhook)
2. **Conflict resolution**: Priority ordering when multiple constraints affect same symbol? (Propose: explicit priority field in constraint YAML)
3. **Migration path**: How to introduce governance to existing strategies without breaking changes? (Propose: optional governance inputs with defaults)
