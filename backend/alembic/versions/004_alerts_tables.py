"""Create alerts and alert_deliveries tables.

Revision ID: 004_alerts
Revises: 003_cleanup
Create Date: 2026-01-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "004_alerts"
down_revision = "003_cleanup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create alerts table
    op.create_table(
        "alerts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.VARCHAR(50), nullable=False),
        sa.Column("severity", sa.INTEGER, nullable=False),
        sa.Column("fingerprint", sa.VARCHAR(255), nullable=False),
        sa.Column("dedupe_key", sa.VARCHAR(300), nullable=False, unique=True),
        sa.Column("summary", sa.VARCHAR(255), nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("entity_account_id", sa.VARCHAR(50), nullable=True),
        sa.Column("entity_symbol", sa.VARCHAR(20), nullable=True),
        sa.Column("entity_strategy_id", sa.VARCHAR(50), nullable=True),
        sa.Column("suppressed_count", sa.INTEGER, nullable=False, server_default="0"),
        sa.Column("event_timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "octet_length(details::text) <= 8192",
            name="ck_alerts_details_size",
        ),
        sa.CheckConstraint(
            "suppressed_count >= 0",
            name="ck_alerts_suppressed_count_non_negative",
        ),
    )

    # Create indexes for alerts table
    op.create_index(
        "idx_alerts_fingerprint",
        "alerts",
        ["fingerprint", sa.text("event_timestamp DESC")],
    )
    op.create_index(
        "idx_alerts_severity",
        "alerts",
        ["severity", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_alerts_type",
        "alerts",
        ["type", sa.text("created_at DESC")],
    )

    # Create alert_deliveries table
    op.create_table(
        "alert_deliveries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "alert_id",
            UUID(as_uuid=True),
            sa.ForeignKey("alerts.id"),
            nullable=False,
        ),
        sa.Column("channel", sa.VARCHAR(20), nullable=False),
        sa.Column("destination_key", sa.VARCHAR(100), nullable=False),
        sa.Column("attempt_number", sa.INTEGER, nullable=False),
        sa.Column("status", sa.VARCHAR(20), nullable=False),
        sa.Column("response_code", sa.INTEGER, nullable=True),
        sa.Column("error_message", sa.TEXT, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "alert_id",
            "destination_key",
            "attempt_number",
            name="uq_deliveries_alert_dest_attempt",
        ),
    )

    # Create indexes for alert_deliveries table
    op.create_index(
        "idx_deliveries_alert",
        "alert_deliveries",
        ["alert_id"],
    )
    op.create_index(
        "idx_deliveries_status",
        "alert_deliveries",
        ["status", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    # Drop alert_deliveries first (has FK to alerts)
    op.drop_index("idx_deliveries_status", table_name="alert_deliveries")
    op.drop_index("idx_deliveries_alert", table_name="alert_deliveries")
    op.drop_table("alert_deliveries")

    # Drop alerts table
    op.drop_index("idx_alerts_type", table_name="alerts")
    op.drop_index("idx_alerts_severity", table_name="alerts")
    op.drop_index("idx_alerts_fingerprint", table_name="alerts")
    op.drop_table("alerts")
