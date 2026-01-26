# Slice 3.1: Alert System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Multi-channel notifications (Email + Webhook) for trading events and system health with deduplication, throttling, and delivery reliability.

**Architecture:** AlertService receives events from business modules, applies throttling via DB dedupe_key, routes to NotificationHub which delivers async with retry. All alerts and delivery attempts are persisted.

**Tech Stack:** Python 3.11+, FastAPI, asyncpg, aiosmtplib, httpx, Pydantic

---

## Task 1: Alert Models

**Files:**
- Create: `backend/src/alerts/models.py`
- Test: `backend/tests/alerts/test_models.py`

**Step 1: Write failing test for AlertType enum**

```python
# backend/tests/alerts/test_models.py
"""Tests for alert models."""

import pytest
from src.alerts.models import AlertType, Severity, RECOVERY_TYPES


class TestAlertType:
    def test_alert_type_values(self):
        """AlertType enum has expected values."""
        assert AlertType.ORDER_REJECTED.value == "order_rejected"
        assert AlertType.DAILY_LOSS_LIMIT.value == "daily_loss_limit"
        assert AlertType.COMPONENT_UNHEALTHY.value == "component_unhealthy"
        assert AlertType.COMPONENT_RECOVERED.value == "component_recovered"
        assert AlertType.ALERT_DELIVERY_FAILED.value == "alert_delivery_failed"

    def test_recovery_types_contains_component_recovered(self):
        """RECOVERY_TYPES includes component_recovered."""
        assert AlertType.COMPONENT_RECOVERED in RECOVERY_TYPES


class TestSeverity:
    def test_severity_ordering(self):
        """SEV1 < SEV2 < SEV3 (lower = more critical)."""
        assert Severity.SEV1.value < Severity.SEV2.value < Severity.SEV3.value
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/alerts/test_models.py::TestAlertType -v
```

Expected: `ModuleNotFoundError: No module named 'src.alerts'`

**Step 3: Write minimal implementation**

```python
# backend/src/alerts/models.py
"""Alert system models."""

from enum import Enum


class AlertType(str, Enum):
    """Types of alerts the system can emit."""

    # Trading events
    ORDER_REJECTED = "order_rejected"
    ORDER_FILLED = "order_filled"
    POSITION_LIMIT_HIT = "position_limit_hit"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"

    # System events
    COMPONENT_UNHEALTHY = "component_unhealthy"
    COMPONENT_RECOVERED = "component_recovered"
    DB_WRITE_FAIL = "db_write_fail"
    STORAGE_THRESHOLD = "storage_threshold"
    ALERT_DELIVERY_FAILED = "alert_delivery_failed"


class Severity(int, Enum):
    """Alert severity levels. Lower value = more critical."""

    SEV1 = 1  # Critical - requires immediate action
    SEV2 = 2  # Warning - needs attention
    SEV3 = 3  # Info - for logging only


# Recovery event types (bypass throttling)
RECOVERY_TYPES: frozenset[AlertType] = frozenset({
    AlertType.COMPONENT_RECOVERED,
})
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/alerts/test_models.py -v
```

Expected: PASS

**Step 5: Add AlertEvent dataclass test**

```python
# Append to backend/tests/alerts/test_models.py

from datetime import datetime, timezone
from uuid import UUID

from src.alerts.models import AlertEvent, EntityRef


class TestAlertEvent:
    def test_create_alert_event(self):
        """Can create AlertEvent with all fields."""
        event = AlertEvent(
            alert_id=UUID("12345678-1234-5678-1234-567812345678"),
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            event_timestamp=datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc),
            fingerprint="order_filled:ACC001:AAPL:",
            entity_ref=EntityRef(account_id="ACC001", symbol="AAPL"),
            summary="Order filled: BUY 100 AAPL @ 150.00",
            details={"order_id": "ORD123", "fill_price": "150.00"},
        )
        assert event.type == AlertType.ORDER_FILLED
        assert event.severity == Severity.SEV2
        assert event.entity_ref.account_id == "ACC001"

    def test_alert_event_is_frozen(self):
        """AlertEvent is immutable."""
        event = AlertEvent(
            alert_id=UUID("12345678-1234-5678-1234-567812345678"),
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            event_timestamp=datetime.now(timezone.utc),
            fingerprint="test",
            entity_ref=None,
            summary="Test",
            details={},
        )
        with pytest.raises(AttributeError):
            event.summary = "Modified"
```

**Step 6: Implement AlertEvent and EntityRef**

```python
# Append to backend/src/alerts/models.py

from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias
from uuid import UUID


# JSON-safe types
JsonScalar: TypeAlias = str | int | float | bool | None


@dataclass(frozen=True)
class EntityRef:
    """Reference to business entity associated with alert."""

    account_id: str | None = None
    symbol: str | None = None
    strategy_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class AlertEvent:
    """Immutable alert event.

    Attributes:
        alert_id: Unique identifier
        type: Alert type enum
        severity: SEV1/SEV2/SEV3
        event_timestamp: When event occurred (must be UTC)
        fingerprint: Deduplication key base
        entity_ref: Optional business entity reference
        summary: Short description (max 255 chars)
        details: JSON-safe context dict
    """

    alert_id: UUID
    type: AlertType
    severity: Severity
    event_timestamp: datetime
    fingerprint: str
    entity_ref: EntityRef | None
    summary: str
    details: dict[str, JsonScalar]
```

**Step 7: Run all model tests**

```bash
cd backend && pytest tests/alerts/test_models.py -v
```

Expected: All PASS

**Step 8: Create __init__.py and commit**

```python
# backend/src/alerts/__init__.py
"""Alert system package."""

from src.alerts.models import (
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    RECOVERY_TYPES,
    Severity,
)

__all__ = [
    "AlertEvent",
    "AlertType",
    "EntityRef",
    "JsonScalar",
    "RECOVERY_TYPES",
    "Severity",
]
```

```bash
# backend/tests/alerts/__init__.py
# (empty file)
```

```bash
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add alert models - AlertType, Severity, AlertEvent"
```

---

## Task 2: JSON Serialization Utilities

**Files:**
- Modify: `backend/src/alerts/models.py`
- Test: `backend/tests/alerts/test_models.py`

**Step 1: Write failing test for to_json_safe**

```python
# Append to backend/tests/alerts/test_models.py

from decimal import Decimal
from uuid import uuid4

from src.alerts.models import to_json_safe, sanitize_details


class TestJsonSerialization:
    def test_to_json_safe_primitives(self):
        """Primitives pass through unchanged."""
        assert to_json_safe(None) is None
        assert to_json_safe("hello") == "hello"
        assert to_json_safe(42) == 42
        assert to_json_safe(3.14) == 3.14
        assert to_json_safe(True) is True

    def test_to_json_safe_decimal(self):
        """Decimal converts to string."""
        assert to_json_safe(Decimal("123.45")) == "123.45"

    def test_to_json_safe_datetime(self):
        """Datetime converts to ISO string."""
        dt = datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc)
        assert to_json_safe(dt) == "2026-01-25T12:00:00+00:00"

    def test_to_json_safe_uuid(self):
        """UUID converts to string."""
        uid = UUID("12345678-1234-5678-1234-567812345678")
        assert to_json_safe(uid) == "12345678-1234-5678-1234-567812345678"

    def test_to_json_safe_exception(self):
        """Exception converts to type: message."""
        err = ValueError("test error")
        assert to_json_safe(err) == "ValueError: test error"


class TestSanitizeDetails:
    def test_sanitize_small_dict(self):
        """Small dict passes through with conversion."""
        details = {"price": Decimal("150.00"), "qty": 100}
        result = sanitize_details(details)
        assert result == {"price": "150.00", "qty": 100}

    def test_sanitize_truncates_large_dict(self):
        """Large dict gets truncated with marker."""
        details = {f"key_{i}": "x" * 100 for i in range(100)}
        result = sanitize_details(details)
        assert "_truncated" in result
        assert len(result) <= 21  # 20 keys + _truncated

    def test_sanitize_truncates_long_strings(self):
        """Long string values get truncated."""
        details = {"long_value": "x" * 1000}
        result = sanitize_details(details)
        assert len(result["long_value"]) <= 525  # 512 + "[truncated]"
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/alerts/test_models.py::TestJsonSerialization -v
```

Expected: `ImportError: cannot import name 'to_json_safe'`

**Step 3: Implement serialization utilities**

```python
# Append to backend/src/alerts/models.py

import json
from decimal import Decimal
from typing import Any

MAX_DETAILS_BYTES = 8192
MAX_STRING_VALUE_LENGTH = 512
MAX_KEYS = 20


def to_json_safe(obj: Any) -> JsonScalar:
    """Convert any object to JSON-safe scalar."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Exception):
        return f"{type(obj).__name__}: {obj}"
    return str(obj)


def sanitize_details(
    details: dict[str, Any],
    max_size: int = MAX_DETAILS_BYTES,
) -> dict[str, JsonScalar]:
    """Ensure details is JSON-safe and within size limit.

    Args:
        details: Raw details dict
        max_size: Maximum size in bytes (default 8KB)

    Returns:
        Sanitized dict that is JSON-serializable and within size limit
    """
    # Step 1: Convert to JSON-safe
    safe = {k: to_json_safe(v) for k, v in details.items()}

    # Step 2: Check size
    if _check_size(safe) <= max_size:
        return safe

    # Step 3: Truncate - keep first N keys
    safe = dict(list(safe.items())[:MAX_KEYS])
    safe["_truncated"] = True

    # Step 4: If still too large, truncate string values
    if _check_size(safe) <= max_size:
        return safe

    for key, value in safe.items():
        if isinstance(value, str) and len(value) > MAX_STRING_VALUE_LENGTH:
            safe[key] = value[:MAX_STRING_VALUE_LENGTH] + "...[truncated]"

    # Step 5: Final check
    if _check_size(safe) > max_size:
        return {"_truncated": True, "_error": "details too large"}

    return safe


def _check_size(obj: dict) -> int:
    """Get JSON-encoded size in bytes."""
    return len(json.dumps(obj).encode("utf-8"))
```

