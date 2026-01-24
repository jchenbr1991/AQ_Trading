# Reconciliation Service Design

Phase 1 implementation plan for the Reconciliation component.

## Overview

The Reconciliation Service ensures local position/account state matches the broker's state. It detects discrepancies, logs them, and publishes alerts via Redis for operator review.

**Key Decisions:**
- Compare: Positions + Account balances
- Triggers: Periodic + After fills + Startup + On-demand
- On discrepancy: Log and alert only (no auto-correction in Phase 1)
- Broker access: Separate `BrokerQuery` protocol
- Discrepancy types: Categorized (6 types)
- Reporting: Redis pub/sub

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  ReconciliationService                       │
│                                                             │
│  Triggers:                                                  │
│  ├── Periodic (every N minutes)                             │
│  ├── After fill events (debounced)                          │
│  ├── On startup                                             │
│  └── On-demand (API call)                                   │
│                                                             │
│  ┌─────────────┐        ┌─────────────┐                     │
│  │ BrokerQuery │        │ Portfolio   │                     │
│  │ (broker     │        │ Manager     │                     │
│  │  positions) │        │ (local DB)  │                     │
│  └──────┬──────┘        └──────┬──────┘                     │
│         │                      │                            │
│         └──────────┬───────────┘                            │
│                    ▼                                        │
│         ┌─────────────────────┐                             │
│         │ Compare & Classify  │                             │
│         │ Discrepancies       │                             │
│         └──────────┬──────────┘                             │
│                    │                                        │
│         ┌─────────────────────┐                             │
│         │ Log + Redis Publish │                             │
│         │ reconciliation:*    │                             │
│         └─────────────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

**Components:**
1. **ReconciliationService** - Orchestrates comparison, runs on triggers
2. **BrokerQuery protocol** - Read-only interface for broker state
3. **Comparator** - Categorizes mismatches by type
4. **Redis publisher** - Real-time alerts to `reconciliation:*` channels

## Data Models

### BrokerQuery Protocol (new)

```python
@runtime_checkable
class BrokerQuery(Protocol):
    """Read-only interface for querying broker state."""

    async def get_positions(self, account_id: str) -> list[BrokerPosition]:
        """Get all positions from broker."""
        ...

    async def get_account(self, account_id: str) -> BrokerAccount:
        """Get account balances from broker."""
        ...
```

### BrokerPosition

```python
@dataclass
class BrokerPosition:
    """Position as reported by broker."""
    symbol: str
    quantity: int
    avg_cost: Decimal
    market_value: Decimal
    asset_type: AssetType  # STOCK, OPTION, FUTURE
```

### BrokerAccount

```python
@dataclass
class BrokerAccount:
    """Account balances as reported by broker."""
    account_id: str
    cash: Decimal
    buying_power: Decimal
    total_equity: Decimal
    margin_used: Decimal
```

### DiscrepancyType

```python
class DiscrepancyType(Enum):
    MISSING_LOCAL = "missing_local"        # Broker has position we don't
    MISSING_BROKER = "missing_broker"      # We have position broker doesn't
    QUANTITY_MISMATCH = "quantity_mismatch"
    COST_MISMATCH = "cost_mismatch"        # Informational only
    CASH_MISMATCH = "cash_mismatch"
    EQUITY_MISMATCH = "equity_mismatch"
```

### DiscrepancySeverity

```python
class DiscrepancySeverity(Enum):
    INFO = "info"          # Informational, no action needed
    WARNING = "warning"    # Attention needed, not critical
    CRITICAL = "critical"  # Immediate attention required
```

**Default severity mapping:**

| DiscrepancyType | Default Severity | Rationale |
|-----------------|------------------|-----------|
| `COST_MISMATCH` | INFO | Usually rounding/timing differences |
| `CASH_MISMATCH` | WARNING | Could be fees/dividends/interest |
| `EQUITY_MISMATCH` | WARNING | May need investigation |
| `QUANTITY_MISMATCH` | CRITICAL | Possible missed fill |
| `MISSING_LOCAL` | CRITICAL | Broker has position we don't track |
| `MISSING_BROKER` | CRITICAL | We think we have position that doesn't exist |

Phase 1 logs severity but doesn't auto-act. Phase 2 can use CRITICAL to trigger kill switch.

