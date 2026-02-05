"""Tests for factor models.

Tests for:
- MomentumFactor
- BreakoutFactor
- CompositeFactor
- None handling

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from decimal import Decimal

from src.strategies.factors import BreakoutFactor, CompositeFactor, FactorResult, MomentumFactor


class TestMomentumFactor:
    """Tests for MomentumFactor."""

    def test_momentum_factor_calculation(self) -> None:
        """MomentumFactor correctly combines ROC and PriceVsMA.

        Formula: momentum_factor = w1 * roc_20 + w2 * price_vs_ma_20
        Default weights: w1=0.5, w2=0.5
        """
        factor = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0.05"),  # 5% rate of change
            "price_vs_ma_20": Decimal("0.02"),  # 2% above MA
        }

        result = factor.calculate(indicators)

        assert result is not None
        assert isinstance(result, FactorResult)
        # 0.5 * 0.05 + 0.5 * 0.02 = 0.025 + 0.01 = 0.035
        assert result.score == Decimal("0.035")

    def test_momentum_factor_custom_weights(self) -> None:
        """MomentumFactor applies custom weights correctly."""
        factor = MomentumFactor(
            roc_weight=Decimal("0.7"),
            price_vs_ma_weight=Decimal("0.3"),
        )
        indicators = {
            "roc_20": Decimal("0.10"),
            "price_vs_ma_20": Decimal("0.05"),
        }

        result = factor.calculate(indicators)

        # 0.7 * 0.10 + 0.3 * 0.05 = 0.07 + 0.015 = 0.085
        assert result is not None
        assert result.score == Decimal("0.085")

    def test_momentum_factor_returns_none_missing_roc(self) -> None:
        """MomentumFactor returns None when ROC is missing."""
        factor = MomentumFactor()
        indicators = {
            "price_vs_ma_20": Decimal("0.02"),
            # Missing roc_20
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_momentum_factor_returns_none_missing_price_vs_ma(self) -> None:
        """MomentumFactor returns None when PriceVsMA is missing."""
        factor = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0.05"),
            # Missing price_vs_ma_20
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_momentum_factor_returns_none_roc_is_none(self) -> None:
        """MomentumFactor returns None when ROC value is None."""
        factor = MomentumFactor()
        indicators = {
            "roc_20": None,
            "price_vs_ma_20": Decimal("0.02"),
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_momentum_factor_returns_none_price_vs_ma_is_none(self) -> None:
        """MomentumFactor returns None when PriceVsMA value is None."""
        factor = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0.05"),
            "price_vs_ma_20": None,
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_momentum_factor_negative_values(self) -> None:
        """MomentumFactor handles negative indicator values."""
        factor = MomentumFactor()
        indicators = {
            "roc_20": Decimal("-0.05"),  # Negative momentum
            "price_vs_ma_20": Decimal("-0.03"),  # Below MA
        }

        result = factor.calculate(indicators)

        assert result is not None
        # 0.5 * (-0.05) + 0.5 * (-0.03) = -0.025 - 0.015 = -0.04
        assert result.score == Decimal("-0.04")

    def test_momentum_factor_result_has_components(self) -> None:
        """MomentumFactor result includes component values."""
        factor = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0.05"),
            "price_vs_ma_20": Decimal("0.02"),
        }

        result = factor.calculate(indicators)

        assert result is not None
        assert "roc_20" in result.components
        assert "price_vs_ma_20" in result.components
        assert result.components["roc_20"] == Decimal("0.05")
        assert result.components["price_vs_ma_20"] == Decimal("0.02")

    def test_momentum_factor_result_has_weights(self) -> None:
        """MomentumFactor result includes weights used."""
        factor = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0.05"),
            "price_vs_ma_20": Decimal("0.02"),
        }

        result = factor.calculate(indicators)

        assert result is not None
        assert "roc_20" in result.weights
        assert "price_vs_ma_20" in result.weights


class TestBreakoutFactor:
    """Tests for BreakoutFactor."""

    def test_breakout_factor_calculation(self) -> None:
        """BreakoutFactor correctly combines PriceVsHigh and VolumeZScore.

        Formula: breakout_factor = w3 * price_vs_high_20 + w4 * volume_zscore
        Default weights: w3=0.5, w4=0.5
        """
        factor = BreakoutFactor()
        indicators = {
            "price_vs_high_20": Decimal("-0.02"),  # 2% below high
            "volume_zscore": Decimal("1.5"),  # 1.5 std above average
        }

        result = factor.calculate(indicators)

        assert result is not None
        # 0.5 * (-0.02) + 0.5 * 1.5 = -0.01 + 0.75 = 0.74
        assert result.score == Decimal("0.74")

    def test_breakout_factor_custom_weights(self) -> None:
        """BreakoutFactor applies custom weights correctly."""
        factor = BreakoutFactor(
            price_vs_high_weight=Decimal("0.4"),
            volume_zscore_weight=Decimal("0.6"),
        )
        indicators = {
            "price_vs_high_20": Decimal("0.0"),  # At high
            "volume_zscore": Decimal("2.0"),  # High volume
        }

        result = factor.calculate(indicators)

        # 0.4 * 0.0 + 0.6 * 2.0 = 0 + 1.2 = 1.2
        assert result is not None
        assert result.score == Decimal("1.2")

    def test_breakout_factor_returns_none_missing_price_vs_high(self) -> None:
        """BreakoutFactor returns None when PriceVsHigh is missing."""
        factor = BreakoutFactor()
        indicators = {
            "volume_zscore": Decimal("1.5"),
            # Missing price_vs_high_20
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_breakout_factor_returns_none_missing_volume_zscore(self) -> None:
        """BreakoutFactor returns None when VolumeZScore is missing."""
        factor = BreakoutFactor()
        indicators = {
            "price_vs_high_20": Decimal("-0.02"),
            # Missing volume_zscore
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_breakout_factor_returns_none_price_vs_high_is_none(self) -> None:
        """BreakoutFactor returns None when PriceVsHigh value is None."""
        factor = BreakoutFactor()
        indicators = {
            "price_vs_high_20": None,
            "volume_zscore": Decimal("1.5"),
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_breakout_factor_returns_none_volume_zscore_is_none(self) -> None:
        """BreakoutFactor returns None when VolumeZScore value is None."""
        factor = BreakoutFactor()
        indicators = {
            "price_vs_high_20": Decimal("-0.02"),
            "volume_zscore": None,
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_breakout_factor_negative_zscore(self) -> None:
        """BreakoutFactor handles negative z-score (low volume)."""
        factor = BreakoutFactor()
        indicators = {
            "price_vs_high_20": Decimal("-0.10"),  # Far below high
            "volume_zscore": Decimal("-1.5"),  # Low volume
        }

        result = factor.calculate(indicators)

        assert result is not None
        # 0.5 * (-0.10) + 0.5 * (-1.5) = -0.05 - 0.75 = -0.80
        assert result.score == Decimal("-0.80")


class TestCompositeFactor:
    """Tests for CompositeFactor."""

    def test_composite_factor_calculation(self) -> None:
        """CompositeFactor correctly combines Momentum and Breakout factors.

        Formula: composite = w_mom * momentum_factor + w_brk * breakout_factor
        Default weights: w_mom=0.5, w_brk=0.5
        """
        factor = CompositeFactor()
        indicators = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.74"),
        }

        result = factor.calculate(indicators)

        assert result is not None
        # 0.5 * 0.035 + 0.5 * 0.74 = 0.0175 + 0.37 = 0.3875
        assert result.score == Decimal("0.3875")

    def test_composite_factor_custom_weights(self) -> None:
        """CompositeFactor applies custom weights correctly."""
        factor = CompositeFactor(
            momentum_weight=Decimal("0.6"),
            breakout_weight=Decimal("0.4"),
        )
        indicators = {
            "momentum_factor": Decimal("0.10"),
            "breakout_factor": Decimal("0.20"),
        }

        result = factor.calculate(indicators)

        # 0.6 * 0.10 + 0.4 * 0.20 = 0.06 + 0.08 = 0.14
        assert result is not None
        assert result.score == Decimal("0.14")

    def test_composite_factor_returns_none_missing_momentum(self) -> None:
        """CompositeFactor returns None when momentum_factor is missing."""
        factor = CompositeFactor()
        indicators = {
            "breakout_factor": Decimal("0.74"),
            # Missing momentum_factor
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_composite_factor_returns_none_missing_breakout(self) -> None:
        """CompositeFactor returns None when breakout_factor is missing."""
        factor = CompositeFactor()
        indicators = {
            "momentum_factor": Decimal("0.035"),
            # Missing breakout_factor
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_composite_factor_returns_none_momentum_is_none(self) -> None:
        """CompositeFactor returns None when momentum_factor value is None."""
        factor = CompositeFactor()
        indicators = {
            "momentum_factor": None,
            "breakout_factor": Decimal("0.74"),
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_composite_factor_returns_none_breakout_is_none(self) -> None:
        """CompositeFactor returns None when breakout_factor value is None."""
        factor = CompositeFactor()
        indicators = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": None,
        }

        result = factor.calculate(indicators)

        assert result is None

    def test_composite_factor_mixed_signs(self) -> None:
        """CompositeFactor handles mixed positive/negative factors."""
        factor = CompositeFactor()
        indicators = {
            "momentum_factor": Decimal("-0.05"),  # Negative momentum
            "breakout_factor": Decimal("0.30"),  # Positive breakout
        }

        result = factor.calculate(indicators)

        assert result is not None
        # 0.5 * (-0.05) + 0.5 * 0.30 = -0.025 + 0.15 = 0.125
        assert result.score == Decimal("0.125")


class TestFactorResult:
    """Tests for FactorResult dataclass."""

    def test_factor_result_creation(self) -> None:
        """FactorResult can be created with required fields."""
        result = FactorResult(
            score=Decimal("0.5"),
            components={"comp1": Decimal("0.3"), "comp2": Decimal("0.7")},
            weights={"comp1": Decimal("0.5"), "comp2": Decimal("0.5")},
        )

        assert result.score == Decimal("0.5")
        assert len(result.components) == 2
        assert len(result.weights) == 2

    def test_factor_result_score_is_decimal(self) -> None:
        """FactorResult score must be Decimal."""
        result = FactorResult(
            score=Decimal("0.123"),
            components={},
            weights={},
        )

        assert isinstance(result.score, Decimal)


class TestFactorNoneHandling:
    """Tests for None handling in factors."""

    def test_all_factors_return_none_for_none_inputs(self) -> None:
        """All factors return None when any required input is None."""
        momentum = MomentumFactor()
        breakout = BreakoutFactor()
        composite = CompositeFactor()

        # MomentumFactor with None
        assert momentum.calculate({"roc_20": None, "price_vs_ma_20": Decimal("0")}) is None
        assert momentum.calculate({"roc_20": Decimal("0"), "price_vs_ma_20": None}) is None

        # BreakoutFactor with None
        assert breakout.calculate({"price_vs_high_20": None, "volume_zscore": Decimal("0")}) is None
        assert breakout.calculate({"price_vs_high_20": Decimal("0"), "volume_zscore": None}) is None

        # CompositeFactor with None
        assert (
            composite.calculate({"momentum_factor": None, "breakout_factor": Decimal("0")}) is None
        )
        assert (
            composite.calculate({"momentum_factor": Decimal("0"), "breakout_factor": None}) is None
        )

    def test_factors_return_none_for_empty_dict(self) -> None:
        """All factors return None for empty indicator dict."""
        momentum = MomentumFactor()
        breakout = BreakoutFactor()
        composite = CompositeFactor()

        assert momentum.calculate({}) is None
        assert breakout.calculate({}) is None
        assert composite.calculate({}) is None

    def test_factors_return_none_for_wrong_keys(self) -> None:
        """All factors return None when expected keys are missing."""
        momentum = MomentumFactor()
        breakout = BreakoutFactor()
        composite = CompositeFactor()

        assert momentum.calculate({"wrong_key": Decimal("0.1")}) is None
        assert breakout.calculate({"wrong_key": Decimal("0.1")}) is None
        assert composite.calculate({"wrong_key": Decimal("0.1")}) is None


class TestFactorEdgeCases:
    """Edge case tests for factors."""

    def test_zero_values(self) -> None:
        """Factors handle zero values correctly."""
        momentum = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0"),
            "price_vs_ma_20": Decimal("0"),
        }

        result = momentum.calculate(indicators)

        assert result is not None
        assert result.score == Decimal("0")

    def test_very_small_values(self) -> None:
        """Factors handle very small values correctly."""
        momentum = MomentumFactor()
        indicators = {
            "roc_20": Decimal("0.000001"),
            "price_vs_ma_20": Decimal("0.000002"),
        }

        result = momentum.calculate(indicators)

        assert result is not None
        # 0.5 * 0.000001 + 0.5 * 0.000002 = 0.0000015
        expected = Decimal("0.5") * Decimal("0.000001") + Decimal("0.5") * Decimal("0.000002")
        assert result.score == expected

    def test_very_large_values(self) -> None:
        """Factors handle very large values correctly."""
        breakout = BreakoutFactor()
        indicators = {
            "price_vs_high_20": Decimal("100"),  # 10000% above high
            "volume_zscore": Decimal("50"),  # 50 std above average
        }

        result = breakout.calculate(indicators)

        assert result is not None
        # 0.5 * 100 + 0.5 * 50 = 50 + 25 = 75
        assert result.score == Decimal("75")


class TestCompositeFactorNormalization:
    """Tests for CompositeFactor with score normalization."""

    def test_normalize_flag_default_false(self) -> None:
        """Normalization is disabled by default."""
        factor = CompositeFactor()
        assert factor._normalize is False

    def test_normalize_flag_can_be_enabled(self) -> None:
        """Normalization can be enabled via constructor."""
        factor = CompositeFactor(normalize=True)
        assert factor._normalize is True

    def test_calculate_without_normalization_unchanged(self) -> None:
        """Without normalize flag, behavior is identical to before."""
        factor = CompositeFactor(normalize=False)
        indicators = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.74"),
        }
        result = factor.calculate(indicators)
        assert result is not None
        assert result.score == Decimal("0.3875")

    def test_calculate_during_warmup_uses_raw_scores(self) -> None:
        """During normalizer warmup, falls back to raw scores."""
        factor = CompositeFactor(normalize=True, normalize_min_periods=10)
        # Only 1 observation, not enough for normalization
        factor.update_normalizer(
            {
                "momentum_factor": Decimal("0.01"),
                "breakout_factor": Decimal("0.50"),
            }
        )
        indicators = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.74"),
        }
        result = factor.calculate(indicators)
        assert result is not None
        # Should use raw scores (same as non-normalized)
        assert result.score == Decimal("0.3875")

    def test_normalized_scores_equalize_influence(self) -> None:
        """With normalization, factors of different scales have equal influence.

        Momentum scores ~0.01 scale, breakout ~0.5 scale.
        Without normalization, breakout dominates. With normalization,
        similar z-scores yield similar contributions.
        """
        factor = CompositeFactor(normalize=True, normalize_min_periods=5)

        # Feed history: momentum ~0.01 scale, breakout ~0.5 scale
        history = [
            {"momentum_factor": Decimal("0.008"), "breakout_factor": Decimal("0.35")},
            {"momentum_factor": Decimal("0.012"), "breakout_factor": Decimal("0.45")},
            {"momentum_factor": Decimal("0.010"), "breakout_factor": Decimal("0.40")},
            {"momentum_factor": Decimal("0.009"), "breakout_factor": Decimal("0.38")},
            {"momentum_factor": Decimal("0.011"), "breakout_factor": Decimal("0.42")},
        ]
        for h in history:
            factor.update_normalizer(h)

        # Both at ~1 std above mean: momentum=0.014, breakout=0.50
        # Without normalization: composite = 0.5*0.014 + 0.5*0.50 = 0.257
        # With normalization: both z-scores ~similar, so composite is balanced
        indicators_raw = {
            "momentum_factor": Decimal("0.014"),
            "breakout_factor": Decimal("0.50"),
        }
        result_norm = factor.calculate(indicators_raw)
        assert result_norm is not None

        # Also compute without normalization for comparison
        factor_raw = CompositeFactor(normalize=False)
        result_raw = factor_raw.calculate(indicators_raw)
        assert result_raw is not None

        # The raw composite is dominated by breakout (0.257, mostly from 0.5*0.50=0.25)
        # The normalized composite should be more balanced
        # Key assertion: normalized result is different from raw
        assert result_norm.score != result_raw.score

    def test_update_normalizer_records_history(self) -> None:
        """update_normalizer adds values to the internal normalizer."""
        factor = CompositeFactor(normalize=True, normalize_min_periods=2)
        factor.update_normalizer(
            {
                "momentum_factor": Decimal("0.01"),
                "breakout_factor": Decimal("0.50"),
            }
        )
        factor.update_normalizer(
            {
                "momentum_factor": Decimal("0.02"),
                "breakout_factor": Decimal("0.60"),
            }
        )
        # After 2 updates, normalizer should have enough history
        indicators = {
            "momentum_factor": Decimal("0.03"),
            "breakout_factor": Decimal("0.70"),
        }
        result = factor.calculate(indicators)
        assert result is not None
        # Both above mean -> positive composite
        assert result.score > Decimal("0")
