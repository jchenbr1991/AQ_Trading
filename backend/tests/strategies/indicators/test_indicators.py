"""Tests for technical indicators.

Tests for:
- ROC (Rate of Change)
- PriceVsMA (Price vs Moving Average)
- PriceVsHigh (Price vs Recent High)
- VolumeZScore (Volume Z-Score)
- Warmup handling
- Division by zero handling

See specs/002-minimal-mvp-trading/data-model.md for indicator formulas.
"""

from decimal import Decimal

import pytest
from src.strategies.indicators import ROC, PriceVsHigh, PriceVsMA, Volatility, VolumeZScore


class TestROC:
    """Tests for Rate of Change indicator."""

    def test_roc_calculation_positive(self) -> None:
        """ROC correctly calculates positive rate of change.

        Formula: roc_n = (price[t] - price[t-n]) / price[t-n]
        """
        roc = ROC(lookback=5)
        prices = [
            Decimal("100"),
            Decimal("102"),
            Decimal("104"),
            Decimal("103"),
            Decimal("105"),
            Decimal("108"),  # Current price
        ]

        result = roc.calculate(prices)

        # (108 - 100) / 100 = 0.08 = 8%
        assert result == Decimal("0.08")

    def test_roc_calculation_negative(self) -> None:
        """ROC correctly calculates negative rate of change."""
        roc = ROC(lookback=5)
        prices = [
            Decimal("100"),
            Decimal("98"),
            Decimal("96"),
            Decimal("94"),
            Decimal("93"),
            Decimal("92"),  # Current price
        ]

        result = roc.calculate(prices)

        # (92 - 100) / 100 = -0.08 = -8%
        assert result == Decimal("-0.08")

    def test_roc_warmup_returns_none(self) -> None:
        """ROC returns None during warmup (insufficient data)."""
        roc = ROC(lookback=5)
        prices = [
            Decimal("100"),
            Decimal("102"),
            Decimal("104"),
        ]  # Only 3 prices, need 6

        result = roc.calculate(prices)

        assert result is None

    def test_roc_division_by_zero(self) -> None:
        """ROC returns None when past price is zero."""
        roc = ROC(lookback=3)
        prices = [
            Decimal("0"),  # Past price is zero
            Decimal("10"),
            Decimal("20"),
            Decimal("30"),  # Current price
        ]

        result = roc.calculate(prices)

        assert result is None

    def test_roc_warmup_bars_property(self) -> None:
        """ROC warmup_bars equals lookback + 1."""
        roc = ROC(lookback=20)

        assert roc.warmup_bars == 21


class TestPriceVsMA:
    """Tests for Price vs Moving Average indicator."""

    def test_price_vs_ma_above_average(self) -> None:
        """PriceVsMA correctly calculates when price is above MA.

        Formula: price_vs_ma_n = (price[t] - SMA[t,n]) / SMA[t,n]
        """
        pvma = PriceVsMA(lookback=3)
        prices = [
            Decimal("100"),
            Decimal("102"),
            Decimal("104"),  # Current price
        ]

        result = pvma.calculate(prices)

        # SMA = (100 + 102 + 104) / 3 = 102
        # (104 - 102) / 102 = 2/102 = 0.0196...
        expected = (Decimal("104") - Decimal("102")) / Decimal("102")
        assert result == expected

    def test_price_vs_ma_below_average(self) -> None:
        """PriceVsMA correctly calculates when price is below MA."""
        pvma = PriceVsMA(lookback=3)
        prices = [
            Decimal("100"),
            Decimal("102"),
            Decimal("98"),  # Current price below average
        ]

        result = pvma.calculate(prices)

        # SMA = (100 + 102 + 98) / 3 = 100
        # (98 - 100) / 100 = -0.02
        assert result == Decimal("-0.02")

    def test_price_vs_ma_warmup_returns_none(self) -> None:
        """PriceVsMA returns None during warmup."""
        pvma = PriceVsMA(lookback=5)
        prices = [Decimal("100"), Decimal("102")]  # Only 2, need 5

        result = pvma.calculate(prices)

        assert result is None

    def test_price_vs_ma_division_by_zero(self) -> None:
        """PriceVsMA returns None when SMA is zero."""
        pvma = PriceVsMA(lookback=3)
        prices = [
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),  # All zeros
        ]

        result = pvma.calculate(prices)

        assert result is None

    def test_price_vs_ma_warmup_bars_property(self) -> None:
        """PriceVsMA warmup_bars equals lookback."""
        pvma = PriceVsMA(lookback=20)

        assert pvma.warmup_bars == 20


