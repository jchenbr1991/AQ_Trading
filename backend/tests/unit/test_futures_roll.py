"""Tests for FuturesRollManager service.

Tests cover:
- FR-017: System supports futures auto-roll
- Support calendar_spread and close_open strategies
- Configurable per-underlying roll strategy
- days_before_expiry configuration
"""

from dataclasses import FrozenInstanceError
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.derivatives.futures_roll import (
    FuturesRollManager,
    RollConfig,
    RollPlan,
    RollStrategy,
)
from src.models.derivative_contract import ContractType, DerivativeContract


class TestRollStrategyEnum:
    """Tests for RollStrategy enum."""

    def test_roll_strategy_calendar_spread(self):
        """RollStrategy should have CALENDAR_SPREAD value."""
        assert RollStrategy.CALENDAR_SPREAD == "calendar_spread"
        assert RollStrategy.CALENDAR_SPREAD.value == "calendar_spread"

    def test_roll_strategy_close_open(self):
        """RollStrategy should have CLOSE_OPEN value."""
        assert RollStrategy.CLOSE_OPEN == "close_open"
        assert RollStrategy.CLOSE_OPEN.value == "close_open"


class TestRollConfigModel:
    """Tests for RollConfig dataclass."""

    def test_roll_config_creation(self):
        """RollConfig should be created with all required fields."""
        config = RollConfig(
            underlying="ES",
            strategy=RollStrategy.CALENDAR_SPREAD,
            days_before_expiry=5,
        )
        assert config.underlying == "ES"
        assert config.strategy == RollStrategy.CALENDAR_SPREAD
        assert config.days_before_expiry == 5

    def test_roll_config_is_frozen(self):
        """RollConfig should be immutable."""
        config = RollConfig(
            underlying="ES",
            strategy=RollStrategy.CALENDAR_SPREAD,
            days_before_expiry=5,
        )
        with pytest.raises(FrozenInstanceError):
            config.days_before_expiry = 10


class TestRollPlanModel:
    """Tests for RollPlan dataclass."""

    def test_roll_plan_creation_calendar_spread(self):
        """RollPlan for calendar spread should have all fields."""
        plan = RollPlan(
            symbol="ESH24",
            strategy=RollStrategy.CALENDAR_SPREAD,
            close_action="SELL ESH24 to close",
            open_action="BUY ESM24 to open",
        )
        assert plan.symbol == "ESH24"
        assert plan.strategy == RollStrategy.CALENDAR_SPREAD
        assert plan.close_action == "SELL ESH24 to close"
        assert plan.open_action == "BUY ESM24 to open"

    def test_roll_plan_creation_close_open(self):
        """RollPlan for close_open strategy should have None open_action."""
        plan = RollPlan(
            symbol="ESH24",
            strategy=RollStrategy.CLOSE_OPEN,
            close_action="SELL ESH24 to close",
            open_action=None,
        )
        assert plan.symbol == "ESH24"
        assert plan.strategy == RollStrategy.CLOSE_OPEN
        assert plan.close_action == "SELL ESH24 to close"
        assert plan.open_action is None

    def test_roll_plan_is_frozen(self):
        """RollPlan should be immutable."""
        plan = RollPlan(
            symbol="ESH24",
            strategy=RollStrategy.CALENDAR_SPREAD,
            close_action="SELL ESH24 to close",
            open_action="BUY ESM24 to open",
        )
        with pytest.raises(FrozenInstanceError):
            plan.symbol = "ESM24"


class TestFuturesRollManagerInit:
    """Tests for FuturesRollManager initialization."""

    def test_default_days_before(self):
        """FuturesRollManager should default to 5 days before expiry."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)
        assert manager.default_days_before == 5

    def test_custom_days_before(self):
        """FuturesRollManager should accept custom days_before."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session, default_days_before=10)
        assert manager.default_days_before == 10

    def test_default_strategy(self):
        """FuturesRollManager should default to CALENDAR_SPREAD strategy."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)
        assert manager.default_strategy == RollStrategy.CALENDAR_SPREAD

    def test_custom_default_strategy(self):
        """FuturesRollManager should accept custom default_strategy."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session, default_strategy=RollStrategy.CLOSE_OPEN)
        assert manager.default_strategy == RollStrategy.CLOSE_OPEN

    def test_negative_days_before_raises(self):
        """FuturesRollManager should raise ValueError for negative days_before."""
        mock_session = MagicMock()
        with pytest.raises(ValueError, match="days_before must be non-negative"):
            FuturesRollManager(session=mock_session, default_days_before=-1)


