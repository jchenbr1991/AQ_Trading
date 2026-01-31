"""Tests for ExpirationManager service.

Tests cover:
- SC-011: User receives expiration warning at least 5 days before expiry
- FR-016: System tracks derivative expiry dates
"""

from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.derivatives.expiration_manager import ExpirationAlert, ExpirationManager
from src.models.derivative_contract import ContractType, DerivativeContract, PutCall


class TestExpirationAlertModel:
    """Tests for ExpirationAlert dataclass."""

    def test_expiration_alert_creation(self):
        """ExpirationAlert should be created with all required fields."""
        alert = ExpirationAlert(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            expiry=date(2024, 1, 19),
            days_to_expiry=5,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )
        assert alert.symbol == "AAPL240119C00150000"
        assert alert.underlying == "AAPL"
        assert alert.expiry == date(2024, 1, 19)
        assert alert.days_to_expiry == 5
        assert alert.contract_type == ContractType.OPTION
        assert alert.put_call == PutCall.CALL
        assert alert.strike == Decimal("150.00")

    def test_expiration_alert_is_frozen(self):
        """ExpirationAlert should be immutable."""
        alert = ExpirationAlert(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            expiry=date(2024, 1, 19),
            days_to_expiry=5,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )
        with pytest.raises(FrozenInstanceError):
            alert.days_to_expiry = 3

    def test_expiration_alert_future_contract(self):
        """ExpirationAlert for futures should have None put_call and strike."""
        alert = ExpirationAlert(
            symbol="ESH24",
            underlying="ES",
            expiry=date(2024, 3, 15),
            days_to_expiry=3,
            contract_type=ContractType.FUTURE,
            put_call=None,
            strike=None,
        )
        assert alert.contract_type == ContractType.FUTURE
        assert alert.put_call is None
        assert alert.strike is None


class TestExpirationManagerInit:
    """Tests for ExpirationManager initialization."""

    def test_default_warning_days(self):
        """ExpirationManager should default to 5 warning days."""
        mock_session = MagicMock()
        manager = ExpirationManager(session=mock_session)
        assert manager._warning_days == 5

    def test_custom_warning_days(self):
        """ExpirationManager should accept custom warning days."""
        mock_session = MagicMock()
        manager = ExpirationManager(session=mock_session, warning_days=10)
        assert manager._warning_days == 10


