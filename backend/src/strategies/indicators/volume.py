# backend/src/strategies/indicators/volume.py
"""Volume and volatility-based technical indicators.

Implements:
- VolumeZScore: volume_zscore = (volume[t] - mean(volume[t-n:t])) / std(volume[t-n:t])
- Volatility: volatility_n = std(returns[t-n:t])

See specs/002-minimal-mvp-trading/data-model.md for formulas.
"""

from decimal import Decimal

from src.strategies.indicators.base import BaseIndicator


def _decimal_sqrt(value: Decimal) -> Decimal:
    """Calculate square root of a Decimal using Newton's method.

    Args:
        value: Non-negative Decimal value.

    Returns:
        Square root as Decimal.

    Raises:
        ValueError: If value is negative.
    """
    if value < Decimal("0"):
        raise ValueError(f"Cannot take sqrt of negative value: {value}")
    if value == Decimal("0"):
        return Decimal("0")

    # Newton's method for square root
    # Use reasonable initial guess and precision
    x = value
    precision = Decimal("0.0000000001")
    max_iterations = 100

    for _ in range(max_iterations):
        x_new = (x + value / x) / Decimal("2")
        if abs(x_new - x) < precision:
            return x_new
        x = x_new

    return x


class VolumeZScore(BaseIndicator):
    """Volume Z-Score indicator.

    Formula: volume_zscore = (volume[t] - mean(volume[t-n:t])) / std(volume[t-n:t])

    Measures how unusual the current volume is compared to recent history.
    - Z > 2: Unusually high volume (potential breakout)
    - Z < -2: Unusually low volume
    - Z near 0: Normal volume

    Note: Uses volumes from past lookback periods (not including current)
    to calculate mean and std, then compares current volume against them.

    Default lookback: 20 bars (per spec).

    Example:
        >>> vz = VolumeZScore(lookback=5)
        >>> volumes = [1000, 1100, 900, 1050, 950, 1500]
        >>> # mean of past 5 = 1000, std ~= 70.7, current = 1500
        >>> # z-score = (1500 - 1000) / 70.7 = ~7.07
    """

    def __init__(self, lookback: int = 20) -> None:
        """Initialize Volume Z-Score indicator.

        Args:
            lookback: Number of periods for mean/std calculation.
                     Default is 20 (per spec).
        """
        super().__init__(lookback)

    @property
    def warmup_bars(self) -> int:
        """Need lookback + 1 bars: lookback past volumes plus current bar."""
        return self._lookback + 1

    def calculate(
        self,
        prices: list[Decimal],
        volumes: list[int] | None = None,
        highs: list[Decimal] | None = None,
    ) -> Decimal | None:
        """Calculate Volume Z-Score.

        Formula: (volume[t] - mean(volume[t-n:t])) / std(volume[t-n:t])

        Uses volumes from the PAST lookback periods (not including current)
        to calculate mean and std.

        Args:
            prices: Not used for this indicator, but required by interface.
            volumes: Historical volumes, oldest first. Required.
                    Requires at least (lookback + 1) volumes.
                    volumes[-1] is current volume (volume[t]).
            highs: Not used, ignored.

        Returns:
            Z-score as Decimal, or None if:
            - volumes is None or insufficient
            - Standard deviation is zero (all past volumes identical)
        """
        if volumes is None:
            return None

        # Need lookback + 1: past lookback volumes plus current
        required_length = self._lookback + 1
        if len(volumes) < required_length:
            return None

        current_volume = Decimal(str(volumes[-1]))

        # Get past lookback volumes (excluding current)
        past_volumes = [Decimal(str(v)) for v in volumes[-(self._lookback + 1) : -1]]

        # Calculate mean
        mean_volume = sum(past_volumes) / Decimal(len(past_volumes))

        # Calculate standard deviation
        variance = sum((v - mean_volume) ** 2 for v in past_volumes) / Decimal(len(past_volumes))
        std_volume = _decimal_sqrt(variance)

        # Return None if std is zero (no variation = can't calculate z-score)
        if std_volume == Decimal("0"):
            return None

        return (current_volume - mean_volume) / std_volume


class Volatility(BaseIndicator):
    """Volatility indicator (standard deviation of returns).

    Formula: volatility_n = std(returns[t-n:t])

    Where returns[i] = (price[i] - price[i-1]) / price[i-1]

    Measures the dispersion of returns over the lookback period.
    Higher values indicate more volatile price action.

    Default lookback: 20 bars (per spec).

    Example:
        >>> vol = Volatility(lookback=5)
        >>> prices = [Decimal("100"), Decimal("102"), Decimal("101"),
        ...           Decimal("103"), Decimal("105"), Decimal("104")]
        >>> # returns: [0.02, -0.0098, 0.0198, 0.0194, -0.0095]
        >>> # volatility = std of these returns
    """

    def __init__(self, lookback: int = 20) -> None:
        """Initialize Volatility indicator.

        Args:
            lookback: Number of returns for std calculation.
                     Default is 20 (per spec).
        """
        super().__init__(lookback)

    @property
    def warmup_bars(self) -> int:
        """Need lookback + 1 bars to calculate lookback returns.

        To get n returns, we need n+1 prices:
        - prices[0:n+1] gives us returns[0:n]
        """
        return self._lookback + 1

    def calculate(
        self,
        prices: list[Decimal],
        volumes: list[int] | None = None,
        highs: list[Decimal] | None = None,
    ) -> Decimal | None:
        """Calculate Volatility (std of returns).

        Formula: std(returns[t-n:t])

        Where returns are calculated as (price[i] - price[i-1]) / price[i-1]

        Args:
            prices: Historical close prices, oldest first.
                   Requires at least (lookback + 1) prices to calculate
                   lookback returns.
            volumes: Not used, ignored.
            highs: Not used, ignored.

        Returns:
            Volatility as Decimal, or None if:
            - Insufficient price data
            - Division by zero in return calculation (price == 0)
        """
        # Need lookback + 1 prices to get lookback returns
        required_length = self._lookback + 1
        if len(prices) < required_length:
            return None

        # Get the window of prices needed for returns calculation
        window = prices[-(required_length):]

        # Calculate returns
        returns: list[Decimal] = []
        for i in range(1, len(window)):
            prev_price = window[i - 1]
            curr_price = window[i]

            if prev_price == Decimal("0"):
                return None  # Can't calculate return with zero price

            ret = (curr_price - prev_price) / prev_price
            returns.append(ret)

        # Calculate standard deviation of returns
        mean_return = sum(returns) / Decimal(len(returns))
        variance = sum((r - mean_return) ** 2 for r in returns) / Decimal(len(returns))
        volatility = _decimal_sqrt(variance)

        return volatility
