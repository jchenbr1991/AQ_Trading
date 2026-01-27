# Close Position Flow Design

MVP for options position closing: idempotency + state machine + OrderManager + fill callback.

## 1. State Machine

```
OPEN ─────────────────────────────────────────────┐
  │                                               │
  │ close_request created                         │
  ▼                                               │
CLOSING ──────────────────────────────────────────┤
  │         │              │              │       │
  │ FILLED  │ PARTIAL+     │ REJECT/      │ ERROR │
  │ (全成)  │ CANCEL       │ CANCEL       │       │
  │         │ (部分成交)   │ (0成交)      │       │
  ▼         ▼              │              ▼       │
CLOSED   CLOSE_RETRYABLE   │        CLOSE_FAILED  │
         (可自动重试)       │        (需人工介入)   │
                           │                      │
                           └──────────────────────┘
                              回退 OPEN (filled_qty==0)
```

### Status Definitions

| Status | Description | Next Actions |
|--------|-------------|--------------|
| `OPEN` | Normal position, can be closed | Accept close request |
| `CLOSING` | Close order(s) in flight | Wait for fills |
| `CLOSED` | Fully closed, qty=0 | Archive |
| `CLOSE_RETRYABLE` | Partial fill + order cancelled, can auto-retry | Reconciler auto-retries |
| `CLOSE_FAILED` | Broker rejection, risk block, needs human | Manual intervention |

## 2. Data Model

### New Table: close_requests

```sql
CREATE TABLE close_requests (
    id UUID PRIMARY KEY,
    position_id INTEGER NOT NULL REFERENCES positions(id),
    idempotency_key VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending → submitted → completed/failed/retryable

    target_qty INTEGER NOT NULL,          -- requested close quantity
    filled_qty INTEGER NOT NULL DEFAULT 0, -- aggregate from all orders
    remaining_qty INTEGER GENERATED ALWAYS AS (target_qty - filled_qty) STORED,

    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    submitted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    UNIQUE(position_id, idempotency_key)
);

CREATE INDEX idx_close_requests_position ON close_requests(position_id);
CREATE INDEX idx_close_requests_status ON close_requests(status) WHERE status IN ('pending', 'submitted');
```

### Position Table Changes

```sql
ALTER TABLE positions ADD COLUMN active_close_request_id UUID REFERENCES close_requests(id);
ALTER TABLE positions ADD COLUMN closed_at TIMESTAMPTZ;
-- status already exists: OPEN, CLOSING, CLOSED, CLOSE_RETRYABLE, CLOSE_FAILED
```

### OrderRecord Changes

```sql
ALTER TABLE orders ADD COLUMN close_request_id UUID REFERENCES close_requests(id);
ALTER TABLE orders ADD COLUMN broker_update_seq BIGINT;  -- NULL if broker doesn't provide
ALTER TABLE orders ADD COLUMN last_broker_update_at TIMESTAMPTZ;
ALTER TABLE orders ADD COLUMN reconcile_not_found_count INTEGER DEFAULT 0;  -- for reconciler retry

CREATE INDEX idx_orders_close_request ON orders(close_request_id) WHERE close_request_id IS NOT NULL;
```

### Outbox Table (for reliable order submission)

```sql
CREATE TABLE outbox_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- pending → processing → completed/failed

    -- Generated column for unique constraint (PostgreSQL 12+)
    close_request_id TEXT GENERATED ALWAYS AS (payload->>'close_request_id') STORED,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    retry_count INTEGER NOT NULL DEFAULT 0
);

-- Unique constraint on generated column (proper PostgreSQL syntax)
CREATE UNIQUE INDEX idx_outbox_idempotency
    ON outbox_events(event_type, close_request_id)
    WHERE close_request_id IS NOT NULL;

-- Index for pending events (worker query)
CREATE INDEX idx_outbox_pending ON outbox_events(created_at) WHERE status = 'pending';

-- Index for cleanup job
CREATE INDEX idx_outbox_completed ON outbox_events(created_at) WHERE status = 'completed';
```

## 3. API Contract

### POST /options/{position_id}/close

**Request:**
```
Header: Idempotency-Key: <uuid>
Body: {} (empty for MVP, later: {qty, price, order_type})
```

