"""Reconciliation service for comparing local vs broker state."""

import asyncio
import json
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
        self._running = False
        self._periodic_task: asyncio.Task | None = None

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

        await self._publish_result(result)

        return result

    async def _publish_result(self, result: ReconciliationResult) -> None:
        """Publish reconciliation result to Redis."""
        try:
            await self._redis.publish(
                "reconciliation:result",
                json.dumps(
                    {
                        "run_id": str(result.run_id),
                        "account_id": result.account_id,
                        "timestamp": result.timestamp.isoformat(),
                        "is_clean": result.is_clean,
                        "discrepancy_count": len(result.discrepancies),
                        "positions_checked": result.positions_checked,
                        "duration_ms": result.duration_ms,
                        "context": result.context,
                    }
                ),
            )

            # Publish each discrepancy separately for targeted alerting
            for d in result.discrepancies:
                await self._redis.publish(
                    "reconciliation:discrepancy",
                    json.dumps(
                        {
                            "run_id": str(result.run_id),  # Correlate with result
                            "type": d.type.value,
                            "severity": d.severity.value,
                            "symbol": d.symbol,
                            "local_value": str(d.local_value)
                            if d.local_value is not None
                            else None,
                            "broker_value": str(d.broker_value)
                            if d.broker_value is not None
                            else None,
                            "timestamp": d.timestamp.isoformat(),
                            "account_id": d.account_id,
                        }
                    ),
                )
        except Exception as e:
            logger.error(f"Failed to publish reconciliation result to Redis: {e}")

    async def start(self) -> None:
        """Start periodic reconciliation loop."""
        if self._running:
            return

        self._running = True

        # Run startup reconciliation immediately
        await self.reconcile(context={"trigger": "startup"})

        # Start periodic loop
        self._periodic_task = asyncio.create_task(self._periodic_loop())

    async def stop(self) -> None:
        """Stop periodic loop."""
        self._running = False
        if self._periodic_task:
            self._periodic_task.cancel()
            try:
                await self._periodic_task
            except asyncio.CancelledError:
                pass
            self._periodic_task = None

    async def _periodic_loop(self) -> None:
        """Run reconciliation at configured interval."""
        while self._running:
            await asyncio.sleep(self._config.interval_seconds)
            if not self._running:
                break
            await self.reconcile(context={"trigger": "periodic"})
