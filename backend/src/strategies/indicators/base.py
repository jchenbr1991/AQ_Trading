# backend/src/strategies/indicators/base.py
"""Base classes for technical indicators with warmup and lag handling.

All indicators follow strict lookahead bias prevention:
- When processing bar[t], only use data from bar[0:t], never bar[t+1:]
- Features return None during warmup period (when len(history) < lookback)
- Division by zero returns None

See specs/002-minimal-mvp-trading/data-model.md for indicator formulas.
"""

from abc import ABC, abstractmethod
from decimal import Decimal


class BaseIndicator(ABC):
    """Base class for technical indicators with warmup and lag handling.

    All indicators must:
    1. Declare their lookback period
    2. Return None during warmup (insufficient data)
    3. Return None for invalid calculations (e.g., division by zero)
    4. Never use future data (lookahead bias prevention)

    Attributes:
        lookback: Number of historical bars needed for calculation.
    """

    def __init__(self, lookback: int) -> None:
        """Initialize indicator with lookback period.

        Args:
            lookback: Number of historical bars needed for calculation.
                     Must be positive.

        Raises:
            ValueError: If lookback is not positive.
        """
        if lookback < 1:
            raise ValueError(f"lookback must be >= 1, got {lookback}")
        self._lookback = lookback

    @property
    def lookback(self) -> int:
        """Number of historical bars needed for calculation."""
        return self._lookback

    @property
    def warmup_bars(self) -> int:
        """Minimum bars needed before indicator produces valid values.

        By default, this equals the lookback period. Subclasses may override
        if they need additional bars (e.g., for returns calculation).
        """
        return self._lookback

    @abstractmethod
    def calculate(
        self,
        prices: list[Decimal],
        volumes: list[int] | None = None,
        highs: list[Decimal] | None = None,
    ) -> Decimal | None:
        """Calculate indicator value from historical data.

        IMPORTANT: This method must never access future data.
        The last element of each list is the current bar's value.

        Args:
            prices: Historical close prices, oldest first.
                   prices[-1] is the current bar's close.
            volumes: Optional historical volumes, oldest first.
            highs: Optional historical high prices, oldest first.

        Returns:
            Calculated indicator value as Decimal, or None if:
            - Insufficient data (warmup period)
            - Invalid calculation (e.g., division by zero)
            - Missing required data (e.g., volumes for volume indicator)
        """
        pass

    def _check_warmup(self, data: list) -> bool:
        """Check if enough data for calculation.

        Args:
            data: Historical data list to check.

        Returns:
            True if len(data) >= lookback, False otherwise.
        """
        return len(data) >= self._lookback

    def _safe_divide(self, numerator: Decimal, denominator: Decimal) -> Decimal | None:
        """Safely divide two Decimals, returning None if denominator is zero.

        Args:
            numerator: The dividend.
            denominator: The divisor.

        Returns:
            numerator / denominator, or None if denominator is zero.
        """
        if denominator == Decimal("0"):
            return None
        return numerator / denominator
