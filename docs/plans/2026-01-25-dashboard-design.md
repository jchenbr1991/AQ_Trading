# Basic Dashboard Design

Phase 1 MVP dashboard for monitoring and emergency controls.

## Overview

Single-page React application that displays portfolio state and provides emergency controls. REST-only (no WebSocket in Phase 1).

**Key Decisions:**
- Scope: Minimal MVP (single page, not multi-page)
- Data: TanStack Query polling every 5 seconds
- Safety: Confirmation modals for all destructive actions
- Freshness: Visual indicators for data staleness (manual calculation)
- Alerts: Reconciliation discrepancies displayed for operator awareness
- State: Trading state visible in header with explicit state machine

## Tech Stack

| Technology | Purpose |
|------------|---------|
| React 18 | UI framework |
| TypeScript | Type safety |
| Vite | Build tool / dev server |
| TanStack Query | Data fetching with auto-refresh |
| Tailwind CSS | Styling |
| Axios | HTTP client |
| Vitest | Testing |

## Layout

```
┌─────────────────────────────────────────────────────┐
│  AQ Trading    [🟢 RUNNING]              [Kill Switch]│
├─────────────────────────────────────────────────────┤
│  Account Summary                                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │ Equity   │ │ Cash     │ │ Day P&L  │            │
│  │ $125,000 │ │ $25,000  │ │ +$1,250  │            │
│  └──────────┘ └──────────┘ └──────────┘            │
├─────────────────────────────────────────────────────┤
│  Positions                 Last updated: 10:32:45 🟢│
│  ┌─────────────────────────────────────────────────┐│
│  │ Symbol │ Qty │ Avg Cost │ Current │ P&L │ Action ││
│  │ AAPL   │ 100 │ $150.00  │ $155.00 │ +$500│[Close]││
│  │ TSLA   │ 50  │ $250.00  │ $245.00 │ -$250│[Close]││
│  └─────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────┤
│  ⚠️ Reconciliation Alerts                           │
│  🔴 10:32:15  MISSING_LOCAL   TSLA: Broker has 50   │
│  🟡 10:30:42  CASH_MISMATCH   Diff: $12             │
│  🟢 10:28:00  Reconciliation passed (clean)         │
└─────────────────────────────────────────────────────┘
```

## Trading State Machine

### States

| State | Badge | Description | Allowed Actions |
|-------|-------|-------------|-----------------|
| `RUNNING` | 🟢 Green | Normal trading | All |
| `PAUSED` | 🟡 Yellow | No new signals, existing orders active | Close position, Cancel |
| `HALTED` | 🔴 Red | Emergency stop, all trading frozen | Resume only (manual) |

### State Transitions

```
RUNNING ──[pause]──> PAUSED ──[resume]──> RUNNING
    │                   │
    └──[kill-switch]────┴──────────────> HALTED
                                            │
                                    [manual resume]
                                            │
                                            v
                                        RUNNING
```

### Kill Switch Definition (Critical)

**Kill Switch is a compound action that executes in order:**

1. **HALT** - Set trading state to HALTED (latched, requires manual resume)
2. **CANCEL_ALL** - Cancel all pending/open orders
3. **FLATTEN_ALL** - Submit market orders to close all positions

**API Response includes executed sub-actions:**

```typescript
// POST /api/risk/kill-switch response
interface KillSwitchResult {
  success: boolean;
  state: "HALTED";
  actions_executed: {
    halted: boolean;
    orders_cancelled: number;
    positions_flattened: number;
    flatten_orders: string[];  // Order IDs for tracking
  };
  errors: string[];  // Any failures during execution
  timestamp: string;
  triggered_by: string;  // "dashboard" | "api" | "auto"
}
```

**Explicit API Design (Split Actions):**

