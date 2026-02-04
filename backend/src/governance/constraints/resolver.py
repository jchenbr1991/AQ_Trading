"""Constraint Resolver for resolving applicable constraints for a symbol.

This module provides the ConstraintResolver class that evaluates all constraints
against a symbol, checks activation conditions, and produces merged effective values.

Classes:
    ConstraintResolver: Resolves and merges constraints for a symbol

Example:
    >>> from src.governance.constraints.resolver import ConstraintResolver
    >>> resolver = ConstraintResolver(
    ...     constraint_registry=constraint_registry,
    ...     hypothesis_registry=hypothesis_registry,
    ... )
    >>> resolved = resolver.resolve("AAPL")
    >>> print(resolved.effective_risk_budget_multiplier)
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.governance.constraints.models import (
    Constraint,
    ConstraintGuardrails,
    ResolvedAction,
    ResolvedConstraints,
)
from src.governance.models import GovernanceAuditEventType, HypothesisStatus, StopMode

if TYPE_CHECKING:
    from src.governance.audit.store import InMemoryAuditStore
    from src.governance.cache import GovernanceCache
    from src.governance.constraints.registry import ConstraintRegistry
    from src.governance.hypothesis.registry import HypothesisRegistry

logger = logging.getLogger(__name__)

# Stop mode restrictiveness ordering (higher index = more restrictive)
STOP_MODE_RESTRICTIVENESS = {
    StopMode.BASELINE: 0,
    StopMode.WIDE: 1,
    StopMode.FUNDAMENTAL_GUARDED: 2,
    "baseline": 0,
    "wide": 1,
    "fundamental_guarded": 2,
}


class ConstraintResolver:
    """Resolves and merges constraints for a symbol.

    The resolver evaluates all constraints from the ConstraintRegistry against
    a symbol, checks activation conditions using the HypothesisRegistry, and
    produces a ResolvedConstraints object with merged effective values.

    Resolution Logic:
        1. Get all constraints applicable to the symbol from ConstraintRegistry
        2. Check activation conditions:
           - If requires_hypotheses_active is set, ALL hypotheses must be ACTIVE
           - If disabled_if_falsified=True and any linked hypothesis is SUNSET, skip
        3. Sort by priority (ascending - lower number = higher priority)
        4. Merge effective values:
           - effective_risk_budget_multiplier: multiply all risk_budget_multiplier values
           - effective_pool_bias_multiplier: multiply all pool_bias_multiplier values
           - effective_stop_mode: most restrictive (fundamental_guarded > wide > baseline)
           - veto_downgrade_active: OR of all veto_downgrade values
        5. Merge guardrails using most restrictive values (minimum for caps)
        6. Generate deterministic version hash from constraint IDs

    Attributes:
        constraint_registry: Registry for querying constraints by symbol.
        hypothesis_registry: Registry for checking hypothesis statuses.
        cache: Optional cache for caching resolved constraints.

    Example:
        >>> resolver = ConstraintResolver(
        ...     constraint_registry=constraint_registry,
        ...     hypothesis_registry=hypothesis_registry,
        ... )
        >>> resolved = resolver.resolve("AAPL")
    """

    # Cache namespace for resolved constraints
    CACHE_NAMESPACE = "resolved_constraints"

    def __init__(
        self,
        constraint_registry: ConstraintRegistry,
        hypothesis_registry: HypothesisRegistry,
        cache: GovernanceCache | None = None,
        audit_store: InMemoryAuditStore | None = None,
    ) -> None:
        """Initialize resolver with registries and optional cache/audit store.

        Args:
            constraint_registry: Registry for querying constraints.
            hypothesis_registry: Registry for checking hypothesis statuses.
            cache: Optional GovernanceCache for caching resolved constraints.
            audit_store: Optional InMemoryAuditStore for logging audit events.
        """
        self.constraint_registry = constraint_registry
        self.hypothesis_registry = hypothesis_registry
        self.cache = cache
        self.audit_store = audit_store

    def _is_constraint_active(self, constraint: Constraint) -> bool:
        """Check if a constraint's activation conditions are met.

        A constraint is active if:
        1. All hypotheses in requires_hypotheses_active are ACTIVE
        2. If disabled_if_falsified=True, no required hypothesis is SUNSET

        Args:
            constraint: The constraint to check.

        Returns:
            True if the constraint should be active, False otherwise.
        """
        activation = constraint.activation
        required_hypothesis_ids = activation.requires_hypotheses_active

        # If no hypothesis requirements, constraint is always active
        if not required_hypothesis_ids:
            return True

        for hypothesis_id in required_hypothesis_ids:
            hypothesis = self.hypothesis_registry.get(hypothesis_id)

            # If hypothesis doesn't exist, treat as not active
            if hypothesis is None:
                logger.warning(
                    f"Constraint {constraint.id} requires hypothesis {hypothesis_id} "
                    f"which does not exist in registry"
                )
                return False

            # Check if hypothesis is ACTIVE
            if hypothesis.status != HypothesisStatus.ACTIVE:
                # If disabled_if_falsified and hypothesis is SUNSET, skip
                if (
                    activation.disabled_if_falsified
                    and hypothesis.status == HypothesisStatus.SUNSET
                ):
                    logger.debug(
                        f"Constraint {constraint.id} disabled: hypothesis "
                        f"{hypothesis_id} is SUNSET and disabled_if_falsified=True"
                    )
                    return False

                # Hypothesis is not ACTIVE (could be DRAFT, SUNSET, REJECTED)
                logger.debug(
                    f"Constraint {constraint.id} inactive: hypothesis "
                    f"{hypothesis_id} status is {hypothesis.status}, not ACTIVE"
                )
                return False

        return True

    def _extract_actions(self, constraint: Constraint) -> list[ResolvedAction]:
        """Extract all defined actions from a constraint.

        Iterates through all action fields in ConstraintActions and creates
        ResolvedAction entries for non-None values.

        Args:
            constraint: The constraint to extract actions from.

        Returns:
            List of ResolvedAction entries for defined actions.
        """
        actions = []
        constraint_actions = constraint.actions

        # Check each possible action field
        if constraint_actions.enable_strategy is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="enable_strategy",
                    value=constraint_actions.enable_strategy,
                )
            )

        if constraint_actions.pool_bias_multiplier is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="pool_bias_multiplier",
                    value=constraint_actions.pool_bias_multiplier,
                )
            )

        if constraint_actions.veto_downgrade is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="veto_downgrade",
                    value=constraint_actions.veto_downgrade,
                )
            )

        if constraint_actions.risk_budget_multiplier is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="risk_budget_multiplier",
                    value=constraint_actions.risk_budget_multiplier,
                )
            )

        if constraint_actions.holding_extension_days is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="holding_extension_days",
                    value=float(constraint_actions.holding_extension_days),
                )
            )

        if constraint_actions.add_position_cap_multiplier is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="add_position_cap_multiplier",
                    value=constraint_actions.add_position_cap_multiplier,
                )
            )

        if constraint_actions.stop_mode is not None:
            actions.append(
                ResolvedAction(
                    constraint_id=constraint.id,
                    action_type="stop_mode",
                    value=constraint_actions.stop_mode.value,
                )
            )

        return actions

    def _generate_version_hash(self, constraint_ids: list[str]) -> str:
        """Generate deterministic version hash from constraint IDs.

        Args:
            constraint_ids: List of constraint IDs to hash.

        Returns:
            Hex digest of SHA256 hash of sorted constraint IDs.
        """
        # Sort for deterministic ordering
        sorted_ids = sorted(constraint_ids)
        combined = ":".join(sorted_ids)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    def _get_most_restrictive_stop_mode(self, stop_modes: list[StopMode | str]) -> str:
        """Get the most restrictive stop mode from a list.

        Restrictiveness order: fundamental_guarded > wide > baseline

        Args:
            stop_modes: List of stop modes to compare.

        Returns:
            The most restrictive stop mode as a string.
        """
        if not stop_modes:
            return "baseline"

        most_restrictive = stop_modes[0]
        max_restrictiveness = STOP_MODE_RESTRICTIVENESS.get(most_restrictive, 0)

        for mode in stop_modes[1:]:
            restrictiveness = STOP_MODE_RESTRICTIVENESS.get(mode, 0)
            if restrictiveness > max_restrictiveness:
                most_restrictive = mode
                max_restrictiveness = restrictiveness

        # Return string value
        if isinstance(most_restrictive, StopMode):
            return most_restrictive.value
        return most_restrictive

    def _merge_guardrails(
        self, guardrails_list: list[ConstraintGuardrails]
    ) -> ConstraintGuardrails | None:
        """Merge guardrails using most restrictive values.

        For caps (max_position_pct, max_gross_exposure_delta): use minimum
        For addons (max_drawdown_addon): use minimum (less tolerance)

        Args:
            guardrails_list: List of ConstraintGuardrails to merge.

        Returns:
            Merged ConstraintGuardrails or None if no guardrails defined.
        """
        if not guardrails_list:
            return None

        # Collect all defined values
        max_position_pct_values = []
        max_gross_exposure_delta_values = []
        max_drawdown_addon_values = []

        for guardrails in guardrails_list:
            if guardrails.max_position_pct is not None:
                max_position_pct_values.append(guardrails.max_position_pct)
            if guardrails.max_gross_exposure_delta is not None:
                max_gross_exposure_delta_values.append(guardrails.max_gross_exposure_delta)
            if guardrails.max_drawdown_addon is not None:
                max_drawdown_addon_values.append(guardrails.max_drawdown_addon)

        # If no values defined, return None
        if not any(
            [
                max_position_pct_values,
                max_gross_exposure_delta_values,
                max_drawdown_addon_values,
            ]
        ):
            return ConstraintGuardrails()

        # Use minimum for most restrictive
        return ConstraintGuardrails(
            max_position_pct=(min(max_position_pct_values) if max_position_pct_values else None),
            max_gross_exposure_delta=(
                min(max_gross_exposure_delta_values) if max_gross_exposure_delta_values else None
            ),
            max_drawdown_addon=(
                min(max_drawdown_addon_values) if max_drawdown_addon_values else None
            ),
        )

    def resolve(self, symbol: str) -> ResolvedConstraints:
        """Resolve all constraints for a symbol.

        Evaluates all constraints applicable to the symbol, checks activation
        conditions, and produces merged effective values.

        Args:
            symbol: The stock symbol to resolve constraints for.

        Returns:
            ResolvedConstraints with merged effective values.
        """
        # Get all constraints applicable to this symbol
        applicable_constraints = self.constraint_registry.filter_by_symbol(symbol)

        # Filter to only active constraints
        active_constraints = [c for c in applicable_constraints if self._is_constraint_active(c)]

        # Sort by priority (ascending - lower number = higher priority)
        active_constraints.sort(key=lambda c: (c.priority, c.id))

        # Collect resolved actions and compute merged values
        all_actions: list[ResolvedAction] = []
        risk_budget_multipliers: list[float] = []
        pool_bias_multipliers: list[float] = []
        stop_modes: list[StopMode | str] = []
        veto_downgrade_values: list[bool] = []
        guardrails_list: list[ConstraintGuardrails] = []
        constraint_ids: list[str] = []

        for constraint in active_constraints:
            constraint_ids.append(constraint.id)

            # Extract actions
            actions = self._extract_actions(constraint)
            all_actions.extend(actions)

            # Collect values for merging
            if constraint.actions.risk_budget_multiplier is not None:
                risk_budget_multipliers.append(constraint.actions.risk_budget_multiplier)

            if constraint.actions.pool_bias_multiplier is not None:
                pool_bias_multipliers.append(constraint.actions.pool_bias_multiplier)

            if constraint.actions.stop_mode is not None:
                stop_modes.append(constraint.actions.stop_mode)

            if constraint.actions.veto_downgrade is not None:
                veto_downgrade_values.append(constraint.actions.veto_downgrade)

            if constraint.guardrails is not None:
                guardrails_list.append(constraint.guardrails)

        # Compute merged effective values
        effective_risk_budget_multiplier = 1.0
        for mult in risk_budget_multipliers:
            effective_risk_budget_multiplier *= mult

        effective_pool_bias_multiplier = 1.0
        for mult in pool_bias_multipliers:
            effective_pool_bias_multiplier *= mult

        effective_stop_mode = self._get_most_restrictive_stop_mode(stop_modes)

        # OR of all veto_downgrade values
        veto_downgrade_active = any(veto_downgrade_values)

        # Merge guardrails
        merged_guardrails = self._merge_guardrails(guardrails_list)

        # Generate version hash
        version = self._generate_version_hash(constraint_ids)

        result = ResolvedConstraints(
            symbol=symbol,
            constraints=all_actions,
            resolved_at=datetime.now(timezone.utc),
            version=version,
            effective_risk_budget_multiplier=effective_risk_budget_multiplier,
            effective_pool_bias_multiplier=effective_pool_bias_multiplier,
            effective_stop_mode=effective_stop_mode,
            veto_downgrade_active=veto_downgrade_active,
            guardrails=merged_guardrails,
        )

        # Log audit events if audit store is configured
        self._log_audit_events(symbol, active_constraints, result)

        return result

    def _log_audit_events(
        self,
        symbol: str,
        active_constraints: list[Constraint],
        result: ResolvedConstraints,
    ) -> None:
        """Log audit events for constraint resolution.

        Logs the following events when audit_store is configured:
        - CONSTRAINT_ACTIVATED for each active constraint
        - VETO_DOWNGRADE when veto_downgrade_active is True
        - RISK_BUDGET_ADJUSTED when effective_risk_budget_multiplier != 1.0

        Args:
            symbol: The stock symbol being resolved.
            active_constraints: List of active constraints that were applied.
            result: The resolved constraints result.
        """
        if self.audit_store is None:
            return

        # Log CONSTRAINT_ACTIVATED for each active constraint
        for constraint in active_constraints:
            self.audit_store.log(
                event_type=GovernanceAuditEventType.CONSTRAINT_ACTIVATED,
                constraint_id=constraint.id,
                symbol=symbol,
                action_details={
                    "priority": constraint.priority,
                    "title": constraint.title,
                    "actions": constraint.actions.model_dump(mode="json", exclude_none=True),
                    "applies_to": constraint.applies_to.model_dump(mode="json"),
                },
            )

        # Log VETO_DOWNGRADE when veto_downgrade_active is True
        if result.veto_downgrade_active:
            constraint_ids = [c.id for c in active_constraints if c.actions.veto_downgrade]
            self.audit_store.log(
                event_type=GovernanceAuditEventType.VETO_DOWNGRADE,
                constraint_id=constraint_ids[0] if constraint_ids else None,
                symbol=symbol,
                action_details={
                    "veto_downgrade_active": True,
                    "constraint_ids": constraint_ids,
                },
            )

        # Log RISK_BUDGET_ADJUSTED when multiplier != 1.0
        if result.effective_risk_budget_multiplier != 1.0:
            self.audit_store.log(
                event_type=GovernanceAuditEventType.RISK_BUDGET_ADJUSTED,
                symbol=symbol,
                action_details={
                    "effective_multiplier": result.effective_risk_budget_multiplier,
                },
            )

        # Log POSITION_CAP_APPLIED when guardrails have position caps
        if result.guardrails and result.guardrails.max_position_pct is not None:
            self.audit_store.log(
                event_type=GovernanceAuditEventType.POSITION_CAP_APPLIED,
                symbol=symbol,
                action_details={
                    "max_position_pct": result.guardrails.max_position_pct,
                },
            )

    async def resolve_async(self, symbol: str) -> ResolvedConstraints:
        """Resolve all constraints for a symbol with cache support.

        Async version that checks cache first and caches the result.

        Args:
            symbol: The stock symbol to resolve constraints for.

        Returns:
            ResolvedConstraints with merged effective values.
        """
        # Try cache first if available
        if self.cache is not None:
            cached = await self.cache.get(self.CACHE_NAMESPACE, symbol, ResolvedConstraints)
            if cached is not None:
                logger.debug(f"Cache hit for resolved constraints: {symbol}")
                return cached

        # Resolve constraints
        result = self.resolve(symbol)

        # Cache result if cache is available
        if self.cache is not None:
            await self.cache.set(self.CACHE_NAMESPACE, symbol, result)
            logger.debug(f"Cached resolved constraints for: {symbol}")

        return result

    async def invalidate_cache(self, symbol: str) -> None:
        """Invalidate cached constraints for a symbol.

        Args:
            symbol: The symbol to invalidate cache for.
        """
        if self.cache is None:
            return

        await self.cache.delete(self.CACHE_NAMESPACE, symbol)
        logger.debug(f"Invalidated cache for: {symbol}")

    async def invalidate_all_cache(self) -> int:
        """Invalidate all cached resolved constraints.

        Returns:
            Count of deleted cache entries.
        """
        if self.cache is None:
            return 0

        count = await self.cache.invalidate_namespace(self.CACHE_NAMESPACE)
        logger.info(f"Invalidated {count} cached resolved constraints")
        return count


__all__ = ["ConstraintResolver"]
