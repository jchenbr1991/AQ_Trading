"""Tests for Greeks Repository.

Tests cover:
- Task 20: GreeksRepository for persisting and retrieving Greeks data
  - save_snapshot persists data correctly
  - get_latest_snapshot returns most recent
  - get_prev_snapshot returns correct time window
  - save_alert persists alert
  - acknowledge_alert updates record
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


def _make_aggregated_greeks(
    scope: str = "ACCOUNT",
    scope_id: str = "acc_001",
    strategy_id: str | None = None,
    dollar_delta: Decimal = Decimal("0"),
    gamma_dollar: Decimal = Decimal("0"),
    gamma_pnl_1pct: Decimal = Decimal("0"),
    vega_per_1pct: Decimal = Decimal("0"),
    theta_per_day: Decimal = Decimal("0"),
    valid_legs_count: int = 0,
    total_legs_count: int = 0,
    valid_notional: Decimal = Decimal("0"),
    total_notional: Decimal = Decimal("0"),
    has_high_risk_missing_legs: bool = False,
    as_of_ts: datetime | None = None,
):
    """Factory function to create AggregatedGreeks for testing."""
    from src.greeks.models import AggregatedGreeks

    return AggregatedGreeks(
        scope=scope,
        scope_id=scope_id,
        strategy_id=strategy_id,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        valid_legs_count=valid_legs_count,
        total_legs_count=total_legs_count,
        valid_notional=valid_notional,
        total_notional=total_notional,
        has_high_risk_missing_legs=has_high_risk_missing_legs,
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
    )


def _make_greeks_alert(
    scope: str = "ACCOUNT",
    scope_id: str = "acc_001",
    alert_type: str = "THRESHOLD",
    metric_value: str = "delta",
    level: str = "WARN",
    current_value: Decimal = Decimal("45000"),
    threshold_value: Decimal = Decimal("40000"),
    prev_value: Decimal | None = None,
    change_pct: Decimal | None = None,
    message: str = "Test alert",
    created_at: datetime | None = None,
):
    """Factory function to create GreeksAlert for testing."""
    from uuid import uuid4

    from src.greeks.alerts import GreeksAlert
    from src.greeks.models import GreeksLevel, RiskMetric

    metric = RiskMetric(metric_value)
    level_enum = GreeksLevel(level.lower())

    return GreeksAlert(
        alert_id=str(uuid4()),
        alert_type=alert_type,
        scope=scope,
        scope_id=scope_id,
        metric=metric,
        level=level_enum,
        current_value=current_value,
        threshold_value=threshold_value,
        prev_value=prev_value,
        change_pct=change_pct,
        message=message,
        created_at=created_at or datetime.now(timezone.utc),
    )


class TestGreeksRepositorySaveSnapshot:
    """Tests for GreeksRepository.save_snapshot - Task 20."""

    @pytest.mark.asyncio
    async def test_save_snapshot_persists_greeks_data(self, db_session):
        """save_snapshot persists AggregatedGreeks to database."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000.5000"),
            gamma_dollar=Decimal("8500.2500"),
            gamma_pnl_1pct=Decimal("42.5000"),
            vega_per_1pct=Decimal("15000.0000"),
            theta_per_day=Decimal("-2500.0000"),
            valid_legs_count=8,
            total_legs_count=10,
            valid_notional=Decimal("500000.0000"),
            total_notional=Decimal("600000.0000"),
            has_high_risk_missing_legs=True,
        )

        snapshot = await repo.save_snapshot(greeks)

        assert snapshot.id is not None
        assert snapshot.scope == "ACCOUNT"
        assert snapshot.scope_id == "acc_001"
        assert snapshot.dollar_delta == Decimal("45000.5000")
        assert snapshot.gamma_dollar == Decimal("8500.2500")
        assert snapshot.gamma_pnl_1pct == Decimal("42.5000")
        assert snapshot.vega_per_1pct == Decimal("15000.0000")
        assert snapshot.theta_per_day == Decimal("-2500.0000")
        assert snapshot.valid_legs_count == 8
        assert snapshot.total_legs_count == 10
        assert snapshot.has_high_risk_missing_legs is True

    @pytest.mark.asyncio
    async def test_save_snapshot_with_strategy_scope(self, db_session):
        """save_snapshot correctly handles STRATEGY scope."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        greeks = _make_aggregated_greeks(
            scope="STRATEGY",
            scope_id="momentum_v1",
            strategy_id="momentum_v1",
            dollar_delta=Decimal("20000"),
        )

        snapshot = await repo.save_snapshot(greeks)

        assert snapshot.scope == "STRATEGY"
        assert snapshot.scope_id == "momentum_v1"
        assert snapshot.strategy_id == "momentum_v1"

    @pytest.mark.asyncio
    async def test_save_snapshot_calculates_coverage_pct(self, db_session):
        """save_snapshot correctly calculates and stores coverage_pct."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        greeks = _make_aggregated_greeks(
            valid_notional=Decimal("90000"),
            total_notional=Decimal("100000"),
        )

        snapshot = await repo.save_snapshot(greeks)

        # Coverage should be 90%
        assert snapshot.coverage_pct == Decimal("90.00")