| Endpoint | Method | Purpose | When to Use |
|----------|--------|---------|-------------|
| `POST /api/risk/halt` | POST | Stop new trading only | Pause for investigation |
| `POST /api/risk/cancel-all` | POST | Cancel pending orders | Clear order book |
| `POST /api/risk/flatten-all` | POST | Market close all positions | Emergency exit |
| `POST /api/risk/kill-switch` | POST | All three above in sequence | Nuclear option |
| `POST /api/risk/resume` | POST | Resume from HALTED/PAUSED | Manual recovery |
| `GET /api/risk/state` | GET | Current trading state | Dashboard polling |

**UI Kill Switch Button calls `/api/risk/kill-switch` which executes all three.**

## Safety Controls

### Double-Tap Confirmation Pattern

All destructive actions require a confirmation modal:

```
┌─────────────────────────────────────────┐
│  ⚠️  Confirm Kill Switch               │
├─────────────────────────────────────────┤
│                                         │
│  This will immediately:                 │
│  1. HALT all trading                    │
│  2. CANCEL all pending orders           │
│  3. FLATTEN all positions (market)      │
│                                         │
│  System will remain HALTED until        │
│  manually resumed.                      │
│                                         │
│  Are you sure?                          │
│                                         │
│         [Cancel]    [Confirm]           │
└─────────────────────────────────────────┘
```

**Actions requiring confirmation:**

| Action | Modal Title | Severity |
|--------|-------------|----------|
| Kill Switch | "Confirm Kill Switch" | Critical (red) |
| Close Position | "Close {SYMBOL} Position?" | Warning (yellow) |

**Modal behavior:**
- Escape key or click outside = cancel
- Loading state disables buttons during API call
- Kill switch button is red with warning icon

## Close Position Semantics

### Request Schema

```typescript
// POST /api/orders/close
interface ClosePositionRequest {
  symbol: string;
  quantity: number | "all";      // Explicit: full or partial
  order_type: "market" | "limit";
  limit_price?: number;          // Required if order_type=limit
  reduce_only: true;             // Always true for close (enforced)
  time_in_force: "GTC" | "DAY" | "IOC";
}
```

### Constraints

| Field | Dashboard Default | Notes |
|-------|-------------------|-------|
| `quantity` | `"all"` | Full position close |
| `order_type` | `"market"` | Immediate execution |
| `reduce_only` | `true` | Cannot increase position |
| `time_in_force` | `"IOC"` | Immediate or cancel |

### Behavior by Trading State

| State | Close Button | Behavior |
|-------|--------------|----------|
| `RUNNING` | Enabled | Normal close |
| `PAUSED` | Enabled | Allowed (controlled exit) |
| `HALTED` | **Disabled** | No orders allowed; use Resume first |

**Note:** In HALTED state, positions were already flattened by kill switch. If operator needs manual close after resume, they must first resume trading.

## Data Freshness & Error States

### Freshness Calculation (Manual, not TanStack isStale)

**IMPORTANT:** Do NOT use TanStack Query's `isStale` - it's cache semantics, not data trust.

```typescript
function calculateFreshness(dataUpdatedAt: number): FreshnessState {
  const ageMs = Date.now() - dataUpdatedAt;
  const ageSeconds = ageMs / 1000;

  if (ageSeconds < 10) return 'live';
  if (ageSeconds < 30) return 'stale';
  return 'error';
}
```

### Staleness States

| State | Indicator | Condition |
|-------|-----------|-----------|
| Live | 🟢 Green | `now - dataUpdatedAt` < 10s |
| Stale | 🟡 Yellow | `now - dataUpdatedAt` 10-30s |
| Error | 🔴 Red | `now - dataUpdatedAt` > 30s OR fetch failed |

### Error State Differentiation

| Error Type | Indicator | Condition | User Message |
|------------|-----------|-----------|--------------|
| **Hard Error** | 🔴 + Banner | 3+ consecutive fetch failures | "Connection lost" |
| **Soft Stale** | 🟡 | No failure but data > 30s old | "Data may be outdated" |
| **Recovering** | 🟡 + spinner | After failure, retrying | "Reconnecting..." |

