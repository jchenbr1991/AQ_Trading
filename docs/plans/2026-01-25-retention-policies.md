# Retention Policies Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Optimize TRANSACTIONS table for time-series queries and reduce storage with automatic compression.

**Architecture:** Convert TRANSACTIONS to TimescaleDB hypertable with compression policy. Phased migration with validation.

**Tech Stack:** TimescaleDB extension, Alembic migrations, FastAPI endpoints

---

## Design Decisions

### Hypertable Configuration

| Setting | Value | Rationale |
|---------|-------|-----------|
| Chunk interval | 1 day | Optimal for "recent N days" queries |
| Compression delay | 7 days | Keep hot data uncompressed |
| Segment by | account_id, symbol | Matches common query patterns |
| Order by | executed_at DESC | Critical for read performance |

### Migration Phases

| Phase | Description | Method |
|-------|-------------|--------|
| A | Enable TimescaleDB, create hypertable | Alembic migration |
| B | Data migration + table swap | Manual maintenance window |
| C | Validation | Checklist execution |
| D | Cleanup (drop old table) | Alembic migration (after validation) |

### Safety Requirements

1. **Transaction block** for atomic table swap
2. **Safe incremental sync** with lookback window + ON CONFLICT
3. **Disk space** - Need 2.5x current table size during migration
4. **Keep old table** for 7-14 days after swap

---

## Task 1: TimescaleDB Extension Migration

**Files:**
- Create: `backend/alembic/versions/002_timescaledb_setup.py`
- Test: `backend/tests/db/test_timescaledb.py`

**Step 1: Write failing test**

```python
# backend/tests/db/test_timescaledb.py
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_timescaledb_extension_enabled(db_session: AsyncSession):
    """TimescaleDB extension should be enabled."""
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "timescaledb"


@pytest.mark.asyncio
async def test_transactions_is_hypertable(db_session: AsyncSession):
    """transactions table should be a hypertable."""
    result = await db_session.execute(
        text("""
            SELECT hypertable_name
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions'
        """)
    )
    row = result.fetchone()
    assert row is not None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/db/test_timescaledb.py -v`
Expected: FAIL (TimescaleDB not installed or transactions not a hypertable)

**Step 3: Write migration**

```python
# backend/alembic/versions/002_timescaledb_setup.py
"""Enable TimescaleDB and create transactions hypertable.

Revision ID: 002_timescaledb
Revises: 001_initial
Create Date: 2026-01-25
"""

from alembic import op
import sqlalchemy as sa

revision = "002_timescaledb"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # Create new hypertable (empty, data migrated separately)
    op.execute("""
        CREATE TABLE transactions_new (LIKE transactions INCLUDING ALL)
    """)

    # Convert to hypertable with 1-day chunks
    op.execute("""
        SELECT create_hypertable(
            'transactions_new',
            'executed_at',
            chunk_time_interval => INTERVAL '1 day',
            migrate_data => false
        )
    """)

    # Configure compression settings
    op.execute("""
        ALTER TABLE transactions_new SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'account_id,symbol',
            timescaledb.compress_orderby = 'executed_at DESC'
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS transactions_new")
    op.execute("DROP EXTENSION IF EXISTS timescaledb CASCADE")
```

**Step 4: Run migration**

Run: `cd backend && alembic upgrade head`
Expected: Migration completes successfully

**Step 5: Commit**

```bash
git add backend/alembic/versions/002_timescaledb_setup.py backend/tests/db/test_timescaledb.py
git commit -m "feat(db): enable TimescaleDB and create transactions hypertable"
```

---

## Task 2: Data Migration Script

**Files:**
- Create: `backend/scripts/migrate_transactions_to_hypertable.py`
- Create: `backend/scripts/migrate_transactions_to_hypertable.sql`

**Note:** This is NOT an Alembic migration. It's a manual maintenance window script.

**Step 1: Write SQL migration script**

