"""Add derivative_contracts table.

Revision ID: 016_derivative_contracts
Revises: 015_greeks_snapshots
Create Date: 2026-02-01
"""

import sqlalchemy as sa
from alembic import op

revision = "016_derivative_contracts"
down_revision = "015_greeks_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create derivative_contracts table
    op.create_table(
        "derivative_contracts",
        sa.Column("symbol", sa.VARCHAR(50), primary_key=True),
        sa.Column("underlying", sa.VARCHAR(50), nullable=False),
        sa.Column("contract_type", sa.VARCHAR(20), nullable=False),
        sa.Column("expiry", sa.Date, nullable=False),
        sa.Column("strike", sa.Numeric(18, 4), nullable=True),
        sa.Column("put_call", sa.VARCHAR(10), nullable=True),
    )

    # Indexes for derivative_contracts
    op.create_index(
        "ix_derivative_contracts_underlying",
        "derivative_contracts",
        ["underlying"],
    )
    op.create_index(
        "ix_derivative_contracts_expiry",
        "derivative_contracts",
        ["expiry"],
    )
    op.create_index(
        "ix_derivative_contracts_underlying_expiry",
        "derivative_contracts",
        ["underlying", "expiry"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_derivative_contracts_underlying_expiry", table_name="derivative_contracts")
    op.drop_index("ix_derivative_contracts_expiry", table_name="derivative_contracts")
    op.drop_index("ix_derivative_contracts_underlying", table_name="derivative_contracts")
    # Drop table
    op.drop_table("derivative_contracts")
