# Risk Manager Implementation Plan

**Created:** 2026-01-23
**Design:** [Risk Manager Design](./2026-01-23-risk-manager-design.md)
**Approach:** TDD (Test-Driven Development)

## Overview

Implement the Risk Manager component that validates trading signals against position limits, portfolio limits, loss limits, and provides emergency controls.

## Tasks

### Task 1: RiskConfig and RiskResult Models

**Goal:** Create the core data models for risk management.

**Test first (`backend/tests/risk/test_models.py`):**

```python
import pytest
from decimal import Decimal
from pathlib import Path
import tempfile
import yaml

from src.risk.models import RiskConfig, RiskResult
from src.strategy.models import Signal


class TestRiskConfig:
    def test_default_values(self):
        """RiskConfig has sensible defaults."""
        config = RiskConfig(account_id="ACC001")

        assert config.account_id == "ACC001"
        assert config.max_position_value == Decimal("10000")
        assert config.max_position_pct == Decimal("5")
        assert config.max_quantity_per_order == 500
        assert config.max_positions == 20
        assert config.max_exposure_pct == Decimal("80")
        assert config.daily_loss_limit == Decimal("1000")
        assert config.max_drawdown_pct == Decimal("10")
        assert config.blocked_symbols == []
        assert config.allowed_symbols == []

    def test_from_yaml(self):
        """Load config from YAML file."""
        yaml_content = """
risk:
  account_id: "TEST001"
  max_position_value: 5000
  max_position_pct: 3
  max_quantity_per_order: 100
  max_positions: 10
  max_exposure_pct: 50
  daily_loss_limit: 500
  max_drawdown_pct: 5
  blocked_symbols:
    - BANNED
  allowed_symbols: []
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = RiskConfig.from_yaml(f.name)

        assert config.account_id == "TEST001"
        assert config.max_position_value == Decimal("5000")
        assert config.max_position_pct == Decimal("3")
        assert config.max_quantity_per_order == 100
        assert config.max_positions == 10
        assert config.blocked_symbols == ["BANNED"]

    def test_from_yaml_missing_file(self):
        """Raise error for missing YAML file."""
        with pytest.raises(FileNotFoundError):
            RiskConfig.from_yaml("/nonexistent/path.yaml")


class TestRiskResult:
    def test_approved_result(self):
        """Create approved RiskResult."""
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = RiskResult(
            approved=True,
            signal=signal,
            checks_passed=["position_limits", "portfolio_limits"]
        )

        assert result.approved is True
        assert result.rejection_reason is None
        assert len(result.checks_passed) == 2
        assert len(result.checks_failed) == 0

    def test_rejected_result(self):
        """Create rejected RiskResult."""
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = RiskResult(
            approved=False,
            signal=signal,
            rejection_reason="position_limits",
            checks_passed=["symbol_allowed"],
            checks_failed=["position_limits"]
        )

        assert result.approved is False
        assert result.rejection_reason == "position_limits"
        assert "symbol_allowed" in result.checks_passed
        assert "position_limits" in result.checks_failed
```

**Implementation (`backend/src/risk/models.py`):**

```python
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.strategy.models import Signal


@dataclass
class RiskResult:
    """Result of risk evaluation for a signal."""

    approved: bool
    signal: "Signal"
    rejection_reason: str | None = None
    checks_passed: list[str] = field(default_factory=list)
    checks_failed: list[str] = field(default_factory=list)


@dataclass
class RiskConfig:
    """Configuration for risk management."""

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
        """Load configuration from a YAML file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = yaml.safe_load(f)

        risk_data = data.get("risk", {})

        return cls(
            account_id=risk_data["account_id"],
            max_position_value=Decimal(str(risk_data.get("max_position_value", 10000))),
            max_position_pct=Decimal(str(risk_data.get("max_position_pct", 5))),
            max_quantity_per_order=risk_data.get("max_quantity_per_order", 500),
            max_positions=risk_data.get("max_positions", 20),
            max_exposure_pct=Decimal(str(risk_data.get("max_exposure_pct", 80))),
            daily_loss_limit=Decimal(str(risk_data.get("daily_loss_limit", 1000))),
            max_drawdown_pct=Decimal(str(risk_data.get("max_drawdown_pct", 10))),
            blocked_symbols=risk_data.get("blocked_symbols", []),
            allowed_symbols=risk_data.get("allowed_symbols", []),
        )
```