**Step 4: Update exports and run tests**

```python
# Update backend/src/alerts/__init__.py exports
from src.alerts.models import (
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    RECOVERY_TYPES,
    Severity,
    sanitize_details,
    to_json_safe,
)

__all__ = [
    "AlertEvent",
    "AlertType",
    "EntityRef",
    "JsonScalar",
    "RECOVERY_TYPES",
    "Severity",
    "sanitize_details",
    "to_json_safe",
]
```

```bash
cd backend && pytest tests/alerts/test_models.py -v
```

Expected: All PASS

**Step 5: Commit**

```bash
git add backend/src/alerts
git commit -m "feat(alerts): add JSON serialization utilities"
```

---

## Task 3: Alert Factory and Validation

**Files:**
- Create: `backend/src/alerts/factory.py`
- Test: `backend/tests/alerts/test_factory.py`

**Step 1: Write failing test**

```python
# backend/tests/alerts/test_factory.py
"""Tests for alert factory."""

import pytest
from datetime import datetime, timezone
from uuid import UUID

from src.alerts.factory import create_alert, compute_dedupe_key, validate_alert
from src.alerts.models import AlertType, Severity, AlertEvent, RECOVERY_TYPES


class TestCreateAlert:
    def test_create_alert_generates_uuid(self):
        """create_alert generates UUID if not provided."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test alert",
            account_id="ACC001",
            symbol="AAPL",
        )
        assert isinstance(alert.alert_id, UUID)

    def test_create_alert_uses_utc_timestamp(self):
        """create_alert uses UTC timestamp."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )
        assert alert.event_timestamp.tzinfo == timezone.utc

    def test_create_alert_builds_fingerprint(self):
        """create_alert builds fingerprint from type and entity."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="Test",
            account_id="ACC001",
            symbol="AAPL",
            strategy_id="MOM01",
        )
        assert alert.fingerprint == "order_rejected:ACC001:AAPL:MOM01"

    def test_create_alert_sanitizes_details(self):
        """create_alert sanitizes details dict."""
        from decimal import Decimal
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
            details={"price": Decimal("150.00")},
        )
        assert alert.details["price"] == "150.00"


class TestComputeDedupeKey:
    def test_normal_event_uses_bucket(self):
        """Normal events use 10-minute time bucket."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="Test",
            timestamp=datetime(2026, 1, 25, 12, 5, 0, tzinfo=timezone.utc),
        )
        key1 = compute_dedupe_key(alert)

        # Same bucket (12:05 and 12:09 are in same 10-min window)
        alert2 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="Test",
            timestamp=datetime(2026, 1, 25, 12, 9, 0, tzinfo=timezone.utc),
        )
        key2 = compute_dedupe_key(alert2)

        # Different fingerprints due to different alert_id, but same bucket
        assert ":176aborr" in key1 or key1.split(":")[-1] == key2.split(":")[-1]

    def test_recovery_event_bypasses_bucket(self):
        """Recovery events use alert_id, not bucket."""
        alert = create_alert(
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV2,
            summary="Redis recovered",
        )
        key = compute_dedupe_key(alert)
        assert "recovery" in key
        assert str(alert.alert_id) in key


class TestValidateAlert:
    def test_validate_accepts_valid_alert(self):
        """validate_alert accepts valid alert."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )
        validate_alert(alert)  # Should not raise

    def test_validate_rejects_naive_timestamp(self):
        """validate_alert rejects naive datetime."""
        from dataclasses import replace
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )
        # Force naive timestamp
        bad_alert = AlertEvent(
            alert_id=alert.alert_id,
            type=alert.type,
            severity=alert.severity,
            event_timestamp=datetime(2026, 1, 25, 12, 0, 0),  # No tzinfo
            fingerprint=alert.fingerprint,
            entity_ref=alert.entity_ref,
            summary=alert.summary,
            details=alert.details,
        )
        with pytest.raises(ValueError, match="timezone-aware"):
            validate_alert(bad_alert)

    def test_validate_rejects_long_summary(self):
        """validate_alert rejects summary > 255 chars."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="x" * 300,
        )
        with pytest.raises(ValueError, match="255"):
            validate_alert(alert)
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/alerts/test_factory.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.alerts.factory'`

**Step 3: Implement factory**

```python
# backend/src/alerts/factory.py
"""Alert factory and validation utilities."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.alerts.models import (
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    RECOVERY_TYPES,
    Severity,
    sanitize_details,
)

COOLDOWN_WINDOW_MINUTES = 10


def create_alert(
    type: AlertType,
    severity: Severity,
    summary: str,
    *,
    alert_id: UUID | None = None,
    timestamp: datetime | None = None,
    account_id: str | None = None,
    symbol: str | None = None,
    strategy_id: str | None = None,
    run_id: str | None = None,
    details: dict[str, JsonScalar] | None = None,
) -> AlertEvent:
    """Factory function to create AlertEvent with sensible defaults.

    Args:
        type: Alert type
        severity: Alert severity
        summary: Short description (max 255 chars)
        alert_id: Optional UUID (generated if not provided)
        timestamp: Optional timestamp (UTC now if not provided)
        account_id: Optional account reference
        symbol: Optional symbol reference
        strategy_id: Optional strategy reference
        run_id: Optional run reference
        details: Optional context dict (will be sanitized)

    Returns:
        Validated AlertEvent
    """
    # Generate ID if not provided
    if alert_id is None:
        alert_id = uuid4()

    # Normalize timestamp to UTC
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    elif timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    elif timestamp.tzinfo != timezone.utc:
        timestamp = timestamp.astimezone(timezone.utc)

    # Build entity ref
    entity_ref = None
    if any([account_id, symbol, strategy_id, run_id]):
        entity_ref = EntityRef(
            account_id=account_id,
            symbol=symbol,
            strategy_id=strategy_id,
            run_id=run_id,
        )

    # Build fingerprint
    fingerprint = _build_fingerprint(type, account_id, symbol, strategy_id)

    # Sanitize details
    safe_details = sanitize_details(details or {})

    # Truncate summary if needed
    if len(summary) > 255:
        summary = summary[:252] + "..."

    return AlertEvent(
        alert_id=alert_id,
        type=type,
        severity=severity,
        event_timestamp=timestamp,
        fingerprint=fingerprint,
        entity_ref=entity_ref,
        summary=summary,
        details=safe_details,
    )


def _build_fingerprint(
    type: AlertType,
    account_id: str | None,
    symbol: str | None,
    strategy_id: str | None,
) -> str:
    """Build fingerprint for deduplication."""
    parts = [
        type.value,
        account_id or "",
        symbol or "",
        strategy_id or "",
    ]
    return ":".join(parts)


def compute_dedupe_key(alert: AlertEvent) -> str:
    """Compute deduplication key for alert.

    Recovery events bypass bucket-based throttling.
    Normal events use 10-minute time buckets.
    """
    if alert.type in RECOVERY_TYPES:
        # Recovery: use alert_id to ensure each recovery sends
        return f"{alert.fingerprint}:recovery:{alert.alert_id}"

    # Normal: use 10-minute bucket
    bucket = int(alert.event_timestamp.timestamp()) // (COOLDOWN_WINDOW_MINUTES * 60)
    return f"{alert.fingerprint}:{bucket}"


def validate_alert(alert: AlertEvent) -> None:
    """Validate alert event.

    Raises:
        ValueError: If alert is invalid
    """
    # Check timestamp is timezone-aware UTC
    if alert.event_timestamp.tzinfo is None:
        raise ValueError("event_timestamp must be timezone-aware")
    if alert.event_timestamp.tzinfo != timezone.utc:
        raise ValueError("event_timestamp must be UTC")

    # Check summary length
    if len(alert.summary) > 255:
        raise ValueError("summary must be <= 255 characters")
```

**Step 4: Update exports**

```python
# backend/src/alerts/__init__.py
"""Alert system package."""

from src.alerts.factory import (
    compute_dedupe_key,
    create_alert,
    validate_alert,
)
from src.alerts.models import (
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    RECOVERY_TYPES,
    Severity,
    sanitize_details,
    to_json_safe,
)

__all__ = [
    "AlertEvent",
    "AlertType",
    "EntityRef",
    "JsonScalar",
    "RECOVERY_TYPES",
    "Severity",
    "compute_dedupe_key",
    "create_alert",
    "sanitize_details",
    "to_json_safe",
    "validate_alert",
]
```

**Step 5: Run tests and commit**

