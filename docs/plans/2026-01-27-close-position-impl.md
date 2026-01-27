# Close Position Flow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the close position flow with idempotency, state machine, outbox pattern, and order fill callback.

**Architecture:** 3-phase transaction (lock → outbox → async worker) with monotonic order updates and reconciler for recovery.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL, Alembic, pytest-asyncio

---

## Task 1: Add New PositionStatus Values

**Files:**
- Modify: `backend/src/models/position.py:22-26`
- Test: `backend/tests/models/test_position_status.py`

**Step 1: Write the failing test**

Create `backend/tests/models/test_position_status.py`:

```python
"""Tests for PositionStatus enum."""

import pytest

from src.models.position import PositionStatus


def test_position_status_has_close_retryable():
    """PositionStatus should have CLOSE_RETRYABLE value."""
    assert PositionStatus.CLOSE_RETRYABLE == "close_retryable"


def test_position_status_has_close_failed():
    """PositionStatus should have CLOSE_FAILED value."""
    assert PositionStatus.CLOSE_FAILED == "close_failed"


def test_all_position_statuses():
    """PositionStatus should have all 5 values."""
    expected = {"open", "closing", "closed", "close_retryable", "close_failed"}
    actual = {s.value for s in PositionStatus}
    assert actual == expected
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/models/test_position_status.py -v`
Expected: FAIL with "CLOSE_RETRYABLE is not a valid PositionStatus"

**Step 3: Write minimal implementation**

Edit `backend/src/models/position.py`:

```python
class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    CLOSE_RETRYABLE = "close_retryable"
    CLOSE_FAILED = "close_failed"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/models/test_position_status.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/position.py backend/tests/models/test_position_status.py
git commit -m "feat(models): add CLOSE_RETRYABLE and CLOSE_FAILED to PositionStatus"
```

---

## Task 2: Add Position.active_close_request_id and closed_at

**Files:**
- Modify: `backend/src/models/position.py:28-62`
- Test: `backend/tests/models/test_position_status.py` (extend)

**Step 1: Write the failing test**

Add to `backend/tests/models/test_position_status.py`:

```python
from datetime import datetime
from uuid import uuid4


def test_position_has_active_close_request_id():
    """Position should have active_close_request_id field."""
    from src.models.position import Position

    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        quantity=100,
    )
    assert hasattr(pos, "active_close_request_id")
    assert pos.active_close_request_id is None


def test_position_has_closed_at():
    """Position should have closed_at field."""
    from src.models.position import Position

    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        quantity=100,
    )
    assert hasattr(pos, "closed_at")
    assert pos.closed_at is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/models/test_position_status.py::test_position_has_active_close_request_id -v`
Expected: FAIL with "no attribute 'active_close_request_id'"

**Step 3: Write minimal implementation**

Edit `backend/src/models/position.py`, add after `updated_at`:

```python
from sqlalchemy.dialects.postgresql import UUID as PGUUID
import uuid

class Position(Base):
    # ... existing fields ...

    # Close request tracking
    active_close_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/models/test_position_status.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/position.py backend/tests/models/test_position_status.py
git commit -m "feat(models): add active_close_request_id and closed_at to Position"
```

---

## Task 3: Create CloseRequest Model

**Files:**
- Create: `backend/src/models/close_request.py`
- Modify: `backend/src/models/__init__.py`
- Test: `backend/tests/models/test_close_request.py`

**Step 1: Write the failing test**

Create `backend/tests/models/test_close_request.py`:

```python
"""Tests for CloseRequest model."""

import pytest
from uuid import uuid4


def test_close_request_status_enum():
    """CloseRequestStatus should have all required values."""
    from src.models.close_request import CloseRequestStatus

    expected = {"pending", "submitted", "completed", "retryable", "failed"}
    actual = {s.value for s in CloseRequestStatus}
    assert actual == expected


def test_close_request_model_fields():
    """CloseRequest should have all required fields."""
    from src.models.close_request import CloseRequest, CloseRequestStatus

    cr = CloseRequest(
        id=uuid4(),
        position_id=1,
        idempotency_key="test-key",
        status=CloseRequestStatus.PENDING,
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.position_id == 1
    assert cr.idempotency_key == "test-key"
    assert cr.status == CloseRequestStatus.PENDING
    assert cr.symbol == "AAPL"
    assert cr.side == "sell"
    assert cr.asset_type == "option"
    assert cr.target_qty == 100
    assert cr.filled_qty == 0
    assert cr.retry_count == 0
    assert cr.max_retries == 3
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/models/test_close_request.py -v`
Expected: FAIL with "No module named 'src.models.close_request'"

