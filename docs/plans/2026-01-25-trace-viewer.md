# Trace Viewer + Slippage Analysis Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Signal-to-fill audit trail with execution quality analysis for backtests.

**Architecture:** Capture signal context during backtest, calculate slippage on fill, return traces in BacktestResult. Frontend displays trace table and slippage statistics.

**Tech Stack:** Python dataclasses, Pydantic schemas, React components

---

## Design Decisions

### Data Models

```python
JsonScalar = str | int | float | bool | None

@dataclass(frozen=True)
class BarSnapshot:
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

@dataclass(frozen=True)
class PortfolioSnapshot:
    cash: Decimal
    position_qty: int
    position_avg_cost: Decimal | None
    equity: Decimal

@dataclass(frozen=True)
class StrategySnapshot:
    """Constraints: keys <= 20, string values <= 256 chars, total <= 8KB"""
    strategy_class: str
    params: dict[str, JsonScalar]
    state: dict[str, JsonScalar]

@dataclass(frozen=True)
class SignalTrace:
    trace_id: str
    signal_timestamp: datetime
    symbol: str
    signal_direction: Literal["buy", "sell"]
    signal_quantity: int
    signal_reason: str | None
    signal_bar: BarSnapshot
    portfolio_state: PortfolioSnapshot
    strategy_snapshot: StrategySnapshot | None
    fill_bar: BarSnapshot | None
    fill_timestamp: datetime | None
    fill_quantity: int | None
    fill_price: Decimal | None
    expected_price: Decimal | None
    expected_price_type: Literal["next_bar_open", "signal_bar_close", "mid_quote", "limit_price"] | None
    slippage: Decimal | None
    slippage_bps: Decimal | None
    commission: Decimal | None
```

### MVP Rules (Hardcoded)

| Rule | Decision |
|------|----------|
| expected_price_type | "next_bar_open" for backtest |
| expected_price | fill_bar.open |
| fill_timestamp | fill_bar.timestamp |
| Missing data | If fill_price/expected_price is None or expected_price == 0 → slippage = None, slippage_bps = None |
| Slippage formula | slippage = fill_price - expected_price |
| Slippage BPS | (slippage / expected_price) * 10000, ROUND_HALF_UP |
| Buy slippage > 0 | Bad (bought higher) |
| Sell slippage > 0 | Bad (sold lower) |

---

## Task 1: Trace Data Models