```bash
cd backend && pytest tests/alerts/ -v
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add alert factory and validation"
```

---

## Task 4: Database Migration for Alerts Tables

**Files:**
- Create: `backend/alembic/versions/004_alerts_tables.py`

**Step 1: Create migration**

```python
# backend/alembic/versions/004_alerts_tables.py
"""Add alerts and alert_deliveries tables.

Revision ID: 004
Revises: 003
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("severity", sa.Integer, nullable=False),
        sa.Column("fingerprint", sa.String(255), nullable=False),
        sa.Column("dedupe_key", sa.String(300), nullable=False, unique=True),
        sa.Column("summary", sa.String(255), nullable=False),
        sa.Column(
            "details",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column("entity_account_id", sa.String(50), nullable=True),
        sa.Column("entity_symbol", sa.String(20), nullable=True),
        sa.Column("entity_strategy_id", sa.String(50), nullable=True),
        sa.Column("suppressed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "event_timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "octet_length(details::text) <= 8192",
            name="ck_alerts_details_size",
        ),
    )

    op.create_index(
        "idx_alerts_fingerprint",
        "alerts",
        ["fingerprint", sa.text("event_timestamp DESC")],
    )
    op.create_index(
        "idx_alerts_severity",
        "alerts",
        ["severity", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_alerts_type",
        "alerts",
        ["type", sa.text("created_at DESC")],
    )

    # alert_deliveries table
    op.create_table(
        "alert_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "alert_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("alerts.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("destination_key", sa.String(100), nullable=False),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("response_code", sa.Integer, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "alert_id",
            "destination_key",
            "attempt_number",
            name="uq_deliveries_alert_dest_attempt",
        ),
    )

    op.create_index("idx_deliveries_alert", "alert_deliveries", ["alert_id"])
    op.create_index(
        "idx_deliveries_status",
        "alert_deliveries",
        ["status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("alert_deliveries")
    op.drop_table("alerts")
```

**Step 2: Run migration**

```bash
cd backend && alembic upgrade head
```

**Step 3: Verify tables created**

```bash
cd backend && python -c "
from sqlalchemy import create_engine, text
from src.config import settings
engine = create_engine(settings.database_url.replace('+asyncpg', ''))
with engine.connect() as conn:
    result = conn.execute(text(\"SELECT table_name FROM information_schema.tables WHERE table_name IN ('alerts', 'alert_deliveries')\"))
    tables = [r[0] for r in result]
    print(f'Tables: {tables}')
    assert 'alerts' in tables
    assert 'alert_deliveries' in tables
    print('Migration verified!')
"
```

**Step 4: Commit**

```bash
git add backend/alembic/versions/004_alerts_tables.py
git commit -m "feat(alerts): add database migration for alerts tables"
```

---

## Task 5: Alert Repository

**Files:**
- Create: `backend/src/alerts/repository.py`
- Test: `backend/tests/alerts/test_repository.py`

**Step 1: Write failing test**

```python
# backend/tests/alerts/test_repository.py
"""Tests for alert repository."""

import pytest
from datetime import datetime, timezone
from uuid import uuid4

from src.alerts.factory import create_alert, compute_dedupe_key
from src.alerts.models import AlertType, Severity
from src.alerts.repository import AlertRepository


@pytest.fixture
def repo(db_session):
    """Create repository with test session."""
    return AlertRepository(db_session)


@pytest.mark.asyncio
class TestAlertRepository:
    async def test_persist_new_alert(self, repo):
        """persist_alert returns is_new=True for new alert."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test alert",
        )
        is_new, alert_id = await repo.persist_alert(alert)

        assert is_new is True
        assert alert_id == alert.alert_id

    async def test_persist_duplicate_returns_not_new(self, repo):
        """persist_alert returns is_new=False for duplicate dedupe_key."""
        alert1 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="First",
            account_id="ACC001",
            timestamp=datetime(2026, 1, 25, 12, 5, 0, tzinfo=timezone.utc),
        )
        alert2 = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="Second",
            account_id="ACC001",
            timestamp=datetime(2026, 1, 25, 12, 7, 0, tzinfo=timezone.utc),
        )

        is_new1, _ = await repo.persist_alert(alert1)
        is_new2, _ = await repo.persist_alert(alert2)

        assert is_new1 is True
        assert is_new2 is False  # Same 10-min bucket

    async def test_persist_increments_suppressed_count(self, repo):
        """Duplicate alerts increment suppressed_count."""
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="Test",
            account_id="ACC001",
        )

        await repo.persist_alert(alert)
        await repo.persist_alert(alert)
        await repo.persist_alert(alert)

        stored = await repo.get_alert(alert.alert_id)
        assert stored["suppressed_count"] == 2  # 2 duplicates

    async def test_record_delivery_attempt(self, repo):
        """Can record delivery attempt."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="email",
            destination_key="email:alerts",
            attempt_number=1,
            status="pending",
        )

        assert delivery_id is not None

    async def test_update_delivery_status(self, repo):
        """Can update delivery status."""
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )
        await repo.persist_alert(alert)

        delivery_id = await repo.record_delivery_attempt(
            alert_id=alert.alert_id,
            channel="email",
            destination_key="email:alerts",
            attempt_number=1,
            status="pending",
        )

        await repo.update_delivery_status(
            delivery_id=delivery_id,
            status="sent",
            response_code=200,
        )

        delivery = await repo.get_delivery(delivery_id)
        assert delivery["status"] == "sent"
        assert delivery["response_code"] == 200
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/alerts/test_repository.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Implement repository**

```python
# backend/src/alerts/repository.py
"""Alert persistence layer."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.factory import compute_dedupe_key
from src.alerts.models import AlertEvent


class AlertRepository:
    """Repository for alert persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def persist_alert(self, alert: AlertEvent) -> tuple[bool, UUID]:
        """Persist alert with deduplication.

        Uses ON CONFLICT to atomically handle duplicates.

        Args:
            alert: Alert event to persist

        Returns:
            Tuple of (is_new, alert_id)
            - is_new: True if this is a new alert, False if deduplicated
            - alert_id: The alert ID (original or existing)
        """
        dedupe_key = compute_dedupe_key(alert)

        result = await self._session.execute(
            text("""
                INSERT INTO alerts (
                    id, type, severity, fingerprint, dedupe_key, summary, details,
                    entity_account_id, entity_symbol, entity_strategy_id,
                    suppressed_count, event_timestamp, created_at
                ) VALUES (
                    :id, :type, :severity, :fingerprint, :dedupe_key, :summary,
                    :details::jsonb, :account_id, :symbol, :strategy_id,
                    0, :event_timestamp, NOW()
                )
                ON CONFLICT (dedupe_key) DO UPDATE SET
                    suppressed_count = alerts.suppressed_count + 1
                RETURNING (xmax = 0) AS is_new, id
            """),
            {
                "id": alert.alert_id,
                "type": alert.type.value,
                "severity": alert.severity.value,
                "fingerprint": alert.fingerprint,
                "dedupe_key": dedupe_key,
                "summary": alert.summary,
                "details": str(alert.details).replace("'", '"'),  # JSON format
                "account_id": alert.entity_ref.account_id if alert.entity_ref else None,
                "symbol": alert.entity_ref.symbol if alert.entity_ref else None,
                "strategy_id": alert.entity_ref.strategy_id if alert.entity_ref else None,
                "event_timestamp": alert.event_timestamp,
            },
        )

        row = result.fetchone()
        await self._session.commit()
        return row.is_new, row.id

    async def get_alert(self, alert_id: UUID) -> dict | None:
        """Get alert by ID."""
        result = await self._session.execute(
            text("SELECT * FROM alerts WHERE id = :id"),
            {"id": alert_id},
        )
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None

    async def record_delivery_attempt(
        self,
        alert_id: UUID,
        channel: str,
        destination_key: str,
        attempt_number: int,
        status: str,
    ) -> UUID:
        """Record a delivery attempt.

        Returns:
            Delivery record ID
        """
        delivery_id = uuid4()
        await self._session.execute(
            text("""
                INSERT INTO alert_deliveries (
                    id, alert_id, channel, destination_key,
                    attempt_number, status, created_at
                ) VALUES (
                    :id, :alert_id, :channel, :destination_key,
                    :attempt_number, :status, NOW()
                )
            """),
            {
                "id": delivery_id,
                "alert_id": alert_id,
                "channel": channel,
                "destination_key": destination_key,
                "attempt_number": attempt_number,
                "status": status,
            },
        )
        await self._session.commit()
        return delivery_id

    async def update_delivery_status(
        self,
        delivery_id: UUID,
        status: str,
        response_code: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update delivery attempt status."""
        await self._session.execute(
            text("""
                UPDATE alert_deliveries
                SET status = :status,
                    response_code = :response_code,
                    error_message = :error_message,
                    sent_at = CASE WHEN :status = 'sent' THEN NOW() ELSE sent_at END
                WHERE id = :id
            """),
            {
                "id": delivery_id,
                "status": status,
                "response_code": response_code,
                "error_message": error_message,
            },
        )
        await self._session.commit()

    async def get_delivery(self, delivery_id: UUID) -> dict | None:
        """Get delivery by ID."""
        result = await self._session.execute(
            text("SELECT * FROM alert_deliveries WHERE id = :id"),
            {"id": delivery_id},
        )
        row = result.fetchone()
        if row:
            return dict(row._mapping)
        return None
```

**Step 4: Update exports, run tests, commit**

```bash
cd backend && pytest tests/alerts/test_repository.py -v
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add alert repository with deduplication"
```

---

---

## Task 6: Notification Channels (Email + Webhook)

**Files:**
- Create: `backend/src/alerts/channels.py`
- Test: `backend/tests/alerts/test_channels.py`

**Step 1: Write failing test for channel protocol**

```python
# backend/tests/alerts/test_channels.py
"""Tests for notification channels."""

import pytest
from unittest.mock import AsyncMock, patch

from src.alerts.channels import (
    NotificationChannel,
    EmailChannel,
    WebhookChannel,
    DeliveryResult,
)
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity


class TestDeliveryResult:
    def test_success_result(self):
        """DeliveryResult success."""
        result = DeliveryResult(success=True, response_code=200)
        assert result.success is True
        assert result.response_code == 200
        assert result.error_message is None

    def test_failure_result(self):
        """DeliveryResult failure."""
        result = DeliveryResult(
            success=False,
            response_code=500,
            error_message="Server error",
        )
        assert result.success is False
        assert result.error_message == "Server error"


@pytest.mark.asyncio
class TestEmailChannel:
    async def test_send_formats_email(self):
        """EmailChannel formats alert as email."""
        channel = EmailChannel(
            smtp_host="localhost",
            smtp_port=587,
            sender="alerts@example.com",
        )
        alert = create_alert(
            type=AlertType.DAILY_LOSS_LIMIT,
            severity=Severity.SEV1,
            summary="Daily loss limit reached",
            details={"loss": "-5000.00"},
        )

        with patch.object(channel, "_send_smtp", new_callable=AsyncMock) as mock:
            mock.return_value = DeliveryResult(success=True, response_code=250)
            result = await channel.send(alert, "risk@example.com")

        assert result.success is True
        mock.assert_called_once()
        # Verify email content
        call_args = mock.call_args
        assert "Daily loss limit reached" in str(call_args)


@pytest.mark.asyncio
class TestWebhookChannel:
    async def test_send_posts_json(self):
        """WebhookChannel posts JSON to URL."""
        channel = WebhookChannel()
        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Kill switch activated",
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock:
            mock.return_value = AsyncMock(status_code=200)
            result = await channel.send(alert, "https://hooks.slack.com/xxx")

        assert result.success is True

    async def test_send_handles_timeout(self):
        """WebhookChannel handles timeout gracefully."""
        import httpx

        channel = WebhookChannel(timeout_seconds=1)
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock:
            mock.side_effect = httpx.TimeoutException("timeout")
            result = await channel.send(alert, "https://example.com")

        assert result.success is False
        assert "timeout" in result.error_message.lower()
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/alerts/test_channels.py -v
```

**Step 3: Implement channels**

```python
# backend/src/alerts/channels.py
"""Notification channel implementations."""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.mime.text import MIMEText

import aiosmtplib
import httpx

from src.alerts.models import AlertEvent

logger = logging.getLogger(__name__)


@dataclass
class DeliveryResult:
    """Result of a delivery attempt."""

    success: bool
    response_code: int | None = None
    error_message: str | None = None


class NotificationChannel(ABC):
    """Abstract base for notification channels."""

    @abstractmethod
    async def send(self, alert: AlertEvent, destination: str) -> DeliveryResult:
        """Send alert to destination.

        Args:
            alert: Alert to send
            destination: Channel-specific destination (email, URL, etc.)

        Returns:
            DeliveryResult with success status
        """
        pass


class EmailChannel(NotificationChannel):
    """SMTP email channel."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
    ):
        self._host = smtp_host
        self._port = smtp_port
        self._sender = sender
        self._username = username
        self._password = password
        self._use_tls = use_tls

    async def send(self, alert: AlertEvent, destination: str) -> DeliveryResult:
        """Send alert via email."""
        try:
            subject = f"[{alert.severity.name}] {alert.summary}"
            body = self._format_body(alert)

            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = self._sender
            msg["To"] = destination

            return await self._send_smtp(msg, destination)

        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return DeliveryResult(
                success=False,
                error_message=f"Email error: {e}",
            )

    async def _send_smtp(self, msg: MIMEText, recipient: str) -> DeliveryResult:
        """Send via SMTP."""
        try:
            async with aiosmtplib.SMTP(
                hostname=self._host,
                port=self._port,
                use_tls=self._use_tls,
            ) as smtp:
                if self._username and self._password:
                    await smtp.login(self._username, self._password)
                await smtp.send_message(msg)

            return DeliveryResult(success=True, response_code=250)

        except aiosmtplib.SMTPException as e:
            return DeliveryResult(
                success=False,
                response_code=getattr(e, "code", None),
                error_message=str(e),
            )

    def _format_body(self, alert: AlertEvent) -> str:
        """Format email body."""
        lines = [
            f"Alert: {alert.summary}",
            f"Type: {alert.type.value}",
            f"Severity: {alert.severity.name}",
            f"Time: {alert.event_timestamp.isoformat()}",
            "",
        ]

        if alert.entity_ref:
            if alert.entity_ref.account_id:
                lines.append(f"Account: {alert.entity_ref.account_id}")
            if alert.entity_ref.symbol:
                lines.append(f"Symbol: {alert.entity_ref.symbol}")
            lines.append("")

        if alert.details:
            lines.append("Details:")
            for k, v in alert.details.items():
                lines.append(f"  {k}: {v}")

        return "\n".join(lines)


