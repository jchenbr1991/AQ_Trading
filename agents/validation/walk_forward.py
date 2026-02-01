# AQ Trading AI Agents - Walk Forward Validator
# T029: Implement WalkForwardValidator for overfitting protection
"""Walk-forward validation for agent suggestions.

This module implements walk-forward validation to prevent overfitting
in agent-generated trading strategies and parameters.

Key features:
- Time-based train/validation/test splits (70/15/15 default)
- Performance degradation detection (<20% drop threshold)
- Parameter stability testing (perturbation analysis)

Usage:
    validator = WalkForwardValidator()
    train, val, test = validator.split_data(data, date_column="date")

    result = validator.validate_performance(
        train_metrics={"sharpe": 1.5},
        val_metrics={"sharpe": 1.3},
        test_metrics={"sharpe": 1.2}
    )

    if not result.is_valid:
        print(f"Validation failed: {result.reason}")
"""

from dataclasses import dataclass, field
from typing import Any, Sequence, TypeVar

import pandas as pd

T = TypeVar("T")


@dataclass(frozen=True)
class ValidationResult:
    """Result of walk-forward performance validation.

    Captures performance metrics across train/validation/test splits
    and determines if the model passes overfitting checks.

    Attributes:
        is_valid: True if validation passed all checks
        train_performance: Primary metric on training data
        val_performance: Primary metric on validation data
        test_performance: Primary metric on test data
        degradation_train_val: Performance drop from train to validation
        degradation_val_test: Performance drop from validation to test
        reason: Explanation if validation failed, None if passed

    Example:
        >>> result = ValidationResult(
        ...     is_valid=True,
        ...     train_performance=1.5,
        ...     val_performance=1.4,
        ...     test_performance=1.3,
        ...     degradation_train_val=0.067,
        ...     degradation_val_test=0.071,
        ...     reason=None
        ... )
    """

    is_valid: bool
    train_performance: float
    val_performance: float
    test_performance: float
    degradation_train_val: float
    degradation_val_test: float
    reason: str | None


@dataclass(frozen=True)
class StabilityResult:
    """Result of parameter stability analysis.

    Captures how sensitive the model is to parameter perturbations.
    A stable model should maintain similar performance when parameters
    are slightly varied.

    Attributes:
        is_stable: True if model is stable under perturbations
        perturbation_results: Map of perturbation label to performance
        max_deviation: Maximum observed deviation from baseline
        reason: Explanation if unstable, None if stable

    Example:
        >>> result = StabilityResult(
        ...     is_stable=True,
        ...     perturbation_results={
        ...         "baseline": 1.5,
        ...         "+10%": 1.45,
        ...         "-10%": 1.48,
        ...         "+20%": 1.38,
        ...         "-20%": 1.42
        ...     },
        ...     max_deviation=0.08,
        ...     reason=None
        ... )
    """

    is_stable: bool
    perturbation_results: dict[str, float] = field(default_factory=dict)
    max_deviation: float = 0.0
    reason: str | None = None


