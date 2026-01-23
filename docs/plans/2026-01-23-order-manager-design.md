# Order Manager Design

## Overview

The Order Manager receives approved signals from Risk Manager via Redis queue, converts them to orders, submits to broker, and handles fills. It uses a Broker abstraction to support both live (Futu) and paper trading modes.

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Broker integration | Abstract Broker interface | Enables paper trading, easier testing |
| Order state storage | Hybrid (in-memory + DB) | Fast active tracking, persistent history |
| Stop-loss orders | Deferred to Phase 2 | Keep Phase 1 focused on core flow |
| Partial fills | Per-fill callbacks | Accurate tracking, strategy can react |
| Signal delivery | Redis queue | Decoupled from Risk Manager |
| **Fill idempotency** | **Dedupe by fill_id** | **Prevent duplicate position updates** |
| **Callback model** | **Sync callback → async task** | **Futu SDK uses thread callbacks** |
| **Crash recovery** | **Persist PENDING before submit** | **No signal loss on crash** |

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Risk Manager   │────▶│   Redis Queue   │────▶│  Order Manager  │
│                 │     │ (approved_sigs) │     │                 │
│  approves       │     │                 │     │  consumes       │
│  signal         │     │                 │     │  submits order  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                        │
                                                        ▼
                                                ┌─────────────────┐
                                                │  Broker (ABC)   │
                                                │                 │
                                                │  FutuBroker     │
                                                │  PaperBroker    │
                                                └─────────────────┘
```

### File Structure

```
backend/src/
├── orders/
│   ├── __init__.py
│   ├── models.py          # Order, OrderStatus
│   ├── manager.py         # OrderManager class
│   └── errors.py          # BrokerError, OrderError
│
├── broker/
│   ├── __init__.py
│   ├── base.py            # Broker protocol
│   ├── futu_broker.py     # FutuBroker implementation
│   └── paper_broker.py    # PaperBroker implementation

backend/tests/
├── orders/
│   ├── test_models.py
│   ├── test_manager.py
│   ├── test_fill_handling.py
│   └── test_idempotency.py
│
├── broker/
│   ├── test_paper_broker.py
│   └── test_futu_broker.py

config/
└── broker.yaml
```

## Order Model

### Order States

```
PENDING ─────────────────────────────────────────────────────────┐
    │                                                            │
    ▼                                                            │
SUBMITTED → PARTIAL_FILL → FILLED                                │
    │            │                                               │
    ├────────────┴──→ CANCELLED ←── CANCEL_REQUESTED            │
    │                                                            │
    └──────────────→ REJECTED                                    │
                                                                 │
Phase 2: EXPIRED, UNKNOWN ◄──────────────────────────────────────┘
```

### Order Dataclass

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal


class OrderStatus(Enum):
    # Active states
    PENDING = "pending"              # Created, persisted, not yet submitted
    SUBMITTED = "submitted"          # Sent to broker, awaiting fill
    PARTIAL_FILL = "partial"         # Some shares filled
    CANCEL_REQUESTED = "cancel_req"  # Cancel sent, awaiting confirmation

    # Terminal states
    FILLED = "filled"                # Fully filled
    CANCELLED = "cancelled"          # Successfully cancelled
    REJECTED = "rejected"            # Broker rejected

    # Phase 2 placeholders
    EXPIRED = "expired"              # GTC/DAY order expired
    UNKNOWN = "unknown"              # State unknown after reconnect


@dataclass
class Order:
    order_id: str                    # Internal UUID
    broker_order_id: str | None      # Futu's order ID (after submission)
    strategy_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"]
    limit_price: Decimal | None
    status: OrderStatus
    filled_qty: int = 0
    avg_fill_price: Decimal | None = None
    created_at: datetime = None
    updated_at: datetime = None
    error_message: str | None = None
```

### OrderFill Dataclass (with idempotency)

```python
@dataclass
class OrderFill:
    """Individual fill event from broker."""
    fill_id: str                     # CRITICAL: Broker's unique trade ID for idempotency
    order_id: str                    # Broker's order ID
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    price: Decimal
    timestamp: datetime
```

**Why fill_id is critical:**
- Futu may send duplicate fill notifications
- Reconnection may replay historical fills
- Without deduplication: position doubles, P&L wrong, no error in logs

## Broker Protocol

```python
from typing import Protocol, Callable

class Broker(Protocol):
    """Abstract broker interface for order execution."""

    async def submit_order(self, order: Order) -> str:
        """
        Submit order to broker.
        Returns broker_order_id on success.
        Raises BrokerError on failure.
        """
        ...

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an open order. Returns True if successful."""
        ...

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Get current status of an order."""
        ...

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        """
        Register SYNCHRONOUS callback for fill notifications.

        IMPORTANT: Callback is sync because Futu SDK uses thread-based callbacks.
        OrderManager wraps this to dispatch to async event loop.
        """
        ...
```

### FutuBroker Implementation

