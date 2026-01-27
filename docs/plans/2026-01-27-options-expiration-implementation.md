# Options Expiration Alerts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement V1 of Options Lifecycle - expiration alerts with manual handling (close/acknowledge)

**Architecture:**
- Extend alerts platform with configurable deduplication strategy (PERMANENT_PER_THRESHOLD)
- ExpirationChecker scans option positions daily, creates alerts per threshold (7/3/1/0 days)
- Two frontend views: /alerts (discovery) + /options/expiring (action)

**Tech Stack:** Python/FastAPI, SQLAlchemy, APScheduler, Postgres Advisory Lock, React/TypeScript

**Design Doc:** `docs/plans/2026-01-27-options-expiration-design.md`

---

## Phase 1: Database Migrations (Day 1)

### Task 1.1: Create Migration - Alerts Unique Index

**Files:**
- Create: `backend/alembic/versions/007_alerts_dedupe_unique_index.py`

**Step 1: Create migration file**

```python
"""Add unique index on alerts(type, dedupe_key)

Revision ID: 007
Revises: 006_degradation
Create Date: 2026-01-27
"""
from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add composite unique index for deduplication
    # This enables ON CONFLICT behavior for idempotent writes
    op.create_index(
        "idx_alerts_type_dedupe_key",
        "alerts",
        ["type", "dedupe_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("idx_alerts_type_dedupe_key", table_name="alerts")
```

**Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration applies successfully

**Step 3: Verify index exists**

Run: `cd backend && alembic current`
Expected: Shows revision 007

**Step 4: Commit**

```bash
git add backend/alembic/versions/007_alerts_dedupe_unique_index.py
git commit -m "chore(db): add unique index on alerts(type, dedupe_key)"
```

---

### Task 1.2: Create Migration - Idempotency Keys Table

**Files:**
- Create: `backend/alembic/versions/008_idempotency_keys.py`

**Step 1: Create migration file**

```python
"""Add idempotency_keys table for API request deduplication

Revision ID: 008
Revises: 007
Create Date: 2026-01-27
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("response_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Index for cleanup job (delete expired keys)
    op.create_index(
        "idx_idempotency_expires",
        "idempotency_keys",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_idempotency_expires", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
```

**Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Table created successfully

**Step 3: Commit**

```bash
git add backend/alembic/versions/008_idempotency_keys.py
git commit -m "chore(db): add idempotency_keys table for API deduplication"
```

---

### Task 1.3: Create Migration - Performance Indexes

**Files:**
- Create: `backend/alembic/versions/009_options_expiration_indexes.py`

**Step 1: Create migration file**

```python
"""Add performance indexes for options expiration queries

Revision ID: 009
Revises: 008
Create Date: 2026-01-27
"""
from alembic import op

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Index for GET /api/options/expiring queries
    op.create_index(
        "idx_alerts_type_created",
        "alerts",
        ["type", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )

    # Partial index for option expiring alerts
    op.execute("""
        CREATE INDEX idx_alerts_option_expiring_pending
        ON alerts (entity_account_id, created_at DESC)
        WHERE type = 'option_expiring'
    """)

    # Index for positions query (if not exists)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_positions_option_expiry
        ON positions (asset_type, expiry)
        WHERE asset_type = 'option'
    """)


def downgrade() -> None:
    op.drop_index("idx_alerts_type_created", table_name="alerts")
    op.execute("DROP INDEX IF EXISTS idx_alerts_option_expiring_pending")
    op.execute("DROP INDEX IF EXISTS idx_positions_option_expiry")
```

**Step 2: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Indexes created successfully

**Step 3: Commit**

```bash
git add backend/alembic/versions/009_options_expiration_indexes.py
git commit -m "chore(db): add performance indexes for options expiration"
```

---

## Phase 2: Alerts Platform Enhancement (Day 1-2)

### Task 2.1: Add OPTION_EXPIRING Alert Type

**Files:**
- Modify: `backend/src/alerts/models.py:31-62`
- Test: `backend/tests/alerts/test_models.py`

**Step 1: Write the failing test**

Create `backend/tests/alerts/test_option_expiring_type.py`:

```python
"""Tests for OPTION_EXPIRING alert type."""
import pytest
from src.alerts.models import AlertType, Severity


def test_option_expiring_alert_type_exists():
    """OPTION_EXPIRING should be a valid AlertType."""
    assert hasattr(AlertType, "OPTION_EXPIRING")
    assert AlertType.OPTION_EXPIRING.value == "option_expiring"


def test_option_expiring_is_not_recovery_type():
    """OPTION_EXPIRING should not be in RECOVERY_TYPES."""
    from src.alerts.models import RECOVERY_TYPES
    assert AlertType.OPTION_EXPIRING not in RECOVERY_TYPES
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/alerts/test_option_expiring_type.py -v`
Expected: FAIL with "AttributeError: OPTION_EXPIRING"

