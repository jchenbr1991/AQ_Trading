"""
Governance module for AQ Trading.

This module implements the L0 Hypothesis + L1 Constraints governance system
that separates human hypotheses from quantitative alpha generation.

Submodules:
- hypothesis: Hypothesis models, loader, and registry
- constraints: Constraint models, loader, resolver, and registry
- pool: Pool builder, filters, and models
- regime: Regime detector and models
- factors: Factor registry and models
- monitoring: Falsifier checker, alerts, scheduler, and metrics
- audit: Audit logger and models
- lint: Alpha path checker and allowlist validator
- utils: Shared utilities including YAML loader
"""

from src.governance.cache import GovernanceCache
from src.governance.context import GovernanceContext, build_governance_context
from src.governance.models import (
    AlertSeverity,
    ComparisonOperator,
    GovernanceAuditEventType,
    GovernanceBaseModel,
    HypothesisStatus,
    RegimeState,
    StopMode,
    TriggerAction,
)

__all__: list[str] = [
    # Base models and enums
    "GovernanceBaseModel",
    "GovernanceAuditEventType",
    "AlertSeverity",
    "RegimeState",
    "HypothesisStatus",
    "ComparisonOperator",
    "TriggerAction",
    "StopMode",
    # Cache
    "GovernanceCache",
    # Context
    "GovernanceContext",
    "build_governance_context",
]
