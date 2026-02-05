# backend/tests/api/test_backtest_api.py
"""Integration tests for Backtest API endpoints (T036-T038).

Tests the OpenAPI contract-compliant backtest endpoints:
- POST /api/backtest
- GET /api/backtest/{backtest_id}/attribution

Per backtest-api.yaml contract specifications.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from src.api.backtest import clear_backtest_results, get_backtest_results
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
    num_bars: int = 30,
    base_price: Decimal = Decimal("100"),
) -> list[Bar]:
    """Create a list of test bars for testing.

    Args:
        symbol: Ticker symbol.
        start_date: First bar date.
        num_bars: Number of bars to create.
        base_price: Starting price (bars will have slight upward trend).

    Returns:
        List of Bar objects with trending prices.
    """
    bars = []
    for i in range(num_bars):
        # Handle month/day rollover
        day = start_date.day + i
        month = start_date.month
        year = start_date.year

        # Simple day calculation (ignoring actual month lengths for test)
        while day > 28:
            day -= 28
            month += 1
            if month > 12:
                month = 1
                year += 1

        bar_date = date(year, month, day)

        # Create slightly trending prices
        price_adj = Decimal(i) * Decimal("0.5")
        open_price = base_price + price_adj
        high_price = open_price + Decimal("2")
        low_price = open_price - Decimal("1")
        close_price = open_price + Decimal("1")

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
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=1000000 + i * 10000,  # Increasing volume
            )
        )
    return bars


class TestPostBacktest:
    """Tests for POST /api/backtest endpoint (T036)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear backtest results before each test."""
        clear_backtest_results()
        yield
        clear_backtest_results()

    @pytest.mark.asyncio
    async def test_run_backtest_success(self, client):
        """POST /api/backtest runs successfully with valid request."""
        # Create enough bars for warmup (TrendBreakout needs 20 bars) + backtest
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,  # 20 warmup + 20 backtest
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "universe": "mvp-universe",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                    "initial_capital": "100000",
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure matches OpenAPI contract
        assert "id" in data
        assert data["status"] == "completed"
        assert "metrics" in data
        assert "trades" in data
        assert "attribution_summary" in data
        assert "equity_curve" in data
        assert data["error"] is None

        # Verify metrics structure
        metrics = data["metrics"]
        assert "total_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics
        assert "total_trades" in metrics

        # Verify equity curve structure
        assert isinstance(data["equity_curve"], list)
        if data["equity_curve"]:
            point = data["equity_curve"][0]
            assert "date" in point
            assert "equity" in point

    @pytest.mark.asyncio
    async def test_run_backtest_with_config(self, client):
        """POST /api/backtest accepts strategy configuration for trend_breakout."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=50,  # TrendBreakout needs 20 bar warmup
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "trend_breakout",  # Use trend_breakout which supports config
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-18",
                    "initial_capital": "50000",
                    "config": {
                        "entry_threshold": 0.01,
                        "exit_threshold": -0.01,
                        "position_sizing": "equal_weight",
                        "position_size": 50,
                    },
                },
            )

        assert response.status_code == 200
        data = response.json()
        # If the backtest failed, show the error for debugging
        if data["status"] == "failed":
            raise AssertionError(f"Backtest failed with error: {data.get('error')}")
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_backtest_unknown_strategy(self, client):
        """POST /api/backtest returns 400 for unknown strategy."""
        response = await client.post(
            "/api/backtest",
            json={
                "strategy": "unknown_strategy",
                "start_date": "2025-01-01",
                "end_date": "2025-01-10",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "unknown strategy" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_backtest_missing_required_fields(self, client):
        """POST /api/backtest returns 422 for missing required fields."""
        response = await client.post(
            "/api/backtest",
            json={
                "strategy": "momentum",
                # Missing start_date and end_date
            },
        )

        assert response.status_code == 422  # Pydantic validation error

    @pytest.mark.asyncio
    async def test_run_backtest_invalid_date_range(self, client):
        """POST /api/backtest handles invalid date range gracefully."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=5,  # Very few bars
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-01",
                    "end_date": "2025-01-05",  # Not enough data for warmup
                    "initial_capital": "100000",
                },
            )

        # Should return 400 for insufficient data
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "insufficient" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_run_backtest_stores_result_for_attribution(self, client):
        """POST /api/backtest stores result for attribution retrieval."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        assert response.status_code == 200
        data = response.json()
        backtest_id = data["id"]

        # Verify result was stored
        results = get_backtest_results()
        assert backtest_id in results

    @pytest.mark.asyncio
    async def test_run_backtest_attribution_summary_structure(self, client):
        """POST /api/backtest returns attribution_summary with correct structure."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        assert response.status_code == 200
        data = response.json()

        # Attribution summary should have required fields
        attribution = data["attribution_summary"]
        assert attribution is not None
        assert "momentum_factor" in attribution
        assert "breakout_factor" in attribution
        assert "total" in attribution


class TestGetAttribution:
    """Tests for GET /api/backtest/{backtest_id}/attribution endpoint (T037)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear backtest results before each test."""
        clear_backtest_results()
        yield
        clear_backtest_results()

    @pytest.mark.asyncio
    async def test_get_attribution_success(self, client):
        """GET /api/backtest/{id}/attribution returns attribution data."""
        # First, run a backtest to get an ID
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            backtest_response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        assert backtest_response.status_code == 200
        backtest_id = backtest_response.json()["id"]

        # Now get attribution
        response = await client.get(f"/api/backtest/{backtest_id}/attribution")

        assert response.status_code == 200
        data = response.json()

        # Verify response structure matches OpenAPI contract
        assert data["backtest_id"] == backtest_id
        assert "summary" in data
        assert "by_trade" in data
        assert "by_symbol" in data

        # Verify summary structure
        summary = data["summary"]
        assert "momentum_factor" in summary
        assert "breakout_factor" in summary
        assert "total" in summary

        # Verify by_trade is a list
        assert isinstance(data["by_trade"], list)

        # Verify by_symbol is a dict
        assert isinstance(data["by_symbol"], dict)

    @pytest.mark.asyncio
    async def test_get_attribution_not_found(self, client):
        """GET /api/backtest/{id}/attribution returns 404 for unknown ID."""
        response = await client.get(
            "/api/backtest/00000000-0000-0000-0000-000000000000/attribution"
        )

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_attribution_invalid_uuid(self, client):
        """GET /api/backtest/{id}/attribution handles invalid UUID."""
        response = await client.get("/api/backtest/invalid-id/attribution")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data

    @pytest.mark.asyncio
    async def test_get_attribution_by_trade_structure(self, client):
        """GET attribution returns proper by_trade structure."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            backtest_response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        backtest_id = backtest_response.json()["id"]
        response = await client.get(f"/api/backtest/{backtest_id}/attribution")

        data = response.json()
        by_trade = data["by_trade"]

        # If there are trades, verify structure
        for trade_attr in by_trade:
            assert "trade_id" in trade_attr
            assert "symbol" in trade_attr
            assert "pnl" in trade_attr
            assert "attribution" in trade_attr
            assert isinstance(trade_attr["attribution"], dict)

    @pytest.mark.asyncio
    async def test_get_attribution_by_symbol_structure(self, client):
        """GET attribution returns proper by_symbol structure."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            backtest_response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        backtest_id = backtest_response.json()["id"]
        response = await client.get(f"/api/backtest/{backtest_id}/attribution")

        data = response.json()
        by_symbol = data["by_symbol"]

        # If there are symbol attributions, verify structure
        for symbol, attr in by_symbol.items():
            assert isinstance(symbol, str)
            assert "momentum_factor" in attr
            assert "breakout_factor" in attr
            assert "total" in attr


class TestLegacyBacktestEndpoint:
    """Tests for POST /api/backtest/legacy endpoint (backward compatibility)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear backtest results before each test."""
        clear_backtest_results()
        yield
        clear_backtest_results()

    @pytest.mark.asyncio
    async def test_legacy_endpoint_success(self, client):
        """POST /api/backtest/legacy runs successfully with legacy format."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=15,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest/legacy",
                json={
                    "strategy_class": "src.strategies.examples.momentum.MomentumStrategy",
                    "strategy_params": {
                        "name": "test",
                        "symbols": ["AAPL"],
                        "lookback_period": 3,
                    },
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

        # Verify legacy response structure
        assert "backtest_id" in data
        assert data["status"] == "completed"
        assert "result" in data
        assert data["result"] is not None
        assert "final_equity" in data["result"]
        assert "total_return" in data["result"]
        assert data["error"] is None

    @pytest.mark.asyncio
    async def test_legacy_endpoint_invalid_strategy(self, client):
        """POST /api/backtest/legacy returns 400 for non-allowlist strategy."""
        response = await client.post(
            "/api/backtest/legacy",
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
        assert "allowed" in data["detail"].lower()


class TestTradeResponse:
    """Tests for trade response structure in backtest results."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear backtest results before each test."""
        clear_backtest_results()
        yield
        clear_backtest_results()

    @pytest.mark.asyncio
    async def test_trade_response_structure(self, client):
        """Verify trade response matches OpenAPI Trade schema."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        assert response.status_code == 200
        data = response.json()
        trades = data["trades"]

        # Verify trades is a list
        assert isinstance(trades, list)

        # If there are trades, verify structure matches OpenAPI contract
        for trade in trades:
            assert "id" in trade
            assert "symbol" in trade
            assert "entry_date" in trade
            assert "entry_price" in trade
            # exit_date can be None for open positions
            assert "exit_date" in trade
            # exit_price can be None for open positions
            assert "exit_price" in trade
            assert "quantity" in trade
            # pnl can be None for open positions
            assert "pnl" in trade
            assert "entry_factors" in trade
            assert "exit_factors" in trade
            assert "attribution" in trade

            # entry_factors and attribution should be dicts
            assert isinstance(trade["entry_factors"], dict)
            assert isinstance(trade["exit_factors"], dict)
            assert isinstance(trade["attribution"], dict)


class TestEquityCurveResponse:
    """Tests for equity curve response in backtest results."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Clear backtest results before each test."""
        clear_backtest_results()
        yield
        clear_backtest_results()

    @pytest.mark.asyncio
    async def test_equity_curve_structure(self, client):
        """Verify equity curve matches OpenAPI schema."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        assert response.status_code == 200
        data = response.json()
        equity_curve = data["equity_curve"]

        # Verify equity_curve is a list
        assert isinstance(equity_curve, list)

        # If there are points, verify structure
        for point in equity_curve:
            assert "date" in point
            assert "equity" in point
            # Date should be ISO format string
            assert isinstance(point["date"], str)
            # Equity should be numeric
            assert isinstance(point["equity"], int | float)

    @pytest.mark.asyncio
    async def test_equity_curve_ordering(self, client):
        """Verify equity curve is in chronological order."""
        test_bars = create_test_bars(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            num_bars=40,
        )
        mock_loader = MockBarLoader(test_bars)

        with patch("src.api.backtest.get_bar_loader", return_value=mock_loader):
            response = await client.post(
                "/api/backtest",
                json={
                    "strategy": "momentum",
                    "start_date": "2025-01-25",
                    "end_date": "2025-02-10",
                },
            )

        assert response.status_code == 200
        data = response.json()
        equity_curve = data["equity_curve"]

        # Verify chronological ordering
        if len(equity_curve) > 1:
            dates = [point["date"] for point in equity_curve]
            assert dates == sorted(dates), "Equity curve should be in chronological order"
