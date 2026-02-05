# backend/src/strategies/factors/__init__.py
"""Factor models package for strategy alpha generation.

This module provides factor implementations that combine multiple indicators
into composite signals for trading decisions.

Available Factors:
- BaseFactor: Abstract base class for all factors
- FactorResult: Result dataclass with score, components, and weights
- MomentumFactor: Combines ROC and Price vs MA indicators
- BreakoutFactor: Combines Price vs High and Volume Z-Score indicators
- CompositeFactor: Combines Momentum and Breakout factors for final signal

See specs/002-minimal-mvp-trading/data-model.md for factor formulas.
"""

from src.strategies.factors.base import BaseFactor, FactorResult
from src.strategies.factors.breakout import BreakoutFactor
from src.strategies.factors.composite import CompositeFactor
from src.strategies.factors.momentum import MomentumFactor

__all__: list[str] = [
    "BaseFactor",
    "FactorResult",
    "MomentumFactor",
    "BreakoutFactor",
    "CompositeFactor",
]
