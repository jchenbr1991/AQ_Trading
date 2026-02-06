# Research: Tiger Trading Broker Adapter

**Date**: 2026-02-05
**Status**: Complete

## R1: Tiger SDK Package and Compatibility

**Decision**: Use `tigeropen` v3.3.3 from PyPI.

**Rationale**: Official Tiger Trading Python SDK, supports Python 3.11+,
actively maintained (last release Oct 2025). No alternative SDK exists.

**Alternatives**: None. Raw HTTP API would require reimplementing auth,
order creation, push protocol — high effort, no benefit.

## R2: Async Integration Strategy

**Decision**: Wrap synchronous `TradeClient`/`QuoteClient` calls with
`asyncio.to_thread()`. Bridge `PushClient` callbacks into asyncio via
`loop.call_soon_threadsafe()` feeding an `asyncio.Queue`.

**Rationale**: The `tigeropen` SDK is entirely synchronous. `TradeClient`
methods (place_order, cancel_order, get_order, get_positions, get_assets)
are blocking HTTP calls. `PushClient` is event-driven with callbacks
invoked from an internal thread.

- `asyncio.to_thread()` (Python 3.9+) is the simplest wrapper for
  blocking calls — no thread pool management needed.
- `PushClient` callbacks arrive on Tiger's internal thread. Using
  `loop.call_soon_threadsafe(queue.put_nowait, item)` bridges to the
  asyncio event loop safely.

**Alternatives considered**:
- `loop.run_in_executor(ThreadPoolExecutor, ...)`: More control but
  unnecessary complexity for our use case. `to_thread` uses the default
  executor internally.
- Native async rewrite of SDK: Impractical, maintenance burden.

## R3: Order Status Mapping

**Decision**: Explicit static mapping from Tiger's `OrderStatus` enum to
AQ Trading's `OrderStatus` enum.

| Tiger Status | Tiger String | AQ OrderStatus |
|-------------|-------------|----------------|
| `PENDING_NEW` | 'PendingNew' | `PENDING` |
| `NEW` | 'Initial' | `SUBMITTED` |
| `HELD` | 'Submitted' | `SUBMITTED` |
| `PARTIALLY_FILLED` | 'PartiallyFilled' | `PARTIAL_FILL` |
| `FILLED` | 'Filled' | `FILLED` |
| `CANCELLED` | 'Cancelled' | `CANCELLED` |
| `PENDING_CANCEL` | 'PendingCancel' | `PENDING` |
| `REJECTED` | 'Inactive' | `REJECTED` |
| `EXPIRED` | 'Invalid' | `EXPIRED` |
| (unmapped) | (any other) | `PENDING` (log warning, per spec edge case) |

**Rationale**: Tiger's `Order.status` property has smart logic (e.g.,
returns `FILLED` if remaining==0 and filled>0). Our mapping respects this.
The `HELD` status maps to `SUBMITTED` because it means the order is active
on the exchange. `PENDING_CANCEL` maps to `PENDING` per FR-004's defined
status set — the cancel-in-flight state is treated as pending until Tiger
confirms the cancellation.

## R4: Fill Notification Mechanism

**Decision**: Use `PushClient.subscribe_transaction` with
`transaction_changed` callback for real-time fill notifications.

**Rationale**: `PushClient` provides real-time `OrderTransactionData`
events with `execution_id` (unique fill identifier), `order_id`, symbol,
fill price, fill quantity, and timestamp. This maps directly to our
`OrderFill` dataclass.

The `execution_id` field serves as our `fill_id` for idempotency.

**Edge case**: If PushClient disconnects, fills during the gap could be
missed. The spec does not require fill recovery polling — this is noted
as a potential future enhancement. Initial implementation relies on
PushClient reconnection and the existing reconnection mechanism.

## R5: Thread Safety for Callbacks

**Decision**: All `PushClient` callbacks (fills, quotes, order status)
will enqueue items onto thread-safe `asyncio.Queue` instances via
`loop.call_soon_threadsafe()`. No shared mutable state between the
Tiger callback thread and the asyncio event loop.

**Rationale**: `PushClient` callbacks execute on Tiger's internal thread.
Direct mutation of asyncio-managed state from this thread would cause
race conditions. The queue-based bridge is a well-established pattern.