class WebhookChannel(NotificationChannel):
    """HTTP webhook channel (Slack, Discord, PagerDuty compatible)."""

    def __init__(self, timeout_seconds: float = 10.0):
        self._timeout = timeout_seconds

    async def send(self, alert: AlertEvent, destination: str) -> DeliveryResult:
        """Send alert via webhook POST."""
        try:
            payload = self._format_payload(alert)

            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    destination,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

            success = 200 <= response.status_code < 300
            return DeliveryResult(
                success=success,
                response_code=response.status_code,
                error_message=None if success else response.text[:200],
            )

        except httpx.TimeoutException:
            return DeliveryResult(
                success=False,
                error_message="Webhook timeout",
            )
        except Exception as e:
            return DeliveryResult(
                success=False,
                error_message=f"Webhook error: {e}",
            )

    def _format_payload(self, alert: AlertEvent) -> dict:
        """Format webhook payload (Slack-compatible)."""
        severity_emoji = {1: "🔴", 2: "🟡", 3: "🔵"}
        emoji = severity_emoji.get(alert.severity.value, "⚪")

        return {
            "text": f"{emoji} [{alert.severity.name}] {alert.summary}",
            "attachments": [
                {
                    "color": "#ff0000" if alert.severity.value == 1 else "#ffcc00",
                    "fields": [
                        {"title": "Type", "value": alert.type.value, "short": True},
                        {"title": "Time", "value": alert.event_timestamp.isoformat(), "short": True},
                    ],
                }
            ],
        }
```

**Step 4: Run tests and commit**

```bash
cd backend && pytest tests/alerts/test_channels.py -v
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add email and webhook notification channels"
```

---

## Task 7: Routing Configuration

**Files:**
- Create: `backend/src/alerts/routing.py`
- Test: `backend/tests/alerts/test_routing.py`

**Step 1: Write failing test**

```python
# backend/tests/alerts/test_routing.py
"""Tests for alert routing."""

import pytest
import os
from unittest.mock import patch

from src.alerts.routing import RoutingConfig, get_destinations_for_alert
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity


class TestRoutingConfig:
    def test_sev1_routes_to_email_and_webhook(self):
        """SEV1 alerts route to email and webhook."""
        config = RoutingConfig()
        channels = config.get_channels_for_severity(Severity.SEV1)
        assert "email" in channels
        assert "webhook" in channels

    def test_sev2_routes_to_webhook_only(self):
        """SEV2 alerts route to webhook only."""
        config = RoutingConfig()
        channels = config.get_channels_for_severity(Severity.SEV2)
        assert "webhook" in channels
        assert "email" not in channels

    def test_sev3_routes_to_nothing(self):
        """SEV3 alerts are log-only."""
        config = RoutingConfig()
        channels = config.get_channels_for_severity(Severity.SEV3)
        assert len(channels) == 0


class TestGetDestinations:
    @patch.dict(os.environ, {
        "ALERT_EMAIL_DEFAULT": "alerts@example.com",
        "ALERT_WEBHOOK_DEFAULT": "https://hooks.slack.com/xxx",
    })
    def test_get_destinations_for_sev1(self):
        """SEV1 alert gets email and webhook destinations."""
        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Kill switch",
        )
        destinations = get_destinations_for_alert(alert)

        assert ("email", "alerts@example.com") in destinations
        assert ("webhook", "https://hooks.slack.com/xxx") in destinations

    @patch.dict(os.environ, {
        "ALERT_EMAIL_RISK": "risk@example.com",
        "ALERT_WEBHOOK_DEFAULT": "https://hooks.slack.com/xxx",
    })
    def test_type_specific_routing(self):
        """Specific alert types route to specific recipients."""
        alert = create_alert(
            type=AlertType.DAILY_LOSS_LIMIT,
            severity=Severity.SEV1,
            summary="Loss limit",
        )
        destinations = get_destinations_for_alert(alert)

        # Should include risk team
        emails = [d[1] for d in destinations if d[0] == "email"]
        assert "risk@example.com" in emails
