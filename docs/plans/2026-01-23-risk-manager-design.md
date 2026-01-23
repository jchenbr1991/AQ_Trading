# Risk Manager Design

## Overview

The Risk Manager validates trading signals before they reach the Order Manager. It enforces position limits, portfolio limits, loss limits, and provides emergency controls (kill switch, strategy pause).

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Risk checks | Core only (no Greeks) | Greeks deferred to Phase 3 with options support |
| On failure | Reject and log | Simple, predictable behavior |
| Configuration | YAML file | Easy to edit, version controlled |
| Kill switch | In-memory flag | Fast, no network latency for emergency stops |
| Check order | Sequential | Fail fast on first rejection |

## Architecture

### Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Strategy Engine │────▶│  Risk Manager   │────▶│  Order Manager  │
│                 │     │                 │     │                 │
│  generates      │     │  evaluates      │     │  executes       │
│  Signal         │     │  RiskResult     │     │  approved       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### File Structure

```
backend/src/risk/
├── __init__.py
├── models.py          # RiskResult, RiskConfig
├── manager.py         # RiskManager class

backend/tests/risk/
├── __init__.py
├── test_risk_manager.py
├── test_position_limits.py
├── test_portfolio_limits.py
├── test_loss_limits.py
└── test_kill_switch.py

config/
└── risk.yaml
```

## Core Models

### RiskResult

```python
from dataclasses import dataclass, field

@dataclass
class RiskResult:
    approved: bool
    signal: Signal
    rejection_reason: str | None = None
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)
```

### RiskConfig

```python
@dataclass
class RiskConfig:
    account_id: str

    # Position limits
    max_position_value: Decimal = Decimal("10000")
    max_position_pct: Decimal = Decimal("5")
    max_quantity_per_order: int = 500

    # Portfolio limits
    max_positions: int = 20
    max_exposure_pct: Decimal = Decimal("80")

    # Loss limits
    daily_loss_limit: Decimal = Decimal("1000")
    max_drawdown_pct: Decimal = Decimal("10")

    # Symbol restrictions
    blocked_symbols: list[str] = field(default_factory=list)
    allowed_symbols: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "RiskConfig":
        """Load config from YAML file."""
```

## RiskManager Interface

```python
class RiskManager:
    def __init__(self, config: RiskConfig, portfolio: PortfolioManager):
        self._config = config
        self._portfolio = portfolio
        self._killed = False
        self._kill_reason: str | None = None
        self._paused_strategies: set[str] = set()
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_equity: Decimal = Decimal("0")

    async def evaluate(self, signal: Signal) -> RiskResult:
        """Run all risk checks on a signal."""

    # Emergency controls
    def activate_kill_switch(self, reason: str) -> None:
    def deactivate_kill_switch(self) -> None:
    def is_killed(self) -> bool:

    # Strategy controls
    def pause_strategy(self, strategy_id: str) -> None:
    def resume_strategy(self, strategy_id: str) -> None:
    def is_strategy_paused(self, strategy_id: str) -> bool:

    # Daily reset
    def reset_daily_stats(self) -> None:
    def update_daily_pnl(self, pnl_change: Decimal) -> None:
```

## Risk Checks

### 1. Symbol Restrictions

```python
def _check_symbol_allowed(self, signal: Signal) -> bool:
    if signal.symbol in self._config.blocked_symbols:
        return False

    if self._config.allowed_symbols:
        return signal.symbol in self._config.allowed_symbols

    return True
```

### 2. Position Limits

```python
async def _check_position_limits(self, signal: Signal) -> bool:
    if signal.action == "sell":
        return True  # Always allow sells

    # Check max quantity per order
    if signal.quantity > self._config.max_quantity_per_order:
        return False

    # Check max position value
    price = await self._get_current_price(signal.symbol)
    position_value = signal.quantity * price

    if position_value > self._config.max_position_value:
        return False

    # Check max position as % of portfolio
    account = await self._portfolio.get_account(self._config.account_id)
    position_pct = (position_value / account.total_equity) * 100

    if position_pct > self._config.max_position_pct:
        return False

    return True
```

### 3. Portfolio Limits

