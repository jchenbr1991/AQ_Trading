"""Performance tests for ExpirationChecker.

Target: 1000 option positions check < 10 seconds (per Design Doc).
"""

import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest
from src.models.position import AssetType, PutCall
from src.options.checker import ExpirationChecker

# Use market timezone for consistency with ExpirationChecker
MARKET_TZ = ZoneInfo("America/New_York")


def create_mock_option_position(
    position_id: int,
    days_to_expiry: int,
    symbol_prefix: str = "TEST",
) -> MagicMock:
    """Create a mock option position with specified DTE.

    Args:
        position_id: Unique position ID
        days_to_expiry: Days until expiration (can be negative for expired)
        symbol_prefix: Symbol prefix for the option

    Returns:
        MagicMock configured as an option position
    """
    # Use market timezone for consistency with checker
    market_today = datetime.now(MARKET_TZ).date()
    pos = MagicMock()
    pos.id = position_id
    pos.symbol = f"{symbol_prefix}{position_id:04d}C150"
    pos.asset_type = AssetType.OPTION
    pos.expiry = market_today + timedelta(days=days_to_expiry)
    pos.strike = Decimal("150.00")
    pos.put_call = PutCall.CALL if position_id % 2 == 0 else PutCall.PUT
    pos.quantity = 10
    pos.contract_key = f"contract_{position_id}"
    return pos


def generate_position_set(count: int) -> list[MagicMock]:
    """Generate a diverse set of mock option positions.

    Distribution:
    - 10% DTE=0 (expiring today, triggers 4 thresholds)
    - 10% DTE=1 (tomorrow, triggers 3 thresholds)
    - 15% DTE=2-3 (triggers 2 thresholds)
    - 15% DTE=4-7 (triggers 1 threshold)
    - 40% DTE=8-30 (no alerts, but still processed)
    - 10% already expired (DTE < 0)

    Args:
        count: Total number of positions to generate

    Returns:
        List of mock positions with varied DTEs
    """
    positions = []

    # Calculate counts for each category
    dte_0_count = int(count * 0.10)
    dte_1_count = int(count * 0.10)
    dte_2_3_count = int(count * 0.15)
    dte_4_7_count = int(count * 0.15)
    dte_out_of_scope_count = int(count * 0.40)
    expired_count = (
        count - dte_0_count - dte_1_count - dte_2_3_count - dte_4_7_count - dte_out_of_scope_count
    )

    pos_id = 1

    # DTE=0 (expiring today)
    for _ in range(dte_0_count):
        positions.append(create_mock_option_position(pos_id, days_to_expiry=0))
        pos_id += 1

    # DTE=1 (tomorrow)
    for _ in range(dte_1_count):
        positions.append(create_mock_option_position(pos_id, days_to_expiry=1))
        pos_id += 1

    # DTE=2-3
    for i in range(dte_2_3_count):
        dte = 2 if i % 2 == 0 else 3
        positions.append(create_mock_option_position(pos_id, days_to_expiry=dte))
        pos_id += 1

    # DTE=4-7
    for i in range(dte_4_7_count):
        dte = 4 + (i % 4)  # 4, 5, 6, 7
        positions.append(create_mock_option_position(pos_id, days_to_expiry=dte))
        pos_id += 1

    # DTE=8-30 (out of scope, no alerts)
    for i in range(dte_out_of_scope_count):
        dte = 8 + (i % 23)  # 8 to 30
        positions.append(create_mock_option_position(pos_id, days_to_expiry=dte))
        pos_id += 1

    # Already expired
    for i in range(expired_count):
        dte = -1 - (i % 10)  # -1 to -10
        positions.append(create_mock_option_position(pos_id, days_to_expiry=dte))
        pos_id += 1

    return positions


