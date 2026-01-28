"""Tests for Greeks Monitor service.

Tests cover:
- Task 21: GreeksMonitor class orchestrating Greeks monitoring
  - MonitorResult dataclass
  - GreeksMonitor.check full cycle (mock dependencies)
  - get_current_greeks returns cached value
- Task 22: load_positions_from_db helper
- Task 23: create_greeks_monitor factory function
"""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_position_info(
    position_id: int = 1,
    symbol: str = "AAPL240119C00150000",
    underlying_symbol: str = "AAPL",
    quantity: int = 10,
    multiplier: int = 100,
    option_type: str = "call",
    strike: Decimal = Decimal("150"),
    expiry: str = "2024-01-19",
    strategy_id: str | None = None,
):
    """Factory function to create PositionInfo for testing."""
    from src.greeks.calculator import PositionInfo

    return PositionInfo(
        position_id=position_id,
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        quantity=quantity,
        multiplier=multiplier,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
    )


def _make_position_greeks(
    position_id: int = 1,
    symbol: str = "AAPL240119C00150000",
    underlying_symbol: str = "AAPL",
    quantity: int = 10,
    multiplier: int = 100,
    option_type: str = "call",
    strike: Decimal = Decimal("150"),
    expiry: str = "2024-01-19",
    underlying_price: Decimal = Decimal("175"),
    dollar_delta: Decimal = Decimal("10000"),
    gamma_dollar: Decimal = Decimal("500"),
    gamma_pnl_1pct: Decimal = Decimal("2.5"),
    vega_per_1pct: Decimal = Decimal("200"),
    theta_per_day: Decimal = Decimal("-50"),
    valid: bool = True,
    strategy_id: str | None = None,
):
    """Factory function to create PositionGreeks for testing."""
    from src.greeks.models import GreeksDataSource, PositionGreeks

    return PositionGreeks(
        position_id=position_id,
        symbol=symbol,
        underlying_symbol=underlying_symbol,
        quantity=quantity,
        multiplier=multiplier,
        option_type=option_type,
        strike=strike,
        expiry=expiry,
        underlying_price=underlying_price,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        source=GreeksDataSource.FUTU,
        model=None,
        valid=valid,
        strategy_id=strategy_id,
    )


def _make_aggregated_greeks(
    scope: str = "ACCOUNT",
    scope_id: str = "acc_001",
    strategy_id: str | None = None,
    dollar_delta: Decimal = Decimal("0"),
    gamma_dollar: Decimal = Decimal("0"),
    vega_per_1pct: Decimal = Decimal("0"),
    theta_per_day: Decimal = Decimal("0"),
    valid_legs_count: int = 0,
    total_legs_count: int = 0,
    as_of_ts: datetime | None = None,
):
    """Factory function to create AggregatedGreeks for testing."""
    from src.greeks.models import AggregatedGreeks

    return AggregatedGreeks(
        scope=scope,
        scope_id=scope_id,
        strategy_id=strategy_id,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        valid_legs_count=valid_legs_count,
        total_legs_count=total_legs_count,
        as_of_ts=as_of_ts or datetime.now(timezone.utc),
    )


class TestMonitorResult:
    """Tests for MonitorResult dataclass - Task 21."""

    def test_monitor_result_creation(self):
        """MonitorResult can be created with required fields."""
        from src.greeks.monitor import MonitorResult

        account_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id="acc_001",
            dollar_delta=Decimal("45000"),
        )
        strategy_greeks = {
            "momentum_v1": _make_aggregated_greeks(
                scope="STRATEGY",
                scope_id="momentum_v1",
                dollar_delta=Decimal("45000"),
            )
        }
        alerts = []

        result = MonitorResult(
            account_greeks=account_greeks,
            strategy_greeks=strategy_greeks,
            alerts=alerts,
            snapshot_saved=True,
        )

        assert result.account_greeks == account_greeks
        assert result.strategy_greeks == strategy_greeks
        assert result.alerts == []
        assert result.snapshot_saved is True

    def test_monitor_result_with_alerts(self):
        """MonitorResult can include alerts."""
        from src.greeks.alerts import GreeksAlert
        from src.greeks.models import GreeksLevel, RiskMetric
        from src.greeks.monitor import MonitorResult

        account_greeks = _make_aggregated_greeks()

        alert = GreeksAlert(
            alert_id="test-id",
            alert_type="THRESHOLD",
            scope="ACCOUNT",
            scope_id="acc_001",
            metric=RiskMetric.DELTA,
            level=GreeksLevel.WARN,
            current_value=Decimal("45000"),
            threshold_value=Decimal("40000"),
            message="Test alert",
            created_at=datetime.now(timezone.utc),
        )

        result = MonitorResult(
            account_greeks=account_greeks,
            strategy_greeks={},
            alerts=[alert],
            snapshot_saved=True,
        )

        assert len(result.alerts) == 1
        assert result.alerts[0].metric == RiskMetric.DELTA


