"""
Post-migration validation checklist for transactions hypertable.

Run this after migration, before dropping transactions_old.
All checks must PASS before proceeding to cleanup.

USAGE:
    python -m scripts.validate_hypertable_migration
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from src.db.database import engine as async_engine


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
            return CheckResult("Row Count", "PASS", f"Both tables have {new_count:,} rows")
        elif new_count > old_count:
            diff = new_count - old_count
            return CheckResult(
                "Row Count",
                "PASS",
                f"New: {new_count:,}, Old: {old_count:,} (new has {diff} more rows - expected if writes continued)",
            )
        else:
            diff = old_count - new_count
            return CheckResult(
                "Row Count",
                "FAIL",
                f"New: {new_count:,}, Old: {old_count:,}, Missing: {diff:,} rows",
            )


async def check_time_range() -> CheckResult:
    """Verify time ranges match."""
    async with async_engine.connect() as conn:
        new_range = (
            await conn.execute(
                text("""
            SELECT min(executed_at), max(executed_at) FROM transactions
        """)
            )
        ).fetchone()
        old_range = (
            await conn.execute(
                text("""
            SELECT min(executed_at), max(executed_at) FROM transactions_old
        """)
            )
        ).fetchone()

        # Allow new range to be equal or larger (if writes continued)
        if new_range[0] == old_range[0]:
            return CheckResult("Time Range", "PASS", f"Min: {new_range[0]}, Max: {new_range[1]}")
        else:
            return CheckResult(
                "Time Range", "FAIL", f"New min: {new_range[0]}, Old min: {old_range[0]}"
            )


async def check_is_hypertable() -> CheckResult:
    """Verify transactions is a hypertable."""
    async with async_engine.connect() as conn:
        result = (
            await conn.execute(
                text("""
            SELECT hypertable_name
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions'
        """)
            )
        ).fetchone()

        if result:
            return CheckResult("Is Hypertable", "PASS", "transactions is a hypertable")
        else:
            return CheckResult("Is Hypertable", "FAIL", "transactions is NOT a hypertable")


async def check_compression_policy() -> CheckResult:
    """Verify compression policy is active."""
    async with async_engine.connect() as conn:
        result = (
            await conn.execute(
                text("""
            SELECT schedule_interval
            FROM timescaledb_information.jobs
            WHERE hypertable_name = 'transactions'
            AND proc_name = 'policy_compression'
        """)
            )
        ).fetchone()

        if result:
            return CheckResult("Compression Policy", "PASS", f"Active with interval: {result[0]}")
        else:
            return CheckResult("Compression Policy", "FAIL", "No compression policy found")


async def check_chunk_info() -> CheckResult:
    """Verify chunks are created correctly."""
    async with async_engine.connect() as conn:
        result = (
            await conn.execute(
                text("""
            SELECT
                count(*) as chunk_count,
                min(range_start) as min_range,
                max(range_end) as max_range
            FROM timescaledb_information.chunks
            WHERE hypertable_name = 'transactions'
        """)
            )
        ).fetchone()

        if result and result[0] > 0:
            return CheckResult(
                "Chunk Info", "PASS", f"{result[0]} chunks, range: {result[1]} to {result[2]}"
            )
        else:
            return CheckResult("Chunk Info", "WARN", "No chunks found (table may be empty)")


async def check_indexes() -> CheckResult:
    """Verify indexes exist on hypertable."""
    async with async_engine.connect() as conn:
        result = (
            await conn.execute(
                text("""
            SELECT indexname
            FROM pg_indexes
            WHERE tablename = 'transactions'
        """)
            )
        ).fetchall()

        index_names = [r[0] for r in result]

        # Check for key indexes
        expected_patterns = ["account_id", "symbol", "executed_at"]
        found = []
        for pattern in expected_patterns:
            if any(pattern in name for name in index_names):
                found.append(pattern)

        if len(found) == len(expected_patterns):
            return CheckResult(
                "Indexes", "PASS", f"Found {len(index_names)} indexes including {', '.join(found)}"
            )
        else:
            missing = [p for p in expected_patterns if p not in found]
            return CheckResult("Indexes", "WARN", f"Missing indexes for: {missing}")


async def check_sample_data() -> CheckResult:
    """Verify sample data matches between tables."""
    async with async_engine.connect() as conn:
        # Get oldest 5 transaction IDs from old table
        old_ids = (
            await conn.execute(
                text("""
            SELECT id FROM transactions_old ORDER BY executed_at LIMIT 5
        """)
            )
        ).fetchall()

        if not old_ids:
            return CheckResult("Sample Data", "WARN", "No data to sample (table may be empty)")

        ids = [r[0] for r in old_ids]

        # Check they exist in new table
        new_count = (
            await conn.execute(
                text("""
            SELECT count(*) FROM transactions WHERE id = ANY(:ids)
        """),
                {"ids": ids},
            )
        ).scalar()

        if new_count == len(ids):
            return CheckResult(
                "Sample Data", "PASS", f"All {len(ids)} sampled rows found in new table"
            )
        else:
            return CheckResult(
                "Sample Data", "FAIL", f"Only {new_count}/{len(ids)} sampled rows found"
            )


async def check_query_performance() -> CheckResult:
    """Test a typical query uses hypertable optimization."""
    async with async_engine.connect() as conn:
        result = (
            await conn.execute(
                text("""
            EXPLAIN (FORMAT TEXT)
            SELECT * FROM transactions
            WHERE account_id = 'test_account'
            AND executed_at > now() - INTERVAL '7 days'
            LIMIT 100
        """)
            )
        ).fetchall()

        plan = "\n".join([r[0] for r in result])
        uses_chunks = "_hyper_" in plan or "Chunk" in plan

        if uses_chunks:
            return CheckResult("Query Performance", "PASS", "Query plan uses hypertable chunks")
        else:
            return CheckResult(
                "Query Performance",
                "WARN",
                "Query plan may not use chunk pruning (expected for small data)",
            )


async def run_validation():
    """Run all validation checks."""
    print("=" * 60)
    print("HYPERTABLE MIGRATION VALIDATION")
    print(f"Run at: {datetime.now()}")
    print("=" * 60)
    print()

    checks = [
        (
            "Data Integrity",
            [
                check_row_count,
                check_time_range,
                check_sample_data,
            ],
        ),
        (
            "Hypertable Setup",
            [
                check_is_hypertable,
                check_compression_policy,
                check_chunk_info,
            ],
        ),
        (
            "Performance",
            [
                check_indexes,
                check_query_performance,
            ],
        ),
    ]

    all_results = []

    for category, category_checks in checks:
        print(f"--- {category} ---")
        for check in category_checks:
            try:
                result = await check()
                all_results.append(result)

                status_icon = {"PASS": "[+]", "FAIL": "[X]", "WARN": "[!]"}[result.status]
                print(f"{status_icon} {result.name}: {result.status}")
                print(f"    {result.details}")
            except Exception as e:
                result = CheckResult(check.__name__, "ERROR", str(e))
                all_results.append(result)
                print(f"[X] {check.__name__}: ERROR")
                print(f"    {e}")
        print()

    # Summary
    passed = sum(1 for r in all_results if r.status == "PASS")
    failed = sum(1 for r in all_results if r.status in ("FAIL", "ERROR"))
    warned = sum(1 for r in all_results if r.status == "WARN")

    print("=" * 60)
    print(f"SUMMARY: {passed} passed, {warned} warnings, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print()
        print("ACTION REQUIRED: Fix failures before dropping transactions_old")
        print()
        print("ROLLBACK INSTRUCTIONS:")
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
