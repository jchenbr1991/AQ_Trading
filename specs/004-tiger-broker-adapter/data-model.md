# Data Model: Tiger Trading Broker Adapter

**Date**: 2026-02-05
**Source**: spec.md (Key Entities), research.md

## Entities

### TigerBroker

Adapter translating AQ Trading's `Broker` and `BrokerQuery` protocols to
Tiger Trading's API.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `_client_config` | `TigerOpenClientConfig` | Tiger SDK connection config |
| `_trade_client` | `TradeClient \| None` | Tiger trade API client |
| `_push_client` | `PushClient \| None` | Tiger push/streaming client |
| `_account_id` | `str` | Tiger trading account ID |
| `_connected` | `bool` | Connection state flag |
| `_fill_callback` | `Callable[[OrderFill], None] \| None` | Registered fill handler |
| `_fill_queue` | `asyncio.Queue[OrderFill]` | Thread-safe bridge for fills |
| `_loop` | `asyncio.AbstractEventLoop` | Event loop reference for thread bridging |
| `_pending_orders` | `dict[str, str]` | Map: Tiger order ID → AQ order ID |

**Relationships**:
- Implements `Broker` protocol (base.py)
- Implements `BrokerQuery` protocol (query.py)
- Wrapped by `LiveBroker` (decorator)
- Created by `load_broker()` factory (config.py)

**Lifecycle**: `connect()` → operational → `disconnect()`

### TigerDataSource

Adapter translating Tiger's real-time quote feed into the `DataSource`
protocol.

**Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `_client_config` | `TigerOpenClientConfig` | Tiger SDK connection config |
| `_push_client` | `PushClient \| None` | Tiger push client for quotes |
| `_account_id` | `str` | Tiger account ID |
| `_symbols` | `list[str]` | Subscribed symbol list |
| `_quote_queue` | `asyncio.Queue[MarketData]` | Thread-safe bridge for quotes |
| `_loop` | `asyncio.AbstractEventLoop` | Event loop reference |
| `_connected` | `bool` | Connection state flag |
| `_last_timestamps` | `dict[str, datetime]` | Per-symbol dedup tracker |
| `_max_symbols` | `int` | Subscription limit (default: 50) |

**Relationships**:
- Implements `DataSource` protocol (sources/base.py)
- Injected into `MarketDataService`
- Shares Tiger credentials with `TigerBroker`

**Lifecycle**: `start()` → streaming → `stop()`

### BrokerConfig (Extended)

Extended configuration dataclass with Tiger-specific settings.

**New fields** (added to existing dataclass):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tiger_credentials_path` | `str` | `""` | Path to tiger_openapi_config.properties |
| `tiger_account_id` | `str` | `""` | Tiger trading account ID |
| `tiger_env` | `str` | `"PROD"` | Tiger environment (PROD or SANDBOX) |
| `tiger_max_reconnect_attempts` | `int` | `3` | Max reconnection attempts |

**YAML mapping**:
```yaml
broker:
  type: "tiger"
  tiger:
    credentials_path: "config/brokers/tiger_openapi_config.properties"
    account_id: "21552525095632360"
    env: "PROD"
    max_reconnect_attempts: 3
```

### Order Status Mapping

Static mapping layer — no new dataclass needed, implemented as a
dict constant in `tiger_broker.py`.

```python
TIGER_STATUS_MAP: dict[str, OrderStatus] = {
    "PendingNew": OrderStatus.PENDING,
    "Initial": OrderStatus.SUBMITTED,
    "Submitted": OrderStatus.SUBMITTED,
    "PartiallyFilled": OrderStatus.PARTIAL_FILL,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "PendingCancel": OrderStatus.PENDING,
    "Inactive": OrderStatus.REJECTED,
    "Invalid": OrderStatus.EXPIRED,
}
```

> **Note on PendingCancel**: Tiger's `PendingCancel` maps to `PENDING` (not
> `CANCEL_REQUESTED`) because FR-004 restricts the mapping target to the
> seven statuses listed: PENDING, SUBMITTED, PARTIAL_FILL, FILLED,
> CANCELLED, REJECTED, EXPIRED. The cancel-in-flight state is best
> represented as PENDING until Tiger confirms the cancellation.

Unmapped statuses default to `OrderStatus.PENDING` with a warning log
(per spec edge case: "unmapped statuses should be logged and treated as PENDING").

### RiskLimits (Unchanged)

Existing dataclass in `live_broker.py`. No changes needed.
Used by LiveBroker when wrapping TigerBroker.

## State Transitions

### TigerBroker Connection State

```
DISCONNECTED → connect() → CONNECTED → disconnect() → DISCONNECTED
                               ↓ (connection loss)
                          RECONNECTING → (success) → CONNECTED
                               ↓ (max retries)
                          DISCONNECTED (log error)
```

### Order Lifecycle (Tiger-specific)

```
submit_order(order) → TradeClient.place_order()
    → Success: store tiger_order_id, return it
    → Failure: raise OrderSubmissionError

PushClient callback: order_changed
    → Map Tiger status to OrderStatus
    → Update internal tracking

PushClient callback: transaction_changed
    → Create OrderFill from execution data
    → Enqueue to fill_queue
    → Fill pump task delivers to registered callback
```

## Validation Rules

1. `tiger_credentials_path` MUST point to an existing file with 0600 permissions
2. `tiger_account_id` MUST be non-empty
3. `tiger_env` MUST be "PROD" or "SANDBOX"
4. Order `quantity` MUST be > 0
5. Limit orders MUST have `limit_price` set
6. `fill_id` (from Tiger's `execution_id`) MUST be unique per fill
