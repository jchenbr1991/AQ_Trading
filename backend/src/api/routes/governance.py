"""Governance API router skeleton.

This module provides the API endpoints for the L0 Hypothesis + L1 Constraints
governance system. Hypothesis endpoints are implemented; other endpoints return
501 Not Implemented until their respective user stories are completed.

Endpoints per OpenAPI spec (specs/003-hypothesis-constraints-system/contracts/openapi.yaml):
    Hypotheses:
        GET  /governance/hypotheses                           - List all hypotheses (IMPLEMENTED)
        GET  /governance/hypotheses/{hypothesis_id}           - Get hypothesis by ID (IMPLEMENTED)
        POST /governance/hypotheses/{hypothesis_id}/falsifiers/check - Run falsifier checks (Phase 6)

    Constraints:
        GET  /governance/constraints                          - List all constraints (IMPLEMENTED)
        GET  /governance/constraints/{constraint_id}          - Get constraint by ID (IMPLEMENTED)
        GET  /governance/constraints/resolve/{symbol}         - Resolve constraints for symbol (IMPLEMENTED)

    Pool:
        GET  /governance/pool                                 - Get current active pool (Phase 5)
        POST /governance/pool                                 - Rebuild pool (Phase 5)
        GET  /governance/pool/{symbol}/audit                  - Get symbol audit trail (Phase 5)

    Regime:
        GET  /governance/regime                               - Get current regime state (Phase 9)

    Audit:
        GET  /governance/audit                                - Query audit logs (Phase 7)

    Lint/Gates:
        POST /governance/lint/alpha-path                      - Run alpha path lint check (IMPLEMENTED)
        POST /governance/lint/constraint-allowlist            - Run allowlist lint check (IMPLEMENTED)
        POST /governance/gates/validate                       - Run all gate validations (IMPLEMENTED)

Example:
    >>> from fastapi import FastAPI
    >>> from src.api.routes.governance import router
    >>> app = FastAPI()
    >>> app.include_router(router)
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Response, status
from pydantic import BaseModel

from src.governance.constraints.loader import ConstraintLoader
from src.governance.constraints.models import Constraint, ResolvedConstraints
from src.governance.constraints.registry import ConstraintRegistry
from src.governance.constraints.resolver import ConstraintResolver
from src.governance.hypothesis.loader import HypothesisLoader
from src.governance.hypothesis.models import Hypothesis
from src.governance.hypothesis.registry import HypothesisRegistry
from src.governance.lint.allowlist import AllowlistLint
from src.governance.lint.alpha_path import AlphaPathLint
from src.governance.lint.models import GateCheckResult, GateResult, LintResult
from src.governance.models import HypothesisStatus
from src.governance.pool.builder import EmptyPoolError, PoolBuilder
from src.governance.pool.models import Pool, PoolAuditEntry, StructuralFilters

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["governance"])

# =============================================================================
# Singleton Registry - Hypotheses
# =============================================================================

# Initialize the hypothesis loader and registry as module-level singletons
_hypothesis_loader: HypothesisLoader | None = None
_hypothesis_registry: HypothesisRegistry | None = None


def get_hypothesis_registry() -> HypothesisRegistry:
    """Get the singleton HypothesisRegistry instance.

    Lazily initializes the loader and registry on first access.
    The registry is loaded from the default hypotheses directory.

    Returns:
        The singleton HypothesisRegistry instance.
    """
    global _hypothesis_loader, _hypothesis_registry

    if _hypothesis_registry is None:
        # Initialize loader with default path (config/hypotheses/)
        _hypothesis_loader = HypothesisLoader()
        _hypothesis_registry = HypothesisRegistry(loader=_hypothesis_loader)

        # Try to load hypotheses, but don't fail if directory is empty/missing
        try:
            _hypothesis_registry.reload()
            logger.info(f"Loaded {_hypothesis_registry.count()} hypotheses into registry")
        except FileNotFoundError:
            # Mark as loaded to prevent lazy loading from trying again
            _hypothesis_registry._loaded = True
            logger.warning("Hypotheses directory not found. Registry initialized empty.")

    return _hypothesis_registry


def reset_hypothesis_registry() -> None:
    """Reset the singleton registry (for testing purposes).

    This function is intended for use in tests to reset the registry state.
    """
    global _hypothesis_loader, _hypothesis_registry
    _hypothesis_loader = None
    _hypothesis_registry = None


# =============================================================================
# Singleton Registry - Constraints
# =============================================================================

# Initialize the constraint loader, registry, and resolver as module-level singletons
_constraint_loader: ConstraintLoader | None = None
_constraint_registry: ConstraintRegistry | None = None
_constraint_resolver: ConstraintResolver | None = None


def get_constraint_registry() -> ConstraintRegistry:
    """Get the singleton ConstraintRegistry instance.

    Lazily initializes the loader and registry on first access.
    The registry is loaded from the default constraints directory.

    Returns:
        The singleton ConstraintRegistry instance.
    """
    global _constraint_loader, _constraint_registry

    if _constraint_registry is None:
        # Initialize loader with default path (config/constraints/)
        _constraint_loader = ConstraintLoader()
        _constraint_registry = ConstraintRegistry(loader=_constraint_loader)

        # Try to load constraints, but don't fail if directory is empty/missing
        try:
            _constraint_registry.reload()
            logger.info(f"Loaded {_constraint_registry.count()} constraints into registry")
        except FileNotFoundError:
            # Mark as loaded to prevent lazy loading from trying again
            _constraint_registry._loaded = True
            logger.warning("Constraints directory not found. Registry initialized empty.")

    return _constraint_registry


def get_constraint_resolver() -> ConstraintResolver:
    """Get the singleton ConstraintResolver instance.

    Lazily initializes the resolver with both hypothesis and constraint registries.

    Returns:
        The singleton ConstraintResolver instance.
    """
    global _constraint_resolver

    if _constraint_resolver is None:
        _constraint_resolver = ConstraintResolver(
            constraint_registry=get_constraint_registry(),
            hypothesis_registry=get_hypothesis_registry(),
        )

    return _constraint_resolver


def reset_constraint_registry() -> None:
    """Reset the constraint singleton registries (for testing purposes).

    This function is intended for use in tests to reset the registry state.
    """
    global _constraint_loader, _constraint_registry, _constraint_resolver
    _constraint_loader = None
    _constraint_registry = None
    _constraint_resolver = None


# =============================================================================
# Singleton - Pool Builder
# =============================================================================

_pool_builder: PoolBuilder | None = None
_current_pool: Pool | None = None


class RebuildPoolRequest(BaseModel):
    """Request body for pool rebuild endpoint."""

    denylist_hypotheses: list[str] = []
    allowlist_hypotheses: list[str] = []
    bias_hypotheses: list[str] = []
    bias_multiplier: float = 1.0


def get_pool_builder() -> PoolBuilder:
    """Get the singleton PoolBuilder instance.

    Returns:
        The singleton PoolBuilder instance.
    """
    global _pool_builder

    if _pool_builder is None:
        _pool_builder = PoolBuilder(
            hypothesis_registry=get_hypothesis_registry(),
        )

    return _pool_builder


def reset_pool_builder() -> None:
    """Reset the pool builder singleton (for testing purposes)."""
    global _pool_builder, _current_pool
    _pool_builder = None
    _current_pool = None


def _not_implemented(phase: int, description: str) -> HTTPException:
    """Create a 501 Not Implemented exception with phase info.

    Args:
        phase: The phase number when this endpoint will be implemented
        description: Brief description of the endpoint

    Returns:
        HTTPException with 501 status and descriptive message
    """
    return HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Not implemented yet. {description} will be implemented in Phase {phase}.",
    )


# =============================================================================
# Hypotheses Endpoints (IMPLEMENTED)
# =============================================================================


@router.get("/hypotheses", response_model=list[Hypothesis])
async def list_hypotheses(
    status: HypothesisStatus | None = Query(
        default=None,
        description="Filter by hypothesis status (DRAFT, ACTIVE, SUNSET, REJECTED)",
    ),
) -> list[Hypothesis]:
    """List all hypotheses.

    Returns all registered hypotheses with their current status.
    Optionally filter by status.

    Args:
        status: Optional filter by status (DRAFT, ACTIVE, SUNSET, REJECTED)

    Returns:
        List of Hypothesis objects matching the filter criteria.

    Example Response:
        [
            {
                "id": "memory_demand_2027",
                "title": "AI Memory Demand Growth",
                "status": "ACTIVE",
                "falsifiers": [...],
                "linked_constraints": [...]
            }
        ]
    """
    registry = get_hypothesis_registry()

    if status is not None:
        return registry.filter_by_status(status)
    return registry.list_all()


@router.get("/hypotheses/{hypothesis_id}", response_model=Hypothesis)
async def get_hypothesis(hypothesis_id: str) -> Hypothesis:
    """Get hypothesis by ID.

    Args:
        hypothesis_id: The unique hypothesis identifier

    Returns:
        The Hypothesis object if found.

    Raises:
        HTTPException 404: If hypothesis not found.

    Example Response:
        {
            "id": "memory_demand_2027",
            "title": "AI Memory Demand Growth",
            "statement": "AI compute demand will drive memory prices up",
            "status": "ACTIVE",
            ...
        }
    """
    registry = get_hypothesis_registry()
    hypothesis = registry.get(hypothesis_id)

    if hypothesis is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hypothesis '{hypothesis_id}' not found",
        )

    return hypothesis


@router.post("/hypotheses/{hypothesis_id}/falsifiers/check")
async def check_falsifiers(hypothesis_id: str):
    """Run falsifier checks for a hypothesis.

    Evaluates all falsifier rules defined for the hypothesis against
    current metric data.

    Args:
        hypothesis_id: The unique hypothesis identifier

    Returns:
        501: Not Implemented - To be completed in Phase 6

    Example Response (when implemented):
        [
            {
                "hypothesis_id": "memory_demand_2027",
                "falsifier_index": 0,
                "metric": "rolling_ic_mean",
                "expected": ">= 0",
                "actual": 0.05,
                "triggered": false,
                "trigger_action": "review",
                "checked_at": "2026-02-03T10:00:00Z"
            }
        ]
    """
    raise _not_implemented(6, f"Check falsifiers for {hypothesis_id}")


# =============================================================================
# Constraints Endpoints (IMPLEMENTED - Phase 4)
# =============================================================================


@router.get("/constraints", response_model=list[Constraint])
async def list_constraints(
    symbol: str | None = Query(
        default=None,
        description="Filter by applicable symbol",
    ),
    active_only: bool = Query(
        default=False,
        description="Only return active constraints (requires hypothesis status check)",
    ),
) -> list[Constraint]:
    """List all constraints.

    Returns all registered constraints with their configuration.
    Optionally filter by symbol or active status.

    Args:
        symbol: Optional filter by applicable symbol
        active_only: If True, only return constraints whose activation conditions are met

    Returns:
        List of Constraint objects matching the filter criteria.

    Example Response:
        [
            {
                "id": "growth_leverage_guard",
                "title": "Growth Stock Leverage Guard",
                "applies_to": {"symbols": ["NVDA", "AMD"], "strategies": ["momentum"]},
                "activation": {"requires_hypotheses_active": ["memory_demand_2027"]},
                "actions": {"risk_budget_multiplier": 1.5, "veto_downgrade": true},
                "guardrails": {"max_position_pct": 0.10},
                "priority": 50
            }
        ]
    """
    registry = get_constraint_registry()

    if symbol is not None:
        constraints = registry.filter_by_symbol(symbol)
    else:
        constraints = registry.list_all()

    if active_only:
        # Filter to only active constraints using the resolver's activation check
        resolver = get_constraint_resolver()
        constraints = [c for c in constraints if resolver._is_constraint_active(c)]

    return constraints


@router.get("/constraints/{constraint_id}", response_model=Constraint)
async def get_constraint(constraint_id: str) -> Constraint:
    """Get constraint by ID.

    Args:
        constraint_id: The unique constraint identifier

    Returns:
        The Constraint object if found.

    Raises:
        HTTPException 404: If constraint not found.

    Example Response:
        {
            "id": "growth_leverage_guard",
            "title": "Growth Stock Leverage Guard",
            "applies_to": {"symbols": ["NVDA", "AMD"], "strategies": ["momentum"]},
            "activation": {"requires_hypotheses_active": ["memory_demand_2027"]},
            "actions": {"risk_budget_multiplier": 1.5, "veto_downgrade": true},
            "guardrails": {"max_position_pct": 0.10},
            "priority": 50
        }
    """
    registry = get_constraint_registry()
    constraint = registry.get(constraint_id)

    if constraint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Constraint '{constraint_id}' not found",
        )

    return constraint


@router.get("/constraints/resolve/{symbol}", response_model=ResolvedConstraints)
async def resolve_constraints(symbol: str) -> ResolvedConstraints:
    """Get resolved constraints for a symbol.

    Returns the computed constraint effects for the specified symbol,
    with all active constraints resolved and merged.

    Args:
        symbol: The trading symbol (e.g., "AAPL")

    Returns:
        ResolvedConstraints with merged effective values.

    Example Response:
        {
            "symbol": "AAPL",
            "constraints": [...],
            "resolved_at": "2026-02-03T10:00:00Z",
            "version": "abc123",
            "effective_risk_budget_multiplier": 1.5,
            "effective_pool_bias_multiplier": 1.2,
            "effective_stop_mode": "wide",
            "veto_downgrade_active": true,
            "guardrails": {"max_position_pct": 0.10}
        }
    """
    resolver = get_constraint_resolver()
    return resolver.resolve(symbol)


# =============================================================================
# Pool Endpoints (Phase 5)
# =============================================================================


@router.get("/pool", response_model=Pool)
async def get_pool() -> Pool:
    """Get current active pool.

    Returns the current trading universe with full audit trail.
    Returns 404 if no pool has been built yet.

    Returns:
        Pool object with symbols, version, timestamp, and audit trail.

    Raises:
        HTTPException 404: If no pool has been built yet.
    """
    global _current_pool

    if _current_pool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pool has been built yet. POST /governance/pool to build one.",
        )

    return _current_pool


@router.post("/pool", response_model=Pool)
async def rebuild_pool(
    request: RebuildPoolRequest | None = None,
) -> Pool:
    """Rebuild pool with current config.

    Triggers a pool rebuild using structural filters from config and
    optional hypothesis gating rules from the request body.

    Args:
        request: Optional rebuild parameters (denylist, allowlist, bias).

    Returns:
        Rebuilt Pool object.

    Raises:
        HTTPException 400: If pool build results in empty pool.
        HTTPException 500: If pool build fails unexpectedly.
    """
    global _current_pool

    builder = get_pool_builder()

    # Load structural filters from config
    from src.governance.utils.yaml_loader import YAMLLoader

    filters = StructuralFilters()
    try:
        loader = YAMLLoader()
        filters = loader.load_file("config/filters/structural_filters.yml", StructuralFilters)
    except Exception:
        logger.warning("Could not load structural filters config, using defaults")

    # Load base universe from config
    universe = _load_base_universe()

    if not universe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Base universe is empty. Configure config/universe/base_universe.yml.",
        )

    req = request or RebuildPoolRequest()

    try:
        pool = builder.build(
            universe=universe,
            filters=filters,
            denylist_hypotheses=req.denylist_hypotheses,
            allowlist_hypotheses=req.allowlist_hypotheses,
            bias_hypotheses=req.bias_hypotheses,
            bias_multiplier=req.bias_multiplier,
        )
        _current_pool = pool
        return pool
    except EmptyPoolError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Pool build resulted in empty pool: {e}",
        ) from e


@router.get("/pool/{symbol}/audit", response_model=list[PoolAuditEntry])
async def get_symbol_audit(symbol: str) -> list[PoolAuditEntry]:
    """Get audit trail for a symbol.

    Returns the inclusion/exclusion history for a specific symbol
    in the current pool.

    Args:
        symbol: The trading symbol (e.g., "AAPL")

    Returns:
        List of PoolAuditEntry objects for the symbol.

    Raises:
        HTTPException 404: If no pool has been built yet.
    """
    global _current_pool

    if _current_pool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pool has been built yet. POST /governance/pool to build one.",
        )

    entries = [e for e in _current_pool.audit_trail if e.symbol == symbol]
    return entries


def _load_base_universe() -> list:
    """Load base universe from config/universe/base_universe.yml.

    Returns:
        List of simple objects with symbol/sector attributes.
    """
    from dataclasses import dataclass
    from pathlib import Path

    import yaml

    @dataclass
    class UniverseSymbol:
        symbol: str
        sector: str = ""
        state_owned_ratio: float = 0.0
        dividend_yield: float = 0.0
        avg_dollar_volume: float = 1_000_000.0
        market_cap: float = 1_000_000_000.0
        price: float = 100.0

    config_path = Path("config/universe/base_universe.yml")
    if not config_path.exists():
        logger.warning("Base universe config not found at %s", config_path)
        return []

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)

        if not data or "symbols" not in data:
            return []

        return [
            UniverseSymbol(
                symbol=s.get("symbol", ""),
                sector=s.get("sector", ""),
                state_owned_ratio=s.get("state_owned_ratio", 0.0),
                dividend_yield=s.get("dividend_yield", 0.0),
                avg_dollar_volume=s.get("avg_dollar_volume", 1_000_000.0),
                market_cap=s.get("market_cap", 1_000_000_000.0),
                price=s.get("price", 100.0),
            )
            for s in data["symbols"]
        ]
    except Exception:
        logger.exception("Failed to load base universe config")
        return []


# =============================================================================
# Regime Endpoints (Phase 9)
# =============================================================================


@router.get("/regime")
async def get_regime():
    """Get current regime state.

    Returns the current market regime classification.

    Returns:
        501: Not Implemented - To be completed in Phase 9

    Example Response (when implemented):
        {
            "state": "NORMAL",
            "volatility": 0.15,
            "drawdown": 0.02,
            "dispersion": 0.18,
            "detected_at": "2026-02-03T10:00:00Z",
            "thresholds": {...}
        }
    """
    raise _not_implemented(9, "Get regime state")


# =============================================================================
# Audit Endpoints (Phase 7)
# =============================================================================


@router.get("/audit")
async def query_audit():
    """Query audit logs.

    Returns governance audit events with optional filters.

    Query Parameters (when implemented):
        start_time: Filter events after this time
        end_time: Filter events before this time
        event_type: Filter by event type
        symbol: Filter by trading symbol
        constraint_id: Filter by constraint ID
        limit: Maximum records to return (default: 100, max: 1000)

    Returns:
        501: Not Implemented - To be completed in Phase 7

    Example Response (when implemented):
        [
            {
                "id": 1,
                "timestamp": "2026-02-03T10:00:00Z",
                "event_type": "constraint_activated",
                "constraint_id": "growth_leverage_guard",
                "action_details": {...}
            }
        ]
    """
    raise _not_implemented(7, "Query audit logs")


# =============================================================================
# Lint/Gate Endpoints (IMPLEMENTED - Phase 4)
# =============================================================================


@router.post(
    "/lint/alpha-path",
    response_model=LintResult,
    responses={
        200: {"description": "Lint passed", "model": LintResult},
        400: {"description": "Lint failed", "model": LintResult},
    },
)
async def run_alpha_path_lint(response: Response) -> LintResult:
    """Run alpha path lint check.

    Validates that no L0/L1 constructs (hypothesis/constraint files)
    are imported in alpha computation paths.

    Returns:
        LintResult with pass/fail status, violations, and metadata.
        200: Lint passed (no violations)
        400: Lint failed (violations found)

    Example Response:
        {
            "passed": true,
            "violations": [],
            "checked_files": 42,
            "checked_at": "2026-02-03T10:00:00Z"
        }
    """
    lint = AlphaPathLint()
    result = lint.run()

    if not result.passed:
        response.status_code = status.HTTP_400_BAD_REQUEST

    return result


@router.post(
    "/lint/constraint-allowlist",
    response_model=LintResult,
    responses={
        200: {"description": "Lint passed", "model": LintResult},
        400: {"description": "Lint failed", "model": LintResult},
    },
)
async def run_constraint_allowlist_lint(response: Response) -> LintResult:
    """Run constraint allowlist lint check.

    Validates that all constraints only use allowlisted action fields.
    This ensures constraints cannot introduce unauthorized actions.

    Returns:
        LintResult with pass/fail status, violations, and metadata.
        200: Lint passed (no violations)
        400: Lint failed (violations found)

    Example Response:
        {
            "passed": true,
            "violations": [],
            "checked_files": 12,
            "checked_at": "2026-02-03T10:00:00Z"
        }
    """
    lint = AllowlistLint()

    # Check if constraints directory exists
    if not lint.constraints_dir.exists():
        # Return success with 0 files checked if directory doesn't exist
        return LintResult(
            passed=True,
            violations=[],
            checked_files=0,
            checked_at=None,
        )

    result = lint.run()

    if not result.passed:
        response.status_code = status.HTTP_400_BAD_REQUEST

    return result


@router.post(
    "/gates/validate",
    response_model=GateResult,
    responses={
        200: {"description": "All gates passed", "model": GateResult},
        400: {"description": "One or more gates failed", "model": GateResult},
    },
)
async def run_gates(response: Response) -> GateResult:
    """Run all gate validations.

    Executes all governance gate checks:
    - hypothesis_requires_falsifiers: All hypotheses must have falsifiers
    - alpha_path_lint: No governance imports in alpha code
    - constraint_allowlist: Only allowlisted action fields

    Returns:
        GateResult with pass/fail status for all gates.
        200: All gates passed
        400: One or more gates failed

    Example Response:
        {
            "passed": true,
            "gates": [
                {
                    "gate_name": "hypothesis_requires_falsifiers",
                    "passed": true,
                    "violations": []
                },
                {
                    "gate_name": "alpha_path_lint",
                    "passed": true,
                    "violations": []
                },
                {
                    "gate_name": "constraint_allowlist",
                    "passed": true,
                    "violations": []
                }
            ]
        }
    """
    gates: list[GateCheckResult] = []

    # Gate 1: hypothesis_requires_falsifiers
    hypothesis_violations = []
    hypothesis_registry = get_hypothesis_registry()
    for hypothesis in hypothesis_registry.list_all():
        if not hypothesis.falsifiers or len(hypothesis.falsifiers) == 0:
            hypothesis_violations.append(f"Hypothesis '{hypothesis.id}' has no falsifiers defined")
    gates.append(
        GateCheckResult(
            gate_name="hypothesis_requires_falsifiers",
            passed=len(hypothesis_violations) == 0,
            violations=hypothesis_violations,
        )
    )

    # Gate 2: alpha_path_lint
    alpha_lint = AlphaPathLint()
    alpha_result = alpha_lint.run()
    gates.append(
        GateCheckResult(
            gate_name="alpha_path_lint",
            passed=alpha_result.passed,
            violations=alpha_result.violations,
        )
    )

    # Gate 3: constraint_allowlist
    allowlist_lint = AllowlistLint()
    if allowlist_lint.constraints_dir.exists():
        allowlist_result = allowlist_lint.run()
        gates.append(
            GateCheckResult(
                gate_name="constraint_allowlist",
                passed=allowlist_result.passed,
                violations=allowlist_result.violations,
            )
        )
    else:
        # Directory doesn't exist, no constraints to check
        gates.append(
            GateCheckResult(
                gate_name="constraint_allowlist",
                passed=True,
                violations=[],
            )
        )

    # Compute overall pass/fail
    all_passed = all(gate.passed for gate in gates)

    result = GateResult(passed=all_passed, gates=gates)

    if not all_passed:
        response.status_code = status.HTTP_400_BAD_REQUEST

    return result


__all__ = [
    "router",
    "get_hypothesis_registry",
    "reset_hypothesis_registry",
    "get_constraint_registry",
    "get_constraint_resolver",
    "reset_constraint_registry",
    "get_pool_builder",
    "reset_pool_builder",
]
