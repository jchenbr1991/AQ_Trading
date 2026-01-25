"""Tests for math utilities for benchmark metrics."""

from decimal import Decimal

import pytest
from src.backtest.math_utils import (
    calculate_returns,
    decimal_covariance,
    decimal_mean,
    decimal_ols,
    decimal_variance,
)


class TestCalculateReturns:
    """Tests for calculate_returns function."""

    def test_basic_returns(self) -> None:
        """Calculate returns from a simple equity curve.

        [100, 110, 121] -> [(110-100)/100, (121-110)/110] = [0.1, 0.1]
        """
        equity_values = [Decimal("100"), Decimal("110"), Decimal("121")]
        returns = calculate_returns(equity_values)

        assert len(returns) == 2
        assert abs(returns[0] - 0.1) < 1e-10
        assert abs(returns[1] - 0.1) < 1e-10

    def test_empty_list(self) -> None:
        """Empty list returns empty list."""
        equity_values: list[Decimal] = []
        returns = calculate_returns(equity_values)

        assert returns == []

    def test_single_value(self) -> None:
        """Single value returns empty list (no returns to compute)."""
        equity_values = [Decimal("100")]
        returns = calculate_returns(equity_values)

        assert returns == []

    def test_zero_previous_value(self) -> None:
        """Zero previous value returns 0.0 for that period."""
        equity_values = [Decimal("0"), Decimal("100"), Decimal("110")]
        returns = calculate_returns(equity_values)

        assert len(returns) == 2
        assert returns[0] == 0.0
        assert abs(returns[1] - 0.1) < 1e-10

    def test_negative_returns(self) -> None:
        """Negative returns are computed correctly."""
        equity_values = [Decimal("100"), Decimal("90"), Decimal("81")]
        returns = calculate_returns(equity_values)

        assert len(returns) == 2
        assert abs(returns[0] - (-0.1)) < 1e-10
        assert abs(returns[1] - (-0.1)) < 1e-10


class TestDecimalMean:
    """Tests for decimal_mean function."""

    def test_basic_mean(self) -> None:
        """Mean of [1, 2, 3] is 2.0."""
        data = [Decimal("1"), Decimal("2"), Decimal("3")]
        result = decimal_mean(data)

        assert result == 2.0

    def test_empty_list(self) -> None:
        """Empty list returns 0.0."""
        data: list[Decimal] = []
        result = decimal_mean(data)

        assert result == 0.0

    def test_single_value(self) -> None:
        """Single value returns that value as float."""
        data = [Decimal("42.5")]
        result = decimal_mean(data)

        assert result == 42.5

    def test_decimal_precision(self) -> None:
        """Mean preserves precision for fractional values."""
        data = [Decimal("1.5"), Decimal("2.5"), Decimal("3.5")]
        result = decimal_mean(data)

        assert abs(result - 2.5) < 1e-10


class TestDecimalVariance:
    """Tests for decimal_variance function."""

    def test_basic_variance(self) -> None:
        """Sample variance of [2, 4, 6] with n-1 denominator.

        mean = 4
        variance = [(2-4)^2 + (4-4)^2 + (6-4)^2] / (3-1) = [4 + 0 + 4] / 2 = 4
        """
        data = [Decimal("2"), Decimal("4"), Decimal("6")]
        result = decimal_variance(data)

        assert result == 4.0

    def test_single_value(self) -> None:
        """Single value returns 0.0."""
        data = [Decimal("42")]
        result = decimal_variance(data)

        assert result == 0.0

    def test_empty_list(self) -> None:
        """Empty list returns 0.0."""
        data: list[Decimal] = []
        result = decimal_variance(data)

        assert result == 0.0

    def test_zero_variance(self) -> None:
        """All same values returns 0.0 variance."""
        data = [Decimal("5"), Decimal("5"), Decimal("5")]
        result = decimal_variance(data)

        assert result == 0.0