**Step 3: Add OPTION_EXPIRING to AlertType enum**

In `backend/src/alerts/models.py`, add after line 61:

```python
    # Options alerts
    OPTION_EXPIRING = "option_expiring"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/alerts/test_option_expiring_type.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/alerts/models.py backend/tests/alerts/test_option_expiring_type.py
git commit -m "feat(alerts): add OPTION_EXPIRING alert type"
```

---

### Task 2.2: Create Deduplication Strategy Config

**Files:**
- Create: `backend/src/alerts/config.py`
- Test: `backend/tests/alerts/test_config.py`

**Step 1: Write the failing test**

Create `backend/tests/alerts/test_config.py`:

```python
"""Tests for alert deduplication strategy configuration."""
import pytest


def test_dedupe_strategy_enum_exists():
    """DedupeStrategy enum should exist with expected values."""
    from src.alerts.config import DedupeStrategy

    assert DedupeStrategy.WINDOWED_10M.value == "windowed_10m"
    assert DedupeStrategy.PERMANENT_PER_THRESHOLD.value == "permanent_per_threshold"


def test_option_expiring_uses_permanent_strategy():
    """OPTION_EXPIRING should use PERMANENT_PER_THRESHOLD strategy."""
    from src.alerts.config import get_dedupe_strategy, DedupeStrategy
    from src.alerts.models import AlertType

    strategy = get_dedupe_strategy(AlertType.OPTION_EXPIRING)
    assert strategy == DedupeStrategy.PERMANENT_PER_THRESHOLD


def test_other_types_use_windowed_strategy():
    """Other alert types should default to WINDOWED_10M."""
    from src.alerts.config import get_dedupe_strategy, DedupeStrategy
    from src.alerts.models import AlertType

    strategy = get_dedupe_strategy(AlertType.ORDER_REJECTED)
    assert strategy == DedupeStrategy.WINDOWED_10M
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/alerts/test_config.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.alerts.config'"

**Step 3: Create config.py**

Create `backend/src/alerts/config.py`:

```python
"""Alert deduplication strategy configuration.

This module defines configurable deduplication strategies for different alert types.
The default strategy (WINDOWED_10M) groups alerts within 10-minute windows.
Special strategies can be registered for specific alert types.
"""
from enum import Enum

from src.alerts.models import AlertType


class DedupeStrategy(str, Enum):
    """Alert deduplication strategies.

    WINDOWED_10M: Group alerts within 10-minute windows (default)
    PERMANENT_PER_THRESHOLD: Dedupe permanently by threshold, no time window
    """

    WINDOWED_10M = "windowed_10m"
    PERMANENT_PER_THRESHOLD = "permanent_per_threshold"


# Alert type to deduplication strategy mapping
DEDUPE_STRATEGIES: dict[AlertType, DedupeStrategy] = {
    AlertType.OPTION_EXPIRING: DedupeStrategy.PERMANENT_PER_THRESHOLD,
    # All other types default to WINDOWED_10M
}


def get_dedupe_strategy(alert_type: AlertType) -> DedupeStrategy:
    """Get deduplication strategy for an alert type.

    Args:
        alert_type: The type of alert

    Returns:
        The deduplication strategy to use
    """
    return DEDUPE_STRATEGIES.get(alert_type, DedupeStrategy.WINDOWED_10M)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/alerts/test_config.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/alerts/config.py backend/tests/alerts/test_config.py
git commit -m "feat(alerts): add configurable deduplication strategy system"
```

---

### Task 2.3: Modify _build_fingerprint for OPTION_EXPIRING

**Files:**
- Modify: `backend/src/alerts/factory.py:179-186`
- Test: `backend/tests/alerts/test_factory_option_expiring.py`

**Step 1: Write the failing test**

Create `backend/tests/alerts/test_factory_option_expiring.py`:

```python
"""Tests for OPTION_EXPIRING fingerprint and dedupe key generation."""
import pytest
from src.alerts.models import AlertType, Severity
from src.alerts.factory import create_alert, compute_dedupe_key


def test_option_expiring_fingerprint_uses_position_id():
    """Fingerprint should use position_id from details, not symbol."""
    alert = create_alert(
        type=AlertType.OPTION_EXPIRING,
        severity=Severity.SEV1,
        summary="Test option expiring",
        account_id="acc123",
        symbol="AAPL240119C150",  # This should NOT be in fingerprint
        details={
            "position_id": 456,
            "threshold_days": 7,
            "expiry_date": "2024-01-19",
            "days_to_expiry": 7,
            "strike": 150.0,
            "put_call": "call",
        },
    )

    # Fingerprint should be: option_expiring:acc123:456
    # NOT: option_expiring:acc123:AAPL240119C150::
    assert "456" in alert.fingerprint
    assert "AAPL240119C150" not in alert.fingerprint


