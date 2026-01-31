"""Greeks V2 data models.

This module defines data structures for Greeks V2 features:
- Pre-order Greeks limit checking
- Scenario shock analysis
- Dynamic limits management
- Historical Greeks queries

V1 Naming Convention:
    All Greeks fields use V1 canonical names:
    - dollar_delta: $ / $1 underlying move
    - gamma_dollar: $ / ($1)² underlying move
    - gamma_pnl_1pct: $ PnL for 1% underlying move
    - vega_per_1pct: $ / 1% IV change
    - theta_per_day: $ / trading day
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

# =============================================================================
# Pre-order Greeks Check Models (Section 2 of V2 Design)
# =============================================================================


@dataclass
class OrderLeg:
    """Single leg of a multi-leg order.

    Represents one option or stock leg within an order intent.
    Used for calculating the Greeks impact of a proposed order.

    Attributes:
        symbol: Option or stock symbol (e.g., "AAPL240119C00150000")
        side: Order side - "buy" or "sell"
        quantity: Number of contracts/shares (always positive)
        contract_type: Type of contract - "call", "put", or "stock"
        strike: Strike price (None for stock)
        expiry: Expiration date (None for stock)
        multiplier: Contract multiplier (default 100 for US options)
    """

    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    contract_type: Literal["call", "put", "stock"]
    strike: Decimal | None = None
    expiry: date | None = None
    multiplier: int = 100


@dataclass
class OrderIntent:
    """Order intent for pre-order Greeks check.

    Represents a complete order intent that may contain multiple legs
    (e.g., spreads, straddles, iron condors).

    Attributes:
        account_id: Account identifier
        strategy_id: Optional strategy identifier
        legs: List of order legs
    """

    account_id: str
    strategy_id: str | None
    legs: list[OrderLeg]


@dataclass
class GreeksCheckDetails:
    """Detailed breakdown of Greeks check results.

    Uses V1 canonical field naming for consistency:
    - dollar_delta, gamma_dollar, vega_per_1pct, theta_per_day

    Attributes:
        asof_ts: Timestamp of current Greeks data
        staleness_seconds: How stale the current data is
        current: Current portfolio Greeks (dict with V1 field names)
        impact: Greeks impact from the proposed order
        projected: current + impact (post-order Greeks)
        limits: Hard limits for each Greek
        breach_dims: List of Greeks that breach limits (e.g., ["dollar_delta"])
    """

    asof_ts: datetime
    staleness_seconds: int
    current: dict[str, Decimal]
    impact: dict[str, Decimal]
    projected: dict[str, Decimal]
    limits: dict[str, Decimal]
    breach_dims: list[str]


@dataclass
class GreeksCheckResult:
    """Result of pre-order Greeks limit check.

    Structured return value supporting audit and debugging.

    Reason codes:
        - APPROVED: Order passes all Greeks limits
        - HARD_BREACH: Order would breach hard limits
        - DATA_UNAVAILABLE: Greeks data not available (fail-closed)
        - DATA_STALE: Greeks data too old (fail-closed)

    Attributes:
        ok: Whether the order is approved
        reason_code: Structured reason code
        details: Detailed breakdown (None if data unavailable/stale)
    """

    ok: bool
    reason_code: Literal["APPROVED", "HARD_BREACH", "DATA_UNAVAILABLE", "DATA_STALE"]
    details: GreeksCheckDetails | None


@dataclass
class GreeksCheckConfig:
    """Configuration for Greeks pre-order checks.

    Attributes:
        max_staleness_seconds: Maximum age of Greeks data before considered stale
        fail_mode: How to handle data issues - "closed" blocks, "open" allows
        hard_limits: Hard limits for each Greek (uses V1 field names)
    """

    max_staleness_seconds: int = 60
    fail_mode: Literal["closed", "open"] = "closed"
    hard_limits: dict[str, Decimal] = field(
        default_factory=lambda: {
            "dollar_delta": Decimal("200000"),
            "gamma_dollar": Decimal("10000"),
            "vega_per_1pct": Decimal("40000"),
            "theta_per_day": Decimal("6000"),
        }
    )


# =============================================================================
# Scenario Shock Models (Section 3 of V2 Design)
# =============================================================================


@dataclass
class CurrentGreeks:
    """Current Greeks snapshot for scenario analysis.

    Uses V1 canonical field naming.

    Attributes:
        dollar_delta: Δ × S × multiplier, $ / $1 underlying move
        gamma_dollar: Γ × S² × multiplier, $ / ($1)²
        gamma_pnl_1pct: 0.5 × gamma_dollar × 0.0001, for scenario PnL
        vega_per_1pct: $ / 1% IV change
        theta_per_day: $ / trading day
    """

    dollar_delta: Decimal
    gamma_dollar: Decimal
    gamma_pnl_1pct: Decimal
    vega_per_1pct: Decimal
    theta_per_day: Decimal


@dataclass
class ScenarioResult:
    """Result of a single scenario shock calculation.

    Formulas (V1 canonical - no double-multiplication by S):
        - pnl_from_delta = dollar_delta × shock × sign
        - pnl_from_gamma = gamma_pnl_1pct × scale (scale = shock_pct²)
        - pnl_impact = pnl_from_delta + pnl_from_gamma
        - delta_change = gamma_dollar × shock × sign
        - new_dollar_delta = dollar_delta + delta_change

    Note: Gamma PnL term does NOT multiply by sign (always positive).

    Attributes:
        shock_pct: Shock percentage (1 = 1%)
        direction: "up" or "down"
        pnl_from_delta: First-order PnL from delta
        pnl_from_gamma: Second-order PnL from gamma (convexity)
        pnl_impact: Total PnL impact
        delta_change: Change in dollar delta
        new_dollar_delta: Projected dollar delta after shock
        breach_level: Limit breach level for projected delta
        breach_dims: List of dimensions that breach limits
    """

    shock_pct: Decimal
    direction: Literal["up", "down"]
    pnl_from_delta: Decimal
    pnl_from_gamma: Decimal
    pnl_impact: Decimal
    delta_change: Decimal
    new_dollar_delta: Decimal
    breach_level: Literal["none", "warn", "crit", "hard"]
    breach_dims: list[str]


@dataclass
class ScenarioShockResponse:
    """Response for scenario shock API.

    Attributes:
        account_id: Account identifier
        scope: "ACCOUNT" or "STRATEGY" (uppercase, V1 convention)
        scope_id: Scope identifier (None for ACCOUNT)
        asof_ts: Timestamp of current Greeks
        current: Current Greeks snapshot
        scenarios: Dict mapping scenario key ("+1%", "-2%", etc.) to result
    """

    account_id: str
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str | None
    asof_ts: datetime
    current: CurrentGreeks
    scenarios: dict[str, ScenarioResult]


# =============================================================================
# Limits Management Models (Section 4 of V2 Design)
# =============================================================================


@dataclass
class ThresholdLevels:
    """Threshold levels for a single Greek metric.

    All values are absolute (positive). Evaluation uses abs() comparison.

    Constraint: 0 < warn < crit < hard

    Attributes:
        warn: Warning threshold (80% of limit typically)
        crit: Critical threshold (100% of limit typically)
        hard: Hard limit (blocking threshold)
    """

    warn: Decimal
    crit: Decimal
    hard: Decimal

    def validate(self) -> list[str]:
        """Validate threshold ordering.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []
        if not (Decimal("0") < self.warn < self.crit < self.hard):
            errors.append("must satisfy 0 < warn < crit < hard")
        return errors


