# Contract: TigerBroker

**Implements**: `Broker` protocol (backend/src/broker/base.py),
`BrokerQuery` protocol (backend/src/broker/query.py)

**File**: `backend/src/broker/tiger_broker.py`

## Constructor

```python
class TigerBroker:
    def __init__(
        self,
        credentials_path: str,
        account_id: str,
        env: str = "PROD",
        max_reconnect_attempts: int = 3,
    ) -> None:
```

**Preconditions**:
- `credentials_path` points to existing file with 0600 permissions
- `account_id` is non-empty string
- `env` is "PROD" or "SANDBOX"

**Raises**: `ValueError` if preconditions not met.

## Broker Protocol Methods

### submit_order

```python
async def submit_order(self, order: Order) -> str:
```

**Input**: AQ Trading `Order` with symbol, side, quantity, order_type,
limit_price (if limit order).

**Output**: Tiger's order ID as string.

**Behavior**:
1. Create `stock_contract(symbol=order.symbol, currency='USD')`
2. Create Tiger order via `market_order()` or `limit_order()`
3. Call `await asyncio.to_thread(self._trade_client.place_order, tiger_order)`
4. Store mapping: tiger_order.id → order.order_id
5. Return `str(tiger_order.id)`

**Precondition**: `_connected` must be `True`. If disconnected, raise
`OrderSubmissionError("Not connected to Tiger")` without calling Tiger API
(per spec edge case: disconnect prevents new orders).

**Errors**: `OrderSubmissionError` if Tiger API fails or rate limit hit
after 3 retries.

### cancel_order

```python
async def cancel_order(self, broker_order_id: str) -> bool:
```

**Input**: Tiger order ID string.

**Output**: `True` if cancel succeeded.

**Behavior**:
1. Call `await asyncio.to_thread(self._trade_client.cancel_order, id=int(broker_order_id))`
2. Return `True`

**Errors**: `OrderCancelError` if Tiger API fails.

### get_order_status

```python
async def get_order_status(self, broker_order_id: str) -> OrderStatus:
```

**Input**: Tiger order ID string.

**Output**: Mapped `OrderStatus` enum value.

**Behavior**:
1. Call `await asyncio.to_thread(self._trade_client.get_order, id=int(broker_order_id))`
2. Map Tiger status string to AQ `OrderStatus` via `TIGER_STATUS_MAP`
3. Return mapped status (default `PENDING` for unmapped, with warning log per spec edge case)

### subscribe_fills

```python
def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
```

**Input**: Callback function receiving `OrderFill` events.

**Behavior**: Stores callback. When PushClient delivers transaction events,
they are converted to `OrderFill` and delivered via this callback.

## BrokerQuery Protocol Methods

### get_positions

```python
async def get_positions(self, account_id: str) -> list[BrokerPosition]:
```

**Output**: List of `BrokerPosition` from Tiger account.

**Mapping**:
- `symbol` ← Tiger position contract symbol
- `quantity` ← Tiger `position_qty`
- `avg_cost` ← Tiger `average_cost`
- `market_value` ← Tiger `market_value`
- `asset_type` ← `AssetType.STOCK` (stocks only for now)

### get_account

```python
async def get_account(self, account_id: str) -> BrokerAccount:
```

**Output**: `BrokerAccount` from Tiger assets.

**Mapping**:
- `account_id` ← config account ID
- `cash` ← Tiger `available_funds` (or similar)
- `buying_power` ← Tiger `buying_power`
- `total_equity` ← Tiger `net_liquidation`
- `margin_used` ← Tiger `margin` (if available, else Decimal("0"))

## Connection Management

### connect

```python
async def connect(self) -> None:
```

1. Create `TigerOpenClientConfig(props_path=credentials_path)`
2. Instantiate `TradeClient(client_config)`
3. Instantiate `PushClient(host, port, use_ssl=True)`
4. Register callbacks: `order_changed`, `transaction_changed`,
   `connect_callback`, `disconnect_callback`
5. Call `push_client.connect(tiger_id, private_key)`
6. Subscribe: `push_client.subscribe_order(account=account_id)`,
   `push_client.subscribe_transaction(account=account_id)`
7. Start fill pump background task

### disconnect

```python
async def disconnect(self) -> None:
```

1. Unsubscribe from PushClient
2. Disconnect PushClient
3. Cancel fill pump task
4. Set `_connected = False`

## Thread Safety

- `_fill_queue`: Standard `asyncio.Queue`, fed via
  `loop.call_soon_threadsafe(queue.put_nowait, fill)` from Tiger's
  callback thread.
- No shared mutable state between callback thread and asyncio.
- Fill pump task: `async for fill in queue: callback(fill)`.

## Edge Case Handling

- **Disconnect prevents orders**: `submit_order` checks `_connected`
  before calling Tiger API; raises `OrderSubmissionError` if disconnected.
- **Unknown fill**: If a fill notification arrives for an order not in
  `_pending_orders`, log a warning and do not crash (per spec edge case).
- **Rate limit retry**: All Tiger API calls retry with exponential backoff
  (1s, 2s, 4s) up to 3 times on rate limit errors before raising.
- **Unmapped order status**: Treated as `PENDING` with a warning log.
- **PendingCancel**: Mapped to `PENDING` per FR-004 status set (not
  `CANCEL_REQUESTED`) — cancel is pending until Tiger confirms.
