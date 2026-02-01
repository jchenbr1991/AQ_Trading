# AQ Trading AI Agents - Walk Forward Validator Tests
# T029: Tests for WalkForwardValidator overfitting protection
"""Tests for the walk-forward validation module.

Tests cover:
- ValidationResult and StabilityResult dataclasses
- WalkForwardValidator initialization and validation
- Data splitting (DataFrame and sequence)
- Performance degradation checks
- Parameter stability analysis
- Edge cases and error handling
"""

import pytest
import pandas as pd
from datetime import datetime, timedelta

from agents.validation.walk_forward import (
    StabilityResult,
    ValidationResult,
    WalkForwardValidator,
)


# ==============================================================================
# Test Fixtures and Helpers
# ==============================================================================


@pytest.fixture
def validator() -> WalkForwardValidator:
    """Default validator with standard parameters."""
    return WalkForwardValidator()


@pytest.fixture
def strict_validator() -> WalkForwardValidator:
    """Validator with strict degradation threshold."""
    return WalkForwardValidator(max_degradation=0.10)


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Sample DataFrame with 100 rows for testing splits."""
    start_date = datetime(2024, 1, 1)
    dates = [start_date + timedelta(days=i) for i in range(100)]
    return pd.DataFrame({
        "date": dates,
        "value": range(100),
        "metric": [i * 0.1 for i in range(100)],
    })


@pytest.fixture
def sample_sequence() -> list[int]:
    """Sample sequence for testing splits."""
    return list(range(100))


# ==============================================================================
# ValidationResult Tests
# ==============================================================================


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_create_valid_result(self):
        """ValidationResult can be created with valid=True."""
        result = ValidationResult(
            is_valid=True,
            train_performance=1.5,
            val_performance=1.4,
            test_performance=1.3,
            degradation_train_val=0.067,
            degradation_val_test=0.071,
            reason=None,
        )

        assert result.is_valid is True
        assert result.train_performance == 1.5
        assert result.val_performance == 1.4
        assert result.test_performance == 1.3
        assert result.degradation_train_val == pytest.approx(0.067, rel=0.01)
        assert result.degradation_val_test == pytest.approx(0.071, rel=0.01)
        assert result.reason is None

    def test_create_invalid_result(self):
        """ValidationResult can be created with valid=False and reason."""
        result = ValidationResult(
            is_valid=False,
            train_performance=1.5,
            val_performance=1.0,
            test_performance=0.8,
            degradation_train_val=0.333,
            degradation_val_test=0.20,
            reason="Performance degraded too much",
        )

        assert result.is_valid is False
        assert result.reason == "Performance degraded too much"

    def test_result_is_frozen(self):
        """ValidationResult is immutable."""
        result = ValidationResult(
            is_valid=True,
            train_performance=1.5,
            val_performance=1.4,
            test_performance=1.3,
            degradation_train_val=0.067,
            degradation_val_test=0.071,
            reason=None,
        )

        with pytest.raises(AttributeError):
            result.is_valid = False  # type: ignore


# ==============================================================================
# StabilityResult Tests
# ==============================================================================


class TestStabilityResult:
    """Tests for StabilityResult dataclass."""

    def test_create_stable_result(self):
        """StabilityResult can be created for stable model."""
        result = StabilityResult(
            is_stable=True,
            perturbation_results={
                "baseline": 1.5,
                "+10%": 1.45,
                "-10%": 1.48,
            },
            max_deviation=0.033,
            reason=None,
        )

        assert result.is_stable is True
        assert result.perturbation_results["baseline"] == 1.5
        assert result.max_deviation == pytest.approx(0.033, rel=0.01)
        assert result.reason is None

    def test_create_unstable_result(self):
        """StabilityResult can be created for unstable model."""
        result = StabilityResult(
            is_stable=False,
            perturbation_results={
                "baseline": 1.5,
                "+20%": 1.0,
            },
            max_deviation=0.333,
            reason="Excessive sensitivity to +20%",
        )

        assert result.is_stable is False
        assert result.max_deviation == pytest.approx(0.333, rel=0.01)
        assert "Excessive" in result.reason

    def test_result_is_frozen(self):
        """StabilityResult is immutable."""
        result = StabilityResult(
            is_stable=True,
            perturbation_results={},
            max_deviation=0.0,
            reason=None,
        )

        with pytest.raises(AttributeError):
            result.is_stable = False  # type: ignore


# ==============================================================================
# WalkForwardValidator Initialization Tests
# ==============================================================================


class TestWalkForwardValidatorInit:
    """Tests for WalkForwardValidator initialization."""

    def test_default_init(self):
        """Validator initializes with default values."""
        validator = WalkForwardValidator()

        assert validator.train_pct == 0.70
        assert validator.val_pct == 0.15
        assert validator.test_pct == 0.15
        assert validator.max_degradation == 0.20

    def test_custom_split_percentages(self):
        """Validator accepts custom split percentages."""
        validator = WalkForwardValidator(
            train_pct=0.60,
            val_pct=0.20,
            test_pct=0.20,
        )

        assert validator.train_pct == 0.60
        assert validator.val_pct == 0.20
        assert validator.test_pct == 0.20

    def test_custom_max_degradation(self):
        """Validator accepts custom max_degradation."""
        validator = WalkForwardValidator(max_degradation=0.10)

        assert validator.max_degradation == 0.10

    def test_invalid_train_pct_raises_error(self):
        """Invalid train_pct raises ValueError."""
        with pytest.raises(ValueError, match="train_pct must be between"):
            WalkForwardValidator(train_pct=0.0)

        with pytest.raises(ValueError, match="train_pct must be between"):
            WalkForwardValidator(train_pct=1.0)

        with pytest.raises(ValueError, match="train_pct must be between"):
            WalkForwardValidator(train_pct=-0.1)

    def test_invalid_val_pct_raises_error(self):
        """Invalid val_pct raises ValueError."""
        with pytest.raises(ValueError, match="val_pct must be between"):
            WalkForwardValidator(val_pct=0.0)

    def test_invalid_test_pct_raises_error(self):
        """Invalid test_pct raises ValueError."""
        with pytest.raises(ValueError, match="test_pct must be between"):
            WalkForwardValidator(test_pct=0.0)

    def test_percentages_not_summing_to_one_raises_error(self):
        """Percentages not summing to 1.0 raises ValueError."""
        with pytest.raises(ValueError, match="must sum to 1.0"):
            WalkForwardValidator(
                train_pct=0.60,
                val_pct=0.20,
                test_pct=0.10,  # Sum = 0.90
            )

    def test_invalid_max_degradation_raises_error(self):
        """Invalid max_degradation raises ValueError."""
        with pytest.raises(ValueError, match="max_degradation must be between"):
            WalkForwardValidator(max_degradation=0.0)

        with pytest.raises(ValueError, match="max_degradation must be between"):
            WalkForwardValidator(max_degradation=1.5)

    def test_repr(self):
        """Validator has informative repr."""
        validator = WalkForwardValidator()
        repr_str = repr(validator)

        assert "WalkForwardValidator" in repr_str
        assert "70%" in repr_str
        assert "15%" in repr_str
        assert "20%" in repr_str


# ==============================================================================
# Data Splitting Tests
# ==============================================================================


class TestSplitData:
    """Tests for DataFrame splitting."""

    def test_split_data_correct_sizes(
        self, validator: WalkForwardValidator, sample_dataframe: pd.DataFrame
    ):
        """split_data returns correctly sized DataFrames."""
        train, val, test = validator.split_data(sample_dataframe, "date")

        # 70/15/15 split of 100 rows
        assert len(train) == 70
        assert len(val) == 15
        assert len(test) == 15

    def test_split_data_temporal_order(
        self, validator: WalkForwardValidator, sample_dataframe: pd.DataFrame
    ):
        """split_data maintains temporal order."""
        train, val, test = validator.split_data(sample_dataframe, "date")

        # Train dates should be before val dates
        assert train["date"].max() < val["date"].min()
        # Val dates should be before test dates
        assert val["date"].max() < test["date"].min()

    def test_split_data_no_overlap(
        self, validator: WalkForwardValidator, sample_dataframe: pd.DataFrame
    ):
        """split_data produces non-overlapping sets."""
        train, val, test = validator.split_data(sample_dataframe, "date")

        train_values = set(train["value"])
        val_values = set(val["value"])
        test_values = set(test["value"])

        # No overlap between sets
        assert len(train_values & val_values) == 0
        assert len(val_values & test_values) == 0
        assert len(train_values & test_values) == 0

    def test_split_data_complete_coverage(
        self, validator: WalkForwardValidator, sample_dataframe: pd.DataFrame
    ):
        """split_data covers all original data."""
        train, val, test = validator.split_data(sample_dataframe, "date")

        total = len(train) + len(val) + len(test)
        assert total == len(sample_dataframe)

    def test_split_data_unsorted_input(self, validator: WalkForwardValidator):
        """split_data handles unsorted input correctly."""
        # Create data in random order using timedelta for valid dates
        start = datetime(2024, 1, 1)
        dates = [
            start + timedelta(days=50),  # Middle
            start + timedelta(days=0),   # Start
            start + timedelta(days=99),  # End
        ] + [start + timedelta(days=i) for i in range(1, 99) if i != 50]

        df = pd.DataFrame({
            "date": dates,
            "value": range(len(dates)),
        })

        train, val, test = validator.split_data(df, "date")

        # Should still maintain temporal order after split
        assert train["date"].max() < val["date"].min()
        assert val["date"].max() < test["date"].min()

    def test_split_data_missing_column_raises_error(
        self, validator: WalkForwardValidator, sample_dataframe: pd.DataFrame
    ):
        """split_data raises error for missing date column."""
        with pytest.raises(ValueError, match="not found in data"):
            validator.split_data(sample_dataframe, "missing_column")

    def test_split_data_empty_dataframe_raises_error(
        self, validator: WalkForwardValidator
    ):
        """split_data raises error for empty DataFrame."""
        empty_df = pd.DataFrame({"date": [], "value": []})

        with pytest.raises(ValueError, match="Cannot split empty"):
            validator.split_data(empty_df, "date")

    def test_split_data_too_small_dataframe_raises_error(
        self, validator: WalkForwardValidator
    ):
        """split_data raises error for too small DataFrame."""
        start = datetime(2024, 1, 1)
        small_df = pd.DataFrame({
            "date": [start + timedelta(days=i) for i in range(5)],
            "value": range(5),
        })

        with pytest.raises(ValueError, match="too small to split"):
            validator.split_data(small_df, "date")

    def test_split_data_custom_percentages(self):
        """split_data respects custom percentages."""
        validator = WalkForwardValidator(
            train_pct=0.60,
            val_pct=0.20,
            test_pct=0.20,
        )

        start = datetime(2024, 1, 1)
        df = pd.DataFrame({
            "date": [start + timedelta(days=i) for i in range(100)],
            "value": range(100),
        })

        train, val, test = validator.split_data(df, "date")

        # 60/20/20 split of 100 rows
        assert len(train) == 60
        assert len(val) == 20
        assert len(test) == 20


class TestSplitSequence:
    """Tests for sequence splitting."""

    def test_split_sequence_correct_sizes(
        self, validator: WalkForwardValidator, sample_sequence: list[int]
    ):
        """split_sequence returns correctly sized sequences."""
        train, val, test = validator.split_sequence(sample_sequence)

        assert len(train) == 70
        assert len(val) == 15
        assert len(test) == 15

    def test_split_sequence_preserves_order(
        self, validator: WalkForwardValidator, sample_sequence: list[int]
    ):
        """split_sequence preserves original order."""
        train, val, test = validator.split_sequence(sample_sequence)

        # Train ends before val starts
        assert max(train) < min(val)
        # Val ends before test starts
        assert max(val) < min(test)

    def test_split_sequence_empty_raises_error(
        self, validator: WalkForwardValidator
    ):
        """split_sequence raises error for empty sequence."""
        with pytest.raises(ValueError, match="Cannot split empty"):
            validator.split_sequence([])

    def test_split_sequence_too_small_raises_error(
        self, validator: WalkForwardValidator
    ):
        """split_sequence raises error for too small sequence."""
        with pytest.raises(ValueError, match="too small to split"):
            validator.split_sequence([1, 2, 3, 4, 5])


# ==============================================================================
# Performance Validation Tests
# ==============================================================================


class TestValidatePerformance:
    """Tests for performance validation."""

    def test_validate_performance_passes_with_small_degradation(
        self, validator: WalkForwardValidator
    ):
        """Validation passes when degradation is within threshold."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.4},  # ~7% drop
            test_metrics={"sharpe": 1.3},  # ~7% drop
        )

        assert result.is_valid is True
        assert result.reason is None
        assert result.train_performance == 1.5
        assert result.val_performance == 1.4
        assert result.test_performance == 1.3

    def test_validate_performance_fails_train_to_val_degradation(
        self, validator: WalkForwardValidator
    ):
        """Validation fails when train-to-val degradation exceeds threshold."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.0},  # 33% drop
            test_metrics={"sharpe": 0.9},
        )

        assert result.is_valid is False
        assert "Train-to-validation" in result.reason
        assert "overfitting" in result.reason.lower()

    def test_validate_performance_fails_val_to_test_degradation(
        self, validator: WalkForwardValidator
    ):
        """Validation fails when val-to-test degradation exceeds threshold."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.4},  # ~7% drop (OK)
            test_metrics={"sharpe": 1.0},  # 29% drop (FAIL)
        )

        assert result.is_valid is False
        assert "Validation-to-test" in result.reason

    def test_validate_performance_with_strict_threshold(
        self, strict_validator: WalkForwardValidator
    ):
        """Stricter threshold catches smaller degradation."""
        # This would pass with default 20% threshold
        result = strict_validator.validate_performance(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.3},  # 13% drop
            test_metrics={"sharpe": 1.2},
        )

        assert result.is_valid is False
        assert strict_validator.max_degradation == 0.10

    def test_validate_performance_custom_primary_metric(
        self, validator: WalkForwardValidator
    ):
        """Validation works with custom primary metric."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 1.5, "return": 0.15},
            val_metrics={"sharpe": 1.2, "return": 0.14},
            test_metrics={"sharpe": 0.8, "return": 0.13},
            primary_metric="return",
        )

        # Using return metric which has smaller degradation
        assert result.is_valid is True
        assert result.train_performance == 0.15

    def test_validate_performance_missing_metric_raises_error(
        self, validator: WalkForwardValidator
    ):
        """Missing primary metric raises ValueError."""
        with pytest.raises(ValueError, match="not found in train_metrics"):
            validator.validate_performance(
                train_metrics={"other": 1.5},
                val_metrics={"sharpe": 1.4},
                test_metrics={"sharpe": 1.3},
            )

        with pytest.raises(ValueError, match="not found in val_metrics"):
            validator.validate_performance(
                train_metrics={"sharpe": 1.5},
                val_metrics={"other": 1.4},
                test_metrics={"sharpe": 1.3},
            )

        with pytest.raises(ValueError, match="not found in test_metrics"):
            validator.validate_performance(
                train_metrics={"sharpe": 1.5},
                val_metrics={"sharpe": 1.4},
                test_metrics={"other": 1.3},
            )

    def test_validate_performance_calculates_degradation_correctly(
        self, validator: WalkForwardValidator
    ):
        """Degradation is calculated correctly."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 2.0},
            val_metrics={"sharpe": 1.6},  # 20% drop
            test_metrics={"sharpe": 1.4},  # 12.5% drop
        )

        assert result.degradation_train_val == pytest.approx(0.20, rel=0.01)
        assert result.degradation_val_test == pytest.approx(0.125, rel=0.01)

    def test_validate_performance_handles_zero_baseline(
        self, validator: WalkForwardValidator
    ):
        """Validation handles zero baseline gracefully."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 0.0},
            val_metrics={"sharpe": 0.0},
            test_metrics={"sharpe": 0.0},
        )

        # Should pass when everything is zero
        assert result.is_valid is True

    def test_validate_performance_handles_improvement(
        self, validator: WalkForwardValidator
    ):
        """Validation handles performance improvement (negative degradation)."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 1.0},
            val_metrics={"sharpe": 1.2},  # Improvement!
            test_metrics={"sharpe": 1.3},  # More improvement!
        )

        # Improvement is always valid
        assert result.is_valid is True
        assert result.degradation_train_val < 0  # Negative = improvement


