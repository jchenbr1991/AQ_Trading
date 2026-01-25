"""Tests for BenchmarkComparison dataclass and BenchmarkBuilder."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from src.backtest.benchmark import BenchmarkBuilder, BenchmarkComparison
from src.backtest.models import Bar


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


class TestBenchmarkBuilder:
    """Tests for BenchmarkBuilder class."""

    def test_buy_and_hold_basic(self) -> None:
        """Normalizes bars to initial capital correctly."""
        bars = [
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1000000,
            ),
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc),
                open=Decimal("101"),
                high=Decimal("110"),
                low=Decimal("100"),
                close=Decimal("110"),
                volume=1200000,
            ),
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 3, 16, 0, 0, tzinfo=timezone.utc),
                open=Decimal("109"),
                high=Decimal("115"),
                low=Decimal("108"),
                close=Decimal("105"),
                volume=900000,
            ),
        ]
        initial_capital = Decimal("10000")

        result = BenchmarkBuilder.buy_and_hold(bars, initial_capital)

        assert len(result) == 3
        # First bar: (100 / 100) * 10000 = 10000
        assert result[0] == (
            datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc),
            Decimal("10000"),
        )
        # Second bar: (110 / 100) * 10000 = 11000
        assert result[1] == (
            datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc),
            Decimal("11000"),
        )
        # Third bar: (105 / 100) * 10000 = 10500
        assert result[2] == (
            datetime(2024, 1, 3, 16, 0, 0, tzinfo=timezone.utc),
            Decimal("10500"),
        )

    def test_buy_and_hold_empty_bars(self) -> None:
        """Empty bars returns empty list."""
        result = BenchmarkBuilder.buy_and_hold([], Decimal("10000"))

        assert result == []

    def test_buy_and_hold_uses_close_price(self) -> None:
        """Verifies only bar.close is used (not open/high/low)."""
        # Create bars where open/high/low differ significantly from close
        bars = [
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc),
                open=Decimal("50"),  # Different from close
                high=Decimal("200"),  # Different from close
                low=Decimal("25"),  # Different from close
                close=Decimal("100"),  # Use this
                volume=1000000,
            ),
            Bar(
                symbol="SPY",
                timestamp=datetime(2024, 1, 2, 16, 0, 0, tzinfo=timezone.utc),
                open=Decimal("80"),  # Different from close
                high=Decimal("180"),  # Different from close
                low=Decimal("70"),  # Different from close
                close=Decimal("120"),  # Use this
                volume=1200000,
            ),
        ]
        initial_capital = Decimal("10000")

        result = BenchmarkBuilder.buy_and_hold(bars, initial_capital)

        # If open were used: (80/50) * 10000 = 16000
        # If high were used: (180/200) * 10000 = 9000
        # If low were used: (70/25) * 10000 = 28000
        # If close is used: (120/100) * 10000 = 12000
        assert result[1][1] == Decimal("12000")