**Response (201 Created):**
```json
{
    "close_request_id": "uuid",
    "position_id": 123,
    "position_status": "CLOSING",
    "close_request_status": "pending",
    "target_qty": 100,
    "filled_qty": 0,
    "orders": [],
    "poll_url": "/api/options/close-requests/{close_request_id}",
    "poll_interval_ms": 1000
}
```

**Response (200 OK) - Idempotent replay:**
```json
{
    "close_request_id": "uuid",
    "position_id": 123,
    "position_status": "CLOSING",
    "target_qty": 100,
    "orders": [{"order_id": "...", "status": "SUBMITTED", "filled_qty": 0}]
}
```

**Response (409 Conflict) - Different key while CLOSING:**
```json
{
    "error": "position_already_closing",
    "active_close_request_id": "uuid",
    "message": "Position is being closed by another request"
}
```

## 4. Core Flow (3-Phase Transaction)

```python
async def close_position(position_id: int, idempotency_key: str) -> ClosePositionResponse:
    """
    Phase 1: Quick lock + mark CLOSING (short DB transaction)
    Phase 2: Outbox event (async order submission)
    Phase 3: Worker processes outbox → calls broker → updates result
    """

    # ══════════════════════════════════════════════════════════
    # PHASE 1: Lock, validate, create CloseRequest (DB transaction)
    # ══════════════════════════════════════════════════════════
    try:
        async with db.begin():
            # 1.1 Pessimistic lock on position (with timeout for user-facing API)
            # SET LOCAL applies only to this transaction
            await db.execute(text("SET LOCAL lock_timeout = '2s'"))

            position = await db.execute(
                select(Position)
                .where(Position.id == position_id)
                .with_for_update()
            ).scalar_one_or_none()

            if not position:
                raise HTTPException(404, "Position not found")
    except asyncpg.exceptions.LockNotAvailableError:
        # Another request is processing this position
        raise HTTPException(
            status_code=409,
            detail={
                "error": "position_locked",
                "message": "Position is being processed, please retry",
                "retry_after_ms": 1000,
            }
        )

        # 1.2 Idempotency check
        existing_request = await db.execute(
            select(CloseRequest)
            .where(CloseRequest.position_id == position_id)
            .where(CloseRequest.idempotency_key == idempotency_key)
        ).scalar_one_or_none()

        if existing_request:
            # Idempotent replay - return existing request
            return await build_response(existing_request, position)

        # 1.3 State validation
        if position.status == PositionStatus.CLOSING:
            raise HTTPException(409, detail={
                "error": "position_already_closing",
                "active_close_request_id": str(position.active_close_request_id)
            })

        if position.status != PositionStatus.OPEN:
            raise HTTPException(400, f"Cannot close position in {position.status} state")

        if position.quantity == 0:
            raise HTTPException(400, "Position already has zero quantity")

        # 1.4 Create CloseRequest
        close_request = CloseRequest(
            id=uuid4(),
            position_id=position_id,
            idempotency_key=idempotency_key,
            status=CloseRequestStatus.PENDING,
            target_qty=abs(position.quantity),
        )
        db.add(close_request)

        # 1.5 Update position state
        position.status = PositionStatus.CLOSING
        position.active_close_request_id = close_request.id

        # 1.6 Write outbox event (atomic with above)
        outbox_event = OutboxEvent(
            event_type="SUBMIT_CLOSE_ORDER",
            payload={
                "close_request_id": str(close_request.id),
                "position_id": position_id,
                "symbol": position.symbol,
                "side": "sell" if position.quantity > 0 else "buy",
                "qty": abs(position.quantity),
                "asset_type": position.asset_type,
            }
        )
        db.add(outbox_event)

    # Transaction committed, lock released
    # Phase 2 & 3 happen async via outbox worker

    return ClosePositionResponse(
        close_request_id=str(close_request.id),
        position_id=position_id,
        position_status=position.status,
        target_qty=close_request.target_qty,
        orders=[],
    )
```

## 5. Outbox Worker

