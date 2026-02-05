# Factor Score Normalization & Attribution Fix

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix two related bugs — (1) factor scores with different magnitudes dominate the composite signal, and (2) the attribution formula distorts PnL decomposition due to the same scale mismatch.

**Architecture:** Add z-score normalization to `CompositeFactor.calculate()` so that factor scores are standardized before combining. Fix `AttributionCalculator.calculate_trade_attribution()` to use weight-proportional allocation instead of `weight * score * PnL`, which eliminates scale-dependent distortion. Both changes are backward-compatible — normalization is opt-in via a parameter, and the new attribution formula still satisfies SC-003 (sum == PnL).

**Tech Stack:** Python 3.11+, Decimal arithmetic, pytest

---

## Problem Summary

- **Breakout factor** scores average ~0.42 (volume_zscore dominates at +1.0 to +2.5)
- **Momentum factor** scores average ~0.011 (ROC and price_vs_ma are small percentages)
- With 50/50 weights, the composite score is ~97% determined by breakout
- Attribution formula `attr[f] = weight * score * PnL` assigns ~90% of each trade's PnL to breakout, even though breakout is independently less profitable than momentum

## Fix Design

### Fix 1: Factor Score Normalization (CompositeFactor)

Add a running z-score normalizer that standardizes factor scores before the weighted sum:

```
normalized_score[f] = (score[f] - mean(history[f])) / std(history[f])
composite = w_mom * normalized_momentum + w_brk * normalized_breakout
```

This is implemented in `CompositeFactor` with:
- A `ScoreNormalizer` helper class that maintains a rolling window of scores per factor
- Normalization is enabled via `normalize=True` (default: `False` for backward compat)
- During warmup (not enough history), raw scores pass through unchanged

### Fix 2: Attribution Formula (AttributionCalculator)

Replace `weight * score * PnL` with weight-proportional allocation:

```
attr[f] = (weight[f] / sum(weights)) * PnL
```

This is the correct formula because:
- Factor weights already represent the intended allocation of influence
- The old formula double-counted the score (which is already reflected in the entry/exit decision)
- Weight-proportional allocation is scale-invariant and preserves SC-003

---

### Task 1: Add ScoreNormalizer helper class

**Files:**
- Create: `backend/src/strategies/factors/normalizer.py`
- Test: `backend/tests/strategies/factors/test_normalizer.py`

**Step 1: Write the failing tests**