```python
from futu import OpenSecTradeContext

class FutuBroker:
    def __init__(self, host: str, port: int, trade_env: str):
        self._context = OpenSecTradeContext(host, port)
        self._trade_env = trade_env  # REAL or SIMULATE
        self._fill_callback = None

    async def submit_order(self, order: Order) -> str:
        # Map Order to Futu's place_order parameters
        # Handle market vs limit order types
        # Return broker_order_id from response

    async def cancel_order(self, broker_order_id: str) -> bool:
        # Call Futu's modify_order with cancel action

    def subscribe_fills(self, callback):
        self._fill_callback = callback
        # Set up Futu's order update handler
        # Extract fill_id from Futu's trd_side + deal_id
```

### PaperBroker Implementation (Realistic)

```python
import random

class PaperBroker:
    """Simulates realistic order execution for paper trading."""

    def __init__(
        self,
        fill_delay_min: float = 0.05,
        fill_delay_max: float = 0.2,
        slippage_pct: float = 0.001,
        partial_fill_prob: float = 0.3,
        reject_prob: float = 0.02
    ):
        self._fill_delay_min = fill_delay_min
        self._fill_delay_max = fill_delay_max
        self._slippage_pct = slippage_pct
        self._partial_fill_prob = partial_fill_prob
        self._reject_prob = reject_prob
        self._fill_callback = None
        self._order_counter = 0
        self._fill_counter = 0

    async def submit_order(self, order: Order) -> str:
        # Random rejection simulation
        if random.random() < self._reject_prob:
            raise OrderSubmissionError("Simulated rejection: insufficient margin")

        self._order_counter += 1
        broker_id = f"PAPER-{self._order_counter:06d}"

        # Simulate fill(s) after random delay
        asyncio.create_task(self._simulate_fills(order, broker_id))

        return broker_id

    async def _simulate_fills(self, order: Order, broker_id: str) -> None:
        """Simulate realistic fills with partials and slippage."""
        remaining = order.quantity

        while remaining > 0:
            # Random delay with variance
            delay = random.uniform(self._fill_delay_min, self._fill_delay_max)
            await asyncio.sleep(delay)

            # Decide fill quantity (partial or full)
            if remaining > 10 and random.random() < self._partial_fill_prob:
                fill_qty = random.randint(1, remaining - 1)
            else:
                fill_qty = remaining

            # Apply slippage
            base_price = order.limit_price or self._default_price
            slippage = base_price * Decimal(str(self._slippage_pct))
            if order.side == "buy":
                fill_price = base_price + slippage * Decimal(str(random.uniform(0, 1)))
            else:
                fill_price = base_price - slippage * Decimal(str(random.uniform(0, 1)))

            # Generate unique fill_id
            self._fill_counter += 1
            fill = OrderFill(
                fill_id=f"PAPER-FILL-{self._fill_counter:08d}",
                order_id=broker_id,
                symbol=order.symbol,
                side=order.side,
                quantity=fill_qty,
                price=fill_price.quantize(Decimal("0.01")),
                timestamp=datetime.utcnow()
            )

            if self._fill_callback:
                self._fill_callback(fill)

            remaining -= fill_qty
```

## OrderManager Class

### Critical Design Points

1. **Persist PENDING before submit** - Prevents signal loss on crash
2. **Sync callback wrapper** - Bridges Futu's thread callback to asyncio
3. **Fill idempotency** - Deduplicates by fill_id

```python
class OrderManager:
    def __init__(
        self,
        broker: Broker,
        portfolio: PortfolioManager,
        redis: Redis,
        db_session: AsyncSession,
        account_id: str
    ):
        self._broker = broker
        self._portfolio = portfolio
        self._redis = redis
        self._db = db_session
        self._account_id = account_id
        self._active_orders: dict[str, Order] = {}  # order_id -> Order
        self._broker_id_map: dict[str, str] = {}    # broker_order_id -> order_id
        self._processed_fills: set[str] = set()     # fill_id set for idempotency
        self._running = False
        self._loop: asyncio.AbstractEventLoop = None

    async def start(self) -> None:
        """Start consuming signals from Redis queue."""
        self._loop = asyncio.get_running_loop()

        # CRITICAL: Use sync wrapper for broker callback
        self._broker.subscribe_fills(self._on_fill_sync)

        self._running = True
        asyncio.create_task(self._consume_signals())

    def _on_fill_sync(self, fill: OrderFill) -> None:
        """
        Sync callback for broker fills.

        IMPORTANT: Futu SDK calls this from a different thread.
        We must schedule the async handler on the event loop.
        """
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self._on_fill_async(fill),
                self._loop
            )

    async def stop(self) -> None:
        """Stop the order manager gracefully."""
        self._running = False
        # Persist active orders to DB for recovery

    async def _consume_signals(self) -> None:
        """Consume approved signals from Redis queue."""
        while self._running:
            try:
                result = await self._redis.brpop("approved_signals", timeout=1)
                if result:
                    _, signal_data = result
                    signal = Signal.from_json(signal_data)
                    await self._process_signal(signal)
            except Exception as e:
                logger.error(f"Error consuming signal: {e}")

    async def _process_signal(self, signal: Signal) -> Order:
        """Convert signal to order and submit."""
        order = self._create_order(signal)

        # CRITICAL: Persist as PENDING before submit
        # This prevents signal loss if we crash between pop and submit
        await self._persist_order(order)
        self._active_orders[order.order_id] = order

        try:
            broker_id = await self._broker.submit_order(order)
            order.broker_order_id = broker_id
            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.utcnow()
            self._broker_id_map[broker_id] = order.order_id
            await self._update_order_in_db(order)
        except BrokerError as e:
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)
            order.updated_at = datetime.utcnow()
            await self._update_order_in_db(order)
            del self._active_orders[order.order_id]

        return order

    def _create_order(self, signal: Signal) -> Order:
        """Convert Signal to Order."""
        return Order(
            order_id=str(uuid4()),
            broker_order_id=None,
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side=signal.action,
            quantity=signal.quantity,
            order_type=signal.order_type,
            limit_price=signal.limit_price,
            status=OrderStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
```

