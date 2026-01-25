# Backtest Engine + Strategy Warm-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable backtesting strategies against historical data with proper warm-up for indicator initialization.

**Architecture:** Single event loop feeds bars to strategy. Warm-up phase discards signals; backtest phase executes at next-bar open with slippage/commission. Metrics computed from equity curve.

**Tech Stack:** Python 3.10+, FastAPI, pytest, Recharts (frontend)

---

## Locked Decisions

### Event Order (No Lookahead)
```
For bar[i]:
1. Strategy receives MarketData (price = bar[i].close)
2. Strategy emits Signal (timestamp = bar[i].timestamp)
3. Signal executes on bar[i+1].open (if exists)

RULE: When processing bar[i], NEVER read bar[i+1] except to check existence.
```

### Warm-up Calculation
- Load `start_date - 3×warmup_bars natural days` to `end_date`
- Slice by bar count, not calendar
- Error if insufficient bars

### Portfolio Constraints
- Long-only (position_qty >= 0)
- No leverage (cash >= 0)
- Sell <= position_qty

### Metrics
- `sharpe_ratio`: Return 0 if std=0 or len<2
- `annualized_return`: Uses trading days = len(equity_curve) - 1
- `win_rate`: Profitable sells / total sells

### BarLoader
- CSVBarLoader for MVP (no external APIs)

---

## Task 1: Bar Model

**Files:**
- Create: `backend/src/backtest/__init__.py`
- Create: `backend/src/backtest/models.py`
- Create: `backend/tests/backtest/__init__.py`
- Create: `backend/tests/backtest/test_models.py`

**Step 1: Write failing test for Bar**

```python
# backend/tests/backtest/test_models.py
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.backtest.models import Bar


class TestBar:
    def test_create_bar(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 20, 21, 0, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.50"),
            volume=1000000,
        )
        assert bar.symbol == "AAPL"
        assert bar.close == Decimal("151.50")
        assert bar.interval == "1d"

    def test_bar_is_frozen(self):
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 20, 21, 0, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.50"),
            volume=1000000,
        )
        with pytest.raises(AttributeError):
            bar.close = Decimal("160.00")

    def test_bar_requires_timezone_aware_timestamp(self):
        # Naive datetime should work but we document it must be tz-aware
        # This test documents the expectation
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2026, 1, 20, 21, 0, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.50"),
            volume=1000000,
        )
        assert bar.timestamp.tzinfo is not None
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_models.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'src.backtest'`

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/__init__.py
"""Backtest engine package."""

