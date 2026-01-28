"""Greeks Aggregator for portfolio and strategy level aggregation.

This module provides the GreeksAggregator class that aggregates position-level
Greeks to account or strategy level with O(N) single-pass accumulation.

High-risk thresholds for missing positions:
    - GAMMA_HIGH_RISK_THRESHOLD: 1000 - positions with gamma above this are high-risk
    - VEGA_HIGH_RISK_THRESHOLD: 2000 - positions with vega above this are high-risk
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from src.greeks.models import AggregatedGreeks, PositionGreeks, RiskMetric


@dataclass
class ContributorInfo:
    """Information about a position's contribution to a Greek metric.

    V1.5: Added contribution_signed for risk analysis (hedging vs directional).

    Attributes:
        position: The PositionGreeks for this contributor.
        metric: The RiskMetric used for ranking.
        rank: Position in the ranking (1 = largest contributor).
        contribution_abs: Absolute contribution value (for threshold comparison).
        contribution_signed: Signed contribution value (for hedging analysis).
            - Positive: adds to exposure
            - Negative: hedges/reduces exposure
    """

    position: PositionGreeks
    metric: RiskMetric
    rank: int
    contribution_abs: Decimal
    contribution_signed: Decimal

# High-risk thresholds for missing positions
GAMMA_HIGH_RISK_THRESHOLD: Decimal = Decimal("1000")
VEGA_HIGH_RISK_THRESHOLD: Decimal = Decimal("2000")


@dataclass
class _Accumulator:
    """Internal single-pass O(N) accumulator for Greeks aggregation.

    This class accumulates Greeks values from multiple positions in a single pass,
    tracking both aggregated values and data quality metrics.

    Attributes:
        dollar_delta: Accumulated dollar delta exposure
        gamma_dollar: Accumulated dollar gamma
        gamma_pnl_1pct: Accumulated gamma PnL for 1% move
        vega_per_1pct: Accumulated vega per 1% IV change
        theta_per_day: Accumulated theta per day
        valid_legs_count: Count of valid positions
        total_legs_count: Count of all positions
        valid_notional: Notional of valid positions
        total_notional: Notional of all positions
        missing_positions: List of invalid position IDs
        high_risk_missing_positions: List of high-risk invalid position IDs
        warning_positions: List of position IDs with quality warnings
        as_of_ts_min: Earliest timestamp among positions
        as_of_ts_max: Latest timestamp among positions
    """

    # Aggregated Greeks
    dollar_delta: Decimal = Decimal("0")
    gamma_dollar: Decimal = Decimal("0")
    gamma_pnl_1pct: Decimal = Decimal("0")
    vega_per_1pct: Decimal = Decimal("0")
    theta_per_day: Decimal = Decimal("0")

    # Coverage tracking
    valid_legs_count: int = 0
    total_legs_count: int = 0
    valid_notional: Decimal = Decimal("0")
    total_notional: Decimal = Decimal("0")

    # Missing and warning positions
    missing_positions: list[int] = field(default_factory=list)
    high_risk_missing_positions: list[int] = field(default_factory=list)
    warning_positions: list[int] = field(default_factory=list)

    # Timestamp tracking
    as_of_ts_min: datetime | None = None
    as_of_ts_max: datetime | None = None

    def add(self, pg: PositionGreeks) -> None:
        """Add a position's Greeks to the accumulator.

        Args:
            pg: The PositionGreeks to accumulate.
        """
        self.total_legs_count += 1
        self.total_notional += pg.notional

        # Update timestamp bounds
        if self.as_of_ts_min is None or pg.as_of_ts < self.as_of_ts_min:
            self.as_of_ts_min = pg.as_of_ts
        if self.as_of_ts_max is None or pg.as_of_ts > self.as_of_ts_max:
            self.as_of_ts_max = pg.as_of_ts

        # Track positions with quality warnings
        if pg.quality_warnings:
            self.warning_positions.append(pg.position_id)

        if pg.valid:
            # Accumulate Greeks for valid positions
            self.dollar_delta += pg.dollar_delta
            self.gamma_dollar += pg.gamma_dollar
            self.gamma_pnl_1pct += pg.gamma_pnl_1pct
            self.vega_per_1pct += pg.vega_per_1pct
            self.theta_per_day += pg.theta_per_day
            self.valid_legs_count += 1
            self.valid_notional += pg.notional
        else:
            # Track invalid/missing positions
            self.missing_positions.append(pg.position_id)

            # Check if high-risk (high gamma or vega)
            if (
                abs(pg.gamma_dollar) > GAMMA_HIGH_RISK_THRESHOLD
                or abs(pg.vega_per_1pct) > VEGA_HIGH_RISK_THRESHOLD
            ):
                self.high_risk_missing_positions.append(pg.position_id)


class GreeksAggregator:
    """Aggregates position-level Greeks to account or strategy level.

    This class provides methods to aggregate PositionGreeks into AggregatedGreeks
    at the account or strategy level.
    """

    def aggregate(
        self,
        positions: list[PositionGreeks],
        scope: Literal["ACCOUNT", "STRATEGY"],
        scope_id: str,
    ) -> AggregatedGreeks:
        """Aggregate positions into account or strategy level Greeks.

        Args:
            positions: List of PositionGreeks to aggregate.
            scope: Either "ACCOUNT" or "STRATEGY".
            scope_id: Identifier for the scope (account ID or strategy ID).

        Returns:
            AggregatedGreeks with accumulated values and quality metrics.
        """
        acc = _Accumulator()

        for pg in positions:
            acc.add(pg)

        # Build result
        result = AggregatedGreeks(
            scope=scope,
            scope_id=scope_id,
            strategy_id=scope_id if scope == "STRATEGY" else None,
            dollar_delta=acc.dollar_delta,
            gamma_dollar=acc.gamma_dollar,
            gamma_pnl_1pct=acc.gamma_pnl_1pct,
            vega_per_1pct=acc.vega_per_1pct,
            theta_per_day=acc.theta_per_day,
            valid_legs_count=acc.valid_legs_count,
            total_legs_count=acc.total_legs_count,
            valid_notional=acc.valid_notional,
            total_notional=acc.total_notional,
            missing_positions=acc.missing_positions,
            has_high_risk_missing_legs=len(acc.high_risk_missing_positions) > 0,
            warning_legs_count=len(acc.warning_positions),
            has_positions=acc.total_legs_count > 0,
        )

        # Set timestamps if we have positions
        if acc.as_of_ts_min is not None:
            result.as_of_ts = acc.as_of_ts_min
            result.as_of_ts_min = acc.as_of_ts_min
            result.as_of_ts_max = acc.as_of_ts_max

        return result

    def aggregate_by_strategy(
        self,
        positions: list[PositionGreeks],
        account_id: str,
    ) -> tuple[AggregatedGreeks, dict[str, AggregatedGreeks]]:
        """Aggregate positions by strategy, returning account total and per-strategy breakdown.

        Args:
            positions: List of PositionGreeks to aggregate.
            account_id: The account identifier.

        Returns:
            Tuple of (account_total, strategy_dict) where:
            - account_total: AggregatedGreeks for entire account
            - strategy_dict: Dict mapping strategy_id to AggregatedGreeks
              (positions without strategy_id go to "_unassigned_")
        """
        # Group positions by strategy_id
        positions_by_strategy: dict[str, list[PositionGreeks]] = defaultdict(list)

        for pg in positions:
            strategy_key = pg.strategy_id if pg.strategy_id is not None else "_unassigned_"
            positions_by_strategy[strategy_key].append(pg)

        # Build strategy-level aggregations
        strategy_dict: dict[str, AggregatedGreeks] = {}
        for strategy_id, strategy_positions in positions_by_strategy.items():
            strategy_dict[strategy_id] = self.aggregate(
                strategy_positions,
                scope="STRATEGY",
                scope_id=strategy_id,
            )

        # Build account-level aggregation
        account_total = self.aggregate(
            positions,
            scope="ACCOUNT",
            scope_id=account_id,
        )

        return account_total, strategy_dict

    def get_top_contributors(
        self,
        positions: list[PositionGreeks],
        metric: RiskMetric,
        top_n: int = 10,
    ) -> list[ContributorInfo]:
        """Get top N positions by absolute contribution to a metric.

        Only supports GREEK category metrics (DELTA, GAMMA, VEGA, THETA).
        Returns empty list for non-Greek metrics (IV, COVERAGE).

        V1.5: Returns ContributorInfo with both signed and absolute contribution.

        Args:
            positions: List of PositionGreeks.
            metric: The RiskMetric to rank by.
            top_n: Number of top positions to return.

        Returns:
            List of ContributorInfo sorted by absolute value descending.
            Excludes invalid positions.
        """
        # Only support Greek metrics
        if not metric.is_greek:
            return []

        # Map metric to the appropriate field
        metric_field_map = {
            RiskMetric.DELTA: "dollar_delta",
            RiskMetric.GAMMA: "gamma_dollar",
            RiskMetric.VEGA: "vega_per_1pct",
            RiskMetric.THETA: "theta_per_day",
        }

        field_name = metric_field_map.get(metric)
        if field_name is None:
            return []

        # Filter valid positions and extract (position, contribution_signed) tuples
        contributions: list[tuple[PositionGreeks, Decimal]] = []
        for pg in positions:
            if pg.valid:
                contribution = getattr(pg, field_name)
                contributions.append((pg, contribution))

        # Sort by absolute value of contribution descending
        contributions.sort(key=lambda x: abs(x[1]), reverse=True)

        # Build ContributorInfo list with ranks
        result: list[ContributorInfo] = []
        for rank, (pg, contribution_signed) in enumerate(contributions[:top_n], start=1):
            result.append(
                ContributorInfo(
                    position=pg,
                    metric=metric,
                    rank=rank,
                    contribution_abs=abs(contribution_signed),
                    contribution_signed=contribution_signed,
                )
            )

        return result