**Step 3: Write minimal implementation**

Create `backend/src/models/close_request.py`:

```python
"""CloseRequest model for tracking position close operations."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class CloseRequestStatus(str, Enum):
    """Status of a close request."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    RETRYABLE = "retryable"
    FAILED = "failed"


class CloseRequest(Base):
    """Tracks a request to close a position.

    Stores order parameters for retry consistency - side/symbol/asset_type
    are captured at creation and not re-derived from position.
    """

    __tablename__ = "close_requests"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    position_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("positions.id"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[CloseRequestStatus] = mapped_column(
        String(20), default=CloseRequestStatus.PENDING
    )

    # Order parameters (stored for retry consistency)
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10))  # "buy" or "sell"
    asset_type: Mapped[str] = mapped_column(String(20))

    # Quantities
    target_qty: Mapped[int] = mapped_column(Integer)
    filled_qty: Mapped[int] = mapped_column(Integer, default=0)
    # NOTE: remaining_qty is computed in PostgreSQL as generated column

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    @property
    def remaining_qty(self) -> int:
        """Calculate remaining quantity to close."""
        return self.target_qty - self.filled_qty
```

Update `backend/src/models/__init__.py`:

```python
from src.models.account import Account
from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.order import OrderRecord, OrderSide, OrderStatus, OrderType
from src.models.position import AssetType, Position, PositionStatus, PutCall
from src.models.transaction import Transaction, TransactionAction

__all__ = [
    "Account",
    "Position",
    "AssetType",
    "PutCall",
    "PositionStatus",
    "Transaction",
    "TransactionAction",
    "OrderRecord",
    "OrderStatus",
    "OrderSide",
    "OrderType",
    "CloseRequest",
    "CloseRequestStatus",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/models/test_close_request.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/close_request.py backend/src/models/__init__.py backend/tests/models/test_close_request.py
git commit -m "feat(models): add CloseRequest model with status enum"
```

---

## Task 4: Create OutboxEvent Model

**Files:**
- Create: `backend/src/models/outbox.py`
- Modify: `backend/src/models/__init__.py`
- Test: `backend/tests/models/test_outbox.py`

**Step 1: Write the failing test**

Create `backend/tests/models/test_outbox.py`:

```python
"""Tests for OutboxEvent model."""

import pytest


def test_outbox_event_status_enum():
    """OutboxEventStatus should have all required values."""
    from src.models.outbox import OutboxEventStatus

    expected = {"pending", "processing", "completed", "failed"}
    actual = {s.value for s in OutboxEventStatus}
    assert actual == expected


def test_outbox_event_model_fields():
    """OutboxEvent should have all required fields."""
    from src.models.outbox import OutboxEvent, OutboxEventStatus

    event = OutboxEvent(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123", "symbol": "AAPL"},
    )

    assert event.event_type == "SUBMIT_CLOSE_ORDER"
    assert event.payload["symbol"] == "AAPL"
    assert event.status == OutboxEventStatus.PENDING
    assert event.retry_count == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/models/test_outbox.py -v`
Expected: FAIL with "No module named 'src.models.outbox'"

**Step 3: Write minimal implementation**

Create `backend/src/models/outbox.py`:

```python
"""OutboxEvent model for reliable async event processing."""

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class OutboxEventStatus(str, Enum):
    """Status of an outbox event."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboxEvent(Base):
    """Event in the outbox for reliable async processing.

    Uses the Outbox Pattern to ensure exactly-once delivery of events
    even when the system crashes between database commit and external call.
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    status: Mapped[OutboxEventStatus] = mapped_column(
        String(20), default=OutboxEventStatus.PENDING
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
```

