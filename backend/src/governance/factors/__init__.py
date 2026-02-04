"""Factors submodule for governance.

Contains factor models, loader, and registry for managing trading factors
with mandatory failure rules that auto-disable degraded factors.
"""

from src.governance.factors.loader import FactorLoader
from src.governance.factors.models import Factor, FactorFailureRule, FactorStatus
from src.governance.factors.registry import (
    DuplicateFactorError,
    FactorHealthCheckResult,
    FactorRegistry,
)

__all__ = [
    "Factor",
    "FactorFailureRule",
    "FactorLoader",
    "FactorRegistry",
    "FactorStatus",
    "DuplicateFactorError",
    "FactorHealthCheckResult",
]