class TestConfigureUnderlying:
    """Tests for configure_underlying method."""

    def test_configure_underlying_sets_config(self):
        """configure_underlying should store config for underlying."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)

        manager.configure_underlying(
            underlying="ES",
            strategy=RollStrategy.CALENDAR_SPREAD,
            days_before=7,
        )

        config = manager.get_config("ES")
        assert config.underlying == "ES"
        assert config.strategy == RollStrategy.CALENDAR_SPREAD
        assert config.days_before_expiry == 7

    def test_configure_underlying_overwrites_existing(self):
        """configure_underlying should overwrite existing config."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)

        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)
        manager.configure_underlying("ES", RollStrategy.CLOSE_OPEN, 10)

        config = manager.get_config("ES")
        assert config.strategy == RollStrategy.CLOSE_OPEN
        assert config.days_before_expiry == 10

    def test_configure_multiple_underlyings(self):
        """configure_underlying should handle multiple underlyings."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)

        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)
        manager.configure_underlying("NQ", RollStrategy.CLOSE_OPEN, 7)
        manager.configure_underlying("CL", RollStrategy.CALENDAR_SPREAD, 10)

        assert manager.get_config("ES").strategy == RollStrategy.CALENDAR_SPREAD
        assert manager.get_config("NQ").strategy == RollStrategy.CLOSE_OPEN
        assert manager.get_config("CL").days_before_expiry == 10

    def test_configure_underlying_negative_days_raises(self):
        """configure_underlying should raise ValueError for negative days."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)

        with pytest.raises(ValueError, match="days_before must be non-negative"):
            manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, -1)