```

**Step 2: Implement routing**

```python
# backend/src/alerts/routing.py
"""Alert routing configuration."""

import os
from dataclasses import dataclass, field

from src.alerts.models import AlertEvent, AlertType, Severity


@dataclass
class RoutingConfig:
    """Alert routing configuration."""

    severity_channels: dict[Severity, list[str]] = field(default_factory=lambda: {
        Severity.SEV1: ["email", "webhook"],
        Severity.SEV2: ["webhook"],
        Severity.SEV3: [],  # Log only
    })

    type_recipients: dict[AlertType, list[str]] = field(default_factory=lambda: {
        AlertType.DAILY_LOSS_LIMIT: ["email:risk"],
        AlertType.KILL_SWITCH_ACTIVATED: ["email:ops", "email:risk"],
        AlertType.POSITION_LIMIT_HIT: ["email:risk"],
    })

    global_recipients: list[str] = field(default_factory=lambda: [
        "email:default",
        "webhook:default",
    ])

    def get_channels_for_severity(self, severity: Severity) -> list[str]:
        """Get enabled channels for severity level."""
        return self.severity_channels.get(severity, [])


# Environment variable mapping for destinations
DESTINATION_ENV_MAP = {
    "email:default": "ALERT_EMAIL_DEFAULT",
    "email:risk": "ALERT_EMAIL_RISK",
    "email:ops": "ALERT_EMAIL_OPS",
    "webhook:default": "ALERT_WEBHOOK_DEFAULT",
    "webhook:wecom": "ALERT_WEBHOOK_WECOM",
}


def resolve_destination(key: str) -> str | None:
    """Resolve destination key to actual address/URL."""
    env_var = DESTINATION_ENV_MAP.get(key)
    if env_var:
        return os.getenv(env_var)
    return None


def get_destinations_for_alert(
    alert: AlertEvent,
    config: RoutingConfig | None = None,
) -> list[tuple[str, str]]:
    """Get list of (channel, destination) for alert.

    Args:
        alert: Alert to route
        config: Optional routing config (uses default if not provided)

    Returns:
        List of (channel_type, resolved_destination) tuples
    """
    if config is None:
        config = RoutingConfig()

    # Get enabled channels for this severity
    enabled_channels = set(config.get_channels_for_severity(alert.severity))
    if not enabled_channels:
        return []

    # Collect destination keys
    dest_keys: set[str] = set()

    # Add type-specific recipients
    type_recipients = config.type_recipients.get(alert.type, [])
    dest_keys.update(type_recipients)

    # Add global recipients
    dest_keys.update(config.global_recipients)

    # Filter by enabled channels and resolve
    result: list[tuple[str, str]] = []
    for key in dest_keys:
        channel = key.split(":")[0]
        if channel in enabled_channels:
            resolved = resolve_destination(key)
            if resolved:
                result.append((channel, resolved))

    return result
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/alerts/test_routing.py -v
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add routing configuration"
```

---

## Task 8: NotificationHub with Async Queue

**Files:**
- Create: `backend/src/alerts/hub.py`
- Test: `backend/tests/alerts/test_hub.py`

**Step 1: Write failing test**

```python
# backend/tests/alerts/test_hub.py
"""Tests for NotificationHub."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.alerts.hub import NotificationHub
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity
from src.alerts.channels import DeliveryResult


@pytest.fixture
def mock_repo():
    """Mock alert repository."""
    repo = AsyncMock()
    repo.record_delivery_attempt = AsyncMock(return_value="delivery-id")
    repo.update_delivery_status = AsyncMock()
    return repo


@pytest.fixture
def mock_channels():
    """Mock notification channels."""
    email = AsyncMock()
    email.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=250))

    webhook = AsyncMock()
    webhook.send = AsyncMock(return_value=DeliveryResult(success=True, response_code=200))

    return {"email": email, "webhook": webhook}


@pytest.mark.asyncio
class TestNotificationHub:
    async def test_enqueue_adds_to_queue(self, mock_repo, mock_channels):
        """enqueue adds alert to queue."""
        hub = NotificationHub(
            repository=mock_repo,
            channels=mock_channels,
        )
        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )

        result = await hub.enqueue(alert)

        assert result is True
        assert hub._queue.qsize() == 1

    async def test_sev1_not_dropped_when_full(self, mock_repo, mock_channels):
        """SEV1 alerts not dropped when queue is full."""
        hub = NotificationHub(
            repository=mock_repo,
            channels=mock_channels,
            max_queue_size=1,
        )

        # Fill queue
        alert1 = create_alert(type=AlertType.ORDER_FILLED, severity=Severity.SEV2, summary="Fill")
        await hub.enqueue(alert1)

        # SEV1 should still be handled
        alert2 = create_alert(type=AlertType.KILL_SWITCH_ACTIVATED, severity=Severity.SEV1, summary="Critical")

        with patch.object(hub, "_fallback_sync_send", new_callable=AsyncMock):
            result = await hub.enqueue(alert2)

        assert result is True
        hub._fallback_sync_send.assert_called_once()

    async def test_worker_processes_queue(self, mock_repo, mock_channels):
        """Worker processes alerts from queue."""
        hub = NotificationHub(
            repository=mock_repo,
            channels=mock_channels,
        )

        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Test",
        )

        # Mock destinations
        with patch("src.alerts.hub.get_destinations_for_alert") as mock_dest:
            mock_dest.return_value = [("webhook", "https://example.com")]

            await hub.enqueue(alert)
            await hub._process_one()

        mock_channels["webhook"].send.assert_called_once()

    async def test_retry_on_failure(self, mock_repo, mock_channels):
        """Retries delivery on failure."""
        hub = NotificationHub(
            repository=mock_repo,
            channels=mock_channels,
            max_retries=3,
            retry_base_delay=0.01,
        )

        # Fail twice, then succeed
        mock_channels["webhook"].send = AsyncMock(side_effect=[
            DeliveryResult(success=False, response_code=500, error_message="Error"),
            DeliveryResult(success=False, response_code=500, error_message="Error"),
            DeliveryResult(success=True, response_code=200),
        ])

        alert = create_alert(type=AlertType.ORDER_FILLED, severity=Severity.SEV2, summary="Test")

        with patch("src.alerts.hub.get_destinations_for_alert") as mock_dest:
            mock_dest.return_value = [("webhook", "https://example.com")]
            await hub._deliver_alert(alert)

        assert mock_channels["webhook"].send.call_count == 3
```

**Step 2: Implement NotificationHub**

```python
# backend/src/alerts/hub.py
"""NotificationHub - async alert delivery with retry."""

import asyncio
import logging
from typing import Any

from src.alerts.channels import DeliveryResult, NotificationChannel
from src.alerts.factory import create_alert
from src.alerts.models import AlertEvent, AlertType, Severity
from src.alerts.repository import AlertRepository
from src.alerts.routing import get_destinations_for_alert

logger = logging.getLogger(__name__)

# Self-alert types that should not trigger more alerts
SELF_ALERT_TYPES = frozenset({AlertType.ALERT_DELIVERY_FAILED})


class NotificationHub:
    """Async notification hub with queue and retry."""

    def __init__(
        self,
        repository: AlertRepository,
        channels: dict[str, NotificationChannel],
        max_queue_size: int = 1000,
        max_retries: int = 5,
        retry_base_delay: float = 1.0,
        retry_multiplier: float = 2.0,
    ):
        self._repo = repository
        self._channels = channels
        self._queue: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._max_retries = max_retries
        self._retry_base = retry_base_delay
        self._retry_mult = retry_multiplier
        self._workers: list[asyncio.Task] = []
        self._running = False

    async def start(self, num_workers: int = 3) -> None:
        """Start worker tasks."""
        self._running = True
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        logger.info(f"NotificationHub started with {num_workers} workers")

    async def stop(self) -> None:
        """Stop workers gracefully."""
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        logger.info("NotificationHub stopped")

    async def enqueue(self, alert: AlertEvent) -> bool:
        """Add alert to delivery queue.

        SEV1 alerts are never dropped - they fall back to sync delivery.

        Returns:
            True if queued/handled, False if dropped
        """
        try:
            self._queue.put_nowait(alert)
            return True
        except asyncio.QueueFull:
            if alert.severity == Severity.SEV1:
                logger.critical(
                    f"Alert queue full, SEV1 fallback: {alert.alert_id} - {alert.summary}"
                )
                await self._record_queue_overflow(alert)
                await self._fallback_sync_send(alert)
                return True
            else:
                logger.warning(
                    f"Alert queue full, dropping SEV{alert.severity.value}: {alert.alert_id}"
                )
                await self._record_dropped(alert)
                return False

    async def _worker(self, worker_id: int) -> None:
        """Worker loop processing alerts."""
        logger.debug(f"Worker {worker_id} started")
        while self._running:
            try:
                await self._process_one()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} error: {e}")

    async def _process_one(self) -> None:
        """Process one alert from queue."""
        try:
            alert = await asyncio.wait_for(self._queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            return

        try:
            await self._deliver_alert(alert)
        finally:
            self._queue.task_done()

    async def _deliver_alert(self, alert: AlertEvent) -> None:
        """Deliver alert to all destinations with retry."""
        destinations = get_destinations_for_alert(alert)

        for channel_type, destination in destinations:
            channel = self._channels.get(channel_type)
            if not channel:
                logger.warning(f"Unknown channel: {channel_type}")
                continue

            await self._deliver_with_retry(alert, channel, channel_type, destination)

    async def _deliver_with_retry(
        self,
        alert: AlertEvent,
        channel: NotificationChannel,
        channel_type: str,
        destination: str,
    ) -> None:
        """Deliver to single destination with exponential backoff retry."""
        delay = self._retry_base

        for attempt in range(1, self._max_retries + 1):
            # Record attempt
            delivery_id = await self._repo.record_delivery_attempt(
                alert_id=alert.alert_id,
                channel=channel_type,
                destination_key=f"{channel_type}:{destination.split('/')[-1][:20]}",
                attempt_number=attempt,
                status="pending",
            )

            # Try delivery
            result = await channel.send(alert, destination)

            # Update status
            await self._repo.update_delivery_status(
                delivery_id=delivery_id,
                status="sent" if result.success else "failed",
                response_code=result.response_code,
                error_message=result.error_message,
            )

            if result.success:
                logger.info(f"Delivered {alert.alert_id} via {channel_type}")
                return

            # Retry logic
            if attempt < self._max_retries:
                logger.warning(
                    f"Delivery failed, retry {attempt}/{self._max_retries}: {result.error_message}"
                )
                await asyncio.sleep(delay)
                delay *= self._retry_mult
            else:
                await self._handle_delivery_failure(alert, channel_type, result.error_message)

    async def _handle_delivery_failure(
        self,
        alert: AlertEvent,
        channel_type: str,
        error: str | None,
    ) -> None:
        """Handle final delivery failure."""
        logger.error(f"Delivery failed after retries: {alert.alert_id} via {channel_type}")

        # Don't create recursive alerts
        if alert.type in SELF_ALERT_TYPES:
            logger.critical(f"ALERT_DELIVERY_FAILED itself failed: {error}")
            return

        # For SEV1, create failure alert (persisted only, not sent)
        if alert.severity == Severity.SEV1:
            failure_alert = create_alert(
                type=AlertType.ALERT_DELIVERY_FAILED,
                severity=Severity.SEV1,
                summary=f"Failed to deliver SEV1: {alert.summary[:100]}",
                details={
                    "original_alert_id": str(alert.alert_id),
                    "channel": channel_type,
                    "error": error or "Unknown",
                },
            )
            await self._repo.persist_alert(failure_alert)

    async def _fallback_sync_send(self, alert: AlertEvent) -> None:
        """Synchronous fallback for SEV1 when queue full."""
        try:
            await asyncio.wait_for(
                self._deliver_alert(alert),
                timeout=30.0,
            )
        except asyncio.TimeoutError:
            logger.critical(f"SEV1 fallback timeout: {alert.alert_id}")

    async def _record_queue_overflow(self, alert: AlertEvent) -> None:
        """Record queue overflow event."""
        logger.warning(f"Queue overflow for alert: {alert.alert_id}")

    async def _record_dropped(self, alert: AlertEvent) -> None:
        """Record dropped alert."""
        logger.warning(f"Dropped alert: {alert.alert_id}")
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/alerts/test_hub.py -v
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add NotificationHub with async queue and retry"
```

---

## Task 9: AlertService (Main Entry Point)

**Files:**
- Create: `backend/src/alerts/service.py`
- Test: `backend/tests/alerts/test_service.py`

**Step 1: Write failing test**

```python
# backend/tests/alerts/test_service.py
"""Tests for AlertService."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.alerts.service import AlertService
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity, RECOVERY_TYPES


