"""Create governance_audit_log table.

Revision ID: 018_governance_audit_log
Revises: 017_agent_results
Create Date: 2026-02-03
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "018_governance_audit_log"
down_revision = "017_agent_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create governance_audit_log table
    op.create_table(
        "governance_audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "timestamp",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("event_type", sa.VARCHAR(50), nullable=False),
        sa.Column("hypothesis_id", sa.VARCHAR(100), nullable=True),
        sa.Column("constraint_id", sa.VARCHAR(100), nullable=True),
        sa.Column("symbol", sa.VARCHAR(20), nullable=True),
        sa.Column("strategy_id", sa.VARCHAR(100), nullable=True),
        sa.Column("action_details", JSONB, nullable=False),
        sa.Column("trace_id", sa.VARCHAR(100), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Create indexes for common query patterns
    op.create_index(
        "idx_governance_audit_timestamp",
        "governance_audit_log",
        ["timestamp"],
    )
    op.create_index(
        "idx_governance_audit_symbol",
        "governance_audit_log",
        ["symbol"],
    )
    op.create_index(
        "idx_governance_audit_constraint",
        "governance_audit_log",
        ["constraint_id"],
    )
    op.create_index(
        "idx_governance_audit_event_type",
        "governance_audit_log",
        ["event_type"],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("idx_governance_audit_event_type", table_name="governance_audit_log")
    op.drop_index("idx_governance_audit_constraint", table_name="governance_audit_log")
    op.drop_index("idx_governance_audit_symbol", table_name="governance_audit_log")
    op.drop_index("idx_governance_audit_timestamp", table_name="governance_audit_log")
    # Drop table
    op.drop_table("governance_audit_log")