```python
async def process_outbox():
    """
    Runs every 1 second, processes pending outbox events.
    Handles SUBMIT_CLOSE_ORDER events.
    """
    while True:
        async with db.begin():
            # Claim oldest pending event with lock
            event = await db.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == "pending")
                .order_by(OutboxEvent.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()

            if not event:
                await asyncio.sleep(1)
                continue

            event.status = "processing"

        # Outside transaction: call broker
        try:
            if event.event_type == "SUBMIT_CLOSE_ORDER":
                await handle_submit_close_order(event.payload)

            async with db.begin():
                event.status = "completed"
                event.processed_at = utcnow()

        except Exception as e:
            async with db.begin():
                event.retry_count += 1
                if event.retry_count >= 3:
                    event.status = "failed"
                    await handle_outbox_failure(event)
                else:
                    event.status = "pending"  # retry


async def handle_submit_close_order(payload: dict):
    """Submit order to broker, update CloseRequest and OrderRecord."""
    close_request_id = payload["close_request_id"]

    async with db.begin():
        close_request = await db.get(CloseRequest, close_request_id)
        if close_request.status != CloseRequestStatus.PENDING:
            return  # Already processed (idempotent)

    # Call broker (outside transaction)
    order = await order_manager.submit_order(
        symbol=payload["symbol"],
        side=payload["side"],
        qty=payload["qty"],
        order_type="market",  # MVP: market order
        close_request_id=close_request_id,
    )

    # Update result
    async with db.begin():
        close_request = await db.get(CloseRequest, close_request_id)

        if order.status == OrderStatus.REJECTED:
            # Immediate rejection - rollback
            close_request.status = CloseRequestStatus.FAILED
            position = await db.get(Position, close_request.position_id)
            position.status = PositionStatus.CLOSE_FAILED
            position.active_close_request_id = None
        else:
            close_request.status = CloseRequestStatus.SUBMITTED
            close_request.submitted_at = utcnow()
            # OrderRecord created by OrderManager with close_request_id
```

## 6. Order Update Handler (Idempotent + Monotonic)