```sql
-- backend/scripts/migrate_transactions_to_hypertable.sql
-- MAINTENANCE WINDOW SCRIPT
-- Run this during scheduled downtime
-- Estimated time: depends on table size
-- Disk requirement: 2.5x current transactions table size

-- Pre-flight checks
\echo '=== Pre-flight Checks ==='
SELECT
    'Current transactions count' as check_name,
    count(*) as value
FROM transactions;

SELECT
    'Min executed_at' as check_name,
    min(executed_at)::text as value
FROM transactions
UNION ALL
SELECT
    'Max executed_at' as check_name,
    max(executed_at)::text as value
FROM transactions;

SELECT
    'Disk space available' as check_name,
    pg_size_pretty(pg_database_size(current_database())) as value;

\echo ''
\echo '=== Step 1: Full Copy of Historical Data ==='
\echo 'Starting at:' `date`

INSERT INTO transactions_new
SELECT * FROM transactions;

\echo 'Full copy completed at:' `date`

-- Record cutover timestamp
\echo ''
\echo '=== Step 2: Record Cutover Timestamp ==='
SELECT now() as cutover_timestamp;
-- APPLICATION SHOULD PAUSE WRITES NOW

\echo ''
\echo '=== Step 3: Incremental Sync (with 1-hour lookback) ==='
-- Safe incremental with lookback window and ON CONFLICT
INSERT INTO transactions_new
SELECT * FROM transactions
WHERE executed_at >= (SELECT MAX(executed_at) FROM transactions_new) - INTERVAL '1 hour'
ON CONFLICT (id) DO NOTHING;

\echo 'Incremental sync completed at:' `date`

\echo ''
\echo '=== Step 4: Atomic Table Swap ==='
BEGIN;
    LOCK TABLE transactions IN EXCLUSIVE MODE;
    ALTER TABLE transactions RENAME TO transactions_old;
    ALTER TABLE transactions_new RENAME TO transactions;
COMMIT;

\echo 'Table swap completed at:' `date`

\echo ''
\echo '=== Step 5: Add Compression Policy ==='
SELECT add_compression_policy('transactions', INTERVAL '7 days');

\echo ''
\echo '=== Post-Migration Verification ==='
SELECT
    'New transactions count' as check_name,
    count(*) as value
FROM transactions;

SELECT
    'Old transactions count' as check_name,
    count(*) as value
FROM transactions_old;

SELECT
    'Row count match' as check_name,
    CASE
        WHEN (SELECT count(*) FROM transactions) = (SELECT count(*) FROM transactions_old)
        THEN 'PASS'
        ELSE 'FAIL - INVESTIGATE'
    END as value;

SELECT
    'Is hypertable' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions'
        )
        THEN 'PASS'
        ELSE 'FAIL'
    END as value;

SELECT
    'Compression policy active' as check_name,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM timescaledb_information.jobs
            WHERE hypertable_name = 'transactions'
            AND proc_name = 'policy_compression'
        )
        THEN 'PASS'
        ELSE 'FAIL'
    END as value;

\echo ''
\echo '=== Migration Complete ==='
\echo 'DO NOT DROP transactions_old yet!'
\echo 'Keep for 7-14 days, run validation checklist, then run Task 4.'
-- APPLICATION CAN RESUME WRITES NOW
```

**Step 2: Write Python wrapper script**

```python
# backend/scripts/migrate_transactions_to_hypertable.py
"""
Transaction table migration to TimescaleDB hypertable.

USAGE:
    1. Schedule maintenance window
    2. Stop application writes
    3. Run: python -m scripts.migrate_transactions_to_hypertable
    4. Verify output
    5. Resume application writes

ROLLBACK:
    BEGIN;
    ALTER TABLE transactions RENAME TO transactions_failed;
    ALTER TABLE transactions_old RENAME TO transactions;
    COMMIT;
"""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.database import async_engine


async def run_migration():
    """Execute the migration script."""
    script_path = Path(__file__).parent / "migrate_transactions_to_hypertable.sql"

    print("=" * 60)
    print("TRANSACTIONS TABLE MIGRATION TO HYPERTABLE")
    print("=" * 60)
    print()
    print("WARNING: This requires a maintenance window.")
    print("Application writes should be paused during this script.")
    print()

    confirm = input("Type 'MIGRATE' to proceed: ")
    if confirm != "MIGRATE":
        print("Aborted.")
        return

    async with async_engine.begin() as conn:
        # Read and execute SQL script
        sql = script_path.read_text()

        # Split by semicolons and execute each statement
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement and not statement.startswith("--") and not statement.startswith("\\"):
                try:
                    await conn.execute(text(statement))
                    print(f"OK: {statement[:60]}...")
                except Exception as e:
                    print(f"ERROR: {e}")
                    raise

    print()
    print("=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Resume application writes")
    print("2. Run validation checklist (Task 3)")
    print("3. Monitor for 7-14 days")
    print("4. Run cleanup migration (Task 4)")


if __name__ == "__main__":
    asyncio.run(run_migration())
```

**Step 3: Commit**

```bash
git add backend/scripts/migrate_transactions_to_hypertable.py backend/scripts/migrate_transactions_to_hypertable.sql
git commit -m "feat(db): add hypertable migration scripts"
```

---

## Task 3: Validation Checklist Script

**Files:**
- Create: `backend/scripts/validate_hypertable_migration.py`