**Files to create:**
- `backend/src/risk/__init__.py`
- `backend/src/risk/models.py`
- `backend/tests/risk/__init__.py`
- `backend/tests/risk/test_models.py`

---

### Task 2: Kill Switch and Strategy Pause

**Goal:** Implement emergency controls that bypass all other checks.

**Test first (`backend/tests/risk/test_kill_switch.py`):**

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.risk.models import RiskConfig
from src.risk.manager import RiskManager
from src.strategy.models import Signal


@pytest.fixture
def config():
    return RiskConfig(account_id="ACC001")


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(return_value=MagicMock(
        total_equity=Decimal("100000"),
        buying_power=Decimal("50000")
    ))
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


@pytest.fixture
def risk_manager(config, mock_portfolio):
    return RiskManager(config, mock_portfolio)


class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_switch_blocks_all_signals(self, risk_manager):
        """When kill switch is active, all signals are rejected."""
        risk_manager.activate_kill_switch("Manual stop")

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await risk_manager.evaluate(signal)

        assert result.approved is False
        assert "kill_switch" in result.checks_failed
        assert "Manual stop" in result.rejection_reason

    @pytest.mark.asyncio
    async def test_deactivate_kill_switch(self, risk_manager):
        """Deactivating kill switch allows signals again."""
        risk_manager.activate_kill_switch("Test")
        risk_manager.deactivate_kill_switch()

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        # Mock price lookup
        risk_manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        result = await risk_manager.evaluate(signal)

        assert result.approved is True

    def test_is_killed_property(self, risk_manager):
        """is_killed reflects kill switch state."""
        assert risk_manager.is_killed() is False

        risk_manager.activate_kill_switch("Test")
        assert risk_manager.is_killed() is True

        risk_manager.deactivate_kill_switch()
        assert risk_manager.is_killed() is False


