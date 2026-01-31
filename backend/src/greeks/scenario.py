"""Scenario Shock calculation for Greeks monitoring.

V2 Feature: Scenario Shock API (Section 3 of V2 Design)

Provides scenario analysis for underlying price shocks:
- ±1%, ±2% standard shocks
- Custom shock percentages
- PnL impact from delta (first-order) and gamma (second-order)
- Delta change projection
- Limit breach detection

Key formulas (V1 canonical - no double-multiplication by S):
- pnl_from_delta = dollar_delta × shock × sign
- pnl_from_gamma = gamma_pnl_1pct × scale (scale = shock_pct², no sign)
- pnl_impact = pnl_from_delta + pnl_from_gamma
- delta_change = gamma_dollar × shock × sign
- new_dollar_delta = dollar_delta + delta_change
"""

from decimal import Decimal
from typing import Literal

from src.greeks.v2_models import CurrentGreeks, ScenarioResult


def calculate_scenario(
    current: CurrentGreeks,
    shock_pct: Decimal,
    direction: Literal["up", "down"],
    limits: dict[str, Decimal],
) -> ScenarioResult:
    """Calculate scenario shock result.

    Args:
        current: Current Greeks snapshot
        shock_pct: Shock percentage (1 = 1%, 2 = 2%)
        direction: Shock direction ("up" or "down")
        limits: Hard limits for breach detection

    Returns:
        ScenarioResult with PnL impact and projected delta
    """
    sign = Decimal("1") if direction == "up" else Decimal("-1")
    shock = shock_pct / Decimal("100")  # 1% → 0.01

    # ========== V1 Canonical Formulas ==========
    # WARNING: dollar_delta already contains S, do NOT multiply by S again!

    # First-order: PnL from delta = dollar_delta × shock × sign
    pnl_from_delta = current.dollar_delta * shock * sign

    # Second-order: PnL from gamma = gamma_pnl_1pct × scale
    # Scale = shock_pct² (2% → 4x)
    # NOTE: No sign multiplication - gamma PnL is always positive (convexity)
    scale = shock_pct**2
    pnl_from_gamma = current.gamma_pnl_1pct * scale

    # Total PnL impact
    pnl_impact = pnl_from_delta + pnl_from_gamma

    # Delta change = gamma_dollar × shock × sign
    delta_change = current.gamma_dollar * shock * sign

    # New dollar delta = current + change
    new_dollar_delta = current.dollar_delta + delta_change

    # Check breach levels
    breach_level, breach_dims = _check_breach(new_dollar_delta, limits)

    return ScenarioResult(
        shock_pct=shock_pct,
        direction=direction,
        pnl_from_delta=pnl_from_delta,
        pnl_from_gamma=pnl_from_gamma,
        pnl_impact=pnl_impact,
        delta_change=delta_change,
        new_dollar_delta=new_dollar_delta,
        breach_level=breach_level,
        breach_dims=breach_dims,
    )


def _check_breach(
    new_dollar_delta: Decimal,
    limits: dict[str, Decimal],
) -> tuple[Literal["none", "warn", "crit", "hard"], list[str]]:
    """Check if projected delta breaches limits.

    Args:
        new_dollar_delta: Projected dollar delta after shock
        limits: Dict of hard limits by field name

    Returns:
        Tuple of (breach_level, breach_dims)
    """
    breach_dims = []

    # Check dollar_delta limit using abs()
    if "dollar_delta" in limits:
        if abs(new_dollar_delta) > limits["dollar_delta"]:
            breach_dims.append("dollar_delta")

    # Determine breach level
    if breach_dims:
        return "hard", breach_dims
    return "none", []


def get_scenario_shocks(
    current: CurrentGreeks,
    limits: dict[str, Decimal],
    shock_pcts: list[Decimal] | None = None,
) -> dict[str, ScenarioResult]:
    """Get scenario shocks for multiple percentages.

    Args:
        current: Current Greeks snapshot
        limits: Hard limits for breach detection
        shock_pcts: Shock percentages (default: [1, 2])

    Returns:
        Dict mapping scenario key ("+1%", "-1%", etc.) to ScenarioResult
    """
    if shock_pcts is None:
        shock_pcts = [Decimal("1"), Decimal("2")]

    results: dict[str, ScenarioResult] = {}

    for pct in shock_pcts:
        # Up scenario
        up_key = f"+{pct}%"
        results[up_key] = calculate_scenario(
            current=current,
            shock_pct=pct,
            direction="up",
            limits=limits,
        )

        # Down scenario
        down_key = f"-{pct}%"
        results[down_key] = calculate_scenario(
            current=current,
            shock_pct=pct,
            direction="down",
            limits=limits,
        )

    return results
