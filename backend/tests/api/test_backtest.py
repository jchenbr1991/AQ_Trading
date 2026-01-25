# backend/tests/api/test_backtest.py
"""Tests for Backtest API endpoints."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from src.backtest.models import Bar


class MockBarLoader:
    """Mock bar loader for testing."""

    def __init__(self, bars: list[Bar] | None = None):
        self._bars = bars or []

    async def load(self, symbol: str, start_date: date, end_date: date) -> list[Bar]:
        """Return pre-configured bars filtered by date range."""
        return [
            b
            for b in self._bars
            if b.symbol == symbol and start_date <= b.timestamp.date() <= end_date
        ]


def create_test_bars(
    symbol: str = "AAPL",
    start_date: date = date(2025, 1, 1),
    num_bars: int = 10,
) -> list[Bar]:
    """Create a list of test bars for testing."""
    bars = []
    for i in range(num_bars):
        bar_date = date(
            start_date.year,
            start_date.month,
            start_date.day + i,
        )
        bars.append(
            Bar(
                symbol=symbol,
                timestamp=datetime(
                    bar_date.year,
                    bar_date.month,
                    bar_date.day,
                    16,
                    0,
                    0,
                    tzinfo=timezone.utc,
                ),
                open=Decimal("100") + Decimal(i),
                high=Decimal("105") + Decimal(i),
                low=Decimal("95") + Decimal(i),
                close=Decimal("102") + Decimal(i),
                volume=1000000,
            )
        )
    return bars


class TestRunBacktest:
    """Tests for POST /api/backtest endpoint."""

    @pytest.mark.asyncio
    async def test_run_backtest_success(self, client):
        """POST /api/backtest runs successfully with valid request."""
        # Create enough bars for warmup (momentum requires lookback_period) + backtest period
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=15,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy_class": "src.strategies.examples.momentum.MomentumStrategy",
                    "strategy_params": {"name": "test", "symbols": ["AAPL"], "lookback_period": 3},
                    "symbol": "AAPL",
                    "start_date": "2025-01-06",
                    "end_date": "2025-01-14",
                    "initial_capital": "100000",
                    "slippage_bps": 5,
                    "commission_per_share": "0.005",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert "backtest_id" in data
        assert data["result"] is not None
        assert "final_equity" in data["result"]
        assert "total_return" in data["result"]
        assert "sharpe_ratio" in data["result"]
        assert "max_drawdown" in data["result"]
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_run_backtest_invalid_strategy(self, client):
        """POST /api/backtest returns 400 for non-allowlist strategy."""
        response = await client.post(
            "/api/backtest",
            json={
                "strategy_class": "malicious.module.BadStrategy",
                "strategy_params": {},
                "symbol": "AAPL",
                "start_date": "2025-01-01",
                "end_date": "2025-01-10",
                "initial_capital": "100000",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert (
            "not in allowed prefix" in data["detail"].lower() or "allowed" in data["detail"].lower()
        )

    @pytest.mark.asyncio
    async def test_run_backtest_insufficient_data(self, client):
        """POST /api/backtest returns 400 when not enough data for warmup."""
        # Create only 2 bars - not enough for warmup
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=2,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy_class": "src.strategies.examples.momentum.MomentumStrategy",
                    "strategy_params": {"name": "test", "symbols": ["AAPL"], "lookback_period": 5},
                    "symbol": "AAPL",
                    "start_date": "2025-01-02",
                    "end_date": "2025-01-02",
                    "initial_capital": "100000",
                },
            )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "insufficient" in data["detail"].lower()


class TestBacktestSchemas:
    """Tests for Backtest API schemas."""

    def test_backtest_request_accepts_benchmark_symbol(self):
        """BacktestRequest accepts optional benchmark_symbol."""
        from src.api.backtest import BacktestRequest

        request = BacktestRequest(
            strategy_class="test.Strategy",
            strategy_params={},
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_capital="100000",
            benchmark_symbol="SPY",
        )
        assert request.benchmark_symbol == "SPY"

    def test_backtest_request_benchmark_symbol_defaults_to_none(self):
        """BacktestRequest benchmark_symbol defaults to None."""
        from src.api.backtest import BacktestRequest

        request = BacktestRequest(
            strategy_class="test.Strategy",
            strategy_params={},
            symbol="AAPL",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_capital="100000",
        )
        assert request.benchmark_symbol is None

    def test_benchmark_comparison_response_schema(self):
        """BenchmarkComparisonResponse schema is valid."""
        from src.api.backtest import BenchmarkComparisonResponse

        response = BenchmarkComparisonResponse(
            benchmark_symbol="SPY",
            benchmark_total_return="0.10",
            alpha="0.05",
            beta="0.8",
            tracking_error="0.02",
            information_ratio="2.5",
            sortino_ratio="1.8",
            up_capture="1.1",
            down_capture="0.9",
        )
        assert response.benchmark_symbol == "SPY"
        assert response.alpha == "0.05"
        assert response.beta == "0.8"
        assert response.tracking_error == "0.02"
        assert response.information_ratio == "2.5"
        assert response.sortino_ratio == "1.8"
        assert response.up_capture == "1.1"
        assert response.down_capture == "0.9"

    def test_backtest_response_includes_benchmark_field(self):
        """BacktestResponse includes optional benchmark field."""
        from src.api.backtest import (
            BacktestResponse,
            BacktestResultSchema,
            BenchmarkComparisonResponse,
        )

        benchmark = BenchmarkComparisonResponse(
            benchmark_symbol="SPY",
            benchmark_total_return="0.10",
            alpha="0.05",
            beta="0.8",
            tracking_error="0.02",
            information_ratio="2.5",
            sortino_ratio="1.8",
            up_capture="1.1",
            down_capture="0.9",
        )

        result = BacktestResultSchema(
            final_equity="100000",
            final_cash="50000",
            final_position_qty=100,
            total_return="0.10",
            annualized_return="0.12",
            sharpe_ratio="1.5",
            max_drawdown="0.05",
            win_rate="0.6",
            total_trades=10,
            avg_trade_pnl="100",
            warm_up_required_bars=5,
            warm_up_bars_used=5,
        )

        response = BacktestResponse(
            backtest_id="test-id",
            status="completed",
            result=result,
            benchmark=benchmark,
        )
        assert response.benchmark is not None
        assert response.benchmark.benchmark_symbol == "SPY"

    def test_backtest_response_benchmark_defaults_to_none(self):
        """BacktestResponse benchmark defaults to None."""
        from src.api.backtest import BacktestResponse

        response = BacktestResponse(
            backtest_id="test-id",
            status="completed",
            result=None,
        )
        assert response.benchmark is None

    def test_signal_trace_response_schema(self):
        """SignalTraceResponse schema is valid with all fields."""
        from src.api.backtest import (
            BarSnapshotResponse,
            PortfolioSnapshotResponse,
            SignalTraceResponse,
            StrategySnapshotResponse,
        )

        signal_bar = BarSnapshotResponse(
            symbol="AAPL",
            timestamp="2025-01-15T16:00:00+00:00",
            open="150.00",
            high="152.00",
            low="149.00",
            close="151.50",
            volume=1000000,
        )

        fill_bar = BarSnapshotResponse(
            symbol="AAPL",
            timestamp="2025-01-16T16:00:00+00:00",
            open="151.75",
            high="153.00",
            low="150.50",
            close="152.00",
            volume=1200000,
        )

        portfolio_state = PortfolioSnapshotResponse(
            cash="100000.00",
            position_qty=0,
            position_avg_cost=None,
            equity="100000.00",
        )

        strategy_snapshot = StrategySnapshotResponse(
            strategy_class="src.strategies.examples.momentum.MomentumStrategy",
            params={"lookback_period": 5, "threshold": 0.02},
            state={"momentum": 0.015, "signal_count": 3},
        )

        trace = SignalTraceResponse(
            trace_id="trace-123",
            signal_timestamp="2025-01-15T16:00:00+00:00",
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason="Momentum signal triggered",
            signal_bar=signal_bar,
            portfolio_state=portfolio_state,
            strategy_snapshot=strategy_snapshot,
            fill_bar=fill_bar,
            fill_timestamp="2025-01-16T09:30:00+00:00",
            fill_quantity=100,
            fill_price="151.83",
            expected_price="151.75",
            expected_price_type="next_bar_open",
            slippage="0.08",
            slippage_bps="5.27",
            commission="0.50",
        )

        # Verify all fields are set correctly
        assert trace.trace_id == "trace-123"
        assert trace.signal_timestamp == "2025-01-15T16:00:00+00:00"
        assert trace.symbol == "AAPL"
        assert trace.signal_direction == "buy"
        assert trace.signal_quantity == 100
        assert trace.signal_reason == "Momentum signal triggered"
        assert trace.signal_bar.symbol == "AAPL"
        assert trace.signal_bar.close == "151.50"
        assert trace.portfolio_state.cash == "100000.00"
        assert trace.portfolio_state.position_qty == 0
        assert trace.strategy_snapshot is not None
        assert (
            trace.strategy_snapshot.strategy_class
            == "src.strategies.examples.momentum.MomentumStrategy"
        )
        assert trace.strategy_snapshot.params["lookback_period"] == 5
        assert trace.fill_bar is not None
        assert trace.fill_bar.open == "151.75"
        assert trace.fill_timestamp == "2025-01-16T09:30:00+00:00"
        assert trace.fill_quantity == 100
        assert trace.fill_price == "151.83"
        assert trace.expected_price == "151.75"
        assert trace.expected_price_type == "next_bar_open"
        assert trace.slippage == "0.08"
        assert trace.slippage_bps == "5.27"
        assert trace.commission == "0.50"

    def test_signal_trace_response_with_optional_none_values(self):
        """SignalTraceResponse handles None optional fields correctly."""
        from src.api.backtest import (
            BarSnapshotResponse,
            PortfolioSnapshotResponse,
            SignalTraceResponse,
        )

        signal_bar = BarSnapshotResponse(
            symbol="AAPL",
            timestamp="2025-01-15T16:00:00+00:00",
            open="150.00",
            high="152.00",
            low="149.00",
            close="151.50",
            volume=1000000,
        )

        portfolio_state = PortfolioSnapshotResponse(
            cash="100000.00",
            position_qty=0,
            position_avg_cost=None,
            equity="100000.00",
        )

        # Create trace with unfilled order (all fill fields None)
        trace = SignalTraceResponse(
            trace_id="trace-456",
            signal_timestamp="2025-01-15T16:00:00+00:00",
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            signal_bar=signal_bar,
            portfolio_state=portfolio_state,
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

        assert trace.signal_reason is None
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

    def test_backtest_response_includes_traces(self):
        """BacktestResponse includes traces field."""
        from src.api.backtest import (
            BacktestResponse,
            BacktestResultSchema,
            BarSnapshotResponse,
            PortfolioSnapshotResponse,
            SignalTraceResponse,
        )

        signal_bar = BarSnapshotResponse(
            symbol="AAPL",
            timestamp="2025-01-15T16:00:00+00:00",
            open="150.00",
            high="152.00",
            low="149.00",
            close="151.50",
            volume=1000000,
        )

        portfolio_state = PortfolioSnapshotResponse(
            cash="100000.00",
            position_qty=0,
            position_avg_cost=None,
            equity="100000.00",
        )

        trace = SignalTraceResponse(
            trace_id="trace-789",
            signal_timestamp="2025-01-15T16:00:00+00:00",
            symbol="AAPL",
            signal_direction="buy",
            signal_quantity=100,
            signal_reason=None,
            signal_bar=signal_bar,
            portfolio_state=portfolio_state,
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

        result = BacktestResultSchema(
            final_equity="100000",
            final_cash="50000",
            final_position_qty=100,
            total_return="0.10",
            annualized_return="0.12",
            sharpe_ratio="1.5",
            max_drawdown="0.05",
            win_rate="0.6",
            total_trades=10,
            avg_trade_pnl="100",
            warm_up_required_bars=5,
            warm_up_bars_used=5,
        )

        response = BacktestResponse(
            backtest_id="test-id",
            status="completed",
            result=result,
            traces=[trace],
        )

        assert len(response.traces) == 1
        assert response.traces[0].trace_id == "trace-789"
        assert response.traces[0].symbol == "AAPL"

    def test_backtest_response_traces_defaults_to_empty_list(self):
        """BacktestResponse traces defaults to empty list."""
        from src.api.backtest import BacktestResponse

        response = BacktestResponse(
            backtest_id="test-id",
            status="completed",
            result=None,
        )

        assert response.traces == []
