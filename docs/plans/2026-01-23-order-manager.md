# Order Manager Implementation Plan

**Created:** 2026-01-23
**Design:** [Order Manager Design](./2026-01-23-order-manager-design.md)
**Approach:** TDD (Test-Driven Development)

## Overview

Implement the Order Manager that receives approved signals from Redis queue, submits orders via Broker abstraction, and handles fills with per-fill callbacks.

## Tasks

### Task 1: Order and OrderStatus Models

**Goal:** Create the Order dataclass and OrderStatus enum.

**Test first (`backend/tests/orders/test_models.py`):**

```python
import pytest
from datetime import datetime
from decimal import Decimal

from src.orders.models import Order, OrderStatus


class TestOrderStatus:
    def test_all_statuses_exist(self):
        """All order statuses are defined."""
        # Active states
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.SUBMITTED.value == "submitted"
        assert OrderStatus.PARTIAL_FILL.value == "partial"
        assert OrderStatus.CANCEL_REQUESTED.value == "cancel_req"
        # Terminal states
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.CANCELLED.value == "cancelled"
        assert OrderStatus.REJECTED.value == "rejected"
        # Phase 2 placeholders
        assert OrderStatus.EXPIRED.value == "expired"
        assert OrderStatus.UNKNOWN.value == "unknown"


class TestOrder:
    def test_create_market_order(self):
        """Create a market order."""
        order = Order(
            order_id="ord-123",
            broker_order_id=None,
            strategy_id="momentum",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.PENDING
        )

        assert order.order_id == "ord-123"
        assert order.broker_order_id is None
        assert order.strategy_id == "momentum"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.quantity == 100
        assert order.order_type == "market"
        assert order.status == OrderStatus.PENDING
        assert order.filled_qty == 0

    def test_create_limit_order(self):
        """Create a limit order with price."""
        order = Order(
            order_id="ord-456",
            broker_order_id=None,
            strategy_id="mean_rev",
            symbol="GOOGL",
            side="sell",
            quantity=50,
            order_type="limit",
            limit_price=Decimal("150.50"),
            status=OrderStatus.PENDING
        )

        assert order.order_type == "limit"
        assert order.limit_price == Decimal("150.50")

    def test_order_from_signal(self):
        """Create order from Signal."""
        from src.strategies.signals import Signal

        signal = Signal(
            strategy_id="test",
            symbol="MSFT",
            action="buy",
            quantity=25,
            order_type="limit",
            limit_price=Decimal("400.00")
        )

        order = Order.from_signal(signal, order_id="ord-789")

        assert order.order_id == "ord-789"
        assert order.strategy_id == "test"
        assert order.symbol == "MSFT"
        assert order.side == "buy"
        assert order.quantity == 25
        assert order.order_type == "limit"
        assert order.limit_price == Decimal("400.00")
        assert order.status == OrderStatus.PENDING

    def test_order_to_json(self):
        """Serialize order to JSON."""
        order = Order(
            order_id="ord-123",
            broker_order_id="BRK-456",
            strategy_id="test",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.FILLED,
            filled_qty=100,
            avg_fill_price=Decimal("150.25")
        )

        data = order.to_json()
        restored = Order.from_json(data)

        assert restored.order_id == order.order_id
        assert restored.status == order.status
        assert restored.avg_fill_price == order.avg_fill_price
```

**Implementation (`backend/src/orders/models.py`):**

```python
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
import json

from src.strategies.signals import Signal


class OrderStatus(Enum):
    # Active states
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL_FILL = "partial"
    CANCEL_REQUESTED = "cancel_req"

    # Terminal states
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

    # Phase 2 placeholders
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass
class Order:
    order_id: str
    broker_order_id: str | None
    strategy_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    order_type: Literal["market", "limit"]
    limit_price: Decimal | None
    status: OrderStatus
    filled_qty: int = 0
    avg_fill_price: Decimal | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: str | None = None

    @classmethod
    def from_signal(cls, signal: Signal, order_id: str) -> "Order":
        return cls(
            order_id=order_id,
            broker_order_id=None,
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side=signal.action,
            quantity=signal.quantity,
            order_type=signal.order_type,
            limit_price=signal.limit_price,
            status=OrderStatus.PENDING
        )

    def to_json(self) -> str:
        return json.dumps({
            "order_id": self.order_id,
            "broker_order_id": self.broker_order_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": str(self.limit_price) if self.limit_price else None,
            "status": self.status.value,
            "filled_qty": self.filled_qty,
            "avg_fill_price": str(self.avg_fill_price) if self.avg_fill_price else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "error_message": self.error_message
        })

    @classmethod
    def from_json(cls, data: str) -> "Order":
        d = json.loads(data)
        return cls(
            order_id=d["order_id"],
            broker_order_id=d["broker_order_id"],
            strategy_id=d["strategy_id"],
            symbol=d["symbol"],
            side=d["side"],
            quantity=d["quantity"],
            order_type=d["order_type"],
            limit_price=Decimal(d["limit_price"]) if d["limit_price"] else None,
            status=OrderStatus(d["status"]),
            filled_qty=d["filled_qty"],
            avg_fill_price=Decimal(d["avg_fill_price"]) if d["avg_fill_price"] else None,
            created_at=datetime.fromisoformat(d["created_at"]) if d["created_at"] else None,
            updated_at=datetime.fromisoformat(d["updated_at"]) if d["updated_at"] else None,
            error_message=d["error_message"]
        )
```