class TestGetConfig:
    """Tests for get_config method."""

    def test_get_config_returns_default_for_unconfigured(self):
        """get_config should return default config for unconfigured underlying."""
        mock_session = MagicMock()
        manager = FuturesRollManager(
            session=mock_session,
            default_days_before=5,
            default_strategy=RollStrategy.CALENDAR_SPREAD,
        )

        config = manager.get_config("ES")

        assert config.underlying == "ES"
        assert config.strategy == RollStrategy.CALENDAR_SPREAD
        assert config.days_before_expiry == 5

    def test_get_config_returns_configured_values(self):
        """get_config should return configured values for underlying."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)
        manager.configure_underlying("ES", RollStrategy.CLOSE_OPEN, 10)

        config = manager.get_config("ES")

        assert config.underlying == "ES"
        assert config.strategy == RollStrategy.CLOSE_OPEN
        assert config.days_before_expiry == 10

    def test_get_config_default_for_unconfigured_after_other_config(self):
        """get_config should return default for unconfigured even when others exist."""
        mock_session = MagicMock()
        manager = FuturesRollManager(
            session=mock_session,
            default_days_before=5,
            default_strategy=RollStrategy.CALENDAR_SPREAD,
        )
        manager.configure_underlying("ES", RollStrategy.CLOSE_OPEN, 10)

        # NQ is not configured, should get defaults
        config = manager.get_config("NQ")

        assert config.underlying == "NQ"
        assert config.strategy == RollStrategy.CALENDAR_SPREAD
        assert config.days_before_expiry == 5


class TestGetPositionsToRoll:
    """Tests for get_positions_to_roll method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_futures(self, mock_session):
        """Should return empty list when no futures positions exist."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = FuturesRollManager(session=mock_session)
        positions = await manager.get_positions_to_roll()

        assert positions == []
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_only_futures_contracts(self, mock_session):
        """Should return only futures contracts, not options."""
        future_contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date.today() + timedelta(days=3),
            strike=None,
            put_call=None,
        )

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [future_contract]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = FuturesRollManager(session=mock_session)
        positions = await manager.get_positions_to_roll()

        assert len(positions) == 1
        assert positions[0].contract_type == ContractType.FUTURE

    @pytest.mark.asyncio
    async def test_uses_default_days_when_not_specified(self, mock_session):
        """Should use default_days_before when days parameter not provided."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = FuturesRollManager(session=mock_session, default_days_before=7)
        await manager.get_positions_to_roll()

        # Query should have been executed
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_uses_custom_days_parameter(self, mock_session):
        """Should use custom days parameter when provided."""
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        manager = FuturesRollManager(session=mock_session, default_days_before=5)
        await manager.get_positions_to_roll(days=10)

        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_multiple_futures_positions(self, mock_session):
        """Should return all futures positions expiring within window."""
        contracts = [
            DerivativeContract(
                symbol="ESH24",
                underlying="ES",
                contract_type=ContractType.FUTURE,
                expiry=date.today() + timedelta(days=2),
                strike=None,
                put_call=None,
            ),
            DerivativeContract(
                symbol="NQH24",
                underlying="NQ",
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

        manager = FuturesRollManager(session=mock_session)
        positions = await manager.get_positions_to_roll()

        assert len(positions) == 2

    @pytest.mark.asyncio
    async def test_negative_days_raises_error(self, mock_session):
        """Should raise ValueError for negative days parameter."""
        manager = FuturesRollManager(session=mock_session)

        with pytest.raises(ValueError, match="days must be non-negative"):
            await manager.get_positions_to_roll(days=-1)


class TestGenerateRollPlan:
    """Tests for generate_roll_plan method."""

    def test_generate_roll_plan_calendar_spread(self):
        """Should generate calendar spread roll plan."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)
        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)

        contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )

        plan = manager.generate_roll_plan(contract)

        assert plan.symbol == "ESH24"
        assert plan.strategy == RollStrategy.CALENDAR_SPREAD
        assert "SELL" in plan.close_action
        assert "ESH24" in plan.close_action
        assert plan.open_action is not None
        assert "BUY" in plan.open_action

    def test_generate_roll_plan_close_open(self):
        """Should generate close_open roll plan with no open_action."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)
        manager.configure_underlying("ES", RollStrategy.CLOSE_OPEN, 5)

        contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )

        plan = manager.generate_roll_plan(contract)

        assert plan.symbol == "ESH24"
        assert plan.strategy == RollStrategy.CLOSE_OPEN
        assert "SELL" in plan.close_action
        assert "ESH24" in plan.close_action
        assert plan.open_action is None

    def test_generate_roll_plan_uses_default_config(self):
        """Should use default config for unconfigured underlying."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session, default_strategy=RollStrategy.CLOSE_OPEN)

        contract = DerivativeContract(
            symbol="CLH24",
            underlying="CL",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )

        plan = manager.generate_roll_plan(contract)

        assert plan.strategy == RollStrategy.CLOSE_OPEN
        assert plan.open_action is None

    def test_generate_roll_plan_for_different_underlyings(self):
        """Should generate different plans based on underlying config."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)
        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)
        manager.configure_underlying("NQ", RollStrategy.CLOSE_OPEN, 7)

        es_contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )
        nq_contract = DerivativeContract(
            symbol="NQH24",
            underlying="NQ",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )

        es_plan = manager.generate_roll_plan(es_contract)
        nq_plan = manager.generate_roll_plan(nq_contract)

        assert es_plan.strategy == RollStrategy.CALENDAR_SPREAD
        assert es_plan.open_action is not None
        assert nq_plan.strategy == RollStrategy.CLOSE_OPEN
        assert nq_plan.open_action is None

    def test_generate_roll_plan_rejects_non_futures(self):
        """Should raise ValueError for non-futures contracts."""
        mock_session = MagicMock()
        manager = FuturesRollManager(session=mock_session)

        option_contract = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date(2024, 1, 19),
            strike=Decimal("150.00"),
            put_call="call",
        )

        with pytest.raises(ValueError, match="Only futures contracts can be rolled"):
            manager.generate_roll_plan(option_contract)