class TestStrategyPause:
    @pytest.mark.asyncio
    async def test_paused_strategy_signals_rejected(self, risk_manager):
        """Signals from paused strategy are rejected."""
        risk_manager.pause_strategy("momentum")

        signal = Signal(
            strategy_id="momentum",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await risk_manager.evaluate(signal)

        assert result.approved is False
        assert "strategy_paused" in result.checks_failed

    @pytest.mark.asyncio
    async def test_other_strategies_not_affected(self, risk_manager):
        """Other strategies work when one is paused."""
        risk_manager.pause_strategy("momentum")
        risk_manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="mean_reversion",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await risk_manager.evaluate(signal)

        assert result.approved is True

    @pytest.mark.asyncio
    async def test_resume_strategy(self, risk_manager):
        """Resumed strategy can trade again."""
        risk_manager.pause_strategy("momentum")
        risk_manager.resume_strategy("momentum")
        risk_manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="momentum",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await risk_manager.evaluate(signal)

        assert result.approved is True

    def test_is_strategy_paused(self, risk_manager):
        """is_strategy_paused reflects pause state."""
        assert risk_manager.is_strategy_paused("test") is False

        risk_manager.pause_strategy("test")
        assert risk_manager.is_strategy_paused("test") is True

        risk_manager.resume_strategy("test")
        assert risk_manager.is_strategy_paused("test") is False
```

**Implementation (`backend/src/risk/manager.py` - partial):**

```python
from decimal import Decimal
from typing import Protocol

from src.risk.models import RiskConfig, RiskResult
from src.strategy.models import Signal


class PortfolioProtocol(Protocol):
    """Protocol for portfolio manager dependency."""

    async def get_account(self, account_id: str): ...
    async def get_positions(self, account_id: str): ...
    async def get_position(self, account_id: str, symbol: str, strategy_id: str): ...


class RiskManager:
    """Validates trading signals against risk limits."""

    def __init__(self, config: RiskConfig, portfolio: PortfolioProtocol):
        self._config = config
        self._portfolio = portfolio
        self._killed = False
        self._kill_reason: str | None = None
        self._paused_strategies: set[str] = set()
        self._daily_pnl: Decimal = Decimal("0")
        self._peak_equity: Decimal = Decimal("0")

    # Emergency controls
    def activate_kill_switch(self, reason: str) -> None:
        """Activate kill switch to block all trading."""
        self._killed = True
        self._kill_reason = reason

    def deactivate_kill_switch(self) -> None:
        """Deactivate kill switch to resume trading."""
        self._killed = False
        self._kill_reason = None

    def is_killed(self) -> bool:
        """Check if kill switch is active."""
        return self._killed

    # Strategy controls
    def pause_strategy(self, strategy_id: str) -> None:
        """Pause a specific strategy."""
        self._paused_strategies.add(strategy_id)

    def resume_strategy(self, strategy_id: str) -> None:
        """Resume a paused strategy."""
        self._paused_strategies.discard(strategy_id)

    def is_strategy_paused(self, strategy_id: str) -> bool:
        """Check if a strategy is paused."""
        return strategy_id in self._paused_strategies

    async def evaluate(self, signal: Signal) -> RiskResult:
        """Run all risk checks on a signal."""
        # Kill switch check
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

        # Placeholder for remaining checks (implemented in later tasks)
        return RiskResult(
            approved=True,
            signal=signal,
            checks_passed=["kill_switch", "strategy_paused"]
        )

    async def _get_current_price(self, symbol: str) -> Decimal:
        """Get current price for a symbol. Placeholder for market data integration."""
        # TODO: Integrate with market data service
        return Decimal("100")
```

**Files to create/update:**
- `backend/src/risk/manager.py`
- `backend/tests/risk/test_kill_switch.py`

---

### Task 3: Symbol Restrictions

**Goal:** Implement blocked/allowed symbol lists.

**Test first (`backend/tests/risk/test_symbol_check.py`):**

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.risk.models import RiskConfig
from src.risk.manager import RiskManager
from src.strategy.models import Signal


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(return_value=MagicMock(
        total_equity=Decimal("100000"),
        buying_power=Decimal("50000")
    ))
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


class TestSymbolRestrictions:
    @pytest.mark.asyncio
    async def test_blocked_symbol_rejected(self, mock_portfolio):
        """Signals for blocked symbols are rejected."""
        config = RiskConfig(
            account_id="ACC001",
            blocked_symbols=["BANNED", "RESTRICTED"]
        )
        manager = RiskManager(config, mock_portfolio)

        signal = Signal(
            strategy_id="test",
            symbol="BANNED",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "symbol_allowed" in result.checks_failed

    @pytest.mark.asyncio
    async def test_allowed_symbol_passes(self, mock_portfolio):
        """Non-blocked symbols pass the check."""
        config = RiskConfig(
            account_id="ACC001",
            blocked_symbols=["BANNED"]
        )
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert "symbol_allowed" in result.checks_passed

    @pytest.mark.asyncio
    async def test_allowed_list_only(self, mock_portfolio):
        """When allowed_symbols set, only those symbols pass."""
        config = RiskConfig(
            account_id="ACC001",
            allowed_symbols=["AAPL", "GOOGL", "MSFT"]
        )
        manager = RiskManager(config, mock_portfolio)

        signal = Signal(
            strategy_id="test",
            symbol="TSLA",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "symbol_allowed" in result.checks_failed

    @pytest.mark.asyncio
    async def test_allowed_list_passes(self, mock_portfolio):
        """Symbols in allowed_symbols list pass."""
        config = RiskConfig(
            account_id="ACC001",
            allowed_symbols=["AAPL", "GOOGL"]
        )
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert "symbol_allowed" in result.checks_passed

    @pytest.mark.asyncio
    async def test_blocked_takes_precedence(self, mock_portfolio):
        """Blocked list takes precedence over allowed list."""
        config = RiskConfig(
            account_id="ACC001",
            blocked_symbols=["AAPL"],
            allowed_symbols=["AAPL", "GOOGL"]
        )
        manager = RiskManager(config, mock_portfolio)

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "symbol_allowed" in result.checks_failed
```

**Implementation (add to `manager.py`):**

```python
def _check_symbol_allowed(self, signal: Signal) -> bool:
    """Check if symbol is allowed to trade."""
    # Blocked list takes precedence
    if signal.symbol in self._config.blocked_symbols:
        return False

    # If allowed list is set, symbol must be in it
    if self._config.allowed_symbols:
        return signal.symbol in self._config.allowed_symbols

    return True
```

**Files to create/update:**
- `backend/tests/risk/test_symbol_check.py`
- `backend/src/risk/manager.py` (add _check_symbol_allowed)

---

### Task 4: Position Limits

**Goal:** Implement max position value, max % of portfolio, max quantity per order.

**Test first (`backend/tests/risk/test_position_limits.py`):**

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.risk.models import RiskConfig
from src.risk.manager import RiskManager
from src.strategy.models import Signal


@pytest.fixture
def config():
    return RiskConfig(
        account_id="ACC001",
        max_position_value=Decimal("10000"),
        max_position_pct=Decimal("5"),
        max_quantity_per_order=100
    )


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(return_value=MagicMock(
        total_equity=Decimal("100000"),
        buying_power=Decimal("50000")
    ))
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


class TestPositionLimits:
    @pytest.mark.asyncio
    async def test_quantity_exceeds_max(self, config, mock_portfolio):
        """Reject when quantity exceeds max_quantity_per_order."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("50"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=150  # Exceeds 100 limit
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_value_exceeds_max(self, config, mock_portfolio):
        """Reject when position value exceeds max_position_value."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("200"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=60  # 60 * 200 = 12000 > 10000 limit
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_pct_exceeds_max(self, config, mock_portfolio):
        """Reject when position % exceeds max_position_pct."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=60  # 60 * 100 = 6000 = 6% > 5% limit
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_within_all_limits(self, config, mock_portfolio):
        """Accept when within all position limits."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=40  # 40 * 100 = 4000 = 4% (all within limits)
        )
        result = await manager.evaluate(signal)

        assert "position_limits" in result.checks_passed

    @pytest.mark.asyncio
    async def test_sell_always_passes(self, config, mock_portfolio):
        """Sell orders always pass position limits."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="sell",
            quantity=1000  # Way over limits, but sell
        )
        result = await manager.evaluate(signal)

        assert "position_limits" in result.checks_passed
```

**Implementation (add to `manager.py`):**

```python
async def _check_position_limits(self, signal: Signal) -> bool:
    """Check position-level limits."""
    # Sells always pass position limits
    if signal.action == "sell":
        return True

    # Check max quantity per order
    if signal.quantity > self._config.max_quantity_per_order:
        return False

    # Get current price
    price = await self._get_current_price(signal.symbol)
    position_value = Decimal(str(signal.quantity)) * price

    # Check max position value
    if position_value > self._config.max_position_value:
        return False

    # Check max position as % of portfolio
    account = await self._portfolio.get_account(self._config.account_id)
    position_pct = (position_value / account.total_equity) * 100

    if position_pct > self._config.max_position_pct:
        return False

    return True
```

**Files to create/update:**
- `backend/tests/risk/test_position_limits.py`
- `backend/src/risk/manager.py` (add _check_position_limits)

---

### Task 5: Portfolio Limits

**Goal:** Implement max positions, max exposure %, buying power check.

**Test first (`backend/tests/risk/test_portfolio_limits.py`):**

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.risk.models import RiskConfig
from src.risk.manager import RiskManager
from src.strategy.models import Signal


@pytest.fixture
def config():
    return RiskConfig(
        account_id="ACC001",
        max_positions=3,
        max_exposure_pct=Decimal("50")
    )


def make_position(symbol: str, market_value: Decimal):
    pos = MagicMock()
    pos.symbol = symbol
    pos.market_value = market_value
    return pos


class TestPortfolioLimits:
    @pytest.mark.asyncio
    async def test_max_positions_exceeded(self, config):
        """Reject new position when at max_positions."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("100000"),
            buying_power=Decimal("50000")
        ))
        portfolio.get_positions = AsyncMock(return_value=[
            make_position("AAPL", Decimal("10000")),
            make_position("GOOGL", Decimal("10000")),
            make_position("MSFT", Decimal("10000")),
        ])
        portfolio.get_position = AsyncMock(return_value=None)  # New position

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="TSLA",  # New position
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "portfolio_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_adding_to_existing_position_ok(self, config):
        """Can add to existing position even at max_positions."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("100000"),
            buying_power=Decimal("50000")
        ))
        portfolio.get_positions = AsyncMock(return_value=[
            make_position("AAPL", Decimal("10000")),
            make_position("GOOGL", Decimal("10000")),
            make_position("MSFT", Decimal("10000")),
        ])
        existing = MagicMock()
        existing.symbol = "AAPL"
        portfolio.get_position = AsyncMock(return_value=existing)

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",  # Existing position
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert "portfolio_limits" in result.checks_passed

    @pytest.mark.asyncio
    async def test_exposure_exceeded(self, config):
        """Reject when new exposure would exceed max_exposure_pct."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("100000"),
            buying_power=Decimal("50000")
        ))
        portfolio.get_positions = AsyncMock(return_value=[
            make_position("AAPL", Decimal("45000")),  # Already at 45%
        ])
        portfolio.get_position = AsyncMock(return_value=None)

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="GOOGL",
            action="buy",
            quantity=100  # 100 * 100 = 10000 -> 55% total > 50%
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "portfolio_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_insufficient_buying_power(self, config):
        """Reject when insufficient buying power."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("100000"),
            buying_power=Decimal("1000")  # Low buying power
        ))
        portfolio.get_positions = AsyncMock(return_value=[])
        portfolio.get_position = AsyncMock(return_value=None)

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=50  # 50 * 100 = 5000 > 1000 buying power
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "portfolio_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_sell_ignores_exposure(self, config):
        """Sell orders don't add exposure."""
        portfolio = MagicMock()
        portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("100000"),
            buying_power=Decimal("0")  # No buying power
        ))
        portfolio.get_positions = AsyncMock(return_value=[
            make_position("AAPL", Decimal("50000")),  # At 50% exposure
        ])
        portfolio.get_position = AsyncMock(return_value=MagicMock())

        manager = RiskManager(config, portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="sell",
            quantity=100
        )
        result = await manager.evaluate(signal)

        assert "portfolio_limits" in result.checks_passed
