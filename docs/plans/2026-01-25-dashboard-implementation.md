# Basic Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a single-page React dashboard with portfolio view, trading state, safety controls, and reconciliation alerts.

**Architecture:** React + TypeScript frontend with TanStack Query for data fetching. Backend FastAPI endpoints for portfolio, risk state, and reconciliation. Safety-critical components (ConfirmModal, FreshnessIndicator) get 100% test coverage.

**Tech Stack:** React 18, TypeScript, Vite, TanStack Query, Tailwind CSS, Axios, Vitest, FastAPI, Pydantic

---

## Part A: Backend API Endpoints

### Task 1: Trading State Model and Storage

**Files:**
- Create: `backend/src/risk/state.py`
- Create: `backend/tests/risk/test_state.py`

**Step 1: Write the failing test**

```python
# backend/tests/risk/test_state.py
import pytest
from datetime import datetime
from src.risk.state import TradingState, TradingStateManager, StateValue


class TestTradingState:
    def test_initial_state_is_running(self):
        manager = TradingStateManager()
        state = manager.get_state()
        assert state.state == StateValue.RUNNING

    def test_halt_changes_state(self):
        manager = TradingStateManager()
        manager.halt(changed_by="test", reason="test halt")
        state = manager.get_state()
        assert state.state == StateValue.HALTED
        assert state.changed_by == "test"
        assert state.reason == "test halt"
        assert not state.can_resume  # Needs manual intervention first

    def test_pause_changes_state(self):
        manager = TradingStateManager()
        manager.pause(changed_by="test")
        state = manager.get_state()
        assert state.state == StateValue.PAUSED
        assert state.can_resume

    def test_resume_from_paused(self):
        manager = TradingStateManager()
        manager.pause(changed_by="test")
        manager.resume(changed_by="test")
        state = manager.get_state()
        assert state.state == StateValue.RUNNING

    def test_resume_from_halted_requires_flag(self):
        manager = TradingStateManager()
        manager.halt(changed_by="test", reason="emergency")
        # First call to resume sets can_resume=True
        manager.enable_resume(changed_by="admin")
        state = manager.get_state()
        assert state.can_resume
        # Second call actually resumes
        manager.resume(changed_by="admin")
        state = manager.get_state()
        assert state.state == StateValue.RUNNING
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/risk/test_state.py -v`
Expected: FAIL with "No module named 'src.risk.state'"

**Step 3: Write minimal implementation**

```python
# backend/src/risk/state.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class StateValue(str, Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    HALTED = "HALTED"


@dataclass
class TradingState:
    state: StateValue
    since: datetime
    changed_by: str
    reason: Optional[str] = None
    can_resume: bool = True


class TradingStateManager:
    """Manages trading state with state machine semantics."""

    def __init__(self):
        self._state = TradingState(
            state=StateValue.RUNNING,
            since=datetime.utcnow(),
            changed_by="system",
            reason="initial state",
            can_resume=True,
        )

    def get_state(self) -> TradingState:
        return self._state

    def halt(self, changed_by: str, reason: str) -> None:
        self._state = TradingState(
            state=StateValue.HALTED,
            since=datetime.utcnow(),
            changed_by=changed_by,
            reason=reason,
            can_resume=False,  # Requires enable_resume first
        )

    def pause(self, changed_by: str, reason: Optional[str] = None) -> None:
        self._state = TradingState(
            state=StateValue.PAUSED,
            since=datetime.utcnow(),
            changed_by=changed_by,
            reason=reason,
            can_resume=True,
        )

    def enable_resume(self, changed_by: str) -> None:
        """Enable resume from HALTED state (manual intervention step)."""
        if self._state.state == StateValue.HALTED:
            self._state = TradingState(
                state=StateValue.HALTED,
                since=self._state.since,
                changed_by=changed_by,
                reason=self._state.reason,
                can_resume=True,
            )

    def resume(self, changed_by: str) -> bool:
        """Resume trading. Returns False if cannot resume."""
        if not self._state.can_resume:
            return False
        self._state = TradingState(
            state=StateValue.RUNNING,
            since=datetime.utcnow(),
            changed_by=changed_by,
            reason="resumed",
            can_resume=True,
        )
        return True

    def is_trading_allowed(self) -> bool:
        """Check if new trading activity is allowed."""
        return self._state.state == StateValue.RUNNING

    def is_close_allowed(self) -> bool:
        """Check if closing positions is allowed."""
        return self._state.state in (StateValue.RUNNING, StateValue.PAUSED)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/risk/test_state.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/risk/state.py backend/tests/risk/test_state.py
git commit -m "feat(risk): add TradingStateManager with state machine"
```

---

### Task 2: Risk API Endpoints (State, Halt, Resume)

**Files:**
- Create: `backend/src/api/risk.py`
- Modify: `backend/src/main.py`
- Create: `backend/tests/api/test_risk_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/api/test_risk_api.py
import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestRiskStateAPI:
    def test_get_state_returns_running(self, client):
        response = client.get("/api/risk/state")
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RUNNING"
        assert "since" in data
        assert "changed_by" in data
        assert "can_resume" in data

    def test_halt_changes_state(self, client):
        response = client.post("/api/risk/halt", json={"reason": "test"})
        assert response.status_code == 200

        state = client.get("/api/risk/state").json()
        assert state["state"] == "HALTED"

    def test_pause_changes_state(self, client):
        response = client.post("/api/risk/pause")
        assert response.status_code == 200

        state = client.get("/api/risk/state").json()
        assert state["state"] == "PAUSED"

    def test_resume_from_paused(self, client):
        client.post("/api/risk/pause")
        response = client.post("/api/risk/resume")
        assert response.status_code == 200

        state = client.get("/api/risk/state").json()
        assert state["state"] == "RUNNING"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_risk_api.py -v`
Expected: FAIL with 404 (endpoint not found)

**Step 3: Write minimal implementation**