Update `backend/src/models/__init__.py` to add:

```python
from src.models.outbox import OutboxEvent, OutboxEventStatus
# ... in __all__:
    "OutboxEvent",
    "OutboxEventStatus",
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/models/test_outbox.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/outbox.py backend/src/models/__init__.py backend/tests/models/test_outbox.py
git commit -m "feat(models): add OutboxEvent model for reliable async processing"
```

---

## Task 5: Add OrderRecord Fields for Close Request Tracking

**Files:**
- Modify: `backend/src/models/order.py:38-82`
- Test: `backend/tests/models/test_order_close_fields.py`

**Step 1: Write the failing test**

Create `backend/tests/models/test_order_close_fields.py`:

```python
"""Tests for OrderRecord close request fields."""

import pytest
from uuid import uuid4


def test_order_record_has_close_request_id():
    """OrderRecord should have close_request_id field."""
    from src.models.order import OrderRecord, OrderSide, OrderType, OrderStatus

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "close_request_id")
    assert order.close_request_id is None


def test_order_record_has_broker_update_seq():
    """OrderRecord should have broker_update_seq field."""
    from src.models.order import OrderRecord, OrderSide, OrderType, OrderStatus

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "broker_update_seq")
    assert order.broker_update_seq is None


def test_order_record_has_reconcile_not_found_count():
    """OrderRecord should have reconcile_not_found_count field."""
    from src.models.order import OrderRecord, OrderSide, OrderType, OrderStatus

    order = OrderRecord(
        order_id="test-order",
        account_id="ACC001",
        strategy_id="test",
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=100,
        order_type=OrderType.LIMIT,
        status=OrderStatus.PENDING,
    )

    assert hasattr(order, "reconcile_not_found_count")
    assert order.reconcile_not_found_count == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/models/test_order_close_fields.py -v`
Expected: FAIL with "no attribute 'close_request_id'"

**Step 3: Write minimal implementation**

Edit `backend/src/models/order.py`, add after `updated_at`:

```python
import uuid
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy import BigInteger

class OrderRecord(Base):
    # ... existing fields ...

    # Close request tracking (nullable - only set for close orders)
    close_request_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )

    # Broker update sequence for monotonic updates (nullable if broker doesn't provide)
    broker_update_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_broker_update_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Reconciler retry tracking
    reconcile_not_found_count: Mapped[int] = mapped_column(Integer, default=0)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/models/test_order_close_fields.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/models/order.py backend/tests/models/test_order_close_fields.py
git commit -m "feat(models): add close_request_id and broker tracking fields to OrderRecord"
```

---

## Task 6: Create Migration for close_requests Table

**Files:**
- Create: `backend/alembic/versions/012_close_requests.py`

**Step 1: Create migration file**

Create `backend/alembic/versions/012_close_requests.py`:

```python
"""Create close_requests table.

Revision ID: 012_close_requests
Revises: 011_orders_table
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "012_close_requests"
down_revision = "011_orders_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create close_requests table
    op.create_table(
        "close_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "position_id",
            sa.Integer,
            sa.ForeignKey("positions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("idempotency_key", sa.VARCHAR(100), nullable=False),
        sa.Column("status", sa.VARCHAR(20), nullable=False, server_default="pending"),
        # Order parameters
        sa.Column("symbol", sa.VARCHAR(50), nullable=False),
        sa.Column("side", sa.VARCHAR(10), nullable=False),
        sa.Column("asset_type", sa.VARCHAR(20), nullable=False),
        # Quantities
        sa.Column("target_qty", sa.Integer, nullable=False),
        sa.Column("filled_qty", sa.Integer, nullable=False, server_default="0"),
        # PostgreSQL generated column for remaining_qty
        sa.Column(
            "remaining_qty",
            sa.Integer,
            sa.Computed("target_qty - filled_qty"),
            nullable=False,
        ),
        # Retry tracking
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Unique constraint for idempotency
    op.create_unique_constraint(
        "uq_close_requests_position_idempotency",
        "close_requests",
        ["position_id", "idempotency_key"],
    )

    # Index for status queries
    op.create_index(
        "idx_close_requests_status",
        "close_requests",
        ["status"],
        postgresql_where=sa.text("status IN ('pending', 'submitted')"),
    )

    # Add active_close_request_id to positions
    op.add_column(
        "positions",
        sa.Column(
            "active_close_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("close_requests.id"),
            nullable=True,
        ),
    )

    # Add closed_at to positions
    op.add_column(
        "positions",
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("positions", "closed_at")
    op.drop_column("positions", "active_close_request_id")
    op.drop_index("idx_close_requests_status", table_name="close_requests")
    op.drop_constraint(
        "uq_close_requests_position_idempotency", "close_requests", type_="unique"
    )
    op.drop_table("close_requests")
```

