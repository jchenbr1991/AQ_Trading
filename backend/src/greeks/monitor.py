"""Greeks Monitor service for orchestrating Greeks monitoring.

This module provides the GreeksMonitor service that coordinates Greeks calculation,
aggregation, alerting, and persistence.

Dataclasses:
    - MonitorResult: Result of a monitoring cycle

Classes:
    - GreeksMonitor: Orchestrates Greeks monitoring for an account

Functions:
    - load_positions_from_db: Load positions from database and convert to PositionInfo
    - create_greeks_monitor: Factory to create a fully configured GreeksMonitor
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.greeks.aggregator import GreeksAggregator
from src.greeks.alerts import AlertEngine, GreeksAlert
from src.greeks.calculator import GreeksCalculator, PositionInfo
from src.greeks.models import AggregatedGreeks, GreeksLimitsConfig
from src.greeks.repository import GreeksRepository
from src.models.position import AssetType, Position, PositionStatus


@dataclass
class MonitorResult:
    """Result of a monitoring cycle.

    Contains the calculated Greeks for account and strategies,
    any generated alerts, and whether the snapshot was persisted.

    Attributes:
        account_greeks: Aggregated Greeks for the entire account
        strategy_greeks: Dict mapping strategy_id to aggregated Greeks
        alerts: List of generated alerts
        snapshot_saved: Whether the snapshot was persisted to database
    """

    account_greeks: AggregatedGreeks
    strategy_greeks: dict[str, AggregatedGreeks]
    alerts: list[GreeksAlert]
    snapshot_saved: bool


class GreeksMonitor:
    """Orchestrates Greeks monitoring for an account.

    Coordinates:
    - Calculator: Fetches and converts Greeks
    - Aggregator: Sums up to account/strategy level
    - AlertEngine: Detects threshold breaches
    - Repository: Persists snapshots and alerts

    Attributes:
        _account_id: Account identifier
        _config: Greeks limits configuration
        _calculator: Greeks calculator instance
        _aggregator: Greeks aggregator instance
        _alert_engine: Alert engine instance
        _repository: Optional repository for persistence
        _current_greeks: Most recent calculated account Greeks
    """

    def __init__(
        self,
        account_id: str,
        limits_config: GreeksLimitsConfig,
        calculator: GreeksCalculator,
        aggregator: GreeksAggregator,
        alert_engine: AlertEngine,
        repository: GreeksRepository | None = None,
    ):
        """Initialize the GreeksMonitor.

        Args:
            account_id: Account identifier
            limits_config: Configuration for Greeks limits and thresholds
            calculator: GreeksCalculator instance for fetching Greeks
            aggregator: GreeksAggregator for portfolio/strategy aggregation
            alert_engine: AlertEngine for threshold breach detection
            repository: Optional GreeksRepository for persistence
        """
        self._account_id = account_id
        self._config = limits_config
        self._calculator = calculator
        self._aggregator = aggregator
        self._alert_engine = alert_engine
        self._repository = repository
        self._current_greeks: AggregatedGreeks | None = None

    async def check(self, positions: list[PositionInfo]) -> MonitorResult:
        """Run a full monitoring cycle.

        1. Calculate Greeks for all positions
        2. Aggregate to account and strategy levels
        3. Get prev_greeks from repository for ROC
        4. Check for alerts
        5. Save snapshot to repository
        6. Save any alerts to repository

        Args:
            positions: List of PositionInfo to monitor

        Returns:
            MonitorResult with all data
        """
        # Step 1: Calculate Greeks for all positions
        position_greeks = self._calculator.calculate(positions)

        # Step 2: Aggregate to account and strategy levels
        account_greeks, strategy_greeks = self._aggregator.aggregate_by_strategy(
            position_greeks, self._account_id
        )

        # Cache the current Greeks
        self._current_greeks = account_greeks

        # Step 3: Get prev_greeks from repository for ROC detection
        prev_greeks: AggregatedGreeks | None = None
        if self._repository is not None:
            prev_greeks = await self._repository.get_prev_snapshot(
                scope="ACCOUNT",
                scope_id=self._account_id,
                window_seconds=self._config.thresholds.get(
                    list(self._config.thresholds.keys())[0]
                ).rate_window_seconds
                if self._config.thresholds
                else 300,
            )

        # Step 4: Check for alerts
        alerts = self._alert_engine.check_alerts(
            account_greeks, self._config, prev_greeks=prev_greeks
        )

        # Also check strategy-level alerts
        for strategy_id, strat_greeks in strategy_greeks.items():
            # Skip unassigned positions for now
            if strategy_id == "_unassigned_":
                continue
            strat_alerts = self._alert_engine.check_alerts(
                strat_greeks, self._config, prev_greeks=None
            )
            alerts.extend(strat_alerts)

        # Step 5: Save snapshot to repository
        snapshot_saved = False
        if self._repository is not None:
            await self._repository.save_snapshot(account_greeks)
            snapshot_saved = True

            # Also save strategy snapshots
            for strat_greeks in strategy_greeks.values():
                await self._repository.save_snapshot(strat_greeks)

        # Step 6: Save any alerts to repository
        if self._repository is not None:
            for alert in alerts:
                await self._repository.save_alert(alert)

        return MonitorResult(
            account_greeks=account_greeks,
            strategy_greeks=strategy_greeks,
            alerts=alerts,
            snapshot_saved=snapshot_saved,
        )

    def get_current_greeks(self) -> AggregatedGreeks | None:
        """Get the most recent calculated Greeks (in-memory).

        Returns:
            The most recent AggregatedGreeks, or None if no check has been run
        """
        return self._current_greeks


async def load_positions_from_db(session: AsyncSession, account_id: str) -> list[PositionInfo]:
    """Load open positions from database and convert to PositionInfo.

    Filters to:
    - status = 'open'
    - asset_type = 'option'
    - account_id matches

    Args:
        session: SQLAlchemy async session
        account_id: Account identifier to filter by

    Returns:
        List of PositionInfo objects for option positions
    """
    stmt = select(Position).where(
        Position.account_id == account_id,
        Position.asset_type == AssetType.OPTION,
        Position.status == PositionStatus.OPEN,
    )

    result = await session.execute(stmt)
    positions = result.scalars().all()

    position_infos: list[PositionInfo] = []
    for pos in positions:
        # Extract underlying symbol from option symbol
        # Option symbols typically start with underlying (e.g., AAPL240119C00150000)
        underlying = _extract_underlying_symbol(pos.symbol)

        # Convert put_call to option_type string
        option_type = "call" if pos.put_call.value == "call" else "put"

        # Convert expiry to ISO string
        expiry_str = pos.expiry.isoformat() if pos.expiry else ""

        position_info = PositionInfo(
            position_id=pos.id,
            symbol=pos.symbol,
            underlying_symbol=underlying,
            quantity=pos.quantity,
            multiplier=100,  # US options standard multiplier
            option_type=option_type,
            strike=pos.strike or Decimal("0"),
            expiry=expiry_str,
        )
        position_infos.append(position_info)

    return position_infos


def _extract_underlying_symbol(option_symbol: str) -> str:
    """Extract underlying symbol from option symbol.

    OCC option symbols format: AAPL240119C00150000
    - Underlying: First 1-5 chars before date
    - Date: YYMMDD
    - Type: C (call) or P (put)
    - Strike: 8 digits (price * 1000)

    Args:
        option_symbol: The full option symbol

    Returns:
        The underlying stock symbol
    """
    # Simple heuristic: find where digits start for the date
    for i, char in enumerate(option_symbol):
        if char.isdigit():
            return option_symbol[:i]
    return option_symbol[:4]  # Fallback to first 4 chars


def create_greeks_monitor(
    account_id: str,
    session: AsyncSession | None = None,
    config: GreeksLimitsConfig | None = None,
) -> GreeksMonitor:
    """Factory to create a fully configured GreeksMonitor.

    Uses default config if not provided.
    Creates all dependencies (Calculator, Aggregator, AlertEngine, Repository).

    Args:
        account_id: Account identifier
        session: Optional SQLAlchemy session for persistence
        config: Optional GreeksLimitsConfig (uses default if not provided)

    Returns:
        Fully configured GreeksMonitor instance
    """
    # Use provided config or create default
    limits_config = config or GreeksLimitsConfig.default_account_config(account_id)

    # Create dependencies
    calculator = GreeksCalculator()
    aggregator = GreeksAggregator()
    alert_engine = AlertEngine()

    # Create repository if session provided
    repository: GreeksRepository | None = None
    if session is not None:
        repository = GreeksRepository(session)

    return GreeksMonitor(
        account_id=account_id,
        limits_config=limits_config,
        calculator=calculator,
        aggregator=aggregator,
        alert_engine=alert_engine,
        repository=repository,
    )
