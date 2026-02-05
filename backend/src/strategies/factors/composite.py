# backend/src/strategies/factors/composite.py
"""Composite factor combining Momentum and Breakout factors.

Formula: composite = w_mom * momentum_factor + w_brk * breakout_factor

Optionally normalizes factor scores via rolling z-score before combining,
so that factors with different natural scales contribute equally.

Default weights: w_mom=0.5, w_brk=0.5

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from decimal import Decimal

from src.strategies.factors.base import BaseFactor, FactorResult
from src.strategies.factors.normalizer import ScoreNormalizer


class CompositeFactor(BaseFactor):
    """Composite factor combining Momentum and Breakout factors.

    This is the final factor used for trading decisions. It combines:
    - momentum_factor: Overall price momentum signal
    - breakout_factor: Breakout potential signal

    Optionally normalizes factor scores via rolling z-score before combining,
    so that factors with different natural scales contribute equally.

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
        normalize: bool = False,
        normalize_min_periods: int = 20,
        normalize_window_size: int = 60,
    ) -> None:
        """Initialize composite factor with configurable weights.

        Args:
            momentum_weight: Weight for momentum factor. Default: 0.5
            breakout_weight: Weight for breakout factor. Default: 0.5
            normalize: If True, z-score normalize factor scores before combining.
                      Default: False (backward compatible).
            normalize_min_periods: Minimum observations before normalization activates.
            normalize_window_size: Rolling window size for normalization statistics.

        Note:
            Weights do not need to sum to 1.0, but are typically normalized.
        """
        self._momentum_weight = momentum_weight
        self._breakout_weight = breakout_weight
        self._normalize = normalize
        self._normalizer: ScoreNormalizer | None = (
            ScoreNormalizer(
                min_periods=normalize_min_periods,
                window_size=normalize_window_size,
            )
            if normalize
            else None
        )

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

    def update_normalizer(self, factor_scores: dict[str, Decimal]) -> None:
        """Record raw factor scores for normalization statistics.

        Should be called each bar with the raw (un-normalized) factor scores
        before calculate() is called.

        Args:
            factor_scores: Raw factor scores, e.g.
                {"momentum_factor": Decimal("0.01"), "breakout_factor": Decimal("0.50")}
        """
        if self._normalizer is None:
            return
        for name, value in factor_scores.items():
            self._normalizer.update(name, value)

    def calculate(self, indicators: dict[str, Decimal | None]) -> FactorResult | None:
        """Calculate composite factor from sub-factor scores.

        If normalization is enabled and the normalizer has enough history,
        factor scores are z-score normalized before the weighted sum.
        During warmup (insufficient history), raw scores are used.

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

        # Store raw components for result reporting
        components = {
            self.MOMENTUM_KEY: momentum_value,
            self.BREAKOUT_KEY: breakout_value,
        }

        # Optionally normalize scores before combining
        calc_values = dict(components)
        if self._normalizer is not None:
            norm_momentum = self._normalizer.normalize(self.MOMENTUM_KEY, momentum_value)
            norm_breakout = self._normalizer.normalize(self.BREAKOUT_KEY, breakout_value)
            # If both can be normalized, use normalized values; otherwise fall back to raw
            if norm_momentum is not None and norm_breakout is not None:
                calc_values = {
                    self.MOMENTUM_KEY: norm_momentum,
                    self.BREAKOUT_KEY: norm_breakout,
                }

        weights = self.weights

        score = self._weighted_sum(calc_values, weights)

        return FactorResult(
            score=score,
            components=components,
            weights=weights,
        )
