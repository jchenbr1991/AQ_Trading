# Reconciliation Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reconciliation service that compares local position/account state with broker state, logs discrepancies with severity levels, and publishes alerts via Redis.

**Architecture:** The ReconciliationService orchestrates comparison between local state (from database via Position/Account models) and broker state (via BrokerQuery protocol). A separate Comparator handles the matching logic with tolerance support. Results are published to Redis channels for operator alerting.

**Tech Stack:** Python 3.11+, pytest, dataclasses, asyncio, Redis (pub/sub)

---

## Task 1: Core Models - DiscrepancyType and DiscrepancySeverity

**Files:**
- Create: `backend/src/reconciliation/__init__.py`
- Create: `backend/src/reconciliation/models.py`
- Create: `backend/tests/reconciliation/__init__.py`
- Create: `backend/tests/reconciliation/test_models.py`

**Step 1: Write failing tests for enums**

```python
# backend/tests/reconciliation/test_models.py
"""Tests for reconciliation models."""

from src.reconciliation.models import DiscrepancyType, DiscrepancySeverity


class TestDiscrepancyType:
    def test_missing_local_value(self):
        assert DiscrepancyType.MISSING_LOCAL.value == "missing_local"

    def test_missing_broker_value(self):
        assert DiscrepancyType.MISSING_BROKER.value == "missing_broker"

    def test_quantity_mismatch_value(self):
        assert DiscrepancyType.QUANTITY_MISMATCH.value == "quantity_mismatch"

    def test_cost_mismatch_value(self):
        assert DiscrepancyType.COST_MISMATCH.value == "cost_mismatch"

    def test_cash_mismatch_value(self):
        assert DiscrepancyType.CASH_MISMATCH.value == "cash_mismatch"

    def test_equity_mismatch_value(self):
        assert DiscrepancyType.EQUITY_MISMATCH.value == "equity_mismatch"


class TestDiscrepancySeverity:
    def test_info_value(self):
        assert DiscrepancySeverity.INFO.value == "info"

    def test_warning_value(self):
        assert DiscrepancySeverity.WARNING.value == "warning"

    def test_critical_value(self):
        assert DiscrepancySeverity.CRITICAL.value == "critical"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_models.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.reconciliation'"

**Step 3: Create package and implement enums**

```python
# backend/src/reconciliation/__init__.py
"""Reconciliation service package."""

# backend/tests/reconciliation/__init__.py
"""Reconciliation tests package."""
```

```python
# backend/src/reconciliation/models.py
"""Reconciliation data models."""

from enum import Enum


class DiscrepancyType(str, Enum):
    """Types of discrepancies between local and broker state."""

    MISSING_LOCAL = "missing_local"        # Broker has position we don't
    MISSING_BROKER = "missing_broker"      # We have position broker doesn't
    QUANTITY_MISMATCH = "quantity_mismatch"
    COST_MISMATCH = "cost_mismatch"        # Informational only
    CASH_MISMATCH = "cash_mismatch"
    EQUITY_MISMATCH = "equity_mismatch"


class DiscrepancySeverity(str, Enum):
    """Severity levels for discrepancies."""

    INFO = "info"          # Informational, no action needed
    WARNING = "warning"    # Attention needed, not critical
    CRITICAL = "critical"  # Immediate attention required
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_models.py -v`
Expected: PASS (9 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/ backend/tests/reconciliation/
git commit -m "feat(reconciliation): add DiscrepancyType and DiscrepancySeverity enums"
```

---

## Task 2: Discrepancy Dataclass with Severity Mapping

**Files:**
- Modify: `backend/src/reconciliation/models.py`
- Modify: `backend/tests/reconciliation/test_models.py`

**Step 1: Write failing tests for Discrepancy**

```python
# Add to backend/tests/reconciliation/test_models.py
from datetime import datetime
from decimal import Decimal

from src.reconciliation.models import (
    Discrepancy,
    DiscrepancyType,
    DiscrepancySeverity,
    DEFAULT_SEVERITY_MAP,
)


class TestDiscrepancy:
    def test_create_discrepancy(self):
        d = Discrepancy(
            type=DiscrepancyType.QUANTITY_MISMATCH,
            severity=DiscrepancySeverity.CRITICAL,
            symbol="AAPL",
            local_value=100,
            broker_value=90,
            timestamp=datetime(2026, 1, 24, 10, 0, 0),
            account_id="ACC001",
        )
        assert d.type == DiscrepancyType.QUANTITY_MISMATCH
        assert d.severity == DiscrepancySeverity.CRITICAL
        assert d.symbol == "AAPL"
        assert d.local_value == 100
        assert d.broker_value == 90
        assert d.account_id == "ACC001"

    def test_account_level_discrepancy_symbol_none(self):
        d = Discrepancy(
            type=DiscrepancyType.CASH_MISMATCH,
            severity=DiscrepancySeverity.WARNING,
            symbol=None,
            local_value=Decimal("10000.00"),
            broker_value=Decimal("10005.00"),
            timestamp=datetime.utcnow(),
            account_id="ACC001",
        )
        assert d.symbol is None


class TestDefaultSeverityMap:
    def test_cost_mismatch_is_info(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.COST_MISMATCH] == DiscrepancySeverity.INFO

    def test_cash_mismatch_is_warning(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.CASH_MISMATCH] == DiscrepancySeverity.WARNING

    def test_equity_mismatch_is_warning(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.EQUITY_MISMATCH] == DiscrepancySeverity.WARNING

    def test_quantity_mismatch_is_critical(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.QUANTITY_MISMATCH] == DiscrepancySeverity.CRITICAL

    def test_missing_local_is_critical(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_LOCAL] == DiscrepancySeverity.CRITICAL

    def test_missing_broker_is_critical(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_BROKER] == DiscrepancySeverity.CRITICAL
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_models.py::TestDiscrepancy -v`
Expected: FAIL with "cannot import name 'Discrepancy'"

**Step 3: Implement Discrepancy and severity map**