**Step 2: Run migration (if DB available)**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

**Step 3: Commit**

```bash
git add backend/alembic/versions/012_close_requests.py
git commit -m "feat(db): add migration for close_requests table"
```

---

## Task 7: Create Migration for outbox_events Table

**Files:**
- Create: `backend/alembic/versions/013_outbox_events.py`

**Step 1: Create migration file**

Create `backend/alembic/versions/013_outbox_events.py`:

```python
"""Create outbox_events table.

Revision ID: 013_outbox_events
Revises: 012_close_requests
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "013_outbox_events"
down_revision = "012_close_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create outbox_events table
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.VARCHAR(50), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.VARCHAR(20), nullable=False, server_default="pending"),
        # Generated column for unique constraint
        sa.Column(
            "close_request_id",
            sa.Text,
            sa.Computed("payload->>'close_request_id'"),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # Retry tracking
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )

    # Unique index for idempotency (only when close_request_id is not null)
    op.create_index(
        "idx_outbox_idempotency",
        "outbox_events",
        ["event_type", "close_request_id"],
        unique=True,
        postgresql_where=sa.text("close_request_id IS NOT NULL"),
    )

    # Index for pending events (worker query)
    op.create_index(
        "idx_outbox_pending",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Index for cleanup job
    op.create_index(
        "idx_outbox_completed",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_completed", table_name="outbox_events")
    op.drop_index("idx_outbox_pending", table_name="outbox_events")
    op.drop_index("idx_outbox_idempotency", table_name="outbox_events")
    op.drop_table("outbox_events")
```

**Step 2: Run migration (if DB available)**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

**Step 3: Commit**

```bash
git add backend/alembic/versions/013_outbox_events.py
git commit -m "feat(db): add migration for outbox_events table with idempotency"
```

---

## Task 8: Create Migration for OrderRecord Close Fields

**Files:**
- Create: `backend/alembic/versions/014_order_close_fields.py`

**Step 1: Create migration file**

Create `backend/alembic/versions/014_order_close_fields.py`:

```python
"""Add close request tracking fields to orders table.

Revision ID: 014_order_close_fields
Revises: 013_outbox_events
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "014_order_close_fields"
down_revision = "013_outbox_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add close_request_id to orders
    op.add_column(
        "orders",
        sa.Column(
            "close_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("close_requests.id"),
            nullable=True,
        ),
    )

    # Add broker update tracking
    op.add_column(
        "orders",
        sa.Column("broker_update_seq", sa.BigInteger, nullable=True),
    )

    op.add_column(
        "orders",
        sa.Column("last_broker_update_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Add reconciler retry tracking
    op.add_column(
        "orders",
        sa.Column(
            "reconcile_not_found_count", sa.Integer, nullable=False, server_default="0"
        ),
    )

    # Index for close_request queries
    op.create_index(
        "idx_orders_close_request",
        "orders",
        ["close_request_id"],
        postgresql_where=sa.text("close_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_orders_close_request", table_name="orders")
    op.drop_column("orders", "reconcile_not_found_count")
    op.drop_column("orders", "last_broker_update_at")
    op.drop_column("orders", "broker_update_seq")
    op.drop_column("orders", "close_request_id")
```

**Step 2: Commit**

```bash
git add backend/alembic/versions/014_order_close_fields.py
git commit -m "feat(db): add migration for order close request tracking fields"
```

---