class TestExpirationCheckerPerformance:
    """Performance tests for ExpirationChecker.

    Validates that processing 1000 option positions completes within
    the target time limit of 10 seconds.
    """

    POSITION_COUNT = 1000
    TARGET_TIME_SECONDS = 10.0

    @pytest.fixture
    def mock_portfolio(self):
        """Create a mock PortfolioManager."""
        portfolio = AsyncMock()
        return portfolio

    @pytest.fixture
    def mock_alert_repo(self):
        """Create a mock AlertRepository with fast responses."""
        repo = AsyncMock()
        # Simulate mix of new and deduplicated alerts
        call_count = [0]

        async def mock_persist(alert):
            call_count[0] += 1
            # First occurrence of each dedupe_key is new
            is_new = call_count[0] % 3 != 0  # ~67% new alerts
            return (is_new, f"alert-{call_count[0]}")

        repo.persist_alert.side_effect = mock_persist
        return repo

    @pytest.mark.asyncio
    async def test_1000_positions_under_10_seconds(
        self,
        mock_portfolio,
        mock_alert_repo,
    ):
        """Check 1000 option positions completes in under 10 seconds.

        This is the primary performance target from the design doc:
        "1000 option positions check < 10s"
        """
        # Generate test positions
        positions = generate_position_set(self.POSITION_COUNT)
        mock_portfolio.get_positions.return_value = positions

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ZoneInfo("America/New_York"),
        )

        # Measure execution time
        start_time = time.perf_counter()
        stats = await checker.check_expirations("perf-test-account")
        elapsed_time = time.perf_counter() - start_time

        # Calculate throughput
        positions_per_second = self.POSITION_COUNT / elapsed_time

        # Log performance metrics
        print(f"\n{'=' * 60}")
        print("PERFORMANCE TEST RESULTS")
        print(f"{'=' * 60}")
        print(f"Positions processed: {stats['positions_checked']}")
        print(f"Elapsed time: {elapsed_time:.3f} seconds")
        print(f"Throughput: {positions_per_second:.1f} positions/second")
        print(f"Target time: {self.TARGET_TIME_SECONDS} seconds")
        print(f"{'=' * 60}")
        print(f"Alerts created: {stats['alerts_created']}")
        print(f"Alerts deduplicated: {stats['alerts_deduplicated']}")
        print(f"Positions already expired: {stats['positions_already_expired']}")
        print(f"Positions not expiring soon: {stats['positions_not_expiring_soon']}")
        print(f"{'=' * 60}")

        # Assertions
        assert stats["positions_checked"] == self.POSITION_COUNT, (
            f"Expected {self.POSITION_COUNT} positions checked, "
            f"got {stats['positions_checked']}"
        )

        assert elapsed_time < self.TARGET_TIME_SECONDS, (
            f"Performance target missed: {elapsed_time:.3f}s > {self.TARGET_TIME_SECONDS}s "
            f"({positions_per_second:.1f} pos/sec)"
        )

        # Verify reasonable alert counts (sanity check)
        assert stats["alerts_attempted"] > 0, "Expected at least some alert attempts"

    @pytest.mark.asyncio
    async def test_2000_positions_scalability(
        self,
        mock_portfolio,
        mock_alert_repo,
    ):
        """Verify scalability with 2x the target position count.

        This tests that performance scales roughly linearly and
        doesn't hit any unexpected bottlenecks.
        """
        position_count = 2000
        # Allow proportionally more time (2x positions = 2x time budget)
        target_time = self.TARGET_TIME_SECONDS * 2

        positions = generate_position_set(position_count)
        mock_portfolio.get_positions.return_value = positions

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ZoneInfo("America/New_York"),
        )

        start_time = time.perf_counter()
        stats = await checker.check_expirations("perf-test-2000")
        elapsed_time = time.perf_counter() - start_time

        positions_per_second = position_count / elapsed_time

        print(f"\n{'=' * 60}")
        print("SCALABILITY TEST (2000 positions)")
        print(f"{'=' * 60}")
        print(f"Positions processed: {stats['positions_checked']}")
        print(f"Elapsed time: {elapsed_time:.3f} seconds")
        print(f"Throughput: {positions_per_second:.1f} positions/second")
        print(f"{'=' * 60}")

        assert stats["positions_checked"] == position_count
        assert (
            elapsed_time < target_time
        ), f"Scalability target missed: {elapsed_time:.3f}s > {target_time}s"

    @pytest.mark.asyncio
    async def test_worst_case_all_expiring_today(
        self,
        mock_portfolio,
        mock_alert_repo,
    ):
        """Test worst-case scenario: all positions expiring today.

        When DTE=0, each position triggers all 4 thresholds,
        maximizing the number of alert creation calls.
        """
        position_count = 1000

        # All positions expiring today (DTE=0) - worst case for alerts
        positions = [
            create_mock_option_position(i, days_to_expiry=0) for i in range(position_count)
        ]
        mock_portfolio.get_positions.return_value = positions

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ZoneInfo("America/New_York"),
        )

        start_time = time.perf_counter()
        stats = await checker.check_expirations("perf-test-worst-case")
        elapsed_time = time.perf_counter() - start_time

        positions_per_second = position_count / elapsed_time

        print(f"\n{'=' * 60}")
        print("WORST CASE TEST (all DTE=0)")
        print(f"{'=' * 60}")
        print(f"Positions processed: {stats['positions_checked']}")
        print(f"Elapsed time: {elapsed_time:.3f} seconds")
        print(f"Throughput: {positions_per_second:.1f} positions/second")
        print(f"Alerts attempted: {stats['alerts_attempted']}")
        print(f"Expected alerts: {position_count * 4} (4 thresholds per position)")
        print(f"{'=' * 60}")

        # Each position with DTE=0 should trigger 4 thresholds
        assert (
            stats["alerts_attempted"] == position_count * 4
        ), f"Expected {position_count * 4} alerts, got {stats['alerts_attempted']}"

        # Should still complete within target time
        assert (
            elapsed_time < self.TARGET_TIME_SECONDS
        ), f"Worst-case performance target missed: {elapsed_time:.3f}s > {self.TARGET_TIME_SECONDS}s"

    @pytest.mark.asyncio
    async def test_best_case_all_out_of_scope(
        self,
        mock_portfolio,
        mock_alert_repo,
    ):
        """Test best-case scenario: all positions out of threshold scope.

        When DTE > 7, no alerts are created, minimizing work.
        This establishes the baseline processing speed.
        """
        position_count = 1000

        # All positions with DTE > 7 (out of scope)
        positions = [
            create_mock_option_position(i, days_to_expiry=30) for i in range(position_count)
        ]
        mock_portfolio.get_positions.return_value = positions

        checker = ExpirationChecker(
            portfolio=mock_portfolio,
            alert_repo=mock_alert_repo,
            market_tz=ZoneInfo("America/New_York"),
        )

        start_time = time.perf_counter()
        stats = await checker.check_expirations("perf-test-best-case")
        elapsed_time = time.perf_counter() - start_time

        positions_per_second = position_count / elapsed_time

        print(f"\n{'=' * 60}")
        print("BEST CASE TEST (all out of scope)")
        print(f"{'=' * 60}")
        print(f"Positions processed: {stats['positions_checked']}")
        print(f"Elapsed time: {elapsed_time:.3f} seconds")
        print(f"Throughput: {positions_per_second:.1f} positions/second")
        print(f"Alerts attempted: {stats['alerts_attempted']}")
        print(f"{'=' * 60}")

        assert stats["alerts_attempted"] == 0
        assert stats["positions_not_expiring_soon"] == position_count

        # Should be significantly faster than target
        assert (
            elapsed_time < self.TARGET_TIME_SECONDS / 2
        ), f"Best-case should be faster: {elapsed_time:.3f}s"