### Discrepancy

```python
@dataclass
class Discrepancy:
    """A single discrepancy between local and broker state."""
    type: DiscrepancyType
    severity: DiscrepancySeverity
    symbol: str | None          # None for account-level discrepancies
    local_value: Any
    broker_value: Any
    timestamp: datetime
    account_id: str
```

### ReconciliationConfig

```python
@dataclass
class ReconciliationConfig:
    """Configuration for reconciliation service."""
    account_id: str
    interval_seconds: int = 300              # 5 minutes default
    post_fill_delay_seconds: float = 5.0     # Debounce after fills
    cash_tolerance: Decimal = Decimal("1.00")       # Ignore < $1 diff
    equity_tolerance_pct: Decimal = Decimal("0.1")  # Ignore < 0.1% diff
    enabled: bool = True
```

### ReconciliationResult

```python
@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""
    run_id: UUID                      # Unique ID for correlation
    account_id: str
    timestamp: datetime
    is_clean: bool                    # No discrepancies found
    discrepancies: list[Discrepancy]
    positions_checked: int
    duration_ms: float
    context: dict[str, Any]           # Trigger context (see below)
```

**Context field** captures why this reconciliation was triggered:

```python
# Periodic trigger
context = {"trigger": "periodic"}

# Startup trigger
context = {"trigger": "startup"}

# On-demand trigger
context = {"trigger": "on_demand", "requested_by": "api"}

# Post-fill trigger
context = {
    "trigger": "post_fill",
    "order_id": "ORD-123",
    "fill_id": "FILL-456",
    "symbol": "AAPL",
}
```

This enables tracing discrepancies back to their root cause during incident investigation.

## Comparison Logic

### Position Comparison

```python
async def _compare_positions(
    self,
    local: list[Position],
    broker: list[BrokerPosition],
) -> list[Discrepancy]:
    discrepancies = []

    # Index by symbol for O(1) lookup
    local_by_symbol = {p.symbol: p for p in local}
    broker_by_symbol = {p.symbol: p for p in broker}

    all_symbols = set(local_by_symbol) | set(broker_by_symbol)

    for symbol in all_symbols:
        local_pos = local_by_symbol.get(symbol)
        broker_pos = broker_by_symbol.get(symbol)

        if local_pos is None:
            # MISSING_LOCAL: broker has position we don't
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.MISSING_LOCAL,
                symbol=symbol,
                local_value=None,
                broker_value=broker_pos.quantity,
                ...
            ))
        elif broker_pos is None:
            # MISSING_BROKER: we have position broker doesn't
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.MISSING_BROKER,
                symbol=symbol,
                local_value=local_pos.quantity,
                broker_value=None,
                ...
            ))
        elif local_pos.quantity != broker_pos.quantity:
            # QUANTITY_MISMATCH
            discrepancies.append(...)
        elif local_pos.avg_cost != broker_pos.avg_cost:
            # COST_MISMATCH (informational)
            discrepancies.append(...)

    return discrepancies
```

### Account Comparison

Account comparison applies tolerances from config:
- `cash_tolerance`: Absolute dollar amount (default $1.00)
- `equity_tolerance_pct`: Percentage difference (default 0.1%)

Only flag `CASH_MISMATCH` or `EQUITY_MISMATCH` if difference exceeds tolerance.

## Public Interface

```python
class ReconciliationService:
    """
    Reconciliation service for comparing local vs broker state.

    Runs periodically and on-demand, publishes discrepancies to Redis.
    """

    def __init__(
        self,
        portfolio: PortfolioManager,
        broker_query: BrokerQuery,
        redis: RedisClient,
        config: ReconciliationConfig,
    ):
        ...

    async def start(self) -> None:
        """Start periodic reconciliation loop."""

    async def stop(self) -> None:
        """Stop periodic loop."""

    async def reconcile(self, account_id: str) -> ReconciliationResult:
        """
        Run reconciliation on-demand.
        Returns result with any discrepancies found.
        """

    async def on_fill(self, fill: OrderFill) -> None:
        """
        Called after a fill - triggers reconciliation with fill context.
        Debounced to avoid excessive checks on rapid fills.

        Automatically sets context:
        {
            "trigger": "post_fill",
            "order_id": fill.order_id,
            "fill_id": fill.fill_id,
            "symbol": fill.symbol,
        }
        """
```

