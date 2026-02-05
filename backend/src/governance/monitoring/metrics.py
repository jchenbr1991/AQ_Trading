"""MetricRegistry for registering and querying metric providers.

This module provides a registry pattern for metric providers. Each metric
(e.g., rolling_ic_mean, win_rate, sharpe_ratio) can be registered with a
callable that returns the current value for that metric.

Classes:
    MetricRegistry: Registry for metric provider functions

Example:
    >>> from src.governance.monitoring.metrics import MetricRegistry
    >>> registry = MetricRegistry()
    >>> registry.register("rolling_ic_mean", lambda window=None: 0.05)
    >>> registry.get_value("rolling_ic_mean", window="6m")
    0.05
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class MetricRegistry:
    """Registry for metric provider functions.

    Allows registering callable metric providers that return the current
    value for a named metric. Providers accept an optional window parameter
    for time-windowed calculations.

    The registry handles provider exceptions gracefully, returning None
    if a provider raises an error.

    Attributes:
        _providers: Internal dict mapping metric names to provider callables.

    Example:
        >>> registry = MetricRegistry()
        >>> registry.register("rolling_ic_mean", lambda window=None: 0.05)
        >>> registry.get_value("rolling_ic_mean")
        0.05
    """

    def __init__(self) -> None:
        """Initialize an empty MetricRegistry."""
        self._providers: dict[str, Callable] = {}
        self._lock = threading.Lock()

    def register(self, metric_name: str, provider: Callable) -> None:
        """Register a metric provider function.

        If a provider for the same metric name already exists, it will be
        overwritten with the new provider. Thread-safe.

        Args:
            metric_name: The name of the metric (e.g., "rolling_ic_mean").
            provider: Callable that accepts an optional window keyword argument
                      and returns a float or None.
        """
        with self._lock:
            self._providers[metric_name] = provider
        logger.debug(f"Registered metric provider: {metric_name}")

    def get_value(self, metric_name: str, window: str | None = None) -> float | None:
        """Get current value for a metric.

        Calls the registered provider for the given metric name.
        Returns None if the metric is not registered or if the provider
        raises an exception. Thread-safe.

        Args:
            metric_name: The name of the metric to query.
            window: Optional lookback window to pass to the provider.

        Returns:
            The metric value as a float, or None if unavailable.
        """
        with self._lock:
            provider = self._providers.get(metric_name)
        if provider is None:
            logger.debug(f"No provider registered for metric: {metric_name}")
            return None

        try:
            return provider(window=window)
        except Exception:
            logger.warning(
                f"Metric provider for '{metric_name}' raised an exception",
                exc_info=True,
            )
            return None

    def has_metric(self, metric_name: str) -> bool:
        """Check if a metric provider is registered. Thread-safe.

        Args:
            metric_name: The name of the metric to check.

        Returns:
            True if a provider is registered for this metric, False otherwise.
        """
        with self._lock:
            return metric_name in self._providers


__all__ = ["MetricRegistry"]