@pytest.fixture
def mock_repo():
    repo = AsyncMock()
    repo.persist_alert = AsyncMock(return_value=(True, "alert-id"))
    return repo


@pytest.fixture
def mock_hub():
    hub = AsyncMock()
    hub.enqueue = AsyncMock(return_value=True)
    return hub


@pytest.mark.asyncio
class TestAlertService:
    async def test_emit_persists_and_enqueues(self, mock_repo, mock_hub):
        """emit persists alert and enqueues for delivery."""
        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_FILLED,
            severity=Severity.SEV2,
            summary="Order filled",
        )

        result = await service.emit(alert)

        assert result is True
        mock_repo.persist_alert.assert_called_once_with(alert)
        mock_hub.enqueue.assert_called_once_with(alert)

    async def test_emit_skips_send_when_deduplicated(self, mock_repo, mock_hub):
        """emit skips enqueue when alert is deduplicated."""
        mock_repo.persist_alert = AsyncMock(return_value=(False, "existing-id"))

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV1,
            summary="Rejected",
        )

        result = await service.emit(alert)

        assert result is True  # Still succeeds
        mock_hub.enqueue.assert_not_called()

    async def test_emit_always_sends_recovery(self, mock_repo, mock_hub):
        """emit always sends recovery events."""
        # Even if dedupe says not new (shouldn't happen, but test the logic)
        mock_repo.persist_alert = AsyncMock(return_value=(True, "alert-id"))

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV2,
            summary="Redis recovered",
        )

        await service.emit(alert)

        mock_hub.enqueue.assert_called_once()

    async def test_emit_respects_send_flag(self, mock_repo, mock_hub):
        """emit with send=False only persists."""
        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ALERT_DELIVERY_FAILED,
            severity=Severity.SEV1,
            summary="Delivery failed",
        )

        await service.emit(alert, send=False)

        mock_repo.persist_alert.assert_called_once()
        mock_hub.enqueue.assert_not_called()
```

**Step 2: Implement AlertService**

```python
# backend/src/alerts/service.py
"""AlertService - main entry point for emitting alerts."""

import logging

from src.alerts.factory import validate_alert
from src.alerts.hub import NotificationHub
from src.alerts.models import AlertEvent, RECOVERY_TYPES
from src.alerts.repository import AlertRepository

logger = logging.getLogger(__name__)


class AlertService:
    """Main service for emitting alerts.

    Business modules use this to emit alerts. It handles:
    - Validation
    - Persistence with deduplication
    - Routing to NotificationHub

    This is the ONLY entry point for sending notifications.
    """

    def __init__(
        self,
        repository: AlertRepository,
        hub: NotificationHub,
    ):
        self._repo = repository
        self._hub = hub

    async def emit(
        self,
        alert: AlertEvent,
        *,
        send: bool = True,
    ) -> bool:
        """Emit an alert.

        Args:
            alert: Alert event to emit
            send: If False, only persist (don't send notifications)

        Returns:
            True if alert was processed successfully
        """
        try:
            # Validate
            validate_alert(alert)

            # Persist with deduplication
            is_new, alert_id = await self._repo.persist_alert(alert)

            if not send:
                logger.debug(f"Alert persisted only (send=False): {alert_id}")
                return True

            # Determine if we should send
            should_send = is_new or alert.type in RECOVERY_TYPES

            if should_send:
                await self._hub.enqueue(alert)
                logger.info(f"Alert emitted: {alert.type.value} - {alert.summary}")
            else:
                logger.debug(f"Alert deduplicated: {alert_id}")

            return True

        except Exception as e:
            logger.error(f"Failed to emit alert: {e}")
            return False
```

**Step 3: Run tests and commit**

```bash
cd backend && pytest tests/alerts/test_service.py -v
git add backend/src/alerts backend/tests/alerts
git commit -m "feat(alerts): add AlertService entry point"
```

---

## Task 10: Alert API Endpoints

**Files:**
- Create: `backend/src/api/alerts.py`
- Test: `backend/tests/api/test_alerts.py`

**Step 1: Write failing test**

```python
# backend/tests/api/test_alerts.py
"""Tests for alert API endpoints."""

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestAlertAPI:
    def test_list_alerts(self, client):
        """GET /api/alerts returns alert list."""
        response = client.get("/api/alerts")
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "total" in data

    def test_list_alerts_filter_by_severity(self, client):
        """GET /api/alerts?severity=1 filters by severity."""
        response = client.get("/api/alerts?severity=1")
        assert response.status_code == 200

    def test_list_alerts_filter_by_type(self, client):
        """GET /api/alerts?type=order_filled filters by type."""
        response = client.get("/api/alerts?type=order_filled")
        assert response.status_code == 200

    def test_get_alert_deliveries(self, client):
        """GET /api/alerts/{id}/deliveries returns delivery attempts."""
        # First create an alert
        # Then check deliveries
        pass  # Integration test

    def test_get_alert_stats(self, client):
        """GET /api/alerts/stats returns alert statistics."""
        response = client.get("/api/alerts/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_24h" in data
        assert "by_severity" in data
```

**Step 2: Implement API**

```python
# backend/src/api/alerts.py
"""Alert API endpoints."""

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertResponse(BaseModel):
    id: str
    type: str
    severity: int
    summary: str
    fingerprint: str
    suppressed_count: int
    event_timestamp: datetime
    created_at: datetime
    entity_account_id: str | None
    entity_symbol: str | None


class AlertListResponse(BaseModel):
    alerts: list[AlertResponse]
    total: int
    offset: int
    limit: int


class DeliveryResponse(BaseModel):
    id: str
    channel: str
    destination_key: str
    attempt_number: int
    status: str
    response_code: int | None
    error_message: str | None
    created_at: datetime
    sent_at: datetime | None


class AlertStatsResponse(BaseModel):
    total_24h: int
    by_severity: dict[str, int]
    by_type: dict[str, int]
    delivery_success_rate: float


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    severity: int | None = None,
    type: str | None = None,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, le=100),
):
    """List alerts with optional filtering."""
    conditions = []
    params = {"offset": offset, "limit": limit}

    if severity is not None:
        conditions.append("severity = :severity")
        params["severity"] = severity

    if type is not None:
        conditions.append("type = :type")
        params["type"] = type

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Get total
    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM alerts {where_clause}"),
        params,
    )
    total = count_result.scalar()

    # Get alerts
    result = await db.execute(
        text(f"""
            SELECT id, type, severity, summary, fingerprint, suppressed_count,
                   event_timestamp, created_at, entity_account_id, entity_symbol
            FROM alerts
            {where_clause}
            ORDER BY created_at DESC
            OFFSET :offset LIMIT :limit
        """),
        params,
    )

    alerts = [
        AlertResponse(
            id=str(row.id),
            type=row.type,
            severity=row.severity,
            summary=row.summary,
            fingerprint=row.fingerprint,
            suppressed_count=row.suppressed_count,
            event_timestamp=row.event_timestamp,
            created_at=row.created_at,
            entity_account_id=row.entity_account_id,
            entity_symbol=row.entity_symbol,
        )
        for row in result
    ]

    return AlertListResponse(alerts=alerts, total=total, offset=offset, limit=limit)