def test_option_expiring_dedupe_key_is_permanent():
    """Dedupe key should include threshold and 'permanent' suffix."""
    alert = create_alert(
        type=AlertType.OPTION_EXPIRING,
        severity=Severity.SEV1,
        summary="Test option expiring",
        account_id="acc123",
        symbol="AAPL240119C150",
        details={
            "position_id": 456,
            "threshold_days": 7,
            "expiry_date": "2024-01-19",
            "days_to_expiry": 7,
            "strike": 150.0,
            "put_call": "call",
        },
    )

    dedupe_key = compute_dedupe_key(alert)

    # Should contain threshold and permanent marker
    assert "threshold_7" in dedupe_key
    assert "permanent" in dedupe_key
    # Should NOT contain time bucket
    assert dedupe_key.count(":") >= 3  # Multiple colons in permanent format


def test_option_expiring_raises_without_position_id():
    """Should raise ValueError if position_id is missing."""
    with pytest.raises(ValueError, match="position_id"):
        create_alert(
            type=AlertType.OPTION_EXPIRING,
            severity=Severity.SEV1,
            summary="Test option expiring",
            account_id="acc123",
            details={
                "threshold_days": 7,
                # position_id is missing!
            },
        )


def test_option_expiring_dedupe_key_raises_without_threshold():
    """compute_dedupe_key should raise if threshold_days is missing."""
    # Create alert without going through factory validation
    from src.alerts.models import AlertEvent
    from uuid import uuid4
    from datetime import datetime, timezone

    alert = AlertEvent(
        alert_id=uuid4(),
        type=AlertType.OPTION_EXPIRING,
        severity=Severity.SEV1,
        event_timestamp=datetime.now(timezone.utc),
        fingerprint="option_expiring:acc123:456",
        entity_ref=None,
        summary="Test",
        details={"position_id": 456},  # No threshold_days
    )

    with pytest.raises(ValueError, match="threshold_days"):
        compute_dedupe_key(alert)


def test_other_alert_types_unchanged():
    """Other alert types should still use original fingerprint logic."""
    alert = create_alert(
        type=AlertType.ORDER_REJECTED,
        severity=Severity.SEV2,
        summary="Order rejected",
        account_id="acc123",
        symbol="AAPL",
    )

    # Should use symbol in fingerprint
    assert "AAPL" in alert.fingerprint

    dedupe_key = compute_dedupe_key(alert)
    # Should NOT contain 'permanent'
    assert "permanent" not in dedupe_key
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/alerts/test_factory_option_expiring.py -v`
Expected: FAIL (fingerprint still uses symbol)

**Step 3: Modify factory.py**

In `backend/src/alerts/factory.py`, add import at top:

```python
from src.alerts.config import DedupeStrategy, get_dedupe_strategy
```

Replace `_build_fingerprint` function (lines 179-186):

```python
def _build_fingerprint(
    alert_type: AlertType,
    account_id: str | None,
    symbol: str | None,
    strategy_id: str | None,
    details: dict[str, Any] | None = None,
) -> str:
    """Build fingerprint for alert deduplication.

    For OPTION_EXPIRING: uses position_id instead of symbol
    For other types: uses standard format {type}:{account}:{symbol}:{strategy}
    """
    # OPTION_EXPIRING uses position_id for stable entity identification
    if alert_type == AlertType.OPTION_EXPIRING:
        position_id = details.get("position_id") if details else None
        if position_id is None:
            raise ValueError(
                "OPTION_EXPIRING alert requires 'position_id' in details"
            )
        # fingerprint: option_expiring:{account_id}:{position_id}
        # Note: strategy_id excluded - expiration is position-level event
        return f"{alert_type.value}:{account_id or ''}:{position_id}"

    # Standard fingerprint for other types
    return f"{alert_type.value}:{account_id or ''}:{symbol or ''}:{strategy_id or ''}"
```

Update `create_alert` to pass details to `_build_fingerprint` (around line 81):

```python
    # Build fingerprint (pass details for special types like OPTION_EXPIRING)
    fingerprint = _build_fingerprint(type, account_id, symbol, strategy_id, details)