```python
# backend/src/api/risk.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from src.risk.state import TradingStateManager, StateValue

router = APIRouter(prefix="/api/risk", tags=["risk"])

# Singleton state manager (in production, use dependency injection)
_state_manager = TradingStateManager()


class TradingStateResponse(BaseModel):
    state: str
    since: str
    changed_by: str
    reason: Optional[str]
    can_resume: bool


class HaltRequest(BaseModel):
    reason: str


class ActionResponse(BaseModel):
    success: bool
    state: str


@router.get("/state", response_model=TradingStateResponse)
async def get_state():
    state = _state_manager.get_state()
    return TradingStateResponse(
        state=state.state.value,
        since=state.since.isoformat(),
        changed_by=state.changed_by,
        reason=state.reason,
        can_resume=state.can_resume,
    )


@router.post("/halt", response_model=ActionResponse)
async def halt(request: HaltRequest):
    _state_manager.halt(changed_by="dashboard", reason=request.reason)
    return ActionResponse(success=True, state="HALTED")


@router.post("/pause", response_model=ActionResponse)
async def pause():
    _state_manager.pause(changed_by="dashboard")
    return ActionResponse(success=True, state="PAUSED")


@router.post("/resume", response_model=ActionResponse)
async def resume():
    state = _state_manager.get_state()
    if state.state == StateValue.HALTED and not state.can_resume:
        raise HTTPException(status_code=400, detail="Cannot resume: enable_resume required first")
    success = _state_manager.resume(changed_by="dashboard")
    if not success:
        raise HTTPException(status_code=400, detail="Cannot resume from current state")
    return ActionResponse(success=True, state="RUNNING")


@router.post("/enable-resume", response_model=ActionResponse)
async def enable_resume():
    _state_manager.enable_resume(changed_by="dashboard")
    return ActionResponse(success=True, state=_state_manager.get_state().state.value)


def get_state_manager() -> TradingStateManager:
    """Get state manager for other modules."""
    return _state_manager


def reset_state_manager():
    """Reset state manager (for testing)."""
    global _state_manager
    _state_manager = TradingStateManager()
```

Add router to main.py:

```python
# backend/src/main.py (add import and include_router)
from src.api.risk import router as risk_router
app.include_router(risk_router)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_risk_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/risk.py backend/src/main.py backend/tests/api/test_risk_api.py
git commit -m "feat(api): add risk state endpoints (state, halt, pause, resume)"
```

---

### Task 3: Portfolio API Endpoints

**Files:**
- Create: `backend/src/api/portfolio.py`
- Modify: `backend/src/main.py`
- Create: `backend/tests/api/test_portfolio_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/api/test_portfolio_api.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestPortfolioAPI:
    def test_get_account_returns_summary(self, client):
        response = client.get("/api/portfolio/account/ACC001")
        assert response.status_code == 200
        data = response.json()
        assert "account_id" in data
        assert "cash" in data
        assert "total_equity" in data
        assert "unrealized_pnl" in data

    def test_get_positions_returns_list(self, client):
        response = client.get("/api/portfolio/positions/ACC001")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_portfolio_api.py -v`
Expected: FAIL with 404

**Step 3: Write minimal implementation**

```python
# backend/src/api/portfolio.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from decimal import Decimal

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class AccountSummary(BaseModel):
    account_id: str
    cash: float
    buying_power: float
    total_equity: float
    unrealized_pnl: float
    day_pnl: float
    updated_at: str


class PositionResponse(BaseModel):
    symbol: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    strategy_id: Optional[str]


@router.get("/account/{account_id}", response_model=AccountSummary)
async def get_account(account_id: str):
    # TODO: Wire to real PortfolioManager
    # For now, return mock data for frontend development
    from datetime import datetime
    return AccountSummary(
        account_id=account_id,
        cash=25000.00,
        buying_power=50000.00,
        total_equity=125000.00,
        unrealized_pnl=1250.00,
        day_pnl=500.00,
        updated_at=datetime.utcnow().isoformat(),
    )


@router.get("/positions/{account_id}", response_model=list[PositionResponse])
async def get_positions(account_id: str):
    # TODO: Wire to real PortfolioManager
    # For now, return mock data for frontend development
    return [
        PositionResponse(
            symbol="AAPL",
            quantity=100,
            avg_cost=150.00,
            current_price=155.00,
            market_value=15500.00,
            unrealized_pnl=500.00,
            strategy_id="momentum_v1",
        ),
        PositionResponse(
            symbol="TSLA",
            quantity=50,
            avg_cost=250.00,
            current_price=245.00,
            market_value=12250.00,
            unrealized_pnl=-250.00,
            strategy_id="momentum_v1",
        ),
    ]
```

Add router to main.py:

```python
# backend/src/main.py (add import and include_router)
from src.api.portfolio import router as portfolio_router
app.include_router(portfolio_router)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_portfolio_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/portfolio.py backend/src/main.py backend/tests/api/test_portfolio_api.py
git commit -m "feat(api): add portfolio endpoints (account, positions)"
```

---

### Task 4: Reconciliation Recent Alerts Endpoint

**Files:**
- Create: `backend/src/api/reconciliation.py`
- Modify: `backend/src/main.py`
- Create: `backend/tests/api/test_reconciliation_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/api/test_reconciliation_api.py
import pytest
from fastapi.testclient import TestClient
from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestReconciliationAPI:
    def test_get_recent_returns_list(self, client):
        response = client.get("/api/reconciliation/recent")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_recent_alerts_have_required_fields(self, client):
        response = client.get("/api/reconciliation/recent")
        data = response.json()
        if len(data) > 0:
            alert = data[0]
            assert "timestamp" in alert
            assert "severity" in alert
            assert "type" in alert
            assert "message" in alert
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_reconciliation_api.py -v`
Expected: FAIL with 404

**Step 3: Write minimal implementation**

```python
# backend/src/api/reconciliation.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from collections import deque

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])

# In-memory store for recent alerts (Phase 1)
# Phase 2: Read from Redis or database
_recent_alerts: deque = deque(maxlen=10)


class ReconciliationAlert(BaseModel):
    timestamp: str
    severity: str  # "info" | "warning" | "critical"
    type: str
    symbol: Optional[str]
    local_value: Optional[str]
    broker_value: Optional[str]
    message: str


@router.get("/recent", response_model=list[ReconciliationAlert])
async def get_recent_alerts():
    return list(_recent_alerts)


def add_alert(alert: ReconciliationAlert):
    """Add alert to recent list (called by ReconciliationService)."""
    _recent_alerts.appendleft(alert)


def clear_alerts():
    """Clear alerts (for testing)."""
    _recent_alerts.clear()


# Add some mock alerts for frontend development
def _init_mock_alerts():
    from datetime import timedelta
    now = datetime.utcnow()
    mock_alerts = [
        ReconciliationAlert(
            timestamp=(now - timedelta(minutes=2)).isoformat(),
            severity="critical",
            type="MISSING_LOCAL",
            symbol="TSLA",
            local_value=None,
            broker_value="50",
            message="Broker has 50 shares we don't track",
        ),
        ReconciliationAlert(
            timestamp=(now - timedelta(minutes=5)).isoformat(),
            severity="warning",
            type="CASH_MISMATCH",
            symbol=None,
            local_value="25000",
            broker_value="25012",
            message="Cash difference: $12",
        ),
        ReconciliationAlert(
            timestamp=(now - timedelta(minutes=8)).isoformat(),
            severity="info",
            type="RECONCILIATION_PASSED",
            symbol=None,
            local_value=None,
            broker_value=None,
            message="Reconciliation passed (clean)",
        ),
    ]
    for alert in mock_alerts:
        _recent_alerts.append(alert)


_init_mock_alerts()
```

