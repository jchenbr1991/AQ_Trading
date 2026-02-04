"""Regime models for position pacing governance.

This module defines the data models for the regime-based position pacing system.
Regime state affects position sizing/pacing but NEVER contributes to alpha.

Classes:
    RegimeThresholds: Volatility and drawdown thresholds for regime transitions
    RegimeConfig: Full regime configuration including thresholds and pacing multipliers
    RegimeSnapshot: Point-in-time regime state with metrics and pacing multiplier
"""

from __future__ import annotations

from datetime import datetime

from src.governance.models import GovernanceBaseModel, RegimeState


class RegimeThresholds(GovernanceBaseModel):
    """Thresholds for regime state transitions.

    Defines the volatility and drawdown levels that trigger transitions
    between NORMAL, TRANSITION, and STRESS regimes.

    Attributes:
        volatility_transition: Portfolio volatility level triggering TRANSITION state.
        volatility_stress: Portfolio volatility level triggering STRESS state.
        drawdown_transition: Max drawdown level triggering TRANSITION state.
        drawdown_stress: Max drawdown level triggering STRESS state.
    """

    volatility_transition: float
    volatility_stress: float
    drawdown_transition: float
    drawdown_stress: float


class RegimeConfig(GovernanceBaseModel):
    """Full regime configuration.

    Combines thresholds with pacing multipliers that map each regime state
    to a position sizing factor.

    Attributes:
        thresholds: Volatility and drawdown thresholds for state transitions.
        pacing_multipliers: Mapping of regime state name to position pacing
            multiplier (e.g., {"NORMAL": 1.0, "TRANSITION": 0.5, "STRESS": 0.1}).
    """

    thresholds: RegimeThresholds
    pacing_multipliers: dict[str, float]


class RegimeSnapshot(GovernanceBaseModel):
    """Point-in-time regime state snapshot.

    Captures the current regime state, previous state for transition tracking,
    the metrics that informed the detection, and the resulting pacing multiplier.

    Attributes:
        state: Current regime state (NORMAL, TRANSITION, STRESS).
        previous_state: Previous regime state, or None if first detection.
        changed_at: Timestamp when this snapshot was created.
        metrics: Current metric values used for detection.
        pacing_multiplier: Position sizing multiplier for the current state.
    """

    state: RegimeState
    previous_state: RegimeState | None
    changed_at: datetime
    metrics: dict[str, float]
    pacing_multiplier: float


__all__ = [
    "RegimeThresholds",
    "RegimeConfig",
    "RegimeSnapshot",
]