```

Replace `compute_dedupe_key` function:

```python
def compute_dedupe_key(alert: AlertEvent) -> str:
    """Compute deduplication key for an alert.

    Strategy depends on alert type:
    - RECOVERY_TYPES: {fingerprint}:recovery:{alert_id}
    - PERMANENT_PER_THRESHOLD: {fingerprint}:threshold_{N}:permanent
    - WINDOWED_10M (default): {fingerprint}:{bucket}
    """
    import logging
    logger = logging.getLogger(__name__)

    if alert.type in RECOVERY_TYPES:
        # Recovery events: unique by alert_id
        return f"{alert.fingerprint}:recovery:{alert.alert_id}"

    strategy = get_dedupe_strategy(alert.type)

    if strategy == DedupeStrategy.PERMANENT_PER_THRESHOLD:
        # Permanent deduplication by threshold (e.g., OPTION_EXPIRING)
        threshold_days = alert.details.get("threshold_days")
        position_id = alert.details.get("position_id", "UNKNOWN")

        if threshold_days is None:
            logger.error(
                f"Alert type {alert.type} requires 'threshold_days' in details "
                f"(position_id={position_id}, alert_id={alert.alert_id})"
            )
            raise ValueError(
                f"Alert type {alert.type} requires 'threshold_days' in details "
                f"(position_id={position_id})"
            )

        return f"{alert.fingerprint}:threshold_{threshold_days}:permanent"

    else:  # WINDOWED_10M (default)
        bucket = int(alert.event_timestamp.timestamp()) // (COOLDOWN_WINDOW_MINUTES * 60)
        return f"{alert.fingerprint}:{bucket}"
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/alerts/test_factory_option_expiring.py -v`
Expected: PASS

**Step 5: Run regression tests**

Run: `cd backend && pytest tests/alerts/ -v`
Expected: All tests pass (no regression)

**Step 6: Commit**

```bash
git add backend/src/alerts/factory.py backend/tests/alerts/test_factory_option_expiring.py
git commit -m "feat(alerts): implement OPTION_EXPIRING fingerprint and dedupe strategy"
```

---

## Phase 3: Options Expiration Core (Day 2-3)

### Task 3.1: Create Threshold Configuration

**Files:**
- Create: `backend/src/options/__init__.py`
- Create: `backend/src/options/thresholds.py`
- Test: `backend/tests/options/test_thresholds.py`

**Step 1: Create options module**

```bash
mkdir -p backend/src/options backend/tests/options
touch backend/src/options/__init__.py backend/tests/options/__init__.py
```

**Step 2: Write the failing test**

Create `backend/tests/options/test_thresholds.py`:

```python
"""Tests for expiration threshold configuration."""
import pytest
from src.alerts.models import Severity


def test_threshold_dataclass():
    """ExpirationThreshold should be a proper dataclass."""
    from src.options.thresholds import ExpirationThreshold

    t = ExpirationThreshold(days=7, severity=Severity.SEV3)
    assert t.days == 7
    assert t.severity == Severity.SEV3


def test_expiration_thresholds_list():
    """EXPIRATION_THRESHOLDS should have 4 entries (0/1/3/7 days)."""
    from src.options.thresholds import EXPIRATION_THRESHOLDS

    assert len(EXPIRATION_THRESHOLDS) == 4

    # Should be sorted ascending by days
    days = [t.days for t in EXPIRATION_THRESHOLDS]
    assert days == [0, 1, 3, 7]


def test_max_threshold_days():
    """MAX_THRESHOLD_DAYS should be 7."""
    from src.options.thresholds import MAX_THRESHOLD_DAYS
    assert MAX_THRESHOLD_DAYS == 7


def test_get_applicable_thresholds_dte_10():
    """DTE=10 should return empty list (out of scope)."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(10)
    assert result == []


def test_get_applicable_thresholds_dte_6():
    """DTE=6 should return [7-day threshold]."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(6)
    assert len(result) == 1
    assert result[0].days == 7


def test_get_applicable_thresholds_dte_2():
    """DTE=2 should return [3-day, 7-day thresholds]."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(2)
    assert len(result) == 2
    days = [t.days for t in result]
    assert 3 in days
    assert 7 in days


def test_get_applicable_thresholds_dte_1():
    """DTE=1 should return [1-day, 3-day, 7-day thresholds]."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(1)
    assert len(result) == 3
    days = [t.days for t in result]
    assert days == [1, 3, 7]


def test_get_applicable_thresholds_dte_0():
    """DTE=0 should return all 4 thresholds."""
    from src.options.thresholds import get_applicable_thresholds

    result = get_applicable_thresholds(0)
    assert len(result) == 4
    days = [t.days for t in result]
    assert days == [0, 1, 3, 7]


def test_severity_mapping():
    """Check severity levels are correct."""
    from src.options.thresholds import EXPIRATION_THRESHOLDS

    severity_map = {t.days: t.severity for t in EXPIRATION_THRESHOLDS}

    assert severity_map[0] == Severity.SEV1  # Critical (today)
    assert severity_map[1] == Severity.SEV1  # Critical (tomorrow)
    assert severity_map[3] == Severity.SEV2  # Warning
    assert severity_map[7] == Severity.SEV3  # Info
```

**Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/options/test_thresholds.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 4: Create thresholds.py**

Create `backend/src/options/thresholds.py`:

```python
"""Expiration threshold configuration for options alerts.

This module defines the threshold-driven logic for option expiration alerts.
Thresholds are table-driven for easy modification (upgrade to config file later).
"""
from dataclasses import dataclass

from src.alerts.models import Severity


@dataclass(frozen=True)
class ExpirationThreshold:
    """Expiration threshold configuration.

    Attributes:
        days: Days to expiry that triggers this threshold
        severity: Alert severity level for this threshold
    """

    days: int
    severity: Severity