```python
async def _check_portfolio_limits(self, signal: Signal) -> bool:
    account = await self._portfolio.get_account(self._config.account_id)
    if not account:
        return False

    positions = await self._portfolio.get_positions(self._config.account_id)

    # Check max positions (only for new positions)
    if signal.action == "buy":
        existing = await self._portfolio.get_position(
            self._config.account_id, signal.symbol, signal.strategy_id
        )
        if not existing and len(positions) >= self._config.max_positions:
            return False

    # Check max exposure
    total_exposure = sum(p.market_value for p in positions)
    price = await self._get_current_price(signal.symbol)
    new_exposure = signal.quantity * price if signal.action == "buy" else 0
    exposure_pct = (total_exposure + new_exposure) / account.total_equity * 100

    if exposure_pct > self._config.max_exposure_pct:
        return False

    # Check buying power
    if signal.action == "buy":
        required = signal.quantity * price
        if required > account.buying_power:
            return False

    return True
```

### 4. Loss Limits

```python
async def _check_loss_limits(self, signal: Signal) -> bool:
    # Check daily loss limit
    if self._daily_pnl < -self._config.daily_loss_limit:
        self.activate_kill_switch("Daily loss limit exceeded")
        return False

    # Check drawdown
    account = await self._portfolio.get_account(self._config.account_id)
    if account.total_equity > self._peak_equity:
        self._peak_equity = account.total_equity

    drawdown_pct = (self._peak_equity - account.total_equity) / self._peak_equity * 100
    if drawdown_pct > self._config.max_drawdown_pct:
        self.activate_kill_switch(f"Drawdown {drawdown_pct:.1f}% exceeded limit")
        return False

    return True
```

## Main Evaluation Flow

```python
async def evaluate(self, signal: Signal) -> RiskResult:
    """Run all risk checks on a signal."""
    checks_passed = []
    checks_failed = []

    # Kill switch is instant rejection
    if self._killed:
        return RiskResult(
            approved=False,
            signal=signal,
            rejection_reason=f"Kill switch active: {self._kill_reason}",
            checks_failed=["kill_switch"]
        )

    # Strategy pause check
    if signal.strategy_id in self._paused_strategies:
        return RiskResult(
            approved=False,
            signal=signal,
            rejection_reason=f"Strategy {signal.strategy_id} is paused",
            checks_failed=["strategy_paused"]
        )

    # Run all checks sequentially (fail fast)
    checks = [
        ("symbol_allowed", self._check_symbol_allowed),
        ("position_limits", self._check_position_limits),
        ("portfolio_limits", self._check_portfolio_limits),
        ("loss_limits", self._check_loss_limits),
    ]

    for check_name, check_fn in checks:
        if await check_fn(signal):
            checks_passed.append(check_name)
        else:
            checks_failed.append(check_name)

    approved = len(checks_failed) == 0

    return RiskResult(
        approved=approved,
        signal=signal,
        rejection_reason=checks_failed[0] if checks_failed else None,
        checks_passed=checks_passed,
        checks_failed=checks_failed
    )
```

## Configuration File

**`config/risk.yaml`:**

```yaml
risk:
  account_id: "ACC001"

  # Position limits
  max_position_value: 10000      # Max $ per position
  max_position_pct: 5            # Max % of portfolio per position
  max_quantity_per_order: 500    # Max shares per order

  # Portfolio limits
  max_positions: 20              # Max concurrent positions
  max_exposure_pct: 80           # Max % of equity in positions

  # Loss limits
  daily_loss_limit: 1000         # Max $ loss per day
  max_drawdown_pct: 10           # Max % drawdown from peak

  # Symbol restrictions (optional)
  blocked_symbols: []            # Never trade these
  allowed_symbols: []            # If set, only trade these
```

## Testing Strategy

Tests follow TDD approach:

1. **test_risk_config.py** - Config loading from YAML
2. **test_position_limits.py** - Max value, max %, max quantity checks
3. **test_portfolio_limits.py** - Max positions, max exposure, buying power
4. **test_loss_limits.py** - Daily loss, drawdown detection
5. **test_kill_switch.py** - Activate, deactivate, blocks all signals
6. **test_strategy_pause.py** - Pause, resume, per-strategy blocking
7. **test_risk_manager.py** - Full evaluate() flow integration