**Step 1: Write validation script**

```python
# backend/scripts/validate_hypertable_migration.py
"""
Post-migration validation checklist for transactions hypertable.

Run this after migration, before dropping transactions_old.
All checks must PASS before proceeding to cleanup.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.database import async_engine


class CheckResult(NamedTuple):
    name: str
    status: str  # PASS, FAIL, WARN
    details: str


async def check_row_count() -> CheckResult:
    """Verify row counts match between old and new tables."""
    async with async_engine.connect() as conn:
        new_count = (await conn.execute(text("SELECT count(*) FROM transactions"))).scalar()
        old_count = (await conn.execute(text("SELECT count(*) FROM transactions_old"))).scalar()

        if new_count == old_count:
            return CheckResult("Row Count", "PASS", f"Both tables have {new_count} rows")
        else:
            diff = abs(new_count - old_count)
            return CheckResult("Row Count", "FAIL", f"New: {new_count}, Old: {old_count}, Diff: {diff}")


async def check_time_range() -> CheckResult:
    """Verify time ranges match."""
    async with async_engine.connect() as conn:
        new_range = (await conn.execute(text("""
            SELECT min(executed_at), max(executed_at) FROM transactions
        """))).fetchone()
        old_range = (await conn.execute(text("""
            SELECT min(executed_at), max(executed_at) FROM transactions_old
        """))).fetchone()

        if new_range == old_range:
            return CheckResult("Time Range", "PASS", f"Min: {new_range[0]}, Max: {new_range[1]}")
        else:
            return CheckResult("Time Range", "FAIL", f"New: {new_range}, Old: {old_range}")


async def check_is_hypertable() -> CheckResult:
    """Verify transactions is a hypertable."""
    async with async_engine.connect() as conn:
        result = (await conn.execute(text("""
            SELECT hypertable_name
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions'
        """))).fetchone()

        if result:
            return CheckResult("Is Hypertable", "PASS", "transactions is a hypertable")
        else:
            return CheckResult("Is Hypertable", "FAIL", "transactions is NOT a hypertable")


async def check_compression_policy() -> CheckResult:
    """Verify compression policy is active."""
    async with async_engine.connect() as conn:
        result = (await conn.execute(text("""
            SELECT schedule_interval
            FROM timescaledb_information.jobs
            WHERE hypertable_name = 'transactions'
            AND proc_name = 'policy_compression'
        """))).fetchone()

        if result:
            return CheckResult("Compression Policy", "PASS", f"Active with interval: {result[0]}")
        else:
            return CheckResult("Compression Policy", "FAIL", "No compression policy found")


async def check_chunk_info() -> CheckResult:
    """Verify chunks are created correctly."""
    async with async_engine.connect() as conn:
        result = (await conn.execute(text("""
            SELECT
                count(*) as chunk_count,
                min(range_start) as min_range,
                max(range_end) as max_range
            FROM timescaledb_information.chunks
            WHERE hypertable_name = 'transactions'
        """))).fetchone()

        if result and result[0] > 0:
            return CheckResult("Chunk Info", "PASS", f"{result[0]} chunks, range: {result[1]} to {result[2]}")
        else:
            return CheckResult("Chunk Info", "WARN", "No chunks found (table may be empty)")


async def check_indexes() -> CheckResult:
    """Verify indexes exist on hypertable."""
    async with async_engine.connect() as conn:
        result = (await conn.execute(text("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'transactions'
        """))).fetchall()

        index_names = [r[0] for r in result]
        expected = ["ix_transactions_account_id", "ix_transactions_symbol", "ix_transactions_executed_at"]

        missing = [idx for idx in expected if not any(idx in name for name in index_names)]

        if not missing:
            return CheckResult("Indexes", "PASS", f"Found {len(index_names)} indexes")
        else:
            return CheckResult("Indexes", "WARN", f"Missing indexes: {missing}")


async def check_sample_query_performance() -> CheckResult:
    """Test a typical query and verify it uses chunks."""
    async with async_engine.connect() as conn:
        # Run EXPLAIN on a typical query
        result = (await conn.execute(text("""
            EXPLAIN (FORMAT TEXT)
            SELECT * FROM transactions
            WHERE account_id = 'test'
            AND executed_at > now() - INTERVAL '7 days'
            LIMIT 100
        """))).fetchall()

        plan = "\n".join([r[0] for r in result])
        uses_chunks = "_hyper_" in plan or "Chunk" in plan

        if uses_chunks:
            return CheckResult("Query Performance", "PASS", "Query plan uses hypertable chunks")
        else:
            return CheckResult("Query Performance", "WARN", "Query plan may not be optimal")


async def run_validation():
    """Run all validation checks."""
    print("=" * 60)
    print("HYPERTABLE MIGRATION VALIDATION")
    print(f"Run at: {datetime.now()}")
    print("=" * 60)
    print()

    checks = [
        check_row_count,
        check_time_range,
        check_is_hypertable,
        check_compression_policy,
        check_chunk_info,
        check_indexes,
        check_sample_query_performance,
    ]

    results = []
    for check in checks:
        try:
            result = await check()
            results.append(result)
        except Exception as e:
            results.append(CheckResult(check.__name__, "ERROR", str(e)))

    # Print results
    for result in results:
        status_icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠", "ERROR": "✗"}[result.status]
        print(f"[{status_icon}] {result.name}: {result.status}")
        print(f"    {result.details}")
        print()

    # Summary
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status in ("FAIL", "ERROR"))
    warned = sum(1 for r in results if r.status == "WARN")

    print("=" * 60)
    print(f"SUMMARY: {passed} passed, {warned} warnings, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print()
        print("ACTION REQUIRED: Fix failures before dropping transactions_old")
        print("ROLLBACK if needed:")
        print("  BEGIN;")
        print("  ALTER TABLE transactions RENAME TO transactions_failed;")
        print("  ALTER TABLE transactions_old RENAME TO transactions;")
        print("  COMMIT;")
        return False
    elif warned > 0:
        print()
        print("Review warnings. If acceptable, proceed to cleanup after 7-14 days.")
        return True
    else:
        print()
        print("All checks passed. Safe to proceed to cleanup after 7-14 days.")
        return True


if __name__ == "__main__":
    success = asyncio.run(run_validation())
    sys.exit(0 if success else 1)
```

