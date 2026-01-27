"""Enable TimescaleDB and create transactions hypertable.

Revision ID: 002_timescaledb
Revises: 001
Create Date: 2026-01-25
"""

from alembic import op

revision = "002_timescaledb"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable TimescaleDB extension
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # Create transactions_new table with composite primary key including executed_at
    # TimescaleDB requires the partitioning column to be part of any unique constraint
    op.execute("""
        CREATE TABLE transactions_new (
            id SERIAL,
            account_id VARCHAR(50) NOT NULL,
            symbol VARCHAR(50) NOT NULL,
            action VARCHAR(20) NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            price NUMERIC(18, 4) NOT NULL DEFAULT 0,
            commission NUMERIC(18, 4) NOT NULL DEFAULT 0,
            realized_pnl NUMERIC(18, 4) NOT NULL DEFAULT 0,
            strategy_id VARCHAR(50),
            order_id VARCHAR(50),
            broker_order_id VARCHAR(50),
            executed_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, executed_at),
            FOREIGN KEY (account_id) REFERENCES accounts(account_id)
        )
    """)

    # Create indexes
    op.execute("CREATE INDEX idx_transactions_new_account_id ON transactions_new(account_id)")
    op.execute("CREATE INDEX idx_transactions_new_symbol ON transactions_new(symbol)")
    op.execute("CREATE INDEX idx_transactions_new_strategy_id ON transactions_new(strategy_id)")
    op.execute("CREATE INDEX idx_transactions_new_order_id ON transactions_new(order_id)")

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
