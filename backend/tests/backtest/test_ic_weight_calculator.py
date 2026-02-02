"""Tests for ICWeightCalculator - systematic factor weight calculation.

Tests for:
- Information Coefficient (IC) calculation
- IC-based weight generation
- Rolling window IC calculation
- Edge cases (insufficient data, zero IC)

The IC (Information Coefficient) measures the correlation between factor values
at time t and returns at time t+1. Higher IC means better predictive power.
"""

from decimal import Decimal

import pytest
from src.backtest.ic_weight_calculator import ICWeightCalculator


class TestICCalculation:
    """Tests for Information Coefficient calculation."""

    def test_ic_positive_correlation(self) -> None:
        """IC is positive when factor predicts returns well."""
        calc = ICWeightCalculator()

        # Factor values at time t
        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
        ]
        # Returns at time t+1 (positively correlated with factor)
        future_returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.03"),
            Decimal("0.04"),
            Decimal("0.05"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        assert ic > Decimal("0.9")  # Strong positive correlation

    def test_ic_negative_correlation(self) -> None:
        """IC is negative when factor inversely predicts returns."""
        calc = ICWeightCalculator()

        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
        ]
        # Returns inversely correlated
        future_returns = [
            Decimal("0.05"),
            Decimal("0.04"),
            Decimal("0.03"),
            Decimal("0.02"),
            Decimal("0.01"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        assert ic < Decimal("-0.9")  # Strong negative correlation

    def test_ic_no_correlation(self) -> None:
        """IC is near zero when factor has no predictive power."""
        calc = ICWeightCalculator()

        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
        ]
        # Returns uncorrelated (random-ish)
        future_returns = [
            Decimal("0.03"),
            Decimal("0.01"),
            Decimal("0.05"),
            Decimal("0.02"),
            Decimal("0.04"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        assert abs(ic) < Decimal("0.5")  # Weak or no correlation

    def test_ic_returns_decimal(self) -> None:
        """IC is returned as Decimal for precision."""
        calc = ICWeightCalculator()

        factor_values = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
        future_returns = [Decimal("0.01"), Decimal("0.02"), Decimal("0.03")]

        ic = calc.calculate_ic(factor_values, future_returns)

        assert isinstance(ic, Decimal)

    def test_ic_requires_minimum_data_points(self) -> None:
        """IC calculation requires at least 3 data points."""
        calc = ICWeightCalculator()

        factor_values = [Decimal("0.1"), Decimal("0.2")]
        future_returns = [Decimal("0.01"), Decimal("0.02")]

        with pytest.raises(ValueError, match="at least 3"):
            calc.calculate_ic(factor_values, future_returns)

    def test_ic_mismatched_lengths_raises(self) -> None:
        """IC calculation raises when array lengths don't match."""
        calc = ICWeightCalculator()

        factor_values = [Decimal("0.1"), Decimal("0.2"), Decimal("0.3")]
        future_returns = [Decimal("0.01"), Decimal("0.02")]

        with pytest.raises(ValueError, match="same length"):
            calc.calculate_ic(factor_values, future_returns)


class TestICWeightGeneration:
    """Tests for IC-based weight calculation."""

    def test_weights_proportional_to_absolute_ic(self) -> None:
        """Weights are proportional to absolute IC values."""
        calc = ICWeightCalculator()

        # Factor ICs
        factor_ics = {
            "momentum_factor": Decimal("0.6"),
            "breakout_factor": Decimal("0.2"),
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        # Momentum has 3x the IC, should have higher weight
        assert weights["momentum_factor"] > weights["breakout_factor"]
        # Should be normalized: 0.6/(0.6+0.2) = 0.75, 0.2/(0.6+0.2) = 0.25
        assert abs(weights["momentum_factor"] - Decimal("0.75")) < Decimal("0.01")
        assert abs(weights["breakout_factor"] - Decimal("0.25")) < Decimal("0.01")

    def test_weights_sum_to_one(self) -> None:
        """Weights always sum to 1.0."""
        calc = ICWeightCalculator()

        factor_ics = {
            "factor_a": Decimal("0.3"),
            "factor_b": Decimal("0.5"),
            "factor_c": Decimal("0.2"),
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        total = sum(weights.values())
        assert abs(total - Decimal("1.0")) < Decimal("0.0001")

    def test_weights_use_absolute_ic(self) -> None:
        """Negative IC (inverse predictor) still contributes weight."""
        calc = ICWeightCalculator()

        # Negative IC means inverse predictor - still valuable!
        factor_ics = {
            "momentum_factor": Decimal("0.4"),
            "contrarian_factor": Decimal("-0.4"),  # Inverse predictor
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        # Both should have equal weight (absolute values are same)
        assert abs(weights["momentum_factor"] - Decimal("0.5")) < Decimal("0.01")
        assert abs(weights["contrarian_factor"] - Decimal("0.5")) < Decimal("0.01")

    def test_weights_returns_decimal(self) -> None:
        """All weights are Decimal type."""
        calc = ICWeightCalculator()

        factor_ics = {
            "factor_a": Decimal("0.3"),
            "factor_b": Decimal("0.5"),
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        for factor_name, weight in weights.items():
            assert isinstance(weight, Decimal), f"{factor_name} weight not Decimal"

    def test_zero_ic_gets_zero_weight(self) -> None:
        """Factor with zero IC gets zero weight."""
        calc = ICWeightCalculator()

        factor_ics = {
            "useful_factor": Decimal("0.5"),
            "useless_factor": Decimal("0"),
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        assert weights["useless_factor"] == Decimal("0")
        assert weights["useful_factor"] == Decimal("1.0")

    def test_all_zero_ic_returns_equal_weights(self) -> None:
        """When all ICs are zero, return equal weights."""
        calc = ICWeightCalculator()

        factor_ics = {
            "factor_a": Decimal("0"),
            "factor_b": Decimal("0"),
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        # Equal weights when no predictive power
        assert weights["factor_a"] == Decimal("0.5")
        assert weights["factor_b"] == Decimal("0.5")

    def test_empty_factors_raises(self) -> None:
        """Empty factor dict raises ValueError."""
        calc = ICWeightCalculator()

        with pytest.raises(ValueError, match="at least one factor"):
            calc.calculate_weights_from_ic({})


class TestRollingICCalculation:
    """Tests for rolling window IC calculation."""

    def test_rolling_ic_uses_window(self) -> None:
        """Rolling IC uses specified lookback window."""
        calc = ICWeightCalculator(lookback_window=5)

        # 7 data points, window=5 means use last 5
        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),  # Not in window
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
            Decimal("0.6"),
            Decimal("0.7"),
        ]
        future_returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.03"),
            Decimal("0.04"),
            Decimal("0.05"),
            Decimal("0.06"),
            Decimal("0.07"),
        ]

        ic = calc.calculate_rolling_ic(factor_values, future_returns)

        # IC calculated on last 5 points should be positive
        assert ic > Decimal("0.9")

    def test_rolling_ic_insufficient_data(self) -> None:
        """Rolling IC raises when data < lookback window."""
        calc = ICWeightCalculator(lookback_window=10)

        factor_values = [Decimal("0.1")] * 5
        future_returns = [Decimal("0.01")] * 5

        with pytest.raises(ValueError, match="Insufficient"):
            calc.calculate_rolling_ic(factor_values, future_returns)

    def test_calculate_weights_from_history(self) -> None:
        """Calculate weights from historical factor and return data."""
        calc = ICWeightCalculator(lookback_window=5)

        # Historical data for two factors
        factor_history = {
            "momentum_factor": [
                Decimal("0.1"),
                Decimal("0.2"),
                Decimal("0.3"),
                Decimal("0.4"),
                Decimal("0.5"),
            ],
            "breakout_factor": [
                Decimal("0.5"),
                Decimal("0.4"),
                Decimal("0.3"),
                Decimal("0.2"),
                Decimal("0.1"),
            ],
        }
        # Returns positively correlated with momentum
        future_returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.03"),
            Decimal("0.04"),
            Decimal("0.05"),
        ]

        weights = calc.calculate_weights_from_history(factor_history, future_returns)

        # Momentum has positive IC, breakout has negative IC
        # Both should have weight based on absolute IC
        assert "momentum_factor" in weights
        assert "breakout_factor" in weights
        assert sum(weights.values()) == Decimal("1.0")


class TestEdgeCases:
    """Edge case tests for IC weight calculator."""

    def test_single_factor(self) -> None:
        """Single factor gets weight of 1.0."""
        calc = ICWeightCalculator()

        factor_ics = {"only_factor": Decimal("0.3")}

        weights = calc.calculate_weights_from_ic(factor_ics)

        assert weights["only_factor"] == Decimal("1.0")

    def test_very_small_ic_values(self) -> None:
        """Very small IC values are handled correctly."""
        calc = ICWeightCalculator()

        factor_ics = {
            "factor_a": Decimal("0.001"),
            "factor_b": Decimal("0.002"),
        }

        weights = calc.calculate_weights_from_ic(factor_ics)

        # Should still sum to 1
        assert abs(sum(weights.values()) - Decimal("1.0")) < Decimal("0.0001")
        # factor_b should have ~2/3 weight
        assert weights["factor_b"] > weights["factor_a"]

    def test_constant_factor_values(self) -> None:
        """Constant factor values result in zero IC."""
        calc = ICWeightCalculator()

        # All same value = no variance = can't correlate
        factor_values = [Decimal("0.5")] * 5
        future_returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.03"),
            Decimal("0.04"),
            Decimal("0.05"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        assert ic == Decimal("0")

    def test_constant_returns(self) -> None:
        """Constant returns result in zero IC."""
        calc = ICWeightCalculator()

        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
        ]
        # All same return
        future_returns = [Decimal("0.02")] * 5

        ic = calc.calculate_ic(factor_values, future_returns)

        assert ic == Decimal("0")

    def test_default_lookback_window(self) -> None:
        """Default lookback window is 60 bars."""
        calc = ICWeightCalculator()

        assert calc.lookback_window == 60

    def test_custom_lookback_window(self) -> None:
        """Custom lookback window is stored correctly."""
        calc = ICWeightCalculator(lookback_window=20)

        assert calc.lookback_window == 20


class TestICIR:
    """Tests for Information Ratio (IC_IR = mean(IC) / std(IC)) calculation."""

    def test_ic_ir_with_consistent_factor(self) -> None:
        """IC_IR is high when factor consistently predicts returns."""
        calc = ICWeightCalculator(lookback_window=5)

        # Generate multiple periods of IC data (rolling windows)
        # Consistent positive correlation across all periods
        ic_history = [
            Decimal("0.6"),
            Decimal("0.5"),
            Decimal("0.55"),
            Decimal("0.52"),
            Decimal("0.58"),
        ]

        ic_ir = calc.calculate_ic_ir(ic_history)

        # High IC_IR = high mean, low std
        assert ic_ir > Decimal("5")  # mean ~0.55, std ~0.04, IR ~13

    def test_ic_ir_with_inconsistent_factor(self) -> None:
        """IC_IR is low when factor is inconsistent."""
        calc = ICWeightCalculator()

        # Inconsistent IC - sometimes positive, sometimes negative
        ic_history = [
            Decimal("0.5"),
            Decimal("-0.3"),
            Decimal("0.4"),
            Decimal("-0.2"),
            Decimal("0.1"),
        ]

        ic_ir = calc.calculate_ic_ir(ic_history)

        # Low IC_IR = inconsistent predictions
        assert ic_ir < Decimal("0.5")

    def test_ic_ir_returns_decimal(self) -> None:
        """IC_IR is returned as Decimal."""
        calc = ICWeightCalculator()

        ic_history = [Decimal("0.3"), Decimal("0.4"), Decimal("0.35")]

        ic_ir = calc.calculate_ic_ir(ic_history)

        assert isinstance(ic_ir, Decimal)

    def test_ic_ir_requires_minimum_periods(self) -> None:
        """IC_IR requires at least 3 IC values."""
        calc = ICWeightCalculator()

        ic_history = [Decimal("0.3"), Decimal("0.4")]

        with pytest.raises(ValueError, match="at least 3"):
            calc.calculate_ic_ir(ic_history)

    def test_ic_ir_zero_std_returns_zero(self) -> None:
        """IC_IR returns 0 when all ICs are identical (zero std)."""
        calc = ICWeightCalculator()

        # All same IC = zero std = undefined IR, return 0
        ic_history = [Decimal("0.5")] * 5

        ic_ir = calc.calculate_ic_ir(ic_history)

        assert ic_ir == Decimal("0")

    def test_weights_from_ic_ir(self) -> None:
        """Calculate weights using IC_IR instead of single IC."""
        calc = ICWeightCalculator()

        # Factor A: consistent predictor (high IC_IR)
        # Factor B: inconsistent predictor (low IC_IR)
        ic_ir_values = {
            "factor_a": Decimal("5.0"),  # High IR
            "factor_b": Decimal("1.0"),  # Low IR
        }

        weights = calc.calculate_weights_from_ic_ir(ic_ir_values)

        # Factor A should get more weight
        assert weights["factor_a"] > weights["factor_b"]
        # Sum to 1
        assert abs(sum(weights.values()) - Decimal("1.0")) < Decimal("0.0001")


class TestEWMA:
    """Tests for Exponentially Weighted Moving Average IC calculation."""

    def test_ewma_ic_weights_recent_more(self) -> None:
        """EWMA IC gives more weight to recent observations."""
        calc = ICWeightCalculator(lookback_window=5, ewma_span=3)

        # Recent data strongly correlated, old data weakly correlated
        # If EWMA works, IC should be closer to recent correlation
        factor_values = [
            Decimal("0.1"),  # Old - weak correlation
            Decimal("0.5"),
            Decimal("0.2"),
            Decimal("0.4"),  # Recent - strong correlation
            Decimal("0.5"),
        ]
        future_returns = [
            Decimal("0.05"),  # Old - weak correlation
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.04"),  # Recent - strong correlation
            Decimal("0.05"),
        ]

        ewma_ic = calc.calculate_ewma_ic(factor_values, future_returns)

        # Should be positive (recent data is positively correlated)
        assert ewma_ic > Decimal("0")
        assert isinstance(ewma_ic, Decimal)

    def test_ewma_span_affects_result(self) -> None:
        """Different EWMA spans produce different results."""
        # Short span = more reactive to recent data
        calc_short = ICWeightCalculator(lookback_window=10, ewma_span=3)
        # Long span = more smoothing
        calc_long = ICWeightCalculator(lookback_window=10, ewma_span=10)

        # Data where recent data has different pattern than old data
        # Old: increasing factor, decreasing returns (negative correlation)
        # Recent: increasing factor, increasing returns (positive correlation)
        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
            Decimal("0.5"),  # Recent: starts flat
            Decimal("0.6"),
            Decimal("0.7"),
            Decimal("0.8"),
            Decimal("0.9"),
        ]
        future_returns = [
            Decimal("0.05"),  # Old: decreasing (negative correlation with increasing factor)
            Decimal("0.04"),
            Decimal("0.03"),
            Decimal("0.02"),
            Decimal("0.01"),
            Decimal("0.01"),  # Recent: increasing (positive correlation)
            Decimal("0.02"),
            Decimal("0.03"),
            Decimal("0.04"),
            Decimal("0.05"),
        ]

        ic_short = calc_short.calculate_ewma_ic(factor_values, future_returns)
        ic_long = calc_long.calculate_ewma_ic(factor_values, future_returns)

        # Both ICs should be different since weighting differs
        # The key point: different spans produce different results
        assert ic_short != ic_long

    def test_ewma_default_span(self) -> None:
        """Default EWMA span is None (disabled)."""
        calc = ICWeightCalculator()

        assert calc.ewma_span is None

    def test_ewma_custom_span(self) -> None:
        """Custom EWMA span is stored correctly."""
        calc = ICWeightCalculator(ewma_span=20)

        assert calc.ewma_span == 20

    def test_ewma_ic_requires_minimum_data(self) -> None:
        """EWMA IC requires enough data points."""
        calc = ICWeightCalculator(lookback_window=10, ewma_span=5)

        factor_values = [Decimal("0.1")] * 3
        future_returns = [Decimal("0.01")] * 3

        with pytest.raises(ValueError, match="Insufficient"):
            calc.calculate_ewma_ic(factor_values, future_returns)


class TestFullPipeline:
    """Tests for complete IC_IR + EWMA pipeline."""

    def test_calculate_weights_with_ic_ir_and_ewma(self) -> None:
        """Full pipeline: historical data -> EWMA IC series -> IC_IR -> weights."""
        calc = ICWeightCalculator(lookback_window=5, ewma_span=3, ic_history_periods=4)

        # Need enough data for multiple rolling windows
        # lookback=5, periods=4 means we need at least 5+4-1=8 data points
        factor_history = {
            "momentum": [Decimal(str(i * 0.05)) for i in range(10)],
            "breakout": [Decimal(str((10 - i) * 0.05)) for i in range(10)],
        }
        future_returns = [Decimal(str(i * 0.01)) for i in range(10)]

        weights = calc.calculate_weights_full_pipeline(factor_history, future_returns)

        assert "momentum" in weights
        assert "breakout" in weights
        assert abs(sum(weights.values()) - Decimal("1.0")) < Decimal("0.0001")

    def test_pipeline_with_single_factor(self) -> None:
        """Pipeline works with single factor."""
        calc = ICWeightCalculator(lookback_window=5, ewma_span=3, ic_history_periods=3)

        factor_history = {
            "only_factor": [Decimal(str(i * 0.1)) for i in range(8)],
        }
        future_returns = [Decimal(str(i * 0.01)) for i in range(8)]

        weights = calc.calculate_weights_full_pipeline(factor_history, future_returns)

        assert weights["only_factor"] == Decimal("1.0")


class TestNumericalPrecision:
    """Tests for numerical precision with Decimal throughout."""

    def test_ic_calculation_uses_decimal_internally(self) -> None:
        """IC calculation maintains Decimal precision."""
        calc = ICWeightCalculator()

        # Values that would lose precision with float
        factor_values = [
            Decimal("0.1"),
            Decimal("0.2"),
            Decimal("0.3"),
            Decimal("0.4"),
            Decimal("0.5"),
        ]
        future_returns = [
            Decimal("0.01"),
            Decimal("0.02"),
            Decimal("0.03"),
            Decimal("0.04"),
            Decimal("0.05"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        # Result should be exactly 1.0 for perfect correlation
        assert ic == Decimal("1")

    def test_ic_with_very_small_values(self) -> None:
        """IC handles very small values without precision loss."""
        calc = ICWeightCalculator()

        factor_values = [
            Decimal("0.00001"),
            Decimal("0.00002"),
            Decimal("0.00003"),
            Decimal("0.00004"),
            Decimal("0.00005"),
        ]
        future_returns = [
            Decimal("0.000001"),
            Decimal("0.000002"),
            Decimal("0.000003"),
            Decimal("0.000004"),
            Decimal("0.000005"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        # Should still be perfect correlation
        assert ic == Decimal("1")

    def test_ic_with_large_values(self) -> None:
        """IC handles large values correctly."""
        calc = ICWeightCalculator()

        factor_values = [
            Decimal("1000000"),
            Decimal("2000000"),
            Decimal("3000000"),
            Decimal("4000000"),
            Decimal("5000000"),
        ]
        future_returns = [
            Decimal("100000"),
            Decimal("200000"),
            Decimal("300000"),
            Decimal("400000"),
            Decimal("500000"),
        ]

        ic = calc.calculate_ic(factor_values, future_returns)

        # Should still be perfect correlation
        assert ic == Decimal("1")


class TestIntegrationWithAttribution:
    """Integration tests showing IC weights work with attribution system."""

    def test_ic_weights_compatible_with_attribution(self) -> None:
        """IC-calculated weights work with AttributionCalculator."""
        from src.backtest.attribution import AttributionCalculator

        ic_calc = ICWeightCalculator()
        attr_calc = AttributionCalculator()

        # Calculate IC-based weights
        factor_ics = {
            "momentum_factor": Decimal("0.6"),
            "breakout_factor": Decimal("0.4"),
        }
        ic_weights = ic_calc.calculate_weights_from_ic(factor_ics)

        # Use IC weights in attribution
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("0.05"),
            "breakout_factor": Decimal("0.03"),
        }

        attribution = attr_calc.calculate_trade_attribution(pnl, entry_factors, ic_weights)

        # Should satisfy SC-003
        assert attr_calc.validate_attribution(attribution, pnl)
        assert sum(attribution.values()) == pnl

    def test_ic_ir_weights_compatible_with_attribution(self) -> None:
        """IC_IR-calculated weights work with AttributionCalculator."""
        from src.backtest.attribution import AttributionCalculator

        ic_calc = ICWeightCalculator()
        attr_calc = AttributionCalculator()

        # Calculate IC_IR-based weights
        ic_ir_values = {
            "momentum_factor": Decimal("3.0"),
            "breakout_factor": Decimal("1.5"),
        }
        ic_ir_weights = ic_calc.calculate_weights_from_ic_ir(ic_ir_values)

        # Use in attribution
        pnl = Decimal("200")
        entry_factors = {
            "momentum_factor": Decimal("0.04"),
            "breakout_factor": Decimal("0.02"),
        }

        attribution = attr_calc.calculate_trade_attribution(pnl, entry_factors, ic_ir_weights)

        assert attr_calc.validate_attribution(attribution, pnl)
