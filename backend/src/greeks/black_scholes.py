"""Black-Scholes Greeks calculator.

Implements the standard Black-Scholes model for European option Greeks.
Used as fallback when Futu API is unavailable.

Formulas:
    d1 = (ln(S/K) + (r + σ²/2)T) / (σ√T)
    d2 = d1 - σ√T

    Call Delta = N(d1)
    Put Delta = N(d1) - 1
    Gamma = φ(d1) / (S σ √T)
    Vega = S φ(d1) √T / 100  (per 1% IV change)
    Call Theta = -S φ(d1) σ / (2√T) - r K e^(-rT) N(d2)
    Put Theta = -S φ(d1) σ / (2√T) + r K e^(-rT) N(-d2)
"""

import math
from dataclasses import dataclass
from decimal import Decimal

# Constants
DAYS_PER_YEAR = 365


@dataclass
class BSGreeksResult:
    """Result of Black-Scholes Greeks calculation.

    All values are per-share (before multiplier scaling).

    Attributes:
        delta: Option delta (-1 to 1)
        gamma: Option gamma
        vega: Option vega per 1% IV change
        theta: Option theta per day (negative = decay)
    """

    delta: Decimal
    gamma: Decimal
    vega: Decimal
    theta: Decimal


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def calculate_bs_greeks(
    spot: Decimal,
    strike: Decimal,
    time_to_expiry_years: Decimal,
    risk_free_rate: Decimal,
    volatility: Decimal,
    is_call: bool,
) -> BSGreeksResult:
    """Calculate Black-Scholes Greeks.

    Args:
        spot: Current underlying price
        strike: Option strike price
        time_to_expiry_years: Time to expiration in years
        risk_free_rate: Risk-free interest rate (decimal, e.g., 0.05 = 5%)
        volatility: Implied volatility (decimal, e.g., 0.20 = 20%)
        is_call: True for call, False for put

    Returns:
        BSGreeksResult with delta, gamma, vega, theta
    """
    # Convert to float for math operations
    S = float(spot)
    K = float(strike)
    T = float(time_to_expiry_years)
    r = float(risk_free_rate)
    sigma = float(volatility)

    # Handle edge cases
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return BSGreeksResult(
            delta=Decimal("0"),
            gamma=Decimal("0"),
            vega=Decimal("0"),
            theta=Decimal("0"),
        )

    sqrt_T = math.sqrt(T)
    sigma_sqrt_T = sigma * sqrt_T

    # Calculate d1 and d2
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sigma_sqrt_T
    d2 = d1 - sigma_sqrt_T

    # Calculate Greeks
    N_d1 = _norm_cdf(d1)
    N_d2 = _norm_cdf(d2)
    phi_d1 = _norm_pdf(d1)

    # Delta
    if is_call:
        delta = N_d1
    else:
        delta = N_d1 - 1

    # Gamma (same for call and put)
    gamma = phi_d1 / (S * sigma_sqrt_T)

    # Vega (per 1% IV change, so divide by 100)
    vega = S * phi_d1 * sqrt_T / 100

    # Theta (per day)
    discount = math.exp(-r * T)
    if is_call:
        theta = (-S * phi_d1 * sigma / (2 * sqrt_T) - r * K * discount * N_d2) / DAYS_PER_YEAR
    else:
        theta = (
            -S * phi_d1 * sigma / (2 * sqrt_T) + r * K * discount * _norm_cdf(-d2)
        ) / DAYS_PER_YEAR

    return BSGreeksResult(
        delta=Decimal(str(round(delta, 6))),
        gamma=Decimal(str(round(gamma, 8))),
        vega=Decimal(str(round(vega, 6))),
        theta=Decimal(str(round(theta, 6))),
    )
