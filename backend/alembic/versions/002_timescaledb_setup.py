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
