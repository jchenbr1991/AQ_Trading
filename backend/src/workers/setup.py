"""Worker setup and lifecycle management for close position flow."""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Protocol

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.db.database import async_session

if TYPE_CHECKING:
    from src.alerts.service import AlertService

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: AsyncIOScheduler | None = None
_outbox_worker_task: asyncio.Task | None = None


class OrderManager(Protocol):
    """Protocol for order submission."""

    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        limit_price: Any,
        close_request_id: str | None = None,
    ) -> Any: ...


class MarketData(Protocol):
    """Protocol for market data."""

    async def get_quote(self, symbol: str) -> Any: ...


class BrokerAPI(Protocol):
    """Protocol for broker API."""

    async def query_order(self, broker_order_id: str) -> Any: ...


async def _run_outbox_worker(
    order_manager: OrderManager,
    market_data: MarketData,
    poll_interval: float = 1.0,
) -> None:
    """Background task that continuously processes outbox events."""
    from src.db.repositories.outbox_repo import OutboxRepository
    from src.workers.outbox_worker import OutboxWorker

    logger.info("Outbox worker started")

    while True:
        try:
            async with async_session() as session:
                repo = OutboxRepository(session)
                events = await repo.claim_pending(limit=1)

                if events:
                    worker = OutboxWorker(session, order_manager, market_data)
                    for event in events:
                        try:
                            await worker.process_event(event)
                        except Exception as e:
                            logger.exception(f"Failed to process event {event.id}: {e}")
                else:
                    await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            logger.info("Outbox worker cancelled")
            break
        except Exception as e:
            logger.exception(f"Outbox worker error: {e}")
            await asyncio.sleep(poll_interval)


async def _run_zombie_detection(broker_api: BrokerAPI) -> None:
    """Scheduled job: detect and fix zombie close requests."""
    from src.workers.reconciler import Reconciler

    try:
        async with async_session() as session:
            reconciler = Reconciler(session, broker_api)
            await reconciler.detect_zombies()
    except Exception as e:
        logger.exception(f"Zombie detection failed: {e}")


async def _run_stuck_order_recovery(broker_api: BrokerAPI) -> None:
    """Scheduled job: recover stuck submitted orders."""
    from src.workers.reconciler import Reconciler

    try:
        async with async_session() as session:
            reconciler = Reconciler(session, broker_api)
            await reconciler.recover_stuck_orders()
    except Exception as e:
        logger.exception(f"Stuck order recovery failed: {e}")


async def _run_partial_fill_retry(broker_api: BrokerAPI) -> None:
    """Scheduled job: retry partial fills."""
    from src.workers.reconciler import Reconciler

    try:
        async with async_session() as session:
            reconciler = Reconciler(session, broker_api)
            await reconciler.retry_partial_fills()
    except Exception as e:
        logger.exception(f"Partial fill retry failed: {e}")


async def _run_invariant_check(broker_api: BrokerAPI) -> None:
    """Scheduled job: check and fix status invariants."""
    from src.workers.reconciler import Reconciler

    try:
        async with async_session() as session:
            reconciler = Reconciler(session, broker_api)
            await reconciler.check_invariants()
    except Exception as e:
        logger.exception(f"Invariant check failed: {e}")


async def _run_outbox_cleanup() -> None:
    """Scheduled job: clean up old outbox events."""
    from src.workers.outbox_cleaner import OutboxCleaner

    try:
        async with async_session() as session:
            cleaner = OutboxCleaner(session)
            count = await cleaner.cleanup()
            if count > 0:
                logger.info(f"Cleaned up {count} old outbox events")
    except Exception as e:
        logger.exception(f"Outbox cleanup failed: {e}")


async def _run_expiration_check(alert_service: "AlertService | None" = None) -> None:
    """Scheduled job: check for expiring derivative positions.

    Runs daily before market open to warn about positions nearing expiry.
    Per SC-011: User receives expiration warning at least 5 days before expiry.
    """
    from src.workers.expiration_worker import ExpirationWorker

    try:
        worker = ExpirationWorker(
            session_factory=async_session,
            alert_service=alert_service,
        )
        alerts = await worker.run_check()
        if alerts:
            logger.info(f"Expiration check found {len(alerts)} expiring positions")
    except Exception as e:
        logger.exception(f"Expiration check failed: {e}")


async def init_workers(
    order_manager: OrderManager,
    market_data: MarketData,
    broker_api: BrokerAPI,
    alert_service: "AlertService | None" = None,
) -> None:
    """Initialize all workers and scheduled jobs.

    Args:
        order_manager: OrderManager instance for order submission
        market_data: MarketData instance for quotes
        broker_api: BrokerAPI instance for order queries
        alert_service: Optional AlertService for expiration alerts
    """
    global _scheduler, _outbox_worker_task

    logger.info("Initializing close position workers...")

    # Start outbox worker background task
    _outbox_worker_task = asyncio.create_task(_run_outbox_worker(order_manager, market_data))

    # Initialize scheduler
    _scheduler = AsyncIOScheduler()

    # Zombie detection: every 1 minute
    _scheduler.add_job(
        lambda: asyncio.create_task(_run_zombie_detection(broker_api)),
        IntervalTrigger(minutes=1),
        id="zombie_detection",
        name="Detect zombie close requests",
    )

    # Stuck order recovery: every 5 minutes
    _scheduler.add_job(
        lambda: asyncio.create_task(_run_stuck_order_recovery(broker_api)),
        IntervalTrigger(minutes=5),
        id="stuck_order_recovery",
        name="Recover stuck orders",
    )

    # Partial fill retry: every 2 minutes
    _scheduler.add_job(
        lambda: asyncio.create_task(_run_partial_fill_retry(broker_api)),
        IntervalTrigger(minutes=2),
        id="partial_fill_retry",
        name="Retry partial fills",
    )

    # Invariant check: every 10 minutes
    _scheduler.add_job(
        lambda: asyncio.create_task(_run_invariant_check(broker_api)),
        IntervalTrigger(minutes=10),
        id="invariant_check",
        name="Check status invariants",
    )

    # Outbox cleanup: daily at 3 AM
    _scheduler.add_job(
        lambda: asyncio.create_task(_run_outbox_cleanup()),
        CronTrigger(hour=3, minute=0),
        id="outbox_cleanup",
        name="Clean up old outbox events",
    )

    # Expiration check: daily at 6 AM (before US market open)
    # Per SC-011: User receives expiration warning at least 5 days before expiry
    _scheduler.add_job(
        lambda: asyncio.create_task(_run_expiration_check(alert_service)),
        CronTrigger(hour=6, minute=0),
        id="expiration_check",
        name="Check for expiring derivative positions",
    )

    _scheduler.start()
    logger.info("Close position workers initialized")


async def shutdown_workers() -> None:
    """Shutdown all workers and scheduled jobs."""
    global _scheduler, _outbox_worker_task

    logger.info("Shutting down close position workers...")

    # Stop scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None

    # Cancel outbox worker
    if _outbox_worker_task is not None:
        _outbox_worker_task.cancel()
        try:
            await _outbox_worker_task
        except asyncio.CancelledError:
            pass
        _outbox_worker_task = None

    logger.info("Close position workers shutdown complete")
