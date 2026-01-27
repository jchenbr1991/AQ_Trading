"""Create orders table for order persistence

Revision ID: 011_orders_table
Revises: 010_position_status
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op

revision = "011_orders_table"
down_revision = "010_position_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(50), nullable=False, unique=True, index=True),
        sa.Column("broker_order_id", sa.String(50), nullable=True, index=True),
        sa.Column(
            "account_id",
            sa.String(50),
            sa.ForeignKey("accounts.account_id"),
            nullable=False,
            index=True,
        ),
        sa.Column("strategy_id", sa.String(50), nullable=False, index=True),
        sa.Column("symbol", sa.String(50), nullable=False, index=True),
        sa.Column("side", sa.String(10), nullable=False),  # buy, sell
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("order_type", sa.String(20), nullable=False),  # market, limit
        sa.Column("limit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, index=True),
        sa.Column("filled_qty", sa.Integer(), nullable=False, default=0),
        sa.Column("avg_fill_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # Composite indexes for common query patterns
    op.create_index(
        "idx_orders_account_status",
        "orders",
        ["account_id", "status"],
    )
    op.create_index(
        "idx_orders_strategy_created",
        "orders",
        ["strategy_id", "created_at"],
    )
    op.create_index(
        "idx_orders_symbol_created",
        "orders",
        ["symbol", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_orders_symbol_created", table_name="orders")
    op.drop_index("idx_orders_strategy_created", table_name="orders")
    op.drop_index("idx_orders_account_status", table_name="orders")
    op.drop_table("orders")