@dataclass
class GreeksLimitSet:
    """Complete set of limits for all Greeks.

    Uses V1 canonical field naming.

    Attributes:
        dollar_delta: Limits for dollar delta
        gamma_dollar: Limits for gamma dollar
        vega_per_1pct: Limits for vega per 1%
        theta_per_day: Limits for theta per day
    """

    dollar_delta: ThresholdLevels
    gamma_dollar: ThresholdLevels
    vega_per_1pct: ThresholdLevels
    theta_per_day: ThresholdLevels

    def validate(self) -> list[str]:
        """Validate all threshold levels.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []
        for field_name in ["dollar_delta", "gamma_dollar", "vega_per_1pct", "theta_per_day"]:
            levels = getattr(self, field_name)
            field_errors = levels.validate()
            for err in field_errors:
                errors.append(f"{field_name}: {err}")
        return errors


@dataclass
class GreeksLimitsRequest:
    """Request to update Greeks limits.

    Note: account_id comes from path parameter, not body.

    Attributes:
        strategy_id: Strategy ID (V2 returns 501 Not Implemented)
        limits: The new limit set
    """

    strategy_id: str | None = None
    limits: GreeksLimitSet | None = None


@dataclass
class GreeksLimitsResponse:
    """Response after updating limits.

    Attributes:
        account_id: Account identifier
        strategy_id: Strategy ID (None for account-level)
        limits: The applied limit set
        updated_at: Timestamp of update
        updated_by: User who made the update
        effective_scope: "ACCOUNT" or "STRATEGY" (uppercase)
    """

    account_id: str
    strategy_id: str | None
    limits: GreeksLimitSet
    updated_at: datetime
    updated_by: str
    effective_scope: Literal["ACCOUNT", "STRATEGY"]


# =============================================================================
# History Query Models (Section 5 of V2 Design)
# =============================================================================


@dataclass
class GreeksHistoryPoint:
    """Single point in Greeks history.

    Uses V1 canonical field naming.

    Attributes:
        ts: Timestamp of this data point
        dollar_delta: Aggregated dollar delta
        gamma_dollar: Aggregated gamma dollar
        vega_per_1pct: Aggregated vega per 1%
        theta_per_day: Aggregated theta per day
        coverage_pct: Data coverage percentage
        point_count: Number of raw points aggregated (1 for raw data)
    """

    ts: datetime
    dollar_delta: Decimal
    gamma_dollar: Decimal
    vega_per_1pct: Decimal
    theta_per_day: Decimal
    coverage_pct: Decimal
    point_count: int = 1


@dataclass
class GreeksHistoryResponse:
    """Response for historical Greeks query.

    Aggregation rules by window:
        - 1h: Raw data (~30s intervals), ~120 points
        - 4h: 1min aggregation, ~240 points
        - 1d: 5min aggregation, ~288 points
        - 7d: 1h aggregation, ~168 points

    Attributes:
        account_id: Account identifier
        scope: "ACCOUNT" or "STRATEGY" (uppercase, V1 convention)
        scope_id: Scope identifier (None for ACCOUNT)
        window: Time window requested (1h, 4h, 1d, 7d)
        interval: Aggregation interval applied
        start_ts: Start of time range
        end_ts: End of time range
        points: List of history points
    """

    account_id: str
    scope: Literal["ACCOUNT", "STRATEGY"]
    scope_id: str | None
    window: str
    interval: str
    start_ts: datetime
    end_ts: datetime
    points: list[GreeksHistoryPoint]
