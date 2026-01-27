"""Add close request tracking fields to orders table.

Revision ID: 014_order_close_fields
Revises: 013_outbox_events
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "014_order_close_fields"
down_revision = "013_outbox_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add close_request_id to orders
    op.add_column(
        "orders",
        sa.Column(
            "close_request_id",
            UUID(as_uuid=True),
            sa.ForeignKey("close_requests.id"),
            nullable=True,
        ),
    )

    # Add broker update tracking
    op.add_column(
        "orders",
        sa.Column("broker_update_seq", sa.BigInteger, nullable=True),
    )

    op.add_column(
        "orders",
        sa.Column("last_broker_update_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Add reconciler retry tracking
    op.add_column(
        "orders",
        sa.Column("reconcile_not_found_count", sa.Integer, nullable=False, server_default="0"),
    )

    # Index for close_request queries
    op.create_index(
        "idx_orders_close_request",
        "orders",
        ["close_request_id"],
        postgresql_where=sa.text("close_request_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_orders_close_request", table_name="orders")
    op.drop_column("orders", "reconcile_not_found_count")
    op.drop_column("orders", "last_broker_update_at")
    op.drop_column("orders", "broker_update_seq")
    op.drop_column("orders", "close_request_id")