Add router to main.py:

```python
# backend/src/main.py (add import and include_router)
from src.api.reconciliation import router as reconciliation_router
app.include_router(reconciliation_router)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_reconciliation_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/reconciliation.py backend/src/main.py backend/tests/api/test_reconciliation_api.py
git commit -m "feat(api): add reconciliation recent alerts endpoint"
```

---

### Task 5: Kill Switch Compound Endpoint

**Files:**
- Modify: `backend/src/api/risk.py`
- Modify: `backend/tests/api/test_risk_api.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/api/test_risk_api.py

class TestKillSwitchAPI:
    def test_kill_switch_halts_and_returns_actions(self, client):
        # Reset state first
        from src.api.risk import reset_state_manager
        reset_state_manager()

        response = client.post("/api/risk/kill-switch")
        assert response.status_code == 200
        data = response.json()

        assert data["success"] == True
        assert data["state"] == "HALTED"
        assert "actions_executed" in data
        assert data["actions_executed"]["halted"] == True
        assert "orders_cancelled" in data["actions_executed"]
        assert "positions_flattened" in data["actions_executed"]

    def test_kill_switch_sets_halted_state(self, client):
        from src.api.risk import reset_state_manager
        reset_state_manager()

        client.post("/api/risk/kill-switch")
        state = client.get("/api/risk/state").json()
        assert state["state"] == "HALTED"
        assert state["can_resume"] == False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_risk_api.py::TestKillSwitchAPI -v`
Expected: FAIL with 404 or missing response fields

**Step 3: Write minimal implementation**

Add to `backend/src/api/risk.py`:

```python
class KillSwitchResult(BaseModel):
    success: bool
    state: str
    actions_executed: dict
    errors: list[str]
    timestamp: str
    triggered_by: str


@router.post("/kill-switch", response_model=KillSwitchResult)
async def kill_switch():
    """
    Emergency kill switch - compound action:
    1. HALT trading
    2. Cancel all pending orders
    3. Flatten all positions (market orders)
    """
    from datetime import datetime
    errors = []
    orders_cancelled = 0
    positions_flattened = 0
    flatten_orders = []

    # Step 1: HALT
    _state_manager.halt(changed_by="dashboard", reason="kill switch triggered")

    # Step 2: Cancel all orders
    # TODO: Wire to OrderManager.cancel_all()
    # For now, mock success
    orders_cancelled = 0  # Would be actual count

    # Step 3: Flatten all positions
    # TODO: Wire to OrderManager to submit market close orders
    # For now, mock success
    positions_flattened = 0  # Would be actual count

    return KillSwitchResult(
        success=True,
        state="HALTED",
        actions_executed={
            "halted": True,
            "orders_cancelled": orders_cancelled,
            "positions_flattened": positions_flattened,
            "flatten_orders": flatten_orders,
        },
        errors=errors,
        timestamp=datetime.utcnow().isoformat(),
        triggered_by="dashboard",
    )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_risk_api.py::TestKillSwitchAPI -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/risk.py backend/tests/api/test_risk_api.py
git commit -m "feat(api): add kill-switch compound endpoint"
```

---

### Task 6: Close Position Endpoint

**Files:**
- Create: `backend/src/api/orders.py`
- Modify: `backend/src/main.py`
- Create: `backend/tests/api/test_orders_api.py`

**Step 1: Write the failing test**

```python
# backend/tests/api/test_orders_api.py
import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.api.risk import reset_state_manager


@pytest.fixture
def client():
    reset_state_manager()  # Ensure RUNNING state
    return TestClient(app)


class TestClosePositionAPI:
    def test_close_position_accepts_request(self, client):
        response = client.post("/api/orders/close", json={
            "symbol": "AAPL",
            "quantity": "all",
            "order_type": "market",
            "time_in_force": "IOC",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "order_id" in data

    def test_close_position_rejected_when_halted(self, client):
        # First halt the system
        client.post("/api/risk/kill-switch")

        response = client.post("/api/orders/close", json={
            "symbol": "AAPL",
            "quantity": "all",
            "order_type": "market",
            "time_in_force": "IOC",
        })
        assert response.status_code == 400
        assert "HALTED" in response.json()["detail"]

    def test_close_position_allowed_when_paused(self, client):
        client.post("/api/risk/pause")

        response = client.post("/api/orders/close", json={
            "symbol": "AAPL",
            "quantity": "all",
            "order_type": "market",
            "time_in_force": "IOC",
        })
        assert response.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/api/test_orders_api.py -v`
Expected: FAIL with 404

**Step 3: Write minimal implementation**

```python
# backend/src/api/orders.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Union
import uuid

router = APIRouter(prefix="/api/orders", tags=["orders"])


class ClosePositionRequest(BaseModel):
    symbol: str
    quantity: Union[int, Literal["all"]]
    order_type: Literal["market", "limit"]
    limit_price: float | None = None
    time_in_force: Literal["GTC", "DAY", "IOC"] = "IOC"


class ClosePositionResponse(BaseModel):
    success: bool
    order_id: str
    message: str


@router.post("/close", response_model=ClosePositionResponse)
async def close_position(request: ClosePositionRequest):
    """Close a position. Only allowed in RUNNING or PAUSED state."""
    from src.api.risk import get_state_manager

    state_manager = get_state_manager()
    if not state_manager.is_close_allowed():
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close position: trading is HALTED. Resume first."
        )

    # TODO: Wire to OrderManager.submit_close_order()
    # For now, return mock success
    order_id = f"ORD-{uuid.uuid4().hex[:8].upper()}"

    return ClosePositionResponse(
        success=True,
        order_id=order_id,
        message=f"Close order submitted for {request.symbol}",
    )
```

Add router to main.py:

```python
# backend/src/main.py (add import and include_router)
from src.api.orders import router as orders_router
app.include_router(orders_router)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/api/test_orders_api.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/orders.py backend/src/main.py backend/tests/api/test_orders_api.py
git commit -m "feat(api): add close position endpoint with state check"
```

---

## Part B: Frontend Implementation

### Task 7: Frontend Project Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`

**Step 1: Create package.json**

```json
{
  "name": "aq-trading-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:ui": "vitest --ui"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@tanstack/react-query": "^5.17.0",
    "axios": "^1.6.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.16",
    "postcss": "^8.4.32",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0",
    "vitest": "^1.1.0",
    "@testing-library/react": "^14.1.0",
    "@testing-library/jest-dom": "^6.2.0",
    "jsdom": "^23.0.0"
  }
}
```

**Step 2: Create vite.config.ts**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
  },
})
```

**Step 3: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

**Step 4: Create tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

**Step 5: Create postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
```

**Step 6: Create index.html**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AQ Trading Dashboard</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

**Step 7: Create src/index.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

**Step 8: Create src/main.tsx**

```typescript
import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchInterval: 5000,
      retry: 2,
      retryDelay: 1000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
)
```

**Step 9: Create src/App.tsx**

```typescript
function App() {
  return (
    <div className="min-h-screen bg-gray-100">
      <h1 className="text-2xl font-bold p-4">AQ Trading Dashboard</h1>
      <p className="p-4">Setup complete. Components coming next.</p>
    </div>
  )
}

export default App
```

**Step 10: Create src/test/setup.ts**

```typescript
import '@testing-library/jest-dom'
```

**Step 11: Create tsconfig.node.json**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

**Step 12: Install dependencies and verify**

Run: `cd frontend && npm install && npm run dev`
Expected: Dev server starts at http://localhost:3000

**Step 13: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): initialize React + TypeScript + Vite + Tailwind project"
```

---

### Task 8: TypeScript Types

**Files:**
- Create: `frontend/src/types/index.ts`

**Step 1: Create types**

```typescript
// frontend/src/types/index.ts

export interface AccountSummary {
  account_id: string;
  cash: number;
  buying_power: number;
  total_equity: number;
  unrealized_pnl: number;
  day_pnl: number;
  updated_at: string;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  strategy_id: string | null;
}

export type TradingStateValue = 'RUNNING' | 'PAUSED' | 'HALTED';

export interface TradingState {
  state: TradingStateValue;
  since: string;
  changed_by: string;
  reason?: string;
  can_resume: boolean;
}

export interface KillSwitchResult {
  success: boolean;
  state: string;
  actions_executed: {
    halted: boolean;
    orders_cancelled: number;
    positions_flattened: number;
    flatten_orders: string[];
  };
  errors: string[];
  timestamp: string;
  triggered_by: string;
}

export interface ClosePositionRequest {
  symbol: string;
  quantity: number | 'all';
  order_type: 'market' | 'limit';
  limit_price?: number;
  time_in_force: 'GTC' | 'DAY' | 'IOC';
}

export interface ReconciliationAlert {
  timestamp: string;
  severity: 'info' | 'warning' | 'critical';
  type: string;
  symbol: string | null;
  local_value: string | null;
  broker_value: string | null;
  message: string;
}

export type FreshnessState = 'live' | 'stale' | 'error';
```

**Step 2: Commit**

```bash
git add frontend/src/types/
git commit -m "feat(frontend): add TypeScript type definitions"
```

---

### Task 9: API Client

**Files:**
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/portfolio.ts`
- Create: `frontend/src/api/risk.ts`
- Create: `frontend/src/api/orders.ts`
- Create: `frontend/src/api/reconciliation.ts`

**Step 1: Create API client**

```typescript
// frontend/src/api/client.ts
import axios from 'axios';

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});
```

**Step 2: Create portfolio API**

```typescript
// frontend/src/api/portfolio.ts
import { apiClient } from './client';
import type { AccountSummary, Position } from '../types';

export async function fetchAccount(accountId: string): Promise<AccountSummary> {
  const response = await apiClient.get<AccountSummary>(`/portfolio/account/${accountId}`);
  return response.data;
}

export async function fetchPositions(accountId: string): Promise<Position[]> {
  const response = await apiClient.get<Position[]>(`/portfolio/positions/${accountId}`);
  return response.data;
}
```

**Step 3: Create risk API**

```typescript
// frontend/src/api/risk.ts
import { apiClient } from './client';
import type { TradingState, KillSwitchResult } from '../types';

export async function fetchTradingState(): Promise<TradingState> {
  const response = await apiClient.get<TradingState>('/risk/state');
  return response.data;
}

export async function triggerKillSwitch(): Promise<KillSwitchResult> {
  const response = await apiClient.post<KillSwitchResult>('/risk/kill-switch');
  return response.data;
}

export async function pauseTrading(): Promise<void> {
  await apiClient.post('/risk/pause');
}

export async function resumeTrading(): Promise<void> {
  await apiClient.post('/risk/resume');
}
```

**Step 4: Create orders API**

```typescript
// frontend/src/api/orders.ts
import { apiClient } from './client';
import type { ClosePositionRequest } from '../types';

export async function closePosition(request: ClosePositionRequest): Promise<{ success: boolean; order_id: string }> {
  const response = await apiClient.post('/orders/close', request);
  return response.data;
}
```

**Step 5: Create reconciliation API**

```typescript
// frontend/src/api/reconciliation.ts
import { apiClient } from './client';
import type { ReconciliationAlert } from '../types';

export async function fetchRecentAlerts(): Promise<ReconciliationAlert[]> {
  const response = await apiClient.get<ReconciliationAlert[]>('/reconciliation/recent');
  return response.data;
}
```

**Step 6: Commit**

```bash
git add frontend/src/api/
git commit -m "feat(frontend): add API client and endpoint functions"
```

---

### Task 10: useFreshness Hook

**Files:**
- Create: `frontend/src/hooks/useFreshness.ts`
- Create: `frontend/src/hooks/useFreshness.test.ts`

**Step 1: Write the failing test**