class TestPriceVsHigh:
    """Tests for Price vs Recent High indicator."""

    def test_price_vs_high_at_high(self) -> None:
        """PriceVsHigh returns 0 when current price equals recent high.

        Formula: price_vs_high_n = (price[t] - max(high[t-n:t])) / max(high[t-n:t])
        """
        pvh = PriceVsHigh(lookback=3)
        prices = [
            Decimal("95"),
            Decimal("97"),
            Decimal("96"),
            Decimal("99"),  # Current close = max past high
        ]
        highs = [
            Decimal("96"),
            Decimal("98"),
            Decimal("97"),
            Decimal("99"),  # Past max = 98, current = 99
        ]

        result = pvh.calculate(prices, highs=highs)

        # max(past highs) = max(96, 98, 97) = 98
        # (99 - 98) / 98 = 0.0102...
        expected = (Decimal("99") - Decimal("98")) / Decimal("98")
        assert result == expected

    def test_price_vs_high_below_high(self) -> None:
        """PriceVsHigh returns negative when price below recent high."""
        pvh = PriceVsHigh(lookback=3)
        prices = [
            Decimal("95"),
            Decimal("100"),
            Decimal("98"),
            Decimal("95"),  # Current price
        ]
        highs = [
            Decimal("96"),
            Decimal("102"),
            Decimal("99"),
            Decimal("96"),  # Past max = 102
        ]

        result = pvh.calculate(prices, highs=highs)

        # max(past highs) = max(96, 102, 99) = 102
        # (95 - 102) / 102 = -0.0686...
        expected = (Decimal("95") - Decimal("102")) / Decimal("102")
        assert result == expected

    def test_price_vs_high_warmup_returns_none(self) -> None:
        """PriceVsHigh returns None during warmup."""
        pvh = PriceVsHigh(lookback=5)
        prices = [Decimal("100"), Decimal("102")]
        highs = [Decimal("101"), Decimal("103")]

        result = pvh.calculate(prices, highs=highs)

        assert result is None

    def test_price_vs_high_missing_highs_returns_none(self) -> None:
        """PriceVsHigh returns None when highs not provided."""
        pvh = PriceVsHigh(lookback=3)
        prices = [
            Decimal("95"),
            Decimal("97"),
            Decimal("96"),
            Decimal("99"),
        ]

        result = pvh.calculate(prices, highs=None)

        assert result is None

    def test_price_vs_high_division_by_zero(self) -> None:
        """PriceVsHigh returns None when max high is zero."""
        pvh = PriceVsHigh(lookback=3)
        prices = [
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("10"),
        ]
        highs = [
            Decimal("0"),
            Decimal("0"),
            Decimal("0"),
            Decimal("10"),  # Past highs all zero
        ]

        result = pvh.calculate(prices, highs=highs)

        assert result is None

    def test_price_vs_high_warmup_bars_property(self) -> None:
        """PriceVsHigh warmup_bars equals lookback + 1."""
        pvh = PriceVsHigh(lookback=20)

        assert pvh.warmup_bars == 21


class TestVolumeZScore:
    """Tests for Volume Z-Score indicator."""

    def test_volume_zscore_high_volume(self) -> None:
        """VolumeZScore correctly calculates positive z-score for high volume.

        Formula: volume_zscore = (volume[t] - mean(volume[t-n:t])) / std(volume[t-n:t])
        """
        vz = VolumeZScore(lookback=5)
        volumes = [
            1000,
            1100,
            900,
            1050,
            950,
            2000,  # Current volume - much higher than average
        ]

        result = vz.calculate([], volumes=volumes)

        # Past volumes: [1000, 1100, 900, 1050, 950]
        # Mean = 1000
        # Current = 2000, which is 1000 above mean
        # Z-score should be positive
        assert result is not None
        assert result > Decimal("0")

    def test_volume_zscore_low_volume(self) -> None:
        """VolumeZScore correctly calculates negative z-score for low volume."""
        vz = VolumeZScore(lookback=5)
        volumes = [
            1000,
            1100,
            900,
            1050,
            950,
            500,  # Current volume - much lower than average
        ]

        result = vz.calculate([], volumes=volumes)

        # Current volume (500) is below mean (~1000)
        # Z-score should be negative
        assert result is not None
        assert result < Decimal("0")

    def test_volume_zscore_warmup_returns_none(self) -> None:
        """VolumeZScore returns None during warmup."""
        vz = VolumeZScore(lookback=5)
        volumes = [1000, 1100]  # Only 2, need 6

        result = vz.calculate([], volumes=volumes)

        assert result is None

    def test_volume_zscore_missing_volumes_returns_none(self) -> None:
        """VolumeZScore returns None when volumes not provided."""
        vz = VolumeZScore(lookback=5)

        result = vz.calculate([], volumes=None)

        assert result is None

    def test_volume_zscore_zero_std_returns_none(self) -> None:
        """VolumeZScore returns None when standard deviation is zero."""
        vz = VolumeZScore(lookback=5)
        volumes = [
            1000,
            1000,
            1000,
            1000,
            1000,
            1500,  # All past volumes identical
        ]

        result = vz.calculate([], volumes=volumes)

        # Std = 0, can't calculate z-score
        assert result is None

    def test_volume_zscore_warmup_bars_property(self) -> None:
        """VolumeZScore warmup_bars equals lookback + 1."""
        vz = VolumeZScore(lookback=20)

        assert vz.warmup_bars == 21


