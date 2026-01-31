# backend/tests/api/test_derivatives_routes.py
"""Tests for derivatives API endpoints.

Tests the expiration monitoring and futures rolling API routes:
- GET /api/derivatives/expiring - List expiring positions with default window
- GET /api/derivatives/expiring/{days} - List positions expiring within N days
- POST /api/derivatives/roll/{symbol} - Generate roll plan for futures
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.db.database import Base, get_session
from src.main import app
from src.models.derivative_contract import ContractType, DerivativeContract, PutCall


@pytest_asyncio.fixture
async def derivatives_db_session():
    """In-memory SQLite database with derivative_contracts table for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables using SQLAlchemy metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def derivatives_client(derivatives_db_session):
    """HTTP client with derivatives database."""

    async def override_get_session():
        yield derivatives_db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


async def insert_derivative_contract(
    session: AsyncSession,
    symbol: str,
    underlying: str,
    contract_type: str,
    expiry: date,
    strike: float | None = None,
    put_call: str | None = None,
) -> None:
    """Insert a test derivative contract into the database using the ORM model."""
    # Convert string to enum
    ct_enum = ContractType(contract_type)
    pc_enum = PutCall(put_call) if put_call else None
    strike_decimal = Decimal(str(strike)) if strike is not None else None

    contract = DerivativeContract(
        symbol=symbol,
        underlying=underlying,
        contract_type=ct_enum,
        expiry=expiry,
        strike=strike_decimal,
        put_call=pc_enum,
    )
    session.add(contract)
    await session.commit()


class TestGetExpiringPositions:
    """Tests for GET /api/derivatives/expiring endpoint."""

    @pytest.mark.asyncio
    async def test_get_expiring_returns_empty_list(self, derivatives_client):
        """Should return empty list when no contracts exist."""
        response = await derivatives_client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["positions"] == []
        assert data["total"] == 0
        assert data["warning_days"] == 5  # Default warning days

    @pytest.mark.asyncio
    async def test_get_expiring_returns_positions_within_window(
        self, derivatives_client, derivatives_db_session
    ):
        """Should return positions expiring within the default 5-day window."""
        today = date.today()

        # Insert position expiring in 3 days (should be returned)
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=3),
            strike=150.0,
            put_call="call",
        )

        # Insert position expiring in 10 days (should NOT be returned)
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240219C00160000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=10),
            strike=160.0,
            put_call="call",
        )

        response = await derivatives_client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["positions"]) == 1

        position = data["positions"][0]
        assert position["symbol"] == "AAPL240119C00150000"
        assert position["underlying"] == "AAPL"
        assert position["days_to_expiry"] == 3
        assert position["contract_type"] == "option"
        assert position["put_call"] == "call"
        assert float(position["strike"]) == 150.0

    @pytest.mark.asyncio
    async def test_get_expiring_returns_futures(self, derivatives_client, derivatives_db_session):
        """Should return futures contracts without strike/put_call."""
        today = date.today()

        await insert_derivative_contract(
            derivatives_db_session,
            symbol="ESH24",
            underlying="ES",
            contract_type="future",
            expiry=today + timedelta(days=2),
            strike=None,
            put_call=None,
        )

        response = await derivatives_client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

        position = data["positions"][0]
        assert position["symbol"] == "ESH24"
        assert position["contract_type"] == "future"
        assert position["put_call"] is None
        assert position["strike"] is None

    @pytest.mark.asyncio
    async def test_get_expiring_excludes_past_positions(
        self, derivatives_client, derivatives_db_session
    ):
        """Should not return positions that have already expired."""
        today = date.today()

        # Insert position that expired yesterday (should NOT be returned)
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today - timedelta(days=1),
            strike=150.0,
            put_call="call",
        )

        response = await derivatives_client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestGetExpiringPositionsWithinDays:
    """Tests for GET /api/derivatives/expiring/{days} endpoint."""

    @pytest.mark.asyncio
    async def test_get_expiring_custom_days(self, derivatives_client, derivatives_db_session):
        """Should return positions expiring within custom days window."""
        today = date.today()

        # Insert position expiring in 7 days
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=7),
            strike=150.0,
            put_call="call",
        )

        # Insert position expiring in 15 days
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240219C00160000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=15),
            strike=160.0,
            put_call="call",
        )

        # Query with 10-day window
        response = await derivatives_client.get("/api/derivatives/expiring/10")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["warning_days"] == 10
        assert data["positions"][0]["symbol"] == "AAPL240119C00150000"

    @pytest.mark.asyncio
    async def test_get_expiring_zero_days(self, derivatives_client, derivatives_db_session):
        """Should return positions expiring today with days=0."""
        today = date.today()

        # Insert position expiring today
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today,
            strike=150.0,
            put_call="call",
        )

        response = await derivatives_client.get("/api/derivatives/expiring/0")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["positions"][0]["days_to_expiry"] == 0

    @pytest.mark.asyncio
    async def test_get_expiring_invalid_days_negative(self, derivatives_client):
        """Should return 422 for negative days."""
        response = await derivatives_client.get("/api/derivatives/expiring/-1")

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_expiring_invalid_days_too_large(self, derivatives_client):
        """Should return 422 for days > 365."""
        response = await derivatives_client.get("/api/derivatives/expiring/400")

        assert response.status_code == 422