**Files:**
- Create: `backend/src/backtest/trace.py`
- Test: `backend/tests/backtest/test_trace.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_trace.py
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from src.backtest.trace import (
    BarSnapshot,
    PortfolioSnapshot,
    StrategySnapshot,
    SignalTrace,
    JsonScalar,
)


class TestBarSnapshot:
    def test_create_bar_snapshot(self):
        snapshot = BarSnapshot(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )
        assert snapshot.symbol == "AAPL"
        assert snapshot.close == Decimal("101")

    def test_bar_snapshot_is_frozen(self):
        snapshot = BarSnapshot(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )
        with pytest.raises(Exception):
            snapshot.close = Decimal("200")


class TestPortfolioSnapshot:
    def test_create_portfolio_snapshot(self):
        snapshot = PortfolioSnapshot(
            cash=Decimal("50000"),
            position_qty=100,
            position_avg_cost=Decimal("150"),
            equity=Decimal("65000"),
        )
        assert snapshot.cash == Decimal("50000")
        assert snapshot.position_qty == 100


class TestStrategySnapshot:
    def test_create_strategy_snapshot(self):
        snapshot = StrategySnapshot(
            strategy_class="MomentumStrategy",
            params={"lookback": 20, "threshold": 2.0},
            state={"sma_20": 150.5, "signal_strength": 0.8},
        )
        assert snapshot.strategy_class == "MomentumStrategy"
        assert snapshot.params["lookback"] == 20
        assert snapshot.state["sma_20"] == 150.5

    def test_strategy_snapshot_only_json_scalars(self):
        # Valid scalars
        snapshot = StrategySnapshot(
            strategy_class="Test",
            params={"int": 1, "float": 1.5, "str": "test", "bool": True, "none": None},
            state={},
        )
        assert snapshot.params["int"] == 1


class TestSignalTrace:
    def test_create_signal_trace_minimal(self):
        """Create trace with required fields only."""
        bar = BarSnapshot(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("50000"),
        )
        trace = SignalTrace(
            trace_id="abc-123",
            signal_timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            signal_bar=bar,
            portfolio_state=portfolio,
            strategy_snapshot=None,
            fill_bar=None,
            fill_timestamp=None,
            fill_quantity=None,
            fill_price=None,
            expected_price=None,
            expected_price_type=None,
            slippage=None,
            slippage_bps=None,
            commission=None,
        )
        assert trace.trace_id == "abc-123"
        assert trace.signal_direction == "buy"
        assert trace.strategy_snapshot is None

    def test_create_signal_trace_with_fill(self):
        """Create trace with fill data and slippage."""
        signal_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )
        fill_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc),
            open=Decimal("101.50"),
            high=Decimal("103"),
            low=Decimal("101"),
            close=Decimal("102"),
            volume=1000000,
        )
        portfolio = PortfolioSnapshot(
            cash=Decimal("50000"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("50000"),
        )
        trace = SignalTrace(
            trace_id="abc-123",
            signal_timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason="momentum signal",
            signal_bar=signal_bar,
            portfolio_state=portfolio,
            strategy_snapshot=None,
            fill_bar=fill_bar,
            fill_timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc),
            fill_quantity=100,
            fill_price=Decimal("101.55"),
            expected_price=Decimal("101.50"),
            expected_price_type="next_bar_open",
            slippage=Decimal("0.05"),
            slippage_bps=Decimal("4.93"),
            commission=Decimal("0.50"),
        )
        assert trace.fill_price == Decimal("101.55")
        assert trace.slippage == Decimal("0.05")
        assert trace.expected_price_type == "next_bar_open"
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_trace.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/trace.py
"""Signal trace models for execution audit trail."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

# JSON-safe scalar types for strategy snapshot
JsonScalar = str | int | float | bool | None


@dataclass(frozen=True)
class BarSnapshot:
    """Lightweight bar capture for trace context."""
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class PortfolioSnapshot:
    """Portfolio state at signal time."""
    cash: Decimal
    position_qty: int
    position_avg_cost: Decimal | None
    equity: Decimal


@dataclass(frozen=True)
class StrategySnapshot:
    """Lightweight strategy state - JSON scalars only.

    Constraints (enforced at creation):
    - keys <= 20
    - each string value <= 256 chars
    - total serialized size <= 8KB
    """
    strategy_class: str
    params: dict[str, JsonScalar]
    state: dict[str, JsonScalar]


@dataclass(frozen=True)
class SignalTrace:
    """Complete audit trail from signal generation to fill.

    Slippage sign convention:
    - slippage = fill_price - expected_price
    - Buy: slippage > 0 means bought higher (bad)
    - Sell: slippage > 0 means sold lower (bad)
    """
    trace_id: str
    signal_timestamp: datetime

    # Signal details
    symbol: str
    signal_direction: Literal["buy", "sell"]
    signal_quantity: int
    signal_reason: str | None

    # Context at signal time
    signal_bar: BarSnapshot
    portfolio_state: PortfolioSnapshot
    strategy_snapshot: StrategySnapshot | None

    # Fill outcome
    fill_bar: BarSnapshot | None
    fill_timestamp: datetime | None
    fill_quantity: int | None
    fill_price: Decimal | None

    # Slippage calculation
    expected_price: Decimal | None
    expected_price_type: Literal["next_bar_open", "signal_bar_close", "mid_quote", "limit_price"] | None
    slippage: Decimal | None
    slippage_bps: Decimal | None
    commission: Decimal | None
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_trace.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/trace.py backend/tests/backtest/test_trace.py
git commit -m "feat(backtest): add trace data models"
```

---

## Task 2: TraceBuilder

