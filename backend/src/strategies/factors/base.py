# backend/src/strategies/factors/base.py
"""Base classes for factor models with weighted composition.

Factors combine multiple indicator values into composite signals for trading
decisions. Each factor uses a weighted sum of its component indicators.

All factors follow strict null handling:
- When any input indicator is None, the factor returns None
- This prevents trading on incomplete information during warmup periods

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class FactorResult:
    """Result of factor calculation with component breakdown.

    Attributes:
        score: The weighted combination of all component values.
        components: Individual component values used in calculation.
        weights: Weight applied to each component.
    """

    score: Decimal
    components: dict[str, Decimal]
    weights: dict[str, Decimal]


class BaseFactor(ABC):
    """Base class for factor calculations.

    Factors combine multiple indicator values using weighted sums to produce
    a composite score for trading decisions.

    Subclasses must implement:
    - calculate(): Compute factor from indicator values

    Example:
        >>> class MyFactor(BaseFactor):
        ...     def calculate(self, indicators):
        ...         if indicators.get("ind1") is None:
        ...             return None
        ...         values = {"ind1": indicators["ind1"]}
        ...         weights = {"ind1": Decimal("1.0")}
        ...         return FactorResult(
        ...             score=self._weighted_sum(values, weights),
        ...             components=values,
        ...             weights=weights,
        ...         )
    """

    @abstractmethod
    def calculate(self, indicators: dict[str, Decimal | None]) -> FactorResult | None:
        """Calculate factor from indicator values.

        Args:
            indicators: Dictionary of indicator name to value.
                       Values may be None during warmup periods.

        Returns:
            FactorResult with score, components, and weights used,
            or None if any required indicator is None.
        """
        pass

    def _weighted_sum(self, values: dict[str, Decimal], weights: dict[str, Decimal]) -> Decimal:
        """Calculate weighted sum of values.

        Args:
            values: Dictionary of component name to Decimal value.
            weights: Dictionary of component name to Decimal weight.
                    Must have the same keys as values.

        Returns:
            Sum of (value * weight) for all components.

        Raises:
            KeyError: If values and weights have different keys.
        """
        return sum(values[k] * weights[k] for k in values)