class TestGreeksMonitor:
    """Tests for GreeksMonitor class - Task 21."""

    def test_greeks_monitor_initialization(self):
        """GreeksMonitor can be initialized with required dependencies."""
        from src.greeks.aggregator import GreeksAggregator
        from src.greeks.alerts import AlertEngine
        from src.greeks.calculator import GreeksCalculator
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"
        config = GreeksLimitsConfig.default_account_config(account_id)
        calculator = GreeksCalculator()
        aggregator = GreeksAggregator()
        alert_engine = AlertEngine()

        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=config,
            calculator=calculator,
            aggregator=aggregator,
            alert_engine=alert_engine,
        )

        assert monitor._account_id == account_id
        assert monitor._config == config
        assert monitor._calculator == calculator
        assert monitor._aggregator == aggregator
        assert monitor._alert_engine == alert_engine

    def test_greeks_monitor_initialization_with_repository(self):
        """GreeksMonitor can be initialized with optional repository."""
        from src.greeks.aggregator import GreeksAggregator
        from src.greeks.alerts import AlertEngine
        from src.greeks.calculator import GreeksCalculator
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"
        config = GreeksLimitsConfig.default_account_config(account_id)
        calculator = GreeksCalculator()
        aggregator = GreeksAggregator()
        alert_engine = AlertEngine()
        repository = MagicMock()  # Mock repository

        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=config,
            calculator=calculator,
            aggregator=aggregator,
            alert_engine=alert_engine,
            repository=repository,
        )

        assert monitor._repository == repository

    @pytest.mark.asyncio
    async def test_greeks_monitor_check_full_cycle(self):
        """GreeksMonitor.check performs full monitoring cycle."""
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"
        config = GreeksLimitsConfig.default_account_config(account_id)

        # Create mock calculator that returns position Greeks
        position_greeks = [
            _make_position_greeks(
                position_id=1,
                dollar_delta=Decimal("25000"),
                strategy_id="momentum_v1",
            ),
            _make_position_greeks(
                position_id=2,
                dollar_delta=Decimal("20000"),
                strategy_id="momentum_v1",
            ),
        ]
        mock_calculator = MagicMock()
        mock_calculator.calculate.return_value = position_greeks

        # Create mock aggregator
        account_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id=account_id,
            dollar_delta=Decimal("45000"),
            valid_legs_count=2,
            total_legs_count=2,
        )
        strategy_greeks = {
            "momentum_v1": _make_aggregated_greeks(
                scope="STRATEGY",
                scope_id="momentum_v1",
                dollar_delta=Decimal("45000"),
            )
        }
        mock_aggregator = MagicMock()
        mock_aggregator.aggregate_by_strategy.return_value = (account_greeks, strategy_greeks)

        # Create mock alert engine
        mock_alert_engine = MagicMock()
        mock_alert_engine.check_alerts.return_value = []

        # Create mock repository
        mock_repository = AsyncMock()
        mock_repository.get_prev_snapshot.return_value = None
        mock_repository.save_snapshot.return_value = MagicMock()
        mock_repository.save_alert.return_value = MagicMock()

        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=config,
            calculator=mock_calculator,
            aggregator=mock_aggregator,
            alert_engine=mock_alert_engine,
            repository=mock_repository,
        )

        positions = [
            _make_position_info(position_id=1),
            _make_position_info(position_id=2),
        ]

        result = await monitor.check(positions)

        # Verify calculator was called
        mock_calculator.calculate.assert_called_once_with(positions)

        # Verify aggregator was called
        mock_aggregator.aggregate_by_strategy.assert_called_once()

        # Verify alert engine was called
        assert mock_alert_engine.check_alerts.called

        # Verify repository was called
        mock_repository.save_snapshot.assert_called()

        # Verify result
        assert result.account_greeks == account_greeks
        assert result.strategy_greeks == strategy_greeks
        assert result.snapshot_saved is True

    @pytest.mark.asyncio
    async def test_greeks_monitor_check_generates_alerts(self):
        """GreeksMonitor.check generates and saves alerts."""
        from src.greeks.alerts import GreeksAlert
        from src.greeks.models import GreeksLevel, GreeksLimitsConfig, RiskMetric
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"
        config = GreeksLimitsConfig.default_account_config(account_id)

        # Create mock dependencies
        mock_calculator = MagicMock()
        mock_calculator.calculate.return_value = [
            _make_position_greeks(dollar_delta=Decimal("45000"))
        ]

        account_greeks = _make_aggregated_greeks(
            scope="ACCOUNT",
            scope_id=account_id,
            dollar_delta=Decimal("45000"),
        )
        mock_aggregator = MagicMock()
        mock_aggregator.aggregate_by_strategy.return_value = (account_greeks, {})

        # Create alert to be returned
        alert = GreeksAlert(
            alert_id="test-id",
            alert_type="THRESHOLD",
            scope="ACCOUNT",
            scope_id=account_id,
            metric=RiskMetric.DELTA,
            level=GreeksLevel.WARN,
            current_value=Decimal("45000"),
            threshold_value=Decimal("40000"),
            message="Delta exceeded WARN threshold",
            created_at=datetime.now(timezone.utc),
        )
        mock_alert_engine = MagicMock()
        mock_alert_engine.check_alerts.return_value = [alert]

        mock_repository = AsyncMock()
        mock_repository.get_prev_snapshot.return_value = None
        mock_repository.save_snapshot.return_value = MagicMock()
        mock_repository.save_alert.return_value = MagicMock()

        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=config,
            calculator=mock_calculator,
            aggregator=mock_aggregator,
            alert_engine=mock_alert_engine,
            repository=mock_repository,
        )

        result = await monitor.check([_make_position_info()])

        # Verify alerts were saved
        mock_repository.save_alert.assert_called_once()

        # Verify result contains alerts
        assert len(result.alerts) == 1
        assert result.alerts[0].metric == RiskMetric.DELTA

    @pytest.mark.asyncio
    async def test_greeks_monitor_check_uses_prev_snapshot_for_roc(self):
        """GreeksMonitor.check retrieves prev_snapshot for ROC detection."""
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"
        config = GreeksLimitsConfig.default_account_config(account_id)

        mock_calculator = MagicMock()
        mock_calculator.calculate.return_value = [_make_position_greeks()]

        account_greeks = _make_aggregated_greeks()
        mock_aggregator = MagicMock()
        mock_aggregator.aggregate_by_strategy.return_value = (account_greeks, {})

        mock_alert_engine = MagicMock()
        mock_alert_engine.check_alerts.return_value = []

        # Create prev_greeks to be returned by repository
        prev_greeks = _make_aggregated_greeks(dollar_delta=Decimal("30000"))

        mock_repository = AsyncMock()
        mock_repository.get_prev_snapshot.return_value = prev_greeks
        mock_repository.save_snapshot.return_value = MagicMock()

        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=config,
            calculator=mock_calculator,
            aggregator=mock_aggregator,
            alert_engine=mock_alert_engine,
            repository=mock_repository,
        )

        await monitor.check([_make_position_info()])

        # Verify get_prev_snapshot was called
        mock_repository.get_prev_snapshot.assert_called()

        # Verify alert engine received prev_greeks
        call_args = mock_alert_engine.check_alerts.call_args
        assert call_args.kwargs.get("prev_greeks") == prev_greeks

    @pytest.mark.asyncio
    async def test_greeks_monitor_check_without_repository(self):
        """GreeksMonitor.check works without repository (no persistence)."""
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"
        config = GreeksLimitsConfig.default_account_config(account_id)

        mock_calculator = MagicMock()
        mock_calculator.calculate.return_value = [_make_position_greeks()]

        account_greeks = _make_aggregated_greeks()
        mock_aggregator = MagicMock()
        mock_aggregator.aggregate_by_strategy.return_value = (account_greeks, {})

        mock_alert_engine = MagicMock()
        mock_alert_engine.check_alerts.return_value = []

        # No repository
        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=config,
            calculator=mock_calculator,
            aggregator=mock_aggregator,
            alert_engine=mock_alert_engine,
            repository=None,
        )

        result = await monitor.check([_make_position_info()])

        # Should work without errors
        assert result.account_greeks == account_greeks
        assert result.snapshot_saved is False  # No repository to save

    def test_get_current_greeks_returns_none_initially(self):
        """get_current_greeks returns None when no check has been run."""
        from src.greeks.aggregator import GreeksAggregator
        from src.greeks.alerts import AlertEngine
        from src.greeks.calculator import GreeksCalculator
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        monitor = GreeksMonitor(
            account_id="acc_001",
            limits_config=GreeksLimitsConfig.default_account_config("acc_001"),
            calculator=GreeksCalculator(),
            aggregator=GreeksAggregator(),
            alert_engine=AlertEngine(),
        )

        assert monitor.get_current_greeks() is None

    @pytest.mark.asyncio
    async def test_get_current_greeks_returns_cached_value(self):
        """get_current_greeks returns the most recent calculated Greeks."""
        from src.greeks.models import GreeksLimitsConfig
        from src.greeks.monitor import GreeksMonitor

        account_id = "acc_001"

        mock_calculator = MagicMock()
        mock_calculator.calculate.return_value = [_make_position_greeks()]

        account_greeks = _make_aggregated_greeks(dollar_delta=Decimal("45000"))
        mock_aggregator = MagicMock()
        mock_aggregator.aggregate_by_strategy.return_value = (account_greeks, {})

        mock_alert_engine = MagicMock()
        mock_alert_engine.check_alerts.return_value = []

        monitor = GreeksMonitor(
            account_id=account_id,
            limits_config=GreeksLimitsConfig.default_account_config(account_id),
            calculator=mock_calculator,
            aggregator=mock_aggregator,
            alert_engine=mock_alert_engine,
        )

        await monitor.check([_make_position_info()])

        current = monitor.get_current_greeks()
        assert current is not None
        assert current.dollar_delta == Decimal("45000")