# ==============================================================================
# Parameter Stability Tests
# ==============================================================================


class TestCheckParameterStability:
    """Tests for parameter stability analysis."""

    def test_stability_passes_with_small_deviation(
        self, validator: WalkForwardValidator
    ):
        """Stability passes when perturbations cause small deviations."""
        result = validator.check_parameter_stability(
            base_metrics={"sharpe": 1.5},
            perturbed_metrics={
                "+10%": {"sharpe": 1.45},  # 3.3% deviation
                "-10%": {"sharpe": 1.48},  # 1.3% deviation
                "+20%": {"sharpe": 1.40},  # 6.7% deviation
                "-20%": {"sharpe": 1.42},  # 5.3% deviation
            },
        )

        assert result.is_stable is True
        assert result.reason is None
        assert result.max_deviation < 0.10

    def test_stability_fails_with_large_deviation(
        self, validator: WalkForwardValidator
    ):
        """Stability fails when perturbations cause large deviations."""
        result = validator.check_parameter_stability(
            base_metrics={"sharpe": 1.5},
            perturbed_metrics={
                "+10%": {"sharpe": 1.45},
                "-10%": {"sharpe": 1.48},
                "+20%": {"sharpe": 1.0},   # 33% deviation (FAIL)
                "-20%": {"sharpe": 1.1},   # 27% deviation (FAIL)
            },
        )

        assert result.is_stable is False
        assert "+20%" in result.reason
        assert "-20%" in result.reason
        assert "sensitive" in result.reason.lower()

    def test_stability_includes_baseline_in_results(
        self, validator: WalkForwardValidator
    ):
        """Stability results include baseline value."""
        result = validator.check_parameter_stability(
            base_metrics={"sharpe": 1.5},
            perturbed_metrics={
                "+10%": {"sharpe": 1.45},
            },
        )

        assert "baseline" in result.perturbation_results
        assert result.perturbation_results["baseline"] == 1.5

    def test_stability_custom_primary_metric(
        self, validator: WalkForwardValidator
    ):
        """Stability works with custom primary metric."""
        result = validator.check_parameter_stability(
            base_metrics={"sharpe": 1.5, "return": 0.15},
            perturbed_metrics={
                "+10%": {"sharpe": 0.5, "return": 0.14},  # Sharpe bad, return OK
            },
            primary_metric="return",
        )

        assert result.is_stable is True  # Using return, not sharpe

    def test_stability_missing_metric_raises_error(
        self, validator: WalkForwardValidator
    ):
        """Missing primary metric raises ValueError."""
        with pytest.raises(ValueError, match="not found in base_metrics"):
            validator.check_parameter_stability(
                base_metrics={"other": 1.5},
                perturbed_metrics={"+10%": {"sharpe": 1.45}},
            )

        with pytest.raises(ValueError, match="not found in perturbed_metrics"):
            validator.check_parameter_stability(
                base_metrics={"sharpe": 1.5},
                perturbed_metrics={"+10%": {"other": 1.45}},
            )

    def test_stability_max_deviation_calculated(
        self, validator: WalkForwardValidator
    ):
        """Maximum deviation is correctly identified."""
        result = validator.check_parameter_stability(
            base_metrics={"sharpe": 1.0},
            perturbed_metrics={
                "+10%": {"sharpe": 0.95},  # 5% deviation
                "+20%": {"sharpe": 0.85},  # 15% deviation (max)
                "-10%": {"sharpe": 0.90},  # 10% deviation
            },
        )

        assert result.max_deviation == pytest.approx(0.15, rel=0.01)


