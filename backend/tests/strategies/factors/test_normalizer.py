"""Tests for ScoreNormalizer.

Tests rolling z-score normalization for factor scores:
- Warmup behavior (returns None until min_periods)
- Z-score correctness
- Zero std handling
- Window size memory bounding
- Independent factor histories
"""

from decimal import Decimal

from src.strategies.factors.normalizer import ScoreNormalizer


class TestScoreNormalizerWarmup:
    """Tests for warmup behavior."""

    def test_returns_none_during_warmup(self) -> None:
        """Returns None when not enough history to normalize."""
        norm = ScoreNormalizer(min_periods=5)
        norm.update("factor_a", Decimal("1.0"))
        result = norm.normalize("factor_a", Decimal("1.0"))
        assert result is None

    def test_returns_none_for_unknown_factor(self) -> None:
        """Returns None for factors with no history."""
        norm = ScoreNormalizer(min_periods=3)
        result = norm.normalize("unknown", Decimal("1.0"))
        assert result is None

    def test_normalizes_after_min_periods(self) -> None:
        """Returns normalized value once min_periods reached."""
        norm = ScoreNormalizer(min_periods=3)
        for v in [Decimal("10"), Decimal("20"), Decimal("30")]:
            norm.update("f", v)
        result = norm.normalize("f", Decimal("40"))
        assert result is not None
        assert isinstance(result, Decimal)


class TestScoreNormalizerZScore:
    """Tests for z-score calculation correctness."""

    def test_z_score_of_mean_is_zero(self) -> None:
        """Z-score of the mean value is zero."""
        norm = ScoreNormalizer(min_periods=3)
        for v in [Decimal("10"), Decimal("20"), Decimal("30")]:
            norm.update("f", v)
        # mean = 20, z-score of 20 should be ~0
        result = norm.normalize("f", Decimal("20"))
        assert result is not None
        assert abs(result) < Decimal("0.01")

    def test_z_score_above_mean_is_positive(self) -> None:
        """Values above mean produce positive z-scores."""
        norm = ScoreNormalizer(min_periods=3)
        for v in [Decimal("10"), Decimal("20"), Decimal("30")]:
            norm.update("f", v)
        result = norm.normalize("f", Decimal("40"))
        assert result is not None
        assert result > Decimal("0")

    def test_z_score_below_mean_is_negative(self) -> None:
        """Values below mean produce negative z-scores."""
        norm = ScoreNormalizer(min_periods=3)
        for v in [Decimal("10"), Decimal("20"), Decimal("30")]:
            norm.update("f", v)
        result = norm.normalize("f", Decimal("5"))
        assert result is not None
        assert result < Decimal("0")

    def test_z_score_magnitude_correct(self) -> None:
        """Z-score magnitude is mathematically correct."""
        norm = ScoreNormalizer(min_periods=4)
        # [10, 20, 30, 40] -> mean=25, population std = sqrt(125) ≈ 11.18
        for v in [Decimal("10"), Decimal("20"), Decimal("30"), Decimal("40")]:
            norm.update("f", v)
        # z-score of 25 + 11.18 ≈ 36.18 should be ~1.0
        result = norm.normalize("f", Decimal("25") + Decimal("11.180339887498949"))
        assert result is not None
        assert abs(result - Decimal("1")) < Decimal("0.01")

    def test_zero_std_returns_zero(self) -> None:
        """Returns zero when all values are identical (std=0)."""
        norm = ScoreNormalizer(min_periods=3)
        for _ in range(5):
            norm.update("f", Decimal("42"))
        result = norm.normalize("f", Decimal("42"))
        assert result == Decimal("0")


class TestScoreNormalizerWindow:
    """Tests for window size bounding."""

    def test_window_size_limits_memory(self) -> None:
        """History is bounded by window_size."""
        norm = ScoreNormalizer(min_periods=3, window_size=5)
        for i in range(100):
            norm.update("f", Decimal(str(i)))
        assert len(norm._history["f"]) <= 5

    def test_window_size_affects_statistics(self) -> None:
        """Recent values dominate when window is small."""
        norm = ScoreNormalizer(min_periods=3, window_size=3)
        # Feed old values (small)
        for v in [Decimal("1"), Decimal("2"), Decimal("3")]:
            norm.update("f", v)
        # Feed new values (large) — old ones should be evicted
        for v in [Decimal("100"), Decimal("200"), Decimal("300")]:
            norm.update("f", v)
        # mean should be ~200, not ~101
        result = norm.normalize("f", Decimal("200"))
        assert result is not None
        assert abs(result) < Decimal("0.01")  # 200 is the mean of [100,200,300]


class TestScoreNormalizerMultipleFactors:
    """Tests for independent factor histories."""

    def test_multiple_factors_independent(self) -> None:
        """Each factor has independent history."""
        norm = ScoreNormalizer(min_periods=2)
        for v in [Decimal("10"), Decimal("20")]:
            norm.update("a", v)
        for v in [Decimal("100"), Decimal("200")]:
            norm.update("b", v)

        result_a = norm.normalize("a", Decimal("30"))
        result_b = norm.normalize("b", Decimal("300"))
        assert result_a is not None
        assert result_b is not None
        # Both above mean -> positive z-scores
        assert result_a > Decimal("0")
        assert result_b > Decimal("0")

    def test_update_one_factor_doesnt_affect_other(self) -> None:
        """Updating one factor doesn't change another's statistics."""
        norm = ScoreNormalizer(min_periods=2)
        for v in [Decimal("10"), Decimal("20")]:
            norm.update("a", v)
        for v in [Decimal("10"), Decimal("20")]:
            norm.update("b", v)

        baseline = norm.normalize("a", Decimal("30"))

        # Update b extensively
        for v in [Decimal("1000"), Decimal("2000"), Decimal("3000")]:
            norm.update("b", v)

        after = norm.normalize("a", Decimal("30"))
        assert baseline == after