class TestLoadPositionsFromDb:
    """Tests for load_positions_from_db helper - Task 22."""

    @pytest.mark.asyncio
    async def test_load_positions_from_db_filters_by_account(self, db_session):
        """load_positions_from_db filters by account_id."""
        from datetime import date
        from decimal import Decimal

        from src.greeks.monitor import load_positions_from_db

        # Create account first
        from src.models.account import Account
        from src.models.position import AssetType, Position, PositionStatus, PutCall

        account = Account(account_id="acc_001", broker="futu")
        db_session.add(account)
        await db_session.commit()

        # Create option position for acc_001
        position1 = Position(
            account_id="acc_001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            status=PositionStatus.OPEN,
            quantity=10,
            strike=Decimal("150"),
            expiry=date(2024, 1, 19),
            put_call=PutCall.CALL,
        )
        db_session.add(position1)
        await db_session.commit()

        positions = await load_positions_from_db(db_session, "acc_001")

        assert len(positions) == 1
        assert positions[0].position_id == position1.id

    @pytest.mark.asyncio
    async def test_load_positions_from_db_filters_options_only(self, db_session):
        """load_positions_from_db filters to asset_type=option."""
        from datetime import date
        from decimal import Decimal

        from src.greeks.monitor import load_positions_from_db
        from src.models.account import Account
        from src.models.position import AssetType, Position, PositionStatus, PutCall

        # Create account
        account = Account(account_id="acc_001", broker="futu")
        db_session.add(account)
        await db_session.commit()

        # Create stock position (should be filtered out)
        stock = Position(
            account_id="acc_001",
            symbol="AAPL",
            asset_type=AssetType.STOCK,
            status=PositionStatus.OPEN,
            quantity=100,
        )
        # Create option position
        option = Position(
            account_id="acc_001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            status=PositionStatus.OPEN,
            quantity=10,
            strike=Decimal("150"),
            expiry=date(2024, 1, 19),
            put_call=PutCall.CALL,
        )
        db_session.add_all([stock, option])
        await db_session.commit()

        positions = await load_positions_from_db(db_session, "acc_001")

        assert len(positions) == 1
        assert "C00150000" in positions[0].symbol

    @pytest.mark.asyncio
    async def test_load_positions_from_db_filters_open_status(self, db_session):
        """load_positions_from_db filters to status=open."""
        from datetime import date
        from decimal import Decimal

        from src.greeks.monitor import load_positions_from_db
        from src.models.account import Account
        from src.models.position import AssetType, Position, PositionStatus, PutCall

        # Create account
        account = Account(account_id="acc_001", broker="futu")
        db_session.add(account)
        await db_session.commit()

        # Create closed position (should be filtered out)
        closed = Position(
            account_id="acc_001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            status=PositionStatus.CLOSED,
            quantity=10,
            strike=Decimal("150"),
            expiry=date(2024, 1, 19),
            put_call=PutCall.CALL,
        )
        # Create open position
        open_pos = Position(
            account_id="acc_001",
            symbol="AAPL240119P00140000",
            asset_type=AssetType.OPTION,
            status=PositionStatus.OPEN,
            quantity=5,
            strike=Decimal("140"),
            expiry=date(2024, 1, 19),
            put_call=PutCall.PUT,
        )
        db_session.add_all([closed, open_pos])
        await db_session.commit()

        positions = await load_positions_from_db(db_session, "acc_001")

        assert len(positions) == 1
        assert "P00140000" in positions[0].symbol

    @pytest.mark.asyncio
    async def test_load_positions_from_db_converts_to_position_info(self, db_session):
        """load_positions_from_db returns PositionInfo objects."""
        from datetime import date
        from decimal import Decimal

        from src.greeks.calculator import PositionInfo
        from src.greeks.monitor import load_positions_from_db
        from src.models.account import Account
        from src.models.position import AssetType, Position, PositionStatus, PutCall

        # Create account
        account = Account(account_id="acc_001", broker="futu")
        db_session.add(account)
        await db_session.commit()

        # Create option position
        position = Position(
            account_id="acc_001",
            symbol="AAPL240119C00150000",
            asset_type=AssetType.OPTION,
            status=PositionStatus.OPEN,
            quantity=10,
            strike=Decimal("150.00"),
            expiry=date(2024, 1, 19),
            put_call=PutCall.CALL,
            strategy_id="momentum_v1",
        )
        db_session.add(position)
        await db_session.commit()

        positions = await load_positions_from_db(db_session, "acc_001")

        assert len(positions) == 1
        assert isinstance(positions[0], PositionInfo)
        assert positions[0].position_id == position.id
        assert positions[0].symbol == "AAPL240119C00150000"
        assert positions[0].quantity == 10
        assert positions[0].strike == Decimal("150.00")
        assert positions[0].option_type == "call"
        assert positions[0].multiplier == 100  # Default US options

    @pytest.mark.asyncio
    async def test_load_positions_from_db_returns_empty_for_no_positions(self, db_session):
        """load_positions_from_db returns empty list when no positions."""
        from src.greeks.monitor import load_positions_from_db
        from src.models.account import Account

        # Create account with no positions
        account = Account(account_id="acc_001", broker="futu")
        db_session.add(account)
        await db_session.commit()

        positions = await load_positions_from_db(db_session, "acc_001")

        assert positions == []


