# backend/tests/api/test_portfolio_api.py
"""Tests for Portfolio API endpoints (Phase 1 - Mock Data)."""

from datetime import datetime


class TestGetAccountSummary:
    """Tests for GET /api/portfolio/account/{account_id} endpoint."""

    async def test_get_account_returns_summary(self, client):
        """GET /api/portfolio/account/{account_id} returns account summary."""
        response = await client.get("/api/portfolio/account/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "ACC001"
        assert "cash" in data
        assert "buying_power" in data
        assert "total_equity" in data
        assert "unrealized_pnl" in data
        assert "day_pnl" in data
        assert "updated_at" in data

    async def test_get_account_returns_numeric_values(self, client):
        """GET /api/portfolio/account/{account_id} returns proper numeric values."""
        response = await client.get("/api/portfolio/account/ACC001")

        assert response.status_code == 200
        data = response.json()
        # Verify values are numeric (float/int)
        assert isinstance(data["cash"], int | float)
        assert isinstance(data["buying_power"], int | float)
        assert isinstance(data["total_equity"], int | float)
        assert isinstance(data["unrealized_pnl"], int | float)
        assert isinstance(data["day_pnl"], int | float)

    async def test_get_account_returns_iso_datetime(self, client):
        """GET /api/portfolio/account/{account_id} returns ISO format datetime."""
        response = await client.get("/api/portfolio/account/ACC001")

        assert response.status_code == 200
        data = response.json()
        # Should be parseable as ISO datetime
        updated_at = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        assert updated_at is not None

    async def test_get_account_different_account_id(self, client):
        """GET /api/portfolio/account/{account_id} reflects the requested account_id."""
        response = await client.get("/api/portfolio/account/TEST123")

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "TEST123"


class TestGetPositions:
    """Tests for GET /api/portfolio/positions/{account_id} endpoint."""

    async def test_get_positions_returns_list(self, client):
        """GET /api/portfolio/positions/{account_id} returns a list of positions."""
        response = await client.get("/api/portfolio/positions/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_positions_returns_position_fields(self, client):
        """GET /api/portfolio/positions/{account_id} returns positions with required fields."""
        response = await client.get("/api/portfolio/positions/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0  # Mock data should have at least one position

        position = data[0]
        assert "symbol" in position
        assert "quantity" in position
        assert "avg_cost" in position
        assert "current_price" in position
        assert "market_value" in position
        assert "unrealized_pnl" in position
        assert "strategy_id" in position

    async def test_get_positions_returns_numeric_values(self, client):
        """GET /api/portfolio/positions/{account_id} returns proper numeric values."""
        response = await client.get("/api/portfolio/positions/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

        position = data[0]
        assert isinstance(position["quantity"], int)
        assert isinstance(position["avg_cost"], int | float)
        assert isinstance(position["current_price"], int | float)
        assert isinstance(position["market_value"], int | float)
        assert isinstance(position["unrealized_pnl"], int | float)

    async def test_get_positions_symbol_is_string(self, client):
        """GET /api/portfolio/positions/{account_id} returns string symbols."""
        response = await client.get("/api/portfolio/positions/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

        for position in data:
            assert isinstance(position["symbol"], str)
            assert len(position["symbol"]) > 0

    async def test_get_positions_different_account_id(self, client):
        """GET /api/portfolio/positions/{account_id} works with different account_ids."""
        response = await client.get("/api/portfolio/positions/TEST456")

        assert response.status_code == 200
        data = response.json()
        # Should return mock data for any account_id
        assert isinstance(data, list)