## Redis Publishing

### Channels

| Channel | Purpose | Payload |
|---------|---------|---------|
| `reconciliation:result` | Every reconciliation run | `ReconciliationResult` JSON |
| `reconciliation:discrepancy` | Each discrepancy found | `Discrepancy` JSON |

### Publishing Logic

```python
async def _publish_result(self, result: ReconciliationResult) -> None:
    """Publish reconciliation result to Redis."""
    await self._redis.publish(
        "reconciliation:result",
        json.dumps({
            "run_id": str(result.run_id),
            "account_id": result.account_id,
            "timestamp": result.timestamp.isoformat(),
            "is_clean": result.is_clean,
            "discrepancy_count": len(result.discrepancies),
            "positions_checked": result.positions_checked,
            "duration_ms": result.duration_ms,
            "context": result.context,
        })
    )

    # Publish each discrepancy separately for targeted alerting
    for d in result.discrepancies:
        await self._redis.publish(
            "reconciliation:discrepancy",
            json.dumps({
                "run_id": str(result.run_id),  # Correlate with result
                "type": d.type.value,
                "severity": d.severity.value,
                "symbol": d.symbol,
                "local_value": str(d.local_value),
                "broker_value": str(d.broker_value),
                "timestamp": d.timestamp.isoformat(),
                "account_id": d.account_id,
            })
        )
```

All discrepancies also logged at `WARNING` level for debugging.

## File Structure

```
backend/src/
├── reconciliation/
│   ├── __init__.py         # Exports
│   ├── service.py          # ReconciliationService
│   ├── models.py           # Discrepancy, DiscrepancyType, Result, Config
│   └── comparator.py       # Position/account comparison logic
├── broker/
│   └── query.py            # BrokerQuery protocol, BrokerPosition, BrokerAccount

backend/tests/
├── reconciliation/
│   ├── __init__.py
│   ├── test_models.py      # Discrepancy types, config defaults
│   ├── test_comparator.py  # Position/account comparison
│   ├── test_service.py     # Periodic, on-demand, post-fill triggers
│   └── test_publishing.py  # Redis publish verification
```

## Testing Strategy

| Category | Tests | Purpose |
|----------|-------|---------|
| **Models** | Config defaults, discrepancy creation | Verify data structures |
| **Comparator** | Position matching, tolerance checks | Verify comparison logic |
| **Service** | Triggers, lifecycle, debouncing | Verify orchestration |
| **Publishing** | Redis channel, JSON format | Verify alerting |

**Key test cases:**

```python
# test_comparator.py
class TestPositionComparison:
    def test_no_discrepancies_when_matching(self)
    def test_missing_local_detected(self)
    def test_missing_broker_detected(self)
    def test_quantity_mismatch_detected(self)
    def test_cost_mismatch_informational(self)

class TestAccountComparison:
    def test_cash_within_tolerance_ok(self)
    def test_cash_outside_tolerance_flagged(self)
    def test_equity_percentage_tolerance(self)

# test_service.py
class TestReconciliationService:
    async def test_periodic_runs_at_interval(self)
    async def test_on_demand_reconcile(self)
    async def test_post_fill_debounced(self)
    async def test_publishes_to_redis(self)
    async def test_startup_reconciliation(self)
```

## Implementation Tasks (TDD Order)

1. **Models** - `Discrepancy`, `DiscrepancyType`, `ReconciliationResult`, `ReconciliationConfig`
2. **BrokerQuery protocol** - `BrokerQuery`, `BrokerPosition`, `BrokerAccount`
3. **PaperBroker extension** - Implement `BrokerQuery` for paper trading
4. **Comparator** - Position and account comparison logic
5. **ReconciliationService** - Core service with periodic loop
6. **Event triggers** - Post-fill debounce, startup hook
7. **Redis publishing** - Result and discrepancy channels
8. **Package exports** - `__init__.py`

## Future Considerations (Not Phase 1)

- **Auto-correction mode**: Optional flag to auto-sync local state to broker
- **Database persistence**: Store reconciliation history for audit
- **Severity levels**: Classify discrepancies by severity (critical/warning/info)
- **Kill switch integration**: Auto-halt trading on critical discrepancies
