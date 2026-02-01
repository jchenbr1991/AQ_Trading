# AQ Trading AI Agents - Volatility Logic
"""Centralized volatility classification and risk adjustment logic.

This module contains deterministic calculations that were previously
embedded in agent prompts. Moving this logic to code ensures:
- Testability
- Consistency across agents
- Deterministic behavior

Usage:
    from agents.tools.volatility import classify_vix_regime, calculate_risk_scaling

    regime = classify_vix_regime(25.5)  # Returns "elevated"
    scaling = calculate_risk_scaling(vix=25.5, drawdown_pct=5.0)
"""

from dataclasses import dataclass
from typing import Literal

VixRegime = Literal["low", "normal", "elevated", "high", "extreme"]


# VIX thresholds for regime classification
VIX_THRESHOLDS = {
    "low": 15.0,
    "normal": 20.0,
    "elevated": 30.0,
    "high": 40.0,
    # Above 40 is "extreme"
}

# Risk scaling by VIX regime
VIX_RISK_SCALING = {
    "low": 1.0,
    "normal": 0.8,
    "elevated": 0.5,
    "high": 0.25,
    "extreme": 0.1,
}

# Drawdown-based risk reduction
DRAWDOWN_THRESHOLDS = [
    (5.0, 0.9),   # 5% drawdown -> 90% of normal
    (10.0, 0.7),  # 10% drawdown -> 70% of normal
    (15.0, 0.5),  # 15% drawdown -> 50% of normal
    (20.0, 0.25), # 20% drawdown -> 25% of normal
]


def classify_vix_regime(vix_value: float | None) -> VixRegime | None:
    """Classify VIX value into a volatility regime.

    Args:
        vix_value: Current VIX value, or None if unavailable

    Returns:
        Regime classification: "low", "normal", "elevated", "high", or "extreme"
        Returns None if vix_value is None.

    Example:
        >>> classify_vix_regime(12.5)
        'low'
        >>> classify_vix_regime(25.0)
        'elevated'
    """
    if vix_value is None:
        return None

    if vix_value < VIX_THRESHOLDS["low"]:
        return "low"
    elif vix_value < VIX_THRESHOLDS["normal"]:
        return "normal"
    elif vix_value < VIX_THRESHOLDS["elevated"]:
        return "elevated"
    elif vix_value < VIX_THRESHOLDS["high"]:
        return "high"
    else:
        return "extreme"


def get_vix_risk_scaling(vix_value: float | None) -> float:
    """Get risk scaling factor based on VIX level.

    Args:
        vix_value: Current VIX value

    Returns:
        Risk scaling factor between 0.1 and 1.0.
        Returns 1.0 if vix_value is None (assume normal conditions).

    Example:
        >>> get_vix_risk_scaling(12.0)
        1.0
        >>> get_vix_risk_scaling(35.0)
        0.25
    """
    regime = classify_vix_regime(vix_value)
    if regime is None:
        return 1.0
    return VIX_RISK_SCALING.get(regime, 1.0)


def get_drawdown_scaling(drawdown_pct: float) -> float:
    """Get risk scaling factor based on portfolio drawdown.

    Args:
        drawdown_pct: Current drawdown as a positive percentage (e.g., 5.0 for 5%)

    Returns:
        Risk scaling factor between 0.25 and 1.0.

    Example:
        >>> get_drawdown_scaling(3.0)
        1.0
        >>> get_drawdown_scaling(12.0)
        0.7
    """
    if drawdown_pct <= 0:
        return 1.0

    # Find the appropriate scaling based on drawdown level
    # Each threshold means "at or above this drawdown, use this scaling"
    scaling = 1.0
    for threshold, threshold_scaling in DRAWDOWN_THRESHOLDS:
        if drawdown_pct >= threshold:
            scaling = threshold_scaling
        else:
            break

    return scaling


def calculate_risk_scaling(
    vix: float | None = None,
    drawdown_pct: float = 0.0,
) -> float:
    """Calculate combined risk scaling from VIX and drawdown.

    The final scaling is the minimum of VIX-based and drawdown-based scaling.

    Args:
        vix: Current VIX value
        drawdown_pct: Current drawdown percentage

    Returns:
        Combined risk scaling factor.

    Example:
        >>> calculate_risk_scaling(vix=25.0, drawdown_pct=8.0)
        0.5  # min(0.5 from VIX elevated, 0.7 from drawdown)
    """
    vix_scaling = get_vix_risk_scaling(vix)
    dd_scaling = get_drawdown_scaling(drawdown_pct)
    return min(vix_scaling, dd_scaling)


@dataclass
class RiskAssessment:
    """Result of a risk assessment calculation."""

    vix_regime: VixRegime | None
    vix_scaling: float
    drawdown_scaling: float
    combined_scaling: float
    risk_level: Literal["low", "medium", "high", "critical"]


def assess_risk(
    vix: float | None = None,
    drawdown_pct: float = 0.0,
) -> RiskAssessment:
    """Perform a comprehensive risk assessment.

    Args:
        vix: Current VIX value
        drawdown_pct: Current drawdown percentage

    Returns:
        RiskAssessment with all calculated values.
    """
    vix_regime = classify_vix_regime(vix)
    vix_scaling = get_vix_risk_scaling(vix)
    dd_scaling = get_drawdown_scaling(drawdown_pct)
    combined = min(vix_scaling, dd_scaling)

    # Determine overall risk level
    if combined >= 0.8:
        risk_level = "low"
    elif combined >= 0.5:
        risk_level = "medium"
    elif combined >= 0.25:
        risk_level = "high"
    else:
        risk_level = "critical"

    return RiskAssessment(
        vix_regime=vix_regime,
        vix_scaling=vix_scaling,
        drawdown_scaling=dd_scaling,
        combined_scaling=combined,
        risk_level=risk_level,
    )