## Task 9: Create CloseRequestRepository

**Files:**
- Create: `backend/src/db/repositories/close_request_repo.py`
- Test: `backend/tests/db/test_close_request_repo.py`

**Step 1: Write the failing test**

Create `backend/tests/db/test_close_request_repo.py`:

```python
"""Tests for CloseRequestRepository."""

import pytest
import pytest_asyncio
from uuid import uuid4

from src.models.close_request import CloseRequest, CloseRequestStatus
from src.db.repositories.close_request_repo import CloseRequestRepository


@pytest_asyncio.fixture
async def repo(db_session):
    """Create repository with test session."""
    return CloseRequestRepository(db_session)


@pytest.mark.asyncio
async def test_create_close_request(repo, db_session):
    """Should create a new close request."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.id is not None
    assert cr.position_id == 1
    assert cr.idempotency_key == "test-key"
    assert cr.status == CloseRequestStatus.PENDING


@pytest.mark.asyncio
async def test_get_by_position_and_key(repo, db_session):
    """Should find close request by position_id and idempotency_key."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    found = await repo.get_by_position_and_key(1, "test-key")
    assert found is not None
    assert found.id == cr.id


@pytest.mark.asyncio
async def test_get_by_position_and_key_not_found(repo):
    """Should return None when not found."""
    found = await repo.get_by_position_and_key(999, "nonexistent")
    assert found is None


@pytest.mark.asyncio
async def test_update_status(repo, db_session):
    """Should update close request status."""
    cr = await repo.create(
        position_id=1,
        idempotency_key="test-key",
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    await repo.update_status(cr.id, CloseRequestStatus.SUBMITTED)

    updated = await repo.get_by_id(cr.id)
    assert updated.status == CloseRequestStatus.SUBMITTED
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/db/test_close_request_repo.py -v`
Expected: FAIL with "No module named 'src.db.repositories.close_request_repo'"

**Step 3: Write minimal implementation**

Create `backend/src/db/repositories/close_request_repo.py`:

```python
"""Repository for CloseRequest operations."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.close_request import CloseRequest, CloseRequestStatus


class CloseRequestRepository:
    """Repository for close request database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        position_id: int,
        idempotency_key: str,
        symbol: str,
        side: str,
        asset_type: str,
        target_qty: int,
    ) -> CloseRequest:
        """Create a new close request."""
        cr = CloseRequest(
            id=uuid.uuid4(),
            position_id=position_id,
            idempotency_key=idempotency_key,
            status=CloseRequestStatus.PENDING,
            symbol=symbol,
            side=side,
            asset_type=asset_type,
            target_qty=target_qty,
            filled_qty=0,
            retry_count=0,
            max_retries=3,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(cr)
        await self.session.flush()
        return cr

    async def get_by_id(self, request_id: uuid.UUID) -> CloseRequest | None:
        """Get close request by ID."""
        result = await self.session.execute(
            select(CloseRequest).where(CloseRequest.id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_by_position_and_key(
        self, position_id: int, idempotency_key: str
    ) -> CloseRequest | None:
        """Get close request by position ID and idempotency key."""
        result = await self.session.execute(
            select(CloseRequest)
            .where(CloseRequest.position_id == position_id)
            .where(CloseRequest.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, request_id: uuid.UUID, status: CloseRequestStatus
    ) -> None:
        """Update close request status."""
        cr = await self.get_by_id(request_id)
        if cr:
            cr.status = status
            if status == CloseRequestStatus.SUBMITTED:
                cr.submitted_at = datetime.now(timezone.utc)
            elif status in (CloseRequestStatus.COMPLETED, CloseRequestStatus.FAILED):
                cr.completed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def increment_filled_qty(
        self, request_id: uuid.UUID, delta: int
    ) -> None:
        """Increment filled quantity."""
        cr = await self.get_by_id(request_id)
        if cr:
            cr.filled_qty += delta
            await self.session.flush()
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/db/test_close_request_repo.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/db/repositories/close_request_repo.py backend/tests/db/test_close_request_repo.py
git commit -m "feat(repo): add CloseRequestRepository with CRUD operations"
```

---