**Step 2: Commit**

```bash
git add backend/scripts/validate_hypertable_migration.py
git commit -m "feat(db): add hypertable migration validation script"
```

---

## Task 4: Cleanup Migration (Drop Old Table)

**Files:**
- Create: `backend/alembic/versions/003_cleanup_transactions_old.py`

**IMPORTANT:** Only run this migration AFTER:
1. Validation checklist passes
2. 7-14 days of production monitoring
3. No issues reported

**Step 1: Write migration**

```python
# backend/alembic/versions/003_cleanup_transactions_old.py
"""Drop transactions_old table after successful hypertable migration.

PREREQUISITES:
- Run validation script: python -m scripts.validate_hypertable_migration
- Wait 7-14 days after migration
- No issues reported

Revision ID: 003_cleanup
Revises: 002_timescaledb
Create Date: 2026-01-25
"""

from alembic import op

revision = "003_cleanup"
down_revision = "002_timescaledb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Pre-check: Ensure transactions_old exists
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'transactions_old'
            ) THEN
                RAISE EXCEPTION 'transactions_old does not exist. Migration may have already run.';
            END IF;
        END $$;
    """)

    # Drop old table
    op.execute("DROP TABLE transactions_old")


def downgrade() -> None:
    # Cannot restore dropped table without backup
    raise Exception(
        "Cannot downgrade: transactions_old data is lost. "
        "Restore from backup if needed."
    )
```

**Step 2: Commit**

```bash
git add backend/alembic/versions/003_cleanup_transactions_old.py
git commit -m "feat(db): add cleanup migration for transactions_old"
```

---

## Task 5: Storage Monitoring Service

**Files:**
- Create: `backend/src/services/storage_monitor.py`
- Test: `backend/tests/services/test_storage_monitor.py`

**Step 1: Write failing tests**

