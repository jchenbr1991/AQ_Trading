# backend/src/strategies/factors/composite.py
"""Composite factor combining Momentum and Breakout factors.

Formula: composite = w_mom * momentum_factor + w_brk * breakout_factor

Default weights: w_mom=0.5, w_brk=0.5

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from decimal import Decimal

from src.strategies.factors.base import BaseFactor, FactorResult


class CompositeFactor(BaseFactor):
    """Composite factor combining Momentum and Breakout factors.

    This is the final factor used for trading decisions. It combines:
    - momentum_factor: Overall price momentum signal
    - breakout_factor: Breakout potential signal

    The composite score is compared against entry/exit thresholds
    to generate trading signals.

    Example:
        >>> factor = CompositeFactor()
        >>> indicators = {
        ...     "momentum_factor": Decimal("0.035"),
        ...     "breakout_factor": Decimal("0.74"),
        ... }
        >>> result = factor.calculate(indicators)
        >>> result.score
        Decimal('0.3875')  # 0.5 * 0.035 + 0.5 * 0.74
    """

    # Component factor names
    MOMENTUM_KEY = "momentum_factor"
    BREAKOUT_KEY = "breakout_factor"

    def __init__(
        self,
        momentum_weight: Decimal = Decimal("0.5"),
        breakout_weight: Decimal = Decimal("0.5"),
    ) -> None:
        """Initialize composite factor with configurable weights.

        Args:
            momentum_weight: Weight for momentum factor. Default: 0.5
            breakout_weight: Weight for breakout factor. Default: 0.5

        Note:
            Weights do not need to sum to 1.0, but are typically normalized.
        """
        self._momentum_weight = momentum_weight
        self._breakout_weight = breakout_weight

    @property
    def weights(self) -> dict[str, Decimal]:
        """Current weight configuration."""
        return {
            self.MOMENTUM_KEY: self._momentum_weight,
            self.BREAKOUT_KEY: self._breakout_weight,
        }

    def update_weights(
        self,
        momentum_weight: Decimal | None = None,
        breakout_weight: Decimal | None = None,
    ) -> None:
        """Update factor weights dynamically.

        Allows IC-based weight calculation to update weights during runtime.

        Args:
            momentum_weight: New weight for momentum factor. None = keep current.
            breakout_weight: New weight for breakout factor. None = keep current.
        """
        if momentum_weight is not None:
            self._momentum_weight = momentum_weight
        if breakout_weight is not None:
            self._breakout_weight = breakout_weight

    def calculate(
        self, indicators: dict[str, Decimal | None]
    ) -> FactorResult | None:
        """Calculate composite factor from sub-factor scores.

        Args:
            indicators: Dictionary containing:
                - "momentum_factor": Momentum factor score (Decimal or None)
                - "breakout_factor": Breakout factor score (Decimal or None)

        Returns:
            FactorResult with composite score, component values, and weights,
            or None if any required factor is None.
        """
        momentum_value = indicators.get(self.MOMENTUM_KEY)
        breakout_value = indicators.get(self.BREAKOUT_KEY)

        # Return None if any required factor is missing or None
        if momentum_value is None or breakout_value is None:
            return None

        components = {
            self.MOMENTUM_KEY: momentum_value,
            self.BREAKOUT_KEY: breakout_value,
        }

        weights = self.weights

        score = self._weighted_sum(components, weights)

        return FactorResult(
            score=score,
            components=components,
            weights=weights,
        )
