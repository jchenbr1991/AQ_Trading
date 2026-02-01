# AQ Trading AI Agents - Validation Module
"""Validation module for preventing overfitting in agent suggestions.

This module provides validators that ensure agent-generated trading
parameters and strategies are robust and generalizable.

Available validators:
- WalkForwardValidator: Walk-forward validation with train/val/test splits
"""

from agents.validation.walk_forward import (
    StabilityResult,
    ValidationResult,
    WalkForwardValidator,
)

__all__ = [
    "WalkForwardValidator",
    "ValidationResult",
    "StabilityResult",
]