class TestVolatility:
    """Tests for Volatility indicator (std of returns)."""

    def test_volatility_calculation(self) -> None:
        """Volatility correctly calculates standard deviation of returns.

        Formula: volatility_n = std(returns[t-n:t])
        Where returns[i] = (price[i] - price[i-1]) / price[i-1]
        """
        vol = Volatility(lookback=5)
        prices = [
            Decimal("100"),
            Decimal("102"),  # +2%
            Decimal("101"),  # -0.98%
            Decimal("103"),  # +1.98%
            Decimal("105"),  # +1.94%
            Decimal("104"),  # -0.95%
        ]

        result = vol.calculate(prices)

        # Should be positive (volatility is std of returns)
        assert result is not None
        assert result > Decimal("0")

    def test_volatility_zero_for_flat_prices(self) -> None:
        """Volatility is zero when all prices are the same."""
        vol = Volatility(lookback=5)
        prices = [
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
        ]

        result = vol.calculate(prices)

        # All returns are 0, so std = 0
        assert result == Decimal("0")

    def test_volatility_warmup_returns_none(self) -> None:
        """Volatility returns None during warmup."""
        vol = Volatility(lookback=10)
        prices = [Decimal("100"), Decimal("102"), Decimal("104")]

        result = vol.calculate(prices)

        assert result is None

    def test_volatility_division_by_zero(self) -> None:
        """Volatility returns None when any price is zero."""
        vol = Volatility(lookback=3)
        prices = [
            Decimal("100"),
            Decimal("0"),  # Zero price
            Decimal("105"),
            Decimal("110"),
        ]

        result = vol.calculate(prices)

        assert result is None

    def test_volatility_warmup_bars_property(self) -> None:
        """Volatility warmup_bars equals lookback + 1."""
        vol = Volatility(lookback=20)

        assert vol.warmup_bars == 21


class TestBaseIndicator:
    """Tests for BaseIndicator base class."""

    def test_lookback_must_be_positive(self) -> None:
        """BaseIndicator raises ValueError for non-positive lookback."""
        with pytest.raises(ValueError, match="lookback must be >= 1"):
            ROC(lookback=0)

        with pytest.raises(ValueError, match="lookback must be >= 1"):
            PriceVsMA(lookback=-1)

    def test_lookback_property(self) -> None:
        """Indicator exposes lookback as property."""
        roc = ROC(lookback=15)

        assert roc.lookback == 15

    def test_safe_divide_normal(self) -> None:
        """_safe_divide returns correct result for non-zero denominator."""
        roc = ROC(lookback=5)

        result = roc._safe_divide(Decimal("10"), Decimal("5"))

        assert result == Decimal("2")

    def test_safe_divide_zero_denominator(self) -> None:
        """_safe_divide returns None for zero denominator."""
        roc = ROC(lookback=5)

        result = roc._safe_divide(Decimal("10"), Decimal("0"))

        assert result is None


class TestIndicatorEdgeCases:
    """Edge case tests for indicators."""

    def test_single_price_in_list(self) -> None:
        """Single price in list should return None for all indicators."""
        prices = [Decimal("100")]
        volumes = [1000]
        highs = [Decimal("101")]

        assert ROC(lookback=1).calculate(prices) is None
        assert PriceVsMA(lookback=1).calculate(prices) is not None  # Needs only 1
        assert PriceVsHigh(lookback=1).calculate(prices, highs=highs) is None
        assert VolumeZScore(lookback=1).calculate(prices, volumes=volumes) is None

    def test_empty_price_list(self) -> None:
        """Empty price list should return None for all indicators."""
        prices: list[Decimal] = []

        assert ROC(lookback=5).calculate(prices) is None
        assert PriceVsMA(lookback=5).calculate(prices) is None
        assert PriceVsHigh(lookback=5).calculate(prices, highs=[]) is None
        assert VolumeZScore(lookback=5).calculate(prices, volumes=[]) is None

    def test_very_small_prices(self) -> None:
        """Indicators handle very small prices correctly."""
        roc = ROC(lookback=2)
        prices = [
            Decimal("0.0001"),
            Decimal("0.0002"),
            Decimal("0.00015"),
        ]

        result = roc.calculate(prices)

        # (0.00015 - 0.0001) / 0.0001 = 0.5
        assert result == Decimal("0.5")

    def test_very_large_prices(self) -> None:
        """Indicators handle very large prices correctly."""
        roc = ROC(lookback=2)
        prices = [
            Decimal("1000000000"),
            Decimal("2000000000"),
            Decimal("1500000000"),
        ]

        result = roc.calculate(prices)

        # (1500000000 - 1000000000) / 1000000000 = 0.5
        assert result == Decimal("0.5")
