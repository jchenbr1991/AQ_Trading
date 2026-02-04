"""Regime detector for position pacing governance.

This module implements regime detection based on market metrics (volatility,
drawdown). The detected regime state drives position pacing multipliers
but NEVER contributes to alpha.

Classes:
    RegimeDetector: Evaluates market conditions against thresholds to determine
        the current regime state and corresponding pacing multiplier.

Example:
    >>> from src.governance.regime.detector import RegimeDetector
    >>> from src.governance.regime.models import RegimeConfig, RegimeThresholds
    >>> from src.governance.monitoring.metrics import MetricRegistry
    >>> config = RegimeConfig(
    ...     thresholds=RegimeThresholds(
    ...         volatility_transition=0.25, volatility_stress=0.40,
    ...         drawdown_transition=0.10, drawdown_stress=0.20,
    ...     ),
    ...     pacing_multipliers={"NORMAL": 1.0, "TRANSITION": 0.5, "STRESS": 0.1},
    ... )
    >>> registry = MetricRegistry()
    >>> registry.register("portfolio_volatility", lambda window=None: 0.15)
    >>> registry.register("max_drawdown", lambda window=None: 0.05)
    >>> detector = RegimeDetector(config=config, metric_registry=registry)
    >>> snapshot = detector.detect()
    >>> snapshot.state.value
    'NORMAL'
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime

from src.governance.models import RegimeState
from src.governance.monitoring.metrics import MetricRegistry
from src.governance.regime.models import RegimeConfig, RegimeSnapshot

logger = logging.getLogger(__name__)


class RegimeDetector:
    """Evaluates market conditions against thresholds to determine regime state.

    The detector queries a MetricRegistry for portfolio_volatility and
    max_drawdown metrics, then classifies the regime as NORMAL, TRANSITION,
    or STRESS based on configured thresholds.

    The regime state determines position pacing multipliers:
    - NORMAL: Full position sizing (multiplier = 1.0)
    - TRANSITION: Reduced position sizing (multiplier = 0.5)
    - STRESS: Minimal new positions (multiplier = 0.1)

    Detection priority: STRESS > TRANSITION > NORMAL.
    If either volatility OR drawdown exceeds a stress threshold, STRESS wins.
    If either exceeds a transition threshold (but not stress), TRANSITION wins.

    Attributes:
        _config: Regime configuration with thresholds and pacing multipliers.
        _metric_registry: Registry to query for market metrics.
        _previous_state: Previous regime state for transition tracking.
    """

    def __init__(self, config: RegimeConfig, metric_registry: MetricRegistry) -> None:
        """Initialize RegimeDetector.

        Args:
            config: Regime configuration with thresholds and pacing multipliers.
            metric_registry: Registry to query for market metrics.
        """
        self._config = config
        self._metric_registry = metric_registry
        self._previous_state: RegimeState | None = None
        self._lock = threading.Lock()

    def detect(self) -> RegimeSnapshot:
        """Evaluate current market metrics and determine regime state.

        Queries the metric registry for portfolio_volatility and max_drawdown.
        Missing or None metrics are treated as 0.0 (defaulting to NORMAL).

        Logic:
            - If volatility >= stress OR drawdown >= stress -> STRESS
            - If volatility >= transition OR drawdown >= transition -> TRANSITION
            - Otherwise -> NORMAL

        Returns:
            RegimeSnapshot with current state, previous state, metrics,
            and the pacing multiplier for the detected state.
        """
        # Get metrics, defaulting to 0.0 for missing/None values
        volatility = self._get_metric("portfolio_volatility")
        drawdown = self._get_metric("max_drawdown")

        thresholds = self._config.thresholds

        # Determine state: STRESS > TRANSITION > NORMAL
        if volatility >= thresholds.volatility_stress or drawdown >= thresholds.drawdown_stress:
            state = RegimeState.STRESS
        elif (
            volatility >= thresholds.volatility_transition
            or drawdown >= thresholds.drawdown_transition
        ):
            state = RegimeState.TRANSITION
        else:
            state = RegimeState.NORMAL

        # Get pacing multiplier from config
        pacing_multiplier = self._config.pacing_multipliers.get(state.value, 1.0)

        # Build snapshot and update previous state atomically
        with self._lock:
            snapshot = RegimeSnapshot(
                state=state,
                previous_state=self._previous_state,
                changed_at=datetime.utcnow(),
                metrics={
                    "portfolio_volatility": volatility,
                    "max_drawdown": drawdown,
                },
                pacing_multiplier=pacing_multiplier,
            )

            # Log state transitions
            if self._previous_state is not None and self._previous_state != state:
                logger.info(
                    "Regime transition: %s -> %s (vol=%.4f, dd=%.4f, pacing=%.2f)",
                    self._previous_state.value,
                    state.value,
                    volatility,
                    drawdown,
                    pacing_multiplier,
                )

            # Track state for next detection
            self._previous_state = state

        return snapshot

    def _get_metric(self, metric_name: str) -> float:
        """Get a metric value from the registry, defaulting to 0.0.

        Args:
            metric_name: Name of the metric to query.

        Returns:
            The metric value as a float, or 0.0 if unavailable or None.
        """
        value = self._metric_registry.get_value(metric_name)
        if value is None:
            return 0.0
        return float(value)


__all__ = ["RegimeDetector"]
