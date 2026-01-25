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