**Files to create:**
- `backend/src/orders/__init__.py`
- `backend/src/orders/models.py`
- `backend/tests/orders/__init__.py`
- `backend/tests/orders/test_models.py`

---

### Task 2: Broker Protocol and Errors

**Goal:** Define the abstract Broker interface and error types.

**Test first (`backend/tests/broker/test_base.py`):**

```python
import pytest
from typing import Protocol, runtime_checkable

from src.broker.base import Broker
from src.broker.errors import BrokerError, OrderSubmissionError, OrderCancelError


class TestBrokerProtocol:
    def test_broker_is_protocol(self):
        """Broker is a Protocol class."""
        assert hasattr(Broker, '__protocol_attrs__') or isinstance(Broker, type)

    def test_protocol_methods(self):
        """Broker defines required methods."""
        # Check method signatures exist
        assert hasattr(Broker, 'submit_order')
        assert hasattr(Broker, 'cancel_order')
        assert hasattr(Broker, 'get_order_status')
        assert hasattr(Broker, 'subscribe_fills')


class TestBrokerErrors:
    def test_broker_error_base(self):
        """BrokerError is base exception."""
        err = BrokerError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert isinstance(err, Exception)

    def test_order_submission_error(self):
        """OrderSubmissionError captures order details."""
        err = OrderSubmissionError(
            message="Insufficient funds",
            order_id="ord-123",
            symbol="AAPL"
        )
        assert err.order_id == "ord-123"
        assert err.symbol == "AAPL"
        assert "Insufficient funds" in str(err)

    def test_order_cancel_error(self):
        """OrderCancelError captures cancel details."""
        err = OrderCancelError(
            message="Order already filled",
            broker_order_id="BRK-456"
        )
        assert err.broker_order_id == "BRK-456"
```

**Implementation (`backend/src/broker/base.py`):**

```python
from typing import Protocol, Callable, runtime_checkable

from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


@runtime_checkable
class Broker(Protocol):
    """Abstract broker interface for order execution."""

    async def submit_order(self, order: Order) -> str:
        """
        Submit order to broker.

        Args:
            order: The order to submit

        Returns:
            broker_order_id on success

        Raises:
            OrderSubmissionError on failure
        """
        ...

    async def cancel_order(self, broker_order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            broker_order_id: The broker's order ID

        Returns:
            True if cancelled successfully

        Raises:
            OrderCancelError on failure
        """
        ...

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Get current status of an order."""
        ...

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        """Register callback for fill notifications."""
        ...
```

**Implementation (`backend/src/broker/errors.py`):**

```python
class BrokerError(Exception):
    """Base exception for broker errors."""
    pass


class OrderSubmissionError(BrokerError):
    """Error submitting order to broker."""

    def __init__(self, message: str, order_id: str = None, symbol: str = None):
        super().__init__(message)
        self.order_id = order_id
        self.symbol = symbol


class OrderCancelError(BrokerError):
    """Error cancelling order."""

    def __init__(self, message: str, broker_order_id: str = None):
        super().__init__(message)
        self.broker_order_id = broker_order_id
```

**Files to create:**
- `backend/src/broker/__init__.py`
- `backend/src/broker/base.py`
- `backend/src/broker/errors.py`
- `backend/tests/broker/__init__.py`
- `backend/tests/broker/test_base.py`

---

### Task 3: PaperBroker Implementation

**Goal:** Implement simulated broker for paper trading.

**Test first (`backend/tests/broker/test_paper_broker.py`):**

