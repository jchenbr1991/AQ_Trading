# backend/tests/test_api_portfolio.py
import pytest
from decimal import Decimal

from src.db.repositories.portfolio_repo import PortfolioRepository


class TestPortfolioAPI:
    async def test_get_account_not_found(self, client):
        response = await client.get("/api/portfolio/accounts/ACC001")
        assert response.status_code == 404

    async def test_get_account_success(self, client, db_session):
        # Setup
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.update_account("ACC001", cash=Decimal("10000"))

        response = await client.get("/api/portfolio/accounts/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "ACC001"
        assert data["cash"] == "10000.0000"

    async def test_get_positions_empty(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")

        response = await client.get("/api/portfolio/accounts/ACC001/positions")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_positions_with_data(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"))
        await repo.create_position("ACC001", "TSLA", 50, Decimal("200"))

        response = await client.get("/api/portfolio/accounts/ACC001/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_positions_filtered_by_strategy(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"), strategy_id="strat_a")
        await repo.create_position("ACC001", "TSLA", 50, Decimal("200"), strategy_id="strat_b")

        response = await client.get("/api/portfolio/accounts/ACC001/positions?strategy_id=strat_a")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "AAPL"

    async def test_get_pnl(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"))

        response = await client.get("/api/portfolio/accounts/ACC001/pnl")

        assert response.status_code == 200
        data = response.json()
        assert "unrealized_pnl" in data
        assert "realized_pnl" in data
        assert "total_pnl" in data
