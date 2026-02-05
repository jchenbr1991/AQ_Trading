# backend/src/strategies/indicators/breakout.py
"""Breakout-based technical indicators.

Implements:
- PriceVsHigh: price_vs_high_n = (price[t] - max(high[t-n:t])) / max(high[t-n:t])

See specs/002-minimal-mvp-trading/data-model.md for formulas.
"""

from decimal import Decimal

from src.strategies.indicators.base import BaseIndicator


class PriceVsHigh(BaseIndicator):
    """Price vs Recent High indicator.

    Formula: price_vs_high_n = (price[t] - max(high[t-n:t])) / max(high[t-n:t])

    Measures how close the current price is to the recent high.
    Values close to 0 indicate price is near the high (potential breakout).
    Negative values indicate price is below the recent high.
    Positive values occur when current price exceeds historical highs.

    Note: The formula uses high[t-n:t] which excludes the current bar's high,
    preventing lookahead bias. The comparison is against PAST highs only.

    Default lookback: 20 bars (per spec).

    Example:
        >>> pvh = PriceVsHigh(lookback=5)
        >>> prices = [Decimal("95"), Decimal("97"), Decimal("96"),
        ...           Decimal("98"), Decimal("94"), Decimal("99")]
        >>> highs = [Decimal("96"), Decimal("98"), Decimal("97"),
        ...          Decimal("99"), Decimal("95"), Decimal("100")]
        >>> # max of past 5 highs = 99, current close = 99
        >>> pvh.calculate(prices, highs=highs)
        Decimal('0')  # (99 - 99) / 99 = 0
    """

    def __init__(self, lookback: int = 20) -> None:
        """Initialize Price vs High indicator.

        Args:
            lookback: Number of periods to look back for maximum high.
                     Default is 20 (per spec).
        """
        super().__init__(lookback)

    @property
    def warmup_bars(self) -> int:
        """Need lookback + 1 bars: lookback past highs plus current bar."""
        return self._lookback + 1

    def calculate(
        self,
        prices: list[Decimal],
        volumes: list[int] | None = None,
        highs: list[Decimal] | None = None,
    ) -> Decimal | None:
        """Calculate Price vs Recent High.

        Formula: (price[t] - max(high[t-n:t])) / max(high[t-n:t])

        Uses highs from the PAST lookback periods (not including current bar)
        to prevent lookahead bias.

        Args:
            prices: Historical close prices, oldest first.
                   Requires at least (lookback + 1) prices.
                   prices[-1] is current price (price[t]).
            volumes: Not used, ignored.
            highs: Historical high prices, oldest first. Required.
                  Requires at least (lookback + 1) highs.
                  highs[-1] is current bar's high (not used in max calculation).

        Returns:
            Price vs High value as Decimal, or None if:
            - Insufficient price data
            - highs is None or insufficient
            - Division by zero (max_high == 0)
        """
        # Require lookback + 1 bars: past lookback highs plus current bar
        required_length = self._lookback + 1

        if len(prices) < required_length:
            return None

        if highs is None or len(highs) < required_length:
            return None

        current_price = prices[-1]

        # Get the past lookback highs (excluding current bar's high)
        # highs[-lookback-1:-1] gives us the lookback bars before current
        past_highs = highs[-(self._lookback + 1) : -1]
        max_high = max(past_highs)

        return self._safe_divide(current_price - max_high, max_high)