```python
import pytest
import asyncio
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock

from src.broker.paper_broker import PaperBroker
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


@pytest.fixture
def paper_broker():
    return PaperBroker(fill_delay=0.01)  # Fast for tests


class TestPaperBroker:
    @pytest.mark.asyncio
    async def test_submit_order_returns_broker_id(self, paper_broker):
        """Submit order returns a broker order ID."""
        order = Order(
            order_id="ord-123",
            broker_order_id=None,
            strategy_id="test",
            symbol="AAPL",
            side="buy",
            quantity=100,
            order_type="market",
            limit_price=None,
            status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)

        assert broker_id.startswith("PAPER-")

    @pytest.mark.asyncio
    async def test_generates_unique_broker_ids(self, paper_broker):
        """Each order gets a unique broker ID."""
        order1 = Order(
            order_id="ord-1", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )
        order2 = Order(
            order_id="ord-2", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        id1 = await paper_broker.submit_order(order1)
        id2 = await paper_broker.submit_order(order2)

        assert id1 != id2

    @pytest.mark.asyncio
    async def test_simulates_fill_after_delay(self, paper_broker):
        """Order fill is simulated after delay."""
        fills_received = []

        def on_fill(fill: OrderFill):
            fills_received.append(fill)

        paper_broker.subscribe_fills(on_fill)

        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)

        # Wait for fill
        await asyncio.sleep(0.05)

        assert len(fills_received) == 1
        assert fills_received[0].order_id == broker_id
        assert fills_received[0].symbol == "AAPL"
        assert fills_received[0].quantity == 100

    @pytest.mark.asyncio
    async def test_limit_order_uses_limit_price(self, paper_broker):
        """Limit orders fill at limit price."""
        fills_received = []
        paper_broker.subscribe_fills(lambda f: fills_received.append(f))

        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="limit", limit_price=Decimal("150.00"),
            status=OrderStatus.PENDING
        )

        await paper_broker.submit_order(order)
        await asyncio.sleep(0.05)

        assert fills_received[0].price == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_cancel_order(self, paper_broker):
        """Can cancel a pending order."""
        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)
        result = await paper_broker.cancel_order(broker_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_get_order_status(self, paper_broker):
        """Can get order status."""
        order = Order(
            order_id="ord-123", broker_order_id=None, strategy_id="test",
            symbol="AAPL", side="buy", quantity=100,
            order_type="market", limit_price=None, status=OrderStatus.PENDING
        )

        broker_id = await paper_broker.submit_order(order)

        # Initially submitted
        status = await paper_broker.get_order_status(broker_id)
        assert status == OrderStatus.SUBMITTED

        # After fill
        await asyncio.sleep(0.05)
        status = await paper_broker.get_order_status(broker_id)
        assert status == OrderStatus.FILLED
```

**Implementation (`backend/src/broker/paper_broker.py`):**

```python
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Callable

from src.broker.base import Broker
from src.broker.errors import OrderCancelError
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


class PaperBroker:
    """Simulates order execution for paper trading."""

    def __init__(self, fill_delay: float = 0.1, default_price: Decimal = Decimal("100")):
        self._fill_delay = fill_delay
        self._default_price = default_price
        self._fill_callback: Callable[[OrderFill], None] | None = None
        self._order_counter = 0
        self._orders: dict[str, Order] = {}
        self._order_statuses: dict[str, OrderStatus] = {}
        self._cancelled: set[str] = set()

    async def submit_order(self, order: Order) -> str:
        """Submit order and schedule simulated fill."""
        self._order_counter += 1
        broker_id = f"PAPER-{self._order_counter:06d}"

        self._orders[broker_id] = order
        self._order_statuses[broker_id] = OrderStatus.SUBMITTED

        # Schedule fill simulation
        asyncio.create_task(self._simulate_fill(order, broker_id))

        return broker_id

    async def cancel_order(self, broker_order_id: str) -> bool:
        """Cancel an order if not yet filled."""
        if broker_order_id not in self._orders:
            raise OrderCancelError("Order not found", broker_order_id)

        if self._order_statuses.get(broker_order_id) == OrderStatus.FILLED:
            raise OrderCancelError("Order already filled", broker_order_id)

        self._cancelled.add(broker_order_id)
        self._order_statuses[broker_order_id] = OrderStatus.CANCELLED
        return True

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        """Get current order status."""
        return self._order_statuses.get(broker_order_id, OrderStatus.PENDING)

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        """Register fill callback."""
        self._fill_callback = callback

    async def _simulate_fill(self, order: Order, broker_id: str) -> None:
        """Simulate order fill after delay."""
        await asyncio.sleep(self._fill_delay)

        # Check if cancelled
        if broker_id in self._cancelled:
            return

        # Determine fill price
        if order.order_type == "limit" and order.limit_price:
            fill_price = order.limit_price
        else:
            fill_price = self._default_price

        # Create fill
        fill = OrderFill(
            order_id=broker_id,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=fill_price,
            timestamp=datetime.utcnow()
        )

        # Update status
        self._order_statuses[broker_id] = OrderStatus.FILLED

        # Notify callback
        if self._fill_callback:
            self._fill_callback(fill)
```

**Files to create:**
- `backend/src/broker/paper_broker.py`
- `backend/tests/broker/test_paper_broker.py`

