"""Pool submodule for governance.

Contains pool builder, structural filters, and pool models for constructing
deterministic, versioned trading pools with audit trails.

Classes:
    StructuralFilters: Configuration for symbol filtering
    PoolAuditEntry: Audit record for inclusion/exclusion decisions
    Pool: Built pool with symbols, weights, version, and audit trail
    EmptyPoolError: Raised when all symbols are excluded
    PoolBuilder: Builds versioned trading pools

Functions:
    apply_structural_filters: Apply structural filters to a symbol universe
"""

from src.governance.pool.builder import EmptyPoolError, PoolBuilder
from src.governance.pool.filters import apply_structural_filters
from src.governance.pool.models import Pool, PoolAuditEntry, StructuralFilters

__all__ = [
    "StructuralFilters",
    "PoolAuditEntry",
    "Pool",
    "EmptyPoolError",
    "PoolBuilder",
    "apply_structural_filters",
]
