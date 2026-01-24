"""Reconciliation service for comparing local vs broker state."""

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from src.broker.query import BrokerQuery
from src.models.position import Position
from src.reconciliation.comparator import Comparator
from src.reconciliation.models import (
    Discrepancy,
    ReconciliationConfig,
    ReconciliationResult,
)

logger = logging.getLogger(__name__)


class PositionProvider(Protocol):
    """Protocol for getting local position/account state."""

    async def get_positions(self, account_id: str) -> list[Position]:
        """Get local positions."""
        ...

    async def get_cash(self, account_id: str) -> Decimal:
        """Get local cash balance."""
        ...

    async def get_equity(self, account_id: str) -> Decimal:
        """Get local total equity."""
        ...


class ReconciliationService:
    """
    Reconciliation service for comparing local vs broker state.

    Runs periodically and on-demand, publishes discrepancies to Redis.
    """

    def __init__(
        self,
        position_provider: PositionProvider,
        broker_query: BrokerQuery,
        redis: Any,  # Redis client
        config: ReconciliationConfig,
    ):
        self._position_provider = position_provider
        self._broker_query = broker_query
        self._redis = redis
        self._config = config
        self._comparator = Comparator(config)

    async def reconcile(self, context: dict[str, Any] | None = None) -> ReconciliationResult:
        """
        Run reconciliation on-demand.
        Returns result with any discrepancies found.
        """
        if context is None:
            context = {"trigger": "on_demand"}

        start_time = time.perf_counter()
        timestamp = datetime.utcnow()
        discrepancies: list[Discrepancy] = []

        # Get local state
        local_positions = await self._position_provider.get_positions(self._config.account_id)
        local_cash = await self._position_provider.get_cash(self._config.account_id)
        local_equity = await self._position_provider.get_equity(self._config.account_id)

        # Get broker state
        broker_positions = await self._broker_query.get_positions(self._config.account_id)
        broker_account = await self._broker_query.get_account(self._config.account_id)

        # Compare positions
        position_discrepancies = self._comparator.compare_positions(
            local_positions, broker_positions
        )
        discrepancies.extend(position_discrepancies)

        # Compare account
        account_discrepancies = self._comparator.compare_account(
            local_cash, local_equity, broker_account
        )
        discrepancies.extend(account_discrepancies)

        # Count unique symbols checked
        local_symbols = {p.symbol for p in local_positions}
        broker_symbols = {p.symbol for p in broker_positions}
        positions_checked = len(local_symbols | broker_symbols)

        duration_ms = (time.perf_counter() - start_time) * 1000

        result = ReconciliationResult(
            account_id=self._config.account_id,
            timestamp=timestamp,
            is_clean=len(discrepancies) == 0,
            discrepancies=discrepancies,
            positions_checked=positions_checked,
            duration_ms=duration_ms,
            context=context,
        )

        # Log discrepancies
        if not result.is_clean:
            for d in discrepancies:
                logger.warning(
                    f"Reconciliation discrepancy: {d.type.value} "
                    f"symbol={d.symbol} local={d.local_value} broker={d.broker_value}"
                )

        return result
