"""Tests for trace data models (signal-to-fill audit trail)."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from src.backtest.trace import (
    BarSnapshot,
    PortfolioSnapshot,
    SignalTrace,
    StrategySnapshot,
)


class TestBarSnapshot:
    """Tests for BarSnapshot dataclass."""

    def test_create_bar_snapshot(self) -> None:
        """Create bar snapshot and verify all fields are set correctly."""
        timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        bar = BarSnapshot(
            symbol="AAPL",
            timestamp=timestamp,
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        assert bar.symbol == "AAPL"
        assert bar.timestamp == timestamp
        assert bar.open == Decimal("185.50")
        assert bar.high == Decimal("187.25")
        assert bar.low == Decimal("184.00")
        assert bar.close == Decimal("186.75")
        assert bar.volume == 50_000_000

    def test_bar_snapshot_is_frozen(self) -> None:
        """Verify BarSnapshot is immutable - raises FrozenInstanceError when modifying."""
        bar = BarSnapshot(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        with pytest.raises(AttributeError):
            bar.symbol = "MSFT"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            bar.close = Decimal("200.00")  # type: ignore[misc]


class TestPortfolioSnapshot:
    """Tests for PortfolioSnapshot dataclass."""

    def test_create_portfolio_snapshot(self) -> None:
        """Create portfolio snapshot with position and verify all fields."""
        snapshot = PortfolioSnapshot(
            cash=Decimal("50000.00"),
            position_qty=100,
            position_avg_cost=Decimal("185.50"),
            equity=Decimal("68550.00"),
        )

        assert snapshot.cash == Decimal("50000.00")
        assert snapshot.position_qty == 100
        assert snapshot.position_avg_cost == Decimal("185.50")
        assert snapshot.equity == Decimal("68550.00")

    def test_create_portfolio_snapshot_no_position(self) -> None:
        """Create portfolio snapshot without position (avg_cost is None)."""
        snapshot = PortfolioSnapshot(
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
        )

        assert snapshot.cash == Decimal("100000.00")
        assert snapshot.position_qty == 0
        assert snapshot.position_avg_cost is None
        assert snapshot.equity == Decimal("100000.00")

    def test_portfolio_snapshot_is_frozen(self) -> None:
        """Verify PortfolioSnapshot is immutable."""
        snapshot = PortfolioSnapshot(
            cash=Decimal("50000.00"),
            position_qty=100,
            position_avg_cost=Decimal("185.50"),
            equity=Decimal("68550.00"),
        )

        with pytest.raises(AttributeError):
            snapshot.cash = Decimal("0")  # type: ignore[misc]


class TestStrategySnapshot:
    """Tests for StrategySnapshot dataclass."""

    def test_create_strategy_snapshot(self) -> None:
        """Create strategy snapshot with JSON-serializable values."""
        snapshot = StrategySnapshot(
            strategy_class="MomentumStrategy",
            params={"fast_period": 10, "slow_period": 20, "threshold": 0.05},
            state={"last_signal": "buy", "position_held": True, "bars_since_signal": 5},
        )

        assert snapshot.strategy_class == "MomentumStrategy"
        assert snapshot.params == {"fast_period": 10, "slow_period": 20, "threshold": 0.05}
        assert snapshot.state == {
            "last_signal": "buy",
            "position_held": True,
            "bars_since_signal": 5,
        }

    def test_strategy_snapshot_with_json_scalars(self) -> None:
        """Verify params and state accept all JsonScalar types."""
        snapshot = StrategySnapshot(
            strategy_class="TestStrategy",
            params={
                "string_param": "value",
                "int_param": 42,
                "float_param": 3.14,
                "bool_param": True,
                "null_param": None,
            },
            state={
                "string_state": "active",
                "int_state": 100,
                "float_state": 0.5,
                "bool_state": False,
                "null_state": None,
            },
        )

        # Verify all types are stored correctly
        assert snapshot.params["string_param"] == "value"
        assert snapshot.params["int_param"] == 42
        assert snapshot.params["float_param"] == 3.14
        assert snapshot.params["bool_param"] is True
        assert snapshot.params["null_param"] is None

        assert snapshot.state["string_state"] == "active"
        assert snapshot.state["int_state"] == 100
        assert snapshot.state["float_state"] == 0.5
        assert snapshot.state["bool_state"] is False
        assert snapshot.state["null_state"] is None

    def test_strategy_snapshot_is_frozen(self) -> None:
        """Verify StrategySnapshot is immutable."""
        snapshot = StrategySnapshot(
            strategy_class="TestStrategy",
            params={"p": 1},
            state={"s": 2},
        )

        with pytest.raises(AttributeError):
            snapshot.strategy_class = "Other"  # type: ignore[misc]


class TestSignalTrace:
    """Tests for SignalTrace dataclass."""

    def test_create_minimal_signal_trace(self) -> None:
        """Create signal trace without fill data (order not yet filled)."""
        signal_timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        signal_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=signal_timestamp,
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )
        portfolio = PortfolioSnapshot(
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
        )

        trace = SignalTrace(
            trace_id="trace-001",
            signal_timestamp=signal_timestamp,
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason="Momentum crossover detected",
            signal_bar=signal_bar,
            portfolio_state=portfolio,
            strategy_snapshot=None,
            fill_bar=None,
            fill_timestamp=None,
            fill_quantity=None,
            fill_price=None,
            expected_price=None,
            expected_price_type=None,
            slippage=None,
            slippage_bps=None,
            commission=None,
        )

        assert trace.trace_id == "trace-001"
        assert trace.signal_timestamp == signal_timestamp
        assert trace.symbol == "AAPL"
        assert trace.signal_direction == "buy"
        assert trace.signal_quantity == 100
        assert trace.signal_reason == "Momentum crossover detected"
        assert trace.signal_bar == signal_bar
        assert trace.portfolio_state == portfolio
        assert trace.strategy_snapshot is None
        assert trace.fill_bar is None
        assert trace.fill_timestamp is None
        assert trace.fill_quantity is None
        assert trace.fill_price is None
        assert trace.expected_price is None
        assert trace.expected_price_type is None
        assert trace.slippage is None
        assert trace.slippage_bps is None
        assert trace.commission is None

    def test_create_signal_trace_with_fill_data(self) -> None:
        """Create signal trace with complete fill data and slippage analysis."""
        signal_timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        fill_timestamp = datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc)

        signal_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=signal_timestamp,
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        fill_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=fill_timestamp,
            open=Decimal("187.00"),
            high=Decimal("188.50"),
            low=Decimal("186.50"),
            close=Decimal("188.00"),
            volume=45_000_000,
        )

        portfolio = PortfolioSnapshot(
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
        )

        strategy = StrategySnapshot(
            strategy_class="MomentumStrategy",
            params={"fast_period": 10, "slow_period": 20},
            state={"signal_count": 5},
        )

        trace = SignalTrace(
            trace_id="trace-002",
            signal_timestamp=signal_timestamp,
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            signal_bar=signal_bar,
            portfolio_state=portfolio,
            strategy_snapshot=strategy,
            fill_bar=fill_bar,
            fill_timestamp=fill_timestamp,
            fill_quantity=100,
            fill_price=Decimal("187.10"),
            expected_price=Decimal("187.00"),
            expected_price_type="next_bar_open",
            slippage=Decimal("0.10"),
            slippage_bps=Decimal("5.35"),
            commission=Decimal("0.50"),
        )

        assert trace.trace_id == "trace-002"
        assert trace.signal_timestamp == signal_timestamp
        assert trace.symbol == "AAPL"
        assert trace.signal_direction == "buy"
        assert trace.signal_quantity == 100
        assert trace.signal_reason is None
        assert trace.signal_bar == signal_bar
        assert trace.portfolio_state == portfolio
        assert trace.strategy_snapshot == strategy
        assert trace.fill_bar == fill_bar
        assert trace.fill_timestamp == fill_timestamp
        assert trace.fill_quantity == 100
        assert trace.fill_price == Decimal("187.10")
        assert trace.expected_price == Decimal("187.00")
        assert trace.expected_price_type == "next_bar_open"
        assert trace.slippage == Decimal("0.10")
        assert trace.slippage_bps == Decimal("5.35")
        assert trace.commission == Decimal("0.50")

    def test_signal_trace_sell_direction(self) -> None:
        """Create signal trace for a sell order."""
        signal_timestamp = datetime(2024, 1, 20, 16, 0, 0, tzinfo=timezone.utc)
        signal_bar = BarSnapshot(
            symbol="MSFT",
            timestamp=signal_timestamp,
            open=Decimal("400.00"),
            high=Decimal("405.00"),
            low=Decimal("398.00"),
            close=Decimal("402.00"),
            volume=30_000_000,
        )
        portfolio = PortfolioSnapshot(
            cash=Decimal("60000.00"),
            position_qty=100,
            position_avg_cost=Decimal("390.00"),
            equity=Decimal("100200.00"),
        )

        trace = SignalTrace(
            trace_id="trace-003",
            signal_timestamp=signal_timestamp,
            symbol="MSFT",
            signal_direction="sell",
            signal_quantity=50,
            signal_reason="Profit target reached",
            signal_bar=signal_bar,
            portfolio_state=portfolio,
            strategy_snapshot=None,
            fill_bar=None,
            fill_timestamp=None,
            fill_quantity=None,
            fill_price=None,
            expected_price=None,
            expected_price_type=None,
            slippage=None,
            slippage_bps=None,
            commission=None,
        )

        assert trace.signal_direction == "sell"
        assert trace.signal_quantity == 50

    def test_signal_trace_is_frozen(self) -> None:
        """Verify SignalTrace is immutable."""
        signal_timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        signal_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=signal_timestamp,
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )
        portfolio = PortfolioSnapshot(
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
        )

        trace = SignalTrace(
            trace_id="trace-001",
            signal_timestamp=signal_timestamp,
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            signal_bar=signal_bar,
            portfolio_state=portfolio,
            strategy_snapshot=None,
            fill_bar=None,
            fill_timestamp=None,
            fill_quantity=None,
            fill_price=None,
            expected_price=None,
            expected_price_type=None,
            slippage=None,
            slippage_bps=None,
            commission=None,
        )

        with pytest.raises(AttributeError):
            trace.trace_id = "new-id"  # type: ignore[misc]

    def test_signal_trace_expected_price_types(self) -> None:
        """Verify all expected_price_type literals are accepted."""
        signal_timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        signal_bar = BarSnapshot(
            symbol="AAPL",
            timestamp=signal_timestamp,
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )
        portfolio = PortfolioSnapshot(
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
        )

        price_types = ["next_bar_open", "signal_bar_close", "mid_quote", "limit_price"]

        for price_type in price_types:
            trace = SignalTrace(
                trace_id=f"trace-{price_type}",
                signal_timestamp=signal_timestamp,
                symbol="AAPL",
                signal_direction="buy",
                signal_quantity=100,
                signal_reason=None,
                signal_bar=signal_bar,
                portfolio_state=portfolio,
                strategy_snapshot=None,
                fill_bar=None,
                fill_timestamp=None,
                fill_quantity=None,
                fill_price=Decimal("187.00"),
                expected_price=Decimal("186.75"),
                expected_price_type=price_type,  # type: ignore[arg-type]
                slippage=Decimal("0.25"),
                slippage_bps=Decimal("13.4"),
                commission=None,
            )
            assert trace.expected_price_type == price_type