```python
# Terminal states - once reached, cannot change
TERMINAL_STATES = frozenset({"FILLED", "CANCELLED", "REJECTED", "EXPIRED"})

# Status progression order (for monotonic updates)
# FILLED is highest - once filled, nothing can override it
STATUS_ORDER = {
    "NEW": 0,
    "SUBMITTED": 1,
    "PARTIAL": 2,
    "CANCELLED": 3,
    "REJECTED": 3,
    "EXPIRED": 3,
    "FILLED": 4,  # Highest - terminal success state
}

async def on_order_update(
    order_id: str,
    broker_status: str,
    filled_qty: int,
    broker_update_seq: int | None = None,  # from broker push (may be None)
):
    """
    Handle broker order updates with idempotency and monotonic progression.

    NOTE: broker_update_seq may be None if broker doesn't provide sequence numbers.
    In that case, we rely purely on STATUS_ORDER for monotonic progression.
    """
    async with db.begin():
        # Lock the order record
        order = await db.execute(
            select(OrderRecord)
            .where(OrderRecord.broker_order_id == order_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not order:
            logger.warning(f"Unknown order update: {order_id}")
            return

        # Idempotency: skip if already processed this update (when seq available)
        if broker_update_seq is not None and order.broker_update_seq is not None:
            if broker_update_seq <= order.broker_update_seq:
                logger.debug(f"Skipping stale update for {order_id}")
                return

        # Terminal state check: once FILLED, never change status
        if order.status in TERMINAL_STATES:
            if order.status == "FILLED":
                logger.debug(f"Order {order_id} already FILLED, ignoring {broker_status}")
                return
            # Other terminal states: still update filled_qty if higher
            order.filled_qty = max(order.filled_qty, filled_qty)
            order.broker_update_seq = broker_update_seq
            return

        # Monotonic: only allow forward status progression
        current_priority = STATUS_ORDER.get(order.status, 0)
        new_priority = STATUS_ORDER.get(broker_status, 0)

        if new_priority < current_priority:
            logger.warning(f"Ignoring backward status: {order.status} -> {broker_status}")
            # But still update filled_qty if higher
            order.filled_qty = max(order.filled_qty, filled_qty)
            order.broker_update_seq = broker_update_seq
            return

        # Update order
        order.status = broker_status
        order.filled_qty = max(order.filled_qty, filled_qty)
        order.broker_update_seq = broker_update_seq
        order.last_broker_update_at = utcnow()

        # If this order is part of a close request, update it
        if order.close_request_id:
            await update_close_request_from_order(order)


async def update_close_request_from_order(order: OrderRecord):
    """
    Aggregate filled_qty from all orders and update CloseRequest/Position.

    IMPORTANT: position.quantity is NOT modified here.
    It should only be updated via broker reconciliation to avoid double-counting.
    We only update PositionStatus to reflect the close request state.
    """
    # Lock CloseRequest to ensure consistent aggregation
    close_request = await db.execute(
        select(CloseRequest)
        .where(CloseRequest.id == order.close_request_id)
        .with_for_update()
    ).scalar_one()

    position = await db.get(Position, close_request.position_id)

    # Save previous filled_qty for delta calculation (if needed later)
    prev_filled_qty = close_request.filled_qty

    # Aggregate filled_qty from all orders for this close_request
    total_filled = await db.execute(
        select(func.coalesce(func.sum(OrderRecord.filled_qty), 0))
        .where(OrderRecord.close_request_id == close_request.id)
    ).scalar()

    close_request.filled_qty = total_filled

    # Check if all orders are in terminal state
    orders = await db.execute(
        select(OrderRecord)
        .where(OrderRecord.close_request_id == close_request.id)
    ).scalars().all()

    all_terminal = all(o.status in TERMINAL_STATES for o in orders)
    all_filled = all(o.status == "FILLED" for o in orders)

    if not all_terminal:
        return  # Still waiting for order updates

    if all_filled and close_request.remaining_qty == 0:
        # Fully closed
        close_request.status = CloseRequestStatus.COMPLETED
        close_request.completed_at = utcnow()
        position.status = PositionStatus.CLOSED
        position.closed_at = utcnow()
        position.active_close_request_id = None
        # NOTE: position.quantity will be updated by broker reconciliation job
        # to ensure accuracy. We do NOT modify it here.

    elif close_request.filled_qty == 0:
        # Zero fill - safe to rollback to OPEN
        close_request.status = CloseRequestStatus.FAILED
        position.status = PositionStatus.OPEN
        position.active_close_request_id = None

    elif close_request.filled_qty > 0 and close_request.remaining_qty > 0:
        # Partial fill - can retry
        close_request.status = CloseRequestStatus.RETRYABLE
        position.status = PositionStatus.CLOSE_RETRYABLE
        # NOTE: position.quantity NOT modified - reconciler will sync from broker
```

## 7. Reconciler Job

