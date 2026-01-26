"""Create mode_transitions and db_buffer_wal tables for graceful degradation.

Revision ID: 006_degradation
Revises: 005_audit_logs
Create Date: 2026-01-27
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "006_degradation"
down_revision = "005_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create mode_transitions table - history of mode transitions
    op.create_table(
        "mode_transitions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("from_mode", sa.VARCHAR(30), nullable=False),
        sa.Column("to_mode", sa.VARCHAR(30), nullable=False),
        sa.Column("reason_code", sa.VARCHAR(50), nullable=False),
        sa.Column("source", sa.VARCHAR(30), nullable=False),
        sa.Column("operator_id", sa.VARCHAR(100), nullable=True),
        sa.Column("override_ttl", sa.INTEGER, nullable=True),
        sa.Column("details", JSONB, nullable=True),
        # CHECK constraints for mode values
        sa.CheckConstraint(
            "from_mode IN ('normal', 'degraded', 'readonly', 'maintenance')",
            name="ck_mode_transitions_from_mode",
        ),
        sa.CheckConstraint(
            "to_mode IN ('normal', 'degraded', 'readonly', 'maintenance')",
            name="ck_mode_transitions_to_mode",
        ),
        sa.CheckConstraint(
            "source IN ('system', 'operator', 'scheduler', 'health_check', 'api')",
            name="ck_mode_transitions_source",
        ),
    )

    # Create indexes for mode_transitions
    op.create_index(
        "idx_mode_transitions_timestamp",
        "mode_transitions",
        [sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_mode_transitions_to_mode",
        "mode_transitions",
        ["to_mode", sa.text("timestamp DESC")],
    )

    # Create db_buffer_wal table - WAL entries for DB buffer
    op.create_table(
        "db_buffer_wal",
        sa.Column("id", sa.BIGINT, primary_key=True, autoincrement=True),
        sa.Column("idempotent_key", sa.VARCHAR(200), nullable=False, unique=True),
        sa.Column("resource_type", sa.VARCHAR(50), nullable=False),
        sa.Column("resource_id", sa.VARCHAR(100), nullable=False),
        sa.Column("old_state", JSONB, nullable=True),
        sa.Column("new_state", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("replayed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Create indexes for db_buffer_wal
    op.create_index(
        "idx_db_buffer_wal_created_at",
        "db_buffer_wal",
        [sa.text("created_at ASC")],
    )
    op.create_index(
        "idx_db_buffer_wal_resource",
        "db_buffer_wal",
        ["resource_type", "resource_id"],
    )

    # Partial index for unreplayed entries
    op.execute("""
        CREATE INDEX idx_db_buffer_wal_unreplayed ON db_buffer_wal (created_at ASC)
        WHERE replayed_at IS NULL
    """)


def downgrade() -> None:
    # Drop indexes for db_buffer_wal
    op.execute("DROP INDEX IF EXISTS idx_db_buffer_wal_unreplayed")
    op.drop_index("idx_db_buffer_wal_resource", table_name="db_buffer_wal")
    op.drop_index("idx_db_buffer_wal_created_at", table_name="db_buffer_wal")

    # Drop db_buffer_wal table
    op.drop_table("db_buffer_wal")

    # Drop indexes for mode_transitions
    op.drop_index("idx_mode_transitions_to_mode", table_name="mode_transitions")
    op.drop_index("idx_mode_transitions_timestamp", table_name="mode_transitions")

    # Drop mode_transitions table
    op.drop_table("mode_transitions")