```typescript
// frontend/src/hooks/useFreshness.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFreshness } from './useFreshness';

describe('useFreshness', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns live when data is fresh (< 10s)', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 5000, false, 0) // 5 seconds ago
    );

    expect(result.current.state).toBe('live');
    expect(result.current.ageSeconds).toBeLessThan(10);
  });

  it('returns stale when data is 10-30s old', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 15000, false, 0) // 15 seconds ago
    );

    expect(result.current.state).toBe('stale');
  });

  it('returns error when data is > 30s old', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 35000, false, 0) // 35 seconds ago
    );

    expect(result.current.state).toBe('error');
  });

  it('returns error when fetch failed 3+ times', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 5000, true, 3) // Fresh data but 3 failures
    );

    expect(result.current.state).toBe('error');
    expect(result.current.failureCount).toBe(3);
  });

  it('updates age over time', () => {
    const now = Date.now();
    const { result } = renderHook(() =>
      useFreshness(now - 5000, false, 0)
    );

    expect(result.current.state).toBe('live');

    // Advance time by 10 seconds
    act(() => {
      vi.advanceTimersByTime(10000);
    });

    // Now should be stale (15s old)
    expect(result.current.ageSeconds).toBeGreaterThanOrEqual(10);
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- useFreshness`
Expected: FAIL with "Cannot find module"

**Step 3: Write minimal implementation**

```typescript
// frontend/src/hooks/useFreshness.ts
import { useState, useEffect } from 'react';
import type { FreshnessState } from '../types';

interface FreshnessResult {
  state: FreshnessState;
  ageSeconds: number;
  failureCount: number;
}

export function useFreshness(
  dataUpdatedAt: number | undefined,
  isError: boolean,
  failureCount: number
): FreshnessResult {
  const [ageSeconds, setAgeSeconds] = useState(0);

  useEffect(() => {
    const updateAge = () => {
      if (dataUpdatedAt) {
        setAgeSeconds(Math.floor((Date.now() - dataUpdatedAt) / 1000));
      }
    };

    updateAge();
    const interval = setInterval(updateAge, 1000);
    return () => clearInterval(interval);
  }, [dataUpdatedAt]);

  const calculateState = (): FreshnessState => {
    // Hard error: 3+ consecutive failures
    if (failureCount >= 3) {
      return 'error';
    }

    // No data yet
    if (!dataUpdatedAt) {
      return isError ? 'error' : 'stale';
    }

    // Calculate based on age
    if (ageSeconds < 10) {
      return 'live';
    } else if (ageSeconds < 30) {
      return 'stale';
    } else {
      return 'error';
    }
  };

  return {
    state: calculateState(),
    ageSeconds,
    failureCount,
  };
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- useFreshness`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/hooks/useFreshness.ts frontend/src/hooks/useFreshness.test.ts
git commit -m "feat(frontend): add useFreshness hook with manual age calculation"
```

---

### Task 11: ConfirmModal Component

**Files:**
- Create: `frontend/src/components/ConfirmModal.tsx`
- Create: `frontend/src/components/ConfirmModal.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/components/ConfirmModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfirmModal } from './ConfirmModal';