### Error Banner

```
┌─────────────────────────────────────────────────────┐
│ 🔴 Connection Error (3 failures)        [Retry Now] │
│ Last successful update: 10:30:12 (2 min ago)        │
└─────────────────────────────────────────────────────┘
```

### TanStack Query Configuration

```typescript
const { data, dataUpdatedAt, isError, failureCount, refetch } = useQuery({
  queryKey: ['positions'],
  queryFn: fetchPositions,
  refetchInterval: 5000,
  retry: 2,
  retryDelay: 1000,
});

// Custom freshness hook
const freshness = useFreshness(dataUpdatedAt, isError, failureCount);
// Returns: { state: 'live'|'stale'|'error', ageSeconds, failureCount }
```

## Trading State Visibility

### Header State Badge

```
┌─────────────────────────────────────────────────────┐
│  AQ Trading    [🟢 RUNNING]              [Kill Switch]│
│                 ▲                                    │
│                 └── State badge with color           │
└─────────────────────────────────────────────────────┘
```

**Badge States:**

| State | Display | Color |
|-------|---------|-------|
| RUNNING | `🟢 RUNNING` | Green background |
| PAUSED | `🟡 PAUSED` | Yellow background |
| HALTED | `🔴 HALTED` | Red background, pulsing |

### State API

```typescript
// GET /api/risk/state
interface TradingState {
  state: "RUNNING" | "PAUSED" | "HALTED";
  since: string;           // ISO timestamp of last state change
  changed_by: string;      // "dashboard" | "api" | "auto" | "system"
  reason?: string;         // Why state changed (e.g., "daily loss limit")
  can_resume: boolean;     // Whether resume is allowed
}
```

**Polling:** State endpoint polled every 5 seconds along with other data.

## Reconciliation Alerts Panel

Displays recent discrepancies from the Reconciliation Service.

**Alert Fields:**

| Field | Source | Display |
|-------|--------|---------|
| Time | `timestamp` | HH:MM:SS |
| Severity | `DiscrepancySeverity` | 🔴 Critical / 🟡 Warning / 🟢 Info |
| Type | `DiscrepancyType` | MISSING_LOCAL, CASH_MISMATCH, etc. |
| Description | `local_value`, `broker_value` | Human-readable diff |

**Operator Decision Flow:**
```
See 🔴 MISSING_LOCAL alert
    ↓
Check positions table
    ↓
Decide: Investigate or Kill Switch
```

## API Endpoints

### Required REST Endpoints

| Endpoint | Method | Purpose | Status |
|----------|--------|---------|--------|
| `/api/health` | GET | Backend health check | ✅ Exists |
| `/api/portfolio/account/{id}` | GET | Account summary | 🆕 Need |
| `/api/portfolio/positions/{id}` | GET | Positions list | 🆕 Need |
| `/api/risk/state` | GET | Current trading state | 🆕 Need |
| `/api/risk/kill-switch` | POST | Emergency stop (compound) | 🔄 Enhance |
| `/api/risk/halt` | POST | Stop trading only | 🆕 Need |
| `/api/risk/cancel-all` | POST | Cancel all orders | 🆕 Need |
| `/api/risk/flatten-all` | POST | Close all positions | 🆕 Need |
| `/api/risk/resume` | POST | Resume trading | 🆕 Need |
| `/api/orders/close` | POST | Close single position | 🆕 Need |
| `/api/reconciliation/recent` | GET | Last 10 alerts | 🆕 Need |

### Response Schemas

