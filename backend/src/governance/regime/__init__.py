"""Regime submodule for governance.

Contains regime detector and models for position pacing based on
market regime state (NORMAL, TRANSITION, STRESS).

Regime NEVER contributes to alpha; only affects position sizing/pacing.
"""

from src.governance.regime.detector import RegimeDetector
from src.governance.regime.models import RegimeConfig, RegimeSnapshot, RegimeThresholds

__all__ = [
    "RegimeConfig",
    "RegimeDetector",
    "RegimeSnapshot",
    "RegimeThresholds",
]
