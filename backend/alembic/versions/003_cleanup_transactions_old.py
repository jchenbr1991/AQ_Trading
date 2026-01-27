"""Drop transactions_old table after successful hypertable migration.

PREREQUISITES (check before running):
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
    # Drop old table if it exists (may not exist in fresh installs)
    op.execute("DROP TABLE IF EXISTS transactions_old")


def downgrade() -> None:
    # Cannot restore dropped table without backup
    raise Exception(
        "Cannot downgrade: transactions_old data is lost. " "Restore from backup if needed."
    )