**Files:**
- Create: `backend/src/backtest/trace_builder.py`
- Test: `backend/tests/backtest/test_trace_builder.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_trace_builder.py
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from src.backtest.trace import BarSnapshot, PortfolioSnapshot, StrategySnapshot, SignalTrace
from src.backtest.trace_builder import TraceBuilder
from src.backtest.models import Bar, Trade


class TestTraceBuilder:
    def test_create_pending_trace(self):
        """Create trace with signal info, no fill yet."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )

        trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason="test",
            cash=Decimal("50000"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("50000"),
            strategy_snapshot=None,
        )

        assert trace.trace_id is not None
        assert trace.signal_direction == "buy"
        assert trace.signal_quantity == 100
        assert trace.signal_bar.symbol == "AAPL"
        assert trace.fill_bar is None
        assert trace.slippage is None

    def test_complete_trace_with_fill(self):
        """Complete pending trace with fill data."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc),
            open=Decimal("101.50"),
            high=Decimal("103"),
            low=Decimal("101"),
            close=Decimal("102"),
            volume=1000000,
        )

        pending = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("50000"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("50000"),
            strategy_snapshot=None,
        )

        completed = TraceBuilder.complete(
            pending_trace=pending,
            fill_bar=fill_bar,
            fill_price=Decimal("101.55"),
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        assert completed.fill_bar is not None
        assert completed.fill_bar.open == Decimal("101.50")
        assert completed.fill_price == Decimal("101.55")
        assert completed.expected_price == Decimal("101.50")  # fill_bar.open
        assert completed.expected_price_type == "next_bar_open"
        assert completed.slippage == Decimal("0.05")  # 101.55 - 101.50
        assert completed.fill_timestamp == fill_bar.timestamp

    def test_slippage_bps_calculation(self):
        """Slippage BPS is (slippage / expected_price) * 10000."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("103"),
            low=Decimal("99"),
            close=Decimal("102"),
            volume=1000000,
        )

        pending = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("50000"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("50000"),
            strategy_snapshot=None,
        )

        completed = TraceBuilder.complete(
            pending_trace=pending,
            fill_bar=fill_bar,
            fill_price=Decimal("100.10"),  # 10 cents slippage on $100
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        # slippage_bps = (0.10 / 100) * 10000 = 10 bps
        assert completed.slippage_bps == Decimal("10")

    def test_missing_data_slippage_is_none(self):
        """Slippage is None when fill_price or expected_price missing."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 1, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("102"),
            low=Decimal("99"),
            close=Decimal("101"),
            volume=1000000,
        )

        pending = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("50000"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("50000"),
            strategy_snapshot=None,
        )

        # No fill bar means no expected_price
        completed = TraceBuilder.complete(
            pending_trace=pending,
            fill_bar=None,
            fill_price=None,
            fill_quantity=None,
            commission=None,
        )

        assert completed.slippage is None
        assert completed.slippage_bps is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/backtest/test_trace_builder.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/trace_builder.py
"""Builder for creating and completing signal traces."""

import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from src.backtest.models import Bar
from src.backtest.trace import (
    BarSnapshot,
    PortfolioSnapshot,
    StrategySnapshot,
    SignalTrace,
)


class TraceBuilder:
    """Factory for creating signal traces."""

    @staticmethod
    def create_pending(
        signal_bar: Bar,
        signal_direction: Literal["buy", "sell"],
        signal_quantity: int,
        signal_reason: str | None,
        cash: Decimal,
        position_qty: int,
        position_avg_cost: Decimal | None,
        equity: Decimal,
        strategy_snapshot: StrategySnapshot | None,
    ) -> SignalTrace:
        """Create a pending trace when signal is generated.

        Fill fields are set to None until complete() is called.
        """
        bar_snapshot = BarSnapshot(
            symbol=signal_bar.symbol,
            timestamp=signal_bar.timestamp,
            open=signal_bar.open,
            high=signal_bar.high,
            low=signal_bar.low,
            close=signal_bar.close,
            volume=signal_bar.volume,
        )

        portfolio_snapshot = PortfolioSnapshot(
            cash=cash,
            position_qty=position_qty,
            position_avg_cost=position_avg_cost,
            equity=equity,
        )

        return SignalTrace(
            trace_id=str(uuid.uuid4()),
            signal_timestamp=signal_bar.timestamp,
            symbol=signal_bar.symbol,
            signal_direction=signal_direction,
            signal_quantity=signal_quantity,
            signal_reason=signal_reason,
            signal_bar=bar_snapshot,
            portfolio_state=portfolio_snapshot,
            strategy_snapshot=strategy_snapshot,
            fill_bar=None,
            fill_timestamp=None,
            fill_quantity=None,
            fill_price=None,
            expected_price=None,
            expected_price_type=None,
            slippage=None,
            slippage_bps=None,
            commission=None,
        )

    @staticmethod
    def complete(
        pending_trace: SignalTrace,
        fill_bar: Bar | None,
        fill_price: Decimal | None,
        fill_quantity: int | None,
        commission: Decimal | None,
    ) -> SignalTrace:
        """Complete a pending trace with fill data.

        Calculates slippage based on MVP rules:
        - expected_price = fill_bar.open (next_bar_open model)
        - slippage = fill_price - expected_price
        - slippage_bps = (slippage / expected_price) * 10000

        If any required data is missing, slippage fields are None.
        """
        fill_bar_snapshot = None
        fill_timestamp = None
        expected_price = None
        expected_price_type = None
        slippage = None
        slippage_bps = None

        if fill_bar is not None:
            fill_bar_snapshot = BarSnapshot(
                symbol=fill_bar.symbol,
                timestamp=fill_bar.timestamp,
                open=fill_bar.open,
                high=fill_bar.high,
                low=fill_bar.low,
                close=fill_bar.close,
                volume=fill_bar.volume,
            )
            fill_timestamp = fill_bar.timestamp
            expected_price = fill_bar.open
            expected_price_type = "next_bar_open"

        # Calculate slippage only if we have all required data
        if (
            fill_price is not None
            and expected_price is not None
            and expected_price != Decimal("0")
        ):
            slippage = fill_price - expected_price
            # BPS = (slippage / expected_price) * 10000, rounded
            slippage_bps = (
                (slippage / expected_price) * Decimal("10000")
            ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

        return SignalTrace(
            trace_id=pending_trace.trace_id,
            signal_timestamp=pending_trace.signal_timestamp,
            symbol=pending_trace.symbol,
            signal_direction=pending_trace.signal_direction,
            signal_quantity=pending_trace.signal_quantity,
            signal_reason=pending_trace.signal_reason,
            signal_bar=pending_trace.signal_bar,
            portfolio_state=pending_trace.portfolio_state,
            strategy_snapshot=pending_trace.strategy_snapshot,
            fill_bar=fill_bar_snapshot,
            fill_timestamp=fill_timestamp,
            fill_quantity=fill_quantity,
            fill_price=fill_price,
            expected_price=expected_price,
            expected_price_type=expected_price_type,
            slippage=slippage,
            slippage_bps=slippage_bps,
            commission=commission,
        )
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/backtest/test_trace_builder.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/trace_builder.py backend/tests/backtest/test_trace_builder.py
git commit -m "feat(backtest): add TraceBuilder for signal traces"
```

