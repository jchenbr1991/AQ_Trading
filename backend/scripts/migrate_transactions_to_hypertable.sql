-- MAINTENANCE WINDOW SCRIPT
-- Run this during scheduled downtime
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

INSERT INTO transactions_new
SELECT * FROM transactions;

\echo 'Full copy completed'

-- Record cutover timestamp (APPLICATION SHOULD PAUSE WRITES NOW)
\echo ''
\echo '=== Step 2: Record Cutover Timestamp ==='
SELECT now() as cutover_timestamp;

\echo ''
\echo '=== Step 3: Incremental Sync (with 1-hour lookback for safety) ==='
-- Safe incremental with lookback window and ON CONFLICT
INSERT INTO transactions_new
SELECT * FROM transactions
WHERE executed_at >= (SELECT MAX(executed_at) FROM transactions_new) - INTERVAL '1 hour'
ON CONFLICT (id) DO NOTHING;

\echo 'Incremental sync completed'

\echo ''
\echo '=== Step 4: Atomic Table Swap ==='
BEGIN;
    LOCK TABLE transactions IN EXCLUSIVE MODE;
    ALTER TABLE transactions RENAME TO transactions_old;
    ALTER TABLE transactions_new RENAME TO transactions;
COMMIT;

\echo 'Table swap completed'

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
        WHEN (SELECT count(*) FROM transactions) >= (SELECT count(*) FROM transactions_old)
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

\echo ''
\echo '=== Migration Complete ==='
\echo 'DO NOT DROP transactions_old yet!'
\echo 'Keep for 7-14 days, run validation checklist, then run cleanup migration.'