describe('ConfirmModal', () => {
  it('renders title and message', () => {
    render(
      <ConfirmModal
        isOpen={true}
        title="Test Title"
        message="Test message"
        severity="warning"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );

    expect(screen.getByText('Test Title')).toBeInTheDocument();
    expect(screen.getByText('Test message')).toBeInTheDocument();
  });

  it('calls onConfirm when confirm button clicked', () => {
    const onConfirm = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Test"
        message="Test"
        severity="warning"
        onConfirm={onConfirm}
        onCancel={() => {}}
      />
    );

    fireEvent.click(screen.getByText('Confirm'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when cancel button clicked', () => {
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Test"
        message="Test"
        severity="warning"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    );

    fireEvent.click(screen.getByText('Cancel'));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('calls onCancel when Escape key pressed', () => {
    const onCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Test"
        message="Test"
        severity="warning"
        onConfirm={() => {}}
        onCancel={onCancel}
      />
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('does not render when isOpen is false', () => {
    render(
      <ConfirmModal
        isOpen={false}
        title="Test"
        message="Test"
        severity="warning"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );

    expect(screen.queryByText('Test')).not.toBeInTheDocument();
  });

  it('applies critical styling for critical severity', () => {
    render(
      <ConfirmModal
        isOpen={true}
        title="Test"
        message="Test"
        severity="critical"
        onConfirm={() => {}}
        onCancel={() => {}}
      />
    );

    const confirmButton = screen.getByText('Confirm');
    expect(confirmButton).toHaveClass('bg-red-600');
  });

  it('disables buttons when loading', () => {
    render(
      <ConfirmModal
        isOpen={true}
        title="Test"
        message="Test"
        severity="warning"
        onConfirm={() => {}}
        onCancel={() => {}}
        isLoading={true}
      />
    );

    expect(screen.getByText('Confirm')).toBeDisabled();
    expect(screen.getByText('Cancel')).toBeDisabled();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- ConfirmModal`
Expected: FAIL

**Step 3: Write minimal implementation**

```typescript
// frontend/src/components/ConfirmModal.tsx
import { useEffect } from 'react';

interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  message: string;
  severity: 'warning' | 'critical';
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
  confirmText?: string;
  cancelText?: string;
}

export function ConfirmModal({
  isOpen,
  title,
  message,
  severity,
  onConfirm,
  onCancel,
  isLoading = false,
  confirmText = 'Confirm',
  cancelText = 'Cancel',
}: ConfirmModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onCancel();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) {
    return null;
  }

  const confirmButtonClass = severity === 'critical'
    ? 'bg-red-600 hover:bg-red-700 text-white'
    : 'bg-yellow-500 hover:bg-yellow-600 text-white';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black bg-opacity-50"
        onClick={onCancel}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6">
        <h2 className="text-xl font-bold mb-4 flex items-center gap-2">
          {severity === 'critical' ? '⚠️' : '⚡'} {title}
        </h2>

        <p className="text-gray-600 mb-6 whitespace-pre-line">{message}</p>

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50"
          >
            {cancelText}
          </button>
          <button
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-4 py-2 rounded-md disabled:opacity-50 ${confirmButtonClass}`}
          >
            {isLoading ? 'Processing...' : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- ConfirmModal`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/ConfirmModal.tsx frontend/src/components/ConfirmModal.test.tsx
git commit -m "feat(frontend): add ConfirmModal component with safety features"
```

---

### Task 12: FreshnessIndicator Component

**Files:**
- Create: `frontend/src/components/FreshnessIndicator.tsx`
- Create: `frontend/src/components/FreshnessIndicator.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/components/FreshnessIndicator.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FreshnessIndicator } from './FreshnessIndicator';

describe('FreshnessIndicator', () => {
  it('shows green indicator for live state', () => {
    render(<FreshnessIndicator state="live" ageSeconds={5} />);
    expect(screen.getByText('🟢')).toBeInTheDocument();
    expect(screen.getByText(/5s ago/)).toBeInTheDocument();
  });

  it('shows yellow indicator for stale state', () => {
    render(<FreshnessIndicator state="stale" ageSeconds={15} />);
    expect(screen.getByText('🟡')).toBeInTheDocument();
  });

  it('shows red indicator for error state', () => {
    render(<FreshnessIndicator state="error" ageSeconds={45} />);
    expect(screen.getByText('🔴')).toBeInTheDocument();
  });

  it('formats time correctly for minutes', () => {
    render(<FreshnessIndicator state="error" ageSeconds={120} />);
    expect(screen.getByText(/2m ago/)).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- FreshnessIndicator`
Expected: FAIL

**Step 3: Write minimal implementation**

```typescript
// frontend/src/components/FreshnessIndicator.tsx
import type { FreshnessState } from '../types';

interface FreshnessIndicatorProps {
  state: FreshnessState;
  ageSeconds: number;
  lastUpdated?: string;
}

export function FreshnessIndicator({ state, ageSeconds, lastUpdated }: FreshnessIndicatorProps) {
  const indicator = {
    live: '🟢',
    stale: '🟡',
    error: '🔴',
  }[state];

  const formatAge = (seconds: number): string => {
    if (seconds < 60) {
      return `${seconds}s ago`;
    }
    const minutes = Math.floor(seconds / 60);
    return `${minutes}m ago`;
  };

  const stateLabel = {
    live: 'Live',
    stale: 'Stale',
    error: 'Error',
  }[state];

  return (
    <div className="flex items-center gap-2 text-sm text-gray-600">
      <span>{indicator}</span>
      <span>{stateLabel}</span>
      <span className="text-gray-400">({formatAge(ageSeconds)})</span>
      {lastUpdated && (
        <span className="text-gray-400">
          Last: {new Date(lastUpdated).toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- FreshnessIndicator`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/FreshnessIndicator.tsx frontend/src/components/FreshnessIndicator.test.tsx
git commit -m "feat(frontend): add FreshnessIndicator component"
```

---

### Task 13: TradingStateBadge Component

**Files:**
- Create: `frontend/src/components/TradingStateBadge.tsx`
- Create: `frontend/src/components/TradingStateBadge.test.tsx`

**Step 1: Write the failing test**

```typescript
// frontend/src/components/TradingStateBadge.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TradingStateBadge } from './TradingStateBadge';

describe('TradingStateBadge', () => {
  it('shows green badge for RUNNING', () => {
    render(<TradingStateBadge state="RUNNING" />);
    const badge = screen.getByText('🟢 RUNNING');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-green-100');
  });

  it('shows yellow badge for PAUSED', () => {
    render(<TradingStateBadge state="PAUSED" />);
    const badge = screen.getByText('🟡 PAUSED');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-yellow-100');
  });

  it('shows red badge for HALTED', () => {
    render(<TradingStateBadge state="HALTED" />);
    const badge = screen.getByText('🔴 HALTED');
    expect(badge).toBeInTheDocument();
    expect(badge).toHaveClass('bg-red-100');
  });

  it('applies pulse animation for HALTED', () => {
    render(<TradingStateBadge state="HALTED" />);
    const badge = screen.getByText('🔴 HALTED');
    expect(badge).toHaveClass('animate-pulse');
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- TradingStateBadge`
Expected: FAIL

**Step 3: Write minimal implementation**

```typescript
// frontend/src/components/TradingStateBadge.tsx
import type { TradingStateValue } from '../types';

interface TradingStateBadgeProps {
  state: TradingStateValue;
}

export function TradingStateBadge({ state }: TradingStateBadgeProps) {
  const config = {
    RUNNING: {
      icon: '🟢',
      bg: 'bg-green-100 text-green-800',
      animate: false,
    },
    PAUSED: {
      icon: '🟡',
      bg: 'bg-yellow-100 text-yellow-800',
      animate: false,
    },
    HALTED: {
      icon: '🔴',
      bg: 'bg-red-100 text-red-800',
      animate: true,
    },
  }[state];

  return (
    <span
      className={`px-3 py-1 rounded-full font-medium ${config.bg} ${
        config.animate ? 'animate-pulse' : ''
      }`}
    >
      {config.icon} {state}
    </span>
  );
}
```

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- TradingStateBadge`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/TradingStateBadge.tsx frontend/src/components/TradingStateBadge.test.tsx
git commit -m "feat(frontend): add TradingStateBadge component"
```

---

### Task 14: ErrorBanner Component

**Files:**
- Create: `frontend/src/components/ErrorBanner.tsx`

**Step 1: Create component**

```typescript
// frontend/src/components/ErrorBanner.tsx
interface ErrorBannerProps {
  failureCount: number;
  lastSuccessful?: string;
  onRetry: () => void;
}

export function ErrorBanner({ failureCount, lastSuccessful, onRetry }: ErrorBannerProps) {
  if (failureCount < 3) {
    return null;
  }

  const formatLastSuccessful = () => {
    if (!lastSuccessful) return 'Unknown';
    const date = new Date(lastSuccessful);
    const diff = Math.floor((Date.now() - date.getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    return `${Math.floor(diff / 60)}m ago`;
  };

  return (
    <div className="bg-red-50 border-l-4 border-red-500 p-4 mb-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <span className="text-red-500 font-medium">
            🔴 Connection Error ({failureCount} failures)
          </span>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1 bg-red-100 text-red-700 rounded hover:bg-red-200"
        >
          Retry Now
        </button>
      </div>
      <p className="text-sm text-red-600 mt-1">
        Last successful update: {formatLastSuccessful()}
      </p>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/ErrorBanner.tsx
git commit -m "feat(frontend): add ErrorBanner component"
```

---

### Task 15: Header, AccountSummary, PositionsTable, AlertsPanel Components

**Files:**
- Create: `frontend/src/components/Header.tsx`
- Create: `frontend/src/components/AccountSummary.tsx`
- Create: `frontend/src/components/PositionsTable.tsx`
- Create: `frontend/src/components/AlertsPanel.tsx`

**Step 1: Create Header**

```typescript
// frontend/src/components/Header.tsx
import { useState } from 'react';
import { TradingStateBadge } from './TradingStateBadge';
import { ConfirmModal } from './ConfirmModal';
import type { TradingStateValue } from '../types';

interface HeaderProps {
  tradingState: TradingStateValue;
  onKillSwitch: () => Promise<void>;
}

export function Header({ tradingState, onKillSwitch }: HeaderProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleConfirm = async () => {
    setIsLoading(true);
    try {
      await onKillSwitch();
    } finally {
      setIsLoading(false);
      setShowConfirm(false);
    }
  };

  return (
    <>
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-bold text-gray-900">AQ Trading</h1>
            <TradingStateBadge state={tradingState} />
          </div>

          <button
            onClick={() => setShowConfirm(true)}
            disabled={tradingState === 'HALTED'}
            className="px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed font-medium"
          >
            ⚠️ Kill Switch
          </button>
        </div>
      </header>

      <ConfirmModal
        isOpen={showConfirm}
        title="Confirm Kill Switch"
        message={`This will immediately:
1. HALT all trading
2. CANCEL all pending orders
3. FLATTEN all positions (market)

System will remain HALTED until manually resumed.

Are you sure?`}
        severity="critical"
        onConfirm={handleConfirm}
        onCancel={() => setShowConfirm(false)}
        isLoading={isLoading}
      />
    </>
  );
}
```

**Step 2: Create AccountSummary**

```typescript
// frontend/src/components/AccountSummary.tsx
import type { AccountSummary as AccountSummaryType } from '../types';

interface AccountSummaryProps {
  account: AccountSummaryType | undefined;
  isLoading: boolean;
}

export function AccountSummary({ account, isLoading }: AccountSummaryProps) {
  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  };

  const formatPnL = (value: number) => {
    const formatted = formatCurrency(Math.abs(value));
    return value >= 0 ? `+${formatted}` : `-${formatted}`;
  };

  if (isLoading || !account) {
    return (
      <div className="grid grid-cols-3 gap-4 mb-6">
        {[1, 2, 3].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow p-4 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-20 mb-2"></div>
            <div className="h-8 bg-gray-200 rounded w-32"></div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4 mb-6">
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Total Equity</p>
        <p className="text-2xl font-bold">{formatCurrency(account.total_equity)}</p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Cash</p>
        <p className="text-2xl font-bold">{formatCurrency(account.cash)}</p>
      </div>
      <div className="bg-white rounded-lg shadow p-4">
        <p className="text-sm text-gray-500">Day P&L</p>
        <p className={`text-2xl font-bold ${account.day_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
          {formatPnL(account.day_pnl)}
        </p>
      </div>
    </div>
  );
}
```

**Step 3: Create PositionsTable**

```typescript
// frontend/src/components/PositionsTable.tsx
import { useState } from 'react';
import { ConfirmModal } from './ConfirmModal';
import { FreshnessIndicator } from './FreshnessIndicator';
import type { Position, TradingStateValue, FreshnessState } from '../types';

interface PositionsTableProps {
  positions: Position[] | undefined;
  isLoading: boolean;
  tradingState: TradingStateValue;
  freshness: { state: FreshnessState; ageSeconds: number };
  onClosePosition: (symbol: string) => Promise<void>;
}

export function PositionsTable({
  positions,
  isLoading,
  tradingState,
  freshness,
  onClosePosition,
}: PositionsTableProps) {
  const [closingSymbol, setClosingSymbol] = useState<string | null>(null);
  const [isClosing, setIsClosing] = useState(false);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(value);
  };

  const handleConfirmClose = async () => {
    if (!closingSymbol) return;
    setIsClosing(true);
    try {
      await onClosePosition(closingSymbol);
    } finally {
      setIsClosing(false);
      setClosingSymbol(null);
    }
  };

  const canClose = tradingState !== 'HALTED';

  return (
    <>
      <div className="bg-white rounded-lg shadow mb-6">
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">Positions</h2>
          <FreshnessIndicator state={freshness.state} ageSeconds={freshness.ageSeconds} />
        </div>

        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Symbol</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Qty</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Avg Cost</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Current</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">P&L</th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                    Loading...
                  </td>
                </tr>
              ) : !positions || positions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                    No positions
                  </td>
                </tr>
              ) : (
                positions.map((pos) => (
                  <tr key={pos.symbol} className="hover:bg-gray-50">
                    <td className="px-4 py-3 font-medium">{pos.symbol}</td>
                    <td className="px-4 py-3 text-right">{pos.quantity}</td>
                    <td className="px-4 py-3 text-right">{formatCurrency(pos.avg_cost)}</td>
                    <td className="px-4 py-3 text-right">{formatCurrency(pos.current_price)}</td>
                    <td className={`px-4 py-3 text-right font-medium ${
                      pos.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'
                    }`}>
                      {pos.unrealized_pnl >= 0 ? '+' : ''}{formatCurrency(pos.unrealized_pnl)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => setClosingSymbol(pos.symbol)}
                        disabled={!canClose}
                        className="px-3 py-1 text-sm bg-gray-100 text-gray-700 rounded hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        Close
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmModal
        isOpen={!!closingSymbol}
        title={`Close ${closingSymbol} Position?`}
        message={`This will submit a market order to close your entire ${closingSymbol} position.`}
        severity="warning"
        onConfirm={handleConfirmClose}
        onCancel={() => setClosingSymbol(null)}
        isLoading={isClosing}
      />
    </>
  );
}
```

**Step 4: Create AlertsPanel**

```typescript
// frontend/src/components/AlertsPanel.tsx
import type { ReconciliationAlert } from '../types';

interface AlertsPanelProps {
  alerts: ReconciliationAlert[] | undefined;
  isLoading: boolean;
}

export function AlertsPanel({ alerts, isLoading }: AlertsPanelProps) {
  const severityIcon = {
    critical: '🔴',
    warning: '🟡',
    info: '🟢',
  };

  const formatTime = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString();
  };

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-4 py-3 border-b">
        <h2 className="text-lg font-semibold">⚠️ Reconciliation Alerts</h2>
      </div>

      <div className="divide-y divide-gray-100 max-h-64 overflow-y-auto">
        {isLoading ? (
          <div className="px-4 py-8 text-center text-gray-500">Loading...</div>
        ) : !alerts || alerts.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-500">No recent alerts</div>
        ) : (
          alerts.map((alert, idx) => (
            <div key={idx} className="px-4 py-3 hover:bg-gray-50">
              <div className="flex items-start gap-3">
                <span className="text-lg">{severityIcon[alert.severity]}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-gray-500">{formatTime(alert.timestamp)}</span>
                    <span className="font-medium text-gray-900">{alert.type}</span>
                    {alert.symbol && (
                      <span className="text-sm text-gray-600">{alert.symbol}</span>
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mt-1">{alert.message}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
```

**Step 5: Commit**

```bash
git add frontend/src/components/Header.tsx frontend/src/components/AccountSummary.tsx frontend/src/components/PositionsTable.tsx frontend/src/components/AlertsPanel.tsx
git commit -m "feat(frontend): add Header, AccountSummary, PositionsTable, AlertsPanel components"
```

---

### Task 16: App Integration

**Files:**
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/hooks/useAccount.ts`
- Create: `frontend/src/hooks/usePositions.ts`
- Create: `frontend/src/hooks/useTradingState.ts`
- Create: `frontend/src/hooks/useAlerts.ts`

**Step 1: Create hooks**

```typescript
// frontend/src/hooks/useAccount.ts
import { useQuery } from '@tanstack/react-query';
import { fetchAccount } from '../api/portfolio';

export function useAccount(accountId: string) {
  return useQuery({
    queryKey: ['account', accountId],
    queryFn: () => fetchAccount(accountId),
  });
}
```

```typescript
// frontend/src/hooks/usePositions.ts
import { useQuery } from '@tanstack/react-query';
import { fetchPositions } from '../api/portfolio';

export function usePositions(accountId: string) {
  return useQuery({
    queryKey: ['positions', accountId],
    queryFn: () => fetchPositions(accountId),
  });
}
```

```typescript
// frontend/src/hooks/useTradingState.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { fetchTradingState, triggerKillSwitch } from '../api/risk';

export function useTradingState() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ['tradingState'],
    queryFn: fetchTradingState,
  });

  const killSwitchMutation = useMutation({
    mutationFn: triggerKillSwitch,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tradingState'] });
    },
  });

  return {
    ...query,
    triggerKillSwitch: killSwitchMutation.mutateAsync,
  };
}
```

```typescript
// frontend/src/hooks/useAlerts.ts
import { useQuery } from '@tanstack/react-query';
import { fetchRecentAlerts } from '../api/reconciliation';

export function useAlerts() {
  return useQuery({
    queryKey: ['alerts'],
    queryFn: fetchRecentAlerts,
  });
}
```

**Step 2: Update App.tsx**

```typescript
// frontend/src/App.tsx
import { Header } from './components/Header';
import { AccountSummary } from './components/AccountSummary';
import { PositionsTable } from './components/PositionsTable';
import { AlertsPanel } from './components/AlertsPanel';
import { ErrorBanner } from './components/ErrorBanner';
import { useAccount } from './hooks/useAccount';
import { usePositions } from './hooks/usePositions';
import { useTradingState } from './hooks/useTradingState';
import { useAlerts } from './hooks/useAlerts';
import { useFreshness } from './hooks/useFreshness';
import { closePosition } from './api/orders';

const ACCOUNT_ID = 'ACC001'; // TODO: Make configurable

function App() {
  const account = useAccount(ACCOUNT_ID);
  const positions = usePositions(ACCOUNT_ID);
  const tradingState = useTradingState();
  const alerts = useAlerts();

  const positionsFreshness = useFreshness(
    positions.dataUpdatedAt,
    positions.isError,
    positions.failureCount ?? 0
  );

  const handleKillSwitch = async () => {
    await tradingState.triggerKillSwitch();
  };

  const handleClosePosition = async (symbol: string) => {
    await closePosition({
      symbol,
      quantity: 'all',
      order_type: 'market',
      time_in_force: 'IOC',
    });
    // Refresh positions after close
    positions.refetch();
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <Header
        tradingState={tradingState.data?.state ?? 'RUNNING'}
        onKillSwitch={handleKillSwitch}
      />

      <main className="max-w-7xl mx-auto px-4 py-6">
        <ErrorBanner
          failureCount={positions.failureCount ?? 0}
          lastSuccessful={positions.dataUpdatedAt ? new Date(positions.dataUpdatedAt).toISOString() : undefined}
          onRetry={() => positions.refetch()}
        />

        <AccountSummary
          account={account.data}
          isLoading={account.isLoading}
        />

        <PositionsTable
          positions={positions.data}
          isLoading={positions.isLoading}
          tradingState={tradingState.data?.state ?? 'RUNNING'}
          freshness={positionsFreshness}
          onClosePosition={handleClosePosition}
        />

        <AlertsPanel
          alerts={alerts.data}
          isLoading={alerts.isLoading}
        />
      </main>
    </div>
  );
}

export default App;
```

**Step 3: Verify it runs**

Run: `cd frontend && npm run dev`
Expected: Dashboard renders with mock data from backend

**Step 4: Commit**

```bash
git add frontend/src/hooks/ frontend/src/App.tsx
git commit -m "feat(frontend): integrate all components in App"
```

---

### Task 17: Final Integration Test

**Step 1: Start backend**

Run: `cd backend && uvicorn src.main:app --reload`

**Step 2: Start frontend**

Run: `cd frontend && npm run dev`

**Step 3: Verify in browser**

Open: http://localhost:3000

Expected:
- Header shows "AQ Trading" with 🟢 RUNNING badge
- Kill Switch button visible
- Account summary cards show mock data
- Positions table shows AAPL and TSLA
- Alerts panel shows mock reconciliation alerts
- Close button works (shows confirm modal)
- Kill Switch works (shows confirm modal, changes state to HALTED)

**Step 4: Run all tests**

Run: `cd backend && python -m pytest && cd ../frontend && npm test`
Expected: All tests pass

**Step 5: Final commit**

```bash
git add -A
git commit -m "feat: complete Basic Dashboard MVP implementation"
```

---

## Summary

**Backend (6 tasks):**
1. TradingStateManager with state machine
2. Risk API endpoints (state, halt, pause, resume)
3. Portfolio API endpoints (account, positions)
4. Reconciliation recent alerts endpoint
5. Kill switch compound endpoint
6. Close position endpoint with state check

**Frontend (11 tasks):**
7. Project setup (Vite, React, TypeScript, Tailwind)
8. TypeScript types
9. API client
10. useFreshness hook
11. ConfirmModal component (safety-critical)
12. FreshnessIndicator component
13. TradingStateBadge component
14. ErrorBanner component
15. Header, AccountSummary, PositionsTable, AlertsPanel
16. App integration
17. Final integration test
