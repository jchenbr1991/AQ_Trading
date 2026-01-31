# Data Model: AQ Trading

**Branch**: `001-product-overview` | **Date**: 2026-01-31

## Overview

This document defines the data model for the AQ Trading system. The models are organized by domain:

1. **Core Trading** - Accounts, Positions, Orders, Transactions
2. **Strategy** - Strategy, Signal, Context, MarketData
3. **Risk** - Greeks, Alerts, Limits
4. **Analytics** - Traces, Backtest Results

---

## 1. Core Trading Entities

### Account

Represents a trading account with a broker.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | int | PK, auto | Internal ID |
| account_id | string(50) | unique, indexed | Broker account identifier |
| broker | string(20) | default="futu" | Broker name |
| currency | string(10) | default="USD" | Base currency |
| cash | decimal(18,4) | default=0 | Available cash |
| buying_power | decimal(18,4) | default=0 | Margin buying power |
| margin_used | decimal(18,4) | default=0 | Margin in use |
| total_equity | decimal(18,4) | default=0 | Total account value |
| created_at | datetime | auto | Creation timestamp |
| updated_at | datetime | auto | Last update timestamp |
| synced_at | datetime | nullable | Last broker sync |

**Relationships**: One-to-many with Position, Order, Transaction

---

### Position

Represents a held position in a security.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | int | PK, auto | Internal ID |
| account_id | string(50) | FK, indexed | Account reference |
| symbol | string(50) | indexed | Security symbol |
| asset_type | enum | STOCK/OPTION/FUTURE | Asset class |
| strategy_id | string(50) | nullable, indexed | Owning strategy (null=manual) |
| status | enum | OPEN/CLOSING/CLOSED/etc | Position lifecycle state |
| quantity | int | default=0 | Number of units |
| avg_cost | decimal(18,4) | default=0 | Average cost basis |
| current_price | decimal(18,4) | default=0 | Current market price |
| strike | decimal(18,4) | nullable | Option strike price |
| expiry | date | nullable | Option/future expiration |
| put_call | enum | PUT/CALL/null | Option type |
| opened_at | datetime | auto | Position open time |
| updated_at | datetime | auto | Last update time |
| active_close_request_id | uuid | nullable | Active close request |
| closed_at | datetime | nullable | Position close time |

**Computed Properties**:
- `market_value`: quantity × current_price × multiplier (100 for options)
- `unrealized_pnl`: (current_price - avg_cost) × quantity × multiplier

**Status States**:
- `OPEN` - Position is active
- `CLOSING` - Close order submitted
- `CLOSED` - Position fully closed
- `CLOSE_RETRYABLE` - Close failed, can retry
- `CLOSE_FAILED` - Close permanently failed

---

### OrderRecord

Persistent record of an order.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | int | PK, auto | Internal ID |
| order_id | string(50) | unique, indexed | Internal order identifier |
| broker_order_id | string(50) | nullable, indexed | Broker's order ID |
| account_id | string(50) | FK, indexed | Account reference |
| strategy_id | string(50) | indexed | Strategy that created order |
| symbol | string(50) | indexed | Security symbol |
| side | enum | BUY/SELL | Order direction |
| quantity | int | required | Order quantity |
| order_type | enum | MARKET/LIMIT | Order type |
| limit_price | decimal(18,4) | nullable | Limit price if applicable |
| status | enum | see below | Order lifecycle status |
| filled_qty | int | default=0 | Quantity filled so far |
| avg_fill_price | decimal(18,4) | nullable | Average fill price |
| error_message | text | nullable | Error details if failed |
| created_at | datetime | auto | Order creation time |
| updated_at | datetime | auto | Last status update |
| close_request_id | uuid | nullable | Associated close request |
| broker_update_seq | bigint | nullable | Broker sequence number |
| last_broker_update_at | datetime | nullable | Last broker update time |
| reconcile_not_found_count | int | default=0 | Reconciliation retries |

**Order Status Lifecycle**:
```
PENDING → SUBMITTED → [PARTIAL_FILL →] FILLED
                    → CANCELLED
                    → REJECTED
                    → EXPIRED
                    → CANCEL_REQUESTED → CANCELLED
```

**Computed Properties**:
- `is_terminal`: status in (FILLED, CANCELLED, REJECTED, EXPIRED)
- `is_active`: not is_terminal

---

### Transaction

Record of executed trade or account event.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | int | PK, auto | Internal ID |
| account_id | string(50) | FK, indexed | Account reference |
| symbol | string(50) | indexed | Security symbol |
| action | enum | BUY/SELL/DIVIDEND/FEE/INTEREST/TRANSFER | Transaction type |
| quantity | int | default=0 | Units transacted |
| price | decimal(18,4) | default=0 | Transaction price |
| commission | decimal(18,4) | default=0 | Broker commission |
| realized_pnl | decimal(18,4) | default=0 | Realized profit/loss |
| strategy_id | string(50) | nullable, indexed | Owning strategy |
| order_id | string(50) | nullable, indexed | Source order |
| broker_order_id | string(50) | nullable | Broker order reference |
| executed_at | datetime | indexed | Execution timestamp |
| created_at | datetime | auto | Record creation time |