```

**Implementation (add to `manager.py`):**

```python
async def _check_portfolio_limits(self, signal: Signal) -> bool:
    """Check portfolio-level limits."""
    account = await self._portfolio.get_account(self._config.account_id)
    if not account:
        return False

    positions = await self._portfolio.get_positions(self._config.account_id)

    # Check max positions (only for new positions, only for buys)
    if signal.action == "buy":
        existing = await self._portfolio.get_position(
            self._config.account_id, signal.symbol, signal.strategy_id
        )
        if not existing and len(positions) >= self._config.max_positions:
            return False

    # Calculate exposure
    total_exposure = sum(p.market_value for p in positions)
    price = await self._get_current_price(signal.symbol)
    new_exposure = Decimal(str(signal.quantity)) * price if signal.action == "buy" else Decimal("0")
    exposure_pct = (total_exposure + new_exposure) / account.total_equity * 100

    if exposure_pct > self._config.max_exposure_pct:
        return False

    # Check buying power (only for buys)
    if signal.action == "buy":
        required = Decimal(str(signal.quantity)) * price
        if required > account.buying_power:
            return False

    return True
```

**Files to create/update:**
- `backend/tests/risk/test_portfolio_limits.py`
- `backend/src/risk/manager.py` (add _check_portfolio_limits)

---

### Task 6: Loss Limits

**Goal:** Implement daily loss limit and drawdown detection.

**Test first (`backend/tests/risk/test_loss_limits.py`):**

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.risk.models import RiskConfig
from src.risk.manager import RiskManager
from src.strategy.models import Signal


@pytest.fixture
def config():
    return RiskConfig(
        account_id="ACC001",
        daily_loss_limit=Decimal("1000"),
        max_drawdown_pct=Decimal("10")
    )


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(return_value=MagicMock(
        total_equity=Decimal("100000"),
        buying_power=Decimal("50000")
    ))
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


class TestLossLimits:
    @pytest.mark.asyncio
    async def test_daily_loss_triggers_kill_switch(self, config, mock_portfolio):
        """Kill switch activates when daily loss exceeded."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        # Simulate losses
        manager.update_daily_pnl(Decimal("-1100"))  # Exceeds 1000 limit

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert manager.is_killed() is True
        assert "Daily loss limit" in manager._kill_reason

    @pytest.mark.asyncio
    async def test_within_daily_loss_ok(self, config, mock_portfolio):
        """Trading allowed when within daily loss limit."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        manager.update_daily_pnl(Decimal("-500"))  # Within limit

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert "loss_limits" in result.checks_passed
        assert manager.is_killed() is False

    @pytest.mark.asyncio
    async def test_drawdown_triggers_kill_switch(self, config, mock_portfolio):
        """Kill switch activates when drawdown exceeded."""
        # Peak was 100k, now 89k = 11% drawdown > 10%
        mock_portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("89000"),
            buying_power=Decimal("50000")
        ))

        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))
        manager._peak_equity = Decimal("100000")

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert manager.is_killed() is True
        assert "Drawdown" in manager._kill_reason

    @pytest.mark.asyncio
    async def test_peak_equity_updates(self, config, mock_portfolio):
        """Peak equity updates when equity increases."""
        mock_portfolio.get_account = AsyncMock(return_value=MagicMock(
            total_equity=Decimal("110000"),  # New high
            buying_power=Decimal("50000")
        ))

        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))
        manager._peak_equity = Decimal("100000")

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10
        )
        await manager.evaluate(signal)

        assert manager._peak_equity == Decimal("110000")

    def test_reset_daily_stats(self, config, mock_portfolio):
        """Daily stats reset at start of day."""
        manager = RiskManager(config, mock_portfolio)
        manager._daily_pnl = Decimal("-500")

        manager.reset_daily_stats()

        assert manager._daily_pnl == Decimal("0")

    def test_update_daily_pnl(self, config, mock_portfolio):
        """update_daily_pnl accumulates P&L."""
        manager = RiskManager(config, mock_portfolio)

        manager.update_daily_pnl(Decimal("100"))
        manager.update_daily_pnl(Decimal("-50"))
        manager.update_daily_pnl(Decimal("25"))

        assert manager._daily_pnl == Decimal("75")
```