## R6: Connection Lifecycle

**Decision**: TigerBroker manages connection lifecycle with:
1. `connect()`: Create `TigerOpenClientConfig`, instantiate `TradeClient`
   and `PushClient`, connect PushClient, subscribe to order/transaction
   updates.
2. `disconnect()`: Unsubscribe, disconnect PushClient.
3. Reconnection: `PushClient` has `disconnect_callback` — on disconnect,
   log warning and attempt reconnect with exponential backoff (3 attempts).

**Rationale**: Tiger SDK's `PushClient` supports connection lifecycle
callbacks (`connect_callback`, `disconnect_callback`, `error_callback`).
We use these to detect connection loss and trigger reconnection.

## R7: Credential Security

**Decision**: Credentials loaded from `tiger_openapi_config.properties`
file. Path specified in strategy YAML config (`broker.tiger.credentials_path`).
File MUST have 0600 permissions (checked at startup). Credential content
MUST NOT appear in logs or error messages.

**Rationale**: Tiger SDK supports loading credentials from properties file
via `TigerOpenClientConfig(props_path=...)`. This is the standard Tiger
approach and avoids any credential parsing in our code.

**Implementation**:
- Check file permissions at startup, warn/error if not 0600.
- Wrap all Tiger API calls in try/except that sanitizes error messages
  (strip any credential content before re-raising).
- `config/brokers/` is already in `.gitignore`.

## R8: Rate Limiting Strategy

**Decision**: Implement client-side rate limiting using a simple
token-bucket per tier. Log warnings when approaching limits. On rate
limit errors from Tiger, retry with exponential backoff up to 3 times
before raising the error (per spec edge case requirement).

**Rationale**: Tiger's rate limits are generous for our use case
(120 orders/min, 60 queries/min). An initial trading system with
a single account is unlikely to hit these limits. Client-side
tracking with warnings provides observability. The retry-with-backoff
approach (spec requirement) handles transient rate limit responses
gracefully without adding excessive complexity.

## R9: Market Data Integration

**Decision**: `TigerDataSource` uses `PushClient.subscribe_quote()`
for real-time Level 1 quotes. Quote callbacks are bridged to an
`AsyncIterator[MarketData]` via `asyncio.Queue`.

**Rationale**: `PushClient` provides real-time quote streaming via
protobuf (since v3.0.0). The `quote_changed` callback receives
symbol, price data, and bid/ask. This maps to our `MarketData`
dataclass (symbol, price, bid, ask, volume, timestamp).

**Symbol limits**: Tiger may impose subscription limits per account
tier. TigerDataSource will log a warning if the symbol count exceeds
a configurable max (default: 50). It will subscribe to as many as
permitted and log which symbols were skipped.

**Deduplication**: Quote callbacks may deliver duplicate or
out-of-order data. TigerDataSource will track the latest timestamp
per symbol and discard quotes with timestamps older than the last
seen.

## R10: MarketDataService Source Selection

**Decision**: Modify `MarketDataService.__init__()` to accept a
`DataSource` instance instead of hardcoding `MockDataSource`.
The caller (strategy engine or app startup) selects the source
based on config (`market_data.source: "tiger" | "mock"`).

**Rationale**: Currently `MarketDataService` hardcodes
`self._source = MockDataSource(config)`. To support Tiger (and future
sources), the service should accept any `DataSource` implementation
via dependency injection. This is a minimal change — replace the
hardcoded constructor call with a parameter.

## R11: LiveBroker Decorator Refactor (FR-007)

**Decision**: Refactor `LiveBroker` to accept an `inner_broker: Broker`
parameter. The inner broker handles actual execution; LiveBroker adds
risk validation, confirmation checks, and connection management on top.

**Rationale**: Current LiveBroker has `broker_type` string parameter
and stub implementation. FR-007 requires it to wrap any Broker
implementation. The decorator pattern is already implied by the
existing architecture — LiveBroker validates, then delegates to the
inner broker.

**Breaking change**: `LiveBroker.__init__()` signature changes from
`broker_type: str` to `inner_broker: Broker`. All existing tests
and call sites must be updated. This is approved in the spec.