@router.get("/stats", response_model=AlertStatsResponse)
async def get_alert_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get alert statistics for last 24 hours."""
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    # Total count
    total_result = await db.execute(
        text("SELECT COUNT(*) FROM alerts WHERE created_at >= :since"),
        {"since": since},
    )
    total = total_result.scalar()

    # By severity
    sev_result = await db.execute(
        text("""
            SELECT severity, COUNT(*) as count
            FROM alerts WHERE created_at >= :since
            GROUP BY severity
        """),
        {"since": since},
    )
    by_severity = {f"SEV{row.severity}": row.count for row in sev_result}

    # By type
    type_result = await db.execute(
        text("""
            SELECT type, COUNT(*) as count
            FROM alerts WHERE created_at >= :since
            GROUP BY type ORDER BY count DESC LIMIT 10
        """),
        {"since": since},
    )
    by_type = {row.type: row.count for row in type_result}

    # Delivery success rate
    delivery_result = await db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'sent') as success,
                COUNT(*) as total
            FROM alert_deliveries
            WHERE created_at >= :since
        """),
        {"since": since},
    )
    row = delivery_result.fetchone()
    success_rate = (row.success / row.total * 100) if row.total > 0 else 100.0

    return AlertStatsResponse(
        total_24h=total,
        by_severity=by_severity,
        by_type=by_type,
        delivery_success_rate=round(success_rate, 1),
    )


