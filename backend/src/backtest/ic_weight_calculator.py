"""Information Coefficient (IC) based weight calculator for systematic factor weighting.

IC measures the correlation between factor values at time t and returns at time t+1.
Higher absolute IC means better predictive power.

Supports three weighting methods:
1. Simple IC: weight[f] = |IC[f]| / Σ |IC[all factors]|
2. IC_IR (Information Ratio): weight[f] = |IC_IR[f]| / Σ |IC_IR[all factors]|
   where IC_IR = mean(IC) / std(IC) - rewards consistency
3. EWMA IC: Exponentially weighted IC giving more weight to recent data

This provides a data-driven, systematic approach to factor weighting instead of
arbitrary manual configuration.
"""

from __future__ import annotations

from decimal import Decimal, getcontext

# Set high precision for financial calculations
getcontext().prec = 28


class ICWeightCalculator:
    """Calculate factor weights based on Information Coefficient (IC).

    IC = correlation(factor_values_t, returns_t+1)

    Higher IC means the factor better predicts future returns.
    Weights can be calculated using simple IC, IC_IR (Information Ratio),
    or EWMA (Exponentially Weighted Moving Average) IC.

    Attributes:
        lookback_window: Number of bars for rolling IC calculation.
        ewma_span: Span for EWMA calculation. None = disabled.
        ic_history_periods: Number of IC values to use for IC_IR calculation.
    """

    DEFAULT_LOOKBACK = 60  # 60 trading days ~ 3 months
    DEFAULT_IC_HISTORY_PERIODS = 12  # 12 rolling ICs for IR calculation

    def __init__(
        self,
        lookback_window: int = DEFAULT_LOOKBACK,
        ewma_span: int | None = None,
        ic_history_periods: int = DEFAULT_IC_HISTORY_PERIODS,
    ) -> None:
        """Initialize IC weight calculator.

        Args:
            lookback_window: Number of bars to use for rolling IC calculation.
                Default is 60 (approximately 3 months of daily bars). Must be >= 3.
            ewma_span: Span for exponential weighting. None = use simple average.
                Lower values = more weight on recent data. Must be >= 1 if set.
            ic_history_periods: Number of IC periods to use for IC_IR calculation.
                Default is 12 (e.g., 12 monthly ICs for annual IR). Must be >= 1.

        Raises:
            ValueError: If lookback_window < 3, ewma_span < 1, or ic_history_periods < 1.
        """
        if lookback_window < 3:
            raise ValueError(f"lookback_window must be >= 3, got {lookback_window}")
        if ewma_span is not None and ewma_span < 1:
            raise ValueError(f"ewma_span must be >= 1, got {ewma_span}")
        if ic_history_periods < 1:
            raise ValueError(f"ic_history_periods must be >= 1, got {ic_history_periods}")

        self._lookback_window = lookback_window
        self._ewma_span = ewma_span
        self._ic_history_periods = ic_history_periods

    @property
    def lookback_window(self) -> int:
        """Return the lookback window size."""
        return self._lookback_window

    @property
    def ewma_span(self) -> int | None:
        """Return the EWMA span (None if disabled)."""
        return self._ewma_span

    @property
    def ic_history_periods(self) -> int:
        """Return the number of IC periods for IR calculation."""
        return self._ic_history_periods

    def calculate_ic(
        self,
        factor_values: list[Decimal],
        future_returns: list[Decimal],
    ) -> Decimal:
        """Calculate Information Coefficient (Pearson correlation) using Decimal.

        IC = correlation(factor_values, future_returns)

        Uses Decimal arithmetic throughout for numerical precision.

        Args:
            factor_values: Factor scores at time t.
            future_returns: Returns at time t+1.

        Returns:
            Decimal correlation coefficient between -1 and 1.

        Raises:
            ValueError: If arrays have different lengths or fewer than 3 points.
        """
        n = len(factor_values)

        if n != len(future_returns):
            raise ValueError(
                f"Arrays must have same length: factor_values={n}, "
                f"future_returns={len(future_returns)}"
            )

        if n < 3:
            raise ValueError(f"Need at least 3 data points, got {n}")

        # Use Decimal throughout for precision
        n_decimal = Decimal(n)

        # Calculate means
        mean_x = sum(factor_values) / n_decimal
        mean_y = sum(future_returns) / n_decimal

        # Calculate variance and covariance
        var_x = sum((x - mean_x) ** 2 for x in factor_values)
        var_y = sum((y - mean_y) ** 2 for y in future_returns)
        cov_xy = sum(
            (x - mean_x) * (y - mean_y) for x, y in zip(factor_values, future_returns, strict=True)
        )

        # Handle zero variance (constant values)
        if var_x == Decimal("0") or var_y == Decimal("0"):
            return Decimal("0")

        # Pearson correlation using Decimal sqrt
        correlation = cov_xy / (var_x.sqrt() * var_y.sqrt())

        return correlation

    def calculate_ic_ir(
        self,
        ic_history: list[Decimal],
    ) -> Decimal:
        """Calculate Information Ratio from IC history.

        IC_IR = mean(IC) / std(IC)

        Higher IC_IR means more consistent predictive power.

        Args:
            ic_history: List of historical IC values.

        Returns:
            Decimal Information Ratio. Returns 0 if std is zero.

        Raises:
            ValueError: If fewer than 3 IC values provided.
        """
        n = len(ic_history)

        if n < 3:
            raise ValueError(f"Need at least 3 IC values, got {n}")

        n_decimal = Decimal(n)

        # Calculate mean IC
        mean_ic = sum(ic_history) / n_decimal

        # Calculate standard deviation of IC
        variance = sum((ic - mean_ic) ** 2 for ic in ic_history) / n_decimal
        std_ic = variance.sqrt()

        # Handle zero std (all ICs identical)
        if std_ic == Decimal("0"):
            return Decimal("0")

        # Information Ratio
        return mean_ic / std_ic

    def calculate_ewma_ic(
        self,
        factor_values: list[Decimal],
        future_returns: list[Decimal],
    ) -> Decimal:
        """Calculate IC using Exponentially Weighted Moving Average.

        Gives more weight to recent observations for better adaptation
        to changing market regimes.

        Args:
            factor_values: Factor scores at time t.
            future_returns: Returns at time t+1. Must have same length as factor_values.

        Returns:
            Decimal EWMA-weighted correlation.

        Raises:
            ValueError: If insufficient data, length mismatch, or ewma_span not set.
        """
        n = len(factor_values)
        n_returns = len(future_returns)

        if n != n_returns:
            raise ValueError(
                f"Arrays must have same length: factor_values={n}, future_returns={n_returns}"
            )

        if n < self._lookback_window:
            raise ValueError(f"Insufficient data: need {self._lookback_window} points, got {n}")

        span = self._ewma_span if self._ewma_span else self._lookback_window

        # Calculate EWMA weights: w_i = alpha * (1 - alpha)^i
        # More recent = higher weight
        alpha = Decimal("2") / (Decimal(span) + Decimal("1"))

        # Use lookback window
        window_factors = factor_values[-self._lookback_window :]
        window_returns = future_returns[-self._lookback_window :]

        # Calculate EWMA weights (newest first)
        weights = []
        for i in range(self._lookback_window):
            # i=0 is most recent
            w = alpha * (Decimal("1") - alpha) ** i
            weights.append(w)

        # Reverse to match data order (oldest first)
        weights = weights[::-1]
        total_weight = sum(weights)

        # Normalize weights
        weights = [w / total_weight for w in weights]

        # Weighted means
        mean_x = sum(w * x for w, x in zip(weights, window_factors, strict=True))
        mean_y = sum(w * y for w, y in zip(weights, window_returns, strict=True))

        # Weighted variance and covariance
        var_x = sum(w * (x - mean_x) ** 2 for w, x in zip(weights, window_factors, strict=True))
        var_y = sum(w * (y - mean_y) ** 2 for w, y in zip(weights, window_returns, strict=True))
        cov_xy = sum(
            w * (x - mean_x) * (y - mean_y)
            for w, x, y in zip(weights, window_factors, window_returns, strict=True)
        )

        # Handle zero variance
        if var_x == Decimal("0") or var_y == Decimal("0"):
            return Decimal("0")

        # Weighted correlation
        return cov_xy / (var_x.sqrt() * var_y.sqrt())

    def calculate_weights_from_ic(
        self,
        factor_ics: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        """Calculate normalized weights from IC values.

        weight[f] = |IC[f]| / Σ |IC[all factors]|

        Args:
            factor_ics: Dictionary mapping factor names to their IC values.

        Returns:
            Dictionary mapping factor names to normalized weights (sum = 1.0).

        Raises:
            ValueError: If factor_ics is empty.
        """
        if not factor_ics:
            raise ValueError("Need at least one factor to calculate weights")

        # Use absolute IC values
        abs_ics = {name: abs(ic) for name, ic in factor_ics.items()}
        total_abs_ic = sum(abs_ics.values())

        # Handle case where all ICs are zero
        if total_abs_ic == Decimal("0"):
            # Equal weights when no predictive power
            n = len(factor_ics)
            equal_weight = Decimal("1") / Decimal(n)
            return dict.fromkeys(factor_ics, equal_weight)

        # Normalize weights to sum to 1
        return {name: abs_ic / total_abs_ic for name, abs_ic in abs_ics.items()}

    def calculate_weights_from_ic_ir(
        self,
        factor_ic_irs: dict[str, Decimal],
    ) -> dict[str, Decimal]:
        """Calculate normalized weights from IC_IR (Information Ratio) values.

        weight[f] = |IC_IR[f]| / Σ |IC_IR[all factors]|

        Higher IC_IR = more consistent predictor = higher weight.

        Args:
            factor_ic_irs: Dictionary mapping factor names to their IC_IR values.

        Returns:
            Dictionary mapping factor names to normalized weights (sum = 1.0).

        Raises:
            ValueError: If factor_ic_irs is empty.
        """
        # Same logic as calculate_weights_from_ic
        return self.calculate_weights_from_ic(factor_ic_irs)

    def calculate_rolling_ic(
        self,
        factor_values: list[Decimal],
        future_returns: list[Decimal],
    ) -> Decimal:
        """Calculate IC using rolling window of recent data.

        Uses the last `lookback_window` data points for calculation.

        Args:
            factor_values: Full history of factor values.
            future_returns: Full history of returns.

        Returns:
            Decimal IC calculated on the lookback window.

        Raises:
            ValueError: If insufficient data for lookback window.
        """
        n = len(factor_values)

        if n < self._lookback_window:
            raise ValueError(f"Insufficient data: need {self._lookback_window} points, got {n}")

        # Use last lookback_window points
        window_factors = factor_values[-self._lookback_window :]
        window_returns = future_returns[-self._lookback_window :]

        return self.calculate_ic(window_factors, window_returns)

    def calculate_weights_from_history(
        self,
        factor_history: dict[str, list[Decimal]],
        future_returns: list[Decimal],
    ) -> dict[str, Decimal]:
        """Calculate weights from historical factor and return data.

        Computes rolling IC for each factor, then converts to weights.
        Aligns factor and returns data to use the shorter length.

        Args:
            factor_history: Dictionary mapping factor names to their value history.
            future_returns: History of returns.

        Returns:
            Dictionary mapping factor names to normalized weights.
        """
        factor_ics = {}

        for factor_name, factor_values in factor_history.items():
            # Align lengths - use the minimum of factor_values and future_returns
            aligned_len = min(len(factor_values), len(future_returns))
            aligned_factors = factor_values[-aligned_len:]
            aligned_returns = future_returns[-aligned_len:]

            # Handle case where we have exactly lookback_window or more
            if aligned_len >= self._lookback_window:
                ic = self.calculate_rolling_ic(aligned_factors, aligned_returns)
            elif aligned_len >= 3:
                # Use all available aligned data if less than window
                ic = self.calculate_ic(aligned_factors, aligned_returns)
            else:
                # Not enough data
                ic = Decimal("0")

            factor_ics[factor_name] = ic

        return self.calculate_weights_from_ic(factor_ics)

    def calculate_weights_full_pipeline(
        self,
        factor_history: dict[str, list[Decimal]],
        future_returns: list[Decimal],
    ) -> dict[str, Decimal]:
        """Full pipeline: historical data -> EWMA IC series -> IC_IR -> weights.

        This is the recommended method for production use. It:
        1. Generates multiple rolling IC values using EWMA
        2. Calculates IC_IR (Information Ratio) from the IC series
        3. Converts IC_IR values to normalized weights

        Args:
            factor_history: Dictionary mapping factor names to their value history.
            future_returns: History of returns.

        Returns:
            Dictionary mapping factor names to normalized weights.
        """
        n = len(future_returns)
        required_data = self._lookback_window + self._ic_history_periods - 1

        factor_ic_irs = {}

        for factor_name, factor_values in factor_history.items():
            if len(factor_values) < required_data:
                # Not enough data for full pipeline, use single IC
                if len(factor_values) >= 3:
                    ic = self.calculate_ic(
                        factor_values[-self._lookback_window :]
                        if len(factor_values) >= self._lookback_window
                        else factor_values,
                        future_returns[-len(factor_values) :],
                    )
                    # Use IC as IR when we don't have history
                    factor_ic_irs[factor_name] = ic
                else:
                    factor_ic_irs[factor_name] = Decimal("0")
                continue

            # Generate IC history using sliding windows
            ic_history = []
            for i in range(self._ic_history_periods):
                # Calculate IC for each period
                end_idx = n - i
                start_idx = end_idx - self._lookback_window

                if start_idx < 0:
                    break

                window_factors = factor_values[start_idx:end_idx]
                window_returns = future_returns[start_idx:end_idx]

                if self._ewma_span:
                    # Use EWMA IC
                    ic = self._calculate_ewma_ic_from_window(window_factors, window_returns)
                else:
                    # Use simple IC
                    ic = self.calculate_ic(window_factors, window_returns)

                ic_history.append(ic)

            # Calculate IC_IR from history
            if len(ic_history) >= 3:
                ic_ir = self.calculate_ic_ir(ic_history)
            else:
                # Fall back to average IC
                ic_ir = sum(ic_history) / Decimal(len(ic_history)) if ic_history else Decimal("0")

            factor_ic_irs[factor_name] = ic_ir

        return self.calculate_weights_from_ic_ir(factor_ic_irs)

    def _calculate_ewma_ic_from_window(
        self,
        window_factors: list[Decimal],
        window_returns: list[Decimal],
    ) -> Decimal:
        """Calculate EWMA IC from a pre-windowed data slice.

        Internal helper for full pipeline calculation.
        """
        n = len(window_factors)
        span = self._ewma_span if self._ewma_span else n

        alpha = Decimal("2") / (Decimal(span) + Decimal("1"))

        # EWMA weights (newest last in window)
        weights = []
        for i in range(n):
            # i=0 is oldest, i=n-1 is newest
            age = n - 1 - i
            w = alpha * (Decimal("1") - alpha) ** age
            weights.append(w)

        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        # Weighted means
        mean_x = sum(w * x for w, x in zip(weights, window_factors, strict=True))
        mean_y = sum(w * y for w, y in zip(weights, window_returns, strict=True))

        # Weighted variance and covariance
        var_x = sum(w * (x - mean_x) ** 2 for w, x in zip(weights, window_factors, strict=True))
        var_y = sum(w * (y - mean_y) ** 2 for w, y in zip(weights, window_returns, strict=True))
        cov_xy = sum(
            w * (x - mean_x) * (y - mean_y)
            for w, x, y in zip(weights, window_factors, window_returns, strict=True)
        )

        if var_x == Decimal("0") or var_y == Decimal("0"):
            return Decimal("0")

        return cov_xy / (var_x.sqrt() * var_y.sqrt())
