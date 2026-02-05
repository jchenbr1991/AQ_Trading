# backend/src/strategies/indicators/momentum.py
"""Momentum-based technical indicators.

Implements:
- ROC (Rate of Change): roc_n = (price[t] - price[t-n]) / price[t-n]
- PriceVsMA (Price vs Moving Average): price_vs_ma_n = (price[t] - SMA[t,n]) / SMA[t,n]

See specs/002-minimal-mvp-trading/data-model.md for formulas.
"""

from decimal import Decimal

from src.strategies.indicators.base import BaseIndicator


class ROC(BaseIndicator):
    """Rate of Change indicator.

    Formula: roc_n = (price[t] - price[t-n]) / price[t-n]

    Measures the percentage change in price over the lookback period.
    Positive values indicate upward momentum, negative values indicate
    downward momentum.

    Default lookback: 5 or 20 bars (per spec).

    Example:
        >>> roc = ROC(lookback=5)
        >>> prices = [Decimal("100"), Decimal("102"), Decimal("104"),
        ...           Decimal("103"), Decimal("105"), Decimal("108")]
        >>> roc.calculate(prices)
        Decimal('0.08')  # (108 - 100) / 100 = 0.08 = 8%
    """

    def __init__(self, lookback: int = 20) -> None:
        """Initialize ROC indicator.

        Args:
            lookback: Number of periods for rate of change calculation.
                     Default is 20 (per spec).
        """
        super().__init__(lookback)

    @property
    def warmup_bars(self) -> int:
        """Need lookback + 1 bars: current price plus lookback periods back."""
        return self._lookback + 1

    def calculate(
        self,
        prices: list[Decimal],
        volumes: list[int] | None = None,
        highs: list[Decimal] | None = None,
    ) -> Decimal | None:
        """Calculate Rate of Change.

        Formula: (price[t] - price[t-n]) / price[t-n]

        Args:
            prices: Historical close prices, oldest first.
                   Requires at least (lookback + 1) prices:
                   - prices[-1] is current price (price[t])
                   - prices[-(lookback+1)] is the comparison price (price[t-n])
            volumes: Not used, ignored.
            highs: Not used, ignored.

        Returns:
            ROC value as Decimal, or None if insufficient data or
            division by zero (price[t-n] == 0).
        """
        # Need lookback + 1 prices: current price plus lookback periods back
        required_length = self._lookback + 1
        if len(prices) < required_length:
            return None

        current_price = prices[-1]
        past_price = prices[-(self._lookback + 1)]

        return self._safe_divide(current_price - past_price, past_price)


class PriceVsMA(BaseIndicator):
    """Price vs Moving Average indicator.

    Formula: price_vs_ma_n = (price[t] - SMA[t,n]) / SMA[t,n]

    Where SMA[t,n] is the Simple Moving Average of the last n prices
    (including the current price).

    Positive values indicate price is above the moving average (bullish),
    negative values indicate price is below (bearish).

    Default lookback: 20 bars (per spec).

    Example:
        >>> pvma = PriceVsMA(lookback=3)
        >>> prices = [Decimal("100"), Decimal("102"), Decimal("104")]
        >>> # SMA = (100 + 102 + 104) / 3 = 102
        >>> pvma.calculate(prices)
        Decimal('0.0196...')  # (104 - 102) / 102
    """

    def __init__(self, lookback: int = 20) -> None:
        """Initialize Price vs MA indicator.

        Args:
            lookback: Number of periods for moving average calculation.
                     Default is 20 (per spec).
        """
        super().__init__(lookback)

    def calculate(
        self,
        prices: list[Decimal],
        volumes: list[int] | None = None,
        highs: list[Decimal] | None = None,
    ) -> Decimal | None:
        """Calculate Price vs Moving Average.

        Formula: (price[t] - SMA[t,n]) / SMA[t,n]

        Args:
            prices: Historical close prices, oldest first.
                   Requires at least lookback prices for SMA calculation.
                   prices[-1] is current price (price[t]).
            volumes: Not used, ignored.
            highs: Not used, ignored.

        Returns:
            Price vs MA value as Decimal, or None if insufficient data or
            division by zero (SMA == 0).
        """
        if not self._check_warmup(prices):
            return None

        # Calculate SMA using the last 'lookback' prices
        window = prices[-self._lookback :]
        sma = sum(window) / Decimal(len(window))

        current_price = prices[-1]

        return self._safe_divide(current_price - sma, sma)