```python
# Add to backend/src/reconciliation/models.py
from dataclasses import dataclass
from datetime import datetime
from typing import Any


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


# Default severity mapping based on discrepancy type
DEFAULT_SEVERITY_MAP: dict[DiscrepancyType, DiscrepancySeverity] = {
    DiscrepancyType.COST_MISMATCH: DiscrepancySeverity.INFO,
    DiscrepancyType.CASH_MISMATCH: DiscrepancySeverity.WARNING,
    DiscrepancyType.EQUITY_MISMATCH: DiscrepancySeverity.WARNING,
    DiscrepancyType.QUANTITY_MISMATCH: DiscrepancySeverity.CRITICAL,
    DiscrepancyType.MISSING_LOCAL: DiscrepancySeverity.CRITICAL,
    DiscrepancyType.MISSING_BROKER: DiscrepancySeverity.CRITICAL,
}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_models.py -v`
Expected: PASS (17 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/models.py backend/tests/reconciliation/test_models.py
git commit -m "feat(reconciliation): add Discrepancy dataclass with severity mapping"
```

---

## Task 3: ReconciliationConfig and ReconciliationResult

**Files:**
- Modify: `backend/src/reconciliation/models.py`
- Modify: `backend/tests/reconciliation/test_models.py`

**Step 1: Write failing tests**

```python
# Add to backend/tests/reconciliation/test_models.py
from uuid import UUID

from src.reconciliation.models import ReconciliationConfig, ReconciliationResult


class TestReconciliationConfig:
    def test_default_values(self):
        config = ReconciliationConfig(account_id="ACC001")
        assert config.account_id == "ACC001"
        assert config.interval_seconds == 300
        assert config.post_fill_delay_seconds == 5.0
        assert config.cash_tolerance == Decimal("1.00")
        assert config.equity_tolerance_pct == Decimal("0.1")
        assert config.enabled is True

    def test_custom_values(self):
        config = ReconciliationConfig(
            account_id="ACC002",
            interval_seconds=60,
            cash_tolerance=Decimal("5.00"),
            enabled=False,
        )
        assert config.interval_seconds == 60
        assert config.cash_tolerance == Decimal("5.00")
        assert config.enabled is False


class TestReconciliationResult:
    def test_clean_result(self):
        result = ReconciliationResult(
            account_id="ACC001",
            timestamp=datetime(2026, 1, 24, 10, 0, 0),
            is_clean=True,
            discrepancies=[],
            positions_checked=5,
            duration_ms=123.45,
            context={"trigger": "periodic"},
        )
        assert result.is_clean is True
        assert len(result.discrepancies) == 0
        assert result.positions_checked == 5
        assert result.duration_ms == 123.45
        assert result.context == {"trigger": "periodic"}
        # run_id should be auto-generated UUID
        assert isinstance(result.run_id, UUID)

    def test_result_with_discrepancies(self):
        discrepancy = Discrepancy(
            type=DiscrepancyType.QUANTITY_MISMATCH,
            severity=DiscrepancySeverity.CRITICAL,
            symbol="AAPL",
            local_value=100,
            broker_value=90,
            timestamp=datetime.utcnow(),
            account_id="ACC001",
        )
        result = ReconciliationResult(
            account_id="ACC001",
            timestamp=datetime.utcnow(),
            is_clean=False,
            discrepancies=[discrepancy],
            positions_checked=5,
            duration_ms=150.0,
            context={"trigger": "on_demand", "requested_by": "api"},
        )
        assert result.is_clean is False
        assert len(result.discrepancies) == 1

    def test_post_fill_context(self):
        result = ReconciliationResult(
            account_id="ACC001",
            timestamp=datetime.utcnow(),
            is_clean=True,
            discrepancies=[],
            positions_checked=3,
            duration_ms=50.0,
            context={
                "trigger": "post_fill",
                "order_id": "ORD-123",
                "fill_id": "FILL-456",
                "symbol": "AAPL",
            },
        )
        assert result.context["trigger"] == "post_fill"
        assert result.context["order_id"] == "ORD-123"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_models.py::TestReconciliationConfig -v`
Expected: FAIL with "cannot import name 'ReconciliationConfig'"

**Step 3: Implement config and result dataclasses**

```python
# Add to backend/src/reconciliation/models.py
from uuid import UUID, uuid4
from dataclasses import field


@dataclass
class ReconciliationConfig:
    """Configuration for reconciliation service."""

    account_id: str
    interval_seconds: int = 300              # 5 minutes default
    post_fill_delay_seconds: float = 5.0     # Debounce after fills
    cash_tolerance: Decimal = field(default_factory=lambda: Decimal("1.00"))
    equity_tolerance_pct: Decimal = field(default_factory=lambda: Decimal("0.1"))
    enabled: bool = True


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""

    account_id: str
    timestamp: datetime
    is_clean: bool                    # No discrepancies found
    discrepancies: list[Discrepancy]
    positions_checked: int
    duration_ms: float
    context: dict[str, Any]           # Trigger context
    run_id: UUID = field(default_factory=uuid4)  # Unique ID for correlation
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_models.py -v`
Expected: PASS (23 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/models.py backend/tests/reconciliation/test_models.py
git commit -m "feat(reconciliation): add ReconciliationConfig and ReconciliationResult"
```

---

## Task 4: BrokerQuery Protocol with BrokerPosition and BrokerAccount

**Files:**
- Create: `backend/src/broker/query.py`
- Create: `backend/tests/broker/test_query.py`

**Step 1: Write failing tests**

```python
# backend/tests/broker/test_query.py
"""Tests for BrokerQuery protocol."""

from decimal import Decimal
from typing import runtime_checkable

from src.broker.query import BrokerPosition, BrokerAccount, BrokerQuery
from src.models.position import AssetType


class TestBrokerPosition:
    def test_create_stock_position(self):
        pos = BrokerPosition(
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
            market_value=Decimal("15500.00"),
            asset_type=AssetType.STOCK,
        )
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100
        assert pos.avg_cost == Decimal("150.00")
        assert pos.market_value == Decimal("15500.00")
        assert pos.asset_type == AssetType.STOCK

    def test_create_option_position(self):
        pos = BrokerPosition(
            symbol="AAPL240315C00150000",
            quantity=10,
            avg_cost=Decimal("5.00"),
            market_value=Decimal("6000.00"),
            asset_type=AssetType.OPTION,
        )
        assert pos.asset_type == AssetType.OPTION


class TestBrokerAccount:
    def test_create_account(self):
        acct = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("50000.00"),
            buying_power=Decimal("100000.00"),
            total_equity=Decimal("150000.00"),
            margin_used=Decimal("25000.00"),
        )
        assert acct.account_id == "ACC001"
        assert acct.cash == Decimal("50000.00")
        assert acct.buying_power == Decimal("100000.00")
        assert acct.total_equity == Decimal("150000.00")
        assert acct.margin_used == Decimal("25000.00")


class TestBrokerQueryProtocol:
    def test_protocol_is_runtime_checkable(self):
        # Protocol should be runtime checkable
        assert hasattr(BrokerQuery, "__protocol_attrs__") or runtime_checkable

    def test_protocol_defines_get_positions(self):
        assert hasattr(BrokerQuery, "get_positions")

    def test_protocol_defines_get_account(self):
        assert hasattr(BrokerQuery, "get_account")
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/broker/test_query.py -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import name 'BrokerPosition'"

**Step 3: Implement BrokerQuery protocol**

```python
# backend/src/broker/query.py
"""Read-only interface for querying broker state."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from src.models.position import AssetType


@dataclass
class BrokerPosition:
    """Position as reported by broker."""

    symbol: str
    quantity: int
    avg_cost: Decimal
    market_value: Decimal
    asset_type: AssetType


@dataclass
class BrokerAccount:
    """Account balances as reported by broker."""

    account_id: str
    cash: Decimal
    buying_power: Decimal
    total_equity: Decimal
    margin_used: Decimal


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

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/broker/test_query.py -v`
Expected: PASS (6 passed)

**Step 5: Commit**

```bash
git add backend/src/broker/query.py backend/tests/broker/test_query.py
git commit -m "feat(broker): add BrokerQuery protocol with BrokerPosition and BrokerAccount"
```

---

## Task 5: PaperBroker Implements BrokerQuery

**Files:**
- Modify: `backend/src/broker/paper_broker.py`
- Modify: `backend/tests/broker/test_paper_broker.py`

**Step 1: Write failing tests**

```python
# Add to backend/tests/broker/test_paper_broker.py (or create new test class)
import pytest
from decimal import Decimal

from src.broker.paper_broker import PaperBroker
from src.broker.query import BrokerQuery, BrokerPosition, BrokerAccount
from src.models.position import AssetType


class TestPaperBrokerQuery:
    """Tests for PaperBroker implementing BrokerQuery."""

    @pytest.fixture
    def paper_broker(self):
        return PaperBroker(fill_delay=0.01)

    def test_implements_broker_query(self, paper_broker):
        """PaperBroker should implement BrokerQuery protocol."""
        assert isinstance(paper_broker, BrokerQuery)

    @pytest.mark.asyncio
    async def test_get_positions_empty(self, paper_broker):
        """Returns empty list when no positions."""
        positions = await paper_broker.get_positions("ACC001")
        assert positions == []

    @pytest.mark.asyncio
    async def test_get_positions_returns_broker_positions(self, paper_broker):
        """Returns positions in BrokerPosition format."""
        # Add a simulated position
        paper_broker.add_position(
            account_id="ACC001",
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
            market_value=Decimal("15500.00"),
            asset_type=AssetType.STOCK,
        )
        positions = await paper_broker.get_positions("ACC001")
        assert len(positions) == 1
        assert isinstance(positions[0], BrokerPosition)
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == 100

    @pytest.mark.asyncio
    async def test_get_account(self, paper_broker):
        """Returns account in BrokerAccount format."""
        paper_broker.set_account(
            account_id="ACC001",
            cash=Decimal("50000.00"),
            buying_power=Decimal("100000.00"),
            total_equity=Decimal("150000.00"),
            margin_used=Decimal("25000.00"),
        )
        account = await paper_broker.get_account("ACC001")
        assert isinstance(account, BrokerAccount)
        assert account.account_id == "ACC001"
        assert account.cash == Decimal("50000.00")

    @pytest.mark.asyncio
    async def test_get_account_default(self, paper_broker):
        """Returns default account values when not set."""
        account = await paper_broker.get_account("ACC001")
        assert account.cash == Decimal("100000.00")  # Default paper trading balance
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/broker/test_paper_broker.py::TestPaperBrokerQuery -v`
Expected: FAIL with "AttributeError: 'PaperBroker' object has no attribute 'add_position'"

**Step 3: Extend PaperBroker with BrokerQuery implementation**

Add to `backend/src/broker/paper_broker.py`:

```python
# Add imports at top
from src.broker.query import BrokerPosition, BrokerAccount
from src.models.position import AssetType

# Add to __init__ method:
self._positions: dict[str, dict[str, BrokerPosition]] = {}  # account_id -> symbol -> position
self._accounts: dict[str, BrokerAccount] = {}

# Add new methods:
def add_position(
    self,
    account_id: str,
    symbol: str,
    quantity: int,
    avg_cost: Decimal,
    market_value: Decimal,
    asset_type: AssetType = AssetType.STOCK,
) -> None:
    """Add or update a simulated position for testing."""
    if account_id not in self._positions:
        self._positions[account_id] = {}
    self._positions[account_id][symbol] = BrokerPosition(
        symbol=symbol,
        quantity=quantity,
        avg_cost=avg_cost,
        market_value=market_value,
        asset_type=asset_type,
    )

def set_account(
    self,
    account_id: str,
    cash: Decimal,
    buying_power: Decimal,
    total_equity: Decimal,
    margin_used: Decimal,
) -> None:
    """Set simulated account state for testing."""
    self._accounts[account_id] = BrokerAccount(
        account_id=account_id,
        cash=cash,
        buying_power=buying_power,
        total_equity=total_equity,
        margin_used=margin_used,
    )

async def get_positions(self, account_id: str) -> list[BrokerPosition]:
    """Get all positions from simulated broker."""
    return list(self._positions.get(account_id, {}).values())

async def get_account(self, account_id: str) -> BrokerAccount:
    """Get account balances from simulated broker."""
    if account_id in self._accounts:
        return self._accounts[account_id]
    # Return default paper trading account
    return BrokerAccount(
        account_id=account_id,
        cash=Decimal("100000.00"),
        buying_power=Decimal("200000.00"),
        total_equity=Decimal("100000.00"),
        margin_used=Decimal("0.00"),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/broker/test_paper_broker.py::TestPaperBrokerQuery -v`
Expected: PASS (5 passed)

**Step 5: Commit**

```bash
git add backend/src/broker/paper_broker.py backend/tests/broker/test_paper_broker.py
git commit -m "feat(broker): PaperBroker implements BrokerQuery protocol"
```

---

## Task 6: Comparator - Position Comparison Logic

**Files:**
- Create: `backend/src/reconciliation/comparator.py`
- Create: `backend/tests/reconciliation/test_comparator.py`

**Step 1: Write failing tests for position comparison**

```python
# backend/tests/reconciliation/test_comparator.py
"""Tests for reconciliation comparison logic."""

from datetime import datetime
from decimal import Decimal

import pytest

from src.broker.query import BrokerPosition
from src.models.position import AssetType, Position
from src.reconciliation.comparator import Comparator
from src.reconciliation.models import (
    DiscrepancyType,
    DiscrepancySeverity,
    ReconciliationConfig,
)


@pytest.fixture
def config():
    return ReconciliationConfig(account_id="ACC001")


@pytest.fixture
def comparator(config):
    return Comparator(config)


class TestPositionComparison:
    def test_no_discrepancies_when_matching(self, comparator):
        """Matching positions produce no discrepancies."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150.00"),
                market_value=Decimal("15500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert discrepancies == []

    def test_missing_local_detected(self, comparator):
        """Detects when broker has position we don't."""
        local = []
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150.00"),
                market_value=Decimal("15500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.MISSING_LOCAL
        assert discrepancies[0].severity == DiscrepancySeverity.CRITICAL
        assert discrepancies[0].symbol == "AAPL"
        assert discrepancies[0].local_value is None
        assert discrepancies[0].broker_value == 100

    def test_missing_broker_detected(self, comparator):
        """Detects when we have position broker doesn't."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = []
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.MISSING_BROKER
        assert discrepancies[0].severity == DiscrepancySeverity.CRITICAL
        assert discrepancies[0].symbol == "AAPL"
        assert discrepancies[0].local_value == 100
        assert discrepancies[0].broker_value is None

    def test_quantity_mismatch_detected(self, comparator):
        """Detects quantity differences."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=90,
                avg_cost=Decimal("150.00"),
                market_value=Decimal("13500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.QUANTITY_MISMATCH
        assert discrepancies[0].severity == DiscrepancySeverity.CRITICAL
        assert discrepancies[0].local_value == 100
        assert discrepancies[0].broker_value == 90

    def test_cost_mismatch_informational(self, comparator):
        """Cost mismatch is INFO severity."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("151.00"),  # Different cost
                market_value=Decimal("15500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.COST_MISMATCH
        assert discrepancies[0].severity == DiscrepancySeverity.INFO

    def test_multiple_discrepancies(self, comparator):
        """Handles multiple symbols with various issues."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
            _make_local_position("GOOG", 50, Decimal("2800.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=90,  # Mismatch
                avg_cost=Decimal("150.00"),
                market_value=Decimal("13500.00"),
                asset_type=AssetType.STOCK,
            ),
            BrokerPosition(
                symbol="TSLA",  # Missing local
                quantity=25,
                avg_cost=Decimal("200.00"),
                market_value=Decimal("5000.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        # AAPL quantity mismatch, GOOG missing broker, TSLA missing local
        assert len(discrepancies) == 3


def _make_local_position(symbol: str, quantity: int, avg_cost: Decimal) -> Position:
    """Helper to create Position for tests."""
    pos = Position()
    pos.symbol = symbol
    pos.quantity = quantity
    pos.avg_cost = avg_cost
    pos.asset_type = AssetType.STOCK
    pos.account_id = "ACC001"
    return pos
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_comparator.py::TestPositionComparison -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import name 'Comparator'"

**Step 3: Implement Comparator with position comparison**

```python
# backend/src/reconciliation/comparator.py
"""Comparison logic for reconciliation."""

from datetime import datetime

from src.broker.query import BrokerPosition, BrokerAccount
from src.models.position import Position
from src.models.account import Account
from src.reconciliation.models import (
    Discrepancy,
    DiscrepancyType,
    DiscrepancySeverity,
    DEFAULT_SEVERITY_MAP,
    ReconciliationConfig,
)


class Comparator:
    """Compares local state with broker state and identifies discrepancies."""

    def __init__(self, config: ReconciliationConfig):
        self._config = config

    def compare_positions(
        self,
        local: list[Position],
        broker: list[BrokerPosition],
    ) -> list[Discrepancy]:
        """Compare local positions against broker positions."""
        discrepancies: list[Discrepancy] = []
        now = datetime.utcnow()

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
                    severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_LOCAL],
                    symbol=symbol,
                    local_value=None,
                    broker_value=broker_pos.quantity,
                    timestamp=now,
                    account_id=self._config.account_id,
                ))
            elif broker_pos is None:
                # MISSING_BROKER: we have position broker doesn't
                discrepancies.append(Discrepancy(
                    type=DiscrepancyType.MISSING_BROKER,
                    severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_BROKER],
                    symbol=symbol,
                    local_value=local_pos.quantity,
                    broker_value=None,
                    timestamp=now,
                    account_id=self._config.account_id,
                ))
            elif local_pos.quantity != broker_pos.quantity:
                # QUANTITY_MISMATCH
                discrepancies.append(Discrepancy(
                    type=DiscrepancyType.QUANTITY_MISMATCH,
                    severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.QUANTITY_MISMATCH],
                    symbol=symbol,
                    local_value=local_pos.quantity,
                    broker_value=broker_pos.quantity,
                    timestamp=now,
                    account_id=self._config.account_id,
                ))
            elif local_pos.avg_cost != broker_pos.avg_cost:
                # COST_MISMATCH (informational)
                discrepancies.append(Discrepancy(
                    type=DiscrepancyType.COST_MISMATCH,
                    severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.COST_MISMATCH],
                    symbol=symbol,
                    local_value=local_pos.avg_cost,
                    broker_value=broker_pos.avg_cost,
                    timestamp=now,
                    account_id=self._config.account_id,
                ))

        return discrepancies
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_comparator.py::TestPositionComparison -v`
Expected: PASS (7 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/comparator.py backend/tests/reconciliation/test_comparator.py
git commit -m "feat(reconciliation): add Comparator with position comparison logic"
```

---

## Task 7: Comparator - Account Comparison with Tolerances

**Files:**
- Modify: `backend/src/reconciliation/comparator.py`
- Modify: `backend/tests/reconciliation/test_comparator.py`

**Step 1: Write failing tests for account comparison**

```python
# Add to backend/tests/reconciliation/test_comparator.py
from src.broker.query import BrokerAccount


class TestAccountComparison:
    def test_cash_within_tolerance_ok(self, comparator):
        """Cash difference within tolerance produces no discrepancy."""
        local_cash = Decimal("10000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10000.50"),  # $0.50 diff, within $1 tolerance
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("50000.00"),
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(local_cash, Decimal("50000.00"), broker)
        cash_discrepancies = [d for d in discrepancies if d.type == DiscrepancyType.CASH_MISMATCH]
        assert cash_discrepancies == []

    def test_cash_outside_tolerance_flagged(self, comparator):
        """Cash difference outside tolerance is flagged."""
        local_cash = Decimal("10000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10005.00"),  # $5 diff, outside $1 tolerance
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("50000.00"),
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(local_cash, Decimal("50000.00"), broker)
        cash_discrepancies = [d for d in discrepancies if d.type == DiscrepancyType.CASH_MISMATCH]
        assert len(cash_discrepancies) == 1
        assert cash_discrepancies[0].severity == DiscrepancySeverity.WARNING

    def test_equity_within_tolerance_ok(self, comparator):
        """Equity difference within percentage tolerance produces no discrepancy."""
        local_equity = Decimal("100000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10000.00"),
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("100050.00"),  # 0.05% diff, within 0.1%
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(Decimal("10000.00"), local_equity, broker)
        equity_discrepancies = [d for d in discrepancies if d.type == DiscrepancyType.EQUITY_MISMATCH]
        assert equity_discrepancies == []

    def test_equity_outside_tolerance_flagged(self, comparator):
        """Equity difference outside percentage tolerance is flagged."""
        local_equity = Decimal("100000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10000.00"),
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("100500.00"),  # 0.5% diff, outside 0.1%
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(Decimal("10000.00"), local_equity, broker)
        equity_discrepancies = [d for d in discrepancies if d.type == DiscrepancyType.EQUITY_MISMATCH]
        assert len(equity_discrepancies) == 1
        assert equity_discrepancies[0].severity == DiscrepancySeverity.WARNING

    def test_custom_tolerance(self):
        """Uses custom tolerances from config."""
        config = ReconciliationConfig(
            account_id="ACC001",
            cash_tolerance=Decimal("10.00"),  # $10 tolerance
            equity_tolerance_pct=Decimal("1.0"),  # 1% tolerance
        )
        comp = Comparator(config)
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10005.00"),  # Within $10
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("100500.00"),  # Within 1%
            margin_used=Decimal("0.00"),
        )
        discrepancies = comp.compare_account(Decimal("10000.00"), Decimal("100000.00"), broker)
        assert discrepancies == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_comparator.py::TestAccountComparison -v`
Expected: FAIL with "AttributeError: 'Comparator' object has no attribute 'compare_account'"

**Step 3: Implement account comparison**

```python
# Add to backend/src/reconciliation/comparator.py
from decimal import Decimal

# Add method to Comparator class:
def compare_account(
    self,
    local_cash: Decimal,
    local_equity: Decimal,
    broker: BrokerAccount,
) -> list[Discrepancy]:
    """Compare local account values against broker account."""
    discrepancies: list[Discrepancy] = []
    now = datetime.utcnow()

    # Check cash with absolute tolerance
    cash_diff = abs(local_cash - broker.cash)
    if cash_diff > self._config.cash_tolerance:
        discrepancies.append(Discrepancy(
            type=DiscrepancyType.CASH_MISMATCH,
            severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.CASH_MISMATCH],
            symbol=None,
            local_value=local_cash,
            broker_value=broker.cash,
            timestamp=now,
            account_id=self._config.account_id,
        ))

    # Check equity with percentage tolerance
    if local_equity != Decimal("0"):
        equity_diff_pct = abs(local_equity - broker.total_equity) / local_equity * 100
        if equity_diff_pct > self._config.equity_tolerance_pct:
            discrepancies.append(Discrepancy(
                type=DiscrepancyType.EQUITY_MISMATCH,
                severity=DEFAULT_SEVERITY_MAP[DiscrepancyType.EQUITY_MISMATCH],
                symbol=None,
                local_value=local_equity,
                broker_value=broker.total_equity,
                timestamp=now,
                account_id=self._config.account_id,
            ))

    return discrepancies
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_comparator.py -v`
Expected: PASS (12 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/comparator.py backend/tests/reconciliation/test_comparator.py
git commit -m "feat(reconciliation): add account comparison with tolerance support"
```

---

## Task 8: ReconciliationService - Core Structure and On-Demand Reconcile

**Files:**
- Create: `backend/src/reconciliation/service.py`
- Create: `backend/tests/reconciliation/test_service.py`

**Step 1: Write failing tests**

```python
# backend/tests/reconciliation/test_service.py
"""Tests for ReconciliationService."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.broker.query import BrokerPosition, BrokerAccount
from src.models.position import AssetType, Position
from src.reconciliation.models import ReconciliationConfig, DiscrepancyType
from src.reconciliation.service import ReconciliationService


@pytest.fixture
def mock_broker_query():
    broker = MagicMock()
    broker.get_positions = AsyncMock(return_value=[])
    broker.get_account = AsyncMock(return_value=BrokerAccount(
        account_id="ACC001",
        cash=Decimal("100000.00"),
        buying_power=Decimal("200000.00"),
        total_equity=Decimal("100000.00"),
        margin_used=Decimal("0.00"),
    ))
    return broker


@pytest.fixture
def mock_position_provider():
    provider = MagicMock()
    provider.get_positions = AsyncMock(return_value=[])
    provider.get_cash = AsyncMock(return_value=Decimal("100000.00"))
    provider.get_equity = AsyncMock(return_value=Decimal("100000.00"))
    return provider


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def config():
    return ReconciliationConfig(account_id="ACC001")


@pytest.fixture
def service(mock_broker_query, mock_position_provider, mock_redis, config):
    return ReconciliationService(
        position_provider=mock_position_provider,
        broker_query=mock_broker_query,
        redis=mock_redis,
        config=config,
    )


class TestOnDemandReconcile:
    @pytest.mark.asyncio
    async def test_reconcile_clean_result(self, service):
        """On-demand reconcile returns clean result when matching."""
        result = await service.reconcile()
        assert result.is_clean is True
        assert result.discrepancies == []
        assert result.account_id == "ACC001"
        assert result.context == {"trigger": "on_demand"}

    @pytest.mark.asyncio
    async def test_reconcile_finds_discrepancies(
        self, service, mock_broker_query, mock_position_provider
    ):
        """On-demand reconcile detects discrepancies."""
        # Local has AAPL, broker doesn't
        pos = Position()
        pos.symbol = "AAPL"
        pos.quantity = 100
        pos.avg_cost = Decimal("150.00")
        pos.asset_type = AssetType.STOCK
        pos.account_id = "ACC001"
        mock_position_provider.get_positions.return_value = [pos]

        result = await service.reconcile()
        assert result.is_clean is False
        assert len(result.discrepancies) == 1
        assert result.discrepancies[0].type == DiscrepancyType.MISSING_BROKER

    @pytest.mark.asyncio
    async def test_reconcile_measures_duration(self, service):
        """Reconcile records duration_ms."""
        result = await service.reconcile()
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_reconcile_counts_positions(
        self, service, mock_broker_query, mock_position_provider
    ):
        """Reconcile counts positions checked."""
        broker_positions = [
            BrokerPosition("AAPL", 100, Decimal("150.00"), Decimal("15000.00"), AssetType.STOCK),
            BrokerPosition("GOOG", 50, Decimal("2800.00"), Decimal("140000.00"), AssetType.STOCK),
        ]
        mock_broker_query.get_positions.return_value = broker_positions
        mock_position_provider.get_positions.return_value = []

        result = await service.reconcile()
        assert result.positions_checked == 2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestOnDemandReconcile -v`
Expected: FAIL with "ModuleNotFoundError" or "cannot import name 'ReconciliationService'"

**Step 3: Implement ReconciliationService**

```python
# backend/src/reconciliation/service.py
"""Reconciliation service for comparing local vs broker state."""

import logging
import time
from datetime import datetime
from typing import Any, Protocol

from src.broker.query import BrokerQuery
from src.models.position import Position
from src.reconciliation.comparator import Comparator
from src.reconciliation.models import (
    Discrepancy,
    ReconciliationConfig,
    ReconciliationResult,
)

logger = logging.getLogger(__name__)


class PositionProvider(Protocol):
    """Protocol for getting local position/account state."""

    async def get_positions(self, account_id: str) -> list[Position]:
        """Get local positions."""
        ...

    async def get_cash(self, account_id: str) -> Decimal:
        """Get local cash balance."""
        ...

    async def get_equity(self, account_id: str) -> Decimal:
        """Get local total equity."""
        ...


class ReconciliationService:
    """
    Reconciliation service for comparing local vs broker state.

    Runs periodically and on-demand, publishes discrepancies to Redis.
    """

    def __init__(
        self,
        position_provider: PositionProvider,
        broker_query: BrokerQuery,
        redis: Any,  # Redis client
        config: ReconciliationConfig,
    ):
        self._position_provider = position_provider
        self._broker_query = broker_query
        self._redis = redis
        self._config = config
        self._comparator = Comparator(config)

    async def reconcile(self, context: dict[str, Any] | None = None) -> ReconciliationResult:
        """
        Run reconciliation on-demand.
        Returns result with any discrepancies found.
        """
        if context is None:
            context = {"trigger": "on_demand"}

        start_time = time.perf_counter()
        timestamp = datetime.utcnow()
        discrepancies: list[Discrepancy] = []

        # Get local state
        local_positions = await self._position_provider.get_positions(self._config.account_id)
        local_cash = await self._position_provider.get_cash(self._config.account_id)
        local_equity = await self._position_provider.get_equity(self._config.account_id)

        # Get broker state
        broker_positions = await self._broker_query.get_positions(self._config.account_id)
        broker_account = await self._broker_query.get_account(self._config.account_id)

        # Compare positions
        position_discrepancies = self._comparator.compare_positions(
            local_positions, broker_positions
        )
        discrepancies.extend(position_discrepancies)

        # Compare account
        account_discrepancies = self._comparator.compare_account(
            local_cash, local_equity, broker_account
        )
        discrepancies.extend(account_discrepancies)

        # Count unique symbols checked
        local_symbols = {p.symbol for p in local_positions}
        broker_symbols = {p.symbol for p in broker_positions}
        positions_checked = len(local_symbols | broker_symbols)

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = ReconciliationResult(
            account_id=self._config.account_id,
            timestamp=timestamp,
            is_clean=len(discrepancies) == 0,
            discrepancies=discrepancies,
            positions_checked=positions_checked,
            duration_ms=duration_ms,
            context=context,
        )

        # Log discrepancies
        if not result.is_clean:
            for d in discrepancies:
                logger.warning(
                    f"Reconciliation discrepancy: {d.type.value} "
                    f"symbol={d.symbol} local={d.local_value} broker={d.broker_value}"
                )

        return result
```

Also need to add the Decimal import at the top of service.py:
```python
from decimal import Decimal
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestOnDemandReconcile -v`
Expected: PASS (4 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/service.py backend/tests/reconciliation/test_service.py
git commit -m "feat(reconciliation): add ReconciliationService with on-demand reconcile"
```

---

## Task 9: ReconciliationService - Redis Publishing

**Files:**
- Modify: `backend/src/reconciliation/service.py`
- Modify: `backend/tests/reconciliation/test_service.py`

**Step 1: Write failing tests**

```python
# Add to backend/tests/reconciliation/test_service.py
import json


class TestRedisPublishing:
    @pytest.mark.asyncio
    async def test_publishes_result_to_redis(self, service, mock_redis):
        """Reconcile publishes result to reconciliation:result channel."""
        result = await service.reconcile()

        mock_redis.publish.assert_called()
        calls = mock_redis.publish.call_args_list
        result_calls = [c for c in calls if c[0][0] == "reconciliation:result"]
        assert len(result_calls) == 1

        payload = json.loads(result_calls[0][0][1])
        assert payload["account_id"] == "ACC001"
        assert payload["is_clean"] is True
        assert "run_id" in payload
        assert "timestamp" in payload

    @pytest.mark.asyncio
    async def test_publishes_discrepancies_to_redis(
        self, service, mock_broker_query, mock_position_provider, mock_redis
    ):
        """Each discrepancy is published separately."""
        # Create discrepancy scenario
        pos = Position()
        pos.symbol = "AAPL"
        pos.quantity = 100
        pos.avg_cost = Decimal("150.00")
        pos.asset_type = AssetType.STOCK
        pos.account_id = "ACC001"
        mock_position_provider.get_positions.return_value = [pos]

        await service.reconcile()

        calls = mock_redis.publish.call_args_list
        discrepancy_calls = [c for c in calls if c[0][0] == "reconciliation:discrepancy"]
        assert len(discrepancy_calls) == 1

        payload = json.loads(discrepancy_calls[0][0][1])
        assert payload["type"] == "missing_broker"
        assert payload["severity"] == "critical"
        assert payload["symbol"] == "AAPL"
        assert "run_id" in payload  # Correlates with result

    @pytest.mark.asyncio
    async def test_run_id_correlates_result_and_discrepancies(
        self, service, mock_broker_query, mock_position_provider, mock_redis
    ):
        """run_id matches between result and discrepancies."""
        pos = Position()
        pos.symbol = "AAPL"
        pos.quantity = 100
        pos.avg_cost = Decimal("150.00")
        pos.asset_type = AssetType.STOCK
        pos.account_id = "ACC001"
        mock_position_provider.get_positions.return_value = [pos]

        await service.reconcile()

        calls = mock_redis.publish.call_args_list
        result_payload = json.loads([c for c in calls if c[0][0] == "reconciliation:result"][0][0][1])
        discrepancy_payload = json.loads([c for c in calls if c[0][0] == "reconciliation:discrepancy"][0][0][1])

        assert result_payload["run_id"] == discrepancy_payload["run_id"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestRedisPublishing -v`
Expected: FAIL (assert statement fails because publish not called yet)

**Step 3: Add Redis publishing to ReconciliationService**

```python
# Add to backend/src/reconciliation/service.py
import json

# Add method to ReconciliationService class:
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
                "local_value": str(d.local_value) if d.local_value is not None else None,
                "broker_value": str(d.broker_value) if d.broker_value is not None else None,
                "timestamp": d.timestamp.isoformat(),
                "account_id": d.account_id,
            })
        )
```

Also update the `reconcile` method to call `_publish_result`:

```python
# At the end of reconcile method, before return:
await self._publish_result(result)

return result
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestRedisPublishing -v`
Expected: PASS (3 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/service.py backend/tests/reconciliation/test_service.py
git commit -m "feat(reconciliation): add Redis publishing for results and discrepancies"
```

---

## Task 10: ReconciliationService - Periodic Loop

**Files:**
- Modify: `backend/src/reconciliation/service.py`
- Modify: `backend/tests/reconciliation/test_service.py`

**Step 1: Write failing tests**

```python
# Add to backend/tests/reconciliation/test_service.py
import asyncio


class TestPeriodicReconciliation:
    @pytest.mark.asyncio
    async def test_start_begins_periodic_loop(self, service, mock_redis, config):
        """start() begins periodic reconciliation."""
        config.interval_seconds = 0.1  # Fast for testing

        await service.start()
        await asyncio.sleep(0.25)  # Wait for at least 2 runs
        await service.stop()

        # Should have published at least 2 results (startup + periodic)
        result_calls = [c for c in mock_redis.publish.call_args_list
                       if c[0][0] == "reconciliation:result"]
        assert len(result_calls) >= 2

    @pytest.mark.asyncio
    async def test_stop_halts_periodic_loop(self, service, mock_redis, config):
        """stop() halts the periodic loop."""
        config.interval_seconds = 0.05

        await service.start()
        await asyncio.sleep(0.1)
        await service.stop()

        call_count = len([c for c in mock_redis.publish.call_args_list
                         if c[0][0] == "reconciliation:result"])
        await asyncio.sleep(0.15)  # Wait more

        # No new calls after stop
        new_call_count = len([c for c in mock_redis.publish.call_args_list
                             if c[0][0] == "reconciliation:result"])
        assert new_call_count == call_count

    @pytest.mark.asyncio
    async def test_startup_reconciliation(self, service, mock_redis):
        """Reconciliation runs immediately on startup."""
        await service.start()
        await asyncio.sleep(0.01)  # Brief wait
        await service.stop()

        # Check first result has startup context
        result_calls = [c for c in mock_redis.publish.call_args_list
                       if c[0][0] == "reconciliation:result"]
        assert len(result_calls) >= 1

        first_payload = json.loads(result_calls[0][0][1])
        assert first_payload["context"]["trigger"] == "startup"

    @pytest.mark.asyncio
    async def test_periodic_context(self, service, mock_redis, config):
        """Periodic runs have correct context."""
        config.interval_seconds = 0.05

        await service.start()
        await asyncio.sleep(0.12)  # Wait for startup + 1 periodic
        await service.stop()

        result_calls = [c for c in mock_redis.publish.call_args_list
                       if c[0][0] == "reconciliation:result"]
        # Find a periodic one (not startup)
        periodic_calls = [c for c in result_calls
                         if json.loads(c[0][1])["context"]["trigger"] == "periodic"]
        assert len(periodic_calls) >= 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestPeriodicReconciliation -v`
Expected: FAIL with "AttributeError: 'ReconciliationService' object has no attribute 'start'"

**Step 3: Implement start/stop lifecycle**

```python
# Add to backend/src/reconciliation/service.py
import asyncio

# Add to __init__:
self._running = False
self._periodic_task: asyncio.Task | None = None

# Add methods:
async def start(self) -> None:
    """Start periodic reconciliation loop."""
    if self._running:
        return

    self._running = True

    # Run startup reconciliation immediately
    await self.reconcile(context={"trigger": "startup"})

    # Start periodic loop
    self._periodic_task = asyncio.create_task(self._periodic_loop())

async def stop(self) -> None:
    """Stop periodic loop."""
    self._running = False
    if self._periodic_task:
        self._periodic_task.cancel()
        try:
            await self._periodic_task
        except asyncio.CancelledError:
            pass
        self._periodic_task = None

async def _periodic_loop(self) -> None:
    """Run reconciliation at configured interval."""
    while self._running:
        await asyncio.sleep(self._config.interval_seconds)
        if not self._running:
            break
        await self.reconcile(context={"trigger": "periodic"})
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestPeriodicReconciliation -v`
Expected: PASS (4 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/service.py backend/tests/reconciliation/test_service.py
git commit -m "feat(reconciliation): add periodic reconciliation loop with start/stop"
```

---

## Task 11: ReconciliationService - Post-Fill Trigger with Debounce

**Files:**
- Modify: `backend/src/reconciliation/service.py`
- Modify: `backend/tests/reconciliation/test_service.py`

**Step 1: Write failing tests**

```python
# Add to backend/tests/reconciliation/test_service.py
from src.strategies.signals import OrderFill


class TestPostFillReconciliation:
    @pytest.mark.asyncio
    async def test_on_fill_triggers_reconciliation(self, service, mock_redis, config):
        """on_fill triggers reconciliation with fill context."""
        config.post_fill_delay_seconds = 0.01  # Fast for testing

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="ORD-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow(),
        )

        await service.on_fill(fill)
        await asyncio.sleep(0.05)

        result_calls = [c for c in mock_redis.publish.call_args_list
                       if c[0][0] == "reconciliation:result"]
        assert len(result_calls) == 1

        payload = json.loads(result_calls[0][0][1])
        assert payload["context"]["trigger"] == "post_fill"
        assert payload["context"]["order_id"] == "ORD-001"
        assert payload["context"]["fill_id"] == "FILL-001"
        assert payload["context"]["symbol"] == "AAPL"

    @pytest.mark.asyncio
    async def test_post_fill_debounced(self, service, mock_redis, config):
        """Multiple rapid fills are debounced to single reconciliation."""
        config.post_fill_delay_seconds = 0.1

        fill1 = OrderFill("FILL-001", "ORD-001", "AAPL", "buy", 50, Decimal("150.00"), datetime.utcnow())
        fill2 = OrderFill("FILL-002", "ORD-001", "AAPL", "buy", 50, Decimal("150.00"), datetime.utcnow())

        # Fire two fills rapidly
        await service.on_fill(fill1)
        await asyncio.sleep(0.02)  # Before debounce expires
        await service.on_fill(fill2)
        await asyncio.sleep(0.15)  # After debounce expires

        # Should only have one reconciliation (debounced)
        result_calls = [c for c in mock_redis.publish.call_args_list
                       if c[0][0] == "reconciliation:result"]
        assert len(result_calls) == 1

    @pytest.mark.asyncio
    async def test_post_fill_disabled_when_service_disabled(self, service, config, mock_redis):
        """on_fill does nothing when service is disabled."""
        config.enabled = False

        fill = OrderFill("FILL-001", "ORD-001", "AAPL", "buy", 100, Decimal("150.00"), datetime.utcnow())
        await service.on_fill(fill)
        await asyncio.sleep(0.1)

        assert mock_redis.publish.call_count == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestPostFillReconciliation -v`
Expected: FAIL with "AttributeError: 'ReconciliationService' object has no attribute 'on_fill'"

**Step 3: Implement on_fill with debounce**

```python
# Add to ReconciliationService __init__:
self._pending_fill_task: asyncio.Task | None = None
self._last_fill: OrderFill | None = None

# Add import at top:
from src.strategies.signals import OrderFill

# Add method:
async def on_fill(self, fill: OrderFill) -> None:
    """
    Called after a fill - triggers reconciliation with fill context.
    Debounced to avoid excessive checks on rapid fills.
    """
    if not self._config.enabled:
        return

    self._last_fill = fill

    # Cancel any pending debounced reconciliation
    if self._pending_fill_task and not self._pending_fill_task.done():
        self._pending_fill_task.cancel()
        try:
            await self._pending_fill_task
        except asyncio.CancelledError:
            pass

    # Schedule new debounced reconciliation
    self._pending_fill_task = asyncio.create_task(self._debounced_post_fill())

async def _debounced_post_fill(self) -> None:
    """Wait for debounce period then run post-fill reconciliation."""
    await asyncio.sleep(self._config.post_fill_delay_seconds)

    if self._last_fill:
        context = {
            "trigger": "post_fill",
            "order_id": self._last_fill.order_id,
            "fill_id": self._last_fill.fill_id,
            "symbol": self._last_fill.symbol,
        }
        await self.reconcile(context=context)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_service.py::TestPostFillReconciliation -v`
Expected: PASS (3 passed)

**Step 5: Commit**

```bash
git add backend/src/reconciliation/service.py backend/tests/reconciliation/test_service.py
git commit -m "feat(reconciliation): add post-fill trigger with debounce"
```

---

## Task 12: Package Exports

**Files:**
- Modify: `backend/src/reconciliation/__init__.py`

**Step 1: Write failing test**

```python
# Add to backend/tests/reconciliation/test_models.py
class TestPackageExports:
    def test_exports_from_package(self):
        from src.reconciliation import (
            DiscrepancyType,
            DiscrepancySeverity,
            Discrepancy,
            ReconciliationConfig,
            ReconciliationResult,
            ReconciliationService,
            Comparator,
        )
        # Just verify imports work
        assert DiscrepancyType is not None
        assert ReconciliationService is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/reconciliation/test_models.py::TestPackageExports -v`
Expected: FAIL with "cannot import name 'ReconciliationService'"

**Step 3: Update package exports**

```python
# backend/src/reconciliation/__init__.py
"""Reconciliation service package."""

from src.reconciliation.models import (
    DiscrepancyType,
    DiscrepancySeverity,
    Discrepancy,
    ReconciliationConfig,
    ReconciliationResult,
    DEFAULT_SEVERITY_MAP,
)
from src.reconciliation.comparator import Comparator
from src.reconciliation.service import ReconciliationService

__all__ = [
    "DiscrepancyType",
    "DiscrepancySeverity",
    "Discrepancy",
    "ReconciliationConfig",
    "ReconciliationResult",
    "DEFAULT_SEVERITY_MAP",
    "Comparator",
    "ReconciliationService",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/reconciliation/test_models.py::TestPackageExports -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/reconciliation/__init__.py backend/tests/reconciliation/test_models.py
git commit -m "feat(reconciliation): add package exports"
```

---

## Task 13: Full Test Suite Verification

**Files:** None (verification only)

**Step 1: Run all reconciliation tests**

Run: `cd backend && pytest tests/reconciliation/ -v`
Expected: All tests pass

**Step 2: Run all backend tests**

Run: `cd backend && pytest -v`
Expected: All tests pass (should be ~170+ tests)

**Step 3: Final commit with feature complete message**

```bash
git add .
git commit -m "feat(reconciliation): complete Reconciliation Service implementation

Implements Phase 1 reconciliation:
- DiscrepancyType and DiscrepancySeverity enums
- Discrepancy dataclass with severity mapping
- ReconciliationConfig and ReconciliationResult
- BrokerQuery protocol (implemented by PaperBroker)
- Comparator for position/account comparison
- ReconciliationService with:
  - On-demand reconcile
  - Periodic loop (start/stop)
  - Post-fill trigger with debounce
  - Redis publishing to reconciliation:* channels

All 13 implementation tasks complete."
```

**Step 4: Push and create PR**

```bash
git push -u origin feat/reconciliation
gh pr create --title "feat(reconciliation): add Reconciliation Service" --body "$(cat <<'EOF'
## Summary
- Adds ReconciliationService for comparing local position/account state with broker
- Detects 6 discrepancy types with severity levels (INFO/WARNING/CRITICAL)
- Runs on multiple triggers: periodic, startup, on-demand, post-fill (debounced)
- Publishes results to Redis `reconciliation:*` channels for operator alerting
- BrokerQuery protocol for read-only broker state access
- PaperBroker now implements BrokerQuery

## Test plan
- [ ] All new reconciliation tests pass
- [ ] All existing tests pass (no regressions)
- [ ] Verify discrepancy detection for position mismatches
- [ ] Verify tolerance-based account comparison
- [ ] Verify Redis publishing with run_id correlation

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
