"""Math utilities for benchmark metrics computation."""

from decimal import Decimal


def calculate_returns(equity_values: list[Decimal]) -> list[float]:
    """Convert equity curve values to returns.

    Computes: r_t = (V_t - V_{t-1}) / V_{t-1}

    Args:
        equity_values: List of equity values over time.

    Returns:
        List of returns. Empty if input has 0 or 1 values.
        Returns 0.0 for any period where the previous value is zero.
    """
    if len(equity_values) < 2:
        return []

    returns: list[float] = []
    for i in range(1, len(equity_values)):
        prev_value = equity_values[i - 1]
        curr_value = equity_values[i]

        if prev_value == 0:
            returns.append(0.0)
        else:
            r = float(curr_value - prev_value) / float(prev_value)
            returns.append(r)

    return returns


def decimal_mean(data: list[Decimal]) -> float:
    """Compute mean of Decimal values, returned as float.

    Args:
        data: List of Decimal values.

    Returns:
        Mean as float. Returns 0.0 if list is empty.
    """
    if not data:
        return 0.0

    total = sum(data)
    return float(total) / len(data)


def decimal_variance(data: list[Decimal]) -> float:
    """Compute sample variance with n-1 denominator.

    Args:
        data: List of Decimal values.

    Returns:
        Sample variance as float. Returns 0.0 if len <= 1.
    """
    if len(data) < 2:
        return 0.0

    mean = decimal_mean(data)
    squared_diffs = [(float(x) - mean) ** 2 for x in data]
    return sum(squared_diffs) / (len(data) - 1)


def decimal_covariance(x: list[Decimal], y: list[Decimal]) -> float:
    """Compute sample covariance of two lists.

    Args:
        x: First list of Decimal values.
        y: Second list of Decimal values.

    Returns:
        Sample covariance as float. Returns 0.0 if len < 2.

    Raises:
        ValueError: If x and y have different lengths.
    """
    if len(x) != len(y):
        raise ValueError("x and y must have same length")

    if len(x) < 2:
        return 0.0

    mean_x = decimal_mean(x)
    mean_y = decimal_mean(y)

    cov_sum = sum((float(xi) - mean_x) * (float(yi) - mean_y) for xi, yi in zip(x, y, strict=False))
    return cov_sum / (len(x) - 1)


def decimal_ols(x: list[Decimal], y: list[Decimal]) -> tuple[float, float, list[float]]:
    """Perform OLS regression: y = alpha + beta * x + residuals.

    Args:
        x: Independent variable values.
        y: Dependent variable values.

    Returns:
        Tuple of (alpha, beta, residuals).
        - If variance(x) = 0: beta=0, alpha=mean(y)
        - If empty or single point: returns (0.0, 0.0, [])
    """
    if len(x) < 2 or len(y) < 2:
        return (0.0, 0.0, [])

    var_x = decimal_variance(x)

    if var_x == 0:
        # No variance in x - can't compute slope
        mean_y = decimal_mean(y)
        residuals = [float(yi) - mean_y for yi in y]
        return (mean_y, 0.0, residuals)

    # Compute beta = cov(x, y) / var(x)
    cov_xy = decimal_covariance(x, y)
    beta = cov_xy / var_x

    # Compute alpha = mean(y) - beta * mean(x)
    mean_x = decimal_mean(x)
    mean_y = decimal_mean(y)
    alpha = mean_y - beta * mean_x

    # Compute residuals: y - (alpha + beta * x)
    residuals = [float(yi) - (alpha + beta * float(xi)) for xi, yi in zip(x, y, strict=False)]

    return (alpha, beta, residuals)