**Implementation (add to `manager.py`):**

```python
def update_daily_pnl(self, pnl_change: Decimal) -> None:
    """Update daily P&L with a change."""
    self._daily_pnl += pnl_change

def reset_daily_stats(self) -> None:
    """Reset daily statistics. Called at start of trading day."""
    self._daily_pnl = Decimal("0")

async def _check_loss_limits(self, signal: Signal) -> bool:
    """Check loss limits (daily loss, drawdown)."""
    # Check daily loss limit
    if self._daily_pnl < -self._config.daily_loss_limit:
        self.activate_kill_switch("Daily loss limit exceeded")
        return False

    # Check drawdown
    account = await self._portfolio.get_account(self._config.account_id)

    # Update peak equity if new high
    if account.total_equity > self._peak_equity:
        self._peak_equity = account.total_equity

    # Calculate drawdown (handle initial case)
    if self._peak_equity > 0:
        drawdown_pct = (self._peak_equity - account.total_equity) / self._peak_equity * 100
        if drawdown_pct > self._config.max_drawdown_pct:
            self.activate_kill_switch(f"Drawdown {drawdown_pct:.1f}% exceeded limit")
            return False

    return True
```

**Files to create/update:**
- `backend/tests/risk/test_loss_limits.py`
- `backend/src/risk/manager.py` (add loss limit methods)