**Computed Properties**:
- `total_value`: quantity × price

---

## 2. Strategy Entities

### Signal (In-Memory)

Trading intent emitted by a strategy.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| strategy_id | string | required | Source strategy |
| symbol | string | required | Target symbol |
| action | enum | buy/sell | Direction |
| quantity | int | required | Desired quantity |
| order_type | enum | market/limit | Order type preference |
| limit_price | decimal | nullable | Limit price if applicable |
| reason | string | default="" | Human-readable rationale |
| timestamp | datetime | auto | Signal generation time |

**Note**: Signals are in-memory only. They become Orders after Risk Manager approval.

---

### MarketData (In-Memory)

Real-time price data.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| symbol | string | required | Security symbol |
| price | decimal | required | Last trade price |
| bid | decimal | required | Best bid price |
| ask | decimal | required | Best ask price |
| volume | int | required | Session volume |
| timestamp | datetime | required | Quote timestamp |

---

### OrderFill (In-Memory)

Order execution notification.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| fill_id | string | required, unique | Broker's trade ID (idempotency key) |
| order_id | string | required | Broker's order ID |
| symbol | string | required | Security symbol |
| side | enum | buy/sell | Fill direction |
| quantity | int | required | Filled quantity |
| price | decimal | required | Fill price |
| timestamp | datetime | required | Fill timestamp |

---

### StrategyContext (In-Memory)

Read-only portfolio view for a strategy.

| Property | Type | Description |
|----------|------|-------------|
| strategy_id | string | Strategy identifier |
| account_id | string | Account identifier |
| get_quote(symbol) | MarketData | Get cached quote |
| get_position(symbol) | Position | Get strategy's position |
| get_my_positions() | list[Position] | All strategy positions |
| get_my_pnl() | decimal | Strategy unrealized P&L |

---

## 3. Risk Entities

### GreeksSnapshot

Point-in-time Greeks aggregation.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | int | PK, auto | Internal ID |
| scope | string(20) | required | ACCOUNT or STRATEGY |
| scope_id | string(50) | required | Account/strategy identifier |
| strategy_id | string(50) | nullable | Strategy if scope=STRATEGY |
| dollar_delta | decimal(18,4) | default=0 | Dollar delta exposure |
| gamma_dollar | decimal(18,4) | default=0 | Dollar gamma |
| gamma_pnl_1pct | decimal(18,4) | default=0 | P&L impact of 1% move |
| vega_per_1pct | decimal(18,4) | default=0 | Vega per 1% IV change |
| theta_per_day | decimal(18,4) | default=0 | Daily theta decay |
| valid_legs_count | int | default=0 | Positions with valid Greeks |
| total_legs_count | int | default=0 | Total option positions |
| valid_notional | decimal(18,4) | default=0 | Notional of valid positions |
| total_notional | decimal(18,4) | default=0 | Total notional |
| coverage_pct | decimal(5,2) | default=100 | % of portfolio with Greeks |
| has_high_risk_missing_legs | bool | default=false | Missing critical Greeks |
| as_of_ts | datetime(tz) | required | Snapshot point in time |
| created_at | datetime(tz) | auto | Record creation time |

---

### GreeksAlertRecord

Greeks-related alert record.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | int | PK, auto | Internal ID |
| alert_id | uuid | unique | Alert identifier |
| alert_type | string(20) | required | THRESHOLD or ROC |
| scope | string(20) | required | ACCOUNT or STRATEGY |
| scope_id | string(50) | required | Account/strategy identifier |
| metric | string(30) | required | Risk metric name |
| level | string(10) | required | WARN/CRIT/HARD |
| current_value | decimal(18,4) | required | Value that triggered alert |
| threshold_value | decimal(18,4) | nullable | Threshold crossed |
| prev_value | decimal(18,4) | nullable | Previous value (ROC alerts) |
| change_pct | decimal(8,4) | nullable | Rate of change % |
| message | text | required | Alert message |
| created_at | datetime(tz) | auto | Alert creation time |
| acknowledged_at | datetime(tz) | nullable | Acknowledgment time |
| acknowledged_by | string(100) | nullable | User who acknowledged |

**Computed Properties**:
- `is_acknowledged`: acknowledged_at is not null

---

## 4. Entity Relationships