class WalkForwardValidator:
    """Walk-forward validator for overfitting protection.

    Implements time-based validation splits and performance checks
    to ensure agent-generated strategies generalize well to unseen data.

    The validator uses a strict temporal split to prevent look-ahead bias:
    - Training set: First 70% of data (by date)
    - Validation set: Next 15% of data
    - Test set: Final 15% of data

    Performance validation checks:
    - Train to validation degradation must be < max_degradation
    - Validation to test degradation must be < max_degradation

    Attributes:
        train_pct: Fraction of data for training (default 0.70)
        val_pct: Fraction of data for validation (default 0.15)
        test_pct: Fraction of data for testing (default 0.15)
        max_degradation: Maximum allowed performance drop (default 0.20)

    Example:
        >>> validator = WalkForwardValidator()
        >>> train, val, test = validator.split_data(df, "date")
        >>> result = validator.validate_performance(
        ...     {"sharpe": 1.5},
        ...     {"sharpe": 1.3},
        ...     {"sharpe": 1.2}
        ... )
    """

    DEFAULT_TRAIN_PCT = 0.70
    DEFAULT_VAL_PCT = 0.15
    DEFAULT_TEST_PCT = 0.15
    DEFAULT_MAX_DEGRADATION = 0.20
    DEFAULT_STABILITY_THRESHOLD = 0.20  # Max deviation for stability

    def __init__(
        self,
        train_pct: float = DEFAULT_TRAIN_PCT,
        val_pct: float = DEFAULT_VAL_PCT,
        test_pct: float = DEFAULT_TEST_PCT,
        max_degradation: float = DEFAULT_MAX_DEGRADATION,
        stability_threshold: float = DEFAULT_STABILITY_THRESHOLD,
    ) -> None:
        """Initialize the walk-forward validator.

        Args:
            train_pct: Fraction of data for training (0.0-1.0)
            val_pct: Fraction of data for validation (0.0-1.0)
            test_pct: Fraction of data for testing (0.0-1.0)
            max_degradation: Maximum allowed performance degradation (0.0-1.0)
            stability_threshold: Maximum deviation for parameter stability

        Raises:
            ValueError: If percentages don't sum to 1.0 or are invalid
        """
        # Validate percentages
        if not (0.0 < train_pct < 1.0):
            raise ValueError(f"train_pct must be between 0 and 1, got {train_pct}")
        if not (0.0 < val_pct < 1.0):
            raise ValueError(f"val_pct must be between 0 and 1, got {val_pct}")
        if not (0.0 < test_pct < 1.0):
            raise ValueError(f"test_pct must be between 0 and 1, got {test_pct}")

        total = train_pct + val_pct + test_pct
        if not (0.99 <= total <= 1.01):  # Allow small floating point error
            raise ValueError(
                f"Percentages must sum to 1.0, got {total:.4f} "
                f"(train={train_pct}, val={val_pct}, test={test_pct})"
            )

        if not (0.0 < max_degradation <= 1.0):
            raise ValueError(
                f"max_degradation must be between 0 and 1, got {max_degradation}"
            )

        if not (0.0 < stability_threshold <= 1.0):
            raise ValueError(
                f"stability_threshold must be between 0 and 1, got {stability_threshold}"
            )

        self._train_pct = train_pct
        self._val_pct = val_pct
        self._test_pct = test_pct
        self._max_degradation = max_degradation
        self._stability_threshold = stability_threshold

    @property
    def train_pct(self) -> float:
        """Fraction of data allocated to training."""
        return self._train_pct

    @property
    def val_pct(self) -> float:
        """Fraction of data allocated to validation."""
        return self._val_pct

    @property
    def test_pct(self) -> float:
        """Fraction of data allocated to testing."""
        return self._test_pct

    @property
    def max_degradation(self) -> float:
        """Maximum allowed performance degradation."""
        return self._max_degradation

    @property
    def stability_threshold(self) -> float:
        """Maximum deviation for parameter stability."""
        return self._stability_threshold

    def split_data(
        self,
        data: pd.DataFrame,
        date_column: str = "date",
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Split data into train/validation/test sets by date.

        Performs a temporal split to prevent look-ahead bias.
        Data is sorted by date and split into consecutive chunks.

        Args:
            data: DataFrame containing the data to split
            date_column: Name of the column containing dates

        Returns:
            Tuple of (train_df, val_df, test_df)

        Raises:
            ValueError: If date_column is not in data
            ValueError: If data is empty or too small to split

        Example:
            >>> df = pd.DataFrame({
            ...     "date": pd.date_range("2024-01-01", periods=100),
            ...     "value": range(100)
            ... })
            >>> validator = WalkForwardValidator()
            >>> train, val, test = validator.split_data(df)
            >>> len(train), len(val), len(test)
            (70, 15, 15)
        """
        if date_column not in data.columns:
            raise ValueError(
                f"Date column '{date_column}' not found in data. "
                f"Available columns: {list(data.columns)}"
            )

        if len(data) == 0:
            raise ValueError("Cannot split empty DataFrame")

        # Minimum rows needed for meaningful splits
        min_rows = 10  # At least 10 rows to split
        if len(data) < min_rows:
            raise ValueError(
                f"Data too small to split: {len(data)} rows. "
                f"Need at least {min_rows} rows."
            )

        # Sort by date to ensure temporal order
        sorted_data = data.sort_values(by=date_column).reset_index(drop=True)

        n = len(sorted_data)
        train_end = int(n * self._train_pct)
        val_end = int(n * (self._train_pct + self._val_pct))

        # Ensure each split has at least one row
        train_end = max(1, train_end)
        val_end = max(train_end + 1, val_end)

        train_df = sorted_data.iloc[:train_end].copy()
        val_df = sorted_data.iloc[train_end:val_end].copy()
        test_df = sorted_data.iloc[val_end:].copy()

        return train_df, val_df, test_df

    def split_sequence(
        self,
        data: Sequence[T],
    ) -> tuple[Sequence[T], Sequence[T], Sequence[T]]:
        """Split a sequence into train/validation/test sets.

        For sequences that are already sorted (e.g., time series data).

        Args:
            data: Sequence to split (list, tuple, etc.)

        Returns:
            Tuple of (train, val, test) sequences

        Raises:
            ValueError: If data is empty or too small

        Example:
            >>> validator = WalkForwardValidator()
            >>> data = list(range(100))
            >>> train, val, test = validator.split_sequence(data)
            >>> len(train), len(val), len(test)
            (70, 15, 15)
        """
        if len(data) == 0:
            raise ValueError("Cannot split empty sequence")

        min_length = 10
        if len(data) < min_length:
            raise ValueError(
                f"Sequence too small to split: {len(data)} items. "
                f"Need at least {min_length} items."
            )

        n = len(data)
        train_end = int(n * self._train_pct)
        val_end = int(n * (self._train_pct + self._val_pct))

        # Ensure each split has at least one item
        train_end = max(1, train_end)
        val_end = max(train_end + 1, val_end)

        # Use slice to preserve sequence type for lists/tuples
        train = data[:train_end]
        val = data[train_end:val_end]
        test = data[val_end:]

        return train, val, test

    def _calculate_degradation(
        self,
        baseline: float,
        comparison: float,
    ) -> float:
        """Calculate performance degradation between two metrics.

        Degradation is relative to baseline:
        - Positive values indicate performance drop
        - Negative values indicate performance improvement

        Args:
            baseline: The baseline performance (e.g., training metric)
            comparison: The comparison performance (e.g., validation metric)

        Returns:
            Fractional degradation (0.0-1.0 for drops up to 100%)
        """
        if baseline == 0:
            # Avoid division by zero
            return 0.0 if comparison == 0 else 1.0

        # Degradation = (baseline - comparison) / |baseline|
        # Using abs(baseline) to handle negative metrics correctly
        degradation = (baseline - comparison) / abs(baseline)
        return degradation

    def validate_performance(
        self,
        train_metrics: dict[str, float],
        val_metrics: dict[str, float],
        test_metrics: dict[str, float],
        primary_metric: str = "sharpe",
    ) -> ValidationResult:
        """Validate performance across train/validation/test splits.

        Checks that performance doesn't degrade excessively between splits,
        which would indicate overfitting.

        Args:
            train_metrics: Performance metrics on training data
            val_metrics: Performance metrics on validation data
            test_metrics: Performance metrics on test data
            primary_metric: Key to use for degradation calculation

        Returns:
            ValidationResult with validation outcome and details

        Raises:
            ValueError: If primary_metric not found in any metrics dict

        Example:
            >>> validator = WalkForwardValidator(max_degradation=0.20)
            >>> result = validator.validate_performance(
            ...     train_metrics={"sharpe": 1.5, "return": 0.15},
            ...     val_metrics={"sharpe": 1.3, "return": 0.12},
            ...     test_metrics={"sharpe": 1.2, "return": 0.11},
            ... )
            >>> result.is_valid
            True
        """
        # Validate that primary metric exists in all dicts
        if primary_metric not in train_metrics:
            raise ValueError(
                f"Primary metric '{primary_metric}' not found in train_metrics. "
                f"Available: {list(train_metrics.keys())}"
            )
        if primary_metric not in val_metrics:
            raise ValueError(
                f"Primary metric '{primary_metric}' not found in val_metrics. "
                f"Available: {list(val_metrics.keys())}"
            )
        if primary_metric not in test_metrics:
            raise ValueError(
                f"Primary metric '{primary_metric}' not found in test_metrics. "
                f"Available: {list(test_metrics.keys())}"
            )

        train_perf = train_metrics[primary_metric]
        val_perf = val_metrics[primary_metric]
        test_perf = test_metrics[primary_metric]

        # Calculate degradation
        degradation_train_val = self._calculate_degradation(train_perf, val_perf)
        degradation_val_test = self._calculate_degradation(val_perf, test_perf)

        # Check for excessive degradation
        is_valid = True
        reason: str | None = None

        if degradation_train_val > self._max_degradation:
            is_valid = False
            reason = (
                f"Train-to-validation degradation ({degradation_train_val:.1%}) "
                f"exceeds threshold ({self._max_degradation:.1%}). "
                f"Train {primary_metric}={train_perf:.4f}, "
                f"Val {primary_metric}={val_perf:.4f}. "
                f"Model may be overfitting to training data."
            )
        elif degradation_val_test > self._max_degradation:
            is_valid = False
            reason = (
                f"Validation-to-test degradation ({degradation_val_test:.1%}) "
                f"exceeds threshold ({self._max_degradation:.1%}). "
                f"Val {primary_metric}={val_perf:.4f}, "
                f"Test {primary_metric}={test_perf:.4f}. "
                f"Model may be overfitting to validation data."
            )

        return ValidationResult(
            is_valid=is_valid,
            train_performance=train_perf,
            val_performance=val_perf,
            test_performance=test_perf,
            degradation_train_val=degradation_train_val,
            degradation_val_test=degradation_val_test,
            reason=reason,
        )

    def check_parameter_stability(
        self,
        base_metrics: dict[str, float],
        perturbed_metrics: dict[str, dict[str, float]],
        primary_metric: str = "sharpe",
    ) -> StabilityResult:
        """Check if model is stable under parameter perturbations.

        Tests if slight variations in parameters (e.g., +/-10%, +/-20%)
        cause significant performance changes.

        Args:
            base_metrics: Baseline performance with original parameters
            perturbed_metrics: Map of perturbation label to metrics dict
                               e.g., {"+10%": {"sharpe": 1.4}, "-10%": {"sharpe": 1.45}}
            primary_metric: Key to use for deviation calculation

        Returns:
            StabilityResult with stability analysis

        Raises:
            ValueError: If primary_metric not found in metrics

        Example:
            >>> validator = WalkForwardValidator()
            >>> result = validator.check_parameter_stability(
            ...     base_metrics={"sharpe": 1.5},
            ...     perturbed_metrics={
            ...         "+10%": {"sharpe": 1.45},
            ...         "-10%": {"sharpe": 1.48},
            ...         "+20%": {"sharpe": 1.38},
            ...         "-20%": {"sharpe": 1.42}
            ...     }
            ... )
            >>> result.is_stable
            True
        """
        if primary_metric not in base_metrics:
            raise ValueError(
                f"Primary metric '{primary_metric}' not found in base_metrics. "
                f"Available: {list(base_metrics.keys())}"
            )

        base_value = base_metrics[primary_metric]
        perturbation_results: dict[str, float] = {"baseline": base_value}
        max_deviation = 0.0
        unstable_perturbations: list[str] = []

        for label, metrics in perturbed_metrics.items():
            if primary_metric not in metrics:
                raise ValueError(
                    f"Primary metric '{primary_metric}' not found in "
                    f"perturbed_metrics['{label}']. "
                    f"Available: {list(metrics.keys())}"
                )

            perturbed_value = metrics[primary_metric]
            perturbation_results[label] = perturbed_value

            # Calculate deviation from baseline
            deviation = abs(self._calculate_degradation(base_value, perturbed_value))
            max_deviation = max(max_deviation, deviation)

            if deviation > self._stability_threshold:
                unstable_perturbations.append(
                    f"{label} (deviation={deviation:.1%})"
                )

        is_stable = len(unstable_perturbations) == 0
        reason: str | None = None

        if not is_stable:
            reason = (
                f"Parameter perturbations caused excessive deviation "
                f"(threshold={self._stability_threshold:.1%}): "
                f"{', '.join(unstable_perturbations)}. "
                f"Max deviation={max_deviation:.1%}. "
                f"Model may be sensitive to parameter choices."
            )

        return StabilityResult(
            is_stable=is_stable,
            perturbation_results=perturbation_results,
            max_deviation=max_deviation,
            reason=reason,
        )

    def validate_with_stability(
        self,
        train_metrics: dict[str, float],
        val_metrics: dict[str, float],
        test_metrics: dict[str, float],
        perturbed_metrics: dict[str, dict[str, float]] | None = None,
        primary_metric: str = "sharpe",
    ) -> tuple[ValidationResult, StabilityResult | None]:
        """Combined performance validation and stability check.

        Convenience method that runs both validation and stability checks.

        Args:
            train_metrics: Training performance metrics
            val_metrics: Validation performance metrics
            test_metrics: Test performance metrics
            perturbed_metrics: Optional perturbation results for stability
            primary_metric: Metric to use for checks

        Returns:
            Tuple of (ValidationResult, StabilityResult or None)
        """
        validation_result = self.validate_performance(
            train_metrics=train_metrics,
            val_metrics=val_metrics,
            test_metrics=test_metrics,
            primary_metric=primary_metric,
        )

        stability_result: StabilityResult | None = None
        if perturbed_metrics is not None:
            # Use val_metrics as base for stability (validation is target set)
            stability_result = self.check_parameter_stability(
                base_metrics=val_metrics,
                perturbed_metrics=perturbed_metrics,
                primary_metric=primary_metric,
            )

        return validation_result, stability_result

    def __repr__(self) -> str:
        return (
            f"WalkForwardValidator("
            f"train={self._train_pct:.0%}, "
            f"val={self._val_pct:.0%}, "
            f"test={self._test_pct:.0%}, "
            f"max_degradation={self._max_degradation:.0%})"
        )