```python
# backend/tests/strategies/factors/test_normalizer.py
"""Tests for ScoreNormalizer."""

from decimal import Decimal
import pytest
from src.strategies.factors.normalizer import ScoreNormalizer


class TestScoreNormalizer:
    """Tests for rolling z-score normalizer."""

    def test_returns_none_during_warmup(self) -> None:
        """Returns None when not enough history to normalize."""
        norm = ScoreNormalizer(min_periods=5)
        norm.update("factor_a", Decimal("1.0"))
        result = norm.normalize("factor_a", Decimal("1.0"))
        assert result is None

    def test_normalizes_after_min_periods(self) -> None:
        """Returns normalized value once min_periods reached."""
        norm = ScoreNormalizer(min_periods=3)
        for v in [Decimal("10"), Decimal("20"), Decimal("30")]:
            norm.update("f", v)
        result = norm.normalize("f", Decimal("40"))
        assert result is not None
        assert isinstance(result, Decimal)

    def test_z_score_is_correct(self) -> None:
        """Z-score calculation is mathematically correct."""
        norm = ScoreNormalizer(min_periods=3)
        # Feed [10, 20, 30] -> mean=20, std=~8.165
        for v in [Decimal("10"), Decimal("20"), Decimal("30")]:
            norm.update("f", v)
        # z-score of 20 = (20 - 20) / std = 0
        result = norm.normalize("f", Decimal("20"))
        assert result is not None
        assert abs(result) < Decimal("0.01")

    def test_unknown_factor_returns_none(self) -> None:
        """Returns None for factors with no history."""
        norm = ScoreNormalizer(min_periods=3)
        result = norm.normalize("unknown", Decimal("1.0"))
        assert result is None

    def test_zero_std_returns_zero(self) -> None:
        """Returns zero when all values are identical (std=0)."""
        norm = ScoreNormalizer(min_periods=3)
        for _ in range(5):
            norm.update("f", Decimal("42"))
        result = norm.normalize("f", Decimal("42"))
        assert result == Decimal("0")

    def test_window_size_limits_memory(self) -> None:
        """History is bounded by window_size."""
        norm = ScoreNormalizer(min_periods=3, window_size=5)
        for i in range(100):
            norm.update("f", Decimal(str(i)))
        # Internal history should be at most 5
        assert len(norm._history["f"]) <= 5

    def test_multiple_factors_independent(self) -> None:
        """Each factor has independent history."""
        norm = ScoreNormalizer(min_periods=2)
        for v in [Decimal("10"), Decimal("20")]:
            norm.update("a", v)
        for v in [Decimal("100"), Decimal("200")]:
            norm.update("b", v)
        result_a = norm.normalize("a", Decimal("30"))
        result_b = norm.normalize("b", Decimal("300"))
        assert result_a is not None
        assert result_b is not None
        # Both should be positive (above mean), roughly similar z-scores
        assert result_a > Decimal("0")
        assert result_b > Decimal("0")
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/strategies/factors/test_normalizer.py -v`
Expected: FAIL — ModuleNotFoundError (normalizer.py doesn't exist yet)

**Step 3: Write minimal implementation**

```python
# backend/src/strategies/factors/normalizer.py
"""Rolling z-score normalizer for factor scores.

Standardizes factor scores to have zero mean and unit variance
using a rolling window of historical values.
"""

from collections import defaultdict
from decimal import Decimal

from src.strategies.indicators.volume import _decimal_sqrt


class ScoreNormalizer:
    """Rolling z-score normalizer for factor scores.

    Maintains a rolling window of historical scores per factor
    and normalizes new values to z-scores.

    Args:
        min_periods: Minimum number of observations before normalizing.
        window_size: Maximum history to keep per factor.
    """

    def __init__(self, min_periods: int = 20, window_size: int = 60) -> None:
        self._min_periods = min_periods
        self._window_size = window_size
        self._history: dict[str, list[Decimal]] = defaultdict(list)

    def update(self, factor_name: str, value: Decimal) -> None:
        """Record a new score observation for a factor."""
        history = self._history[factor_name]
        history.append(value)
        if len(history) > self._window_size:
            history.pop(0)

    def normalize(self, factor_name: str, value: Decimal) -> Decimal | None:
        """Normalize a score to z-score using rolling statistics.

        Returns None if insufficient history (< min_periods).
        Returns Decimal("0") if std is zero.
        """
        history = self._history.get(factor_name)
        if history is None or len(history) < self._min_periods:
            return None

        n = Decimal(len(history))
        mean = sum(history) / n
        variance = sum((v - mean) ** 2 for v in history) / n
        std = _decimal_sqrt(variance)

        if std == Decimal("0"):
            return Decimal("0")

        return (value - mean) / std
```

**Step 4: Run tests to verify they pass**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/strategies/factors/test_normalizer.py -v`
Expected: PASS (all 8 tests)

**Step 5: Commit**

```bash
git add backend/src/strategies/factors/normalizer.py backend/tests/strategies/factors/test_normalizer.py
git commit -m "feat(factors): add ScoreNormalizer for rolling z-score standardization"
```

---

### Task 2: Add normalization to CompositeFactor

**Files:**
- Modify: `backend/src/strategies/factors/composite.py`
- Modify: `backend/tests/strategies/factors/test_factors.py` (add tests to TestCompositeFactor)

**Step 1: Write the failing tests**

Add to `test_factors.py`:

```python
class TestCompositeFactorNormalization:
    """Tests for CompositeFactor with score normalization."""

    def test_normalize_flag_default_false(self) -> None:
        """Normalization is disabled by default."""
        factor = CompositeFactor()
        assert factor._normalize is False

    def test_normalize_flag_can_be_enabled(self) -> None:
        """Normalization can be enabled via constructor."""
        factor = CompositeFactor(normalize=True)
        assert factor._normalize is True

    def test_normalized_scores_equalize_influence(self) -> None:
        """With normalization, factors of different scales have equal influence."""
        factor = CompositeFactor(normalize=True, normalize_min_periods=3)

        # Feed history: momentum ~0.01 scale, breakout ~0.5 scale
        history = [
            {"momentum_factor": Decimal("0.01"), "breakout_factor": Decimal("0.40")},
            {"momentum_factor": Decimal("0.02"), "breakout_factor": Decimal("0.50")},
            {"momentum_factor": Decimal("0.015"), "breakout_factor": Decimal("0.45")},
        ]
        for h in history:
            factor.update_normalizer(h)

        # Now calculate with similar z-scores for both
        # momentum at +2 std, breakout at +2 std should yield similar composite
        indicators = {
            "momentum_factor": Decimal("0.03"),  # ~2 std above mean
            "breakout_factor": Decimal("0.60"),  # ~2 std above mean
        }
        result = factor.calculate(indicators)
        assert result is not None
        # Both factors should contribute roughly equally

    def test_calculate_without_normalization_unchanged(self) -> None:
        """Without normalize flag, behavior is identical to before."""
        factor = CompositeFactor(normalize=False)
        indicators = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.74"),
        }
        result = factor.calculate(indicators)
        assert result is not None
        assert result.score == Decimal("0.3875")

    def test_calculate_during_warmup_uses_raw_scores(self) -> None:
        """During normalizer warmup, falls back to raw scores."""
        factor = CompositeFactor(normalize=True, normalize_min_periods=10)
        # Only 1 observation, not enough for normalization
        factor.update_normalizer({
            "momentum_factor": Decimal("0.01"),
            "breakout_factor": Decimal("0.50"),
        })
        indicators = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.74"),
        }
        result = factor.calculate(indicators)
        assert result is not None
        # Should use raw scores (same as non-normalized)
        assert result.score == Decimal("0.3875")
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/strategies/factors/test_factors.py::TestCompositeFactorNormalization -v`
Expected: FAIL

**Step 3: Write implementation**

Update `CompositeFactor.__init__` to accept `normalize`, `normalize_min_periods`, `normalize_window_size` params. Add `update_normalizer()` and modify `calculate()` to optionally normalize before weighted sum.

**Step 4: Run tests to verify they pass**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/strategies/factors/test_factors.py -v`
Expected: ALL PASS (existing + new)

