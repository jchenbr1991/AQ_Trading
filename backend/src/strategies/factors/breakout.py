# backend/src/strategies/factors/breakout.py
"""Breakout factor combining Price vs High and Volume Z-Score indicators.

Formula: breakout_factor = w3 * price_vs_high_20 + w4 * volume_zscore

Default weights: w3=0.5, w4=0.5

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from decimal import Decimal

from src.strategies.factors.base import BaseFactor, FactorResult


class BreakoutFactor(BaseFactor):
    """Breakout factor combining Price vs High and Volume Z-Score.

    This factor identifies potential breakout conditions by combining:
    - price_vs_high_20: Distance from 20-period high (breakout proximity)
    - volume_zscore: Volume relative to recent average (confirmation)

    Higher values indicate stronger breakout potential (price near highs
    with above-average volume).

    Example:
        >>> factor = BreakoutFactor()
        >>> indicators = {
        ...     "price_vs_high_20": Decimal("-0.02"),
        ...     "volume_zscore": Decimal("1.5"),
        ... }
        >>> result = factor.calculate(indicators)
        >>> result.score
        Decimal('0.74')  # 0.5 * (-0.02) + 0.5 * 1.5
    """

    # Component indicator names
    PRICE_VS_HIGH_KEY = "price_vs_high_20"
    VOLUME_ZSCORE_KEY = "volume_zscore"

    def __init__(
        self,
        price_vs_high_weight: Decimal = Decimal("0.5"),
        volume_zscore_weight: Decimal = Decimal("0.5"),
    ) -> None:
        """Initialize breakout factor with configurable weights.

        Args:
            price_vs_high_weight: Weight for Price vs High indicator. Default: 0.5
            volume_zscore_weight: Weight for Volume Z-Score indicator. Default: 0.5

        Note:
            Weights do not need to sum to 1.0, but are typically normalized.
        """
        self._price_vs_high_weight = price_vs_high_weight
        self._volume_zscore_weight = volume_zscore_weight

    @property
    def weights(self) -> dict[str, Decimal]:
        """Current weight configuration."""
        return {
            self.PRICE_VS_HIGH_KEY: self._price_vs_high_weight,
            self.VOLUME_ZSCORE_KEY: self._volume_zscore_weight,
        }

    def calculate(self, indicators: dict[str, Decimal | None]) -> FactorResult | None:
        """Calculate breakout factor from indicator values.

        Args:
            indicators: Dictionary containing:
                - "price_vs_high_20": Price vs high value (Decimal or None)
                - "volume_zscore": Volume z-score value (Decimal or None)

        Returns:
            FactorResult with breakout score, component values, and weights,
            or None if any required indicator is None.
        """
        price_vs_high_value = indicators.get(self.PRICE_VS_HIGH_KEY)
        volume_zscore_value = indicators.get(self.VOLUME_ZSCORE_KEY)

        # Return None if any required indicator is missing or None
        if price_vs_high_value is None or volume_zscore_value is None:
            return None

        components = {
            self.PRICE_VS_HIGH_KEY: price_vs_high_value,
            self.VOLUME_ZSCORE_KEY: volume_zscore_value,
        }

        weights = self.weights

        score = self._weighted_sum(components, weights)

        return FactorResult(
            score=score,
            components=components,
            weights=weights,
        )
