"""Add idempotency_keys table for API request deduplication

Revision ID: 008
Revises: 007_alerts_dedupe_unique
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op

revision = "008_idempotency_keys"
down_revision = "007_alerts_dedupe_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(255), primary_key=True),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=False),
        sa.Column("response_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Index for cleanup job (delete expired keys)
    op.create_index(
        "idx_idempotency_expires",
        "idempotency_keys",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_idempotency_expires", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