---

### Task 4: OrderManager Core

**Goal:** Implement OrderManager with signal consumption and order submission.

**Test first (`backend/tests/orders/test_manager.py`):**

```python
import pytest
import asyncio
import json
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch

from src.orders.manager import OrderManager
from src.orders.models import Order, OrderStatus
from src.strategies.signals import Signal


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.submit_order = AsyncMock(return_value="BRK-001")
    broker.subscribe_fills = MagicMock()
    return broker


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.record_fill = AsyncMock()
    return portfolio


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.brpop = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def order_manager(mock_broker, mock_portfolio, mock_redis, mock_db):
    return OrderManager(
        broker=mock_broker,
        portfolio=mock_portfolio,
        redis=mock_redis,
        db_session=mock_db,
        account_id="ACC001"
    )


class TestOrderManagerProcessSignal:
    @pytest.mark.asyncio
    async def test_creates_order_from_signal(self, order_manager, mock_broker):
        """Signal is converted to Order."""
        signal = Signal(
            strategy_id="momentum",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="market"
        )

        order = await order_manager.process_signal(signal)

        assert order.strategy_id == "momentum"
        assert order.symbol == "AAPL"
        assert order.side == "buy"
        assert order.quantity == 100
        assert order.status == OrderStatus.SUBMITTED

    @pytest.mark.asyncio
    async def test_submits_to_broker(self, order_manager, mock_broker):
        """Order is submitted to broker."""
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=100
        )

        order = await order_manager.process_signal(signal)

        mock_broker.submit_order.assert_called_once()
        assert order.broker_order_id == "BRK-001"

    @pytest.mark.asyncio
    async def test_tracks_active_order(self, order_manager):
        """Order is tracked in active orders."""
        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=100
        )

        order = await order_manager.process_signal(signal)

        assert order.order_id in order_manager.active_orders
        assert order_manager.get_order(order.order_id) == order

    @pytest.mark.asyncio
    async def test_broker_rejection_handled(self, order_manager, mock_broker):
        """Broker rejection updates order status."""
        from src.broker.errors import OrderSubmissionError

        mock_broker.submit_order = AsyncMock(
            side_effect=OrderSubmissionError("Insufficient funds")
        )

        signal = Signal(
            strategy_id="test",
            symbol="AAPL",
            action="buy",
            quantity=100
        )

        order = await order_manager.process_signal(signal)

        assert order.status == OrderStatus.REJECTED
        assert "Insufficient funds" in order.error_message


class TestOrderManagerGetters:
    @pytest.mark.asyncio
    async def test_get_order_by_id(self, order_manager):
        """Can retrieve order by ID."""
        signal = Signal(
            strategy_id="test", symbol="AAPL", action="buy", quantity=100
        )

        order = await order_manager.process_signal(signal)
        retrieved = order_manager.get_order(order.order_id)

        assert retrieved == order

    @pytest.mark.asyncio
    async def test_get_orders_by_strategy(self, order_manager):
        """Can filter orders by strategy."""
        signal1 = Signal(strategy_id="strat_a", symbol="AAPL", action="buy", quantity=100)
        signal2 = Signal(strategy_id="strat_b", symbol="GOOGL", action="buy", quantity=50)
        signal3 = Signal(strategy_id="strat_a", symbol="MSFT", action="sell", quantity=25)

        await order_manager.process_signal(signal1)
        await order_manager.process_signal(signal2)
        await order_manager.process_signal(signal3)

        strat_a_orders = order_manager.get_orders_by_strategy("strat_a")

        assert len(strat_a_orders) == 2
        assert all(o.strategy_id == "strat_a" for o in strat_a_orders)
```

**Implementation (`backend/src/orders/manager.py`):**