class TestGenerateRollPlan:
    """Tests for POST /api/derivatives/roll/{symbol} endpoint."""

    @pytest.mark.asyncio
    async def test_roll_plan_not_found(self, derivatives_client):
        """Should return 404 when contract doesn't exist."""
        response = await derivatives_client.post("/api/derivatives/roll/NONEXISTENT")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_roll_plan_not_futures(self, derivatives_client, derivatives_db_session):
        """Should return 400 when contract is not a futures contract."""
        today = date.today()

        # Insert an option contract
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=30),
            strike=150.0,
            put_call="call",
        )

        response = await derivatives_client.post("/api/derivatives/roll/AAPL240119C00150000")

        assert response.status_code == 400
        assert "not a futures contract" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_roll_plan_success_calendar_spread(
        self, derivatives_client, derivatives_db_session
    ):
        """Should generate roll plan with calendar spread strategy for futures."""
        today = date.today()

        # Insert a futures contract
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="ESH24",
            underlying="ES",
            contract_type="future",
            expiry=today + timedelta(days=10),
            strike=None,
            put_call=None,
        )

        response = await derivatives_client.post("/api/derivatives/roll/ESH24")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "ESH24"
        assert data["strategy"] == "calendar_spread"
        assert data["close_action"] == "SELL ESH24 to close"
        assert data["open_action"] is not None
        assert "BUY" in data["open_action"]

    @pytest.mark.asyncio
    async def test_roll_plan_generates_next_contract(
        self, derivatives_client, derivatives_db_session
    ):
        """Should generate correct next contract symbol in open_action."""
        today = date.today()

        # Insert a futures contract with month code H (March)
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="ESH24",
            underlying="ES",
            contract_type="future",
            expiry=today + timedelta(days=10),
            strike=None,
            put_call=None,
        )

        response = await derivatives_client.post("/api/derivatives/roll/ESH24")

        assert response.status_code == 200
        data = response.json()
        # H (March) -> J (April)
        assert "ESJ24" in data["open_action"]


class TestMultipleExpiringPositions:
    """Tests for multiple expiring positions scenarios."""

    @pytest.mark.asyncio
    async def test_multiple_positions_sorted_by_expiry(
        self, derivatives_client, derivatives_db_session
    ):
        """Should return positions sorted by expiry date (ascending)."""
        today = date.today()

        # Insert positions out of order
        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=5),
            strike=150.0,
            put_call="call",
        )

        await insert_derivative_contract(
            derivatives_db_session,
            symbol="ESH24",
            underlying="ES",
            contract_type="future",
            expiry=today + timedelta(days=2),
        )

        await insert_derivative_contract(
            derivatives_db_session,
            symbol="MSFT240119P00200000",
            underlying="MSFT",
            contract_type="option",
            expiry=today + timedelta(days=4),
            strike=200.0,
            put_call="put",
        )

        response = await derivatives_client.get("/api/derivatives/expiring/10")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3

        # Verify sorted by expiry (ascending)
        days = [p["days_to_expiry"] for p in data["positions"]]
        assert days == sorted(days)

    @pytest.mark.asyncio
    async def test_mixed_options_and_futures(self, derivatives_client, derivatives_db_session):
        """Should correctly handle both options and futures."""
        today = date.today()

        await insert_derivative_contract(
            derivatives_db_session,
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type="option",
            expiry=today + timedelta(days=3),
            strike=150.0,
            put_call="call",
        )

        await insert_derivative_contract(
            derivatives_db_session,
            symbol="ESH24",
            underlying="ES",
            contract_type="future",
            expiry=today + timedelta(days=3),
        )

        response = await derivatives_client.get("/api/derivatives/expiring")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

        # Verify we have both types
        contract_types = [p["contract_type"] for p in data["positions"]]
        assert "option" in contract_types
        assert "future" in contract_types
