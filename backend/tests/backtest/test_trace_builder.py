"""Tests for TraceBuilder (signal trace construction)."""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.models import Bar
from src.backtest.trace import StrategySnapshot
from src.backtest.trace_builder import TraceBuilder


class TestCreatePendingTrace:
    """Tests for TraceBuilder.create_pending()."""

    def test_create_pending_trace(self) -> None:
        """Create pending trace with signal info, fill fields are None."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        strategy_snapshot = StrategySnapshot(
            strategy_class="MomentumStrategy",
            params={"fast_period": 10, "slow_period": 20},
            state={"signal_count": 5},
        )

        trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason="Momentum crossover detected",
            cash=Decimal("50000.00"),
            position_qty=50,
            position_avg_cost=Decimal("180.00"),
            equity=Decimal("59337.50"),
            strategy_snapshot=strategy_snapshot,
        )

        # Verify trace_id is a valid UUID string
        assert trace.trace_id is not None
        assert len(trace.trace_id) == 36  # UUID format: 8-4-4-4-12

        # Verify signal data
        assert trace.signal_timestamp == signal_bar.timestamp
        assert trace.symbol == "AAPL"
        assert trace.signal_direction == "buy"
        assert trace.signal_quantity == 100
        assert trace.signal_reason == "Momentum crossover detected"

        # Verify bar snapshot was created correctly
        assert trace.signal_bar.symbol == "AAPL"
        assert trace.signal_bar.timestamp == signal_bar.timestamp
        assert trace.signal_bar.open == Decimal("185.00")
        assert trace.signal_bar.high == Decimal("187.25")
        assert trace.signal_bar.low == Decimal("184.00")
        assert trace.signal_bar.close == Decimal("186.75")
        assert trace.signal_bar.volume == 50_000_000

        # Verify portfolio snapshot was created correctly
        assert trace.portfolio_state.cash == Decimal("50000.00")
        assert trace.portfolio_state.position_qty == 50
        assert trace.portfolio_state.position_avg_cost == Decimal("180.00")
        assert trace.portfolio_state.equity == Decimal("59337.50")

        # Verify strategy snapshot is preserved
        assert trace.strategy_snapshot == strategy_snapshot

        # Verify all fill fields are None
        assert trace.fill_bar is None
        assert trace.fill_timestamp is None
        assert trace.fill_quantity is None
        assert trace.fill_price is None
        assert trace.expected_price is None
        assert trace.expected_price_type is None
        assert trace.slippage is None
        assert trace.slippage_bps is None
        assert trace.commission is None

    def test_create_pending_trace_without_strategy_snapshot(self) -> None:
        """Create pending trace without strategy snapshot (None)."""
        signal_bar = Bar(
            symbol="MSFT",
            timestamp=datetime(2024, 1, 20, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("400.00"),
            high=Decimal("405.00"),
            low=Decimal("398.00"),
            close=Decimal("402.00"),
            volume=30_000_000,
        )

        trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="sell",
            signal_quantity=50,
            signal_reason=None,
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
            strategy_snapshot=None,
        )

        assert trace.strategy_snapshot is None
        assert trace.signal_reason is None
        assert trace.portfolio_state.position_avg_cost is None


class TestCompleteTrace:
    """Tests for TraceBuilder.complete()."""

    def test_complete_trace_with_fill(self) -> None:
        """Complete pending trace with fill data and slippage calculation."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason="Momentum crossover",
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
            strategy_snapshot=None,
        )

        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("187.00"),
            high=Decimal("188.50"),
            low=Decimal("186.50"),
            close=Decimal("188.00"),
            volume=45_000_000,
        )

        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=fill_bar,
            fill_price=Decimal("187.10"),
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        # Verify trace_id is preserved
        assert completed_trace.trace_id == pending_trace.trace_id

        # Verify signal data is preserved
        assert completed_trace.signal_timestamp == pending_trace.signal_timestamp
        assert completed_trace.symbol == pending_trace.symbol
        assert completed_trace.signal_direction == pending_trace.signal_direction
        assert completed_trace.signal_quantity == pending_trace.signal_quantity
        assert completed_trace.signal_reason == pending_trace.signal_reason
        assert completed_trace.signal_bar == pending_trace.signal_bar
        assert completed_trace.portfolio_state == pending_trace.portfolio_state

        # Verify fill data
        assert completed_trace.fill_bar is not None
        assert completed_trace.fill_bar.symbol == "AAPL"
        assert completed_trace.fill_bar.open == Decimal("187.00")
        assert completed_trace.fill_timestamp == fill_bar.timestamp
        assert completed_trace.fill_quantity == 100
        assert completed_trace.fill_price == Decimal("187.10")
        assert completed_trace.commission == Decimal("0.50")

        # Verify slippage calculation (next_bar_open model)
        assert completed_trace.expected_price == Decimal("187.00")
        assert completed_trace.expected_price_type == "next_bar_open"
        assert completed_trace.slippage == Decimal("0.10")
        # slippage_bps = (0.10 / 187.00) * 10000 = 5.347... -> 5.35 (ROUND_HALF_UP)
        assert completed_trace.slippage_bps == Decimal("5.35")

    def test_slippage_bps_calculation(self) -> None:
        """Verify BPS formula with various values."""
        signal_bar = Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.50"),
            volume=1_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("10000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("10000.00"),
            strategy_snapshot=None,
        )

        fill_bar = Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.00"),  # expected_price
            high=Decimal("102.00"),
            low=Decimal("99.50"),
            close=Decimal("101.00"),
            volume=1_200_000,
        )

        # Test case: fill_price = 100.50, expected = 100.00
        # slippage = 0.50
        # slippage_bps = (0.50 / 100.00) * 10000 = 50.00
        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=fill_bar,
            fill_price=Decimal("100.50"),
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        assert completed_trace.slippage == Decimal("0.50")
        assert completed_trace.slippage_bps == Decimal("50.00")

    def test_negative_slippage(self) -> None:
        """Verify negative slippage when fill_price < expected_price."""
        signal_bar = Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.50"),
            volume=1_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("10000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("10000.00"),
            strategy_snapshot=None,
        )

        fill_bar = Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.00"),  # expected_price
            high=Decimal("102.00"),
            low=Decimal("99.50"),
            close=Decimal("101.00"),
            volume=1_200_000,
        )

        # fill_price < expected_price -> negative slippage (favorable for buy)
        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=fill_bar,
            fill_price=Decimal("99.50"),
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        assert completed_trace.slippage == Decimal("-0.50")
        assert completed_trace.slippage_bps == Decimal("-50.00")

    def test_missing_data_slippage_is_none(self) -> None:
        """Missing data returns None for slippage, not 0."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
            strategy_snapshot=None,
        )

        # Test case 1: No fill_bar (order not filled)
        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=None,
            fill_price=None,
            fill_quantity=None,
            commission=None,
        )

        assert completed_trace.fill_bar is None
        assert completed_trace.fill_price is None
        assert completed_trace.expected_price is None
        assert completed_trace.expected_price_type is None
        assert completed_trace.slippage is None
        assert completed_trace.slippage_bps is None

    def test_fill_price_none_slippage_is_none(self) -> None:
        """If fill_price is None, slippage should be None."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
            strategy_snapshot=None,
        )

        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("187.00"),
            high=Decimal("188.50"),
            low=Decimal("186.50"),
            close=Decimal("188.00"),
            volume=45_000_000,
        )

        # fill_bar present but fill_price is None
        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=fill_bar,
            fill_price=None,
            fill_quantity=None,
            commission=None,
        )

        assert completed_trace.fill_bar is not None
        assert completed_trace.expected_price == Decimal("187.00")
        assert completed_trace.expected_price_type == "next_bar_open"
        assert completed_trace.slippage is None
        assert completed_trace.slippage_bps is None

    def test_zero_expected_price_slippage_is_none(self) -> None:
        """If expected_price is 0, slippage should be None (avoid division by zero)."""
        signal_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.00"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("100000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("100000.00"),
            strategy_snapshot=None,
        )

        # Edge case: fill_bar with open = 0 (should not happen in practice)
        fill_bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("0"),
            high=Decimal("188.50"),
            low=Decimal("186.50"),
            close=Decimal("188.00"),
            volume=45_000_000,
        )

        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=fill_bar,
            fill_price=Decimal("187.10"),
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        assert completed_trace.expected_price == Decimal("0")
        assert completed_trace.slippage is None
        assert completed_trace.slippage_bps is None

    def test_slippage_bps_rounding(self) -> None:
        """Verify slippage_bps is rounded with ROUND_HALF_UP."""
        signal_bar = Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("100.00"),
            high=Decimal("101.00"),
            low=Decimal("99.00"),
            close=Decimal("100.50"),
            volume=1_000_000,
        )

        pending_trace = TraceBuilder.create_pending(
            signal_bar=signal_bar,
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            cash=Decimal("10000.00"),
            position_qty=0,
            position_avg_cost=None,
            equity=Decimal("10000.00"),
            strategy_snapshot=None,
        )

        fill_bar = Bar(
            symbol="TEST",
            timestamp=datetime(2024, 1, 16, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("187.00"),
            high=Decimal("188.00"),
            low=Decimal("186.00"),
            close=Decimal("187.50"),
            volume=1_200_000,
        )

        # slippage = 0.10
        # slippage_bps = (0.10 / 187.00) * 10000 = 5.347593... -> 5.35 (ROUND_HALF_UP)
        completed_trace = TraceBuilder.complete(
            pending_trace=pending_trace,
            fill_bar=fill_bar,
            fill_price=Decimal("187.10"),
            fill_quantity=100,
            commission=Decimal("0.50"),
        )

        assert completed_trace.slippage == Decimal("0.10")
        assert completed_trace.slippage_bps == Decimal("5.35")
