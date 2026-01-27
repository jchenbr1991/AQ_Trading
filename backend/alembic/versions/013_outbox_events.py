"""Create outbox_events table.

Revision ID: 013_outbox_events
Revises: 012_close_requests
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "013_outbox_events"
down_revision = "012_close_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create outbox_events table
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.VARCHAR(50), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("status", sa.VARCHAR(20), nullable=False, server_default="pending"),
        # Generated column for unique constraint
        sa.Column(
            "close_request_id",
            sa.Text,
            sa.Computed("payload->>'close_request_id'"),
            nullable=True,
        ),
        # Timestamps
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # Retry tracking
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )

    # Unique index for idempotency (only when close_request_id is not null)
    op.create_index(
        "idx_outbox_idempotency",
        "outbox_events",
        ["event_type", "close_request_id"],
        unique=True,
        postgresql_where=sa.text("close_request_id IS NOT NULL"),
    )

    # Index for pending events (worker query)
    op.create_index(
        "idx_outbox_pending",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Index for cleanup job
    op.create_index(
        "idx_outbox_completed",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("status = 'completed'"),
    )


def downgrade() -> None:
    op.drop_index("idx_outbox_completed", table_name="outbox_events")
    op.drop_index("idx_outbox_pending", table_name="outbox_events")
    op.drop_index("idx_outbox_idempotency", table_name="outbox_events")
    op.drop_table("outbox_events")