class TestGreeksRepositoryGetLatestSnapshot:
    """Tests for GreeksRepository.get_latest_snapshot - Task 20."""

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_returns_most_recent(self, db_session):
        """get_latest_snapshot returns the most recent snapshot for scope."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Save older snapshot
        old_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("30000"),
            as_of_ts=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        await repo.save_snapshot(old_greeks)

        # Save newer snapshot
        new_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
            as_of_ts=datetime.now(timezone.utc),
        )
        await repo.save_snapshot(new_greeks)

        # Get latest
        latest = await repo.get_latest_snapshot("ACCOUNT", "acc_001")

        assert latest is not None
        assert latest.dollar_delta == Decimal("45000")

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_returns_none_when_not_found(self, db_session):
        """get_latest_snapshot returns None when no snapshot exists."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        latest = await repo.get_latest_snapshot("ACCOUNT", "nonexistent")

        assert latest is None

    @pytest.mark.asyncio
    async def test_get_latest_snapshot_filters_by_scope(self, db_session):
        """get_latest_snapshot only returns snapshots for the specified scope."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Save snapshot for acc_001
        greeks1 = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
        )
        await repo.save_snapshot(greeks1)

        # Save snapshot for acc_002
        greeks2 = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_002",
            dollar_delta=Decimal("55000"),
        )
        await repo.save_snapshot(greeks2)

        # Get latest for acc_001
        latest = await repo.get_latest_snapshot("ACCOUNT", "acc_001")

        assert latest is not None
        assert latest.dollar_delta == Decimal("45000")


class TestGreeksRepositoryGetPrevSnapshot:
    """Tests for GreeksRepository.get_prev_snapshot - Task 20."""

    @pytest.mark.asyncio
    async def test_get_prev_snapshot_returns_snapshot_from_window(self, db_session):
        """get_prev_snapshot returns snapshot from ~window_seconds ago."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save snapshot from 10 minutes ago
        old_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("30000"),
            as_of_ts=now - timedelta(minutes=10),
        )
        await repo.save_snapshot(old_greeks)

        # Save snapshot from 1 minute ago (should not be returned with 5 min window)
        recent_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
            as_of_ts=now - timedelta(minutes=1),
        )
        await repo.save_snapshot(recent_greeks)

        # Get prev snapshot with 5 minute window (300 seconds)
        prev = await repo.get_prev_snapshot("ACCOUNT", "acc_001", window_seconds=300)

        assert prev is not None
        assert prev.dollar_delta == Decimal("30000")

    @pytest.mark.asyncio
    async def test_get_prev_snapshot_returns_none_when_no_old_snapshot(self, db_session):
        """get_prev_snapshot returns None when no snapshot older than window exists."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save only recent snapshot
        recent_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
            as_of_ts=now - timedelta(minutes=1),
        )
        await repo.save_snapshot(recent_greeks)

        # Get prev with 5 minute window - should return None
        prev = await repo.get_prev_snapshot("ACCOUNT", "acc_001", window_seconds=300)

        assert prev is None

    @pytest.mark.asyncio
    async def test_get_prev_snapshot_uses_default_window(self, db_session):
        """get_prev_snapshot uses default 300 second window."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save snapshot from 6 minutes ago (should be returned)
        old_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("30000"),
            as_of_ts=now - timedelta(minutes=6),
        )
        await repo.save_snapshot(old_greeks)

        # Get prev with default window
        prev = await repo.get_prev_snapshot("ACCOUNT", "acc_001")

        assert prev is not None
        assert prev.dollar_delta == Decimal("30000")


