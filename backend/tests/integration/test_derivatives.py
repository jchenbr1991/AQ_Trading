# backend/tests/integration/test_derivatives.py
"""End-to-end integration tests for derivatives API.

Tests the derivatives lifecycle management endpoints:
- GET /api/derivatives/expiring - List expiring positions
- GET /api/derivatives/expiring/{days} - Positions within N days
- POST /api/derivatives/roll/{symbol} - Generate roll plan

Acceptance Criteria:
- SC-011: User receives expiration warning at least 5 days before expiry
- FR-016: System tracks derivative expiry dates
- FR-017: System supports futures auto-roll
"""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.db.database import get_session
from src.main import app
from src.models.derivative_contract import ContractType, DerivativeContract, PutCall


@pytest_asyncio.fixture
async def client(db_session):
    """HTTP client with test database."""

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


class TestDerivativesExpiringEndpoints:
    """Tests for /api/derivatives/expiring endpoints."""

    @pytest.mark.asyncio
    async def test_get_expiring_positions_empty(self, client):
        """Should return empty list when no positions exist."""
        response = await client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        assert "total" in data
        assert "warning_days" in data
        assert data["warning_days"] == 5  # SC-011: 5 days default
        assert data["total"] == 0
        assert data["positions"] == []

    @pytest.mark.asyncio
    async def test_get_expiring_positions_with_days(self, client):
        """Should accept custom days parameter."""
        response = await client.get("/api/derivatives/expiring/10")

        assert response.status_code == 200
        data = response.json()
        assert data["warning_days"] == 10

    @pytest.mark.asyncio
    async def test_get_expiring_positions_invalid_days(self, client):
        """Should reject invalid days parameter."""
        # Negative days
        response = await client.get("/api/derivatives/expiring/-1")
        assert response.status_code == 422

        # Over 365 days
        response = await client.get("/api/derivatives/expiring/400")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_expiring_positions_zero_days(self, client):
        """Should accept 0 days (today only)."""
        response = await client.get("/api/derivatives/expiring/0")

        assert response.status_code == 200
        data = response.json()
        assert data["warning_days"] == 0


class TestDerivativesRollEndpoints:
    """Tests for /api/derivatives/roll endpoints."""

    @pytest.mark.asyncio
    async def test_roll_nonexistent_symbol(self, client):
        """Should return 404 for nonexistent symbol."""
        response = await client.post("/api/derivatives/roll/NONEXISTENT")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_roll_endpoint_exists(self, client):
        """Roll endpoint should exist and respond."""
        # Even with invalid symbol, should get 404 not 405
        response = await client.post("/api/derivatives/roll/TEST123")
        assert response.status_code in [404, 400]  # Not found or not a future


class TestDerivativesWithData:
    """Tests with seeded derivative contract data."""

    @pytest_asyncio.fixture
    async def seeded_client(self, db_session, client):
        """Client with seeded derivative contracts."""
        # Create test contracts
        today = date.today()

        # Expiring soon (within 5 days)
        expiring_option = DerivativeContract(
            symbol="AAPL240201C200",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=today + timedelta(days=3),
            strike=200.0,
            put_call=PutCall.CALL,
        )

        # Expiring later (10 days)
        later_option = DerivativeContract(
            symbol="AAPL240210P195",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=today + timedelta(days=10),
            strike=195.0,
            put_call=PutCall.PUT,
        )

        # Future contract
        future = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=today + timedelta(days=4),
        )

        db_session.add_all([expiring_option, later_option, future])
        await db_session.commit()

        yield client

    @pytest.mark.asyncio
    async def test_get_expiring_within_5_days(self, seeded_client):
        """Should return positions expiring within 5 days."""
        response = await seeded_client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2  # option + future
        assert data["warning_days"] == 5

        symbols = [p["symbol"] for p in data["positions"]]
        assert "AAPL240201C200" in symbols
        assert "ESH24" in symbols
        assert "AAPL240210P195" not in symbols

    @pytest.mark.asyncio
    async def test_get_expiring_within_15_days(self, seeded_client):
        """Should return all positions within 15 days."""
        response = await seeded_client.get("/api/derivatives/expiring/15")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3  # All three contracts

    @pytest.mark.asyncio
    async def test_roll_futures_contract(self, seeded_client):
        """Should generate roll plan for futures contract."""
        response = await seeded_client.post("/api/derivatives/roll/ESH24")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "ESH24"
        assert "strategy" in data
        assert "close_action" in data
        assert "open_action" in data

    @pytest.mark.asyncio
    async def test_roll_option_fails(self, seeded_client):
        """Should fail to roll an options contract."""
        response = await seeded_client.post("/api/derivatives/roll/AAPL240201C200")

        assert response.status_code == 400
        assert "not a futures" in response.json()["detail"].lower()


class TestDerivativesAcceptanceCriteria:
    """Tests for acceptance criteria verification."""

    @pytest.mark.asyncio
    async def test_sc011_default_warning_days(self, client):
        """SC-011: Default warning window should be 5 days."""
        response = await client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["warning_days"] == 5

    @pytest.mark.asyncio
    async def test_fr016_expiry_tracking_response_format(self, client):
        """FR-016: Response should include expiry date information."""
        response = await client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()

        # Response schema should support expiry tracking
        assert "positions" in data
        assert "total" in data
        assert "warning_days" in data

    @pytest.mark.asyncio
    async def test_fr017_roll_endpoint_available(self, client):
        """FR-017: Roll endpoint should be available (returns 404 for unknown symbol)."""
        response = await client.post("/api/derivatives/roll/UNKNOWN")
        assert response.status_code == 404  # Endpoint exists but symbol not found
