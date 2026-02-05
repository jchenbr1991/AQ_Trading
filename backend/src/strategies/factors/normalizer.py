"""Rolling z-score normalizer for factor scores.

Standardizes factor scores to have zero mean and unit variance
using a rolling window of historical values. This ensures factors
with different natural scales (e.g., momentum ~0.01 vs breakout ~0.5)
contribute equally to composite signals.
"""

from collections import defaultdict
from decimal import Decimal

from src.strategies.indicators.volume import _decimal_sqrt


class ScoreNormalizer:
    """Rolling z-score normalizer for factor scores.

    Maintains a rolling window of historical scores per factor
    and normalizes new values to z-scores.

    Args:
        min_periods: Minimum number of observations before normalizing.
        window_size: Maximum history to keep per factor.
    """

    def __init__(self, min_periods: int = 20, window_size: int = 60) -> None:
        self._min_periods = min_periods
        self._window_size = window_size
        self._history: dict[str, list[Decimal]] = defaultdict(list)

    def update(self, factor_name: str, value: Decimal) -> None:
        """Record a new score observation for a factor.

        Args:
            factor_name: Name of the factor (e.g., "momentum_factor").
            value: Raw factor score to record.
        """
        history = self._history[factor_name]
        history.append(value)
        if len(history) > self._window_size:
            history.pop(0)

    def normalize(self, factor_name: str, value: Decimal) -> Decimal | None:
        """Normalize a score to z-score using rolling statistics.

        Args:
            factor_name: Name of the factor.
            value: Raw score to normalize.

        Returns:
            Z-score as Decimal, or None if insufficient history.
            Returns Decimal("0") if std is zero (all values identical).
        """
        history = self._history.get(factor_name)
        if history is None or len(history) < self._min_periods:
            return None

        n = Decimal(len(history))
        mean = sum(history) / n
        variance = sum((v - mean) ** 2 for v in history) / n
        std = _decimal_sqrt(variance)

        if std == Decimal("0"):
            return Decimal("0")

        return (value - mean) / std