---

### Task 7: Full Evaluate Flow Integration

**Goal:** Wire all checks together in evaluate() and test the full flow.

**Test first (`backend/tests/risk/test_risk_manager.py`):**

```python
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.risk.models import RiskConfig
from src.risk.manager import RiskManager
from src.strategy.models import Signal


@pytest.fixture
def config():
    return RiskConfig(
        account_id="ACC001",
        max_position_value=Decimal("10000"),
        max_position_pct=Decimal("5"),
        max_quantity_per_order=100,
        max_positions=10,
        max_exposure_pct=Decimal("50"),
        daily_loss_limit=Decimal("1000"),
        max_drawdown_pct=Decimal("10"),
        blocked_symbols=["BANNED"]
    )


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.get_account = AsyncMock(return_value=MagicMock(
        total_equity=Decimal("100000"),
        buying_power=Decimal("50000")
    ))
    portfolio.get_positions = AsyncMock(return_value=[])
    portfolio.get_position = AsyncMock(return_value=None)
    return portfolio


class TestFullEvaluateFlow:
    @pytest.mark.asyncio
    async def test_all_checks_pass(self, config, mock_portfolio):
        """Signal passes when all checks succeed."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=10  # 10 * 100 = 1000, well within limits
        )
        result = await manager.evaluate(signal)

        assert result.approved is True
        assert result.rejection_reason is None
        assert "symbol_allowed" in result.checks_passed
        assert "position_limits" in result.checks_passed
        assert "portfolio_limits" in result.checks_passed
        assert "loss_limits" in result.checks_passed
        assert len(result.checks_failed) == 0

    @pytest.mark.asyncio
    async def test_first_failure_recorded(self, config, mock_portfolio):
        """First failed check is recorded as rejection reason."""
        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("100"))

        signal = Signal(
            strategy_id="test",
            symbol="BANNED",  # Blocked symbol
            action="buy",
            quantity=10
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert result.rejection_reason == "symbol_allowed"

    @pytest.mark.asyncio
    async def test_multiple_failures(self, config, mock_portfolio):
        """Multiple failures are all recorded."""
        # Make portfolio return high exposure
        mock_portfolio.get_positions = AsyncMock(return_value=[
            MagicMock(market_value=Decimal("45000"))
        ])

        manager = RiskManager(config, mock_portfolio)
        manager._get_current_price = AsyncMock(return_value=Decimal("1000"))

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=200  # Exceeds quantity AND would exceed exposure
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        # Should fail position_limits first (quantity), then portfolio_limits (exposure)
        assert "position_limits" in result.checks_failed

    @pytest.mark.asyncio
    async def test_kill_switch_short_circuits(self, config, mock_portfolio):
        """Kill switch bypasses all other checks."""
        manager = RiskManager(config, mock_portfolio)
        manager.activate_kill_switch("Emergency")

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=1
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "kill_switch" in result.checks_failed
        # Other checks not run
        assert "symbol_allowed" not in result.checks_passed
        assert "symbol_allowed" not in result.checks_failed

    @pytest.mark.asyncio
    async def test_strategy_pause_short_circuits(self, config, mock_portfolio):
        """Strategy pause bypasses other checks for that strategy."""
        manager = RiskManager(config, mock_portfolio)
        manager.pause_strategy("momentum")

        signal = Signal(
            strategy_id="momentum",
            symbol="AAPL",
            action="buy",
            quantity=1
        )
        result = await manager.evaluate(signal)

        assert result.approved is False
        assert "strategy_paused" in result.checks_failed
```

