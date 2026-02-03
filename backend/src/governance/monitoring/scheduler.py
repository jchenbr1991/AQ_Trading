"""Scheduled falsifier check runner.

This module provides the FalsifierScheduler class that orchestrates
running all falsifier checks and generating alerts for triggered ones.

Note: This module does NOT implement actual scheduling (no APScheduler
dependency). It provides the run_checks() interface that a scheduler
would call.

Classes:
    FalsifierScheduler: Orchestrates falsifier checks and alert generation

Spec Requirements:
    FR-025: Falsifier checks on configurable schedule
            (default: daily for market, weekly for fundamental)

Example:
    >>> from src.governance.monitoring.scheduler import FalsifierScheduler
    >>> scheduler = FalsifierScheduler(checker=checker, alert_generator=generator)
    >>> results = scheduler.run_checks()
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.governance.monitoring.models import FalsifierCheckResult

if TYPE_CHECKING:
    from src.governance.monitoring.alerts import AlertGenerator
    from src.governance.monitoring.falsifier import FalsifierChecker

logger = logging.getLogger(__name__)


class FalsifierScheduler:
    """Orchestrates falsifier checks and alert generation.

    Runs all falsifier checks via FalsifierChecker.check_all() and
    generates alerts for any triggered falsifiers via AlertGenerator.

    This class does not implement actual scheduling. It provides the
    run_checks() method that would be called by an external scheduler
    (e.g., APScheduler, cron, or a FastAPI background task).

    Attributes:
        checker: FalsifierChecker for running checks.
        alert_generator: AlertGenerator for creating and delivering alerts.

    Example:
        >>> scheduler = FalsifierScheduler(checker, alert_generator)
        >>> results = scheduler.run_checks()
        >>> triggered = [r for r in results if r.triggered]
    """

    def __init__(
        self,
        checker: FalsifierChecker,
        alert_generator: AlertGenerator,
    ) -> None:
        """Initialize FalsifierScheduler.

        Args:
            checker: FalsifierChecker for evaluating falsifiers.
            alert_generator: AlertGenerator for creating alerts.
        """
        self.checker = checker
        self.alert_generator = alert_generator

    def run_checks(self) -> list[FalsifierCheckResult]:
        """Run all falsifier checks and generate alerts for triggered ones.

        Calls FalsifierChecker.check_all() to evaluate all active hypothesis
        falsifiers, then generates alerts for any triggered results via
        AlertGenerator.generate_from_check().

        Returns:
            List of all FalsifierCheckResult objects from the check run.
        """
        logger.info("Starting scheduled falsifier check run")

        results = self.checker.check_all()

        triggered_count = 0
        for result in results:
            if result.triggered:
                triggered_count += 1
                self.alert_generator.generate_from_check(result)

        logger.info(
            f"Falsifier check run complete: {len(results)} checks, " f"{triggered_count} triggered"
        )

        return results


__all__ = ["FalsifierScheduler"]
