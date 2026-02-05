"""Pydantic models for the Pool governance layer.

This module defines the data structures for pool building, structural filtering,
and audit trail tracking within the L0 Hypothesis + L1 Constraints governance system.

Classes:
    StructuralFilters: Configuration for symbol filtering (volume, sector, price, etc.)
    PoolAuditEntry: Individual audit record for pool inclusion/exclusion decisions
    Pool: The built pool of symbols with version, weights, and audit trail
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from src.governance.models import GovernanceBaseModel


class StructuralFilters(GovernanceBaseModel):
    """Configuration for structural symbol filtering.

    Structural filters are independent of hypotheses and define hard constraints
    on which symbols can appear in the active trading pool. All filters use
    AND logic -- a symbol must pass ALL active filters to be included.

    Attributes:
        exclude_state_owned_ratio_gte: Exclude symbols with state-owned ratio >= threshold (0-1).
        exclude_dividend_yield_gte: Exclude symbols with dividend yield >= threshold (>=0).
        min_avg_dollar_volume: Minimum average daily dollar volume required (>=0).
        exclude_sectors: List of sector names to exclude from the pool.
        min_market_cap: Minimum market capitalization required (>=0).
        max_price: Maximum share price allowed (>=0).
        min_price: Minimum share price required (>=0).
    """

    exclude_state_owned_ratio_gte: Annotated[float, Field(ge=0, le=1)] | None = None
    exclude_dividend_yield_gte: Annotated[float, Field(ge=0)] | None = None
    min_avg_dollar_volume: Annotated[float, Field(ge=0)] | None = None
    exclude_sectors: list[str] = []
    min_market_cap: Annotated[float, Field(ge=0)] | None = None
    max_price: Annotated[float, Field(ge=0)] | None = None
    min_price: Annotated[float, Field(ge=0)] | None = None


class PoolAuditEntry(GovernanceBaseModel):
    """Individual audit record for a pool inclusion/exclusion decision.

    Each symbol processed by the pool builder gets an audit entry recording
    whether it was included, excluded, or prioritized, along with the reason
    and source of the decision.

    Attributes:
        symbol: Ticker symbol (e.g., "AAPL").
        action: Decision type -- "included", "excluded", or "prioritized".
        reason: Human-readable reason for the decision.
        source: Source of the decision (e.g., filter name, hypothesis ID).
    """

    symbol: str
    action: Literal["included", "excluded", "prioritized"]
    reason: str
    source: str


class Pool(GovernanceBaseModel):
    """The built pool of symbols ready for trading.

    Represents a deterministic, versioned snapshot of the active symbol pool
    after applying structural filters and hypothesis gating. The version hash
    ensures identical inputs produce identical outputs.

    Attributes:
        symbols: List of ticker symbols in the pool (sorted for determinism).
        weights: Optional priority weights per symbol (default empty).
        version: Version string in format "{timestamp}_{config_hash}".
        built_at: UTC timestamp when the pool was built.
        audit_trail: List of audit entries documenting inclusion/exclusion decisions.
    """

    symbols: list[str]
    weights: dict[str, float] = {}
    version: str
    built_at: datetime
    audit_trail: list[PoolAuditEntry]

    @property
    def is_empty(self) -> bool:
        """Check if the pool contains no symbols.

        Returns:
            True if the symbols list is empty, False otherwise.
        """
        return len(self.symbols) == 0


__all__ = [
    "StructuralFilters",
    "PoolAuditEntry",
    "Pool",
]