# ==============================================================================
# Combined Validation Tests
# ==============================================================================


class TestValidateWithStability:
    """Tests for combined validation and stability check."""

    def test_combined_validation_without_perturbations(
        self, validator: WalkForwardValidator
    ):
        """Combined validation works without perturbation data."""
        val_result, stab_result = validator.validate_with_stability(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.4},
            test_metrics={"sharpe": 1.3},
            perturbed_metrics=None,
        )

        assert val_result is not None
        assert val_result.is_valid is True
        assert stab_result is None

    def test_combined_validation_with_perturbations(
        self, validator: WalkForwardValidator
    ):
        """Combined validation works with perturbation data."""
        val_result, stab_result = validator.validate_with_stability(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.4},
            test_metrics={"sharpe": 1.3},
            perturbed_metrics={
                "+10%": {"sharpe": 1.35},
                "-10%": {"sharpe": 1.38},
            },
        )

        assert val_result is not None
        assert val_result.is_valid is True
        assert stab_result is not None
        assert stab_result.is_stable is True

    def test_combined_validation_both_fail(
        self, validator: WalkForwardValidator
    ):
        """Combined validation can fail both checks."""
        val_result, stab_result = validator.validate_with_stability(
            train_metrics={"sharpe": 1.5},
            val_metrics={"sharpe": 1.0},  # 33% degradation (FAIL)
            test_metrics={"sharpe": 0.8},
            perturbed_metrics={
                "+20%": {"sharpe": 0.5},  # 50% deviation (FAIL)
            },
        )

        assert val_result.is_valid is False
        assert stab_result.is_stable is False