class TestGreeksRepositorySaveAlert:
    """Tests for GreeksRepository.save_alert - Task 20."""

    @pytest.mark.asyncio
    async def test_save_alert_persists_threshold_alert(self, db_session):
        """save_alert persists a THRESHOLD alert to database."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        alert = _make_greeks_alert(
            alert_type="THRESHOLD",
            scope="ACCOUNT",
            scope_id="acc_001",
            metric_value="delta",
            level="WARN",
            current_value=Decimal("45000"),
            threshold_value=Decimal("40000"),
            message="Delta exceeded WARN threshold",
        )

        record = await repo.save_alert(alert)

        assert record.id is not None
        assert str(record.alert_id) == alert.alert_id
        assert record.alert_type == "THRESHOLD"
        assert record.scope == "ACCOUNT"
        assert record.scope_id == "acc_001"
        assert record.metric == "delta"
        assert record.level == "warn"
        assert record.current_value == Decimal("45000")
        assert record.threshold_value == Decimal("40000")
        assert record.message == "Delta exceeded WARN threshold"
        assert record.acknowledged_at is None

    @pytest.mark.asyncio
    async def test_save_alert_persists_roc_alert(self, db_session):
        """save_alert persists a ROC alert with prev_value and change_pct."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        alert = _make_greeks_alert(
            alert_type="ROC",
            metric_value="gamma",
            current_value=Decimal("8000"),
            threshold_value=Decimal("1000"),
            prev_value=Decimal("5000"),
            change_pct=Decimal("60.0"),
            message="Gamma changed by 60%",
        )

        record = await repo.save_alert(alert)

        assert record.alert_type == "ROC"
        assert record.prev_value == Decimal("5000")
        assert record.change_pct == Decimal("60.0")


class TestGreeksRepositoryGetUnacknowledgedAlerts:
    """Tests for GreeksRepository.get_unacknowledged_alerts - Task 20."""

    @pytest.mark.asyncio
    async def test_get_unacknowledged_alerts_returns_unacked(self, db_session):
        """get_unacknowledged_alerts returns alerts without acknowledgment."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Save two alerts
        alert1 = _make_greeks_alert(metric_value="delta")
        alert2 = _make_greeks_alert(metric_value="gamma")
        await repo.save_alert(alert1)
        await repo.save_alert(alert2)

        alerts = await repo.get_unacknowledged_alerts()

        assert len(alerts) == 2

    @pytest.mark.asyncio
    async def test_get_unacknowledged_alerts_excludes_acked(self, db_session):
        """get_unacknowledged_alerts excludes acknowledged alerts."""

        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Save alert and acknowledge it
        alert = _make_greeks_alert()
        await repo.save_alert(alert)
        await repo.acknowledge_alert(alert.alert_id, "test_user")

        alerts = await repo.get_unacknowledged_alerts()

        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_get_unacknowledged_alerts_filters_by_scope(self, db_session):
        """get_unacknowledged_alerts can filter by scope and scope_id."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Save alerts for different accounts
        alert1 = _make_greeks_alert(scope="ACCOUNT", scope_id="acc_001")
        alert2 = _make_greeks_alert(scope="ACCOUNT", scope_id="acc_002")
        await repo.save_alert(alert1)
        await repo.save_alert(alert2)

        # Filter by scope_id
        alerts = await repo.get_unacknowledged_alerts(scope="ACCOUNT", scope_id="acc_001")

        assert len(alerts) == 1
        assert alerts[0].scope_id == "acc_001"


class TestGreeksRepositoryAcknowledgeAlert:
    """Tests for GreeksRepository.acknowledge_alert - Task 20."""

    @pytest.mark.asyncio
    async def test_acknowledge_alert_updates_record(self, db_session):
        """acknowledge_alert sets acknowledged_at and acknowledged_by."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Save alert
        alert = _make_greeks_alert()
        await repo.save_alert(alert)

        # Acknowledge it
        result = await repo.acknowledge_alert(alert.alert_id, "admin_user")

        assert result is True

        # Verify in database
        alerts = await repo.get_unacknowledged_alerts()
        assert len(alerts) == 0

    @pytest.mark.asyncio
    async def test_acknowledge_alert_returns_false_for_nonexistent(self, db_session):
        """acknowledge_alert returns False for nonexistent alert_id."""
        from uuid import uuid4

        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        result = await repo.acknowledge_alert(str(uuid4()), "admin_user")

        assert result is False

    @pytest.mark.asyncio
    async def test_acknowledge_alert_is_idempotent(self, db_session):
        """acknowledge_alert can be called multiple times."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        alert = _make_greeks_alert()
        await repo.save_alert(alert)

        # First acknowledgment
        result1 = await repo.acknowledge_alert(alert.alert_id, "user1")
        assert result1 is True

        # Second acknowledgment - should still succeed
        result2 = await repo.acknowledge_alert(alert.alert_id, "user2")
        assert result2 is True


