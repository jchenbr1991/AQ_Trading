# backend/src/strategies/factors/momentum.py
"""Momentum factor combining ROC and Price vs MA indicators.

Formula: momentum_factor = w1 * roc_20 + w2 * price_vs_ma_20

Default weights: w1=0.5, w2=0.5

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from decimal import Decimal

from src.strategies.factors.base import BaseFactor, FactorResult


class MomentumFactor(BaseFactor):
    """Momentum factor combining ROC and Price vs MA indicators.

    This factor measures overall price momentum by combining:
    - roc_20: Rate of change over 20 periods (trend strength)
    - price_vs_ma_20: Distance from 20-period moving average (mean reversion)

    Higher values indicate stronger upward momentum.

    Example:
        >>> factor = MomentumFactor()
        >>> indicators = {
        ...     "roc_20": Decimal("0.05"),
        ...     "price_vs_ma_20": Decimal("0.02"),
        ... }
        >>> result = factor.calculate(indicators)
        >>> result.score
        Decimal('0.035')  # 0.5 * 0.05 + 0.5 * 0.02
    """

    # Component indicator names
    ROC_KEY = "roc_20"
    PRICE_VS_MA_KEY = "price_vs_ma_20"

    def __init__(
        self,
        roc_weight: Decimal = Decimal("0.5"),
        price_vs_ma_weight: Decimal = Decimal("0.5"),
    ) -> None:
        """Initialize momentum factor with configurable weights.

        Args:
            roc_weight: Weight for ROC indicator. Default: 0.5
            price_vs_ma_weight: Weight for Price vs MA indicator. Default: 0.5

        Note:
            Weights do not need to sum to 1.0, but are typically normalized.
        """
        self._roc_weight = roc_weight
        self._price_vs_ma_weight = price_vs_ma_weight

    @property
    def weights(self) -> dict[str, Decimal]:
        """Current weight configuration."""
        return {
            self.ROC_KEY: self._roc_weight,
            self.PRICE_VS_MA_KEY: self._price_vs_ma_weight,
        }

    def calculate(self, indicators: dict[str, Decimal | None]) -> FactorResult | None:
        """Calculate momentum factor from indicator values.

        Args:
            indicators: Dictionary containing:
                - "roc_20": Rate of change value (Decimal or None)
                - "price_vs_ma_20": Price vs MA value (Decimal or None)

        Returns:
            FactorResult with momentum score, component values, and weights,
            or None if any required indicator is None.
        """
        roc_value = indicators.get(self.ROC_KEY)
        price_vs_ma_value = indicators.get(self.PRICE_VS_MA_KEY)

        # Return None if any required indicator is missing or None
        if roc_value is None or price_vs_ma_value is None:
            return None

        components = {
            self.ROC_KEY: roc_value,
            self.PRICE_VS_MA_KEY: price_vs_ma_value,
        }

        weights = self.weights

        score = self._weighted_sum(components, weights)

        return FactorResult(
            score=score,
            components=components,
            weights=weights,
        )