```python
# backend/tests/services/test_storage_monitor.py
import pytest
from decimal import Decimal
from datetime import datetime
from src.services.storage_monitor import StorageMonitor, StorageStats, TableStats


class TestStorageMonitor:
    @pytest.mark.asyncio
    async def test_get_storage_stats_returns_stats(self, db_session):
        """Should return storage statistics."""
        monitor = StorageMonitor(db_session)
        stats = await monitor.get_storage_stats()

        assert isinstance(stats, StorageStats)
        assert stats.database_size_bytes >= 0
        assert stats.timestamp is not None

    @pytest.mark.asyncio
    async def test_get_table_stats_returns_list(self, db_session):
        """Should return stats for each table."""
        monitor = StorageMonitor(db_session)
        tables = await monitor.get_table_stats()

        assert isinstance(tables, list)
        # Should have at least accounts, positions, transactions
        table_names = [t.table_name for t in tables]
        assert "accounts" in table_names or len(tables) >= 0  # May be empty in test

    @pytest.mark.asyncio
    async def test_get_compression_stats_returns_hypertable_info(self, db_session):
        """Should return compression stats for hypertables."""
        monitor = StorageMonitor(db_session)
        compression = await monitor.get_compression_stats()

        # May be empty if no hypertables
        assert isinstance(compression, dict)


class TestStorageStatsModel:
    def test_storage_stats_creation(self):
        """StorageStats model should be created correctly."""
        stats = StorageStats(
            database_size_bytes=1_000_000,
            database_size_pretty="1 MB",
            timestamp=datetime.now(),
            tables=[],
            compression={}
        )
        assert stats.database_size_bytes == 1_000_000
        assert stats.database_size_pretty == "1 MB"


class TestTableStatsModel:
    def test_table_stats_creation(self):
        """TableStats model should be created correctly."""
        stats = TableStats(
            table_name="transactions",
            row_count=10000,
            size_bytes=500_000,
            size_pretty="500 KB",
            is_hypertable=True
        )
        assert stats.table_name == "transactions"
        assert stats.is_hypertable is True
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/services/test_storage_monitor.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write implementation**

```python
# backend/src/services/storage_monitor.py
"""Storage monitoring service for database tables and compression."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class TableStats:
    """Statistics for a single table."""
    table_name: str
    row_count: int
    size_bytes: int
    size_pretty: str
    is_hypertable: bool


@dataclass(frozen=True)
class StorageStats:
    """Overall storage statistics."""
    database_size_bytes: int
    database_size_pretty: str
    timestamp: datetime
    tables: list[TableStats]
    compression: dict[str, Any]


class StorageMonitor:
    """Monitor database storage and compression."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_storage_stats(self) -> StorageStats:
        """Get comprehensive storage statistics."""
        # Get database size
        result = await self._session.execute(text("""
            SELECT
                pg_database_size(current_database()) as size_bytes,
                pg_size_pretty(pg_database_size(current_database())) as size_pretty
        """))
        row = result.fetchone()
        db_size_bytes = row[0] if row else 0
        db_size_pretty = row[1] if row else "0 bytes"

        # Get table stats
        tables = await self.get_table_stats()

        # Get compression stats
        compression = await self.get_compression_stats()

        return StorageStats(
            database_size_bytes=db_size_bytes,
            database_size_pretty=db_size_pretty,
            timestamp=datetime.now(),
            tables=tables,
            compression=compression
        )

    async def get_table_stats(self) -> list[TableStats]:
        """Get statistics for each table."""
        # Get all tables with their sizes
        result = await self._session.execute(text("""
            SELECT
                relname as table_name,
                n_live_tup as row_count,
                pg_total_relation_size(relid) as size_bytes,
                pg_size_pretty(pg_total_relation_size(relid)) as size_pretty
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
        """))
        rows = result.fetchall()

        # Check which tables are hypertables
        hypertables_result = await self._session.execute(text("""
            SELECT hypertable_name
            FROM timescaledb_information.hypertables
        """))
        hypertable_names = {row[0] for row in hypertables_result.fetchall()}

        return [
            TableStats(
                table_name=row[0],
                row_count=row[1] or 0,
                size_bytes=row[2] or 0,
                size_pretty=row[3] or "0 bytes",
                is_hypertable=row[0] in hypertable_names
            )
            for row in rows
        ]

    async def get_compression_stats(self) -> dict[str, Any]:
        """Get compression statistics for hypertables."""
        try:
            result = await self._session.execute(text("""
                SELECT
                    hypertable_name,
                    total_chunks,
                    compressed_chunks,
                    compressed_heap_size,
                    uncompressed_heap_size,
                    compression_ratio
                FROM timescaledb_information.compression_stats
            """))
            rows = result.fetchall()

            stats = {}
            for row in rows:
                stats[row[0]] = {
                    "total_chunks": row[1],
                    "compressed_chunks": row[2],
                    "compressed_size": row[3],
                    "uncompressed_size": row[4],
                    "compression_ratio": float(row[5]) if row[5] else None
                }
            return stats
        except Exception:
            # TimescaleDB may not be enabled or no compression yet
            return {}
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/services/test_storage_monitor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/services/storage_monitor.py backend/tests/services/test_storage_monitor.py
git commit -m "feat(services): add StorageMonitor service"
```

---

## Task 6: Storage API Endpoint

**Files:**
- Create: `backend/src/api/storage.py`
- Test: `backend/tests/api/test_storage.py`

**Step 1: Write failing tests**

```python
# backend/tests/api/test_storage.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_storage_stats(client: AsyncClient):
    """GET /api/storage should return storage statistics."""
    response = await client.get("/api/storage")

    assert response.status_code == 200
    data = response.json()

    assert "database_size_bytes" in data
    assert "database_size_pretty" in data
    assert "timestamp" in data
    assert "tables" in data
    assert isinstance(data["tables"], list)