```python
async def reconcile_closing_positions():
    """
    Runs every 5 minutes. Handles:
    1. Zombie requests (PENDING but no order sent)
    2. Stuck CLOSING (orders not updating)
    3. CLOSE_RETRYABLE auto-retry
    """
    now = utcnow()

    # ══════════════════════════════════════════════════════════
    # Case 1: Zombie requests (stuck in PENDING for >2 minutes)
    # ══════════════════════════════════════════════════════════
    zombie_requests = await db.execute(
        select(CloseRequest)
        .where(CloseRequest.status == CloseRequestStatus.PENDING)
        .where(CloseRequest.created_at < now - timedelta(minutes=2))
    ).scalars().all()

    for request in zombie_requests:
        logger.warning(f"Zombie close_request: {request.id}")
        # Check if there's an unprocessed outbox event
        outbox = await db.execute(
            select(OutboxEvent)
            .where(OutboxEvent.payload["close_request_id"].astext == str(request.id))
            .where(OutboxEvent.status == "pending")
        ).scalar_one_or_none()

        if outbox:
            # Outbox exists but not processed - let outbox worker handle
            continue

        # No outbox event - system crashed before writing it
        # Safe to rollback
        async with db.begin():
            request.status = CloseRequestStatus.FAILED
            position = await db.get(Position, request.position_id)
            position.status = PositionStatus.OPEN
            position.active_close_request_id = None

    # ══════════════════════════════════════════════════════════
    # Case 2: Stuck SUBMITTED (no updates for >10 minutes)
    # ══════════════════════════════════════════════════════════
    stuck_requests = await db.execute(
        select(CloseRequest)
        .where(CloseRequest.status == CloseRequestStatus.SUBMITTED)
        .where(CloseRequest.submitted_at < now - timedelta(minutes=10))
    ).scalars().all()

    for request in stuck_requests:
        # Query broker for all orders in this request
        orders = await db.execute(
            select(OrderRecord)
            .where(OrderRecord.close_request_id == request.id)
        ).scalars().all()

        for order in orders:
            if order.broker_order_id:
                try:
                    broker_status = await broker.query_order(order.broker_order_id)
                    await on_order_update(
                        order.broker_order_id,
                        broker_status.status,
                        broker_status.filled_qty,
                        broker_status.update_seq,
                    )
                except OrderNotFound:
                    # Order doesn't exist at broker - could be:
                    # 1. Order too old (archived)
                    # 2. broker_order_id mismatch
                    # 3. Temporary API issue
                    # DO NOT immediately mark as REJECTED - retry first
                    order.reconcile_not_found_count = (order.reconcile_not_found_count or 0) + 1
                    if order.reconcile_not_found_count >= 3:
                        # After 3 failed lookups, mark as CLOSE_FAILED for human review
                        logger.error(f"Order {order.broker_order_id} not found after 3 attempts")
                        async with db.begin():
                            close_request = await db.get(CloseRequest, order.close_request_id)
                            position = await db.get(Position, close_request.position_id)
                            close_request.status = CloseRequestStatus.FAILED
                            position.status = PositionStatus.CLOSE_FAILED
                            # Emit alert for human intervention
                            await emit_alert(
                                AlertType.ORDER_RECONCILE_FAILED,
                                f"Order {order.broker_order_id} not found at broker"
                            )
                except BrokerAPIError as e:
                    logger.warning(f"Broker API error for {order.broker_order_id}: {e}")

    # ══════════════════════════════════════════════════════════
    # Case 3: Auto-retry CLOSE_RETRYABLE
    # ══════════════════════════════════════════════════════════
    retryable_requests = await db.execute(
        select(CloseRequest)
        .where(CloseRequest.status == CloseRequestStatus.RETRYABLE)
        .where(CloseRequest.retry_count < CloseRequest.max_retries)
    ).scalars().all()

    for request in retryable_requests:
        async with db.begin():
            position = await db.get(Position, request.position_id)

            # Create new outbox event for remaining qty
            outbox_event = OutboxEvent(
                event_type="SUBMIT_CLOSE_ORDER",
                payload={
                    "close_request_id": str(request.id),
                    "position_id": request.position_id,
                    "symbol": position.symbol,
                    "side": "sell" if position.quantity > 0 else "buy",
                    "qty": request.remaining_qty,
                    "asset_type": position.asset_type,
                    "is_retry": True,
                }
            )
            db.add(outbox_event)

            request.status = CloseRequestStatus.SUBMITTED
            request.retry_count += 1
            position.status = PositionStatus.CLOSING
```

## 8. Outbox Cleaner Job

```python
async def cleanup_outbox():
    """
    Runs daily at 3 AM. Removes old completed/failed outbox events.
    Prevents table bloat and vacuum performance issues.
    """
    retention_days = 3

    async with db.begin():
        deleted = await db.execute(
            delete(OutboxEvent)
            .where(OutboxEvent.status.in_(["completed", "failed"]))
            .where(OutboxEvent.created_at < utcnow() - timedelta(days=retention_days))
            .returning(OutboxEvent.id)
        )
        count = len(deleted.fetchall())
        logger.info(f"Cleaned up {count} old outbox events")
```

## 9. Status Invariants

The system maintains these invariants between Position and CloseRequest status:

| Position Status | CloseRequest Status | Invariant |
|-----------------|--------------------|----|
| `OPEN` | (none or FAILED) | No active close request |
| `CLOSING` | `PENDING` or `SUBMITTED` | Exactly one active close request |
| `CLOSED` | `COMPLETED` | Close request fully filled |
| `CLOSE_RETRYABLE` | `RETRYABLE` | Partial fill, awaiting retry |
| `CLOSE_FAILED` | `FAILED` | Terminal failure, needs human |