```python
import asyncio
import json
from datetime import datetime
from decimal import Decimal
from typing import Callable
from uuid import uuid4

from src.broker.base import Broker
from src.broker.errors import BrokerError
from src.orders.models import Order, OrderStatus
from src.strategies.signals import Signal, OrderFill


class OrderManager:
    """Manages order lifecycle from signal to fill."""

    def __init__(
        self,
        broker: Broker,
        portfolio,  # PortfolioManager
        redis,      # Redis client
        db_session, # AsyncSession
        account_id: str
    ):
        self._broker = broker
        self._portfolio = portfolio
        self._redis = redis
        self._db = db_session
        self._account_id = account_id
        self._active_orders: dict[str, Order] = {}
        self._broker_id_map: dict[str, str] = {}
        self._running = False

    @property
    def active_orders(self) -> dict[str, Order]:
        """Get active orders dict."""
        return self._active_orders

    async def start(self) -> None:
        """Start consuming signals from Redis queue."""
        self._broker.subscribe_fills(self._on_fill)
        self._running = True
        asyncio.create_task(self._consume_signals())

    async def stop(self) -> None:
        """Stop the order manager."""
        self._running = False

    async def _consume_signals(self) -> None:
        """Consume approved signals from Redis queue."""
        while self._running:
            try:
                result = await self._redis.brpop("approved_signals", timeout=1)
                if result:
                    _, signal_data = result
                    signal = Signal.from_json(signal_data)
                    await self.process_signal(signal)
            except Exception as e:
                # Log error, continue consuming
                pass

    async def process_signal(self, signal: Signal) -> Order:
        """Convert signal to order and submit to broker."""
        order = Order.from_signal(signal, order_id=str(uuid4()))
        self._active_orders[order.order_id] = order

        try:
            broker_id = await self._broker.submit_order(order)
            order.broker_order_id = broker_id
            order.status = OrderStatus.SUBMITTED
            order.updated_at = datetime.utcnow()
            self._broker_id_map[broker_id] = order.order_id
        except BrokerError as e:
            order.status = OrderStatus.REJECTED
            order.error_message = str(e)
            order.updated_at = datetime.utcnow()

        return order

    def get_order(self, order_id: str) -> Order | None:
        """Get order by internal ID."""
        return self._active_orders.get(order_id)

    def get_orders_by_strategy(self, strategy_id: str) -> list[Order]:
        """Get all active orders for a strategy."""
        return [
            order for order in self._active_orders.values()
            if order.strategy_id == strategy_id
        ]

    def _on_fill(self, fill: OrderFill) -> None:
        """Handle fill notification - implemented in Task 5."""
        pass
```

**Files to create:**
- `backend/src/orders/manager.py`
- `backend/tests/orders/test_manager.py`

---

### Task 5: Fill Handling

**Goal:** Implement fill handling with portfolio updates and strategy notifications.

**Test first (`backend/tests/orders/test_fill_handling.py`):**

```python
import pytest
import asyncio
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from src.orders.manager import OrderManager
from src.orders.models import Order, OrderStatus
from src.strategies.signals import Signal, OrderFill


@pytest.fixture
def mock_broker():
    broker = MagicMock()
    broker.submit_order = AsyncMock(return_value="BRK-001")
    broker.subscribe_fills = MagicMock()
    return broker


@pytest.fixture
def mock_portfolio():
    portfolio = MagicMock()
    portfolio.record_fill = AsyncMock()
    return portfolio


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.brpop = AsyncMock()
    redis.publish = AsyncMock()
    return redis


@pytest.fixture
def order_manager(mock_broker, mock_portfolio, mock_redis):
    return OrderManager(
        broker=mock_broker,
        portfolio=mock_portfolio,
        redis=mock_redis,
        db_session=MagicMock(),
        account_id="ACC001"
    )


class TestFillHandling:
    @pytest.mark.asyncio
    async def test_full_fill_updates_order(self, order_manager):
        """Full fill updates order status to FILLED."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",  # CRITICAL: unique fill ID
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill)

        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 100
        assert order.avg_fill_price == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_partial_fill_updates_order(self, order_manager):
        """Partial fill updates status to PARTIAL_FILL."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001",
            symbol="AAPL",
            side="buy",
            quantity=60,
            price=Decimal("150.00"),
            timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill)

        assert order.status == OrderStatus.PARTIAL_FILL
        assert order.filled_qty == 60

    @pytest.mark.asyncio
    async def test_multiple_partials_complete_order(self, order_manager):
        """Multiple partial fills complete the order."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill1 = OrderFill(
            fill_id="FILL-001",  # Different fill_id for each fill
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=60, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )
        fill2 = OrderFill(
            fill_id="FILL-002",  # Different fill_id
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=40, price=Decimal("151.00"), timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill1)
        await order_manager.handle_fill(fill2)

        assert order.status == OrderStatus.FILLED
        assert order.filled_qty == 100

    @pytest.mark.asyncio
    async def test_avg_price_calculation(self, order_manager):
        """Average fill price is calculated correctly."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        # 60 @ 150 + 40 @ 160 = 9000 + 6400 = 15400 / 100 = 154
        fill1 = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=60, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )
        fill2 = OrderFill(
            fill_id="FILL-002",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=40, price=Decimal("160.00"), timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill1)
        await order_manager.handle_fill(fill2)

        assert order.avg_fill_price == Decimal("154.00")

    @pytest.mark.asyncio
    async def test_fill_updates_portfolio(self, order_manager, mock_portfolio):
        """Fill triggers portfolio update."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=100, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill)

        mock_portfolio.record_fill.assert_called_once()

    @pytest.mark.asyncio
    async def test_fill_publishes_event(self, order_manager, mock_redis):
        """Fill publishes event to Redis."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=100, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill)

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "fills"

    @pytest.mark.asyncio
    async def test_completed_order_removed_from_active(self, order_manager):
        """Filled orders are removed from active tracking."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)
        order_id = order.order_id

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=100, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill)

        assert order_id not in order_manager.active_orders


class TestFillIdempotency:
    """CRITICAL: Tests for fill deduplication."""

    @pytest.mark.asyncio
    async def test_duplicate_fill_ignored(self, order_manager, mock_portfolio):
        """Same fill_id is only processed once."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        order = await order_manager.process_signal(signal)

        fill = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=100, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )

        # Process same fill twice
        await order_manager.handle_fill(fill)
        await order_manager.handle_fill(fill)  # Duplicate!

        # Should only update portfolio once
        assert mock_portfolio.record_fill.call_count == 1
        assert order.filled_qty == 100  # Not 200!

    @pytest.mark.asyncio
    async def test_different_fill_ids_processed(self, order_manager, mock_portfolio):
        """Different fill_ids are all processed."""
        signal = Signal(strategy_id="test", symbol="AAPL", action="buy", quantity=100)
        await order_manager.process_signal(signal)

        fill1 = OrderFill(
            fill_id="FILL-001",
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=50, price=Decimal("150.00"), timestamp=datetime.utcnow()
        )
        fill2 = OrderFill(
            fill_id="FILL-002",  # Different ID
            order_id="BRK-001", symbol="AAPL", side="buy",
            quantity=50, price=Decimal("151.00"), timestamp=datetime.utcnow()
        )

        await order_manager.handle_fill(fill1)
        await order_manager.handle_fill(fill2)

        assert mock_portfolio.record_fill.call_count == 2
```