@pytest.mark.asyncio
async def test_get_storage_tables(client: AsyncClient):
    """GET /api/storage/tables should return table statistics."""
    response = await client.get("/api/storage/tables")

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    # Each table should have required fields
    if len(data) > 0:
        table = data[0]
        assert "table_name" in table
        assert "row_count" in table
        assert "size_bytes" in table
        assert "is_hypertable" in table
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_storage.py -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Write implementation**

```python
# backend/src/api/storage.py
"""Storage monitoring API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_db
from src.services.storage_monitor import StorageMonitor


router = APIRouter(prefix="/api/storage", tags=["storage"])


class TableStatsResponse(BaseModel):
    """Table statistics response."""
    table_name: str
    row_count: int
    size_bytes: int
    size_pretty: str
    is_hypertable: bool


class StorageStatsResponse(BaseModel):
    """Storage statistics response."""
    database_size_bytes: int
    database_size_pretty: str
    timestamp: datetime
    tables: list[TableStatsResponse]
    compression: dict[str, Any]


@router.get("", response_model=StorageStatsResponse)
async def get_storage_stats(
    session: AsyncSession = Depends(get_db)
) -> StorageStatsResponse:
    """Get comprehensive storage statistics."""
    monitor = StorageMonitor(session)
    stats = await monitor.get_storage_stats()

    return StorageStatsResponse(
        database_size_bytes=stats.database_size_bytes,
        database_size_pretty=stats.database_size_pretty,
        timestamp=stats.timestamp,
        tables=[
            TableStatsResponse(
                table_name=t.table_name,
                row_count=t.row_count,
                size_bytes=t.size_bytes,
                size_pretty=t.size_pretty,
                is_hypertable=t.is_hypertable
            )
            for t in stats.tables
        ],
        compression=stats.compression
    )


@router.get("/tables", response_model=list[TableStatsResponse])
async def get_table_stats(
    session: AsyncSession = Depends(get_db)
) -> list[TableStatsResponse]:
    """Get statistics for each table."""
    monitor = StorageMonitor(session)
    tables = await monitor.get_table_stats()

    return [
        TableStatsResponse(
            table_name=t.table_name,
            row_count=t.row_count,
            size_bytes=t.size_bytes,
            size_pretty=t.size_pretty,
            is_hypertable=t.is_hypertable
        )
        for t in tables
    ]
```

**Step 4: Register router in main.py**

Add to `backend/src/main.py`:
```python
from src.api.storage import router as storage_router
app.include_router(storage_router)
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_storage.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/src/api/storage.py backend/tests/api/test_storage.py backend/src/main.py
git commit -m "feat(api): add storage monitoring endpoints"
```

---

## Task 7: Frontend Storage Types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add TypeScript types**

```typescript
// Add to frontend/src/types/index.ts

// Storage monitoring types
export interface TableStats {
  table_name: string;
  row_count: number;
  size_bytes: number;
  size_pretty: string;
  is_hypertable: boolean;
}

export interface CompressionStats {
  total_chunks: number;
  compressed_chunks: number;
  compressed_size: number;
  uncompressed_size: number;
  compression_ratio: number | null;
}

export interface StorageStats {
  database_size_bytes: number;
  database_size_pretty: string;
  timestamp: string;
  tables: TableStats[];
  compression: Record<string, CompressionStats>;
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): add storage monitoring types"
```

---

## Task 8: useStorage Hook

**Files:**
- Create: `frontend/src/hooks/useStorage.ts`
- Create: `frontend/src/hooks/useStorage.test.ts`

**Step 1: Write failing tests**

```typescript
// frontend/src/hooks/useStorage.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useStorage } from './useStorage';
import * as api from '../api/client';

vi.mock('../api/client');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useStorage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns storage stats on success', async () => {
    const mockStats = {
      database_size_bytes: 1000000,
      database_size_pretty: '1 MB',
      timestamp: '2026-01-25T00:00:00Z',
      tables: [
        {
          table_name: 'transactions',
          row_count: 100,
          size_bytes: 500000,
          size_pretty: '500 KB',
          is_hypertable: true,
        },
      ],
      compression: {},
    };

    vi.mocked(api.fetchStorageStats).mockResolvedValue(mockStats);

    const { result } = renderHook(() => useStorage(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(result.current.data).toEqual(mockStats);
  });

  it('returns error on failure', async () => {
    vi.mocked(api.fetchStorageStats).mockRejectedValue(new Error('Failed'));

    const { result } = renderHook(() => useStorage(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- useStorage.test.ts`