class TestAcceptanceCriteria:
    """Tests verifying acceptance criteria from spec.md."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_fr017_futures_auto_roll_support(self, mock_session):
        """FR-017: System supports futures auto-roll.

        Verifies that the system can:
        1. Configure roll strategies per underlying
        2. Identify futures expiring within the roll window
        3. Generate roll plans for futures positions
        """
        # Configure roll strategy for ES futures
        manager = FuturesRollManager(session=mock_session, default_days_before=5)
        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)

        # Create futures contract expiring within window
        contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date.today() + timedelta(days=3),
            strike=None,
            put_call=None,
        )

        # Mock get_positions_to_roll to return our contract
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [contract]
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        # Get positions to roll
        positions = await manager.get_positions_to_roll()
        assert len(positions) == 1

        # Generate roll plan
        plan = manager.generate_roll_plan(positions[0])
        assert plan.symbol == "ESH24"
        assert plan.strategy == RollStrategy.CALENDAR_SPREAD
        assert plan.close_action is not None
        assert plan.open_action is not None

    def test_calendar_spread_strategy(self, mock_session):
        """Calendar spread strategy should open position in next contract month."""
        manager = FuturesRollManager(session=mock_session)
        manager.configure_underlying("ES", RollStrategy.CALENDAR_SPREAD, 5)

        contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )

        plan = manager.generate_roll_plan(contract)

        # Calendar spread should have both close and open actions
        assert plan.strategy == RollStrategy.CALENDAR_SPREAD
        assert "SELL" in plan.close_action
        assert plan.open_action is not None
        assert "BUY" in plan.open_action

    def test_close_open_strategy(self, mock_session):
        """Close_open strategy should only close position without opening new one."""
        manager = FuturesRollManager(session=mock_session)
        manager.configure_underlying("ES", RollStrategy.CLOSE_OPEN, 5)

        contract = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date(2024, 3, 15),
            strike=None,
            put_call=None,
        )

        plan = manager.generate_roll_plan(contract)

        # Close_open should only have close action
        assert plan.strategy == RollStrategy.CLOSE_OPEN
        assert "SELL" in plan.close_action
        assert plan.open_action is None


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
    async def test_queries_database_for_futures_to_roll(self, db_session):
        """Should query database and return only futures expiring within window."""
        today = date.today()

        # Futures contract expiring within window
        expiring_future = DerivativeContract(
            symbol="ESH24_EXPIRING",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=today + timedelta(days=3),
            strike=None,
            put_call=None,
        )
        # Futures contract NOT expiring within window
        non_expiring_future = DerivativeContract(
            symbol="ESM24_NOT_EXPIRING",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=today + timedelta(days=30),
            strike=None,
            put_call=None,
        )
        # Option contract (should not be returned)
        option_contract = DerivativeContract(
            symbol="AAPL_OPTION",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=today + timedelta(days=3),
            strike=Decimal("150.00"),
            put_call="call",
        )

        db_session.add(expiring_future)
        db_session.add(non_expiring_future)
        db_session.add(option_contract)
        await db_session.commit()

        manager = FuturesRollManager(session=db_session, default_days_before=5)
        positions = await manager.get_positions_to_roll()

        # Should only return the expiring futures contract
        assert len(positions) == 1
        assert positions[0].symbol == "ESH24_EXPIRING"
        assert positions[0].contract_type == ContractType.FUTURE

    @pytest.mark.asyncio
    async def test_generates_roll_plans_from_database(self, db_session):
        """Should generate roll plans for futures from database."""
        today = date.today()
        contract = DerivativeContract(
            symbol="NQH24",
            underlying="NQ",
            contract_type=ContractType.FUTURE,
            expiry=today + timedelta(days=2),
            strike=None,
            put_call=None,
        )

        db_session.add(contract)
        await db_session.commit()

        manager = FuturesRollManager(session=db_session)
        manager.configure_underlying("NQ", RollStrategy.CALENDAR_SPREAD, 5)

        positions = await manager.get_positions_to_roll()
        assert len(positions) == 1

        plan = manager.generate_roll_plan(positions[0])
        assert plan.symbol == "NQH24"
        assert plan.strategy == RollStrategy.CALENDAR_SPREAD