**Update `manager.py` evaluate() to wire all checks:**

```python
async def evaluate(self, signal: Signal) -> RiskResult:
    """Run all risk checks on a signal."""
    checks_passed: list[str] = []
    checks_failed: list[str] = []

    # Kill switch is instant rejection (short-circuit)
    if self._killed:
        return RiskResult(
            approved=False,
            signal=signal,
            rejection_reason=f"Kill switch active: {self._kill_reason}",
            checks_failed=["kill_switch"]
        )

    # Strategy pause check (short-circuit)
    if signal.strategy_id in self._paused_strategies:
        return RiskResult(
            approved=False,
            signal=signal,
            rejection_reason=f"Strategy {signal.strategy_id} is paused",
            checks_failed=["strategy_paused"]
        )

    # Run all checks sequentially
    checks = [
        ("symbol_allowed", self._check_symbol_allowed),
        ("position_limits", self._check_position_limits),
        ("portfolio_limits", self._check_portfolio_limits),
        ("loss_limits", self._check_loss_limits),
    ]

    for check_name, check_fn in checks:
        passed = await check_fn(signal)
        if passed:
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

**Files to create/update:**
- `backend/tests/risk/test_risk_manager.py`
- `backend/src/risk/manager.py` (update evaluate)

---

### Task 8: Package Exports and Config File

**Goal:** Create package exports and default config file.

**Implementation (`backend/src/risk/__init__.py`):**

```python
"""Risk management module."""

from src.risk.models import RiskConfig, RiskResult
from src.risk.manager import RiskManager

__all__ = [
    "RiskConfig",
    "RiskResult",
    "RiskManager",
]
```

**Create default config (`config/risk.yaml`):**

```yaml
risk:
  account_id: "default"

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

**Files to create:**
- `backend/src/risk/__init__.py`
- `config/risk.yaml`

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | RiskConfig and RiskResult models | 4 |
| 2 | Kill switch and strategy pause | 8 |
| 3 | Symbol restrictions | 5 |
| 4 | Position limits | 5 |
| 5 | Portfolio limits | 5 |
| 6 | Loss limits | 6 |
| 7 | Full evaluate flow | 5 |
| 8 | Package exports and config | - |

**Total: 8 tasks, ~38 tests**

## Execution

Run tests with:
```bash
cd backend && pytest tests/risk/ -v
```