@router.get("/{alert_id}/deliveries", response_model=list[DeliveryResponse])
async def get_alert_deliveries(
    alert_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get delivery attempts for an alert."""
    result = await db.execute(
        text("""
            SELECT id, channel, destination_key, attempt_number, status,
                   response_code, error_message, created_at, sent_at
            FROM alert_deliveries
            WHERE alert_id = :alert_id
            ORDER BY attempt_number
        """),
        {"alert_id": alert_id},
    )

    return [
        DeliveryResponse(
            id=str(row.id),
            channel=row.channel,
            destination_key=row.destination_key,
            attempt_number=row.attempt_number,
            status=row.status,
            response_code=row.response_code,
            error_message=row.error_message,
            created_at=row.created_at,
            sent_at=row.sent_at,
        )
        for row in result
    ]
```

**Step 3: Register router in main.py and run tests**

```python
# Add to backend/src/main.py imports:
from src.api.alerts import router as alerts_router

# Add to router includes:
app.include_router(alerts_router)
```

```bash
cd backend && pytest tests/api/test_alerts.py -v
git add backend/src/api/alerts.py backend/src/main.py backend/tests/api
git commit -m "feat(alerts): add alert API endpoints"
```

---

## Task 11: Frontend Types and Hook

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/hooks/useAlerts.ts`

**Step 1: Add TypeScript types**

```typescript
// Append to frontend/src/types/index.ts

// Alert types
export type AlertSeverity = 1 | 2 | 3;

export interface Alert {
  id: string;
  type: string;
  severity: AlertSeverity;
  summary: string;
  fingerprint: string;
  suppressed_count: number;
  event_timestamp: string;
  created_at: string;
  entity_account_id: string | null;
  entity_symbol: string | null;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
  offset: number;
  limit: number;
}

export interface AlertDelivery {
  id: string;
  channel: string;
  destination_key: string;
  attempt_number: number;
  status: 'pending' | 'sent' | 'failed';
  response_code: number | null;
  error_message: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface AlertStats {
  total_24h: number;
  by_severity: Record<string, number>;
  by_type: Record<string, number>;
  delivery_success_rate: number;
}
```

**Step 2: Create useAlerts hook**

```typescript
// frontend/src/hooks/useAlerts.ts
import { useQuery } from '@tanstack/react-query';
import type { AlertListResponse, AlertStats, AlertDelivery } from '../types';

const API_BASE = '/api/alerts';

async function fetchAlerts(params: {
  severity?: number;
  type?: string;
  offset?: number;
  limit?: number;
}): Promise<AlertListResponse> {
  const searchParams = new URLSearchParams();
  if (params.severity) searchParams.set('severity', String(params.severity));
  if (params.type) searchParams.set('type', params.type);
  if (params.offset) searchParams.set('offset', String(params.offset));
  if (params.limit) searchParams.set('limit', String(params.limit));

  const url = `${API_BASE}?${searchParams}`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch alerts');
  return response.json();
}

async function fetchAlertStats(): Promise<AlertStats> {
  const response = await fetch(`${API_BASE}/stats`);
  if (!response.ok) throw new Error('Failed to fetch alert stats');
  return response.json();
}

async function fetchDeliveries(alertId: string): Promise<AlertDelivery[]> {
  const response = await fetch(`${API_BASE}/${alertId}/deliveries`);
  if (!response.ok) throw new Error('Failed to fetch deliveries');
  return response.json();
}

export function useAlerts(params: {
  severity?: number;
  type?: string;
  offset?: number;
  limit?: number;
} = {}) {
  return useQuery({
    queryKey: ['alerts', params],
    queryFn: () => fetchAlerts(params),
    refetchInterval: 30000, // 30 seconds
  });
}

export function useAlertStats() {
  return useQuery({
    queryKey: ['alertStats'],
    queryFn: fetchAlertStats,
    refetchInterval: 60000, // 1 minute
  });
}

export function useAlertDeliveries(alertId: string) {
  return useQuery({
    queryKey: ['alertDeliveries', alertId],
    queryFn: () => fetchDeliveries(alertId),
    enabled: !!alertId,
  });
}
```

**Step 3: Commit**

```bash
git add frontend/src/types/index.ts frontend/src/hooks/useAlerts.ts
git commit -m "feat(frontend): add alert types and useAlerts hook"
```

---

## Task 12: Frontend AlertsPage

**Files:**
- Create: `frontend/src/pages/AlertsPage.tsx`
- Create: `frontend/src/components/AlertsTable.tsx`
- Create: `frontend/src/components/AlertStats.tsx`
- Modify: `frontend/src/App.tsx` (add route)

**Step 1: Create AlertStats component**

```tsx
// frontend/src/components/AlertStats.tsx
import { useAlertStats } from '../hooks/useAlerts';

export function AlertStats() {
  const { data: stats, isLoading } = useAlertStats();

  if (isLoading) return <div>Loading stats...</div>;
  if (!stats) return null;

  return (
    <div className="grid grid-cols-4 gap-4 mb-6">
      <div className="bg-white rounded-lg p-4 shadow">
        <div className="text-2xl font-bold">{stats.total_24h}</div>
        <div className="text-gray-500 text-sm">Alerts (24h)</div>
      </div>
      <div className="bg-white rounded-lg p-4 shadow">
        <div className="text-2xl font-bold text-red-600">
          {stats.by_severity['SEV1'] || 0}
        </div>
        <div className="text-gray-500 text-sm">Critical (SEV1)</div>
      </div>
      <div className="bg-white rounded-lg p-4 shadow">
        <div className="text-2xl font-bold text-yellow-600">
          {stats.by_severity['SEV2'] || 0}
        </div>
        <div className="text-gray-500 text-sm">Warning (SEV2)</div>
      </div>
      <div className="bg-white rounded-lg p-4 shadow">
        <div className="text-2xl font-bold text-green-600">
          {stats.delivery_success_rate}%
        </div>
        <div className="text-gray-500 text-sm">Delivery Rate</div>
      </div>
    </div>
  );
}
```

**Step 2: Create AlertsTable component**

```tsx
// frontend/src/components/AlertsTable.tsx
import { useState } from 'react';
import { useAlerts } from '../hooks/useAlerts';
import type { Alert } from '../types';

const severityColors: Record<number, string> = {
  1: 'bg-red-100 text-red-800',
  2: 'bg-yellow-100 text-yellow-800',
  3: 'bg-blue-100 text-blue-800',
};

export function AlertsTable() {
  const [severity, setSeverity] = useState<number | undefined>();
  const { data, isLoading } = useAlerts({ severity, limit: 50 });

  if (isLoading) return <div>Loading alerts...</div>;

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="p-4 border-b flex gap-2">
        <button
          onClick={() => setSeverity(undefined)}
          className={`px-3 py-1 rounded ${!severity ? 'bg-gray-200' : ''}`}
        >
          All
        </button>
        <button
          onClick={() => setSeverity(1)}
          className={`px-3 py-1 rounded ${severity === 1 ? 'bg-red-200' : ''}`}
        >
          SEV1
        </button>
        <button
          onClick={() => setSeverity(2)}
          className={`px-3 py-1 rounded ${severity === 2 ? 'bg-yellow-200' : ''}`}
        >
          SEV2
        </button>
      </div>
      <table className="w-full">
        <thead className="bg-gray-50">
          <tr>
            <th className="px-4 py-2 text-left">Severity</th>
            <th className="px-4 py-2 text-left">Type</th>
            <th className="px-4 py-2 text-left">Summary</th>
            <th className="px-4 py-2 text-left">Time</th>
            <th className="px-4 py-2 text-right">Suppressed</th>
          </tr>
        </thead>
        <tbody>
          {data?.alerts.map((alert: Alert) => (
            <tr key={alert.id} className="border-t hover:bg-gray-50">
              <td className="px-4 py-2">
                <span className={`px-2 py-1 rounded text-xs font-medium ${severityColors[alert.severity]}`}>
                  SEV{alert.severity}
                </span>
              </td>
              <td className="px-4 py-2 font-mono text-sm">{alert.type}</td>
              <td className="px-4 py-2">{alert.summary}</td>
              <td className="px-4 py-2 text-sm text-gray-500">
                {new Date(alert.event_timestamp).toLocaleString()}
              </td>
              <td className="px-4 py-2 text-right">
                {alert.suppressed_count > 0 && (
                  <span className="text-gray-500">+{alert.suppressed_count}</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="p-4 border-t text-sm text-gray-500">
        Showing {data?.alerts.length} of {data?.total} alerts
      </div>
    </div>
  );
}
```

**Step 3: Create AlertsPage**

```tsx
// frontend/src/pages/AlertsPage.tsx
import { AlertStats } from '../components/AlertStats';
import { AlertsTable } from '../components/AlertsTable';

export function AlertsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold mb-6">Alerts</h1>
      <AlertStats />
      <AlertsTable />
    </div>
  );
}
```

**Step 4: Add route to App.tsx**

```tsx
// Add to frontend/src/App.tsx
import { AlertsPage } from './pages/AlertsPage';

// In routes:
<Route path="/alerts" element={<AlertsPage />} />

// In navigation:
<Link to="/alerts">Alerts</Link>
```

**Step 5: Commit**

```bash
git add frontend/src/pages/AlertsPage.tsx frontend/src/components/AlertStats.tsx \
        frontend/src/components/AlertsTable.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add AlertsPage with stats and table"
```

---

## Task 13: Integration - Wire AlertService to Business Modules

**Files:**
- Create: `backend/src/alerts/setup.py`
- Modify: `backend/src/main.py`
- Modify: `backend/src/health/monitor.py` (emit alerts on status change)

**Step 1: Create setup module**

```python
# backend/src/alerts/setup.py
"""Alert system initialization."""

import os
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.channels import EmailChannel, WebhookChannel
from src.alerts.hub import NotificationHub
from src.alerts.repository import AlertRepository
from src.alerts.service import AlertService

logger = logging.getLogger(__name__)

_alert_service: AlertService | None = None


async def init_alert_service(db_session: AsyncSession) -> AlertService:
    """Initialize alert service with channels."""
    global _alert_service

    # Create repository
    repo = AlertRepository(db_session)

    # Create channels
    channels = {}

    # Email channel (if configured)
    smtp_host = os.getenv("SMTP_HOST")
    if smtp_host:
        channels["email"] = EmailChannel(
            smtp_host=smtp_host,
            smtp_port=int(os.getenv("SMTP_PORT", "587")),
            sender=os.getenv("SMTP_SENDER", "alerts@localhost"),
            username=os.getenv("SMTP_USERNAME"),
            password=os.getenv("SMTP_PASSWORD"),
        )
        logger.info("Email channel configured")

    # Webhook channel (always available)
    channels["webhook"] = WebhookChannel()
    logger.info("Webhook channel configured")

    # Create hub
    hub = NotificationHub(repository=repo, channels=channels)
    await hub.start(num_workers=2)

    # Create service
    _alert_service = AlertService(repository=repo, hub=hub)
    logger.info("AlertService initialized")

    return _alert_service


def get_alert_service() -> AlertService | None:
    """Get the global alert service instance."""
    return _alert_service
```

**Step 2: Update main.py lifespan**

```python
# backend/src/main.py - update lifespan
from src.alerts.setup import init_alert_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    # Startup
    init_health_monitor()
    # Note: AlertService needs DB session, initialized per-request or with background session
    yield
    # Shutdown
```

**Step 3: Example integration with HealthMonitor**

```python
# Example: Modify backend/src/health/monitor.py to emit alerts

from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity
from src.alerts.setup import get_alert_service

async def _emit_health_alert(component: str, status: ComponentStatus, prev_status: ComponentStatus | None):
    """Emit alert on health status change."""
    service = get_alert_service()
    if not service:
        return

    if status == ComponentStatus.DOWN and prev_status != ComponentStatus.DOWN:
        alert = create_alert(
            type=AlertType.COMPONENT_UNHEALTHY,
            severity=Severity.SEV1,
            summary=f"{component} is DOWN",
            details={"component": component, "previous_status": prev_status.value if prev_status else None},
        )
        await service.emit(alert)

    elif status == ComponentStatus.HEALTHY and prev_status == ComponentStatus.DOWN:
        alert = create_alert(
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV2,
            summary=f"{component} recovered",
            details={"component": component},
        )
        await service.emit(alert)
```

**Step 4: Commit**

```bash
git add backend/src/alerts/setup.py backend/src/main.py backend/src/health/monitor.py
git commit -m "feat(alerts): integrate AlertService with application lifecycle"
```

---

## Task 14: Update Exports and Final Tests

**Files:**
- Update: `backend/src/alerts/__init__.py`
- Run: Full test suite

**Step 1: Update exports**

```python
# backend/src/alerts/__init__.py
"""Alert system package."""

from src.alerts.channels import (
    DeliveryResult,
    EmailChannel,
    NotificationChannel,
    WebhookChannel,
)
from src.alerts.factory import (
    compute_dedupe_key,
    create_alert,
    validate_alert,
)
from src.alerts.hub import NotificationHub
from src.alerts.models import (
    AlertEvent,
    AlertType,
    EntityRef,
    JsonScalar,
    RECOVERY_TYPES,
    Severity,
    sanitize_details,
    to_json_safe,
)
from src.alerts.repository import AlertRepository
from src.alerts.routing import (
    RoutingConfig,
    get_destinations_for_alert,
)
from src.alerts.service import AlertService
from src.alerts.setup import get_alert_service, init_alert_service

__all__ = [
    # Models
    "AlertEvent",
    "AlertType",
    "EntityRef",
    "JsonScalar",
    "RECOVERY_TYPES",
    "Severity",
    # Factory
    "compute_dedupe_key",
    "create_alert",
    "validate_alert",
    # Serialization
    "sanitize_details",
    "to_json_safe",
    # Channels
    "DeliveryResult",
    "EmailChannel",
    "NotificationChannel",
    "WebhookChannel",
    # Hub
    "NotificationHub",
    # Repository
    "AlertRepository",
    # Routing
    "RoutingConfig",
    "get_destinations_for_alert",
    # Service
    "AlertService",
    "get_alert_service",
    "init_alert_service",
]
```

**Step 2: Run full test suite**

```bash
cd backend && pytest tests/alerts/ -v
cd backend && pytest -v  # All tests
```

**Step 3: Final commit**

```bash
git add backend/src/alerts/__init__.py
git commit -m "feat(alerts): complete Slice 3.1 Alert System"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Alert Models | `alerts/models.py` |
| 2 | JSON Serialization | `alerts/models.py` |
| 3 | Alert Factory | `alerts/factory.py` |
| 4 | DB Migration | `alembic/versions/004_alerts_tables.py` |
| 5 | Alert Repository | `alerts/repository.py` |
| 6 | Notification Channels | `alerts/channels.py` |
| 7 | Routing Config | `alerts/routing.py` |
| 8 | NotificationHub | `alerts/hub.py` |
| 9 | AlertService | `alerts/service.py` |
| 10 | Alert API | `api/alerts.py` |
| 11 | Frontend Types/Hook | `types/index.ts`, `hooks/useAlerts.ts` |
| 12 | AlertsPage | `pages/AlertsPage.tsx`, components |
| 13 | Integration | `alerts/setup.py`, main.py |
| 14 | Exports & Tests | `alerts/__init__.py` |

**Exit Criteria:**
- Alerts persist with deduplication
- Email and webhook channels deliver with retry
- SEV1 never dropped
- Dashboard shows alert stats and history
- Business modules can emit alerts via AlertService