# backend/src/backtest/models.py
"""Backtest data models."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class Bar:
    """OHLCV bar representing a closed interval (prev_close, timestamp].

    Event order: Signal generated at bar close, fill at next bar open.
    Timezone: Must be timezone-aware (UTC recommended).
    """
    symbol: str
    timestamp: datetime  # Bar close time, timezone-aware
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    interval: Literal["1d"] = "1d"
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_models.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/ backend/tests/backtest/
git commit -m "feat(backtest): add Bar model"
```

---

## Task 2: Trade Model

**Files:**
- Modify: `backend/src/backtest/models.py`
- Modify: `backend/tests/backtest/test_models.py`

**Step 1: Write failing test for Trade**

```python
# backend/tests/backtest/test_models.py (add to file)
from src.backtest.models import Bar, Trade


class TestTrade:
    def test_create_buy_trade(self):
        trade = Trade(
            trade_id="trade-001",
            timestamp=datetime(2026, 1, 21, 14, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),  # 5 bps on $150
            fill_price=Decimal("150.075"),  # gross + slippage for buy
            commission=Decimal("0.50"),  # 100 * $0.005
            signal_bar_timestamp=datetime(2026, 1, 20, 21, 0, 0, tzinfo=timezone.utc),
        )
        assert trade.side == "buy"
        assert trade.fill_price == Decimal("150.075")

    def test_create_sell_trade(self):
        trade = Trade(
            trade_id="trade-002",
            timestamp=datetime(2026, 1, 22, 14, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("155.00"),
            slippage=Decimal("0.0775"),  # 5 bps
            fill_price=Decimal("154.9225"),  # gross - slippage for sell
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2026, 1, 21, 21, 0, 0, tzinfo=timezone.utc),
        )
        assert trade.side == "sell"
        assert trade.fill_price == Decimal("154.9225")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_models.py::TestTrade -v
```
Expected: FAIL with `ImportError`

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/models.py (add to file)

@dataclass
class Trade:
    """Execution record for a backtest trade."""
    trade_id: str
    timestamp: datetime  # Fill time (next bar open)
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    gross_price: Decimal  # Next bar open (before slippage)
    slippage: Decimal  # Per-share slippage amount
    fill_price: Decimal  # Actual execution price
    commission: Decimal  # Total commission
    signal_bar_timestamp: datetime  # When signal was generated
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_models.py::TestTrade -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/models.py backend/tests/backtest/test_models.py
git commit -m "feat(backtest): add Trade model"
```

---

## Task 3: BacktestConfig Model

**Files:**
- Modify: `backend/src/backtest/models.py`
- Modify: `backend/tests/backtest/test_models.py`

**Step 1: Write failing test**

```python
# backend/tests/backtest/test_models.py (add to file)
from datetime import date
from src.backtest.models import BacktestConfig


class TestBacktestConfig:
    def test_create_config_with_defaults(self):
        config = BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={"lookback_period": 20},
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            initial_capital=Decimal("100000"),
        )
        assert config.fill_model == "next_bar_open"
        assert config.slippage_model == "fixed_bps"
        assert config.slippage_bps == 5
        assert config.commission_model == "per_share"
        assert config.commission_per_share == Decimal("0.005")

    def test_config_with_custom_values(self):
        config = BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={},
            symbol="TSLA",
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=Decimal("50000"),
            slippage_bps=10,
            commission_per_share=Decimal("0.01"),
        )
        assert config.slippage_bps == 10
        assert config.commission_per_share == Decimal("0.01")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_models.py::TestBacktestConfig -v
```
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/models.py (add to file)
from datetime import date


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""
    strategy_class: str
    strategy_params: dict
    symbol: str
    start_date: date
    end_date: date
    initial_capital: Decimal
    fill_model: Literal["next_bar_open"] = "next_bar_open"
    slippage_model: Literal["fixed_bps"] = "fixed_bps"
    slippage_bps: int = 5
    commission_model: Literal["per_share"] = "per_share"
    commission_per_share: Decimal = Decimal("0.005")
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_models.py::TestBacktestConfig -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/models.py backend/tests/backtest/test_models.py
git commit -m "feat(backtest): add BacktestConfig model"
```

---

## Task 4: BacktestResult Model

**Files:**
- Modify: `backend/src/backtest/models.py`
- Modify: `backend/tests/backtest/test_models.py`

**Step 1: Write failing test**

```python
# backend/tests/backtest/test_models.py (add to file)
from src.backtest.models import BacktestConfig, BacktestResult, Trade


class TestBacktestResult:
    def test_create_result(self):
        config = BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={},
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
            initial_capital=Decimal("100000"),
        )
        result = BacktestResult(
            config=config,
            equity_curve=[
                (datetime(2025, 1, 2, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
                (datetime(2025, 1, 3, 21, 0, tzinfo=timezone.utc), Decimal("101000")),
            ],
            trades=[],
            final_equity=Decimal("110000"),
            final_cash=Decimal("110000"),
            final_position_qty=0,
            total_return=Decimal("0.10"),
            annualized_return=Decimal("0.10"),
            sharpe_ratio=Decimal("1.5"),
            max_drawdown=Decimal("0.05"),
            win_rate=Decimal("0.60"),
            total_trades=10,
            avg_trade_pnl=Decimal("1000"),
            warm_up_required_bars=20,
            warm_up_bars_used=20,
            first_signal_bar=datetime(2025, 1, 2, 21, 0, tzinfo=timezone.utc),
            started_at=datetime(2026, 1, 25, 10, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 1, 25, 10, 1, tzinfo=timezone.utc),
        )
        assert result.total_return == Decimal("0.10")
        assert result.total_trades == 10
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_models.py::TestBacktestResult -v
```
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/models.py (add to file)

@dataclass
class BacktestResult:
    """Complete results from a backtest run."""
    config: BacktestConfig

    # Equity curve: EOD valuations aligned to bar.timestamp
    equity_curve: list[tuple[datetime, Decimal]]

    # Trade log
    trades: list[Trade]

    # Final state
    final_equity: Decimal
    final_cash: Decimal
    final_position_qty: int

    # Summary metrics
    total_return: Decimal
    annualized_return: Decimal
    sharpe_ratio: Decimal
    max_drawdown: Decimal
    win_rate: Decimal
    total_trades: int
    avg_trade_pnl: Decimal

    # Warm-up tracking
    warm_up_required_bars: int
    warm_up_bars_used: int
    first_signal_bar: datetime | None

    # Metadata
    started_at: datetime
    completed_at: datetime
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_models.py::TestBacktestResult -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/models.py backend/tests/backtest/test_models.py
git commit -m "feat(backtest): add BacktestResult model"
```

---

## Task 5: BacktestPortfolio

**Files:**
- Create: `backend/src/backtest/portfolio.py`
- Create: `backend/tests/backtest/test_portfolio.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_portfolio.py
from decimal import Decimal

import pytest

from src.backtest.models import Trade
from src.backtest.portfolio import BacktestPortfolio


class TestBacktestPortfolio:
    def test_initial_state(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        assert portfolio.cash == Decimal("100000")
        assert portfolio.position_qty == 0
        assert portfolio.position_avg_cost == Decimal("0")

    def test_equity_no_position(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        assert portfolio.equity(current_price=Decimal("150")) == Decimal("100000")

    def test_equity_with_position(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        portfolio._cash = Decimal("85000")
        portfolio._position_qty = 100
        assert portfolio.equity(current_price=Decimal("160")) == Decimal("101000")

    def test_can_buy_sufficient_cash(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        assert portfolio.can_buy(
            price=Decimal("150"), quantity=100, commission=Decimal("0.50")
        ) is True

    def test_can_buy_insufficient_cash(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("1000"))
        assert portfolio.can_buy(
            price=Decimal("150"), quantity=100, commission=Decimal("0.50")
        ) is False

    def test_can_sell_with_position(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        portfolio._position_qty = 100
        assert portfolio.can_sell(quantity=50) is True
        assert portfolio.can_sell(quantity=100) is True
        assert portfolio.can_sell(quantity=101) is False

    def test_can_sell_no_position(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        assert portfolio.can_sell(quantity=1) is False


class TestApplyTrade:
    def test_apply_buy_trade(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        trade = Trade(
            trade_id="t1",
            timestamp=None,  # Not used in apply_trade
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150"),
            slippage=Decimal("0.075"),
            fill_price=Decimal("150.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=None,
        )
        portfolio.apply_trade(trade)

        # Cash: 100000 - (150.075 * 100) - 0.50 = 84992.00
        assert portfolio.cash == Decimal("84992.00")
        assert portfolio.position_qty == 100
        assert portfolio.position_avg_cost == Decimal("150.075")

    def test_apply_sell_trade(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        portfolio._cash = Decimal("85000")
        portfolio._position_qty = 100
        portfolio._position_avg_cost = Decimal("150")

        trade = Trade(
            trade_id="t2",
            timestamp=None,
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160"),
            slippage=Decimal("0.08"),
            fill_price=Decimal("159.92"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=None,
        )
        portfolio.apply_trade(trade)

        # Cash: 85000 + (159.92 * 100) - 0.50 = 100991.50
        assert portfolio.cash == Decimal("100991.50")
        assert portfolio.position_qty == 0

    def test_apply_partial_sell(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        portfolio._cash = Decimal("85000")
        portfolio._position_qty = 100
        portfolio._position_avg_cost = Decimal("150")

        trade = Trade(
            trade_id="t3",
            timestamp=None,
            symbol="AAPL",
            side="sell",
            quantity=50,
            gross_price=Decimal("160"),
            slippage=Decimal("0.08"),
            fill_price=Decimal("159.92"),
            commission=Decimal("0.25"),
            signal_bar_timestamp=None,
        )
        portfolio.apply_trade(trade)

        assert portfolio.position_qty == 50
        # Avg cost unchanged for partial sell
        assert portfolio.position_avg_cost == Decimal("150")

    def test_apply_additional_buy_updates_avg_cost(self):
        portfolio = BacktestPortfolio(initial_capital=Decimal("100000"))
        portfolio._cash = Decimal("70000")
        portfolio._position_qty = 100
        portfolio._position_avg_cost = Decimal("150")

        trade = Trade(
            trade_id="t4",
            timestamp=None,
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("160"),
            slippage=Decimal("0.08"),
            fill_price=Decimal("160.08"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=None,
        )
        portfolio.apply_trade(trade)

        assert portfolio.position_qty == 200
        # New avg cost: (100*150 + 100*160.08) / 200 = 155.04
        assert portfolio.position_avg_cost == Decimal("155.04")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_portfolio.py -v
```
Expected: FAIL with `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/portfolio.py
"""Backtest portfolio tracking."""
from decimal import Decimal

from src.backtest.models import Trade


class BacktestPortfolio:
    """Tracks cash, position, and equity during backtest.

    Constraints (long-only, no leverage):
    - position_qty >= 0 (no shorting)
    - cash >= 0 (no leverage)
    - sell quantity <= position_qty
    """

    def __init__(self, initial_capital: Decimal) -> None:
        self._cash: Decimal = initial_capital
        self._position_qty: int = 0
        self._position_avg_cost: Decimal = Decimal("0")

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def position_qty(self) -> int:
        return self._position_qty

    @property
    def position_avg_cost(self) -> Decimal:
        return self._position_avg_cost

    def equity(self, current_price: Decimal) -> Decimal:
        """Total portfolio value: cash + position * current_price."""
        return self._cash + (self._position_qty * current_price)

    def can_buy(self, price: Decimal, quantity: int, commission: Decimal) -> bool:
        """Check if sufficient cash for purchase."""
        total_cost = (price * quantity) + commission
        return self._cash >= total_cost

    def can_sell(self, quantity: int) -> bool:
        """Check if sufficient position to sell."""
        return self._position_qty >= quantity

    def apply_trade(self, trade: Trade) -> None:
        """Update cash and position based on trade."""
        if trade.side == "buy":
            total_cost = (trade.fill_price * trade.quantity) + trade.commission
            self._cash -= total_cost

            # Update average cost
            old_value = self._position_avg_cost * self._position_qty
            new_value = trade.fill_price * trade.quantity
            new_qty = self._position_qty + trade.quantity
            self._position_avg_cost = (old_value + new_value) / new_qty
            self._position_qty = new_qty
        else:  # sell
            proceeds = (trade.fill_price * trade.quantity) - trade.commission
            self._cash += proceeds
            self._position_qty -= trade.quantity
            # Note: avg_cost unchanged on sell (only matters for buy)
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_portfolio.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/portfolio.py backend/tests/backtest/test_portfolio.py
git commit -m "feat(backtest): add BacktestPortfolio"
```

---

## Task 6: SimulatedFillEngine

**Files:**
- Create: `backend/src/backtest/fill_engine.py`
- Create: `backend/tests/backtest/test_fill_engine.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_fill_engine.py
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.models import Bar
from src.strategies.signals import Signal


class TestSimulatedFillEngine:
    def test_execute_buy_with_slippage(self):
        engine = SimulatedFillEngine(
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            timestamp=datetime(2025, 1, 20, 21, 0, tzinfo=timezone.utc),
        )
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 21, 21, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.00"),
            volume=1000000,
        )

        trade = engine.execute(signal, fill_bar)

        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 100
        assert trade.gross_price == Decimal("150.00")
        # Slippage: 150 * 5/10000 = 0.075
        assert trade.slippage == Decimal("0.075")
        # Buy: fill = gross + slippage
        assert trade.fill_price == Decimal("150.075")
        # Commission: 100 * 0.005 = 0.50
        assert trade.commission == Decimal("0.50")
        assert trade.signal_bar_timestamp == signal.timestamp

    def test_execute_sell_with_slippage(self):
        engine = SimulatedFillEngine(
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="sell",
            quantity=100,
            order_type="market",
            timestamp=datetime(2025, 1, 20, 21, 0, tzinfo=timezone.utc),
        )
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 21, 21, 0, tzinfo=timezone.utc),
            open=Decimal("155.00"),
            high=Decimal("156.00"),
            low=Decimal("154.00"),
            close=Decimal("155.50"),
            volume=1000000,
        )

        trade = engine.execute(signal, fill_bar)

        assert trade.side == "sell"
        assert trade.gross_price == Decimal("155.00")
        # Slippage: 155 * 5/10000 = 0.0775
        assert trade.slippage == Decimal("0.0775")
        # Sell: fill = gross - slippage
        assert trade.fill_price == Decimal("154.9225")

    def test_execute_with_zero_slippage(self):
        engine = SimulatedFillEngine(
            slippage_bps=0,
            commission_per_share=Decimal("0"),
        )
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=50,
            order_type="market",
            timestamp=datetime(2025, 1, 20, 21, 0, tzinfo=timezone.utc),
        )
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 21, 21, 0, tzinfo=timezone.utc),
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.50"),
            volume=500000,
        )

        trade = engine.execute(signal, fill_bar)

        assert trade.slippage == Decimal("0")
        assert trade.fill_price == Decimal("100.00")
        assert trade.commission == Decimal("0")

    def test_trade_id_is_unique(self):
        engine = SimulatedFillEngine(
            slippage_bps=5,
            commission_per_share=Decimal("0.005"),
        )
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market",
            timestamp=datetime(2025, 1, 20, 21, 0, tzinfo=timezone.utc),
        )
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2025, 1, 21, 21, 0, tzinfo=timezone.utc),
            open=Decimal("150.00"),
            high=Decimal("152.00"),
            low=Decimal("149.00"),
            close=Decimal("151.00"),
            volume=1000000,
        )

        trade1 = engine.execute(signal, fill_bar)
        trade2 = engine.execute(signal, fill_bar)

        assert trade1.trade_id != trade2.trade_id
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_fill_engine.py -v
```
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/fill_engine.py
"""Simulated order execution for backtesting."""
from decimal import Decimal
from uuid import uuid4

from src.backtest.models import Bar, Trade
from src.strategies.signals import Signal


class SimulatedFillEngine:
    """Simulates order execution with slippage and commission."""

    def __init__(
        self,
        slippage_bps: int,
        commission_per_share: Decimal,
    ) -> None:
        self._slippage_bps = slippage_bps
        self._commission_per_share = commission_per_share

    def execute(self, signal: Signal, fill_bar: Bar) -> Trade:
        """Create a Trade from a Signal using fill_bar.open.

        Slippage:
          - Buy: fill_price = gross_price * (1 + slippage_bps/10000)
          - Sell: fill_price = gross_price * (1 - slippage_bps/10000)
        """
        gross_price = fill_bar.open
        slippage_rate = Decimal(self._slippage_bps) / Decimal("10000")
        slippage = gross_price * slippage_rate

        if signal.action == "buy":
            fill_price = gross_price + slippage
        else:
            fill_price = gross_price - slippage

        commission = self._commission_per_share * signal.quantity

        return Trade(
            trade_id=str(uuid4()),
            timestamp=fill_bar.timestamp,
            symbol=signal.symbol,
            side=signal.action,
            quantity=signal.quantity,
            gross_price=gross_price,
            slippage=slippage,
            fill_price=fill_price,
            commission=commission,
            signal_bar_timestamp=signal.timestamp,
        )
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_fill_engine.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/fill_engine.py backend/tests/backtest/test_fill_engine.py
git commit -m "feat(backtest): add SimulatedFillEngine"
```

---

## Task 7: MetricsCalculator

**Files:**
- Create: `backend/src/backtest/metrics.py`
- Create: `backend/tests/backtest/test_metrics.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_metrics.py
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.backtest.metrics import MetricsCalculator
from src.backtest.models import Trade


class TestMetricsCalculator:
    def test_total_return(self):
        equity_curve = [
            (datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2025, 1, 2, 21, 0, tzinfo=timezone.utc), Decimal("110000")),
        ]
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=[],
            initial_capital=Decimal("100000"),
        )
        assert metrics["total_return"] == Decimal("0.1")

    def test_annualized_return(self):
        # 10% return over 252 trading days = ~10% annualized
        equity_curve = [
            (datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
        ] + [
            (datetime(2025, 1, i, 21, 0, tzinfo=timezone.utc), Decimal("100000"))
            for i in range(2, 253)
        ]
        equity_curve.append(
            (datetime(2025, 12, 31, 21, 0, tzinfo=timezone.utc), Decimal("110000"))
        )
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=[],
            initial_capital=Decimal("100000"),
        )
        # Should be approximately 10% (252 trading days)
        assert Decimal("0.09") < metrics["annualized_return"] < Decimal("0.11")

    def test_sharpe_ratio_with_zero_std(self):
        # Flat equity curve = 0 std = sharpe 0
        equity_curve = [
            (datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2025, 1, 2, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2025, 1, 3, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
        ]
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=[],
            initial_capital=Decimal("100000"),
        )
        assert metrics["sharpe_ratio"] == Decimal("0")

    def test_sharpe_ratio_with_single_point(self):
        equity_curve = [
            (datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
        ]
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=[],
            initial_capital=Decimal("100000"),
        )
        assert metrics["sharpe_ratio"] == Decimal("0")

    def test_max_drawdown(self):
        equity_curve = [
            (datetime(2025, 1, 1, 21, 0, tzinfo=timezone.utc), Decimal("100000")),
            (datetime(2025, 1, 2, 21, 0, tzinfo=timezone.utc), Decimal("110000")),  # Peak
            (datetime(2025, 1, 3, 21, 0, tzinfo=timezone.utc), Decimal("99000")),   # Trough
            (datetime(2025, 1, 4, 21, 0, tzinfo=timezone.utc), Decimal("105000")),
        ]
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=[],
            initial_capital=Decimal("100000"),
        )
        # Drawdown: (110000 - 99000) / 110000 = 0.1 (10%)
        assert metrics["max_drawdown"] == Decimal("0.1")

    def test_win_rate_all_winners(self):
        trades = [
            Trade(
                trade_id="1", timestamp=None, symbol="AAPL", side="sell",
                quantity=100, gross_price=Decimal("160"), slippage=Decimal("0"),
                fill_price=Decimal("160"), commission=Decimal("0"),
                signal_bar_timestamp=None,
            ),
        ]
        # Need to track entry price for PnL calculation
        # For simplicity, assume we have entry info or use realized_pnl field
        # This test verifies the interface exists
        metrics = MetricsCalculator.compute(
            equity_curve=[(datetime(2025, 1, 1, tzinfo=timezone.utc), Decimal("100000"))],
            trades=trades,
            initial_capital=Decimal("100000"),
            entry_prices={"AAPL": Decimal("150")},  # Entry at 150, exit at 160 = win
        )
        assert metrics["win_rate"] == Decimal("1.0")

    def test_win_rate_no_trades(self):
        metrics = MetricsCalculator.compute(
            equity_curve=[(datetime(2025, 1, 1, tzinfo=timezone.utc), Decimal("100000"))],
            trades=[],
            initial_capital=Decimal("100000"),
        )
        assert metrics["win_rate"] == Decimal("0")

    def test_avg_trade_pnl_no_trades(self):
        metrics = MetricsCalculator.compute(
            equity_curve=[(datetime(2025, 1, 1, tzinfo=timezone.utc), Decimal("100000"))],
            trades=[],
            initial_capital=Decimal("100000"),
        )
        assert metrics["avg_trade_pnl"] == Decimal("0")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_metrics.py -v
```
Expected: FAIL

**Step 3: Write minimal implementation**

```python
# backend/src/backtest/metrics.py
"""Performance metrics calculation for backtests."""
from datetime import datetime
from decimal import Decimal
from typing import Any

from src.backtest.models import Trade


class MetricsCalculator:
    """Computes performance metrics from equity curve and trades."""

    @staticmethod
    def compute(
        equity_curve: list[tuple[datetime, Decimal]],
        trades: list[Trade],
        initial_capital: Decimal,
        entry_prices: dict[str, Decimal] | None = None,
    ) -> dict[str, Any]:
        """Compute all summary metrics.

        Args:
            equity_curve: List of (timestamp, portfolio_value) tuples
            trades: List of executed trades
            initial_capital: Starting capital
            entry_prices: Optional dict of symbol -> entry price for PnL calc

        Returns:
            Dict with metrics: total_return, annualized_return, sharpe_ratio,
            max_drawdown, win_rate, total_trades, avg_trade_pnl
        """
        entry_prices = entry_prices or {}

        # Total return
        if not equity_curve:
            final_equity = initial_capital
        else:
            final_equity = equity_curve[-1][1]
        total_return = (final_equity - initial_capital) / initial_capital

        # Annualized return (using trading days)
        trading_days = max(len(equity_curve) - 1, 1)
        annualized_return = (
            (1 + total_return) ** (Decimal("252") / Decimal(trading_days)) - 1
        )

        # Daily returns for Sharpe
        daily_returns = []
        for i in range(1, len(equity_curve)):
            prev_val = equity_curve[i - 1][1]
            curr_val = equity_curve[i][1]
            if prev_val != 0:
                daily_returns.append((curr_val - prev_val) / prev_val)

        # Sharpe ratio
        if len(daily_returns) < 2:
            sharpe_ratio = Decimal("0")
        else:
            mean_return = sum(daily_returns) / len(daily_returns)
            variance = sum((r - mean_return) ** 2 for r in daily_returns) / len(daily_returns)
            std_return = variance ** Decimal("0.5")
            if std_return == 0:
                sharpe_ratio = Decimal("0")
            else:
                sharpe_ratio = (mean_return / std_return) * (Decimal("252") ** Decimal("0.5"))

        # Max drawdown
        max_drawdown = Decimal("0")
        peak = Decimal("0")
        for _, value in equity_curve:
            if value > peak:
                peak = value
            if peak > 0:
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        # Win rate (based on sell trades with positive PnL)
        sell_trades = [t for t in trades if t.side == "sell"]
        if not sell_trades:
            win_rate = Decimal("0")
            avg_trade_pnl = Decimal("0")
        else:
            winning_trades = 0
            total_pnl = Decimal("0")
            for trade in sell_trades:
                entry_price = entry_prices.get(trade.symbol, trade.fill_price)
                pnl = (trade.fill_price - entry_price) * trade.quantity - trade.commission
                total_pnl += pnl
                if pnl > 0:
                    winning_trades += 1
            win_rate = Decimal(winning_trades) / Decimal(len(sell_trades))
            avg_trade_pnl = total_pnl / Decimal(len(sell_trades))

        return {
            "total_return": total_return,
            "annualized_return": annualized_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "total_trades": len(trades),
            "avg_trade_pnl": avg_trade_pnl,
        }
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_metrics.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/metrics.py backend/tests/backtest/test_metrics.py
git commit -m "feat(backtest): add MetricsCalculator"
```

---

## Task 8: CSVBarLoader

**Files:**
- Create: `backend/src/backtest/bar_loader.py`
- Create: `backend/tests/backtest/test_bar_loader.py`
- Create: `backend/tests/backtest/fixtures/sample_bars.csv`

**Step 1: Create test fixture**

```csv
# backend/tests/backtest/fixtures/sample_bars.csv
timestamp,symbol,open,high,low,close,volume
2025-01-02T21:00:00+00:00,AAPL,150.00,152.00,149.00,151.00,1000000
2025-01-03T21:00:00+00:00,AAPL,151.00,153.00,150.00,152.50,1100000
2025-01-06T21:00:00+00:00,AAPL,152.50,154.00,151.00,153.00,900000
2025-01-07T21:00:00+00:00,AAPL,153.00,155.00,152.00,154.50,1200000
2025-01-08T21:00:00+00:00,AAPL,154.50,156.00,154.00,155.00,1050000
```

**Step 2: Write failing tests**

```python
# backend/tests/backtest/test_bar_loader.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from src.backtest.bar_loader import CSVBarLoader


class TestCSVBarLoader:
    @pytest.fixture
    def sample_csv_path(self) -> Path:
        return Path(__file__).parent / "fixtures" / "sample_bars.csv"

    @pytest.mark.asyncio
    async def test_load_all_bars(self, sample_csv_path):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert len(bars) == 5
        assert bars[0].symbol == "AAPL"
        assert bars[0].close == Decimal("151.00")

    @pytest.mark.asyncio
    async def test_load_date_range(self, sample_csv_path):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 3),
            end_date=date(2025, 1, 7),
        )
        assert len(bars) == 3  # Jan 3, 6, 7

    @pytest.mark.asyncio
    async def test_bars_are_sorted_ascending(self, sample_csv_path):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        for i in range(1, len(bars)):
            assert bars[i].timestamp > bars[i - 1].timestamp

    @pytest.mark.asyncio
    async def test_bars_are_timezone_aware(self, sample_csv_path):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        for bar in bars:
            assert bar.timestamp.tzinfo is not None

    @pytest.mark.asyncio
    async def test_load_wrong_symbol_returns_empty(self, sample_csv_path):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        bars = await loader.load(
            symbol="TSLA",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )
        assert len(bars) == 0
```

**Step 3: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_bar_loader.py -v
```
Expected: FAIL

**Step 4: Write minimal implementation**

```python
# backend/src/backtest/bar_loader.py
"""Bar data loaders for backtesting."""
import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from src.backtest.models import Bar


class BarLoader(Protocol):
    """Protocol for loading historical bars."""

    async def load(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Load bars in chronological order (oldest first)."""
        ...