```
                                ┌──────────────┐
                                │   Account    │
                                └──────┬───────┘
                                       │
             ┌─────────────┬───────────┼───────────┬─────────────┐
             │             │           │           │             │
             ▼             ▼           ▼           ▼             ▼
      ┌──────────┐  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
      │ Position │  │  Order   │ │Transaction│ │  Greeks  │ │  Greeks  │
      │          │  │  Record  │ │          │ │ Snapshot │ │  Alert   │
      └────┬─────┘  └────┬─────┘ └──────────┘ └──────────┘ └──────────┘
           │             │
           │             │ strategy_id
           └─────────────┴────────────────┐
                                          │
                         ┌────────────────┼────────────────┐
                         │                │                │
                         ▼                ▼                ▼
                   ┌──────────┐    ┌──────────┐    ┌──────────┐
                   │ Strategy │◄───│  Signal  │───►│MarketData│
                   │(runtime) │    │(runtime) │    │(runtime) │
                   └──────────┘    └──────────┘    └──────────┘
```

---

## 5. State Transitions

### Position Status

```
                    ┌─────────────────────────────────────┐
                    │                                     │
                    ▼                                     │
               ┌────────┐                                 │
    ────────►  │  OPEN  │ ◄───────────────────────────────┤
               └────┬───┘                                 │
                    │ close_requested                     │
                    ▼                                     │
               ┌─────────┐                                │
               │ CLOSING │                                │
               └────┬────┘                                │
                    │                                     │
         ┌──────────┼──────────┐                          │
         │          │          │                          │
         ▼          ▼          ▼                          │
    ┌────────┐ ┌─────────────┐ ┌──────────────┐          │
    │ CLOSED │ │CLOSE_RETRY- │ │ CLOSE_FAILED │          │
    │        │ │   ABLE      │─┘              │          │
    └────────┘ └──────┬──────┘                └──────────┘
                      │ retry
                      └─────────────────────────────────┘
```

### Order Status

```
    ┌─────────┐
    │ PENDING │
    └────┬────┘
         │ submit_to_broker
         ▼
    ┌───────────┐
    │ SUBMITTED │
    └─────┬─────┘
          │
    ┌─────┴─────────────┬──────────────┬───────────────┐
    │                   │              │               │
    ▼                   ▼              ▼               ▼
┌─────────────┐    ┌────────┐    ┌──────────┐    ┌─────────┐
│PARTIAL_FILL │    │ FILLED │    │CANCELLED │    │REJECTED │
└──────┬──────┘    └────────┘    └──────────┘    └─────────┘
       │                              ▲
       │ final_fill                   │
       └──────────────┬───────────────┘
                      │ cancel_requested
                      ▼
                ┌───────────────┐
                │CANCEL_REQUESTED│
                └───────────────┘
```

---

## 6. Validation Rules

### Account
- `account_id` must be unique per broker
- `cash`, `buying_power`, `margin_used`, `total_equity` must be non-negative

### Position
- `quantity` must be non-negative
- `strike`, `expiry`, `put_call` required when `asset_type = OPTION`
- `expiry` required when `asset_type = FUTURE`
- `strategy_id` can be null (manual trades)

### Order
- `quantity` must be positive
- `limit_price` required when `order_type = LIMIT`
- `filled_qty <= quantity`

### Transaction
- `quantity` must be non-negative
- `price` must be non-negative
- `commission` must be non-negative

### Greeks
- `coverage_pct` must be between 0 and 100
- `valid_legs_count <= total_legs_count`

---

## 7. Phase 3 Entities (Planned)

### DerivativeContract (Planned)

For expiration tracking and lifecycle management.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| symbol | string | PK | Contract symbol |
| underlying | string | required | Underlying symbol |
| contract_type | enum | option/future | Derivative type |
| expiry | date | required | Expiration date |
| strike | decimal | nullable | Strike (options only) |
| put_call | enum | nullable | Put/call (options only) |

**Computed Properties**:
- `days_to_expiry`: expiry - today
- `is_expiring_soon`: days_to_expiry <= 5

### AgentResult (Planned)

Agent invocation results for the CLI Agent system.

| Field | Type | Constraints | Description |
|-------|------|-------------|-------------|
| id | uuid | PK | Result identifier |
| role | enum | required | researcher/analyst/risk_controller/ops |
| task | string | required | Task description |
| context | json | required | Input context |
| result | json | nullable | Agent output |
| success | bool | default=false | Success flag |
| error | text | nullable | Error message if failed |
| started_at | datetime | auto | Invocation start |
| completed_at | datetime | nullable | Completion time |
| duration_ms | int | nullable | Execution duration |

---

## 8. Index Strategy

### Primary Indexes
- All `id` fields have primary key index
- `account_id`, `order_id` fields have unique index where applicable

### Foreign Key Indexes
- `positions.account_id`
- `orders.account_id`
- `transactions.account_id`

### Query Pattern Indexes
- `positions.symbol` - Position lookup by symbol
- `positions.strategy_id` - Strategy isolation
- `positions.status` - Open position queries
- `orders.status` - Active order queries
- `orders.strategy_id` - Strategy order history
- `transactions.executed_at` - Time-range queries
- `greeks_snapshots.as_of_ts` - Historical Greeks
- `greeks_alerts.created_at` - Recent alerts

### TimescaleDB Hypertables
- `greeks_snapshots` - Partitioned by `as_of_ts`
- Time-series data optimized for range queries and compression
