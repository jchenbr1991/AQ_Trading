"""Tests for AttributionCalculator.

Tests for:
- calculate_trade_attribution
- Normalization (SC-003)
- calculate_summary
- Edge cases (zero pnl, empty factors)

See specs/002-minimal-mvp-trading/data-model.md for attribution formulas.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.attribution import AttributionCalculator
from src.backtest.models import Trade


class TestCalculateTradeAttribution:
    """Tests for calculate_trade_attribution method."""

    def test_attribution_with_equal_weights(self) -> None:
        """Attribution correctly uses equal weights when not specified.

        FR-023: Attribution = factor_weight * factor_score_at_entry * trade_pnl
        """
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        assert attribution is not None
        assert len(attribution) == 2
        # With equal weights (0.5 each) and equal factors (0.5 each),
        # raw = 0.5 * 0.5 * 100 = 25 for each
        # After normalization, each should be 50
        assert "momentum_factor" in attribution
        assert "breakout_factor" in attribution

    def test_attribution_with_custom_weights(self) -> None:
        """Attribution correctly applies custom factor weights."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }
        factor_weights = {
            "momentum_factor": Decimal("0.6"),
            "breakout_factor": Decimal("0.4"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors, factor_weights)

        assert attribution is not None
        # raw momentum = 0.6 * 0.5 * 100 = 30
        # raw breakout = 0.4 * 0.5 * 100 = 20
        # total raw = 50
        # After normalization to sum = 100:
        # momentum = 30 * 100 / 50 = 60
        # breakout = 20 * 100 / 50 = 40
        assert attribution["momentum_factor"] == Decimal("60")
        assert attribution["breakout_factor"] == Decimal("40")

    def test_attribution_values_are_decimal(self) -> None:
        """All attribution values are Decimal type."""
        calc = AttributionCalculator()
        pnl = Decimal("500")
        entry_factors = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.021"),
            "composite": Decimal("0.028"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        for key, value in attribution.items():
            assert isinstance(value, Decimal), f"{key} should be Decimal"

    def test_attribution_with_negative_pnl(self) -> None:
        """Attribution handles negative PnL correctly."""
        calc = AttributionCalculator()
        pnl = Decimal("-100")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        assert attribution is not None
        # Sum should equal PnL after normalization
        total = sum(attribution.values())
        assert abs(total - pnl) < Decimal("0.001")

    def test_attribution_with_negative_factor_scores(self) -> None:
        """Attribution handles negative factor scores correctly."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("-0.3"),
            "breakout_factor": Decimal("0.7"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        assert attribution is not None
        # Sum should equal PnL after normalization
        total = sum(attribution.values())
        assert abs(total - pnl) < Decimal("0.001")


class TestNormalization:
    """Tests for SC-003: Attribution normalization."""

    def test_attribution_sum_equals_pnl(self) -> None:
        """SC-003: Sum of attributions equals total PnL within 0.1% tolerance."""
        calc = AttributionCalculator()
        pnl = Decimal("1234.56")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.3"),
            "composite": Decimal("0.2"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        total = sum(attribution.values())
        relative_error = abs(total - pnl) / abs(pnl)
        assert relative_error <= Decimal("0.001")  # 0.1% tolerance

    def test_normalization_with_zero_raw_sum(self) -> None:
        """When raw attribution sum is zero, distribute equally."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "factor_a": Decimal("0"),
            "factor_b": Decimal("0"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        # Should distribute equally
        assert attribution["factor_a"] == Decimal("50")
        assert attribution["factor_b"] == Decimal("50")
        # Sum equals PnL
        assert sum(attribution.values()) == pnl

    def test_validate_attribution_within_tolerance(self) -> None:
        """validate_attribution returns True when sum is within tolerance."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        attribution = {
            "momentum_factor": Decimal("60.05"),  # Slightly off
            "breakout_factor": Decimal("39.95"),
        }
        # Sum = 100, exactly equals pnl

        result = calc.validate_attribution(attribution, pnl)

        assert result is True

    def test_validate_attribution_outside_tolerance(self) -> None:
        """validate_attribution returns False when sum is outside tolerance."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        attribution = {
            "momentum_factor": Decimal("60"),
            "breakout_factor": Decimal("50"),  # Sum = 110, way off
        }

        result = calc.validate_attribution(attribution, pnl)

        assert result is False


class TestCalculateSummary:
    """Tests for calculate_summary method."""

    def test_summary_sums_attributions(self) -> None:
        """Summary correctly sums attributions across trades."""
        calc = AttributionCalculator()

        trades = [
            _create_trade_with_attribution(
                {
                    "momentum_factor": Decimal("100"),
                    "breakout_factor": Decimal("50"),
                }
            ),
            _create_trade_with_attribution(
                {
                    "momentum_factor": Decimal("200"),
                    "breakout_factor": Decimal("100"),
                }
            ),
        ]

        summary = calc.calculate_summary(trades)

        assert summary["momentum_factor"] == Decimal("300")
        assert summary["breakout_factor"] == Decimal("150")
        assert summary["total"] == Decimal("450")

    def test_summary_empty_trades(self) -> None:
        """Summary returns empty dict for no trades."""
        calc = AttributionCalculator()

        summary = calc.calculate_summary([])

        assert summary == {}

    def test_summary_with_empty_attribution(self) -> None:
        """Summary handles trades with empty attribution."""
        calc = AttributionCalculator()

        trades = [
            _create_trade_with_attribution({}),
            _create_trade_with_attribution(
                {
                    "momentum_factor": Decimal("100"),
                }
            ),
        ]

        summary = calc.calculate_summary(trades)

        assert summary["momentum_factor"] == Decimal("100")
        assert summary["total"] == Decimal("100")

    def test_summary_includes_total(self) -> None:
        """Summary includes 'total' key with sum of all factors."""
        calc = AttributionCalculator()

        trades = [
            _create_trade_with_attribution(
                {
                    "momentum_factor": Decimal("100"),
                    "breakout_factor": Decimal("50"),
                    "other_factor": Decimal("25"),
                }
            ),
        ]

        summary = calc.calculate_summary(trades)

        assert "total" in summary
        expected_total = Decimal("100") + Decimal("50") + Decimal("25")
        assert summary["total"] == expected_total


class TestEdgeCases:
    """Edge case tests for attribution."""

    def test_zero_pnl_returns_zero_attribution(self) -> None:
        """Zero PnL results in zero attribution for all factors."""
        calc = AttributionCalculator()
        pnl = Decimal("0")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.3"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        assert attribution["momentum_factor"] == Decimal("0")
        assert attribution["breakout_factor"] == Decimal("0")

    def test_empty_factors_returns_empty_dict(self) -> None:
        """Empty entry_factors returns empty attribution."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors: dict[str, Decimal] = {}

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        assert attribution == {}

    def test_single_factor(self) -> None:
        """Single factor gets all attribution."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        # Single factor gets all PnL after normalization
        assert attribution["momentum_factor"] == pnl

    def test_very_small_pnl(self) -> None:
        """Attribution handles very small PnL correctly."""
        calc = AttributionCalculator()
        pnl = Decimal("0.0001")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        total = sum(attribution.values())
        relative_error = abs(total - pnl) / abs(pnl)
        assert relative_error <= Decimal("0.001")

    def test_very_large_pnl(self) -> None:
        """Attribution handles very large PnL correctly."""
        calc = AttributionCalculator()
        pnl = Decimal("1000000000")
        entry_factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        total = sum(attribution.values())
        relative_error = abs(total - pnl) / abs(pnl)
        assert relative_error <= Decimal("0.001")

    def test_validate_empty_attribution_zero_pnl(self) -> None:
        """validate_attribution returns True for empty attribution with zero PnL."""
        calc = AttributionCalculator()

        result = calc.validate_attribution({}, Decimal("0"))

        assert result is True

    def test_validate_empty_attribution_nonzero_pnl(self) -> None:
        """validate_attribution returns False for empty attribution with non-zero PnL."""
        calc = AttributionCalculator()

        result = calc.validate_attribution({}, Decimal("100"))

        assert result is False

    def test_validate_zero_pnl_nonzero_attribution(self) -> None:
        """validate_attribution returns False when PnL is zero but attribution is not."""
        calc = AttributionCalculator()
        attribution = {"momentum_factor": Decimal("50")}

        result = calc.validate_attribution(attribution, Decimal("0"))

        assert result is False


class TestAttributionWithMixedFactors:
    """Tests with mixed factor scenarios."""

    def test_many_factors(self) -> None:
        """Attribution handles many factors correctly."""
        calc = AttributionCalculator()
        pnl = Decimal("1000")
        entry_factors = {
            "factor_1": Decimal("0.1"),
            "factor_2": Decimal("0.2"),
            "factor_3": Decimal("0.3"),
            "factor_4": Decimal("0.15"),
            "factor_5": Decimal("0.25"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors)

        # Verify all factors are present
        assert len(attribution) == 5
        # Verify sum equals PnL
        total = sum(attribution.values())
        relative_error = abs(total - pnl) / abs(pnl)
        assert relative_error <= Decimal("0.001")

    def test_unequal_weights(self) -> None:
        """Attribution with unequal weights distributes correctly."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "factor_a": Decimal("1.0"),  # Strong positive
            "factor_b": Decimal("0.1"),  # Weak positive
        }
        factor_weights = {
            "factor_a": Decimal("0.8"),
            "factor_b": Decimal("0.2"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors, factor_weights)

        # factor_a should get more attribution due to higher weight and score
        assert attribution["factor_a"] > attribution["factor_b"]
        # Sum equals PnL
        assert sum(attribution.values()) == pnl


class TestComprehensiveAttributionValidation:
    """T054: Comprehensive attribution validation tests for SC-003.

    SC-003: Sum of factor attributions must equal total PnL within 0.1% tolerance.
    """

    def test_sc003_multiple_trades_sum_validation(self) -> None:
        """SC-003: Validate attribution sums match PnL across multiple trades."""
        calc = AttributionCalculator()

        # Create multiple trades with varying PnL and factors
        test_cases = [
            # (pnl, factors)
            (Decimal("500"), {"momentum": Decimal("0.3"), "breakout": Decimal("0.7")}),
            (Decimal("-200"), {"momentum": Decimal("0.5"), "breakout": Decimal("0.5")}),
            (Decimal("1000"), {"momentum": Decimal("0.8"), "breakout": Decimal("0.2")}),
            (Decimal("-50"), {"momentum": Decimal("-0.1"), "breakout": Decimal("0.9")}),
            (Decimal("750"), {"momentum": Decimal("0.6"), "breakout": Decimal("0.4")}),
        ]

        for i, (pnl, factors) in enumerate(test_cases):
            attribution = calc.calculate_trade_attribution(pnl, factors)

            # Verify SC-003: sum equals PnL within 0.1%
            attr_sum = sum(attribution.values())

            if pnl != Decimal("0"):
                relative_error = abs(attr_sum - pnl) / abs(pnl)
                assert relative_error <= Decimal(
                    "0.001"
                ), f"Trade {i}: SC-003 FAILED - relative error {relative_error:.6f} > 0.1%"
            else:
                assert attr_sum == Decimal("0"), f"Trade {i}: Zero PnL should have zero attribution"

            # Also verify via validate method
            assert calc.validate_attribution(
                attribution, pnl
            ), f"Trade {i}: validate_attribution failed"

    def test_sc003_extreme_factor_values(self) -> None:
        """SC-003: Validate with extreme factor values."""
        calc = AttributionCalculator()

        extreme_cases = [
            # Very small factors
            {
                "pnl": Decimal("1000"),
                "factors": {"f1": Decimal("0.001"), "f2": Decimal("0.002")},
            },
            # Very large factors
            {
                "pnl": Decimal("1000"),
                "factors": {"f1": Decimal("100"), "f2": Decimal("200")},
            },
            # Mixed positive/negative
            {
                "pnl": Decimal("500"),
                "factors": {"f1": Decimal("-0.5"), "f2": Decimal("1.5")},
            },
            # One factor dominates
            {
                "pnl": Decimal("100"),
                "factors": {"f1": Decimal("0.99"), "f2": Decimal("0.01")},
            },
        ]

        for i, case in enumerate(extreme_cases):
            attribution = calc.calculate_trade_attribution(case["pnl"], case["factors"])

            assert calc.validate_attribution(
                attribution, case["pnl"]
            ), f"Extreme case {i}: SC-003 validation failed"

    def test_sc003_portfolio_level_validation(self) -> None:
        """SC-003: Validate at portfolio level (sum of all trade attributions)."""
        calc = AttributionCalculator()

        # Create trades representing a trading session
        trades_data = [
            # (pnl, factors)
            (
                Decimal("150"),
                {"momentum_factor": Decimal("0.4"), "breakout_factor": Decimal("0.6")},
            ),
            (
                Decimal("-75"),
                {"momentum_factor": Decimal("0.5"), "breakout_factor": Decimal("0.5")},
            ),
            (
                Decimal("200"),
                {"momentum_factor": Decimal("0.7"), "breakout_factor": Decimal("0.3")},
            ),
            (
                Decimal("100"),
                {"momentum_factor": Decimal("0.3"), "breakout_factor": Decimal("0.7")},
            ),
            (
                Decimal("-25"),
                {"momentum_factor": Decimal("0.6"), "breakout_factor": Decimal("0.4")},
            ),
        ]

        trades = []
        total_pnl = Decimal("0")

        for pnl, factors in trades_data:
            attribution = calc.calculate_trade_attribution(pnl, factors)
            trades.append(_create_trade_with_attribution(attribution))
            total_pnl += pnl

        # Calculate summary
        summary = calc.calculate_summary(trades)

        # Verify summary total matches sum of PnLs
        summary_total = summary.get("total", Decimal("0"))
        relative_error = (
            abs(summary_total - total_pnl) / abs(total_pnl) if total_pnl != 0 else Decimal("0")
        )

        assert relative_error <= Decimal("0.001"), (
            f"SC-003 FAILED at portfolio level: "
            f"summary total {summary_total} vs actual PnL {total_pnl}, "
            f"error {relative_error:.6f}"
        )

        print("\nPortfolio Attribution Validation:")
        print(f"  Total PnL: ${total_pnl:.2f}")
        print(f"  Summary total: ${summary_total:.2f}")
        print(f"  Relative error: {relative_error:.6f}")

    def test_sc003_with_realistic_trend_breakout_factors(self) -> None:
        """SC-003: Test with realistic TrendBreakout factor scores."""
        calc = AttributionCalculator()

        # Realistic factor scores from TrendBreakout strategy
        realistic_cases = [
            # Typical entry signal
            {
                "pnl": Decimal("250"),
                "factors": {
                    "momentum_factor": Decimal("0.035"),
                    "breakout_factor": Decimal("0.021"),
                    "composite": Decimal("0.028"),
                },
            },
            # Typical exit signal
            {
                "pnl": Decimal("-100"),
                "factors": {
                    "momentum_factor": Decimal("-0.015"),
                    "breakout_factor": Decimal("-0.025"),
                    "composite": Decimal("-0.020"),
                },
            },
            # Strong momentum
            {
                "pnl": Decimal("500"),
                "factors": {
                    "momentum_factor": Decimal("0.08"),
                    "breakout_factor": Decimal("0.02"),
                    "composite": Decimal("0.05"),
                },
            },
            # Strong breakout
            {
                "pnl": Decimal("300"),
                "factors": {
                    "momentum_factor": Decimal("0.01"),
                    "breakout_factor": Decimal("0.07"),
                    "composite": Decimal("0.04"),
                },
            },
        ]

        for i, case in enumerate(realistic_cases):
            attribution = calc.calculate_trade_attribution(case["pnl"], case["factors"])

            # Validate SC-003
            assert calc.validate_attribution(
                attribution, case["pnl"]
            ), f"Realistic case {i}: SC-003 validation failed"

            # Verify all factors are present in attribution
            for factor_name in case["factors"]:
                assert (
                    factor_name in attribution
                ), f"Realistic case {i}: Missing factor {factor_name}"

    def test_sc003_tolerance_boundary(self) -> None:
        """Test behavior at the 0.1% tolerance boundary."""
        calc = AttributionCalculator()
        pnl = Decimal("10000")

        # Create attribution that's exactly at the boundary
        factors = {"f1": Decimal("0.5"), "f2": Decimal("0.5")}
        attribution = calc.calculate_trade_attribution(pnl, factors)

        # Should pass validation
        assert calc.validate_attribution(attribution, pnl)

        # Now test with attribution that's just inside tolerance
        inside_attribution = {
            "f1": Decimal("5000.05"),  # 0.1% = $10 for $10000
            "f2": Decimal("4999.95"),
        }
        # Sum = 10000, exactly equal, so should pass
        assert calc.validate_attribution(inside_attribution, pnl)

        # Test with attribution just outside tolerance
        outside_attribution = {
            "f1": Decimal("5010"),  # Sum = 10020, 0.2% over
            "f2": Decimal("5010"),
        }
        assert not calc.validate_attribution(outside_attribution, pnl)

    def test_attribution_with_zero_and_nonzero_factors(self) -> None:
        """Test attribution when some factors are zero."""
        calc = AttributionCalculator()
        pnl = Decimal("100")

        # One factor is zero
        factors = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0"),  # Zero factor
        }

        attribution = calc.calculate_trade_attribution(pnl, factors)

        # Should still satisfy SC-003
        assert calc.validate_attribution(attribution, pnl)

        # All PnL should be attributed to non-zero factor after normalization
        # (normalization distributes based on raw values)
        assert sum(attribution.values()) == pnl

    def test_attribution_preserves_relative_proportions(self) -> None:
        """Test that attribution preserves relative factor contributions."""
        calc = AttributionCalculator()
        pnl = Decimal("1000")

        # Factors with clear 2:1 ratio in contribution
        factors = {
            "factor_a": Decimal("0.4"),
            "factor_b": Decimal("0.2"),  # Half of factor_a
        }
        # With equal weights (0.5 each):
        # raw_a = 0.5 * 0.4 * 1000 = 200
        # raw_b = 0.5 * 0.2 * 1000 = 100
        # After normalization to 1000:
        # a = 200 * 1000 / 300 = 666.67
        # b = 100 * 1000 / 300 = 333.33

        attribution = calc.calculate_trade_attribution(pnl, factors)

        # Check relative proportion is maintained (a should be 2x b)
        ratio = float(attribution["factor_a"] / attribution["factor_b"])
        assert (
            abs(ratio - 2.0) < 0.001
        ), f"Relative proportion not maintained: ratio = {ratio}, expected 2.0"


# Helper functions


def _create_trade_with_attribution(
    attribution: dict[str, Decimal],
) -> Trade:
    """Create a Trade with specified attribution for testing."""
    return Trade(
        trade_id="test-trade",
        timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
        symbol="TEST",
        side="sell",
        quantity=100,
        gross_price=Decimal("110.00"),
        slippage=Decimal("0.055"),
        commission=Decimal("0.50"),
        signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        attribution=attribution,
    )