class TestGetExpiringPositions:
    """Tests for get_expiring_positions method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_positions(self, mock_session):
        """Should return empty list when no positions are expiring."""
        # Mock scalars().all() chain
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        positions = await manager.get_expiring_positions()

        assert positions == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_expiring_positions(self, mock_session):
        """Should return positions expiring within warning window."""
        # Create mock contract
        contract = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today() + timedelta(days=3),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [contract]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        positions = await manager.get_expiring_positions()

        assert len(positions) == 1
        assert positions[0].symbol == "AAPL240119C00150000"

    @pytest.mark.asyncio
    async def test_uses_default_warning_days(self, mock_session):
        """Should use default warning_days when days parameter not specified."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session, warning_days=7)
        await manager.get_expiring_positions()

        # Verify the query was executed (detailed SQL check would be in integration tests)
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_custom_days_parameter(self, mock_session):
        """Should use custom days parameter when provided."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session, warning_days=5)
        await manager.get_expiring_positions(days=10)

        # Should execute with custom days override
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_multiple_expiring_positions(self, mock_session):
        """Should return all positions expiring within window."""
        contracts = [
            DerivativeContract(
                symbol="AAPL240119C00150000",
                underlying="AAPL",
                contract_type=ContractType.OPTION,
                expiry=date.today() + timedelta(days=2),
                strike=Decimal("150.00"),
                put_call=PutCall.CALL,
            ),
            DerivativeContract(
                symbol="TSLA240119P00200000",
                underlying="TSLA",
                contract_type=ContractType.OPTION,
                expiry=date.today() + timedelta(days=4),
                strike=Decimal("200.00"),
                put_call=PutCall.PUT,
            ),
            DerivativeContract(
                symbol="ESH24",
                underlying="ES",
                contract_type=ContractType.FUTURE,
                expiry=date.today() + timedelta(days=5),
                strike=None,
                put_call=None,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = contracts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        positions = await manager.get_expiring_positions()

        assert len(positions) == 3


class TestCheckExpirations:
    """Tests for check_expirations method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_expiring(self, mock_session):
        """Should return empty list when no positions are expiring."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        alerts = await manager.check_expirations()

        assert alerts == []

    @pytest.mark.asyncio
    async def test_returns_alerts_for_expiring_options(self, mock_session):
        """Should return alerts for expiring option contracts."""
        expiry_date = date.today() + timedelta(days=3)
        contract = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=expiry_date,
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [contract]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        alerts = await manager.check_expirations()

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.symbol == "AAPL240119C00150000"
        assert alert.underlying == "AAPL"
        assert alert.expiry == expiry_date
        assert alert.days_to_expiry == 3
        assert alert.contract_type == ContractType.OPTION
        assert alert.put_call == PutCall.CALL
        assert alert.strike == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_returns_alerts_for_expiring_futures(self, mock_session):
        """Should return alerts for expiring future contracts."""
        expiry_date = date.today() + timedelta(days=2)
        contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=expiry_date,
            strike=None,
            put_call=None,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [contract]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        alerts = await manager.check_expirations()

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.symbol == "ESH24"
        assert alert.underlying == "ES"
        assert alert.days_to_expiry == 2
        assert alert.contract_type == ContractType.FUTURE
        assert alert.put_call is None
        assert alert.strike is None

    @pytest.mark.asyncio
    async def test_calculates_correct_days_to_expiry(self, mock_session):
        """Should calculate correct days_to_expiry for each contract."""
        today = date.today()
        contracts = [
            DerivativeContract(
                symbol="AAPL_1D",
                underlying="AAPL",
                contract_type=ContractType.OPTION,
                expiry=today + timedelta(days=1),
                strike=Decimal("150.00"),
                put_call=PutCall.CALL,
            ),
            DerivativeContract(
                symbol="AAPL_0D",
                underlying="AAPL",
                contract_type=ContractType.OPTION,
                expiry=today,  # Expires today
                strike=Decimal("150.00"),
                put_call=PutCall.CALL,
            ),
            DerivativeContract(
                symbol="AAPL_5D",
                underlying="AAPL",
                contract_type=ContractType.OPTION,
                expiry=today + timedelta(days=5),
                strike=Decimal("150.00"),
                put_call=PutCall.CALL,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = contracts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        alerts = await manager.check_expirations()

        assert len(alerts) == 3
        # Sort by days_to_expiry to check
        alerts_by_days = {a.days_to_expiry: a for a in alerts}
        assert 0 in alerts_by_days  # Expires today
        assert 1 in alerts_by_days  # 1 day
        assert 5 in alerts_by_days  # 5 days

    @pytest.mark.asyncio
    async def test_returns_multiple_alerts(self, mock_session):
        """Should return multiple alerts when multiple contracts expiring."""
        contracts = [
            DerivativeContract(
                symbol="AAPL240119C00150000",
                underlying="AAPL",
                contract_type=ContractType.OPTION,
                expiry=date.today() + timedelta(days=2),
                strike=Decimal("150.00"),
                put_call=PutCall.CALL,
            ),
            DerivativeContract(
                symbol="TSLA240119P00200000",
                underlying="TSLA",
                contract_type=ContractType.OPTION,
                expiry=date.today() + timedelta(days=4),
                strike=Decimal("200.00"),
                put_call=PutCall.PUT,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = contracts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        alerts = await manager.check_expirations()

        assert len(alerts) == 2
        symbols = {a.symbol for a in alerts}
        assert "AAPL240119C00150000" in symbols
        assert "TSLA240119P00200000" in symbols


class TestAcceptanceCriteria:
    """Tests verifying acceptance criteria from spec.md."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_sc011_warning_5_days_before_expiry(self, mock_session):
        """SC-011: User receives expiration warning at least 5 days before expiry.

        Verifies that contracts expiring within 5 days generate alerts.
        """
        # Contract expiring in exactly 5 days
        contract_5d = DerivativeContract(
            symbol="AAPL_5D",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today() + timedelta(days=5),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [contract_5d]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session, warning_days=5)
        alerts = await manager.check_expirations()

        # Should get alert for contract expiring in 5 days
        assert len(alerts) == 1
        assert alerts[0].days_to_expiry == 5

    @pytest.mark.asyncio
    async def test_fr016_tracks_derivative_expiry(self, mock_session):
        """FR-016: System tracks derivative expiry dates.

        Verifies that the system can query and return derivative contracts
        based on their expiry dates.
        """
        contracts = [
            DerivativeContract(
                symbol="AAPL240119C00150000",
                underlying="AAPL",
                contract_type=ContractType.OPTION,
                expiry=date.today() + timedelta(days=3),
                strike=Decimal("150.00"),
                put_call=PutCall.CALL,
            ),
            DerivativeContract(
                symbol="ESH24",
                underlying="ES",
                contract_type=ContractType.FUTURE,
                expiry=date.today() + timedelta(days=4),
                strike=None,
                put_call=None,
            ),
        ]

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = contracts
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = ExpirationManager(session=mock_session)
        positions = await manager.get_expiring_positions(days=5)

        # System should track both options and futures expiry dates
        assert len(positions) == 2
        expiries = {p.expiry for p in positions}
        assert len(expiries) == 2  # Both have different expiry dates


class TestDatabaseIntegration:
    """Integration tests using real SQLite database."""

    @pytest.fixture
    async def db_session(self):
        """Create an in-memory SQLite database with test data."""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        from sqlalchemy.orm import sessionmaker
        from src.db.database import Base

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            yield session

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_queries_database_for_expiring_positions(self, db_session):
        """Should query database and return expiring positions."""
        # Insert test contracts
        today = date.today()
        expiring_contract = DerivativeContract(
            symbol="AAPL_EXPIRING",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=today + timedelta(days=3),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        non_expiring_contract = DerivativeContract(
            symbol="AAPL_NOT_EXPIRING",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=today + timedelta(days=30),  # Not within warning window
            strike=Decimal("160.00"),
            put_call=PutCall.CALL,
        )

        db_session.add(expiring_contract)
        db_session.add(non_expiring_contract)
        await db_session.commit()

        manager = ExpirationManager(session=db_session, warning_days=5)
        positions = await manager.get_expiring_positions()

        # Should only return the expiring contract
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL_EXPIRING"

    @pytest.mark.asyncio
    async def test_generates_alerts_from_database(self, db_session):
        """Should generate alerts from database records."""
        today = date.today()
        contract = DerivativeContract(
            symbol="TSLA240119P00200000",
            underlying="TSLA",
            contract_type=ContractType.OPTION,
            expiry=today + timedelta(days=2),
            strike=Decimal("200.00"),
            put_call=PutCall.PUT,
        )

        db_session.add(contract)
        await db_session.commit()

        manager = ExpirationManager(session=db_session)
        alerts = await manager.check_expirations()

        assert len(alerts) == 1
        alert = alerts[0]
        assert alert.symbol == "TSLA240119P00200000"
        assert alert.underlying == "TSLA"
        assert alert.days_to_expiry == 2
        assert alert.contract_type == ContractType.OPTION
        assert alert.put_call == PutCall.PUT
        assert alert.strike == Decimal("200.00")