class CSVBarLoader:
    """Loads bars from a CSV file.

    Expected CSV format:
    timestamp,symbol,open,high,low,close,volume
    2025-01-02T21:00:00+00:00,AAPL,150.00,152.00,149.00,151.00,1000000
    """

    def __init__(self, csv_path: Path | str) -> None:
        self._csv_path = Path(csv_path)

    async def load(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> list[Bar]:
        """Load bars for symbol within date range."""
        bars = []

        with open(self._csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["symbol"] != symbol:
                    continue

                timestamp = datetime.fromisoformat(row["timestamp"])
                bar_date = timestamp.date()

                if bar_date < start_date or bar_date > end_date:
                    continue

                bar = Bar(
                    symbol=row["symbol"],
                    timestamp=timestamp,
                    open=Decimal(row["open"]),
                    high=Decimal(row["high"]),
                    low=Decimal(row["low"]),
                    close=Decimal(row["close"]),
                    volume=int(row["volume"]),
                )
                bars.append(bar)

        # Sort ascending by timestamp
        bars.sort(key=lambda b: b.timestamp)
        return bars
```

**Step 5: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_bar_loader.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/backtest/bar_loader.py backend/tests/backtest/test_bar_loader.py backend/tests/backtest/fixtures/
git commit -m "feat(backtest): add CSVBarLoader"
```

---

## Task 9: Strategy warmup_bars Property

**Files:**
- Modify: `backend/src/strategies/base.py`
- Modify: `backend/src/strategies/examples/momentum.py`
- Modify: `backend/tests/test_momentum_strategy.py`

**Step 1: Write failing test**

```python
# backend/tests/test_momentum_strategy.py (add to file)

class TestWarmupBars:
    def test_warmup_bars_equals_lookback_period(self):
        strategy = MomentumStrategy(
            name="test",
            symbols=["AAPL"],
            lookback_period=25,
        )
        assert strategy.warmup_bars == 25

    def test_default_warmup_bars(self):
        strategy = MomentumStrategy(
            name="test",
            symbols=["AAPL"],
        )
        assert strategy.warmup_bars == 20  # Default lookback
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/test_momentum_strategy.py::TestWarmupBars -v
```
Expected: FAIL (no warmup_bars property)

**Step 3: Write minimal implementation**

```python
# backend/src/strategies/base.py (add property to Strategy class)

class Strategy(ABC):
    # ... existing code ...

    @property
    def warmup_bars(self) -> int:
        """Number of historical bars needed before generating valid signals.

        Override this in subclasses based on indicator requirements.
        Example: A 20-period moving average needs warmup_bars = 20.

        Returns:
            Number of bars. Default is 0 (no warm-up needed).
        """
        return 0


# backend/src/strategies/examples/momentum.py (add property)

class MomentumStrategy(Strategy):
    # ... existing __init__ and methods ...

    @property
    def warmup_bars(self) -> int:
        """Momentum needs lookback_period bars to calculate."""
        return self.lookback_period
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/test_momentum_strategy.py::TestWarmupBars -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/strategies/base.py backend/src/strategies/examples/momentum.py backend/tests/test_momentum_strategy.py
git commit -m "feat(strategies): add warmup_bars property"
```

---

## Task 10: BacktestEngine Core Loop

**Files:**
- Create: `backend/src/backtest/engine.py`
- Create: `backend/tests/backtest/test_engine.py`

**Step 1: Write failing tests**

```python
# backend/tests/backtest/test_engine.py
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig, Bar


class TestBacktestEngine:
    @pytest.fixture
    def sample_csv_path(self) -> Path:
        return Path(__file__).parent / "fixtures" / "sample_bars.csv"

    @pytest.fixture
    def config(self) -> BacktestConfig:
        return BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={"lookback_period": 2, "threshold": 0.01, "position_size": 10},
            symbol="AAPL",
            start_date=date(2025, 1, 6),  # After 2 bars for warmup
            end_date=date(2025, 1, 8),
            initial_capital=Decimal("100000"),
            slippage_bps=0,
            commission_per_share=Decimal("0"),
        )

    @pytest.mark.asyncio
    async def test_run_returns_result(self, sample_csv_path, config):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        engine = BacktestEngine(bar_loader=loader)

        result = await engine.run(config)

        assert result.config == config
        assert result.final_equity > 0
        assert result.warm_up_required_bars == 2
        assert result.warm_up_bars_used >= 2

    @pytest.mark.asyncio
    async def test_warmup_phase_does_not_trade(self, sample_csv_path, config):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        engine = BacktestEngine(bar_loader=loader)

        result = await engine.run(config)

        # Trades should only occur after start_date
        for trade in result.trades:
            assert trade.timestamp.date() >= config.start_date

    @pytest.mark.asyncio
    async def test_insufficient_warmup_raises_error(self, sample_csv_path):
        config = BacktestConfig(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            strategy_params={"lookback_period": 100},  # Need 100 bars, only have 5
            symbol="AAPL",
            start_date=date(2025, 1, 6),
            end_date=date(2025, 1, 8),
            initial_capital=Decimal("100000"),
        )
        loader = CSVBarLoader(csv_path=sample_csv_path)
        engine = BacktestEngine(bar_loader=loader)

        with pytest.raises(ValueError, match="Insufficient"):
            await engine.run(config)

    @pytest.mark.asyncio
    async def test_equity_curve_starts_at_initial_capital(self, sample_csv_path, config):
        loader = CSVBarLoader(csv_path=sample_csv_path)
        engine = BacktestEngine(bar_loader=loader)

        result = await engine.run(config)

        assert result.equity_curve[0][1] == config.initial_capital

    @pytest.mark.asyncio
    async def test_no_lookahead_bias(self, sample_csv_path, config):
        """Verify signals use bar close, fills use next bar open."""
        loader = CSVBarLoader(csv_path=sample_csv_path)
        engine = BacktestEngine(bar_loader=loader)

        result = await engine.run(config)

        for trade in result.trades:
            # Trade timestamp should be after signal timestamp
            assert trade.timestamp > trade.signal_bar_timestamp
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/backtest/test_engine.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/backtest/engine.py
"""Backtest engine for running strategies against historical data."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from importlib import import_module
from typing import Any

from src.backtest.bar_loader import BarLoader
from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.metrics import MetricsCalculator
from src.backtest.models import BacktestConfig, BacktestResult, Bar, Trade
from src.backtest.portfolio import BacktestPortfolio
from src.strategies.base import MarketData, Strategy
from src.strategies.signals import Signal


class BacktestEngine:
    """Orchestrates backtest execution."""

    # Allowlist for strategy class imports (security)
    ALLOWED_STRATEGY_PREFIX = "src.strategies."

    def __init__(self, bar_loader: BarLoader) -> None:
        self._bar_loader = bar_loader

    async def run(self, config: BacktestConfig) -> BacktestResult:
        """Execute a complete backtest.

        Event order (no lookahead):
        For bar[i]:
          1. Strategy receives MarketData (price = bar[i].close)
          2. Strategy emits Signal (timestamp = bar[i].timestamp)
          3. Signal executes on bar[i+1].open (if exists)
        """
        started_at = datetime.now(tz=timezone.utc)

        # 1. Instantiate strategy
        strategy = self._create_strategy(config)
        warmup_required = strategy.warmup_bars

        # 2. Load bars (extra buffer for warmup)
        warmup_buffer_days = warmup_required * 3  # Natural days buffer
        data_start = config.start_date - timedelta(days=warmup_buffer_days)
        all_bars = await self._bar_loader.load(
            symbol=config.symbol,
            start_date=data_start,
            end_date=config.end_date,
        )

        # 3. Find warmup split point
        backtest_bars = [b for b in all_bars if b.timestamp.date() >= config.start_date]
        warmup_bars = [b for b in all_bars if b.timestamp.date() < config.start_date]

        if len(warmup_bars) < warmup_required:
            raise ValueError(
                f"Insufficient warmup data: need {warmup_required} bars, "
                f"got {len(warmup_bars)}. Load more historical data."
            )

        # Take only required warmup bars (last N before start_date)
        warmup_bars = warmup_bars[-warmup_required:] if warmup_required > 0 else []
        bars_to_process = warmup_bars + backtest_bars

        # 4. Initialize components
        portfolio = BacktestPortfolio(config.initial_capital)
        fill_engine = SimulatedFillEngine(
            slippage_bps=config.slippage_bps,
            commission_per_share=config.commission_per_share,
        )

        # 5. Run event loop
        trades: list[Trade] = []
        equity_curve: list[tuple[datetime, Decimal]] = []
        pending_signal: Signal | None = None
        first_signal_bar: datetime | None = None
        entry_prices: dict[str, Decimal] = {}

        for i, bar in enumerate(bars_to_process):
            is_backtest_phase = bar.timestamp.date() >= config.start_date

            # Execute pending signal at this bar's open (if in backtest phase)
            if pending_signal is not None and is_backtest_phase:
                can_execute = (
                    (pending_signal.action == "buy" and
                     portfolio.can_buy(bar.open, pending_signal.quantity,
                                       config.commission_per_share * pending_signal.quantity))
                    or
                    (pending_signal.action == "sell" and
                     portfolio.can_sell(pending_signal.quantity))
                )

                if can_execute:
                    trade = fill_engine.execute(pending_signal, bar)
                    portfolio.apply_trade(trade)
                    trades.append(trade)

                    # Track entry price for win rate calculation
                    if trade.side == "buy":
                        entry_prices[trade.symbol] = trade.fill_price

                pending_signal = None

            # Convert bar to MarketData (using close price)
            market_data = self._bar_to_market_data(bar)

            # Create mock context for strategy
            context = self._create_backtest_context(strategy, portfolio, bar)

            # Strategy processes bar
            signals = await strategy.on_market_data(market_data, context)

            # Capture signal for next bar execution
            if signals:
                pending_signal = signals[0]
                if first_signal_bar is None:
                    first_signal_bar = bar.timestamp

            # Record equity at bar close (only in backtest phase)
            if is_backtest_phase:
                equity = portfolio.equity(bar.close)
                equity_curve.append((bar.timestamp, equity))

        # 6. Compute metrics
        metrics = MetricsCalculator.compute(
            equity_curve=equity_curve,
            trades=trades,
            initial_capital=config.initial_capital,
            entry_prices=entry_prices,
        )

        completed_at = datetime.now(tz=timezone.utc)

        return BacktestResult(
            config=config,
            equity_curve=equity_curve,
            trades=trades,
            final_equity=portfolio.equity(bars_to_process[-1].close) if bars_to_process else config.initial_capital,
            final_cash=portfolio.cash,
            final_position_qty=portfolio.position_qty,
            total_return=metrics["total_return"],
            annualized_return=metrics["annualized_return"],
            sharpe_ratio=metrics["sharpe_ratio"],
            max_drawdown=metrics["max_drawdown"],
            win_rate=metrics["win_rate"],
            total_trades=metrics["total_trades"],
            avg_trade_pnl=metrics["avg_trade_pnl"],
            warm_up_required_bars=warmup_required,
            warm_up_bars_used=len(warmup_bars),
            first_signal_bar=first_signal_bar,
            started_at=started_at,
            completed_at=completed_at,
        )

    def _create_strategy(self, config: BacktestConfig) -> Strategy:
        """Dynamically instantiate strategy from class path."""
        if not config.strategy_class.startswith(self.ALLOWED_STRATEGY_PREFIX):
            raise ValueError(
                f"Strategy class must start with '{self.ALLOWED_STRATEGY_PREFIX}'. "
                f"Got: {config.strategy_class}"
            )

        module_path, class_name = config.strategy_class.rsplit(".", 1)
        module = import_module(module_path)
        strategy_cls = getattr(module, class_name)

        return strategy_cls(
            name="backtest",
            symbols=[config.symbol],
            **config.strategy_params,
        )

    def _bar_to_market_data(self, bar: Bar) -> MarketData:
        """Convert Bar to MarketData using close as current price."""
        return MarketData(
            symbol=bar.symbol,
            price=bar.close,
            bid=bar.close,  # Simplified: bid/ask = close
            ask=bar.close,
            volume=bar.volume,
            timestamp=bar.timestamp,
        )

    def _create_backtest_context(
        self,
        strategy: Strategy,
        portfolio: BacktestPortfolio,
        bar: Bar,
    ) -> Any:
        """Create a minimal context for backtest."""
        # Create a mock context that provides position info
        from unittest.mock import AsyncMock, MagicMock

        context = MagicMock()
        context.strategy_id = strategy.name

        # Mock get_position to return current holdings
        async def get_position(symbol: str):
            if symbol == bar.symbol and portfolio.position_qty > 0:
                pos = MagicMock()
                pos.quantity = portfolio.position_qty
                pos.avg_cost = portfolio.position_avg_cost
                return pos
            return None

        context.get_position = get_position
        context.get_quote = MagicMock(return_value=None)

        return context
```

**Step 4: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/backtest/test_engine.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/backtest/engine.py backend/tests/backtest/test_engine.py
git commit -m "feat(backtest): add BacktestEngine core loop"
```

---

## Task 11: Backtest API Endpoint

**Files:**
- Create: `backend/src/api/backtest.py`
- Create: `backend/tests/api/test_backtest.py`

**Step 1: Write failing tests**

```python
# backend/tests/api/test_backtest.py
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


class TestBacktestEndpoint:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def sample_csv_path(self) -> Path:
        return Path(__file__).parent.parent / "backtest" / "fixtures" / "sample_bars.csv"

    def test_run_backtest_success(self, client, sample_csv_path):
        with patch("src.api.backtest.get_bar_loader") as mock_loader:
            from src.backtest.bar_loader import CSVBarLoader
            mock_loader.return_value = CSVBarLoader(sample_csv_path)

            response = client.post(
                "/api/backtest",
                json={
                    "strategy_class": "src.strategies.examples.momentum.MomentumStrategy",
                    "strategy_params": {"lookback_period": 2, "threshold": 0.01, "position_size": 10},
                    "symbol": "AAPL",
                    "start_date": "2025-01-06",
                    "end_date": "2025-01-08",
                    "initial_capital": "100000",
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "completed"
            assert "result" in data
            assert data["result"]["final_equity"] is not None

    def test_run_backtest_invalid_strategy(self, client):
        response = client.post(
            "/api/backtest",
            json={
                "strategy_class": "malicious.module.Strategy",  # Not in allowlist
                "strategy_params": {},
                "symbol": "AAPL",
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
                "initial_capital": "100000",
            },
        )

        assert response.status_code == 400
        assert "must start with" in response.json()["detail"]

    def test_run_backtest_insufficient_data(self, client, sample_csv_path):
        with patch("src.api.backtest.get_bar_loader") as mock_loader:
            from src.backtest.bar_loader import CSVBarLoader
            mock_loader.return_value = CSVBarLoader(sample_csv_path)

            response = client.post(
                "/api/backtest",
                json={
                    "strategy_class": "src.strategies.examples.momentum.MomentumStrategy",
                    "strategy_params": {"lookback_period": 100},  # Need 100 bars
                    "symbol": "AAPL",
                    "start_date": "2025-01-06",
                    "end_date": "2025-01-08",
                    "initial_capital": "100000",
                },
            )

            assert response.status_code == 400
            assert "Insufficient" in response.json()["detail"]
```

**Step 2: Run test to verify it fails**

```bash
cd backend && python -m pytest tests/api/test_backtest.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# backend/src/api/backtest.py
"""Backtest API endpoints."""
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.backtest.bar_loader import CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.models import BacktestConfig


router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    strategy_class: str
    strategy_params: dict
    symbol: str
    start_date: date
    end_date: date
    initial_capital: Decimal = Decimal("100000")
    slippage_bps: int = 5
    commission_per_share: Decimal = Decimal("0.005")


class BacktestResultSchema(BaseModel):
    final_equity: str
    final_cash: str
    final_position_qty: int
    total_return: str
    annualized_return: str
    sharpe_ratio: str
    max_drawdown: str
    win_rate: str
    total_trades: int
    avg_trade_pnl: str
    warm_up_required_bars: int
    warm_up_bars_used: int

    class Config:
        from_attributes = True


class BacktestResponse(BaseModel):
    backtest_id: str
    status: str
    result: BacktestResultSchema | None = None
    error: str | None = None


def get_bar_loader():
    """Get the bar loader instance. Override in tests."""
    # Default: look for CSV in data directory
    csv_path = Path(__file__).parent.parent.parent / "data" / "bars.csv"
    return CSVBarLoader(csv_path)


@router.post("", response_model=BacktestResponse)
async def run_backtest(request: BacktestRequest) -> BacktestResponse:
    """Run a backtest with the given configuration."""
    from uuid import uuid4

    backtest_id = str(uuid4())

    config = BacktestConfig(
        strategy_class=request.strategy_class,
        strategy_params=request.strategy_params,
        symbol=request.symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        initial_capital=request.initial_capital,
        slippage_bps=request.slippage_bps,
        commission_per_share=request.commission_per_share,
    )

    try:
        bar_loader = get_bar_loader()
        engine = BacktestEngine(bar_loader=bar_loader)
        result = await engine.run(config)

        return BacktestResponse(
            backtest_id=backtest_id,
            status="completed",
            result=BacktestResultSchema(
                final_equity=str(result.final_equity),
                final_cash=str(result.final_cash),
                final_position_qty=result.final_position_qty,
                total_return=str(result.total_return),
                annualized_return=str(result.annualized_return),
                sharpe_ratio=str(result.sharpe_ratio),
                max_drawdown=str(result.max_drawdown),
                win_rate=str(result.win_rate),
                total_trades=result.total_trades,
                avg_trade_pnl=str(result.avg_trade_pnl),
                warm_up_required_bars=result.warm_up_required_bars,
                warm_up_bars_used=result.warm_up_bars_used,
            ),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        return BacktestResponse(
            backtest_id=backtest_id,
            status="failed",
            error=str(e),
        )
```

**Step 4: Register router in main.py**

```python
# backend/src/main.py (add import and router)
from src.api.backtest import router as backtest_router

# Add with other routers
app.include_router(backtest_router)
```

**Step 5: Run test to verify it passes**

```bash
cd backend && python -m pytest tests/api/test_backtest.py -v
```
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/backtest.py backend/tests/api/test_backtest.py backend/src/main.py
git commit -m "feat(api): add backtest endpoint"
```

---

## Task 12: Frontend Types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add TypeScript types**

```typescript
// frontend/src/types/index.ts (add to file)

// Backtest types
export interface BacktestRequest {
  strategy_class: string;
  strategy_params: Record<string, unknown>;
  symbol: string;
  start_date: string;  // YYYY-MM-DD
  end_date: string;    // YYYY-MM-DD
  initial_capital: string;
  slippage_bps?: number;
  commission_per_share?: string;
}

export interface BacktestResult {
  final_equity: string;
  final_cash: string;
  final_position_qty: number;
  total_return: string;
  annualized_return: string;
  sharpe_ratio: string;
  max_drawdown: string;
  win_rate: string;
  total_trades: number;
  avg_trade_pnl: string;
  warm_up_required_bars: number;
  warm_up_bars_used: number;
}

export interface BacktestResponse {
  backtest_id: string;
  status: 'completed' | 'failed';
  result: BacktestResult | null;
  error: string | null;
}

export interface EquityCurvePoint {
  timestamp: string;
  equity: number;
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): add backtest types"
```

---

## Task 13: useBacktest Hook

**Files:**
- Create: `frontend/src/api/backtest.ts`
- Create: `frontend/src/hooks/useBacktest.ts`
- Create: `frontend/src/hooks/useBacktest.test.tsx`

**Step 1: Write API function and hook**

```typescript
// frontend/src/api/backtest.ts
import { apiClient } from './client';
import type { BacktestRequest, BacktestResponse } from '../types';

export async function runBacktest(request: BacktestRequest): Promise<BacktestResponse> {
  const response = await apiClient.post<BacktestResponse>('/backtest', request);
  return response.data;
}
```

```typescript
// frontend/src/hooks/useBacktest.ts
import { useMutation } from '@tanstack/react-query';
import { runBacktest } from '../api/backtest';
import type { BacktestRequest, BacktestResponse } from '../types';

export function useBacktest() {
  return useMutation<BacktestResponse, Error, BacktestRequest>({
    mutationFn: runBacktest,
  });
}
```

**Step 2: Write test**

```typescript
// frontend/src/hooks/useBacktest.test.tsx
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useBacktest } from './useBacktest';
import * as backtestApi from '../api/backtest';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useBacktest', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('runs backtest and returns result', async () => {
    const mockResponse = {
      backtest_id: 'test-123',
      status: 'completed' as const,
      result: {
        final_equity: '110000',
        final_cash: '110000',
        final_position_qty: 0,
        total_return: '0.1',
        annualized_return: '0.1',
        sharpe_ratio: '1.5',
        max_drawdown: '0.05',
        win_rate: '0.6',
        total_trades: 5,
        avg_trade_pnl: '2000',
        warm_up_required_bars: 20,
        warm_up_bars_used: 20,
      },
      error: null,
    };

    vi.spyOn(backtestApi, 'runBacktest').mockResolvedValue(mockResponse);

    const { result } = renderHook(() => useBacktest(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      strategy_class: 'src.strategies.examples.momentum.MomentumStrategy',
      strategy_params: { lookback_period: 20 },
      symbol: 'AAPL',
      start_date: '2025-01-01',
      end_date: '2025-12-31',
      initial_capital: '100000',
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data?.status).toBe('completed');
    expect(result.current.data?.result?.total_return).toBe('0.1');
  });

  it('handles error', async () => {
    vi.spyOn(backtestApi, 'runBacktest').mockRejectedValue(new Error('API Error'));

    const { result } = renderHook(() => useBacktest(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      strategy_class: 'invalid',
      strategy_params: {},
      symbol: 'AAPL',
      start_date: '2025-01-01',
      end_date: '2025-12-31',
      initial_capital: '100000',
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
```

**Step 3: Run tests**

```bash
cd frontend && npm test -- --run useBacktest
```
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/api/backtest.ts frontend/src/hooks/useBacktest.ts frontend/src/hooks/useBacktest.test.tsx
git commit -m "feat(frontend): add useBacktest hook"
```

---

## Task 14: BacktestForm Component

**Files:**
- Create: `frontend/src/components/BacktestForm.tsx`
- Create: `frontend/src/components/BacktestForm.test.tsx`

**Step 1: Write component**

```typescript
// frontend/src/components/BacktestForm.tsx
import { useState } from 'react';
import type { BacktestRequest } from '../types';

interface BacktestFormProps {
  onSubmit: (request: BacktestRequest) => void;
  isLoading: boolean;
}

export function BacktestForm({ onSubmit, isLoading }: BacktestFormProps) {
  const [formData, setFormData] = useState({
    strategy_class: 'src.strategies.examples.momentum.MomentumStrategy',
    symbol: 'AAPL',
    start_date: '2025-01-01',
    end_date: '2025-12-31',
    initial_capital: '100000',
    lookback_period: '20',
    threshold: '0.02',
    position_size: '100',
    slippage_bps: '5',
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      strategy_class: formData.strategy_class,
      strategy_params: {
        lookback_period: parseInt(formData.lookback_period),
        threshold: parseFloat(formData.threshold),
        position_size: parseInt(formData.position_size),
      },
      symbol: formData.symbol,
      start_date: formData.start_date,
      end_date: formData.end_date,
      initial_capital: formData.initial_capital,
      slippage_bps: parseInt(formData.slippage_bps),
    });
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4 p-4 bg-white rounded-lg shadow">
      <h2 className="text-xl font-semibold">Run Backtest</h2>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">Symbol</label>
          <input
            type="text"
            name="symbol"
            value={formData.symbol}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Initial Capital</label>
          <input
            type="text"
            name="initial_capital"
            value={formData.initial_capital}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Start Date</label>
          <input
            type="date"
            name="start_date"
            value={formData.start_date}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">End Date</label>
          <input
            type="date"
            name="end_date"
            value={formData.end_date}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Lookback Period</label>
          <input
            type="number"
            name="lookback_period"
            value={formData.lookback_period}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Threshold</label>
          <input
            type="text"
            name="threshold"
            value={formData.threshold}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Position Size</label>
          <input
            type="number"
            name="position_size"
            value={formData.position_size}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">Slippage (bps)</label>
          <input
            type="number"
            name="slippage_bps"
            value={formData.slippage_bps}
            onChange={handleChange}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={isLoading}
        className="w-full py-2 px-4 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400"
      >
        {isLoading ? 'Running...' : 'Run Backtest'}
      </button>
    </form>
  );
}
```

**Step 2: Write test**

```typescript
// frontend/src/components/BacktestForm.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { BacktestForm } from './BacktestForm';

describe('BacktestForm', () => {
  it('renders form fields', () => {
    render(<BacktestForm onSubmit={() => {}} isLoading={false} />);

    expect(screen.getByLabelText(/symbol/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/initial capital/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/start date/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/end date/i)).toBeInTheDocument();
  });

  it('calls onSubmit with form data', () => {
    const onSubmit = vi.fn();
    render(<BacktestForm onSubmit={onSubmit} isLoading={false} />);

    fireEvent.click(screen.getByRole('button', { name: /run backtest/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        symbol: 'AAPL',
        initial_capital: '100000',
      })
    );
  });

  it('shows loading state', () => {
    render(<BacktestForm onSubmit={() => {}} isLoading={true} />);

    expect(screen.getByRole('button')).toHaveTextContent('Running...');
    expect(screen.getByRole('button')).toBeDisabled();
  });
});
```

**Step 3: Run tests**

```bash
cd frontend && npm test -- --run BacktestForm
```
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/src/components/BacktestForm.tsx frontend/src/components/BacktestForm.test.tsx
git commit -m "feat(frontend): add BacktestForm component"
```

---

## Task 15: BacktestResults and EquityChart Components

**Files:**
- Create: `frontend/src/components/BacktestResults.tsx`
- Create: `frontend/src/components/EquityChart.tsx`
- Create: `frontend/src/components/BacktestResults.test.tsx`

**Step 1: Write EquityChart component**

```typescript
// frontend/src/components/EquityChart.tsx
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import type { EquityCurvePoint } from '../types';

interface EquityChartProps {
  data: EquityCurvePoint[];
}

export function EquityChart({ data }: EquityChartProps) {
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey="timestamp"
            tick={{ fontSize: 12 }}
            tickFormatter={(value) => new Date(value).toLocaleDateString()}
          />
          <YAxis
            tick={{ fontSize: 12 }}
            tickFormatter={(value) => `$${value.toLocaleString()}`}
          />
          <Tooltip
            formatter={(value: number) => [`$${value.toLocaleString()}`, 'Equity']}
            labelFormatter={(label) => new Date(label).toLocaleDateString()}
          />
          <Line
            type="monotone"
            dataKey="equity"
            stroke="#2563eb"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

**Step 2: Write BacktestResults component**

```typescript
// frontend/src/components/BacktestResults.tsx
import type { BacktestResult, EquityCurvePoint } from '../types';
import { EquityChart } from './EquityChart';

interface BacktestResultsProps {
  result: BacktestResult;
  equityCurve?: EquityCurvePoint[];
}

export function BacktestResults({ result, equityCurve }: BacktestResultsProps) {
  const formatPercent = (value: string) => {
    const num = parseFloat(value) * 100;
    return `${num >= 0 ? '+' : ''}${num.toFixed(2)}%`;
  };

  const formatCurrency = (value: string) => {
    const num = parseFloat(value);
    return `$${num.toLocaleString()}`;
  };

  const metrics = [
    { label: 'Final Equity', value: formatCurrency(result.final_equity) },
    { label: 'Total Return', value: formatPercent(result.total_return) },
    { label: 'Annualized Return', value: formatPercent(result.annualized_return) },
    { label: 'Sharpe Ratio', value: parseFloat(result.sharpe_ratio).toFixed(2) },
    { label: 'Max Drawdown', value: formatPercent(result.max_drawdown) },
    { label: 'Win Rate', value: formatPercent(result.win_rate) },
    { label: 'Total Trades', value: result.total_trades.toString() },
    { label: 'Avg Trade P&L', value: formatCurrency(result.avg_trade_pnl) },
  ];

  return (
    <div className="p-4 bg-white rounded-lg shadow space-y-4">
      <h2 className="text-xl font-semibold">Backtest Results</h2>

      {equityCurve && equityCurve.length > 0 && (
        <div>
          <h3 className="text-lg font-medium mb-2">Equity Curve</h3>
          <EquityChart data={equityCurve} />
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {metrics.map(({ label, value }) => (
          <div key={label} className="p-3 bg-gray-50 rounded">
            <div className="text-sm text-gray-500">{label}</div>
            <div className="text-lg font-semibold">{value}</div>
          </div>
        ))}
      </div>

      <div className="text-sm text-gray-500">
        Warm-up: {result.warm_up_bars_used} / {result.warm_up_required_bars} bars
      </div>
    </div>
  );
}
```

**Step 3: Write test**

```typescript
// frontend/src/components/BacktestResults.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { BacktestResults } from './BacktestResults';

const mockResult = {
  final_equity: '110000',
  final_cash: '110000',
  final_position_qty: 0,
  total_return: '0.1',
  annualized_return: '0.1',
  sharpe_ratio: '1.5',
  max_drawdown: '0.05',
  win_rate: '0.6',
  total_trades: 10,
  avg_trade_pnl: '1000',
  warm_up_required_bars: 20,
  warm_up_bars_used: 20,
};

describe('BacktestResults', () => {
  it('displays key metrics', () => {
    render(<BacktestResults result={mockResult} />);

    expect(screen.getByText('$110,000')).toBeInTheDocument();
    expect(screen.getByText('+10.00%')).toBeInTheDocument();
    expect(screen.getByText('1.50')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
  });

  it('shows warm-up info', () => {
    render(<BacktestResults result={mockResult} />);

    expect(screen.getByText(/20 \/ 20 bars/)).toBeInTheDocument();
  });
});
```

**Step 4: Install recharts**

```bash
cd frontend && npm install recharts
```

**Step 5: Run tests**

```bash
cd frontend && npm test -- --run BacktestResults
```
Expected: PASS

**Step 6: Commit**

```bash
git add frontend/src/components/EquityChart.tsx frontend/src/components/BacktestResults.tsx frontend/src/components/BacktestResults.test.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): add BacktestResults and EquityChart components"
```

---

## Task 16: BacktestPage

**Files:**
- Create: `frontend/src/pages/BacktestPage.tsx`
- Create: `frontend/src/pages/BacktestPage.test.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Write page component**

```typescript
// frontend/src/pages/BacktestPage.tsx
import { BacktestForm } from '../components/BacktestForm';
import { BacktestResults } from '../components/BacktestResults';
import { useBacktest } from '../hooks/useBacktest';

export function BacktestPage() {
  const { mutate, data, isPending, isError, error } = useBacktest();

  return (
    <div className="container mx-auto p-4 space-y-6">
      <h1 className="text-2xl font-bold">Strategy Backtester</h1>

      <BacktestForm onSubmit={mutate} isLoading={isPending} />

      {isError && (
        <div className="p-4 bg-red-100 text-red-700 rounded">
          Error: {error.message}
        </div>
      )}

      {data?.status === 'failed' && (
        <div className="p-4 bg-red-100 text-red-700 rounded">
          Backtest failed: {data.error}
        </div>
      )}

      {data?.status === 'completed' && data.result && (
        <BacktestResults result={data.result} />
      )}
    </div>
  );
}
```

**Step 2: Add route to App.tsx**

```typescript
// frontend/src/App.tsx (add import and route)
import { BacktestPage } from './pages/BacktestPage';

// Add route alongside existing routes
<Route path="/backtest" element={<BacktestPage />} />

// Add nav link
<Link to="/backtest" className="...">Backtest</Link>
```

**Step 3: Write test**

```typescript
// frontend/src/pages/BacktestPage.test.tsx
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect } from 'vitest';
import { BacktestPage } from './BacktestPage';

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('BacktestPage', () => {
  it('renders form', () => {
    render(<BacktestPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Strategy Backtester')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /run backtest/i })).toBeInTheDocument();
  });
});
```

**Step 4: Run tests**

```bash
cd frontend && npm test -- --run BacktestPage
```
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/pages/BacktestPage.tsx frontend/src/pages/BacktestPage.test.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add BacktestPage with routing"
```

---

## Task 17: Update Package Exports and Final Integration

**Files:**
- Modify: `backend/src/backtest/__init__.py`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Update backend exports**

```python
# backend/src/backtest/__init__.py
"""Backtest engine package."""
from src.backtest.bar_loader import BarLoader, CSVBarLoader
from src.backtest.engine import BacktestEngine
from src.backtest.fill_engine import SimulatedFillEngine
from src.backtest.metrics import MetricsCalculator
from src.backtest.models import BacktestConfig, BacktestResult, Bar, Trade
from src.backtest.portfolio import BacktestPortfolio

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestPortfolio",
    "BacktestResult",
    "Bar",
    "BarLoader",
    "CSVBarLoader",
    "MetricsCalculator",
    "SimulatedFillEngine",
    "Trade",
]
```

**Step 2: Update frontend exports**

```typescript
// frontend/src/hooks/index.ts (add export)
export { useBacktest } from './useBacktest';
```

**Step 3: Run all tests**

```bash
cd backend && python -m pytest tests/backtest/ -v
cd frontend && npm test -- --run
```
Expected: All tests pass

**Step 4: Commit**

```bash
git add backend/src/backtest/__init__.py frontend/src/hooks/index.ts
git commit -m "feat(backtest): finalize package exports"
```

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Bar model | 3 |
| 2 | Trade model | 2 |
| 3 | BacktestConfig model | 2 |
| 4 | BacktestResult model | 1 |
| 5 | BacktestPortfolio | 10 |
| 6 | SimulatedFillEngine | 4 |
| 7 | MetricsCalculator | 8 |
| 8 | CSVBarLoader | 5 |
| 9 | Strategy warmup_bars | 2 |
| 10 | BacktestEngine | 5 |
| 11 | Backtest API | 3 |
| 12 | Frontend types | - |
| 13 | useBacktest hook | 2 |
| 14 | BacktestForm | 3 |
| 15 | BacktestResults + EquityChart | 2 |
| 16 | BacktestPage | 1 |
| 17 | Package exports | - |

**Total: 17 tasks, ~53 tests**