**Reconciler invariant check:**

```python
async def check_status_invariants():
    """Find and fix inconsistent Position/CloseRequest status pairs."""

    # Find positions in CLOSING but no active close request
    orphaned = await db.execute(
        select(Position)
        .where(Position.status == PositionStatus.CLOSING)
        .where(Position.active_close_request_id.is_(None))
    ).scalars().all()

    for pos in orphaned:
        logger.error(f"Invariant violation: Position {pos.id} CLOSING but no active request")
        pos.status = PositionStatus.CLOSE_FAILED

    # Find close requests SUBMITTED but position not CLOSING
    mismatched = await db.execute(
        select(CloseRequest)
        .join(Position)
        .where(CloseRequest.status == CloseRequestStatus.SUBMITTED)
        .where(Position.status != PositionStatus.CLOSING)
    ).scalars().all()

    for req in mismatched:
        logger.error(f"Invariant violation: CloseRequest {req.id} SUBMITTED but position not CLOSING")
        # Fix by syncing position to close request state
```

## 10. Enums and Constants

```python
class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    CLOSE_RETRYABLE = "close_retryable"
    CLOSE_FAILED = "close_failed"

class CloseRequestStatus(str, Enum):
    PENDING = "pending"       # Created, waiting for outbox
    SUBMITTED = "submitted"   # Order(s) sent to broker
    COMPLETED = "completed"   # Fully filled
    RETRYABLE = "retryable"   # Partial fill, can auto-retry
    FAILED = "failed"         # Terminal failure, needs human
```

## 11. File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `models/close_request.py` | NEW | CloseRequest model |
| `models/outbox.py` | NEW | OutboxEvent model |
| `models/position.py` | MODIFY | Add CLOSE_RETRYABLE, CLOSE_FAILED statuses |
| `models/order.py` | MODIFY | Add close_request_id, broker_update_seq, reconcile_not_found_count |
| `db/repositories/close_request_repo.py` | NEW | CloseRequest CRUD |
| `db/repositories/outbox_repo.py` | NEW | Outbox operations |
| `api/options.py` | MODIFY | Implement close_position with 3-phase, add GET /close-requests/{id} |
| `orders/manager.py` | MODIFY | Accept close_request_id, wire fill callback |
| `workers/outbox_worker.py` | NEW | Process outbox events |
| `workers/reconciler.py` | NEW | Reconcile stuck positions + invariant checks |
| `workers/outbox_cleaner.py` | NEW | Daily cleanup of old outbox events |
| `alembic/versions/012_close_requests.py` | NEW | Migration |
| `alembic/versions/013_outbox.py` | NEW | Migration |

## 12. Testing Scenarios

1. **Happy path**: OPEN → close request → CLOSING → FILLED → CLOSED
2. **Idempotent replay**: Same key returns same response
3. **Concurrent requests**: Different key while CLOSING → 409
4. **Lock timeout**: Position locked by another request → 409 with retry hint
5. **Broker rejection**: Immediate rollback to CLOSE_FAILED
6. **Partial fill + cancel**: CLOSE_RETRYABLE → auto-retry (up to max_retries)
7. **Zero fill + cancel**: Rollback to OPEN
8. **Zombie request**: Crash after CLOSING, before order → reconciler fixes
9. **Out-of-order updates**: Monotonic progression prevents FILLED→CANCELLED regression
10. **Stuck order**: Reconciler queries broker and updates
11. **Order not found at broker**: 3 retries before CLOSE_FAILED
12. **Status invariant violation**: Reconciler detects and fixes inconsistent states
13. **Retry count limit**: After max_retries, stops auto-retry
14. **Outbox cleanup**: Old completed events deleted after retention period

## 13. Future Enhancements (V2)

- [ ] Position reconciliation with broker holdings
- [ ] Limit order support with price parameter
- [ ] Manual retry endpoint for CLOSE_FAILED
- [ ] Split orders for large positions
- [ ] Webhook notifications on state changes
- [ ] Batch close for multiple positions