## Fill Handling (Idempotent)

```python
class OrderManager:
    # ... continued

    async def _on_fill_async(self, fill: OrderFill) -> None:
        """
        Handle fill notification from broker.

        CRITICAL: This method is idempotent via fill_id deduplication.
        """
        # IDEMPOTENCY CHECK - Must be first!
        if fill.fill_id in self._processed_fills:
            logger.debug(f"Duplicate fill ignored: {fill.fill_id}")
            return
        self._processed_fills.add(fill.fill_id)

        # Find corresponding order
        order_id = self._broker_id_map.get(fill.order_id)
        if not order_id:
            logger.warning(f"Unknown broker order: {fill.order_id}")
            return

        order = self._active_orders.get(order_id)
        if not order:
            logger.warning(f"Order not in active orders: {order_id}")
            return

        # Update order state
        order.filled_qty += fill.quantity
        order.avg_fill_price = self._calc_avg_price(order, fill)
        order.updated_at = datetime.utcnow()

        if order.filled_qty >= order.quantity:
            order.status = OrderStatus.FILLED
        else:
            order.status = OrderStatus.PARTIAL_FILL

        # 1. Update portfolio
        await self._portfolio.record_fill(
            account_id=self._account_id,
            symbol=order.symbol,
            side=order.side,
            quantity=fill.quantity,
            price=fill.price,
            strategy_id=order.strategy_id
        )

        # 2. Publish fill event for Strategy Engine
        await self._redis.publish("fills", fill.to_json())

        # 3. Update order in DB
        await self._update_order_in_db(order)

        # 4. If fully filled, cleanup active tracking
        if order.status == OrderStatus.FILLED:
            del self._active_orders[order.order_id]
            del self._broker_id_map[order.broker_order_id]

    def _calc_avg_price(self, order: Order, fill: OrderFill) -> Decimal:
        """Calculate volume-weighted average fill price."""
        prev_qty = order.filled_qty
        prev_avg = order.avg_fill_price or Decimal("0")

        total_qty = prev_qty + fill.quantity
        total_value = (prev_avg * prev_qty) + (fill.price * fill.quantity)

        return total_value / total_qty

    async def _persist_order(self, order: Order) -> None:
        """Save new order to database."""
        # Convert to SQLAlchemy model and INSERT

    async def _update_order_in_db(self, order: Order) -> None:
        """Update existing order in database."""
        # UPDATE order row with current state
```

## Configuration

**`config/broker.yaml`:**

```yaml
broker:
  type: "paper"  # "futu" or "paper"

  futu:
    host: "127.0.0.1"
    port: 11111
    trade_env: "SIMULATE"  # "REAL" or "SIMULATE"
    trade_password: ""     # Set via environment variable

  paper:
    fill_delay_min: 0.05     # Min seconds before fill
    fill_delay_max: 0.2      # Max seconds before fill
    slippage_pct: 0.001      # 0.1% slippage
    partial_fill_prob: 0.3   # 30% chance of partial fill
    reject_prob: 0.02        # 2% rejection rate
```

## Testing Strategy

1. **test_models.py** - Order creation, status transitions
2. **test_manager.py** - Signal processing, order submission
3. **test_fill_handling.py** - Partial fills, average price calculation
4. **test_idempotency.py** - Duplicate fill handling, fill_id deduplication
5. **test_paper_broker.py** - Simulated execution, partials, rejections
6. **test_futu_broker.py** - Integration tests (requires Futu gateway)

## Phase 2 Extensions

Based on code review feedback, these are planned for Phase 2:

1. **Order Recovery** - On restart, sync with broker to recover active order state
2. **Cancel/Replace** - Full cancel flow with CANCEL_REQUESTED state
3. **Redis Streams** - Replace BRPOP with consumer groups for at-least-once with ack
4. **Execution Metrics** - Slippage attribution, latency tracking
