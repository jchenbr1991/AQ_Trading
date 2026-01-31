"""Tests for Greeks V2 API endpoints.

Tests cover:
- GET /api/greeks/accounts/{account_id}/scenario
- PUT /api/greeks/accounts/{account_id}/limits
- GET /api/greeks/accounts/{account_id}/history
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from src.greeks.models import AggregatedGreeks


def _make_aggregated_greeks(
    account_id: str = "acc_001",
    dollar_delta: Decimal = Decimal("50000"),
    gamma_dollar: Decimal = Decimal("2000"),
    gamma_pnl_1pct: Decimal = Decimal("100"),
    vega_per_1pct: Decimal = Decimal("15000"),
    theta_per_day: Decimal = Decimal("-2800"),
) -> AggregatedGreeks:
    """Factory for AggregatedGreeks."""
    return AggregatedGreeks(
        scope="ACCOUNT",
        scope_id=account_id,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        valid_legs_count=5,
        total_legs_count=5,
        valid_notional=Decimal("100000"),
        total_notional=Decimal("100000"),
        as_of_ts=datetime.now(timezone.utc),
        as_of_ts_min=datetime.now(timezone.utc),
    )


class TestScenarioEndpoint:
    """Tests for GET /api/greeks/accounts/{account_id}/scenario."""

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        from src.main import app

        return TestClient(app)

    @pytest.mark.asyncio
    async def test_scenario_endpoint_returns_scenarios(self, client):
        """GET /scenario returns scenario shocks."""
        with (
            patch("src.api.greeks.load_positions_from_db") as mock_load,
            patch("src.api.greeks.GreeksCalculator") as mock_calc_cls,
            patch("src.api.greeks.GreeksAggregator") as mock_agg_cls,
        ):
            # Setup mocks
            mock_load.return_value = [MagicMock()]  # Has positions

            mock_calc = MagicMock()
            mock_calc.calculate.return_value = [MagicMock()]
            mock_calc_cls.return_value = mock_calc

            mock_agg = MagicMock()
            mock_agg.aggregate.return_value = _make_aggregated_greeks()
            mock_agg_cls.return_value = mock_agg

            response = client.get("/api/greeks/accounts/acc_001/scenario")

            assert response.status_code == 200
            data = response.json()

            # Should have standard scenarios
            assert "scenarios" in data
            assert "+1%" in data["scenarios"]
            assert "-1%" in data["scenarios"]
            assert "+2%" in data["scenarios"]
            assert "-2%" in data["scenarios"]

    @pytest.mark.asyncio
    async def test_scenario_endpoint_returns_current_greeks(self, client):
        """GET /scenario returns current Greeks snapshot."""
        with (
            patch("src.api.greeks.load_positions_from_db") as mock_load,
            patch("src.api.greeks.GreeksCalculator") as mock_calc_cls,
            patch("src.api.greeks.GreeksAggregator") as mock_agg_cls,
        ):
            mock_load.return_value = [MagicMock()]

            mock_calc = MagicMock()
            mock_calc.calculate.return_value = [MagicMock()]
            mock_calc_cls.return_value = mock_calc

            mock_agg = MagicMock()
            mock_agg.aggregate.return_value = _make_aggregated_greeks(dollar_delta=Decimal("50000"))
            mock_agg_cls.return_value = mock_agg

            response = client.get("/api/greeks/accounts/acc_001/scenario")

            assert response.status_code == 200
            data = response.json()

            assert "current" in data
            assert data["current"]["dollar_delta"] == 50000

    @pytest.mark.asyncio
    async def test_scenario_endpoint_custom_shocks(self, client):
        """GET /scenario?shocks=1,3 returns custom shock percentages."""
        with (
            patch("src.api.greeks.load_positions_from_db") as mock_load,
            patch("src.api.greeks.GreeksCalculator") as mock_calc_cls,
            patch("src.api.greeks.GreeksAggregator") as mock_agg_cls,
        ):
            mock_load.return_value = [MagicMock()]

            mock_calc = MagicMock()
            mock_calc.calculate.return_value = [MagicMock()]
            mock_calc_cls.return_value = mock_calc

            mock_agg = MagicMock()
            mock_agg.aggregate.return_value = _make_aggregated_greeks()
            mock_agg_cls.return_value = mock_agg

            response = client.get("/api/greeks/accounts/acc_001/scenario?shocks=1,3")

            assert response.status_code == 200
            data = response.json()

            assert "+1%" in data["scenarios"]
            assert "+3%" in data["scenarios"]
            assert "+2%" not in data["scenarios"]

    @pytest.mark.asyncio
    async def test_scenario_endpoint_no_positions(self, client):
        """GET /scenario with no positions returns 404."""
        with patch("src.api.greeks.load_positions_from_db") as mock_load:
            mock_load.return_value = []

            response = client.get("/api/greeks/accounts/acc_001/scenario")

            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_scenario_endpoint_scope_filter(self, client):
        """GET /scenario?scope=STRATEGY requires strategy_id."""
        with patch("src.api.greeks.load_positions_from_db") as mock_load:
            mock_load.return_value = [MagicMock()]

            response = client.get("/api/greeks/accounts/acc_001/scenario?scope=STRATEGY")

            # Should return 400 if strategy_id not provided
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_scenario_response_structure(self, client):
        """GET /scenario response matches ScenarioShockResponse schema."""
        with (
            patch("src.api.greeks.load_positions_from_db") as mock_load,
            patch("src.api.greeks.GreeksCalculator") as mock_calc_cls,
            patch("src.api.greeks.GreeksAggregator") as mock_agg_cls,
        ):
            mock_load.return_value = [MagicMock()]

            mock_calc = MagicMock()
            mock_calc.calculate.return_value = [MagicMock()]
            mock_calc_cls.return_value = mock_calc

            mock_agg = MagicMock()
            mock_agg.aggregate.return_value = _make_aggregated_greeks()
            mock_agg_cls.return_value = mock_agg

            response = client.get("/api/greeks/accounts/acc_001/scenario")

            assert response.status_code == 200
            data = response.json()

            # Check response structure
            assert "account_id" in data
            assert "scope" in data
            assert "asof_ts" in data
            assert "current" in data
            assert "scenarios" in data

            # Check scenario result structure
            scenario = data["scenarios"]["+1%"]
            assert "shock_pct" in scenario
            assert "direction" in scenario
            assert "pnl_from_delta" in scenario
            assert "pnl_from_gamma" in scenario
            assert "pnl_impact" in scenario
            assert "delta_change" in scenario
            assert "new_dollar_delta" in scenario
            assert "breach_level" in scenario

    @pytest.fixture(autouse=True)
    def reset_limits_store(self):
        """Reset the limits store before each test."""
        import src.greeks.limits_store as limits_module

        limits_module._limits_store = None
        yield
        limits_module._limits_store = None

    @pytest.mark.asyncio
    async def test_scenario_uses_account_limits_from_store(self, client):
        """GET /scenario uses limits from limits_store, not hardcoded values."""
        # First, set low limits for the account
        client.put(
            "/api/greeks/accounts/acc_001/limits",
            json={
                "limits": {
                    "dollar_delta": {"warn": 10000, "crit": 20000, "hard": 30000},
                    "gamma_dollar": {"warn": 500, "crit": 1000, "hard": 1500},
                    "vega_per_1pct": {"warn": 5000, "crit": 10000, "hard": 15000},
                    "theta_per_day": {"warn": 1000, "crit": 2000, "hard": 3000},
                }
            },
            headers={"X-User-ID": "test_user"},
        )

        with (
            patch("src.api.greeks.load_positions_from_db") as mock_load,
            patch("src.api.greeks.GreeksCalculator") as mock_calc_cls,
            patch("src.api.greeks.GreeksAggregator") as mock_agg_cls,
        ):
            mock_load.return_value = [MagicMock()]

            mock_calc = MagicMock()
            mock_calc.calculate.return_value = [MagicMock()]
            mock_calc_cls.return_value = mock_calc

            mock_agg = MagicMock()
            # dollar_delta=50000 exceeds hard limit of 30000
            mock_agg.aggregate.return_value = _make_aggregated_greeks(dollar_delta=Decimal("50000"))
            mock_agg_cls.return_value = mock_agg

            response = client.get("/api/greeks/accounts/acc_001/scenario")

            assert response.status_code == 200
            data = response.json()

            # With custom limits (hard=30000), current dollar_delta=50000 should breach
            # The scenario should detect breach based on account limits, not hardcoded 200000
            scenario = data["scenarios"]["+1%"]
            # At +1%, new_dollar_delta = 50000 + (50000 * 0.01) = 50500
            # This exceeds hard limit of 30000, so breach_level should be "hard"
            assert scenario["breach_level"] == "hard", (
                f"Expected 'hard' breach with custom limits (hard=30000), "
                f"got '{scenario['breach_level']}'. "
                f"new_dollar_delta={scenario['new_dollar_delta']}"
            )
            assert "dollar_delta" in scenario["breach_dims"]


class TestLimitsEndpoint:
    """Tests for PUT /api/greeks/accounts/{account_id}/limits."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import app

        return TestClient(app)

    @pytest.fixture(autouse=True)
    def reset_limits_store(self):
        """Reset the limits store before each test."""
        import src.greeks.limits_store as limits_module

        limits_module._limits_store = None
        yield
        limits_module._limits_store = None

    def test_put_limits_success(self, client):
        """PUT /limits with valid limits succeeds."""
        response = client.put(
            "/api/greeks/accounts/acc_001/limits",
            json={
                "limits": {
                    "dollar_delta": {"warn": 100000, "crit": 150000, "hard": 200000},
                    "gamma_dollar": {"warn": 5000, "crit": 7500, "hard": 10000},
                    "vega_per_1pct": {"warn": 20000, "crit": 30000, "hard": 40000},
                    "theta_per_day": {"warn": 3000, "crit": 4500, "hard": 6000},
                }
            },
            headers={"X-User-ID": "user_123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "acc_001"
        assert data["effective_scope"] == "ACCOUNT"
        assert data["limits"]["dollar_delta"]["hard"] == 200000

    def test_put_limits_validation_error(self, client):
        """PUT /limits with invalid limits returns 400."""
        response = client.put(
            "/api/greeks/accounts/acc_001/limits",
            json={
                "limits": {
                    "dollar_delta": {"warn": 200000, "crit": 100000, "hard": 300000},  # Invalid
                    "gamma_dollar": {"warn": 5000, "crit": 7500, "hard": 10000},
                    "vega_per_1pct": {"warn": 20000, "crit": 30000, "hard": 40000},
                    "theta_per_day": {"warn": 3000, "crit": 4500, "hard": 6000},
                }
            },
            headers={"X-User-ID": "user_123"},
        )

        assert response.status_code == 400

    def test_put_limits_strategy_returns_501(self, client):
        """PUT /limits with strategy_id returns 501 Not Implemented."""
        response = client.put(
            "/api/greeks/accounts/acc_001/limits",
            json={
                "strategy_id": "strat_001",
                "limits": {
                    "dollar_delta": {"warn": 100000, "crit": 150000, "hard": 200000},
                    "gamma_dollar": {"warn": 5000, "crit": 7500, "hard": 10000},
                    "vega_per_1pct": {"warn": 20000, "crit": 30000, "hard": 40000},
                    "theta_per_day": {"warn": 3000, "crit": 4500, "hard": 6000},
                },
            },
            headers={"X-User-ID": "user_123"},
        )

        assert response.status_code == 501

    def test_put_limits_returns_updated_by(self, client):
        """PUT /limits returns updated_by from header."""
        response = client.put(
            "/api/greeks/accounts/acc_001/limits",
            json={
                "limits": {
                    "dollar_delta": {"warn": 100000, "crit": 150000, "hard": 200000},
                    "gamma_dollar": {"warn": 5000, "crit": 7500, "hard": 10000},
                    "vega_per_1pct": {"warn": 20000, "crit": 30000, "hard": 40000},
                    "theta_per_day": {"warn": 3000, "crit": 4500, "hard": 6000},
                }
            },
            headers={"X-User-ID": "test_user"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_by"] == "test_user"

    def test_get_limits_returns_current(self, client):
        """GET /limits returns current limits."""
        # First set limits
        client.put(
            "/api/greeks/accounts/acc_001/limits",
            json={
                "limits": {
                    "dollar_delta": {"warn": 111000, "crit": 150000, "hard": 200000},
                    "gamma_dollar": {"warn": 5000, "crit": 7500, "hard": 10000},
                    "vega_per_1pct": {"warn": 20000, "crit": 30000, "hard": 40000},
                    "theta_per_day": {"warn": 3000, "crit": 4500, "hard": 6000},
                }
            },
            headers={"X-User-ID": "user_123"},
        )

        # Then get them
        response = client.get("/api/greeks/accounts/acc_001/limits")

        assert response.status_code == 200
        data = response.json()
        assert data["limits"]["dollar_delta"]["warn"] == 111000


class TestHistoryEndpoint:
    """Tests for GET /api/greeks/accounts/{account_id}/history."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.main import app

        return TestClient(app)

    @pytest.mark.asyncio
    async def test_history_endpoint_returns_points(self, client):
        """GET /history returns history points."""
        from src.greeks.v2_models import GreeksHistoryPoint

        with patch("src.api.greeks.GreeksRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_history = AsyncMock(
                return_value=[
                    GreeksHistoryPoint(
                        ts=datetime.now(timezone.utc),
                        dollar_delta=Decimal("50000"),
                        gamma_dollar=Decimal("2000"),
                        vega_per_1pct=Decimal("15000"),
                        theta_per_day=Decimal("-2800"),
                        coverage_pct=Decimal("98.5"),
                        point_count=2,
                    )
                ]
            )
            mock_repo_cls.return_value = mock_repo

            response = client.get("/api/greeks/accounts/acc_001/history?window=1h")

            assert response.status_code == 200
            data = response.json()
            assert "points" in data
            assert len(data["points"]) == 1
            assert data["points"][0]["dollar_delta"] == 50000.0

    @pytest.mark.asyncio
    async def test_history_endpoint_window_parameter(self, client):
        """GET /history respects window parameter."""
        with patch("src.api.greeks.GreeksRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_history = AsyncMock(return_value=[])
            mock_repo_cls.return_value = mock_repo

            response = client.get("/api/greeks/accounts/acc_001/history?window=4h")

            assert response.status_code == 200
            data = response.json()
            assert data["window"] == "4h"
            assert data["interval"] == "1m"

    @pytest.mark.asyncio
    async def test_history_endpoint_invalid_window(self, client):
        """GET /history rejects invalid window."""
        response = client.get("/api/greeks/accounts/acc_001/history?window=invalid")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_history_endpoint_scope_strategy_requires_id(self, client):
        """GET /history with scope=STRATEGY requires strategy_id."""
        response = client.get("/api/greeks/accounts/acc_001/history?window=1h&scope=STRATEGY")

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_history_response_structure(self, client):
        """GET /history response matches GreeksHistoryApiResponse schema."""
        with patch("src.api.greeks.GreeksRepository") as mock_repo_cls:
            mock_repo = MagicMock()
            mock_repo.get_history = AsyncMock(return_value=[])
            mock_repo_cls.return_value = mock_repo

            response = client.get("/api/greeks/accounts/acc_001/history?window=1h")

            assert response.status_code == 200
            data = response.json()

            assert "account_id" in data
            assert "scope" in data
            assert "window" in data
            assert "interval" in data
            assert "start_ts" in data
            assert "end_ts" in data
            assert "points" in data
