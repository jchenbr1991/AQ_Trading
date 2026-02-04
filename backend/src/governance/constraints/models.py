"""Pydantic models for L1 Constraints.

This module defines the data structures for constraints in the governance system.
Constraints link to hypotheses and define actions to take when hypotheses are active.

Classes:
    ConstraintAppliesTo: Scope of constraint (symbols, strategies)
    ConstraintActivation: Activation rules linked to hypotheses
    ConstraintActions: Allowlisted actions a constraint can take
    ConstraintGuardrails: Risk guardrails for the constraint
    Constraint: Complete constraint definition
    ResolvedAction: Single resolved action from a constraint
    ResolvedConstraints: Result of resolving all constraints for a symbol
"""

from datetime import datetime

from pydantic import Field

from src.governance.models import GovernanceBaseModel, StopMode


class ConstraintAppliesTo(GovernanceBaseModel):
    """Defines what a constraint applies to.

    Attributes:
        symbols: List of stock symbols this constraint applies to.
                 Empty list means all symbols.
        strategies: List of strategy IDs this constraint applies to.
                   Empty list means all strategies.
    """

    symbols: list[str] = Field(default_factory=list)
    strategies: list[str] = Field(default_factory=list)


class ConstraintActivation(GovernanceBaseModel):
    """Defines when a constraint becomes active.

    Attributes:
        requires_hypotheses_active: List of hypothesis IDs that must be active
                                   for this constraint to activate.
        disabled_if_falsified: If True (default), constraint is disabled when
                              any linked hypothesis is falsified/sunset.
    """

    requires_hypotheses_active: list[str] = Field(default_factory=list)
    disabled_if_falsified: bool = Field(default=True)


class ConstraintActions(GovernanceBaseModel):
    """Allowlisted actions a constraint can take.

    All fields are optional/nullable. Only specified fields will be applied.

    Attributes:
        enable_strategy: Enable or disable a strategy.
        pool_bias_multiplier: Multiplier for pool bias (must be > 0).
        veto_downgrade: Enable veto downgrade protection.
        risk_budget_multiplier: Multiplier for risk budget (must be >= 1).
        holding_extension_days: Days to extend holding period (must be >= 0).
        add_position_cap_multiplier: Multiplier for position cap (must be > 0).
        stop_mode: Stop loss mode (baseline, wide, fundamental_guarded).
    """

    enable_strategy: bool | None = None
    pool_bias_multiplier: float | None = Field(default=None, gt=0)
    veto_downgrade: bool | None = None
    risk_budget_multiplier: float | None = Field(default=None, ge=1)
    holding_extension_days: int | None = Field(default=None, ge=0)
    add_position_cap_multiplier: float | None = Field(default=None, gt=0)
    stop_mode: StopMode | None = None


class ConstraintGuardrails(GovernanceBaseModel):
    """Risk guardrails for a constraint.

    These guardrails provide upper bounds on risk-taking even when
    a constraint's actions are applied.

    Attributes:
        max_position_pct: Maximum position size as percentage (0 to 1).
        max_gross_exposure_delta: Maximum change in gross exposure.
        max_drawdown_addon: Maximum additional drawdown allowed.
    """

    max_position_pct: float | None = Field(default=None, ge=0, le=1)
    max_gross_exposure_delta: float | None = None
    max_drawdown_addon: float | None = None


class Constraint(GovernanceBaseModel):
    """Complete constraint definition.

    A constraint links to one or more hypotheses and defines actions to take
    when those hypotheses are active. Constraints are loaded from YAML files
    in the config/constraints/ directory.

    Attributes:
        id: Unique identifier (lowercase alphanumeric with underscores).
        title: Human-readable title for the constraint.
        applies_to: Scope of the constraint (symbols, strategies).
        activation: Activation rules linked to hypotheses.
        actions: Actions to take when constraint is active.
        guardrails: Optional risk guardrails.
        priority: Priority for conflict resolution (default 100, minimum 1).
                 Lower number = higher priority.
    """

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    title: str
    applies_to: ConstraintAppliesTo
    activation: ConstraintActivation
    actions: ConstraintActions
    guardrails: ConstraintGuardrails | None = None
    priority: int = Field(default=100, ge=1)


class ResolvedAction(GovernanceBaseModel):
    """Single resolved action from a constraint.

    Represents one action that should be taken based on a resolved constraint.
    The value can be a number (multipliers), boolean (flags), or string (modes).

    Attributes:
        constraint_id: ID of the constraint this action came from.
        action_type: Type of action (e.g., risk_budget_multiplier, stop_mode).
        value: The action value - can be number, boolean, or string.
    """

    constraint_id: str
    action_type: str
    value: float | bool | str


class ResolvedConstraints(GovernanceBaseModel):
    """Result of resolving all constraints for a symbol.

    Contains the merged effective values from all applicable constraints,
    along with the list of individual resolved actions for transparency.

    Attributes:
        symbol: The stock symbol these constraints were resolved for.
        constraints: List of individual resolved actions from all constraints.
        resolved_at: Timestamp when constraints were resolved.
        version: Deterministic hash of constraint IDs for cache invalidation.
        effective_risk_budget_multiplier: Product of all risk_budget_multiplier values.
        effective_pool_bias_multiplier: Product of all pool_bias_multiplier values.
        effective_stop_mode: Most restrictive stop mode across all constraints.
        veto_downgrade_active: OR of all veto_downgrade values.
        guardrails: Merged guardrails using most restrictive values.
    """

    symbol: str
    constraints: list[ResolvedAction]
    resolved_at: datetime
    version: str
    effective_risk_budget_multiplier: float = Field(default=1.0)
    effective_pool_bias_multiplier: float = Field(default=1.0)
    effective_stop_mode: str = Field(default="baseline")
    veto_downgrade_active: bool = Field(default=False)
    guardrails: ConstraintGuardrails | None = None


__all__ = [
    "ConstraintAppliesTo",
    "ConstraintActivation",
    "ConstraintActions",
    "ConstraintGuardrails",
    "Constraint",
    "ResolvedAction",
    "ResolvedConstraints",
]