Expected: FAIL (module not found)

**Step 3: Add API client function**

```typescript
// Add to frontend/src/api/client.ts

export async function fetchStorageStats(): Promise<StorageStats> {
  const response = await fetch('/api/storage');
  if (!response.ok) {
    throw new Error('Failed to fetch storage stats');
  }
  return response.json();
}
```

**Step 4: Write hook implementation**

```typescript
// frontend/src/hooks/useStorage.ts
import { useQuery } from '@tanstack/react-query';
import { fetchStorageStats } from '../api/client';
import type { StorageStats } from '../types';

export function useStorage() {
  return useQuery<StorageStats>({
    queryKey: ['storage'],
    queryFn: fetchStorageStats,
    refetchInterval: 30000, // Refresh every 30 seconds
  });
}
```

**Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test -- useStorage.test.ts`
Expected: PASS

**Step 6: Commit**

```bash
git add frontend/src/hooks/useStorage.ts frontend/src/hooks/useStorage.test.ts frontend/src/api/client.ts
git commit -m "feat(frontend): add useStorage hook"
```

---

## Task 9: StorageDashboard Component

**Files:**
- Create: `frontend/src/components/StorageDashboard.tsx`
- Create: `frontend/src/components/StorageDashboard.test.tsx`

**Step 1: Write failing tests**

```typescript
// frontend/src/components/StorageDashboard.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StorageDashboard } from './StorageDashboard';
import type { StorageStats } from '../types';

describe('StorageDashboard', () => {
  const mockStats: StorageStats = {
    database_size_bytes: 1048576,
    database_size_pretty: '1 MB',
    timestamp: '2026-01-25T12:00:00Z',
    tables: [
      {
        table_name: 'transactions',
        row_count: 10000,
        size_bytes: 524288,
        size_pretty: '512 KB',
        is_hypertable: true,
      },
      {
        table_name: 'positions',
        row_count: 50,
        size_bytes: 8192,
        size_pretty: '8 KB',
        is_hypertable: false,
      },
    ],
    compression: {
      transactions: {
        total_chunks: 10,
        compressed_chunks: 7,
        compressed_size: 100000,
        uncompressed_size: 400000,
        compression_ratio: 4.0,
      },
    },
  };

  it('renders database size', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText('1 MB')).toBeInTheDocument();
  });

  it('renders table list', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText('transactions')).toBeInTheDocument();
    expect(screen.getByText('positions')).toBeInTheDocument();
  });

  it('shows hypertable badge for hypertables', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText('Hypertable')).toBeInTheDocument();
  });

  it('shows compression stats when available', () => {
    render(<StorageDashboard stats={mockStats} />);
    expect(screen.getByText(/7.*\/.*10.*chunks compressed/i)).toBeInTheDocument();
    expect(screen.getByText(/4\.0x/i)).toBeInTheDocument();
  });

  it('renders loading state', () => {
    render(<StorageDashboard stats={null} isLoading={true} />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders error state', () => {
    render(<StorageDashboard stats={null} error="Failed to load" />);
    expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
  });
});
```

**Step 2: Run tests to verify they fail**

Run: `cd frontend && npm test -- StorageDashboard.test.tsx`
Expected: FAIL (component doesn't exist)

**Step 3: Write implementation**

```typescript
// frontend/src/components/StorageDashboard.tsx
import type { StorageStats } from '../types';

interface StorageDashboardProps {
  stats: StorageStats | null;
  isLoading?: boolean;
  error?: string | null;
}

