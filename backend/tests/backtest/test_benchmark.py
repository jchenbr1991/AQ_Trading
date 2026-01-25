"""Tests for BenchmarkComparison dataclass."""

from decimal import Decimal

import pytest
from src.backtest.benchmark import BenchmarkComparison


class TestBenchmarkComparison:
    """Tests for BenchmarkComparison dataclass."""

    def test_create_benchmark_comparison_with_all_fields(self) -> None:
        """Create BenchmarkComparison and verify all fields are set correctly."""
        comparison = BenchmarkComparison(
            benchmark_symbol="SPY",
            benchmark_total_return=Decimal("0.15"),
            alpha=Decimal("0.05"),
            beta=Decimal("1.2"),
            tracking_error=Decimal("0.08"),
            information_ratio=Decimal("0.625"),
            sortino_ratio=Decimal("1.8"),
            up_capture=Decimal("1.1"),
            down_capture=Decimal("0.9"),
        )

        assert comparison.benchmark_symbol == "SPY"
        assert comparison.benchmark_total_return == Decimal("0.15")
        assert comparison.alpha == Decimal("0.05")
        assert comparison.beta == Decimal("1.2")
        assert comparison.tracking_error == Decimal("0.08")
        assert comparison.information_ratio == Decimal("0.625")
        assert comparison.sortino_ratio == Decimal("1.8")
        assert comparison.up_capture == Decimal("1.1")
        assert comparison.down_capture == Decimal("0.9")

    def test_benchmark_comparison_is_frozen(self) -> None:
        """Verify BenchmarkComparison is immutable - raises exception on modification."""
        comparison = BenchmarkComparison(
            benchmark_symbol="SPY",
            benchmark_total_return=Decimal("0.15"),
            alpha=Decimal("0.05"),
            beta=Decimal("1.2"),
            tracking_error=Decimal("0.08"),
            information_ratio=Decimal("0.625"),
            sortino_ratio=Decimal("1.8"),
            up_capture=Decimal("1.1"),
            down_capture=Decimal("0.9"),
        )

        # Verify modifying any field raises FrozenInstanceError (subclass of AttributeError)
        with pytest.raises(AttributeError):
            comparison.benchmark_symbol = "QQQ"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            comparison.alpha = Decimal("0.10")  # type: ignore[misc]

        with pytest.raises(AttributeError):
            comparison.beta = Decimal("0.8")  # type: ignore[misc]
