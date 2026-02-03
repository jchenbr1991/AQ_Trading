"""Pool builder with hash-based versioning and hypothesis gating.

This module implements the PoolBuilder class that constructs deterministic,
versioned trading pools by applying structural filters and hypothesis gating
(denylist/allowlist) to a base universe of symbols.

Classes:
    EmptyPoolError: Raised when all symbols are excluded from the pool.
    PoolBuilder: Builds versioned trading pools with audit trails.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from src.governance.pool.filters import apply_structural_filters
from src.governance.pool.models import Pool, PoolAuditEntry, StructuralFilters

if TYPE_CHECKING:
    from src.governance.hypothesis.registry import HypothesisRegistry


class EmptyPoolError(Exception):
    """Raised when all symbols are excluded from the pool after filtering.

    This error prevents strategy execution with an empty universe, which would
    be nonsensical. The audit_trail attribute provides debugging information
    showing why each symbol was excluded.

    Attributes:
        audit_trail: List of PoolAuditEntry objects documenting exclusion reasons.
    """

    def __init__(self, message: str, audit_trail: list[PoolAuditEntry] | None = None) -> None:
        """Initialize with a descriptive message and optional audit trail.

        Args:
            message: Error message (should contain 'empty' for assertion checks).
            audit_trail: List of audit entries showing why symbols were excluded.
        """
        super().__init__(message)
        self.audit_trail = audit_trail if audit_trail is not None else []


class PoolBuilder:
    """Builds deterministic, versioned trading pools.

    The pool builder applies structural filters and hypothesis gating to a base
    universe of symbols, producing a Pool with:
    - Sorted symbol list (alphabetical for determinism)
    - Version string with timestamp and config hash
    - Complete audit trail of inclusion/exclusion decisions
    - Optional priority weights from hypothesis bias

    Attributes:
        hypothesis_registry: Optional registry for hypothesis lookups.

    Example:
        >>> from src.governance.hypothesis.registry import HypothesisRegistry
        >>> from src.governance.pool.builder import PoolBuilder
        >>> from src.governance.pool.models import StructuralFilters
        >>> registry = HypothesisRegistry()
        >>> builder = PoolBuilder(hypothesis_registry=registry)
        >>> pool = builder.build(universe=symbols, filters=StructuralFilters())
    """

    def __init__(self, hypothesis_registry: HypothesisRegistry | None = None) -> None:
        """Initialize the pool builder.

        Args:
            hypothesis_registry: Optional HypothesisRegistry for hypothesis gating.
        """
        self.hypothesis_registry = hypothesis_registry

    def build(
        self,
        universe: list[Any],
        filters: StructuralFilters,
        denylist_hypotheses: list[str] | None = None,
        allowlist_hypotheses: list[str] | None = None,
        bias_hypotheses: list[str] | None = None,
        bias_multiplier: float = 1.0,
    ) -> Pool:
        """Build a versioned trading pool from the universe.

        Steps:
        1. Apply structural filters to the universe.
        2. Apply hypothesis gating (denylist exclusions, allowlist restrictions, bias weights).
        3. Sort symbols alphabetically for determinism.
        4. Generate version string with timestamp and config hash.
        5. Record audit trail for all symbols.
        6. Raise EmptyPoolError if no symbols remain.

        Args:
            universe: List of symbol data objects.
            filters: Structural filter configuration.
            denylist_hypotheses: List of hypothesis IDs whose scope.symbols should be excluded.
            allowlist_hypotheses: List of hypothesis IDs whose scope restricts pool to only
                matching symbols/sectors. Only ACTIVE hypotheses are applied.
            bias_hypotheses: List of hypothesis IDs whose scope.sectors get weight bias.
            bias_multiplier: Multiplier for bias weights (default 1.0).

        Returns:
            Pool object with symbols, weights, version, timestamp, and audit trail.

        Raises:
            EmptyPoolError: If all symbols are excluded after filtering.
        """
        denylist_hypotheses = denylist_hypotheses or []
        allowlist_hypotheses = allowlist_hypotheses or []
        bias_hypotheses = bias_hypotheses or []

        audit_trail: list[PoolAuditEntry] = []

        # Step 1: Apply structural filters
        passed, excluded = apply_structural_filters(universe, filters)

        # Record structural exclusions in audit trail
        for symbol_data, reason in excluded:
            audit_trail.append(
                PoolAuditEntry(
                    symbol=symbol_data.symbol,
                    action="excluded",
                    reason=reason,
                    source=_extract_filter_source(reason),
                )
            )

        # Step 2: Apply hypothesis gating - denylist
        remaining_symbols = list(passed)
        denylist_symbols = self._resolve_denylist(denylist_hypotheses)

        symbols_after_denylist = []
        for symbol_data in remaining_symbols:
            if symbol_data.symbol in denylist_symbols:
                hypothesis_id = denylist_symbols[symbol_data.symbol]
                audit_trail.append(
                    PoolAuditEntry(
                        symbol=symbol_data.symbol,
                        action="excluded",
                        reason=f"hypothesis:{hypothesis_id}",
                        source=hypothesis_id,
                    )
                )
            else:
                symbols_after_denylist.append(symbol_data)

        # Step 2b: Apply hypothesis gating - allowlist
        allowed = self._resolve_allowlist(allowlist_hypotheses)
        if allowed is not None:
            allowed_symbols_set = allowed["symbols"]
            allowed_sectors_set = allowed["sectors"]
            symbols_after_allowlist = []
            for sd in symbols_after_denylist:
                if sd.symbol in allowed_symbols_set or sd.sector in allowed_sectors_set:
                    symbols_after_allowlist.append(sd)
                else:
                    hypothesis_ids = allowed.get("hypothesis_ids", [])
                    source = hypothesis_ids[0] if hypothesis_ids else "allowlist"
                    audit_trail.append(
                        PoolAuditEntry(
                            symbol=sd.symbol,
                            action="excluded",
                            reason=f"hypothesis_allowlist:{source}",
                            source=source,
                        )
                    )
            symbols_after_denylist = symbols_after_allowlist

        # Step 3: Sort symbols alphabetically for determinism
        symbols_after_denylist.sort(key=lambda sd: sd.symbol)

        # Build final symbol list and weights
        final_symbols = [sd.symbol for sd in symbols_after_denylist]
        weights: dict[str, float] = {}

        # Apply hypothesis bias weights
        bias_sectors = self._resolve_bias_sectors(bias_hypotheses)
        if bias_sectors and bias_multiplier != 1.0:
            for sd in symbols_after_denylist:
                if sd.sector in bias_sectors:
                    weights[sd.symbol] = bias_multiplier
                    hypothesis_id = bias_sectors[sd.sector]
                    audit_trail.append(
                        PoolAuditEntry(
                            symbol=sd.symbol,
                            action="prioritized",
                            reason=f"hypothesis:{hypothesis_id}",
                            source=hypothesis_id,
                        )
                    )

        # Record inclusions in audit trail
        for sd in symbols_after_denylist:
            audit_trail.append(
                PoolAuditEntry(
                    symbol=sd.symbol,
                    action="included",
                    reason="passed_all_filters",
                    source="pool_builder",
                )
            )

        # Step 6: Raise EmptyPoolError if no symbols remain
        if not final_symbols:
            raise EmptyPoolError(
                "Pool is empty after filtering: all symbols were excluded",
                audit_trail=audit_trail,
            )

        # Step 4: Generate version string
        now = datetime.now(timezone.utc)
        version = self._generate_version(
            now,
            filters,
            denylist_hypotheses,
            allowlist_hypotheses,
            bias_hypotheses,
            bias_multiplier,
        )

        # Step 5: Return Pool
        return Pool(
            symbols=final_symbols,
            weights=weights,
            version=version,
            built_at=now,
            audit_trail=audit_trail,
        )

    def _resolve_denylist(self, denylist_hypotheses: list[str]) -> dict[str, str]:
        """Resolve denylist hypothesis IDs to a map of symbol -> hypothesis_id.

        Only ACTIVE hypotheses are applied. Inactive (DRAFT, SUNSET, REJECTED)
        hypotheses are silently skipped.

        Args:
            denylist_hypotheses: List of hypothesis IDs to check.

        Returns:
            Dict mapping symbol -> hypothesis_id for all denylisted symbols.
        """
        if not self.hypothesis_registry or not denylist_hypotheses:
            return {}

        denylist: dict[str, str] = {}
        for hypothesis_id in denylist_hypotheses:
            hypothesis = self.hypothesis_registry.get(hypothesis_id)
            if hypothesis is None:
                continue
            if not hypothesis.is_active:
                continue
            for symbol in hypothesis.scope.symbols:
                denylist[symbol] = hypothesis_id

        return denylist

    def _resolve_allowlist(
        self, allowlist_hypotheses: list[str]
    ) -> dict[str, set[str] | list[str]] | None:
        """Resolve allowlist hypothesis IDs to allowed symbols and sectors.

        Only ACTIVE hypotheses are applied. If no allowlist hypotheses are
        specified or none are active, returns None (no restriction).

        Args:
            allowlist_hypotheses: List of hypothesis IDs to check.

        Returns:
            Dict with "symbols" (set), "sectors" (set), and "hypothesis_ids" (list),
            or None if no allowlist restriction applies.
        """
        if not self.hypothesis_registry or not allowlist_hypotheses:
            return None

        allowed_symbols: set[str] = set()
        allowed_sectors: set[str] = set()
        active_ids: list[str] = []

        for hypothesis_id in allowlist_hypotheses:
            hypothesis = self.hypothesis_registry.get(hypothesis_id)
            if hypothesis is None:
                continue
            if not hypothesis.is_active:
                continue
            active_ids.append(hypothesis_id)
            allowed_symbols.update(hypothesis.scope.symbols)
            allowed_sectors.update(hypothesis.scope.sectors)

        if not active_ids:
            return None

        return {
            "symbols": allowed_symbols,
            "sectors": allowed_sectors,
            "hypothesis_ids": active_ids,
        }

    def _resolve_bias_sectors(self, bias_hypotheses: list[str]) -> dict[str, str]:
        """Resolve bias hypothesis IDs to a map of sector -> hypothesis_id.

        Only ACTIVE hypotheses are applied.

        Args:
            bias_hypotheses: List of hypothesis IDs to check.

        Returns:
            Dict mapping sector -> hypothesis_id for all biased sectors.
        """
        if not self.hypothesis_registry or not bias_hypotheses:
            return {}

        bias_sectors: dict[str, str] = {}
        for hypothesis_id in bias_hypotheses:
            hypothesis = self.hypothesis_registry.get(hypothesis_id)
            if hypothesis is None:
                continue
            if not hypothesis.is_active:
                continue
            for sector in hypothesis.scope.sectors:
                bias_sectors[sector] = hypothesis_id

        return bias_sectors

    def _generate_version(
        self,
        timestamp: datetime,
        filters: StructuralFilters,
        denylist_hypotheses: list[str],
        allowlist_hypotheses: list[str],
        bias_hypotheses: list[str],
        bias_multiplier: float,
    ) -> str:
        """Generate a deterministic version string.

        Format: "{date}_{config_hash}" where:
        - date is YYYYMMDD format
        - config_hash is first 12 chars of SHA256 of serialized config

        Args:
            timestamp: Build timestamp.
            filters: Structural filter configuration.
            denylist_hypotheses: Denylist hypothesis IDs.
            allowlist_hypotheses: Allowlist hypothesis IDs.
            bias_hypotheses: Bias hypothesis IDs.
            bias_multiplier: Bias weight multiplier.

        Returns:
            Version string in format "YYYYMMDD_<hash>".
        """
        date_str = timestamp.strftime("%Y%m%d")

        # Create deterministic config representation for hashing
        config = {
            "filters": filters.model_dump(mode="json"),
            "denylist_hypotheses": sorted(denylist_hypotheses),
            "allowlist_hypotheses": sorted(allowlist_hypotheses),
            "bias_hypotheses": sorted(bias_hypotheses),
            "bias_multiplier": bias_multiplier,
        }

        config_json = json.dumps(config, sort_keys=True, default=str)
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:12]

        return f"{date_str}_{config_hash}"


def _extract_filter_source(reason: str) -> str:
    """Extract the filter name from a structural filter reason string.

    Args:
        reason: Reason string like "structural_filter:min_avg_dollar_volume (...)".

    Returns:
        The filter name (e.g., "min_avg_dollar_volume").
    """
    if "structural_filter:" in reason:
        # Extract the filter name between "structural_filter:" and the next space or end
        after_prefix = reason.split("structural_filter:")[1]
        return after_prefix.split(" ")[0].strip()
    return reason


__all__ = [
    "EmptyPoolError",
    "PoolBuilder",
]
