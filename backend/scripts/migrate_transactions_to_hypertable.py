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
from src.db.database import engine as async_engine


async def run_migration():
    """Execute the migration script."""
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
        return False

    async with async_engine.begin() as conn:
        # Pre-flight: Check transactions count
        print("\n=== Pre-flight Checks ===")
        result = await conn.execute(text("SELECT count(*) FROM transactions"))
        count = result.scalar()
        print(f"Current transactions count: {count}")

        result = await conn.execute(
            text("""
            SELECT min(executed_at), max(executed_at) FROM transactions
        """)
        )
        row = result.fetchone()
        print(f"Time range: {row[0]} to {row[1]}")

        # Step 1: Full copy
        print("\n=== Step 1: Full Copy ===")
        await conn.execute(
            text("""
            INSERT INTO transactions_new SELECT * FROM transactions
        """)
        )
        print("Full copy completed")

        # Step 2: Cutover timestamp
        print("\n=== Step 2: Cutover Timestamp ===")
        result = await conn.execute(text("SELECT now()"))
        cutover = result.scalar()
        print(f"Cutover timestamp: {cutover}")
        print("APPLICATION SHOULD PAUSE WRITES NOW")

        # Step 3: Incremental sync with lookback
        print("\n=== Step 3: Incremental Sync ===")
        await conn.execute(
            text("""
            INSERT INTO transactions_new
            SELECT * FROM transactions
            WHERE executed_at >= (SELECT MAX(executed_at) FROM transactions_new) - INTERVAL '1 hour'
            ON CONFLICT (id) DO NOTHING
        """)
        )
        print("Incremental sync completed")

        # Step 4: Atomic swap in transaction
        print("\n=== Step 4: Atomic Table Swap ===")
        await conn.execute(text("LOCK TABLE transactions IN EXCLUSIVE MODE"))
        await conn.execute(text("ALTER TABLE transactions RENAME TO transactions_old"))
        await conn.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
        print("Table swap completed")

        # Step 5: Add compression policy
        print("\n=== Step 5: Add Compression Policy ===")
        await conn.execute(text("SELECT add_compression_policy('transactions', INTERVAL '7 days')"))
        print("Compression policy added")

        # Post-migration verification
        print("\n=== Post-Migration Verification ===")
        result = await conn.execute(text("SELECT count(*) FROM transactions"))
        new_count = result.scalar()
        result = await conn.execute(text("SELECT count(*) FROM transactions_old"))
        old_count = result.scalar()

        print(f"New transactions count: {new_count}")
        print(f"Old transactions count: {old_count}")

        if new_count >= old_count:
            print("Row count: PASS")
        else:
            print("Row count: FAIL - INVESTIGATE")
            return False

        result = await conn.execute(
            text("""
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables
                WHERE hypertable_name = 'transactions'
            )
        """)
        )
        is_hypertable = result.scalar()
        print(f"Is hypertable: {'PASS' if is_hypertable else 'FAIL'}")

    print("\n" + "=" * 60)
    print("MIGRATION COMPLETE")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Resume application writes")
    print("2. Run validation checklist (Task 3)")
    print("3. Monitor for 7-14 days")
    print("4. Run cleanup migration (Task 4)")
    return True


if __name__ == "__main__":
    success = asyncio.run(run_migration())
    sys.exit(0 if success else 1)
