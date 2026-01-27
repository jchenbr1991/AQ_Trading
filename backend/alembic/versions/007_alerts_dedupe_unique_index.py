"""Add unique index on alerts(type, dedupe_key)

Revision ID: 007_alerts_dedupe_unique
Revises: 006_degradation
Create Date: 2026-01-27
"""

from alembic import op

revision = "007_alerts_dedupe_unique"
down_revision = "006_degradation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First drop the existing unique constraint on dedupe_key alone
    # (from 004_alerts_tables.py line 26: dedupe_key was created with unique=True)
    op.drop_constraint("alerts_dedupe_key_key", "alerts", type_="unique")

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
    # Restore the original unique constraint on dedupe_key alone
    op.create_unique_constraint("alerts_dedupe_key_key", "alerts", ["dedupe_key"])
