"""Create close_requests table.

Revision ID: 012_close_requests
Revises: 011_orders_table
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "012_close_requests"
down_revision = "011_orders_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create close_requests table
    op.create_table(
        "close_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "position_id",
            sa.Integer,
            sa.ForeignKey("positions.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("idempotency_key", sa.VARCHAR(100), nullable=False),
        sa.Column("status", sa.VARCHAR(20), nullable=False, server_default="pending"),
        # Order parameters
        sa.Column("symbol", sa.VARCHAR(50), nullable=False),
        sa.Column("side", sa.VARCHAR(10), nullable=False),
        sa.Column("asset_type", sa.VARCHAR(20), nullable=False),
        # Quantities
        sa.Column("target_qty", sa.Integer, nullable=False),
        sa.Column("filled_qty", sa.Integer, nullable=False, server_default="0"),
        # PostgreSQL generated column for remaining_qty
        sa.Column(
            "remaining_qty",
            sa.Integer,
            sa.Computed("target_qty - filled_qty"),
            nullable=False,
        ),
        # Retry tracking
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer, nullable=False, server_default="3"),
        # Timestamps
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Unique constraint for idempotency
    op.create_unique_constraint(
        "uq_close_requests_position_idempotency",
        "close_requests",
        ["position_id", "idempotency_key"],
    )

    # Index for status queries
    op.create_index(
        "idx_close_requests_status",
        "close_requests",
        ["status"],
        postgresql_where=sa.text("status IN ('pending', 'submitted')"),
    )

    # Add active_close_request_id to positions
    op.add_column(
        "positions",
        sa.Column(
            "active_close_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("close_requests.id"),
            nullable=True,
        ),
    )

    # Add closed_at to positions
    op.add_column(
        "positions",
        sa.Column("closed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("positions", "closed_at")
    op.drop_column("positions", "active_close_request_id")
    op.drop_index("idx_close_requests_status", table_name="close_requests")
    op.drop_constraint("uq_close_requests_position_idempotency", "close_requests", type_="unique")
    op.drop_table("close_requests")
