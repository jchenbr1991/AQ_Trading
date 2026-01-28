"""Tests for Greeks Aggregator.

Tests cover:
- Task 5: Basic aggregation with _Accumulator class
- Task 6: Strategy-level aggregation
- Task 7: Top contributors ranking
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal


def _make_position_greeks(
    position_id: int,
    symbol: str = "AAPL240119C00150000",
    underlying_symbol: str = "AAPL",
    quantity: int = 10,
    multiplier: int = 100,
    underlying_price: Decimal = Decimal("150.00"),
    option_type: str = "call",
    strike: Decimal = Decimal("150.00"),
    expiry: str = "2024-01-19",
    dollar_delta: Decimal = Decimal("5000.00"),
    gamma_dollar: Decimal = Decimal("100.00"),
    gamma_pnl_1pct: Decimal = Decimal("0.50"),
    vega_per_1pct: Decimal = Decimal("200.00"),
    theta_per_day: Decimal = Decimal("-50.00"),
    valid: bool = True,
    quality_warnings: list[str] | None = None,
    as_of_ts: datetime | None = None,
    strategy_id: str | None = None,
):
    """Factory function to create PositionGreeks for testing."""
    from src.greeks.models import GreeksDataSource, PositionGreeks

    return PositionGreeks(
        position_id=position_id,
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        quantity=quantity,
        multiplier=multiplier,
        underlying_price=underlying_price,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        source=GreeksDataSource.FUTU,
        model=None,
        valid=valid,
        quality_warnings=quality_warnings or [],
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
        strategy_id=strategy_id,
    )


class TestAccumulator:
    """Tests for internal _Accumulator class."""

    def test_accumulator_initial_state(self):
        """_Accumulator initializes with zero values."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()

        assert acc.dollar_delta == Decimal("0")
        assert acc.gamma_dollar == Decimal("0")
        assert acc.gamma_pnl_1pct == Decimal("0")
        assert acc.vega_per_1pct == Decimal("0")
        assert acc.theta_per_day == Decimal("0")
        assert acc.valid_legs_count == 0
        assert acc.total_legs_count == 0
        assert acc.valid_notional == Decimal("0")
        assert acc.total_notional == Decimal("0")
        assert acc.missing_positions == []
        assert acc.high_risk_missing_positions == []
        assert acc.warning_positions == []
        assert acc.as_of_ts_min is None
        assert acc.as_of_ts_max is None

    def test_accumulator_add_valid_position(self):
        """_Accumulator.add() accumulates valid position Greeks."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()
        pg = _make_position_greeks(
            position_id=1,
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.50"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
        )

        acc.add(pg)

        assert acc.dollar_delta == Decimal("5000.00")
        assert acc.gamma_dollar == Decimal("100.00")
        assert acc.gamma_pnl_1pct == Decimal("0.50")
        assert acc.vega_per_1pct == Decimal("200.00")
        assert acc.theta_per_day == Decimal("-50.00")
        assert acc.valid_legs_count == 1
        assert acc.total_legs_count == 1
        # notional = 10 * 150 * 100 = 150000
        assert acc.valid_notional == Decimal("150000.00")
        assert acc.total_notional == Decimal("150000.00")
        assert acc.missing_positions == []

    def test_accumulator_add_multiple_positions(self):
        """_Accumulator.add() accumulates multiple positions."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()
        pg1 = _make_position_greeks(
            position_id=1,
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.50"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
        )
        pg2 = _make_position_greeks(
            position_id=2,
            symbol="TSLA240119P00200000",
            underlying_symbol="TSLA",
            underlying_price=Decimal("200.00"),
            dollar_delta=Decimal("-3000.00"),
            gamma_dollar=Decimal("80.00"),
            gamma_pnl_1pct=Decimal("0.40"),
            vega_per_1pct=Decimal("150.00"),
            theta_per_day=Decimal("-30.00"),
        )

        acc.add(pg1)
        acc.add(pg2)

        assert acc.dollar_delta == Decimal("2000.00")  # 5000 + (-3000)
        assert acc.gamma_dollar == Decimal("180.00")  # 100 + 80
        assert acc.gamma_pnl_1pct == Decimal("0.90")  # 0.50 + 0.40
        assert acc.vega_per_1pct == Decimal("350.00")  # 200 + 150
        assert acc.theta_per_day == Decimal("-80.00")  # -50 + (-30)
        assert acc.valid_legs_count == 2
        assert acc.total_legs_count == 2
        # pg1 notional = 10 * 150 * 100 = 150000
        # pg2 notional = 10 * 200 * 100 = 200000
        assert acc.valid_notional == Decimal("350000.00")
        assert acc.total_notional == Decimal("350000.00")

    def test_accumulator_add_invalid_position(self):
        """_Accumulator.add() tracks invalid positions without accumulating Greeks."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()
        pg = _make_position_greeks(
            position_id=42,
            valid=False,
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
        )

        acc.add(pg)

        # Greeks should not be accumulated for invalid positions
        assert acc.dollar_delta == Decimal("0")
        assert acc.gamma_dollar == Decimal("0")
        assert acc.valid_legs_count == 0
        assert acc.total_legs_count == 1
        assert acc.valid_notional == Decimal("0")
        # notional still tracked in total
        assert acc.total_notional == Decimal("150000.00")
        assert 42 in acc.missing_positions

    def test_accumulator_high_risk_threshold_gamma(self):
        """_Accumulator tracks high gamma missing positions."""
        from src.greeks.aggregator import GAMMA_HIGH_RISK_THRESHOLD, _Accumulator

        acc = _Accumulator()
        # Create invalid position with high gamma
        pg = _make_position_greeks(
            position_id=99,
            valid=False,
            gamma_dollar=Decimal(str(GAMMA_HIGH_RISK_THRESHOLD + 100)),
        )

        acc.add(pg)

        assert 99 in acc.missing_positions
        assert 99 in acc.high_risk_missing_positions

    def test_accumulator_high_risk_threshold_vega(self):
        """_Accumulator tracks high vega missing positions."""
        from src.greeks.aggregator import VEGA_HIGH_RISK_THRESHOLD, _Accumulator

        acc = _Accumulator()
        # Create invalid position with high vega
        pg = _make_position_greeks(
            position_id=88,
            valid=False,
            vega_per_1pct=Decimal(str(VEGA_HIGH_RISK_THRESHOLD + 100)),
        )

        acc.add(pg)

        assert 88 in acc.missing_positions
        assert 88 in acc.high_risk_missing_positions

    def test_accumulator_tracks_warning_positions(self):
        """_Accumulator tracks positions with quality warnings."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()
        pg = _make_position_greeks(
            position_id=77,
            valid=True,
            quality_warnings=["Staleness approaching threshold"],
        )

        acc.add(pg)

        assert 77 in acc.warning_positions
        assert acc.valid_legs_count == 1  # Still valid

    def test_accumulator_timestamp_tracking_min(self):
        """_Accumulator tracks minimum timestamp."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()
        now = datetime.now(timezone.utc)
        ts_old = now - timedelta(seconds=60)
        ts_new = now - timedelta(seconds=10)

        pg1 = _make_position_greeks(position_id=1, as_of_ts=ts_old)
        pg2 = _make_position_greeks(position_id=2, as_of_ts=ts_new)

        acc.add(pg1)
        acc.add(pg2)

        assert acc.as_of_ts_min == ts_old

    def test_accumulator_timestamp_tracking_max(self):
        """_Accumulator tracks maximum timestamp."""
        from src.greeks.aggregator import _Accumulator

        acc = _Accumulator()
        now = datetime.now(timezone.utc)
        ts_old = now - timedelta(seconds=60)
        ts_new = now - timedelta(seconds=10)

        pg1 = _make_position_greeks(position_id=1, as_of_ts=ts_old)
        pg2 = _make_position_greeks(position_id=2, as_of_ts=ts_new)

        acc.add(pg1)
        acc.add(pg2)

        assert acc.as_of_ts_max == ts_new


class TestGreeksAggregatorBasic:
    """Tests for GreeksAggregator.aggregate() - Task 5."""

    def test_aggregate_single_position(self):
        """GreeksAggregator.aggregate() works with single position."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        pg = _make_position_greeks(
            position_id=1,
            dollar_delta=Decimal("5000.00"),
            gamma_dollar=Decimal("100.00"),
            gamma_pnl_1pct=Decimal("0.50"),
            vega_per_1pct=Decimal("200.00"),
            theta_per_day=Decimal("-50.00"),
        )

        result = agg.aggregate([pg], scope="ACCOUNT", scope_id="acc_001")

        assert result.scope == "ACCOUNT"
        assert result.scope_id == "acc_001"
        assert result.dollar_delta == Decimal("5000.00")
        assert result.gamma_dollar == Decimal("100.00")
        assert result.gamma_pnl_1pct == Decimal("0.50")
        assert result.vega_per_1pct == Decimal("200.00")
        assert result.theta_per_day == Decimal("-50.00")
        assert result.valid_legs_count == 1
        assert result.total_legs_count == 1
        assert result.has_positions is True

    def test_aggregate_multiple_positions(self):
        """GreeksAggregator.aggregate() sums multiple positions."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        positions = [
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("5000.00"),
                gamma_dollar=Decimal("100.00"),
                gamma_pnl_1pct=Decimal("0.50"),
                vega_per_1pct=Decimal("200.00"),
                theta_per_day=Decimal("-50.00"),
            ),
            _make_position_greeks(
                position_id=2,
                dollar_delta=Decimal("-3000.00"),
                gamma_dollar=Decimal("80.00"),
                gamma_pnl_1pct=Decimal("0.40"),
                vega_per_1pct=Decimal("150.00"),
                theta_per_day=Decimal("-30.00"),
            ),
        ]

        result = agg.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        assert result.dollar_delta == Decimal("2000.00")
        assert result.gamma_dollar == Decimal("180.00")
        assert result.gamma_pnl_1pct == Decimal("0.90")
        assert result.vega_per_1pct == Decimal("350.00")
        assert result.theta_per_day == Decimal("-80.00")
        assert result.valid_legs_count == 2
        assert result.total_legs_count == 2

    def test_aggregate_with_invalid_positions(self):
        """GreeksAggregator.aggregate() tracks missing_positions for invalid."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        positions = [
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("5000.00"),
                gamma_dollar=Decimal("100.00"),
            ),
            _make_position_greeks(
                position_id=42,
                valid=False,
                dollar_delta=Decimal("10000.00"),
            ),
        ]

        result = agg.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        assert result.dollar_delta == Decimal("5000.00")  # Only valid position
        assert result.valid_legs_count == 1
        assert result.total_legs_count == 2
        assert 42 in result.missing_positions

    def test_aggregate_empty_positions(self):
        """GreeksAggregator.aggregate() handles empty list."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()

        result = agg.aggregate([], scope="ACCOUNT", scope_id="acc_001")

        assert result.has_positions is False
        assert result.dollar_delta == Decimal("0")
        assert result.gamma_dollar == Decimal("0")
        assert result.valid_legs_count == 0
        assert result.total_legs_count == 0
        assert result.coverage_pct == Decimal("100.0")

    def test_aggregate_timestamp_min_max(self):
        """GreeksAggregator.aggregate() sets as_of_ts_min and as_of_ts_max."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        now = datetime.now(timezone.utc)
        ts_old = now - timedelta(seconds=60)
        ts_new = now - timedelta(seconds=10)

        positions = [
            _make_position_greeks(position_id=1, as_of_ts=ts_old),
            _make_position_greeks(position_id=2, as_of_ts=ts_new),
        ]

        result = agg.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        assert result.as_of_ts_min == ts_old
        assert result.as_of_ts_max == ts_new
        # as_of_ts should equal as_of_ts_min per semantic convention
        assert result.as_of_ts == ts_old

    def test_aggregate_high_risk_missing_flag(self):
        """GreeksAggregator.aggregate() sets has_high_risk_missing_legs."""
        from src.greeks.aggregator import GAMMA_HIGH_RISK_THRESHOLD, GreeksAggregator

        agg = GreeksAggregator()
        positions = [
            _make_position_greeks(position_id=1),
            _make_position_greeks(
                position_id=99,
                valid=False,
                gamma_dollar=Decimal(str(GAMMA_HIGH_RISK_THRESHOLD + 100)),
            ),
        ]

        result = agg.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        assert result.has_high_risk_missing_legs is True
        assert 99 in result.missing_positions

    def test_aggregate_warning_legs_count(self):
        """GreeksAggregator.aggregate() counts warning legs."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        positions = [
            _make_position_greeks(position_id=1),
            _make_position_greeks(
                position_id=2,
                quality_warnings=["Staleness warning"],
            ),
            _make_position_greeks(
                position_id=3,
                quality_warnings=["Another warning"],
            ),
        ]

        result = agg.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        assert result.warning_legs_count == 2

    def test_aggregate_coverage_calculation(self):
        """GreeksAggregator.aggregate() calculates coverage correctly."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        positions = [
            _make_position_greeks(
                position_id=1,
                quantity=10,
                underlying_price=Decimal("100.00"),
            ),
            _make_position_greeks(
                position_id=2,
                quantity=10,
                underlying_price=Decimal("100.00"),
                valid=False,
            ),
        ]

        result = agg.aggregate(positions, scope="ACCOUNT", scope_id="acc_001")

        # valid_notional = 10 * 100 * 100 = 100000
        # total_notional = 100000 + 100000 = 200000
        assert result.valid_notional == Decimal("100000.00")
        assert result.total_notional == Decimal("200000.00")
        assert result.coverage_pct == Decimal("50.0")

    def test_aggregate_strategy_scope(self):
        """GreeksAggregator.aggregate() works with STRATEGY scope."""
        from src.greeks.aggregator import GreeksAggregator

        agg = GreeksAggregator()
        pg = _make_position_greeks(position_id=1, strategy_id="momentum_v1")

        result = agg.aggregate([pg], scope="STRATEGY", scope_id="momentum_v1")

        assert result.scope == "STRATEGY"
        assert result.scope_id == "momentum_v1"
