"""Add agent_results table.

Revision ID: 017_agent_results
Revises: 016_derivative_contracts
Create Date: 2026-02-01
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSON, UUID

revision = "017_agent_results"
down_revision = "016_derivative_contracts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create agent_results table
    op.create_table(
        "agent_results",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("role", sa.VARCHAR(30), nullable=False),
        sa.Column("task", sa.VARCHAR(500), nullable=False),
        sa.Column("context", JSON, nullable=False),
        sa.Column("result", JSON, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )

    # Indexes for agent_results
    op.create_index(
        "ix_agent_results_role",
        "agent_results",
        ["role"],
    )
    op.create_index(
        "ix_agent_results_started_at",
        "agent_results",
        [sa.text("started_at DESC")],
    )
    op.create_index(
        "ix_agent_results_role_started_at",
        "agent_results",
        ["role", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_agent_results_role_started_at", table_name="agent_results")
    op.drop_index("ix_agent_results_started_at", table_name="agent_results")
    op.drop_index("ix_agent_results_role", table_name="agent_results")
    # Drop table
    op.drop_table("agent_results")