**Update `backend/src/orders/manager.py`:**

```python
# Add to OrderManager class

# In __init__, add:
self._processed_fills: set[str] = set()  # For idempotency
self._loop: asyncio.AbstractEventLoop = None

# In start(), add:
async def start(self) -> None:
    self._loop = asyncio.get_running_loop()
    # CRITICAL: Use sync wrapper for broker callback
    self._broker.subscribe_fills(self._on_fill_sync)
    # ... rest of start

# Sync wrapper for thread-safe callback
def _on_fill_sync(self, fill: OrderFill) -> None:
    """
    Sync callback for broker fills.
    IMPORTANT: Futu SDK calls this from a different thread.
    """
    if self._loop and self._loop.is_running():
        asyncio.run_coroutine_threadsafe(
            self.handle_fill(fill),
            self._loop
        )

async def handle_fill(self, fill: OrderFill) -> None:
    """Handle fill notification from broker (idempotent)."""
    # IDEMPOTENCY CHECK - Must be first!
    if fill.fill_id in self._processed_fills:
        return  # Duplicate, ignore
    self._processed_fills.add(fill.fill_id)

    order_id = self._broker_id_map.get(fill.order_id)
    if not order_id:
        return  # Unknown order

    order = self._active_orders.get(order_id)
    if not order:
        return

    # Update order state
    prev_qty = order.filled_qty
    prev_avg = order.avg_fill_price or Decimal("0")

    order.filled_qty += fill.quantity
    order.avg_fill_price = self._calc_avg_price(prev_qty, prev_avg, fill)
    order.updated_at = datetime.utcnow()

    if order.filled_qty >= order.quantity:
        order.status = OrderStatus.FILLED
    else:
        order.status = OrderStatus.PARTIAL_FILL

    # Update portfolio
    await self._portfolio.record_fill(
        account_id=self._account_id,
        symbol=order.symbol,
        side=order.side,
        quantity=fill.quantity,
        price=fill.price,
        strategy_id=order.strategy_id
    )

    # Publish fill event
    await self._redis.publish("fills", fill.to_json())

    # Cleanup if fully filled
    if order.status == OrderStatus.FILLED:
        await self._persist_order(order)
        del self._active_orders[order.order_id]
        del self._broker_id_map[order.broker_order_id]

def _calc_avg_price(
    self,
    prev_qty: int,
    prev_avg: Decimal,
    fill: OrderFill
) -> Decimal:
    """Calculate volume-weighted average fill price."""
    total_qty = prev_qty + fill.quantity
    total_value = (prev_avg * prev_qty) + (fill.price * fill.quantity)
    return total_value / total_qty

async def _persist_order(self, order: Order) -> None:
    """Save completed order to database."""
    # TODO: Implement DB persistence
    pass

def _on_fill(self, fill: OrderFill) -> None:
    """Callback for broker fill notifications."""
    asyncio.create_task(self.handle_fill(fill))
```

**Files to update:**
- `backend/src/orders/manager.py`
- `backend/tests/orders/test_fill_handling.py`

