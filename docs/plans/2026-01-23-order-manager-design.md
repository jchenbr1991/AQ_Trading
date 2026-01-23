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
│   └── test_fill_handling.py
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
PENDING → SUBMITTED → PARTIAL_FILL → FILLED
              │              │
              ├──────────────┴──→ CANCELLED
              │
              └──────────────────→ REJECTED
```

### Order Dataclass

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal


class OrderStatus(Enum):
    PENDING = "pending"        # Created, not yet submitted
    SUBMITTED = "submitted"    # Sent to broker
    PARTIAL_FILL = "partial"   # Some shares filled
    FILLED = "filled"          # Fully filled
    CANCELLED = "cancelled"    # Cancelled by user or system
    REJECTED = "rejected"      # Broker rejected


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
        """Register callback for fill notifications."""
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
```

### PaperBroker Implementation

```python
class PaperBroker:
    """Simulates order execution for paper trading."""

    def __init__(self, fill_delay: float = 0.1):
        self._fill_delay = fill_delay
        self._fill_callback = None
        self._order_counter = 0

    async def submit_order(self, order: Order) -> str:
        self._order_counter += 1
        broker_id = f"PAPER-{self._order_counter}"

        # Simulate fill after delay
        asyncio.create_task(self._simulate_fill(order, broker_id))

        return broker_id

    async def _simulate_fill(self, order: Order, broker_id: str):
        await asyncio.sleep(self._fill_delay)

        fill = OrderFill(
            order_id=broker_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.limit_price or self._get_market_price(order.symbol),
            timestamp=datetime.utcnow()
        )

        if self._fill_callback:
            self._fill_callback(fill)
```

## OrderManager Class

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

    async def start(self) -> None:
        """Start consuming signals from Redis queue."""
        self._broker.subscribe_fills(self._on_fill)
        asyncio.create_task(self._consume_signals())

    async def stop(self) -> None:
        """Stop the order manager gracefully."""
        # Cancel pending orders if configured
        # Persist active orders to DB

    async def _consume_signals(self) -> None:
        """Consume approved signals from Redis queue."""
        while True:
            _, signal_data = await self._redis.brpop("approved_signals")
            signal = Signal.from_json(signal_data)
            await self._process_signal(signal)

    async def _process_signal(self, signal: Signal) -> Order:
        """Convert signal to order and submit."""
        order = self._create_order(signal)
        self._active_orders[order.order_id] = order

        try:
            broker_id = await self._broker.submit_order(order)
            order.broker_order_id = broker_id
            order.status = OrderStatus.SUBMITTED
            self._broker_id_map[broker_id] = order.order_id
        except BrokerError as e:
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)
            await self._persist_order(order)
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

## Fill Handling

```python
class OrderManager:
    # ... continued

    async def _on_fill(self, fill: OrderFill) -> None:
        """Handle fill notification from broker."""
        order_id = self._broker_id_map.get(fill.order_id)
        if not order_id:
            logger.warning(f"Unknown broker order: {fill.order_id}")
            return

        order = self._active_orders.get(order_id)
        if not order:
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

        # 3. If fully filled, persist and cleanup
        if order.status == OrderStatus.FILLED:
            await self._persist_order(order)
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
        """Save completed order to database."""
        # Convert to SQLAlchemy model and save
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
    fill_delay: 0.1        # Seconds before simulated fill
    slippage_pct: 0.01     # 1% slippage simulation
```

## Testing Strategy

1. **test_models.py** - Order creation, status transitions
2. **test_manager.py** - Signal processing, order submission
3. **test_fill_handling.py** - Partial fills, average price calculation
4. **test_paper_broker.py** - Simulated execution
5. **test_futu_broker.py** - Integration tests (requires Futu gateway)