class TestGreeksRepositoryGetHistory:
    """Tests for GreeksRepository.get_history - V2 Feature."""

    @pytest.mark.asyncio
    async def test_get_history_returns_points_within_time_range(self, db_session):
        """get_history returns snapshots within the specified time range."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save snapshots at different times
        for i in range(5):
            greeks = _make_aggregated_greeks(
                scope="ACCOUNT",
                scope_id="acc_001",
                dollar_delta=Decimal(f"{10000 + i * 1000}"),
                as_of_ts=now - timedelta(minutes=i * 10),
            )
            await repo.save_snapshot(greeks)

        # Get history for last hour
        start_ts = now - timedelta(hours=1)
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=now,
        )

        # All 5 snapshots should be within 1 hour
        assert len(points) == 5

    @pytest.mark.asyncio
    async def test_get_history_excludes_points_outside_range(self, db_session):
        """get_history excludes snapshots outside the time range."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save snapshot within range
        greeks_in = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("10000"),
            as_of_ts=now - timedelta(minutes=30),
        )
        await repo.save_snapshot(greeks_in)

        # Save snapshot outside range (2 hours ago)
        greeks_out = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("20000"),
            as_of_ts=now - timedelta(hours=2),
        )
        await repo.save_snapshot(greeks_out)

        # Get history for last hour only
        start_ts = now - timedelta(hours=1)
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=now,
        )

        assert len(points) == 1
        assert points[0].dollar_delta == Decimal("10000")

    @pytest.mark.asyncio
    async def test_get_history_returns_empty_list_when_no_data(self, db_session):
        """get_history returns empty list when no snapshots exist."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)
        start_ts = now - timedelta(hours=1)

        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="nonexistent",
            start_ts=start_ts,
            end_ts=now,
        )

        assert points == []

    @pytest.mark.asyncio
    async def test_get_history_filters_by_scope(self, db_session):
        """get_history only returns snapshots for the specified scope."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save for acc_001
        greeks1 = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("10000"),
            as_of_ts=now - timedelta(minutes=5),
        )
        await repo.save_snapshot(greeks1)

        # Save for acc_002
        greeks2 = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_002",
            dollar_delta=Decimal("20000"),
            as_of_ts=now - timedelta(minutes=5),
        )
        await repo.save_snapshot(greeks2)

        start_ts = now - timedelta(hours=1)
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=now,
        )

        assert len(points) == 1
        assert points[0].dollar_delta == Decimal("10000")

    @pytest.mark.asyncio
    async def test_get_history_returns_ordered_by_timestamp(self, db_session):
        """get_history returns points ordered by timestamp ascending."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        # Save in reverse order
        for i in [3, 1, 2]:
            greeks = _make_aggregated_greeks(
                scope="ACCOUNT",
                scope_id="acc_001",
                dollar_delta=Decimal(f"{i * 10000}"),
                as_of_ts=now - timedelta(minutes=i * 10),
            )
            await repo.save_snapshot(greeks)

        start_ts = now - timedelta(hours=1)
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=now,
        )

        assert len(points) == 3
        # Should be in ascending order (oldest first)
        assert points[0].ts < points[1].ts < points[2].ts

    @pytest.mark.asyncio
    async def test_get_history_returns_greeks_history_points(self, db_session):
        """get_history returns GreeksHistoryPoint objects with correct fields."""
        from src.greeks.repository import GreeksRepository
        from src.greeks.v2_models import GreeksHistoryPoint

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("50000"),
            gamma_dollar=Decimal("2500"),
            vega_per_1pct=Decimal("15000"),
            theta_per_day=Decimal("-3000"),
            valid_notional=Decimal("90000"),
            total_notional=Decimal("100000"),
            as_of_ts=now - timedelta(minutes=5),
        )
        await repo.save_snapshot(greeks)

        start_ts = now - timedelta(hours=1)
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=now,
        )

        assert len(points) == 1
        point = points[0]
        assert isinstance(point, GreeksHistoryPoint)
        assert point.dollar_delta == Decimal("50000")
        assert point.gamma_dollar == Decimal("2500")
        assert point.vega_per_1pct == Decimal("15000")
        assert point.theta_per_day == Decimal("-3000")
        assert point.coverage_pct == Decimal("90.00")
        assert point.point_count == 1

    @pytest.mark.asyncio
    async def test_get_history_aggregates_by_interval(self, db_session):
        """get_history with interval aggregates points into time buckets."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Use a fixed base time aligned to minute boundary
        base_time = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        # Save 6 snapshots at 10-second intervals within the same 1-minute bucket
        for i in range(6):
            greeks = _make_aggregated_greeks(
                scope="ACCOUNT",
                scope_id="acc_001",
                dollar_delta=Decimal(f"{10000 + i * 1000}"),  # 10000, 11000, ..., 15000
                gamma_dollar=Decimal("2000"),
                vega_per_1pct=Decimal("15000"),
                theta_per_day=Decimal("-3000"),
                valid_notional=Decimal("100000"),
                total_notional=Decimal("100000"),
                as_of_ts=base_time + timedelta(seconds=i * 10),  # 10:30:00, 10:30:10, ..., 10:30:50
            )
            await repo.save_snapshot(greeks)

        start_ts = base_time - timedelta(hours=1)
        end_ts = base_time + timedelta(hours=1)
        # Request with 1-minute interval aggregation
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=end_ts,
            interval_seconds=60,  # 1 minute
        )

        # All 6 points should be aggregated into 1 bucket
        assert len(points) == 1
        point = points[0]
        # Average of 10000, 11000, 12000, 13000, 14000, 15000 = 12500
        assert point.dollar_delta == Decimal("12500")
        assert point.point_count == 6

    @pytest.mark.asyncio
    async def test_get_history_aggregates_into_multiple_buckets(self, db_session):
        """get_history creates multiple buckets when data spans intervals."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        # Use fixed base times for predictable bucket boundaries
        bucket1_time = datetime(2026, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        bucket2_time = datetime(2026, 1, 15, 10, 31, 0, tzinfo=timezone.utc)

        # Save 2 snapshots in bucket 1 (10:30:xx)
        for i in range(2):
            greeks = _make_aggregated_greeks(
                scope="ACCOUNT",
                scope_id="acc_001",
                dollar_delta=Decimal(f"{(i + 1) * 10000}"),  # 10000, 20000
                as_of_ts=bucket1_time + timedelta(seconds=i * 10),
            )
            await repo.save_snapshot(greeks)

        # Save 2 snapshots in bucket 2 (10:31:xx)
        for i in range(2):
            greeks = _make_aggregated_greeks(
                scope="ACCOUNT",
                scope_id="acc_001",
                dollar_delta=Decimal(f"{(i + 3) * 10000}"),  # 30000, 40000
                as_of_ts=bucket2_time + timedelta(seconds=i * 10),
            )
            await repo.save_snapshot(greeks)

        start_ts = bucket1_time - timedelta(hours=1)
        end_ts = bucket2_time + timedelta(hours=1)
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=end_ts,
            interval_seconds=60,
        )

        # Should have 2 buckets
        assert len(points) == 2
        # Each bucket should have 2 points aggregated
        assert all(p.point_count == 2 for p in points)
        # First bucket avg: (10000+20000)/2 = 15000
        assert points[0].dollar_delta == Decimal("15000")
        # Second bucket avg: (30000+40000)/2 = 35000
        assert points[1].dollar_delta == Decimal("35000")

    @pytest.mark.asyncio
    async def test_get_history_no_interval_returns_raw(self, db_session):
        """get_history without interval returns raw points (point_count=1)."""
        from src.greeks.repository import GreeksRepository

        repo = GreeksRepository(db_session)

        now = datetime.now(timezone.utc)

        for i in range(3):
            greeks = _make_aggregated_greeks(
                scope="ACCOUNT",
                scope_id="acc_001",
                dollar_delta=Decimal(f"{10000 + i * 1000}"),
                as_of_ts=now - timedelta(seconds=i * 10),
            )
            await repo.save_snapshot(greeks)

        start_ts = now - timedelta(hours=1)
        # No interval = raw data
        points = await repo.get_history(
            scope="ACCOUNT",
            scope_id="acc_001",
            start_ts=start_ts,
            end_ts=now,
        )

        assert len(points) == 3
        assert all(p.point_count == 1 for p in points)