---

### Task 6: Signal JSON Serialization

**Goal:** Add JSON serialization to Signal for Redis queue.

**Test first (`backend/tests/strategies/test_signals.py`):**

```python
import pytest
from decimal import Decimal
from datetime import datetime

from src.strategies.signals import Signal, OrderFill


class TestSignalSerialization:
    def test_signal_to_json(self):
        """Signal serializes to JSON."""
        signal = Signal(
            strategy_id="momentum",
            symbol="AAPL",
            action="buy",
            quantity=100,
            order_type="limit",
            limit_price=Decimal("150.50"),
            reason="Price crossed MA"
        )

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.strategy_id == signal.strategy_id
        assert restored.symbol == signal.symbol
        assert restored.action == signal.action
        assert restored.quantity == signal.quantity
        assert restored.order_type == signal.order_type
        assert restored.limit_price == signal.limit_price
        assert restored.reason == signal.reason

    def test_signal_market_order(self):
        """Market order signal without limit price."""
        signal = Signal(
            strategy_id="test",
            symbol="GOOGL",
            action="sell",
            quantity=50
        )

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.order_type == "market"
        assert restored.limit_price is None


class TestOrderFillSerialization:
    def test_order_fill_to_json(self):
        """OrderFill serializes to JSON."""
        fill = OrderFill(
            order_id="ord-123",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.25"),
            timestamp=datetime(2026, 1, 23, 12, 0, 0)
        )

        json_str = fill.to_json()
        restored = OrderFill.from_json(json_str)

        assert restored.order_id == fill.order_id
        assert restored.symbol == fill.symbol
        assert restored.side == fill.side
        assert restored.quantity == fill.quantity
        assert restored.price == fill.price
```

**Update `backend/src/strategies/signals.py`:**

```python
# Add to Signal class
import json

def to_json(self) -> str:
    return json.dumps({
        "strategy_id": self.strategy_id,
        "symbol": self.symbol,
        "action": self.action,
        "quantity": self.quantity,
        "order_type": self.order_type,
        "limit_price": str(self.limit_price) if self.limit_price else None,
        "reason": self.reason,
        "timestamp": self.timestamp.isoformat()
    })

@classmethod
def from_json(cls, data: str) -> "Signal":
    d = json.loads(data)
    return cls(
        strategy_id=d["strategy_id"],
        symbol=d["symbol"],
        action=d["action"],
        quantity=d["quantity"],
        order_type=d.get("order_type", "market"),
        limit_price=Decimal(d["limit_price"]) if d.get("limit_price") else None,
        reason=d.get("reason", ""),
        timestamp=datetime.fromisoformat(d["timestamp"]) if d.get("timestamp") else datetime.utcnow()
    )


# Add to OrderFill class (or create if not exists)
@dataclass
class OrderFill:
    fill_id: str  # CRITICAL: Broker's unique trade ID for idempotency
    order_id: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    price: Decimal
    timestamp: datetime

    def to_json(self) -> str:
        return json.dumps({
            "fill_id": self.fill_id,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": str(self.price),
            "timestamp": self.timestamp.isoformat()
        })

    @classmethod
    def from_json(cls, data: str) -> "OrderFill":
        d = json.loads(data)
        return cls(
            fill_id=d["fill_id"],
            order_id=d["order_id"],
            symbol=d["symbol"],
            side=d["side"],
            quantity=d["quantity"],
            price=Decimal(d["price"]),
            timestamp=datetime.fromisoformat(d["timestamp"])
        )
```

**Files to update:**
- `backend/src/strategies/signals.py`
- `backend/tests/strategies/test_signals.py`

---

### Task 7: Broker Configuration

**Goal:** Add broker configuration loading from YAML.

**Test first (`backend/tests/broker/test_config.py`):**

```python
import pytest
import tempfile

from src.broker.config import BrokerConfig, load_broker


class TestBrokerConfig:
    def test_load_paper_broker_config(self):
        """Load paper broker from config."""
        yaml_content = """
broker:
  type: "paper"
  paper:
    fill_delay: 0.05
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = BrokerConfig.from_yaml(f.name)

        assert config.broker_type == "paper"
        assert config.paper_fill_delay == 0.05

    def test_load_futu_broker_config(self):
        """Load Futu broker from config."""
        yaml_content = """
broker:
  type: "futu"
  futu:
    host: "127.0.0.1"
    port: 11111
    trade_env: "SIMULATE"
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            config = BrokerConfig.from_yaml(f.name)

        assert config.broker_type == "futu"
        assert config.futu_host == "127.0.0.1"
        assert config.futu_port == 11111
        assert config.futu_trade_env == "SIMULATE"

    def test_create_paper_broker(self):
        """Factory creates PaperBroker."""
        yaml_content = """
broker:
  type: "paper"
  paper:
    fill_delay: 0.1
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            broker = load_broker(f.name)

        from src.broker.paper_broker import PaperBroker
        assert isinstance(broker, PaperBroker)
```