## Task 10: Create OutboxRepository

**Files:**
- Create: `backend/src/db/repositories/outbox_repo.py`
- Test: `backend/tests/db/test_outbox_repo.py`

**Step 1: Write the failing test**

Create `backend/tests/db/test_outbox_repo.py`:

```python
"""Tests for OutboxRepository."""

import pytest
import pytest_asyncio

from src.models.outbox import OutboxEvent, OutboxEventStatus
from src.db.repositories.outbox_repo import OutboxRepository


@pytest_asyncio.fixture
async def repo(db_session):
    """Create repository with test session."""
    return OutboxRepository(db_session)


@pytest.mark.asyncio
async def test_create_event(repo):
    """Should create a new outbox event."""
    event = await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123", "symbol": "AAPL"},
    )

    assert event.id is not None
    assert event.event_type == "SUBMIT_CLOSE_ORDER"
    assert event.status == OutboxEventStatus.PENDING


@pytest.mark.asyncio
async def test_claim_pending_events(repo):
    """Should claim pending events for processing."""
    await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "1"},
    )
    await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "2"},
    )

    events = await repo.claim_pending(limit=1)
    assert len(events) == 1
    assert events[0].status == OutboxEventStatus.PROCESSING


@pytest.mark.asyncio
async def test_mark_completed(repo):
    """Should mark event as completed."""
    event = await repo.create(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123"},
    )

    await repo.mark_completed(event.id)

    updated = await repo.get_by_id(event.id)
    assert updated.status == OutboxEventStatus.COMPLETED
    assert updated.processed_at is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/db/test_outbox_repo.py -v`
Expected: FAIL with "No module named 'src.db.repositories.outbox_repo'"

**Step 3: Write minimal implementation**

Create `backend/src/db/repositories/outbox_repo.py`:

```python
"""Repository for OutboxEvent operations."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.outbox import OutboxEvent, OutboxEventStatus


class OutboxRepository:
    """Repository for outbox event database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> OutboxEvent:
        """Create a new outbox event."""
        event = OutboxEvent(
            event_type=event_type,
            payload=payload,
            status=OutboxEventStatus.PENDING,
            created_at=datetime.now(timezone.utc),
            retry_count=0,
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_by_id(self, event_id: int) -> OutboxEvent | None:
        """Get outbox event by ID."""
        result = await self.session.execute(
            select(OutboxEvent).where(OutboxEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def claim_pending(self, limit: int = 1) -> list[OutboxEvent]:
        """Claim pending events for processing.

        Uses FOR UPDATE SKIP LOCKED for concurrent worker safety.
        """
        result = await self.session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxEventStatus.PENDING)
            .order_by(OutboxEvent.created_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = list(result.scalars().all())

        for event in events:
            event.status = OutboxEventStatus.PROCESSING

        await self.session.flush()
        return events

    async def mark_completed(self, event_id: int) -> None:
        """Mark event as completed."""
        event = await self.get_by_id(event_id)
        if event:
            event.status = OutboxEventStatus.COMPLETED
            event.processed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def mark_failed(self, event_id: int) -> None:
        """Mark event as failed."""
        event = await self.get_by_id(event_id)
        if event:
            event.status = OutboxEventStatus.FAILED
            event.processed_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def increment_retry(self, event_id: int) -> int:
        """Increment retry count and return new count."""
        event = await self.get_by_id(event_id)
        if event:
            event.retry_count += 1
            event.status = OutboxEventStatus.PENDING  # Reset to pending for retry
            await self.session.flush()
            return event.retry_count
        return 0
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/db/test_outbox_repo.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/db/repositories/outbox_repo.py backend/tests/db/test_outbox_repo.py
git commit -m "feat(repo): add OutboxRepository with claim and mark operations"
```

---

## Task 11: Implement close_position API Endpoint (Phase 1)

**Files:**
- Modify: `backend/src/api/options.py`
- Modify: `backend/src/options/models.py`
- Test: `backend/tests/api/test_close_position.py`

**Step 1: Write the failing test**

Create `backend/tests/api/test_close_position.py`:

