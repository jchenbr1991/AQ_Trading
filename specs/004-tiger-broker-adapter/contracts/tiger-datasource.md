# Contract: TigerDataSource

**Implements**: `DataSource` protocol (backend/src/market_data/sources/base.py)

**File**: `backend/src/market_data/sources/tiger.py`

## Constructor

```python
class TigerDataSource:
    def __init__(
        self,
        credentials_path: str,
        account_id: str,
        symbols: list[str],
        env: str = "PROD",
        max_symbols: int = 50,
    ) -> None:
```

**Preconditions**:
- `credentials_path` points to existing file with 0600 permissions
- `account_id` is non-empty string
- `symbols` is non-empty list
- `env` is "PROD" or "SANDBOX"

## DataSource Protocol Methods

### start

```python
async def start(self) -> None:
```

**Behavior**:
1. Capture current event loop reference (`asyncio.get_running_loop()`)
2. Create `TigerOpenClientConfig(props_path=credentials_path)`
3. Instantiate `PushClient` with protobuf enabled
4. Register `quote_changed` callback
5. Register `connect_callback`, `disconnect_callback`
6. Connect PushClient
7. Subscribe to quotes: `push_client.subscribe_quote(symbols[:max_symbols])`
8. If `len(symbols) > max_symbols`, log warning with skipped symbols

### stop

```python
async def stop(self) -> None:
```

**Behavior**:
1. Unsubscribe from quotes
2. Disconnect PushClient
3. Set `_connected = False`

### subscribe

```python
async def subscribe(self, symbols: list[str]) -> None:
```

**Behavior**: Idempotent. Adds new symbols to subscription.
1. Filter out already-subscribed symbols
2. Check total count against `max_symbols`
3. Call `push_client.subscribe_quote(new_symbols)` if any

### quotes

```python
def quotes(self) -> AsyncIterator[MarketData]:
```

**Output**: Async iterator yielding `MarketData` events from the
internal `_quote_queue`.

**Implementation**: Returns an async generator that reads from
`_quote_queue` indefinitely until `stop()` is called.

## Quote Callback Processing

When Tiger's `quote_changed(symbol, items, hour_trading)` fires:

1. Extract price, bid, ask, volume, timestamp from `items`
2. **Deduplication**: Check `_last_timestamps[symbol]`. If new timestamp
   is <= last seen, discard (out-of-order/duplicate)
3. Create `MarketData(symbol, price, bid, ask, volume, timestamp)`
4. Enqueue via `loop.call_soon_threadsafe(queue.put_nowait, market_data)`
5. Update `_last_timestamps[symbol]`

## Reconnection

On `disconnect_callback`:
1. Log warning
2. Set `_connected = False`
3. Attempt reconnect with exponential backoff (1s, 2s, 4s)
4. On success: re-subscribe to all symbols
5. On failure after max retries: log error, remain disconnected

## Field Mapping

Tiger `quote_changed` items → `MarketData`:

| Tiger Field | MarketData Field | Notes |
|-------------|-----------------|-------|
| `latest_price` | `price` | Convert to Decimal |
| `bid_price` | `bid` | Convert to Decimal |
| `ask_price` | `ask` | Convert to Decimal |
| `volume` | `volume` | Integer |
| `timestamp` | `timestamp` | Convert from ms epoch to datetime |

If any required field is missing from the callback data, skip the quote
entirely and log a warning (do not fabricate data).
