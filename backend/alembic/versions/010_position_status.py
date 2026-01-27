"""Add status column to positions table

Revision ID: 010_position_status
Revises: 009_options_expiration_indexes
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op

revision = "010_position_status"
down_revision = "009_options_expiration_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add status column with default 'open' for existing positions
    op.add_column(
        "positions",
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
    )

    # Add index for efficient status filtering
    op.create_index("idx_positions_status", "positions", ["status"])

    # Add composite index for common query pattern (account + status)
    op.create_index(
        "idx_positions_account_status",
        "positions",
        ["account_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_positions_account_status", table_name="positions")
    op.drop_index("idx_positions_status", table_name="positions")
    op.drop_column("positions", "status")