# Threshold table (ascending by days: 0 is most urgent, 7 is least)
EXPIRATION_THRESHOLDS = [
    ExpirationThreshold(days=0, severity=Severity.SEV1),  # Today - critical
    ExpirationThreshold(days=1, severity=Severity.SEV1),  # Tomorrow - critical
    ExpirationThreshold(days=3, severity=Severity.SEV2),  # 3 days - warning
    ExpirationThreshold(days=7, severity=Severity.SEV3),  # 7 days - info
]

# Maximum threshold for "out of scope" classification
MAX_THRESHOLD_DAYS = max(t.days for t in EXPIRATION_THRESHOLDS)


def get_applicable_thresholds(days_to_expiry: int) -> list[ExpirationThreshold]:
    """Return all thresholds that should trigger for given DTE.

    Returns thresholds where threshold.days >= days_to_expiry.
    This enables "catch-up" behavior on restart: DTE=0 triggers all 4 thresholds,
    relying on dedupe_key to filter already-created alerts.

    Args:
        days_to_expiry: Days until option expiration (must be >= 0)

    Returns:
        List of applicable thresholds, sorted by days ascending

    Examples:
        DTE=10 -> []
        DTE=6  -> [7-day]
        DTE=2  -> [3-day, 7-day]
        DTE=1  -> [1-day, 3-day, 7-day]
        DTE=0  -> [0-day, 1-day, 3-day, 7-day]
    """
    return [t for t in EXPIRATION_THRESHOLDS if t.days >= days_to_expiry]
```

**Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/options/test_thresholds.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/options/ backend/tests/options/
git commit -m "feat(options): add expiration threshold configuration"
```

---

### Task 3.2: Create Prometheus Metrics

**Files:**
- Create: `backend/src/options/metrics.py`
- Test: `backend/tests/options/test_metrics.py`

**Step 1: Write the failing test**

Create `backend/tests/options/test_metrics.py`:

```python
"""Tests for options expiration metrics."""
import pytest


def test_metrics_exist():
    """All required metrics should be defined."""
    from src.options.metrics import (
        expiration_check_runs_total,
        alerts_created_total,
        alerts_deduped_total,
        check_errors_total,
        check_duration_seconds,
        pending_alerts_gauge,
    )

    # Just verify they exist and are the right types
    assert expiration_check_runs_total is not None
    assert alerts_created_total is not None
    assert alerts_deduped_total is not None
    assert check_errors_total is not None
    assert check_duration_seconds is not None
    assert pending_alerts_gauge is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/options/test_metrics.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create metrics.py**

Create `backend/src/options/metrics.py`:

```python
"""Prometheus metrics for options expiration monitoring.

Metrics exported:
- options_expiration_check_runs_total: Counter of check runs by status
- options_expiration_alerts_created_total: Counter of alerts created
- options_expiration_alerts_deduped_total: Counter of deduplicated alerts
- options_expiration_check_errors_total: Counter of errors by type
- options_expiration_check_duration_seconds: Histogram of check duration
- options_expiration_pending_alerts: Gauge of unacknowledged alerts
"""
from prometheus_client import Counter, Histogram, Gauge

# Check execution metrics
expiration_check_runs_total = Counter(
    "options_expiration_check_runs_total",
    "Total number of expiration check runs",
    ["status"],  # success, failed, skipped
)

# Alert creation metrics
alerts_created_total = Counter(
    "options_expiration_alerts_created_total",
    "Total number of expiration alerts created",
)

alerts_deduped_total = Counter(
    "options_expiration_alerts_deduped_total",
    "Total number of deduplicated expiration alerts",
)

# Error metrics
check_errors_total = Counter(
    "options_expiration_check_errors_total",
    "Total number of errors during expiration check",
    ["error_type"],  # missing_expiry, alert_creation, position_processing
)