**Implementation (`backend/src/broker/config.py`):**

```python
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.broker.paper_broker import PaperBroker


@dataclass
class BrokerConfig:
    broker_type: str

    # Paper broker settings
    paper_fill_delay: float = 0.1

    # Futu broker settings
    futu_host: str = "127.0.0.1"
    futu_port: int = 11111
    futu_trade_env: str = "SIMULATE"

    @classmethod
    def from_yaml(cls, path: str) -> "BrokerConfig":
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(file_path) as f:
            data = yaml.safe_load(f)

        broker_data = data.get("broker", {})
        paper_data = broker_data.get("paper", {})
        futu_data = broker_data.get("futu", {})

        return cls(
            broker_type=broker_data.get("type", "paper"),
            paper_fill_delay=paper_data.get("fill_delay", 0.1),
            futu_host=futu_data.get("host", "127.0.0.1"),
            futu_port=futu_data.get("port", 11111),
            futu_trade_env=futu_data.get("trade_env", "SIMULATE")
        )


def load_broker(config_path: str):
    """Factory function to create broker from config."""
    config = BrokerConfig.from_yaml(config_path)

    if config.broker_type == "paper":
        return PaperBroker(fill_delay=config.paper_fill_delay)
    elif config.broker_type == "futu":
        # FutuBroker implementation deferred
        raise NotImplementedError("FutuBroker not yet implemented")
    else:
        raise ValueError(f"Unknown broker type: {config.broker_type}")
```

**Create config file (`config/broker.yaml`):**

```yaml
broker:
  type: "paper"  # "futu" or "paper"

  futu:
    host: "127.0.0.1"
    port: 11111
    trade_env: "SIMULATE"  # "REAL" or "SIMULATE"

  paper:
    fill_delay: 0.1        # Seconds before simulated fill
```

**Files to create:**
- `backend/src/broker/config.py`
- `backend/tests/broker/test_config.py`
- `config/broker.yaml`

---

### Task 8: Package Exports

**Goal:** Create package __init__.py files with proper exports.

**Implementation (`backend/src/orders/__init__.py`):**

```python
"""Order management module."""

from src.orders.models import Order, OrderStatus
from src.orders.manager import OrderManager

__all__ = [
    "Order",
    "OrderStatus",
    "OrderManager",
]
```

**Implementation (`backend/src/broker/__init__.py`):**

```python
"""Broker abstraction module."""

from src.broker.base import Broker
from src.broker.errors import BrokerError, OrderSubmissionError, OrderCancelError
from src.broker.paper_broker import PaperBroker
from src.broker.config import BrokerConfig, load_broker

__all__ = [
    "Broker",
    "BrokerError",
    "OrderSubmissionError",
    "OrderCancelError",
    "PaperBroker",
    "BrokerConfig",
    "load_broker",
]
```

**Files to create/update:**
- `backend/src/orders/__init__.py`
- `backend/src/broker/__init__.py`

---

## Summary

| Task | Description | Tests |
|------|-------------|-------|
| 1 | Order and OrderStatus models (with Phase 2 placeholders) | 5 |
| 2 | Broker protocol and errors | 4 |
| 3 | PaperBroker implementation (realistic: partials, rejections, slippage) | 8 |
| 4 | OrderManager core (persist PENDING before submit) | 6 |
| 5 | Fill handling (with idempotency via fill_id) | 9 |
| 6 | Signal JSON serialization (with fill_id) | 4 |
| 7 | Broker configuration | 3 |
| 8 | Package exports | - |

**Total: 8 tasks, ~39 tests**

## Critical Fixes (from code review)

These fixes are incorporated into the tasks above:

1. **Fill Idempotency** (Task 5) - Deduplicate by fill_id to prevent position doubling
2. **Sync/Async Callback** (Task 4) - Use `asyncio.run_coroutine_threadsafe` for Futu thread callbacks
3. **Persist Before Submit** (Task 4) - Write PENDING order to DB before broker submit
4. **Realistic PaperBroker** (Task 3) - Partial fills, rejections, slippage variance
5. **Order State Placeholders** (Task 1) - CANCEL_REQUESTED, EXPIRED, UNKNOWN for Phase 2

## Execution

Run tests with:
```bash
cd backend && pytest tests/orders/ tests/broker/ -v
```

## Phase 2 Extensions

- Order recovery on restart (sync with broker)
- Cancel/Replace flow with CANCEL_REQUESTED state
- Redis Streams with consumer groups
- Execution metrics (slippage, latency)