---

## Task 3: Update BacktestResult with traces

**Files:**
- Modify: `backend/src/backtest/models.py`
- Modify: `backend/tests/backtest/test_models.py`

Add field to BacktestResult:
```python
traces: list[SignalTrace] = field(default_factory=list)
```

**Commit:** `feat(backtest): add traces field to BacktestResult`

---

## Task 4: Integrate TraceBuilder into BacktestEngine

**Files:**
- Modify: `backend/src/backtest/engine.py`
- Modify: `backend/tests/backtest/test_engine.py`

Modify engine to:
1. Create pending trace when signal generated
2. Complete trace when fill executed
3. Include traces in result

**Commit:** `feat(backtest): integrate trace capture into engine`

---

## Task 5: Update API Schema with traces

**Files:**
- Modify: `backend/src/api/backtest.py`
- Modify: `backend/tests/api/test_backtest.py`

Add response schemas:
- BarSnapshotResponse
- PortfolioSnapshotResponse
- StrategySnapshotResponse
- SignalTraceResponse
- Add traces to BacktestResponse

**Commit:** `feat(api): add trace schemas to backtest response`

---

## Task 6: Frontend Types for Traces

**Files:**
- Modify: `frontend/src/types/index.ts`

Add TypeScript interfaces:
- BarSnapshot
- PortfolioSnapshot
- StrategySnapshot
- SignalTrace
- Update BacktestResult

**Commit:** `feat(frontend): add trace types`

---

## Task 7: TraceTable Component

**Files:**
- Create: `frontend/src/components/TraceTable.tsx`
- Create: `frontend/src/components/TraceTable.test.tsx`

Display traces in a table with columns:
Time | Symbol | Direction | Qty | Expected | Fill | Slippage (bps) | Status

**Commit:** `feat(frontend): add TraceTable component`

---

## Task 8: SlippageStats Component

**Files:**
- Create: `frontend/src/components/SlippageStats.tsx`
- Create: `frontend/src/components/SlippageStats.test.tsx`

Display aggregate slippage statistics:
- Total slippage ($)
- Avg slippage per trade (bps)
- Worst slippage (bps)
- % of trades with positive slippage

**Commit:** `feat(frontend): add SlippageStats component`

---

## Task 9: Integrate Traces into BacktestResults

**Files:**
- Modify: `frontend/src/components/BacktestResults.tsx`
- Modify: `frontend/src/components/BacktestResults.test.tsx`

Add TraceTable and SlippageStats to BacktestResults component.

**Commit:** `feat(frontend): integrate traces into backtest results`

---

## Task 10: Update Module Exports

**Files:**
- Modify: `backend/src/backtest/__init__.py`

Export trace modules:
- SignalTrace, BarSnapshot, PortfolioSnapshot, StrategySnapshot
- TraceBuilder

**Commit:** `feat(backtest): export trace modules`

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Trace data models | trace.py |
| 2 | TraceBuilder | trace_builder.py |
| 3 | BacktestResult.traces | models.py |
| 4 | Engine integration | engine.py |
| 5 | API schemas | api/backtest.py |
| 6 | Frontend types | types/index.ts |
| 7 | TraceTable component | TraceTable.tsx |
| 8 | SlippageStats component | SlippageStats.tsx |
| 9 | Integrate into results | BacktestResults.tsx |
| 10 | Module exports | __init__.py |
