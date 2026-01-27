"""Create audit_logs hypertable and audit_chain_head table.

Revision ID: 005_audit_logs
Revises: 004_alerts
Create Date: 2026-01-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "005_audit_logs"
down_revision = "004_alerts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create sequence for audit log ordering
    op.execute("CREATE SEQUENCE audit_sequence START 1")

    # Create audit_chain_head table for chain integrity tracking
    op.create_table(
        "audit_chain_head",
        sa.Column("chain_key", sa.VARCHAR(100), primary_key=True),
        sa.Column("checksum", sa.VARCHAR(64), nullable=False),
        sa.Column("sequence_id", sa.BIGINT, nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Create audit_logs table
    # Note: TimescaleDB requires partitioning column in primary key
    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_id", sa.BIGINT, nullable=False),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", "timestamp"),
        sa.Column("event_type", sa.VARCHAR(50), nullable=False),
        sa.Column("severity", sa.VARCHAR(20), nullable=False),
        sa.Column("actor_id", sa.VARCHAR(100), nullable=False),
        sa.Column("actor_type", sa.VARCHAR(20), nullable=False),
        sa.Column("resource_type", sa.VARCHAR(50), nullable=False),
        sa.Column("resource_id", sa.VARCHAR(100), nullable=False),
        sa.Column("request_id", sa.VARCHAR(100), nullable=False),
        sa.Column("source", sa.VARCHAR(20), nullable=False),
        sa.Column("environment", sa.VARCHAR(20), nullable=False),
        sa.Column("service", sa.VARCHAR(50), nullable=False),
        sa.Column("version", sa.VARCHAR(20), nullable=False),
        sa.Column("correlation_id", sa.VARCHAR(100), nullable=True),
        sa.Column("session_id", sa.VARCHAR(100), nullable=True),
        sa.Column("parent_event_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "value_mode",
            sa.VARCHAR(20),
            nullable=False,
            server_default="diff",
        ),
        sa.Column("old_value", JSONB, nullable=True),
        sa.Column("new_value", JSONB, nullable=True),
        sa.Column("diff", JSONB, nullable=True),
        sa.Column("value_hash", sa.VARCHAR(64), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("checksum", sa.VARCHAR(64), nullable=False),
        sa.Column("prev_checksum", sa.VARCHAR(64), nullable=True),
        sa.Column("chain_key", sa.VARCHAR(100), nullable=False),
        # CHECK constraints for enum values
        sa.CheckConstraint(
            "event_type IN ('order_placed', 'order_acknowledged', 'order_filled', "
            "'order_cancelled', 'order_rejected', 'config_created', 'config_updated', "
            "'config_deleted', 'alert_emitted', 'alert_acknowledged', 'alert_resolved', "
            "'system_started', 'system_stopped', 'health_changed', 'auth_login', "
            "'auth_logout', 'auth_failed', 'permission_changed')",
            name="ck_audit_logs_event_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'critical')",
            name="ck_audit_logs_severity",
        ),
        sa.CheckConstraint(
            "actor_type IN ('user', 'system', 'api', 'scheduler')",
            name="ck_audit_logs_actor_type",
        ),
        sa.CheckConstraint(
            "resource_type IN ('order', 'position', 'config', 'alert', "
            "'strategy', 'account', 'permission', 'session')",
            name="ck_audit_logs_resource_type",
        ),
        sa.CheckConstraint(
            "source IN ('web', 'api', 'worker', 'scheduler', 'system', 'cli')",
            name="ck_audit_logs_source",
        ),
        sa.CheckConstraint(
            "value_mode IN ('diff', 'snapshot', 'reference')",
            name="ck_audit_logs_value_mode",
        ),
        # Size limits on JSONB fields (32KB for values, 8KB for metadata)
        sa.CheckConstraint(
            "old_value IS NULL OR octet_length(old_value::text) <= 32768",
            name="ck_audit_logs_old_value_size",
        ),
        sa.CheckConstraint(
            "new_value IS NULL OR octet_length(new_value::text) <= 32768",
            name="ck_audit_logs_new_value_size",
        ),
        sa.CheckConstraint(
            "diff IS NULL OR octet_length(diff::text) <= 32768",
            name="ck_audit_logs_diff_size",
        ),
        sa.CheckConstraint(
            "metadata IS NULL OR octet_length(metadata::text) <= 8192",
            name="ck_audit_logs_metadata_size",
        ),
    )

    # Convert audit_logs to TimescaleDB hypertable with 1-day chunks
    op.execute("""
        SELECT create_hypertable(
            'audit_logs',
            'timestamp',
            chunk_time_interval => INTERVAL '1 day',
            migrate_data => false
        )
    """)

    # Configure compression settings (compress after 7 days)
    op.execute("""
        ALTER TABLE audit_logs SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'chain_key,event_type',
            timescaledb.compress_orderby = 'timestamp DESC'
        )
    """)

    # Add compression policy to compress chunks older than 7 days
    op.execute("""
        SELECT add_compression_policy('audit_logs', INTERVAL '7 days')
    """)

    # Create indexes for common query patterns
    op.create_index(
        "idx_audit_resource",
        "audit_logs",
        ["resource_type", "resource_id", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_audit_actor",
        "audit_logs",
        ["actor_type", "actor_id", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_audit_event_type",
        "audit_logs",
        ["event_type", sa.text("timestamp DESC")],
    )
    op.create_index(
        "idx_audit_request",
        "audit_logs",
        ["request_id"],
    )
    op.create_index(
        "idx_audit_sequence",
        "audit_logs",
        [sa.text("sequence_id DESC")],
    )

    # Partial index for correlation_id (only when not null)
    op.execute("""
        CREATE INDEX idx_audit_correlation ON audit_logs (correlation_id)
        WHERE correlation_id IS NOT NULL
    """)

    # Role permissions for audit log protection
    # Wrap in try/except for environments without these roles
    op.execute("""
        DO $$
        BEGIN
            -- Revoke modification privileges to ensure tamper-proof logs
            REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC;

            -- Grant minimal required privileges
            GRANT INSERT, SELECT ON audit_logs TO PUBLIC;
            GRANT USAGE ON SEQUENCE audit_sequence TO PUBLIC;
        EXCEPTION
            WHEN undefined_object THEN
                -- Roles don't exist in this environment, skip
                NULL;
            WHEN insufficient_privilege THEN
                -- Not enough privileges to modify grants, skip
                NULL;
        END $$;
    """)


def downgrade() -> None:
    # Remove compression policy first
    op.execute("""
        SELECT remove_compression_policy('audit_logs', if_exists => true)
    """)

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS idx_audit_correlation")
    op.drop_index("idx_audit_sequence", table_name="audit_logs")
    op.drop_index("idx_audit_request", table_name="audit_logs")
    op.drop_index("idx_audit_event_type", table_name="audit_logs")
    op.drop_index("idx_audit_actor", table_name="audit_logs")
    op.drop_index("idx_audit_resource", table_name="audit_logs")

    # Drop tables
    op.drop_table("audit_logs")
    op.drop_table("audit_chain_head")

    # Drop sequence
    op.execute("DROP SEQUENCE IF EXISTS audit_sequence")