```python
"""Tests for close_position API endpoint."""

import pytest
import pytest_asyncio
from uuid import uuid4

from src.models.position import Position, PositionStatus, AssetType


@pytest_asyncio.fixture
async def open_position(db_session):
    """Create an open position for testing."""
    pos = Position(
        account_id="ACC001",
        symbol="AAPL240119C00150000",
        asset_type=AssetType.OPTION,
        quantity=10,
        status=PositionStatus.OPEN,
    )
    db_session.add(pos)
    await db_session.flush()
    return pos


@pytest.mark.asyncio
async def test_close_position_creates_close_request(client, open_position):
    """Should create CloseRequest and return pending status."""
    response = await client.post(
        f"/api/options/{open_position.id}/close",
        json={},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["close_request_id"] is not None
    assert data["position_status"] == "closing"
    assert data["close_request_status"] == "pending"
    assert data["target_qty"] == 10


@pytest.mark.asyncio
async def test_close_position_idempotent(client, open_position):
    """Should return same response for same idempotency key."""
    key = str(uuid4())

    response1 = await client.post(
        f"/api/options/{open_position.id}/close",
        json={},
        headers={"Idempotency-Key": key},
    )
    response2 = await client.post(
        f"/api/options/{open_position.id}/close",
        json={},
        headers={"Idempotency-Key": key},
    )

    assert response1.status_code == 201
    assert response2.status_code == 200  # Idempotent replay
    assert response1.json()["close_request_id"] == response2.json()["close_request_id"]


@pytest.mark.asyncio
async def test_close_position_rejects_different_key_while_closing(client, open_position):
    """Should reject different key while position is CLOSING."""
    # First close request
    response1 = await client.post(
        f"/api/options/{open_position.id}/close",
        json={},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert response1.status_code == 201

    # Second close request with different key
    response2 = await client.post(
        f"/api/options/{open_position.id}/close",
        json={},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response2.status_code == 409
    assert response2.json()["detail"]["error"] == "position_already_closing"


@pytest.mark.asyncio
async def test_close_position_not_found(client):
    """Should return 404 for nonexistent position."""
    response = await client.post(
        "/api/options/99999/close",
        json={},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_close_position_zero_quantity(client, db_session):
    """Should reject position with zero quantity."""
    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        asset_type=AssetType.OPTION,
        quantity=0,
        status=PositionStatus.OPEN,
    )
    db_session.add(pos)
    await db_session.flush()

    response = await client.post(
        f"/api/options/{pos.id}/close",
        json={},
        headers={"Idempotency-Key": str(uuid4())},
    )

    assert response.status_code == 400
    assert "zero quantity" in response.json()["detail"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_close_position.py -v`
Expected: FAIL (various assertion failures)

**Step 3: Write implementation**

This is a larger change - update `backend/src/api/options.py` with the new close_position implementation. See design document Section 4 for the full implementation.

Update `backend/src/options/models.py` to add new response model fields.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_close_position.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/options.py backend/src/options/models.py backend/tests/api/test_close_position.py
git commit -m "feat(api): implement close_position with 3-phase transaction"
```

---

## Remaining Tasks (Summary)

### Task 12: Implement Outbox Worker
- Create `backend/src/workers/outbox_worker.py`
- Test with mocked broker/market data

### Task 13: Implement Order Update Handler
- Create `backend/src/workers/order_handler.py`
- Add `on_order_update` with monotonic progression

### Task 14: Implement Reconciler Jobs
- Create `backend/src/workers/reconciler.py`
- Zombie detection, stuck order recovery, auto-retry

### Task 15: Implement Outbox Cleaner Job
- Create `backend/src/workers/outbox_cleaner.py`
- Daily cleanup of old events

### Task 16: Integration Tests
- E2E test: close → fill → position closed
- Test partial fill + retry
- Test broker rejection + rollback

### Task 17: Wire Workers to Application
- Add startup/shutdown hooks to main.py
- Configure APScheduler for reconciler jobs

---

## Execution Notes

- Run all tests before each commit: `pytest -v`
- Migrations require PostgreSQL - skip if using SQLite for tests
- Workers need event loop management - test with `pytest-asyncio`
