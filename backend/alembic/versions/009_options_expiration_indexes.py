"""Add performance indexes for options expiration queries

Revision ID: 009
Revises: 008_idempotency_keys
Create Date: 2026-01-27
"""

from alembic import op

revision = "009_options_expiration_indexes"
down_revision = "008_idempotency_keys"
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
