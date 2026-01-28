"""Greeks Aggregator for portfolio and strategy level aggregation.

This module provides the GreeksAggregator class that aggregates position-level
Greeks to account or strategy level with O(N) single-pass accumulation.

High-risk thresholds for missing positions:
    - GAMMA_HIGH_RISK_THRESHOLD: 1000 - positions with gamma above this are high-risk
    - VEGA_HIGH_RISK_THRESHOLD: 2000 - positions with vega above this are high-risk
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Literal

from src.greeks.models import AggregatedGreeks, PositionGreeks

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