# ==============================================================================
# Edge Case Tests
# ==============================================================================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_at_threshold_boundary(self):
        """Validation at threshold boundary (just under passes)."""
        validator = WalkForwardValidator(max_degradation=0.20)

        # Just under 20% threshold should pass
        result = validator.validate_performance(
            train_metrics={"sharpe": 1.0},
            val_metrics={"sharpe": 0.81},  # 19% drop - under threshold
            test_metrics={"sharpe": 0.66},  # ~18.5% drop - under threshold
        )

        # Just under threshold should pass
        assert result.is_valid is True
        assert result.degradation_train_val < 0.20
        assert result.degradation_val_test < 0.20

    def test_just_over_threshold(self):
        """Validation just over threshold fails."""
        validator = WalkForwardValidator(max_degradation=0.20)

        result = validator.validate_performance(
            train_metrics={"sharpe": 1.0},
            val_metrics={"sharpe": 0.79},  # 21% drop
            test_metrics={"sharpe": 0.7},
        )

        assert result.is_valid is False

    def test_negative_metrics(self, validator: WalkForwardValidator):
        """Validation handles negative metrics correctly."""
        result = validator.validate_performance(
            train_metrics={"sharpe": -0.5},
            val_metrics={"sharpe": -0.55},  # Worse (more negative)
            test_metrics={"sharpe": -0.6},
        )

        # Should detect degradation even with negative values
        assert result.degradation_train_val > 0

    def test_very_small_values(self, validator: WalkForwardValidator):
        """Validation handles very small values."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 0.001},
            val_metrics={"sharpe": 0.0009},
            test_metrics={"sharpe": 0.0008},
        )

        assert result.is_valid is True

    def test_large_values(self, validator: WalkForwardValidator):
        """Validation handles large values."""
        result = validator.validate_performance(
            train_metrics={"sharpe": 1000.0},
            val_metrics={"sharpe": 900.0},
            test_metrics={"sharpe": 850.0},
        )

        assert result.is_valid is True


# ==============================================================================
# Integration Tests
# ==============================================================================


class TestIntegration:
    """Integration tests for full workflow."""

    def test_full_workflow(self):
        """Test complete validation workflow."""
        # Create validator
        validator = WalkForwardValidator(
            train_pct=0.70,
            val_pct=0.15,
            test_pct=0.15,
            max_degradation=0.20,
        )

        # Create sample data
        dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(100)]
        df = pd.DataFrame({
            "date": dates,
            "price": [100 + i * 0.5 for i in range(100)],
        })

        # Split data
        train, val, test = validator.split_data(df, "date")

        assert len(train) == 70
        assert len(val) == 15
        assert len(test) == 15

        # Simulate metrics (would come from backtest)
        train_metrics = {"sharpe": 1.5, "return": 0.12}
        val_metrics = {"sharpe": 1.35, "return": 0.10}
        test_metrics = {"sharpe": 1.25, "return": 0.09}

        # Validate performance
        val_result = validator.validate_performance(
            train_metrics, val_metrics, test_metrics
        )

        assert val_result.is_valid is True

        # Check parameter stability
        stab_result = validator.check_parameter_stability(
            base_metrics=val_metrics,
            perturbed_metrics={
                "+10%": {"sharpe": 1.30, "return": 0.095},
                "-10%": {"sharpe": 1.32, "return": 0.098},
                "+20%": {"sharpe": 1.20, "return": 0.085},
                "-20%": {"sharpe": 1.28, "return": 0.092},
            },
        )

        assert stab_result.is_stable is True

    def test_rejection_workflow(self):
        """Test workflow that correctly rejects overfit model."""
        validator = WalkForwardValidator(max_degradation=0.20)

        # Simulate overfit scenario
        train_metrics = {"sharpe": 2.5}  # Suspiciously high
        val_metrics = {"sharpe": 1.5}    # 40% drop!
        test_metrics = {"sharpe": 0.8}   # Even worse

        result = validator.validate_performance(
            train_metrics, val_metrics, test_metrics
        )

        assert result.is_valid is False
        assert "overfitting" in result.reason.lower()
