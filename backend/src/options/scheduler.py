"""Expiration check scheduler with distributed lock support.

This module implements the ExpirationScheduler that runs periodic
expiration checks. It supports both single-instance and multi-instance
deployments using Postgres advisory locks.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.options.checker import ExpirationChecker

logger = logging.getLogger(__name__)

# Optional APScheduler support
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    AsyncIOScheduler = None
    CronTrigger = None


class ExpirationScheduler:
    """Options expiration check scheduler.

    Deployment options:
    1. Single instance: Set use_distributed_lock=False
    2. Multi-instance: Set use_distributed_lock=True (uses Postgres advisory lock)

    Why Postgres Advisory Lock:
    - No additional Redis infrastructure required
    - Works with existing database connection
    - Lock auto-releases on connection close
    - Minimal performance overhead
    """

    def __init__(
        self,
        checker: ExpirationChecker,
        account_id: str,
        session: AsyncSession,
        market_tz: ZoneInfo = ZoneInfo("America/New_York"),
        use_distributed_lock: bool = False,
    ):
        """Initialize scheduler.

        Args:
            checker: ExpirationChecker instance
            account_id: Account to check expirations for
            session: SQLAlchemy async session for advisory lock
            market_tz: Market timezone (default: US East)
            use_distributed_lock: Whether to use Postgres advisory lock
        """
        self.checker = checker
        self.account_id = account_id
        self.session = session
        self.market_tz = market_tz
        self.use_distributed_lock = use_distributed_lock

        # Optional APScheduler
        if HAS_APSCHEDULER:
            self.scheduler = AsyncIOScheduler(timezone=market_tz)
        else:
            self.scheduler = None

        # Postgres advisory lock key (fixed hash to avoid conflicts)
        self.lock_key = hash("options_expiration_check") % (2**31)

    async def _run_check_with_lock(self) -> dict:
        """Run expiration check with optional distributed lock.

        Returns:
            Stats dict with 'executed' flag indicating if check ran
        """
        if self.use_distributed_lock:
            lock_acquired = await self._try_acquire_lock()
            if not lock_acquired:
                logger.info(
                    f"Expiration check skipped: lock held by another instance "
                    f"(lock_key={self.lock_key})"
                )
                return {"executed": False, "reason": "lock_held_by_another_instance"}

            try:
                stats = await self.checker.check_expirations(self.account_id)
                stats["executed"] = True
                return stats
            finally:
                await self._release_lock()
        else:
            # Single instance deployment, run directly
            stats = await self.checker.check_expirations(self.account_id)
            stats["executed"] = True
            return stats

    async def _try_acquire_lock(self) -> bool:
        """Try to acquire Postgres advisory lock.

        Uses pg_try_advisory_lock() for non-blocking lock acquisition.
        Returns False immediately if lock is held by another session.

        Lock lifecycle:
        - Lock is tied to database session (connection)
        - Auto-releases on connection close
        - No explicit timeout needed

        Returns:
            True if lock acquired, False if held by another session
        """
        sql = text("SELECT pg_try_advisory_lock(:lock_key)")
        result = await self.session.execute(sql, {"lock_key": self.lock_key})
        acquired = result.scalar()

        if acquired:
            logger.info(f"Acquired advisory lock: lock_key={self.lock_key}")
        else:
            logger.debug(f"Failed to acquire lock: lock_key={self.lock_key}")

        return acquired

    async def _release_lock(self) -> None:
        """Release Postgres advisory lock.

        Note: Only the session holding the lock can release it.
        """
        sql = text("SELECT pg_advisory_unlock(:lock_key)")
        result = await self.session.execute(sql, {"lock_key": self.lock_key})
        released = result.scalar()

        if released:
            logger.info(f"Released advisory lock: lock_key={self.lock_key}")
        else:
            logger.warning(f"Failed to release lock (may not be held): lock_key={self.lock_key}")

    def start(self) -> None:
        """Start the scheduler.

        Schedules:
        - Immediate check on startup
        - Daily at 8:00 AM market time (before market open)
        - Daily at 3:00 PM market time (before market close)

        Requires APScheduler to be installed.
        """
        if not HAS_APSCHEDULER or self.scheduler is None:
            raise RuntimeError(
                "APScheduler is required for scheduling. " "Install with: pip install apscheduler"
            )

        # Immediate check on startup
        logger.info("Scheduling immediate expiration check on startup")
        self.scheduler.add_job(
            self._run_check_with_lock,
            trigger="date",
            run_date=datetime.now(self.market_tz),
            id="startup_check",
        )

        # Daily morning check (8:00 AM, before market open)
        self.scheduler.add_job(
            self._run_check_with_lock,
            trigger=CronTrigger(hour=8, minute=0, timezone=self.market_tz),
            id="daily_morning_check",
        )

        # Daily closing check (3:00 PM, before market close)
        self.scheduler.add_job(
            self._run_check_with_lock,
            trigger=CronTrigger(hour=15, minute=0, timezone=self.market_tz),
            id="daily_closing_check",
        )

        self.scheduler.start()
        logger.info("ExpirationScheduler started")

    def shutdown(self) -> None:
        """Shutdown the scheduler."""
        if self.scheduler is not None:
            self.scheduler.shutdown()
            logger.info("ExpirationScheduler shut down")