class TestCreateGreeksMonitor:
    """Tests for create_greeks_monitor factory function - Task 23."""

    def test_create_greeks_monitor_with_defaults(self):
        """create_greeks_monitor creates monitor with default config."""
        from src.greeks.monitor import GreeksMonitor, create_greeks_monitor

        monitor = create_greeks_monitor(account_id="acc_001")

        assert isinstance(monitor, GreeksMonitor)
        assert monitor._account_id == "acc_001"
        assert monitor._config is not None
        assert monitor._calculator is not None
        assert monitor._aggregator is not None
        assert monitor._alert_engine is not None

    def test_create_greeks_monitor_with_custom_config(self):
        """create_greeks_monitor uses provided config."""
        from decimal import Decimal

        from src.greeks.models import (
            GreeksLimitsConfig,
            GreeksThresholdConfig,
            RiskMetric,
        )
        from src.greeks.monitor import create_greeks_monitor

        custom_config = GreeksLimitsConfig(
            scope="ACCOUNT",
            scope_id="acc_001",
            thresholds={
                RiskMetric.DELTA: GreeksThresholdConfig(
                    metric=RiskMetric.DELTA,
                    limit=Decimal("100000"),  # Custom limit
                ),
            },
        )

        monitor = create_greeks_monitor(
            account_id="acc_001",
            config=custom_config,
        )

        assert monitor._config == custom_config
        assert monitor._config.thresholds[RiskMetric.DELTA].limit == Decimal("100000")

    @pytest.mark.asyncio
    async def test_create_greeks_monitor_with_session(self, db_session):
        """create_greeks_monitor creates repository when session provided."""
        from src.greeks.monitor import create_greeks_monitor

        monitor = create_greeks_monitor(
            account_id="acc_001",
            session=db_session,
        )

        assert monitor._repository is not None

    def test_create_greeks_monitor_without_session(self):
        """create_greeks_monitor sets repository to None when no session."""
        from src.greeks.monitor import create_greeks_monitor

        monitor = create_greeks_monitor(account_id="acc_001")

        assert monitor._repository is None
