"""
Hypothesis submodule for governance.

Contains hypothesis models, loader, and registry.
"""

from src.governance.hypothesis.loader import HypothesisLoader
from src.governance.hypothesis.models import (
    Evidence,
    Falsifier,
    Hypothesis,
    HypothesisScope,
)
from src.governance.hypothesis.registry import (
    DuplicateHypothesisError,
    HypothesisRegistry,
)

__all__ = [
    "DuplicateHypothesisError",
    "Evidence",
    "Falsifier",
    "Hypothesis",
    "HypothesisLoader",
    "HypothesisRegistry",
    "HypothesisScope",
]
