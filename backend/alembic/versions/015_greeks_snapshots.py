"""Create greeks_snapshots and greeks_alerts tables.

Revision ID: 015_greeks_snapshots
Revises: 014_order_close_fields
Create Date: 2026-01-28
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "015_greeks_snapshots"
down_revision = "014_order_close_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create greeks_snapshots table
    op.create_table(
        "greeks_snapshots",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("scope", sa.VARCHAR(20), nullable=False),  # 'ACCOUNT' or 'STRATEGY'
        sa.Column("scope_id", sa.VARCHAR(50), nullable=False),
        sa.Column("strategy_id", sa.VARCHAR(50), nullable=True),  # NULL for ACCOUNT scope
        # Dollar Greeks
        sa.Column(
            "dollar_delta",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "gamma_dollar",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "gamma_pnl_1pct",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "vega_per_1pct",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "theta_per_day",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        # Coverage
        sa.Column(
            "valid_legs_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_legs_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "valid_notional",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_notional",
            sa.Numeric(18, 4),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "coverage_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="100.0",
        ),
        sa.Column(
            "has_high_risk_missing_legs",
            sa.Boolean,
            nullable=False,
            server_default="false",
        ),
        # Timestamps
        sa.Column("as_of_ts", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    # Indexes for greeks_snapshots
    op.create_index(
        "ix_greeks_snapshots_scope_scope_id",
        "greeks_snapshots",
        ["scope", "scope_id"],
    )
    op.create_index(
        "ix_greeks_snapshots_as_of_ts",
        "greeks_snapshots",
        [sa.text("as_of_ts DESC")],
    )
    op.create_index(
        "ix_greeks_snapshots_scope_as_of",
        "greeks_snapshots",
        ["scope", "scope_id", sa.text("as_of_ts DESC")],
    )

    # Create greeks_alerts table
    op.create_table(
        "greeks_alerts",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("alert_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("alert_type", sa.VARCHAR(20), nullable=False),  # 'THRESHOLD' or 'ROC'
        sa.Column("scope", sa.VARCHAR(20), nullable=False),
        sa.Column("scope_id", sa.VARCHAR(50), nullable=False),
        sa.Column("metric", sa.VARCHAR(30), nullable=False),  # RiskMetric value
        sa.Column("level", sa.VARCHAR(10), nullable=False),  # GreeksLevel value
        # Alert values
        sa.Column("current_value", sa.Numeric(18, 4), nullable=False),
        sa.Column("threshold_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("prev_value", sa.Numeric(18, 4), nullable=True),
        sa.Column("change_pct", sa.Numeric(8, 4), nullable=True),
        # Message
        sa.Column("message", sa.Text, nullable=False),
        # Timestamps
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("acknowledged_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("acknowledged_by", sa.VARCHAR(100), nullable=True),
    )

    # Indexes for greeks_alerts
    op.create_index(
        "ix_greeks_alerts_scope",
        "greeks_alerts",
        ["scope", "scope_id"],
    )
    op.create_index(
        "ix_greeks_alerts_created_at",
        "greeks_alerts",
        [sa.text("created_at DESC")],
    )
    op.create_index(
        "ix_greeks_alerts_level",
        "greeks_alerts",
        ["level"],
    )


def downgrade() -> None:
    # Drop greeks_alerts indexes and table
    op.drop_index("ix_greeks_alerts_level", table_name="greeks_alerts")
    op.drop_index("ix_greeks_alerts_created_at", table_name="greeks_alerts")
    op.drop_index("ix_greeks_alerts_scope", table_name="greeks_alerts")
    op.drop_table("greeks_alerts")

    # Drop greeks_snapshots indexes and table
    op.drop_index("ix_greeks_snapshots_scope_as_of", table_name="greeks_snapshots")
    op.drop_index("ix_greeks_snapshots_as_of_ts", table_name="greeks_snapshots")
    op.drop_index("ix_greeks_snapshots_scope_scope_id", table_name="greeks_snapshots")
    op.drop_table("greeks_snapshots")