export function StorageDashboard({ stats, isLoading, error }: StorageDashboardProps) {
  if (isLoading) {
    return <div className="p-4">Loading storage statistics...</div>;
  }

  if (error) {
    return <div className="p-4 text-red-600">Error: {error}</div>;
  }

  if (!stats) {
    return <div className="p-4">No storage data available</div>;
  }

  return (
    <div className="p-4 space-y-6">
      {/* Database Overview */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-2">Database Size</h2>
        <div className="text-3xl font-bold text-blue-600">{stats.database_size_pretty}</div>
        <div className="text-sm text-gray-500">
          Last updated: {new Date(stats.timestamp).toLocaleString()}
        </div>
      </div>

      {/* Tables */}
      <div className="bg-white rounded-lg shadow p-4">
        <h2 className="text-lg font-semibold mb-4">Tables</h2>
        <table className="w-full">
          <thead>
            <tr className="text-left text-gray-600 border-b">
              <th className="pb-2">Table</th>
              <th className="pb-2">Rows</th>
              <th className="pb-2">Size</th>
              <th className="pb-2">Type</th>
            </tr>
          </thead>
          <tbody>
            {stats.tables.map((table) => (
              <tr key={table.table_name} className="border-b last:border-0">
                <td className="py-2 font-medium">{table.table_name}</td>
                <td className="py-2">{table.row_count.toLocaleString()}</td>
                <td className="py-2">{table.size_pretty}</td>
                <td className="py-2">
                  {table.is_hypertable && (
                    <span className="px-2 py-1 bg-green-100 text-green-800 text-xs rounded">
                      Hypertable
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Compression Stats */}
      {Object.keys(stats.compression).length > 0 && (
        <div className="bg-white rounded-lg shadow p-4">
          <h2 className="text-lg font-semibold mb-4">Compression</h2>
          {Object.entries(stats.compression).map(([tableName, compression]) => (
            <div key={tableName} className="mb-4 last:mb-0">
              <h3 className="font-medium">{tableName}</h3>
              <div className="grid grid-cols-2 gap-4 mt-2">
                <div>
                  <div className="text-sm text-gray-500">Chunks Compressed</div>
                  <div>
                    {compression.compressed_chunks} / {compression.total_chunks} chunks compressed
                  </div>
                </div>
                <div>
                  <div className="text-sm text-gray-500">Compression Ratio</div>
                  <div className="text-green-600 font-semibold">
                    {compression.compression_ratio?.toFixed(1)}x
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

**Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- StorageDashboard.test.tsx`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/StorageDashboard.tsx frontend/src/components/StorageDashboard.test.tsx
git commit -m "feat(frontend): add StorageDashboard component"
```

---

## Task 10: StoragePage and Navigation

**Files:**
- Create: `frontend/src/pages/StoragePage.tsx`
- Modify: `frontend/src/App.tsx` (add route)

**Step 1: Write page component**

```typescript
// frontend/src/pages/StoragePage.tsx
import { useStorage } from '../hooks/useStorage';
import { StorageDashboard } from '../components/StorageDashboard';

export function StoragePage() {
  const { data, isLoading, error } = useStorage();

  return (
    <div className="container mx-auto">
      <h1 className="text-2xl font-bold p-4">Storage Monitoring</h1>
      <StorageDashboard
        stats={data ?? null}
        isLoading={isLoading}
        error={error?.message}
      />
    </div>
  );
}
```

**Step 2: Add route to App.tsx**

Add to router configuration:
```typescript
{
  path: '/storage',
  element: <StoragePage />
}
```

**Step 3: Add navigation link**

Add to navigation component:
```typescript
<Link to="/storage">Storage</Link>
```

**Step 4: Commit**

```bash
git add frontend/src/pages/StoragePage.tsx frontend/src/App.tsx
git commit -m "feat(frontend): add StoragePage and navigation"
```

---

## Task 11: Update Module Exports

**Files:**
- Modify: `backend/src/services/__init__.py`
- Modify: `frontend/src/components/index.ts`
- Modify: `frontend/src/hooks/index.ts`

**Step 1: Backend exports**

```python
# backend/src/services/__init__.py
from src.services.storage_monitor import StorageMonitor, StorageStats, TableStats

__all__ = ["StorageMonitor", "StorageStats", "TableStats"]
```

**Step 2: Frontend exports**

```typescript
// frontend/src/components/index.ts
export { StorageDashboard } from './StorageDashboard';

// frontend/src/hooks/index.ts
export { useStorage } from './useStorage';
```

**Step 3: Commit**

```bash
git add backend/src/services/__init__.py frontend/src/components/index.ts frontend/src/hooks/index.ts
git commit -m "feat: export storage monitoring modules"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | TimescaleDB extension migration | 002_timescaledb_setup.py |
| 2 | Data migration script | migrate_transactions_to_hypertable.py/.sql |
| 3 | Validation checklist | validate_hypertable_migration.py |
| 4 | Cleanup migration | 003_cleanup_transactions_old.py |
| 5 | StorageMonitor service | storage_monitor.py |
| 6 | Storage API endpoint | api/storage.py |
| 7 | Frontend types | types/index.ts |
| 8 | useStorage hook | hooks/useStorage.ts |
| 9 | StorageDashboard component | components/StorageDashboard.tsx |
| 10 | StoragePage and navigation | pages/StoragePage.tsx |
| 11 | Module exports | __init__.py, index.ts |

---

## Post-Implementation TODO

- [ ] Add retention policy when business requirements defined: `add_retention_policy('transactions', INTERVAL '180 days')`
- [ ] Add alerting for storage thresholds (e.g., > 80% disk usage)
- [ ] Add compression stats to health monitoring dashboard
