# Basic Dashboard Design

Phase 1 MVP dashboard for monitoring and emergency controls.

## Overview

Single-page React application that displays portfolio state and provides emergency controls. REST-only (no WebSocket in Phase 1).

**Key Decisions:**
- Scope: Minimal MVP (single page, not multi-page)
- Data: TanStack Query polling every 5 seconds
- Safety: Confirmation modals for all destructive actions
- Freshness: Visual indicators for data staleness
- Alerts: Reconciliation discrepancies displayed for operator awareness

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
│  AQ Trading Dashboard                    [Kill Switch]│
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

## Safety Controls

### Double-Tap Confirmation Pattern

All destructive actions require a confirmation modal:

```
┌─────────────────────────────────────────┐
│  ⚠️  Confirm Kill Switch               │
├─────────────────────────────────────────┤
│                                         │
│  This will:                             │
│  • Close ALL open positions             │
│  • Cancel ALL pending orders            │
│  • Halt ALL trading                     │
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

## Data Freshness & Error States

### Last Updated Indicator

Every data section shows when it was last successfully fetched.

### Staleness States

| State | Indicator | Condition |
|-------|-----------|-----------|
| Live | 🟢 Green | Updated < 10s ago |
| Stale | 🟡 Yellow | Updated 10-30s ago |
| Error | 🔴 Red | Fetch failed or > 30s |

### Error Banner

```
┌─────────────────────────────────────────────────────┐
│ ⚠️  Connection Error                    [Retry Now] │
│ Failed to fetch data. Last successful: 10:30:12    │
└─────────────────────────────────────────────────────┘
```

### TanStack Query Integration

```typescript
const { data, dataUpdatedAt, isError, isStale, refetch } = useQuery({
  queryKey: ['positions'],
  queryFn: fetchPositions,
  refetchInterval: 5000,
  staleTime: 10000,
});
```

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
| `/api/risk/kill-switch` | POST | Trigger kill switch | ✅ Exists |
| `/api/orders` | POST | Submit close order | ✅ Exists |
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
    │   │   ├── AccountSummary.tsx
    │   │   ├── PositionsTable.tsx
    │   │   ├── AlertsPanel.tsx
    │   │   ├── ConfirmModal.tsx
    │   │   ├── StatusIndicator.tsx
    │   │   └── ErrorBanner.tsx
    │   │
    │   ├── hooks/
    │   │   ├── useAccount.ts
    │   │   ├── usePositions.ts
    │   │   └── useAlerts.ts
    │   │
    │   └── types/
    │       └── index.ts
    │
    └── tests/
        └── components/
            └── ConfirmModal.test.tsx
```

## Testing Strategy

| Category | Tool | Focus |
|----------|------|-------|
| Component | Vitest + React Testing Library | UI rendering, user interactions |
| API Mocking | MSW (Mock Service Worker) | API response handling |
| E2E (Phase 2) | Playwright | Full flow testing |

**Key Test Cases:**

- ConfirmModal: confirm/cancel behavior, escape key, severity styling
- PositionsTable: rendering, close button, P&L colors
- usePositions: fetch on mount, refetch interval, error states

**MVP Test Coverage Target:**
- ConfirmModal: 100% (safety-critical)
- API hooks: 80%
- Other components: 60%

## Implementation Tasks

1. **Project Setup** - Vite + React + TypeScript + Tailwind
2. **API Client** - Axios instance, endpoint functions
3. **Types** - TypeScript interfaces for API responses
4. **ConfirmModal** - Reusable confirmation dialog
5. **StatusIndicator** - Freshness indicator component
6. **ErrorBanner** - Connection error display
7. **Header** - Logo + Kill Switch button
8. **AccountSummary** - Equity/Cash/P&L cards
9. **PositionsTable** - Positions with Close buttons
10. **AlertsPanel** - Reconciliation alerts display
11. **App Integration** - Wire up all components
12. **Backend API** - Add missing endpoints
13. **Testing** - Component and hook tests

## Future Considerations (Phase 2+)

- WebSocket for real-time updates
- Multi-page routing (strategies, orders, settings)
- Strategy pause/resume controls
- Dark mode toggle
- Mobile responsive design