class TestDecimalCovariance:
    """Tests for decimal_covariance function."""

    def test_basic_covariance(self) -> None:
        """Covariance of perfectly correlated data.

        x = [1, 2, 3], y = [2, 4, 6]
        mean_x = 2, mean_y = 4
        cov = [(1-2)(2-4) + (2-2)(4-4) + (3-2)(6-4)] / (3-1)
            = [(-1)(-2) + (0)(0) + (1)(2)] / 2
            = [2 + 0 + 2] / 2 = 2
        """
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("2"), Decimal("4"), Decimal("6")]
        result = decimal_covariance(x, y)

        assert result == 2.0

    def test_different_lengths_error(self) -> None:
        """Raise ValueError if x and y have different lengths."""
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("1"), Decimal("2")]

        with pytest.raises(ValueError, match="same length"):
            decimal_covariance(x, y)

    def test_single_value(self) -> None:
        """Single value returns 0.0 (len < 2)."""
        x = [Decimal("1")]
        y = [Decimal("2")]
        result = decimal_covariance(x, y)

        assert result == 0.0

    def test_empty_lists(self) -> None:
        """Empty lists return 0.0."""
        x: list[Decimal] = []
        y: list[Decimal] = []
        result = decimal_covariance(x, y)

        assert result == 0.0

    def test_negative_covariance(self) -> None:
        """Negatively correlated data has negative covariance."""
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("6"), Decimal("4"), Decimal("2")]
        result = decimal_covariance(x, y)

        assert result == -2.0


class TestDecimalOls:
    """Tests for decimal_ols function (OLS regression)."""

    def test_perfect_fit(self) -> None:
        """OLS on y = 2 + 3*x gives alpha=2, beta=3, residuals=0.

        x = [1, 2, 3], y = [5, 8, 11] (which is 2 + 3*x)
        """
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("5"), Decimal("8"), Decimal("11")]

        alpha, beta, residuals = decimal_ols(x, y)

        assert abs(beta - 3.0) < 1e-10
        assert abs(alpha - 2.0) < 1e-10
        assert len(residuals) == 3
        for r in residuals:
            assert abs(r) < 1e-10

    def test_zero_variance_x(self) -> None:
        """When variance(x) = 0, beta=0 and alpha=mean(y).

        x = [5, 5, 5], y = [10, 20, 30]
        beta = 0, alpha = mean(y) = 20
        """
        x = [Decimal("5"), Decimal("5"), Decimal("5")]
        y = [Decimal("10"), Decimal("20"), Decimal("30")]

        alpha, beta, residuals = decimal_ols(x, y)

        assert beta == 0.0
        assert alpha == 20.0
        assert len(residuals) == 3

    def test_empty_lists(self) -> None:
        """Empty lists return (0.0, 0.0, [])."""
        x: list[Decimal] = []
        y: list[Decimal] = []

        alpha, beta, residuals = decimal_ols(x, y)

        assert alpha == 0.0
        assert beta == 0.0
        assert residuals == []

    def test_single_point(self) -> None:
        """Single point returns (0.0, 0.0, [])."""
        x = [Decimal("1")]
        y = [Decimal("5")]

        alpha, beta, residuals = decimal_ols(x, y)

        assert alpha == 0.0
        assert beta == 0.0
        assert residuals == []

    def test_residuals_correct(self) -> None:
        """Residuals are y - (alpha + beta * x).

        x = [1, 2, 3], y = [3, 5, 8]
        This is approximately y = 0.5 + 2.5*x, but not perfect.
        """
        x = [Decimal("1"), Decimal("2"), Decimal("3")]
        y = [Decimal("3"), Decimal("5"), Decimal("8")]

        alpha, beta, residuals = decimal_ols(x, y)

        # Verify residuals: y - (alpha + beta * x)
        for i, (xi, yi) in enumerate(zip(x, y, strict=False)):
            expected_residual = float(yi) - (alpha + beta * float(xi))
            assert abs(residuals[i] - expected_residual) < 1e-10

    def test_ols_with_intercept_only(self) -> None:
        """When x values are centered, alpha is mean(y) and beta from covariance.

        x = [-1, 0, 1], y = [1, 2, 3]
        mean_x = 0, mean_y = 2
        beta = cov(x,y) / var(x) = 2 / 1 = 2
        alpha = mean_y - beta * mean_x = 2 - 2*0 = 2
        """
        x = [Decimal("-1"), Decimal("0"), Decimal("1")]
        y = [Decimal("1"), Decimal("2"), Decimal("3")]

        alpha, beta, residuals = decimal_ols(x, y)

        assert abs(beta - 1.0) < 1e-10  # cov = 1, var = 1
        assert abs(alpha - 2.0) < 1e-10