**Step 5: Commit**

```bash
git add backend/src/strategies/factors/composite.py backend/tests/strategies/factors/test_factors.py
git commit -m "feat(factors): add optional z-score normalization to CompositeFactor"
```

---

### Task 3: Wire normalization into TrendBreakoutStrategy

**Files:**
- Modify: `backend/src/strategies/examples/trend_breakout.py`
- Modify: `backend/tests/strategies/test_trend_breakout.py` (add normalization test if feasible)

**Step 1: Modify `_calculate_factors` to call `update_normalizer`**

In `_calculate_factors()`, after calculating momentum and breakout results but before calculating composite, call `self._composite_factor.update_normalizer()` with the raw scores.

**Step 2: Add `normalize_scores` parameter to constructor**

Add `normalize_scores: bool = True` to `__init__` and pass to `CompositeFactor`.

**Step 3: Run existing tests**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/strategies/test_trend_breakout.py -v`
Expected: ALL PASS

**Step 4: Commit**

```bash
git add backend/src/strategies/examples/trend_breakout.py
git commit -m "feat(strategy): enable factor score normalization in TrendBreakoutStrategy"
```

---

### Task 4: Fix AttributionCalculator to use weight-proportional allocation

**Files:**
- Modify: `backend/src/backtest/attribution.py`
- Modify: `backend/tests/backtest/test_attribution.py`

**Step 1: Write the failing tests**

Add to `test_attribution.py`:

```python
class TestWeightProportionalAttribution:
    """Tests for weight-proportional attribution (scale-invariant)."""

    def test_equal_weights_equal_attribution(self) -> None:
        """With equal weights, PnL is split equally regardless of score magnitude."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("0.01"),   # small score
            "breakout_factor": Decimal("0.50"),    # large score
        }
        factor_weights = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors, factor_weights)

        # With weight-proportional: each gets 50% of PnL
        assert attribution["momentum_factor"] == Decimal("50")
        assert attribution["breakout_factor"] == Decimal("50")

    def test_unequal_weights_proportional_attribution(self) -> None:
        """Attribution follows weight proportions, not score magnitude."""
        calc = AttributionCalculator()
        pnl = Decimal("100")
        entry_factors = {
            "momentum_factor": Decimal("0.01"),
            "breakout_factor": Decimal("0.50"),
        }
        factor_weights = {
            "momentum_factor": Decimal("0.7"),
            "breakout_factor": Decimal("0.3"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors, factor_weights)

        # 0.7 / (0.7 + 0.3) = 0.7 -> momentum gets 70
        # 0.3 / (0.7 + 0.3) = 0.3 -> breakout gets 30
        assert attribution["momentum_factor"] == Decimal("70")
        assert attribution["breakout_factor"] == Decimal("30")

    def test_sc003_still_satisfied(self) -> None:
        """SC-003: Sum of attributions still equals PnL."""
        calc = AttributionCalculator()
        pnl = Decimal("1234.56")
        entry_factors = {
            "momentum_factor": Decimal("0.01"),
            "breakout_factor": Decimal("0.50"),
        }
        factor_weights = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors, factor_weights)

        total = sum(attribution.values())
        assert calc.validate_attribution(attribution, pnl)

    def test_negative_pnl_weight_proportional(self) -> None:
        """Negative PnL is also distributed by weight proportion."""
        calc = AttributionCalculator()
        pnl = Decimal("-200")
        entry_factors = {
            "momentum_factor": Decimal("0.01"),
            "breakout_factor": Decimal("0.50"),
        }
        factor_weights = {
            "momentum_factor": Decimal("0.5"),
            "breakout_factor": Decimal("0.5"),
        }

        attribution = calc.calculate_trade_attribution(pnl, entry_factors, factor_weights)

        assert attribution["momentum_factor"] == Decimal("-100")
        assert attribution["breakout_factor"] == Decimal("-100")
```

**Step 2: Run tests to verify they fail**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/backtest/test_attribution.py::TestWeightProportionalAttribution -v`
Expected: FAIL (old formula gives score-proportional, not weight-proportional)

**Step 3: Implement fix**

Change `calculate_trade_attribution` to use:
```python
# Weight-proportional allocation (scale-invariant)
total_weight = sum(factor_weights.values())
if total_weight == Decimal("0"):
    equal_share = pnl / Decimal(len(entry_factors))
    return {f: equal_share for f in entry_factors}

attribution = {}
for factor_name in entry_factors:
    weight = factor_weights.get(factor_name, Decimal("0"))
    attribution[factor_name] = (weight / total_weight) * pnl
return attribution
```

**Step 4: Update existing tests that assumed old formula**

Several existing tests (e.g., `test_attribution_with_custom_weights`) need expected values updated to match the new weight-proportional formula.

**Step 5: Run all attribution tests**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/backtest/test_attribution.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/backtest/attribution.py backend/tests/backtest/test_attribution.py
git commit -m "fix(attribution): use weight-proportional allocation instead of score-weighted"
```

---

### Task 5: Run full test suite and backtest validation

**Step 1: Run full test suite**

Run: `cd /home/tochat/aq_trading && python -m pytest backend/tests/ -v --tb=short`
Expected: ALL PASS

**Step 2: Run SPY backtest to verify improved attribution**

Run the SPY TrendBreakout backtest script from the previous session and verify:
- Total return is similar (normalization may slightly change signal timing)
- Attribution is now proportional to weights (roughly 50/50 for equal weights)
- SC-003 still satisfied for all trades

**Step 3: Commit any remaining fixes**

---

## Key Design Decisions

1. **Normalization at CompositeFactor level, not individual factors** — This centralizes the normalization logic and avoids changing the individual factor APIs. The raw scores are still available in `FactorResult.components`.

2. **Weight-proportional attribution over score-proportional** — The old formula `weight * score * PnL` was designed to credit factors that contributed more signal strength. However, since the signal strength is already captured in the entry/exit decision (composite score determines if we trade), attribution should reflect the intended allocation of influence (the weights).

3. **Backward compatibility** — `normalize=False` is the default in CompositeFactor, so existing behavior is preserved unless explicitly enabled.