# Performance metrics
check_duration_seconds = Histogram(
    "options_expiration_check_duration_seconds",
    "Duration of expiration check in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# Current state metrics
pending_alerts_gauge = Gauge(
    "options_expiration_pending_alerts",
    "Number of pending (unacknowledged) expiration alerts",
)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/options/test_metrics.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/options/metrics.py backend/tests/options/test_metrics.py
git commit -m "feat(options): add Prometheus metrics for expiration checks"
```

---

### Task 3.3: Create ExpirationChecker

**Files:**
- Create: `backend/src/options/checker.py`
- Test: `backend/tests/options/test_checker.py`

**Step 1: Write the failing test**

Create `backend/tests/options/test_checker.py`:

```python
"""Tests for ExpirationChecker."""
import pytest
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from src.alerts.models import Severity
from src.models.position import AssetType, PutCall


@pytest.fixture
def mock_position():
    """Create a mock option position."""
    pos = MagicMock()
    pos.id = 123
    pos.symbol = "AAPL240119C150"
    pos.asset_type = AssetType.OPTION
    pos.expiry = date.today() + timedelta(days=1)  # Tomorrow
    pos.strike = Decimal("150.00")
    pos.put_call = PutCall.CALL
    pos.quantity = 10
    return pos


@pytest.fixture
def mock_portfolio():
    """Create a mock PortfolioManager."""
    portfolio = AsyncMock()
    return portfolio


@pytest.fixture
def mock_alert_repo():
    """Create a mock AlertRepository."""
    repo = AsyncMock()
    repo.persist_alert.return_value = (True, "alert-123")  # is_new=True
    return repo


class TestExpirationChecker:
    """Tests for ExpirationChecker class."""

    @pytest.mark.asyncio
    async def test_check_expirations_creates_alerts(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should create alerts for positions within threshold."""
        from src.options.checker import ExpirationChecker

        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ZoneInfo("America/New_York"),
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_checked"] == 1
        assert stats["alerts_created"] >= 1  # At least 1 threshold triggered
        assert mock_alert_repo.persist_alert.called

    @pytest.mark.asyncio
    async def test_check_expirations_deduplicates(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should count deduplicated alerts correctly."""
        from src.options.checker import ExpirationChecker

        mock_portfolio.get_positions.return_value = [mock_position]
        mock_alert_repo.persist_alert.return_value = (False, "alert-123")  # is_new=False

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["alerts_created"] == 0
        assert stats["alerts_deduplicated"] >= 1

    @pytest.mark.asyncio
    async def test_check_expirations_skips_missing_expiry(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should skip positions without expiry date."""
        from src.options.checker import ExpirationChecker

        mock_position.expiry = None
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_skipped_missing_expiry"] == 1
        assert "missing expiry" in stats["errors"][0].lower()

    @pytest.mark.asyncio
    async def test_check_expirations_skips_expired(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should skip already expired positions."""
        from src.options.checker import ExpirationChecker

        mock_position.expiry = date.today() - timedelta(days=1)  # Yesterday
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_already_expired"] == 1
        assert stats["alerts_created"] == 0

    @pytest.mark.asyncio
    async def test_check_expirations_skips_out_of_scope(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should skip positions outside threshold range (DTE > 7)."""
        from src.options.checker import ExpirationChecker

        mock_position.expiry = date.today() + timedelta(days=30)  # 30 days out
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert stats["positions_not_expiring_soon"] == 1
        assert stats["alerts_created"] == 0

    @pytest.mark.asyncio
    async def test_check_expirations_filters_options_only(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Should only process OPTION positions."""
        from src.options.checker import ExpirationChecker

        stock_position = MagicMock()
        stock_position.asset_type = AssetType.STOCK

        mock_portfolio.get_positions.return_value = [stock_position, mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        # Only the option should be checked
        assert stats["positions_checked"] == 1

    @pytest.mark.asyncio
    async def test_check_expirations_returns_run_id(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """Stats should include run_id for traceability."""
        from src.options.checker import ExpirationChecker

        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
        )

        stats = await checker.check_expirations("acc123")

        assert "run_id" in stats
        assert len(stats["run_id"]) > 0


class TestDTECalculation:
    """Tests for DTE (days to expiry) calculation."""

    @pytest.mark.asyncio
    async def test_dte_uses_market_timezone(
        self, mock_portfolio, mock_alert_repo, mock_position
    ):
        """DTE should be calculated using market timezone."""
        from src.options.checker import ExpirationChecker

        # Set position to expire "today" in NY timezone
        ny_tz = ZoneInfo("America/New_York")
        ny_today = datetime.now(ny_tz).date()
        mock_position.expiry = ny_today
        mock_portfolio.get_positions.return_value = [mock_position]

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ny_tz,
        )

        stats = await checker.check_expirations("acc123")

        # Should trigger all 4 thresholds (DTE=0)
        # Since this is DTE=0, all 4 thresholds apply
        assert stats["alerts_attempted"] == 4
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/options/test_checker.py -v`
Expected: FAIL with ModuleNotFoundError

**Step 3: Create checker.py**

Create `backend/src/options/checker.py`:

```python
"""Expiration checker for option positions.

This module implements the ExpirationChecker class that:
1. Scans option positions for upcoming expirations
2. Creates alerts for each applicable threshold
3. Uses dedupe_key for idempotent alert creation
"""
import logging
from datetime import datetime
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.alerts.factory import create_alert
from src.alerts.models import AlertType
from src.alerts.repository import AlertRepository
from src.core.portfolio import PortfolioManager
from src.models.position import AssetType
from src.options.thresholds import ExpirationThreshold, get_applicable_thresholds
from src.options.metrics import (
    expiration_check_runs_total,
    alerts_created_total,
    alerts_deduped_total,
    check_errors_total,
    check_duration_seconds,
)

logger = logging.getLogger(__name__)


class ExpirationChecker:
    """Checks option positions for upcoming expirations and creates alerts.

    Responsibilities:
    1. Scan all option positions for an account
    2. Calculate days to expiry (DTE) using market timezone
    3. Create alerts for each applicable threshold
    4. Rely on dedupe_key for idempotent writes
    """

    def __init__(
        self,
        portfolio: PortfolioManager,
        alert_repo: AlertRepository,
        market_tz: ZoneInfo = ZoneInfo("America/New_York"),
    ):
        """Initialize the checker.

        Args:
            portfolio: Portfolio manager for fetching positions
            alert_repo: Alert repository for persisting alerts
            market_tz: Market timezone for DTE calculation (default: US East)
        """
        self.portfolio = portfolio
        self.alert_repo = alert_repo
        self.market_tz = market_tz

    @check_duration_seconds.time()
    async def check_expirations(self, account_id: str) -> dict:
        """Check option positions and create expiration alerts.

        Args:
            account_id: Account to check positions for

        Returns:
            Statistics dictionary with counts and errors
        """
        run_id = str(uuid4())
        logger.info(f"Starting expiration check run_id={run_id} account={account_id}")

        stats = {
            "run_id": run_id,
            "positions_checked": 0,
            "positions_skipped_missing_expiry": 0,
            "positions_already_expired": 0,
            "positions_not_expiring_soon": 0,
            "alerts_attempted": 0,
            "alerts_created": 0,
            "alerts_deduplicated": 0,
            "errors": [],
        }

        try:
            # Get all positions and filter to options
            positions = await self.portfolio.get_positions(account_id=account_id)
            option_positions = [p for p in positions if p.asset_type == AssetType.OPTION]

            # Calculate "today" in market timezone
            today = datetime.now(self.market_tz).date()
            logger.info(
                f"run_id={run_id} checking {len(option_positions)} option positions "
                f"relative to {today} ({self.market_tz})"
            )

            for pos in option_positions:
                stats["positions_checked"] += 1

                try:
                    # Validate expiry exists
                    if pos.expiry is None:
                        error_msg = (
                            f"Position {pos.id} (symbol={pos.symbol}) missing expiry date"
                        )
                        logger.warning(f"run_id={run_id} {error_msg}")
                        stats["positions_skipped_missing_expiry"] += 1
                        stats["errors"].append(error_msg)
                        check_errors_total.labels(error_type="missing_expiry").inc()
                        continue

                    # Calculate DTE
                    days_to_expiry = (pos.expiry - today).days

                    # Skip already expired
                    if days_to_expiry < 0:
                        stats["positions_already_expired"] += 1
                        logger.debug(f"run_id={run_id} position {pos.id} already expired")
                        continue

                    # Get applicable thresholds
                    thresholds = get_applicable_thresholds(days_to_expiry)

                    if not thresholds:
                        stats["positions_not_expiring_soon"] += 1
                        logger.debug(
                            f"run_id={run_id} position {pos.id} "
                            f"DTE={days_to_expiry} out of scope"
                        )
                        continue

                    # Create alert for each threshold
                    for threshold in thresholds:
                        stats["alerts_attempted"] += 1

                        try:
                            alert = self._create_expiration_alert(
                                position=pos,
                                threshold=threshold,
                                days_to_expiry=days_to_expiry,
                                account_id=account_id,
                            )

                            # Idempotent write (dedupe_key handles duplicates)
                            is_new, alert_id = await self.alert_repo.persist_alert(alert)

                            if is_new:
                                stats["alerts_created"] += 1
                                alerts_created_total.inc()
                                logger.info(
                                    f"run_id={run_id} created alert: "
                                    f"position_id={pos.id} symbol={pos.symbol} "
                                    f"DTE={days_to_expiry} threshold={threshold.days}d "
                                    f"alert_id={alert_id}"
                                )
                            else:
                                stats["alerts_deduplicated"] += 1
                                alerts_deduped_total.inc()
                                logger.debug(
                                    f"run_id={run_id} alert deduplicated: "
                                    f"position_id={pos.id} threshold={threshold.days}d"
                                )

                        except Exception as e:
                            error_msg = (
                                f"Failed to create alert for position_id={pos.id} "
                                f"threshold={threshold.days}d: {e}"
                            )
                            logger.error(f"run_id={run_id} {error_msg}", exc_info=True)
                            stats["errors"].append(error_msg)
                            check_errors_total.labels(error_type="alert_creation").inc()

                except Exception as e:
                    error_msg = f"Failed to process position_id={pos.id}: {e}"
                    logger.error(f"run_id={run_id} {error_msg}", exc_info=True)
                    stats["errors"].append(error_msg)
                    check_errors_total.labels(error_type="position_processing").inc()

            logger.info(
                f"run_id={run_id} check complete: "
                f"{stats['positions_checked']} checked, "
                f"{stats['alerts_created']} created, "
                f"{stats['alerts_deduplicated']} deduplicated, "
                f"{len(stats['errors'])} errors"
            )

            expiration_check_runs_total.labels(status="success").inc()
            return stats

        except Exception as e:
            logger.error(f"run_id={run_id} check failed", exc_info=True)
            expiration_check_runs_total.labels(status="failed").inc()
            raise

    def _create_expiration_alert(
        self,
        position,
        threshold: ExpirationThreshold,
        days_to_expiry: int,
        account_id: str,
    ):
        """Create an expiration alert for a position/threshold.

        Args:
            position: The option position
            threshold: The threshold being triggered
            days_to_expiry: Current DTE
            account_id: Account ID for the alert

        Returns:
            AlertEvent ready for persistence

        Raises:
            ValueError: If required position fields are missing
        """
        # Validate required fields
        if position.strike is None:
            raise ValueError(f"Position {position.id} missing strike price")
        if position.put_call is None:
            raise ValueError(f"Position {position.id} missing put_call type")

        # Build summary message
        if days_to_expiry == 0:
            summary = f"期权 {position.symbol} 今日收盘到期"
        elif days_to_expiry == 1:
            summary = f"期权 {position.symbol} 明日到期"
        else:
            summary = f"期权 {position.symbol} 将在 {days_to_expiry} 天后到期"

        # Build details (V1 minimal set)
        strike_value = (
            float(position.strike)
            if isinstance(position.strike, Decimal)
            else position.strike
        )

        details = {
            "threshold_days": threshold.days,
            "expiry_date": position.expiry.isoformat(),
            "days_to_expiry": days_to_expiry,
            "position_id": position.id,
            "strike": strike_value,
            "put_call": position.put_call.value,
            "quantity": position.quantity,
        }

        # Add contract_key if available
        if hasattr(position, "contract_key") and position.contract_key:
            details["contract_key"] = position.contract_key

        # Create alert (symbol preserved for display)
        return create_alert(
            type=AlertType.OPTION_EXPIRING,
            severity=threshold.severity,
            summary=summary,
            account_id=account_id,
            symbol=position.symbol,
            details=details,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/options/test_checker.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/options/checker.py backend/tests/options/test_checker.py
git commit -m "feat(options): implement ExpirationChecker with DTE calculation"
```

---

## Phase 4: Scheduler & API (Day 4-5)

> **Note:** Tasks 4.1-4.5 follow the same TDD pattern. See design doc for full implementation.

### Task 4.1: Create Idempotency Service

**Files:**
- Create: `backend/src/options/idempotency.py`
- Test: `backend/tests/options/test_idempotency.py`

### Task 4.2: Create Scheduler with Advisory Lock

**Files:**
- Create: `backend/src/options/scheduler.py`
- Test: `backend/tests/options/test_scheduler.py`

### Task 4.3: Create API Pydantic Models

**Files:**
- Create: `backend/src/options/models.py`
- Test: `backend/tests/options/test_models.py`

### Task 4.4: Create API Endpoints

**Files:**
- Create: `backend/src/api/options.py`
- Test: `backend/tests/api/test_options.py`

### Task 4.5: Register Router in main.py

**Files:**
- Modify: `backend/src/main.py`

---

## Phase 5: Frontend Implementation (Day 6-8)

> **Note:** Tasks 5.1-5.4 follow frontend patterns. See design doc for component specs.

### Task 5.1: Generate TypeScript Types

**Files:**
- Run: `cd frontend && ./scripts/generate-types.sh`

### Task 5.2: Create API Client

**Files:**
- Create: `frontend/src/api/options.ts`

### Task 5.3: Create OptionsExpiringPage

**Files:**
- Create: `frontend/src/pages/OptionsExpiringPage.tsx`
- Create: `frontend/src/components/options/ExpiringAlertsList.tsx`

### Task 5.4: Enhance AlertsPage

**Files:**
- Modify: `frontend/src/components/alerts/AlertRow.tsx`
- Modify: `frontend/src/App.tsx`

---

## Phase 6: Integration Testing (Day 9-10)

### Task 6.1: End-to-End Test

**Files:**
- Create: `backend/tests/integration/test_options_expiration_e2e.py`

### Task 6.2: Performance Test

**Files:**
- Create: `backend/tests/performance/test_expiration_performance.py`

---

## Commit Checklist

After each task, verify:
- [ ] Tests pass: `pytest tests/path/test_file.py -v`
- [ ] No regressions: `pytest tests/ -v`
- [ ] Linting: `ruff check src/`
- [ ] Types: `mypy src/`

## Definition of Done

- [ ] All 3 migrations applied successfully
- [ ] OPTION_EXPIRING alert type functional
- [ ] ExpirationChecker creates alerts correctly
- [ ] Scheduler runs on startup + daily
- [ ] API endpoints working with idempotency
- [ ] Frontend pages rendering correctly
- [ ] Deep link + highlight working
- [ ] E2E test passing
- [ ] Performance: 1000 positions < 10s
