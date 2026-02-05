"""Attribution calculator for PnL decomposition by factor.

Implements FR-023: Attribution = factor_weight * factor_score_at_entry * trade_pnl
Implements SC-003: Sum of attributions equals total PnL within 0.1% tolerance.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.backtest.models import Trade


class AttributionCalculator:
    """Calculate PnL attribution by factor.

    This calculator decomposes trade PnL into contributions from each factor
    based on the factor scores at entry time. The attribution is normalized
    to ensure the sum equals the total PnL (SC-003 requirement).

    The raw attribution formula is:
        attribution[f] = factor_weight[f] * entry_factors[f] * pnl

    After normalization:
        attribution[f] = attribution[f] * pnl / sum(attributions)

    This ensures sum(attribution.values()) == pnl within 0.1% tolerance.
    """

    # Tolerance for SC-003 validation (0.1% = 0.001)
    TOLERANCE = Decimal("0.001")

    def calculate_trade_attribution(
        self,
        pnl: Decimal,
        entry_factors: dict[str, Decimal],
        factor_weights: dict[str, Decimal] | None = None,
    ) -> dict[str, Decimal]:
        """Calculate attribution for a single trade.

        Implements FR-023: Attribution = factor_weight * factor_score_at_entry * pnl
        Implements SC-003: Normalize so sum equals pnl within 0.1%.

        Args:
            pnl: The realized profit/loss of the trade.
            entry_factors: Factor scores at the time of entry.
                Example: {"momentum_factor": Decimal("0.035"), "composite": Decimal("0.028")}
            factor_weights: Optional weights for each factor. If not provided,
                assumes equal weights (1/N) for N factors.

        Returns:
            Dictionary mapping factor names to their attributed PnL contribution.
            The sum of values equals pnl after normalization.
            Empty dict if no factors or pnl is zero.

        Example:
            >>> calc = AttributionCalculator()
            >>> calc.calculate_trade_attribution(
            ...     pnl=Decimal("100"),
            ...     entry_factors={"momentum": Decimal("0.5"), "breakout": Decimal("0.5")},
            ...     factor_weights={"momentum": Decimal("0.6"), "breakout": Decimal("0.4")}
            ... )
            {"momentum": Decimal("60"), "breakout": Decimal("40")}
        """
        # Handle edge cases
        if not entry_factors:
            return {}

        if pnl == Decimal("0"):
            # Zero PnL means zero attribution for all factors
            return {f: Decimal("0") for f in entry_factors}

        # Determine factor weights
        if factor_weights is None:
            # Equal weights if not provided
            num_factors = len(entry_factors)
            default_weight = Decimal("1") / Decimal(num_factors)
            factor_weights = {f: default_weight for f in entry_factors}

        # Calculate raw attribution per FR-023
        raw_attribution: dict[str, Decimal] = {}
        for factor_name, factor_score in entry_factors.items():
            weight = factor_weights.get(factor_name, Decimal("0"))
            raw_attribution[factor_name] = weight * factor_score * pnl

        # Normalize to satisfy SC-003 (sum equals pnl)
        return self._normalize_attribution(raw_attribution, pnl)

    def _normalize_attribution(
        self,
        raw_attribution: dict[str, Decimal],
        pnl: Decimal,
    ) -> dict[str, Decimal]:
        """Normalize attribution so sum equals pnl exactly.

        Implements the normalization step from data-model.md:
        If total_raw != 0:
            attribution[f] = attribution[f] * pnl / total_raw

        Args:
            raw_attribution: Unnormalized attribution values.
            pnl: Target sum (the trade's PnL).

        Returns:
            Normalized attribution where sum equals pnl.
            If raw sum is zero, distributes pnl equally among factors.
        """
        if not raw_attribution:
            return {}

        total_raw = sum(raw_attribution.values())

        if total_raw == Decimal("0"):
            # Edge case: all raw attributions are zero
            # Distribute pnl equally among factors
            num_factors = len(raw_attribution)
            equal_share = pnl / Decimal(num_factors)
            return {f: equal_share for f in raw_attribution}

        # Normalize: scale so sum equals pnl
        normalized: dict[str, Decimal] = {}
        for factor_name, raw_value in raw_attribution.items():
            normalized[factor_name] = raw_value * pnl / total_raw

        return normalized

    def calculate_summary(
        self,
        trades: list[Trade],
    ) -> dict[str, Decimal]:
        """Calculate total attribution across all trades.

        Sums the attribution from each trade to produce an overall
        summary of which factors contributed how much to total PnL.

        Args:
            trades: List of Trade objects with attribution already calculated.

        Returns:
            Dictionary mapping factor names to total attributed PnL.
            Also includes a "total" key with sum of all values.
            Empty dict if no trades or no attributions.

        Example:
            >>> calc = AttributionCalculator()
            >>> summary = calc.calculate_summary(trades)
            >>> summary
            {
                "momentum_factor": Decimal("1234.56"),
                "breakout_factor": Decimal("567.89"),
                "total": Decimal("1802.45")
            }
        """
        if not trades:
            return {}

        summary: dict[str, Decimal] = {}

        for trade in trades:
            for factor_name, attr_value in trade.attribution.items():
                if factor_name not in summary:
                    summary[factor_name] = Decimal("0")
                summary[factor_name] += attr_value

        # Add total
        if summary:
            summary["total"] = sum(summary.values())

        return summary

    def validate_attribution(
        self,
        attribution: dict[str, Decimal],
        pnl: Decimal,
    ) -> bool:
        """Validate that attribution sum equals pnl within tolerance.

        Implements SC-003 validation: sum must be within 0.1% of pnl.

        Args:
            attribution: Attribution dictionary to validate.
            pnl: Expected sum (trade's PnL).

        Returns:
            True if sum of attribution values is within 0.1% of pnl.
            True if both attribution sum and pnl are zero.
        """
        if not attribution:
            return pnl == Decimal("0")

        attr_sum = sum(attribution.values())

        if pnl == Decimal("0"):
            return attr_sum == Decimal("0")

        # Calculate relative error
        relative_error = abs(attr_sum - pnl) / abs(pnl)
        return relative_error <= self.TOLERANCE
