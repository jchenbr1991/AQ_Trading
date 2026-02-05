"""GovernanceContext for strategy interface integration.

This module provides the GovernanceContext — an immutable, scalar-only data
object that the strategy layer uses to read governance decisions. It exposes
ONLY simple types (str, float, bool, list[str]) and never raw Constraint,
Hypothesis, or other governance domain models.

Classes:
    GovernanceContext: Frozen Pydantic model with governance scalars

Functions:
    build_governance_context: Assemble a GovernanceContext from governance components

Example:
    >>> from src.governance.context import GovernanceContext, build_governance_context
    >>> ctx = build_governance_context(symbol="AAPL")
    >>> ctx.pacing_multiplier
    1.0
    >>> ctx.active_pool
    []
"""

from __future__ import annotations

import logging

from pydantic import ConfigDict, Field

from src.governance.models import GovernanceBaseModel

logger = logging.getLogger(__name__)


class GovernanceContext(GovernanceBaseModel):
    """Immutable, scalar-only governance context for the strategy layer.

    This model is the sole interface between the governance system and the
    strategy framework. It contains ONLY scalar values and simple types —
    no raw Constraint, Hypothesis, or other governance domain objects.

    Frozen to prevent accidental mutation after construction.

    Attributes:
        active_pool: Symbols in the current trading pool (from PoolBuilder).
        pacing_multiplier: Position pacing factor from regime detector (0.0-1.0).
        risk_budget_multiplier: Multiplied risk budget from resolved constraints.
        veto_downgrade_active: Whether veto downgrade protection is active.
        stop_mode: Stop loss mode (baseline, wide, fundamental_guarded).
        pool_version: Version hash from the pool builder for cache coherence.
        regime_state: Current regime state name (NORMAL, TRANSITION, STRESS).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    active_pool: list[str] = Field(
        description="Symbols in the current trading pool",
    )
    pacing_multiplier: float = Field(
        description="Position pacing factor from regime detector",
    )
    risk_budget_multiplier: float = Field(
        description="Multiplied risk budget from resolved constraints",
    )
    veto_downgrade_active: bool = Field(
        description="Whether veto downgrade protection is active",
    )
    stop_mode: str = Field(
        default="baseline",
        description="Stop loss mode (baseline, wide, fundamental_guarded)",
    )
    pool_version: str = Field(
        description="Version hash from pool builder",
    )
    regime_state: str = Field(
        description="Current regime state name (NORMAL, TRANSITION, STRESS)",
    )


def build_governance_context(symbol: str) -> GovernanceContext:
    """Assemble a GovernanceContext from governance components.

    Uses PoolBuilder, RegimeDetector, and ConstraintResolver to build a
    complete governance context with all resolved scalar values. When
    components are not configured (e.g., no config files), sensible
    defaults are used.

    Args:
        symbol: The trading symbol to resolve governance context for.

    Returns:
        GovernanceContext with resolved scalar values.
    """
    # --- Resolve regime ---
    regime_state = "NORMAL"
    pacing_multiplier = 1.0
    try:
        from src.api.routes.governance import get_regime_detector

        detector = get_regime_detector()
        snapshot = detector.detect()
        regime_state = snapshot.state.value
        pacing_multiplier = snapshot.pacing_multiplier
    except Exception:
        logger.warning("Could not detect regime, using defaults", exc_info=True)

    # --- Resolve constraints ---
    risk_budget_multiplier = 1.0
    veto_downgrade_active = False
    stop_mode = "baseline"
    try:
        from src.api.routes.governance import get_constraint_resolver

        resolver = get_constraint_resolver()
        resolved = resolver.resolve(symbol)
        risk_budget_multiplier = resolved.effective_risk_budget_multiplier
        veto_downgrade_active = resolved.veto_downgrade_active
        stop_mode = resolved.effective_stop_mode
    except Exception:
        logger.warning("Could not resolve constraints, using defaults", exc_info=True)

    # --- Resolve pool ---
    active_pool: list[str] = []
    pool_version = "none"
    try:
        from src.api.routes.governance import _current_pool

        if _current_pool is not None:
            active_pool = list(_current_pool.symbols)
            pool_version = _current_pool.version
    except Exception:
        logger.warning("Could not read pool, using defaults", exc_info=True)

    return GovernanceContext(
        active_pool=active_pool,
        pacing_multiplier=pacing_multiplier,
        risk_budget_multiplier=risk_budget_multiplier,
        veto_downgrade_active=veto_downgrade_active,
        stop_mode=stop_mode,
        pool_version=pool_version,
        regime_state=regime_state,
    )


__all__ = [
    "GovernanceContext",
    "build_governance_context",
]
