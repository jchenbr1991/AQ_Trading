"""Greeks Repository for persisting and retrieving Greeks data.

This module provides the GreeksRepository class for database operations
related to Greeks snapshots and alerts.

Classes:
    - GreeksRepository: Repository for persisting and retrieving Greeks data
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.greeks.alerts import GreeksAlert
from src.greeks.models import AggregatedGreeks
from src.models.greeks import GreeksAlertRecord, GreeksSnapshot


class GreeksRepository:
    """Repository for persisting and retrieving Greeks data.

    Provides methods to:
    - Save Greeks snapshots to the database
    - Retrieve latest and historical snapshots
    - Save and manage alerts

    Attributes:
        _session: SQLAlchemy async session for database operations
    """

    def __init__(self, session: AsyncSession):
        """Initialize the repository with a database session.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self._session = session

    async def save_snapshot(self, greeks: AggregatedGreeks) -> GreeksSnapshot:
        """Persist an AggregatedGreeks snapshot to the database.

        Args:
            greeks: The AggregatedGreeks dataclass to persist

        Returns:
            The created GreeksSnapshot database record
        """
        # Calculate coverage percentage
        coverage_pct = greeks.coverage_pct

        snapshot = GreeksSnapshot(
            scope=greeks.scope,
            scope_id=greeks.scope_id,
            strategy_id=greeks.strategy_id,
            dollar_delta=greeks.dollar_delta,
            gamma_dollar=greeks.gamma_dollar,
            gamma_pnl_1pct=greeks.gamma_pnl_1pct,
            vega_per_1pct=greeks.vega_per_1pct,
            theta_per_day=greeks.theta_per_day,
            valid_legs_count=greeks.valid_legs_count,
            total_legs_count=greeks.total_legs_count,
            valid_notional=greeks.valid_notional,
            total_notional=greeks.total_notional,
            coverage_pct=coverage_pct,
            has_high_risk_missing_legs=greeks.has_high_risk_missing_legs,
            as_of_ts=greeks.as_of_ts,
        )

        self._session.add(snapshot)
        await self._session.commit()
        await self._session.refresh(snapshot)

        return snapshot

    async def get_latest_snapshot(self, scope: str, scope_id: str) -> AggregatedGreeks | None:
        """Get the most recent snapshot for a scope.

        Used for ROC detection - returns prev_greeks from persistent storage.

        Args:
            scope: The scope type ("ACCOUNT" or "STRATEGY")
            scope_id: The scope identifier (account ID or strategy ID)

        Returns:
            AggregatedGreeks if found, None otherwise
        """
        stmt = (
            select(GreeksSnapshot)
            .where(
                GreeksSnapshot.scope == scope,
                GreeksSnapshot.scope_id == scope_id,
            )
            .order_by(GreeksSnapshot.as_of_ts.desc())
            .limit(1)
        )

        result = await self._session.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            return None

        return self._snapshot_to_aggregated(snapshot)

    async def get_prev_snapshot(
        self, scope: str, scope_id: str, window_seconds: int = 300
    ) -> AggregatedGreeks | None:
        """Get snapshot from ~window_seconds ago for ROC comparison.

        Returns the latest snapshot older than window_seconds ago.

        Args:
            scope: The scope type ("ACCOUNT" or "STRATEGY")
            scope_id: The scope identifier (account ID or strategy ID)
            window_seconds: Time window in seconds (default 300 = 5 minutes)

        Returns:
            AggregatedGreeks if found, None otherwise
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)

        stmt = (
            select(GreeksSnapshot)
            .where(
                GreeksSnapshot.scope == scope,
                GreeksSnapshot.scope_id == scope_id,
                GreeksSnapshot.as_of_ts < cutoff_time,
            )
            .order_by(GreeksSnapshot.as_of_ts.desc())
            .limit(1)
        )

        result = await self._session.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            return None

        return self._snapshot_to_aggregated(snapshot)

    def _snapshot_to_aggregated(self, snapshot: GreeksSnapshot) -> AggregatedGreeks:
        """Convert a GreeksSnapshot to an AggregatedGreeks dataclass.

        Args:
            snapshot: The database snapshot record

        Returns:
            AggregatedGreeks dataclass with snapshot data
        """
        return AggregatedGreeks(
            scope=snapshot.scope,  # type: ignore
            scope_id=snapshot.scope_id,
            strategy_id=snapshot.strategy_id,
            dollar_delta=snapshot.dollar_delta,
            gamma_dollar=snapshot.gamma_dollar,
            gamma_pnl_1pct=snapshot.gamma_pnl_1pct,
            vega_per_1pct=snapshot.vega_per_1pct,
            theta_per_day=snapshot.theta_per_day,
            valid_legs_count=snapshot.valid_legs_count,
            total_legs_count=snapshot.total_legs_count,
            valid_notional=snapshot.valid_notional,
            total_notional=snapshot.total_notional,
            has_high_risk_missing_legs=snapshot.has_high_risk_missing_legs,
            has_positions=snapshot.total_legs_count > 0,
            as_of_ts=snapshot.as_of_ts,
        )

    async def save_alert(self, alert: GreeksAlert) -> GreeksAlertRecord:
        """Persist an alert to the database.

        Args:
            alert: The GreeksAlert dataclass to persist

        Returns:
            The created GreeksAlertRecord database record
        """
        record = GreeksAlertRecord(
            alert_id=UUID(alert.alert_id),
            alert_type=alert.alert_type,
            scope=alert.scope,
            scope_id=alert.scope_id,
            metric=alert.metric.value,
            level=alert.level.value,
            current_value=alert.current_value,
            threshold_value=alert.threshold_value,
            prev_value=alert.prev_value,
            change_pct=alert.change_pct,
            message=alert.message,
            created_at=alert.created_at,
        )

        self._session.add(record)
        await self._session.commit()
        await self._session.refresh(record)

        return record

    async def get_unacknowledged_alerts(
        self, scope: str | None = None, scope_id: str | None = None
    ) -> list[GreeksAlertRecord]:
        """Get alerts that haven't been acknowledged.

        Args:
            scope: Optional filter by scope type
            scope_id: Optional filter by scope ID

        Returns:
            List of unacknowledged GreeksAlertRecord records
        """
        stmt = select(GreeksAlertRecord).where(GreeksAlertRecord.acknowledged_at.is_(None))

        if scope is not None:
            stmt = stmt.where(GreeksAlertRecord.scope == scope)

        if scope_id is not None:
            stmt = stmt.where(GreeksAlertRecord.scope_id == scope_id)

        stmt = stmt.order_by(GreeksAlertRecord.created_at.desc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Mark an alert as acknowledged.

        Args:
            alert_id: The UUID string of the alert to acknowledge
            acknowledged_by: The user/system acknowledging the alert

        Returns:
            True if alert was found and updated, False otherwise
        """
        try:
            alert_uuid = UUID(alert_id)
        except ValueError:
            return False

        stmt = (
            update(GreeksAlertRecord)
            .where(GreeksAlertRecord.alert_id == alert_uuid)
            .values(
                acknowledged_at=datetime.now(timezone.utc),
                acknowledged_by=acknowledged_by,
            )
        )

        result = await self._session.execute(stmt)
        await self._session.commit()

        return result.rowcount > 0
