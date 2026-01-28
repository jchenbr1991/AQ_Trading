# backend/src/models/greeks.py
"""SQLAlchemy models for Greeks snapshots and alerts."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class GreeksSnapshot(Base):
    """Persisted snapshot of aggregated Greeks at a point in time.

    Stores dollar Greeks and coverage metrics for either account-level
    or strategy-level aggregations.
    """

    __tablename__ = "greeks_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Scope identification
    scope: Mapped[str] = mapped_column(String(20), nullable=False)  # 'ACCOUNT' or 'STRATEGY'
    scope_id: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Dollar Greeks
    dollar_delta: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    gamma_dollar: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    gamma_pnl_1pct: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    vega_per_1pct: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    theta_per_day: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Coverage metrics
    valid_legs_count: Mapped[int] = mapped_column(Integer, default=0)
    total_legs_count: Mapped[int] = mapped_column(Integer, default=0)
    valid_notional: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_notional: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    coverage_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("100.0"))
    has_high_risk_missing_legs: Mapped[bool] = mapped_column(Boolean, default=False)

    # Timestamps
    as_of_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class GreeksAlertRecord(Base):
    """Persisted record of a Greeks-related alert.

    Stores threshold and rate-of-change alerts with acknowledgment tracking.
    """

    __tablename__ = "greeks_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), unique=True, nullable=False)

    # Alert classification
    alert_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'THRESHOLD' or 'ROC'
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(50), nullable=False)
    metric: Mapped[str] = mapped_column(String(30), nullable=False)  # RiskMetric value
    level: Mapped[str] = mapped_column(String(10), nullable=False)  # GreeksLevel value

    # Alert values
    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    threshold_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    prev_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)

    # Message
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    @property
    def is_acknowledged(self) -> bool:
        """Check if the alert has been acknowledged."""
        return self.acknowledged_at is not None