```typescript
// GET /api/portfolio/account/{id}
interface AccountSummary {
  account_id: string;
  cash: number;
  buying_power: number;
  total_equity: number;
  unrealized_pnl: number;
  day_pnl: number;
  updated_at: string;
}

// GET /api/portfolio/positions/{id}
interface Position {
  symbol: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  strategy_id: string | null;
}

// GET /api/risk/state
interface TradingState {
  state: "RUNNING" | "PAUSED" | "HALTED";
  since: string;
  changed_by: string;
  reason?: string;
  can_resume: boolean;
}

// POST /api/risk/kill-switch
interface KillSwitchResult {
  success: boolean;
  state: "HALTED";
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

// POST /api/orders/close
interface ClosePositionRequest {
  symbol: string;
  quantity: number | "all";
  order_type: "market" | "limit";
  limit_price?: number;
  reduce_only: true;
  time_in_force: "GTC" | "DAY" | "IOC";
}

// GET /api/reconciliation/recent
interface ReconciliationAlert {
  timestamp: string;
  severity: "info" | "warning" | "critical";
  type: string;
  symbol: string | null;
  local_value: string | null;
  broker_value: string | null;
  message: string;
}
```

## File Structure

```
aq_trading/
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── tailwind.config.js
    ├── index.html
    │
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   │
    │   ├── api/
    │   │   ├── client.ts
    │   │   ├── portfolio.ts
    │   │   ├── orders.ts
    │   │   ├── risk.ts
    │   │   └── reconciliation.ts
    │   │
    │   ├── components/
    │   │   ├── Header.tsx
    │   │   ├── TradingStateBadge.tsx
    │   │   ├── AccountSummary.tsx
    │   │   ├── PositionsTable.tsx
    │   │   ├── AlertsPanel.tsx
    │   │   ├── ConfirmModal.tsx
    │   │   ├── FreshnessIndicator.tsx
    │   │   └── ErrorBanner.tsx
    │   │
    │   ├── hooks/
    │   │   ├── useAccount.ts
    │   │   ├── usePositions.ts
    │   │   ├── useTradingState.ts
    │   │   ├── useAlerts.ts
    │   │   └── useFreshness.ts
    │   │
    │   └── types/
    │       └── index.ts
    │
    └── tests/
        └── components/
            ├── ConfirmModal.test.tsx
            └── FreshnessIndicator.test.tsx
```

## Testing Strategy

| Category | Tool | Focus |
|----------|------|-------|
| Component | Vitest + React Testing Library | UI rendering, user interactions |
| API Mocking | MSW (Mock Service Worker) | API response handling |
| E2E (Phase 2) | Playwright | Full flow testing |

**Key Test Cases:**

- ConfirmModal: confirm/cancel behavior, escape key, severity styling
- PositionsTable: rendering, close button disabled in HALTED state
- FreshnessIndicator: correct state for age thresholds
- TradingStateBadge: correct color/text for each state
- useFreshness: manual calculation from dataUpdatedAt

**MVP Test Coverage Target:**
- ConfirmModal: 100% (safety-critical)
- FreshnessIndicator: 100% (safety-critical)
- TradingStateBadge: 100% (safety-critical)
- API hooks: 80%
- Other components: 60%

## Implementation Tasks

1. **Project Setup** - Vite + React + TypeScript + Tailwind
2. **API Client** - Axios instance, endpoint functions
3. **Types** - TypeScript interfaces for API responses
4. **useFreshness Hook** - Manual freshness calculation
5. **ConfirmModal** - Reusable confirmation dialog
6. **FreshnessIndicator** - 🟢🟡🔴 with age display
7. **ErrorBanner** - Connection error with failure count
8. **TradingStateBadge** - State display in header
9. **Header** - Logo + State Badge + Kill Switch
10. **AccountSummary** - Equity/Cash/P&L cards
11. **PositionsTable** - Positions with Close buttons (state-aware)
12. **AlertsPanel** - Reconciliation alerts display
13. **App Integration** - Wire up all components
14. **Backend API** - Add/enhance endpoints (state, kill-switch, close)
15. **Testing** - Component and hook tests

## Future Considerations (Phase 2+)

- WebSocket for real-time updates
- Multi-page routing (strategies, orders, settings)
- Strategy pause/resume controls
- Dark mode toggle
- Mobile responsive design
- Audit log for state changes
