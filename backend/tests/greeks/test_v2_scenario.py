"""Tests for Scenario Shock calculation.

Tests cover V2 Scenario Shock API (Section 3):
- calculate_scenario returns correct PnL from delta
- calculate_scenario returns correct PnL from gamma (no sign multiplication)
- calculate_scenario returns correct delta change
- calculate_scenario returns correct new_dollar_delta
- calculate_scenario detects breach levels
- get_scenario_shocks returns all standard scenarios
"""

from decimal import Decimal

from src.greeks.v2_models import CurrentGreeks


def _make_current_greeks(
    dollar_delta: Decimal = Decimal("50000"),
    gamma_dollar: Decimal = Decimal("2000"),
    gamma_pnl_1pct: Decimal = Decimal("100"),
    vega_per_1pct: Decimal = Decimal("15000"),
    theta_per_day: Decimal = Decimal("-2800"),
) -> CurrentGreeks:
    """Factory for CurrentGreeks."""
    return CurrentGreeks(
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
    )


class TestCalculateScenario:
    """Tests for calculate_scenario function."""

    def test_pnl_from_delta_up_shock(self):
        """PnL from delta = dollar_delta × shock × sign (+1 for up)."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(dollar_delta=Decimal("50000"))
        limits = {"dollar_delta": Decimal("200000")}

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        # pnl_from_delta = 50000 × 0.01 × 1 = 500
        assert result.pnl_from_delta == Decimal("500")

    def test_pnl_from_delta_down_shock(self):
        """PnL from delta = dollar_delta × shock × sign (-1 for down)."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(dollar_delta=Decimal("50000"))
        limits = {"dollar_delta": Decimal("200000")}

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="down",
            limits=limits,
        )

        # pnl_from_delta = 50000 × 0.01 × -1 = -500
        assert result.pnl_from_delta == Decimal("-500")

    def test_pnl_from_gamma_no_sign_multiplication(self):
        """PnL from gamma = gamma_pnl_1pct × scale (no sign, always positive)."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(gamma_pnl_1pct=Decimal("100"))
        limits = {"dollar_delta": Decimal("200000")}

        # Up 1% shock
        result_up = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )
        # pnl_from_gamma = 100 × 1² = 100
        assert result_up.pnl_from_gamma == Decimal("100")

        # Down 1% shock - SAME result, no sign
        result_down = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="down",
            limits=limits,
        )
        assert result_down.pnl_from_gamma == Decimal("100")

    def test_pnl_from_gamma_scales_quadratically(self):
        """PnL from gamma scales with shock_pct squared."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(gamma_pnl_1pct=Decimal("100"))
        limits = {"dollar_delta": Decimal("200000")}

        # 2% shock → scale = 4
        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("2"),
            direction="up",
            limits=limits,
        )
        # pnl_from_gamma = 100 × 2² = 400
        assert result.pnl_from_gamma == Decimal("400")

    def test_pnl_impact_is_sum(self):
        """pnl_impact = pnl_from_delta + pnl_from_gamma."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(
            dollar_delta=Decimal("50000"),
            gamma_pnl_1pct=Decimal("100"),
        )
        limits = {"dollar_delta": Decimal("200000")}

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        # pnl_from_delta = 500, pnl_from_gamma = 100
        assert result.pnl_impact == Decimal("600")

    def test_delta_change_calculation(self):
        """delta_change = gamma_dollar × shock × sign."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(gamma_dollar=Decimal("2000"))
        limits = {"dollar_delta": Decimal("200000")}

        result_up = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )
        # delta_change = 2000 × 0.01 × 1 = 20
        assert result_up.delta_change == Decimal("20")

        result_down = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="down",
            limits=limits,
        )
        # delta_change = 2000 × 0.01 × -1 = -20
        assert result_down.delta_change == Decimal("-20")

    def test_new_dollar_delta_calculation(self):
        """new_dollar_delta = dollar_delta + delta_change."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(
            dollar_delta=Decimal("50000"),
            gamma_dollar=Decimal("2000"),
        )
        limits = {"dollar_delta": Decimal("200000")}

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        # new_dollar_delta = 50000 + 20 = 50020
        assert result.new_dollar_delta == Decimal("50020")

    def test_breach_level_none_when_within_limits(self):
        """breach_level = 'none' when new_delta within all limits."""
        from src.greeks.scenario import calculate_scenario

        current = _make_current_greeks(dollar_delta=Decimal("50000"))
        limits = {
            "dollar_delta": Decimal("200000"),
        }

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        assert result.breach_level == "none"
        assert result.breach_dims == []

    def test_breach_level_hard_when_exceeds_limit(self):
        """breach_level = 'hard' when new_delta exceeds hard limit."""
        from src.greeks.scenario import calculate_scenario

        # Current delta near limit, shock pushes over
        current = _make_current_greeks(
            dollar_delta=Decimal("195000"),
            gamma_dollar=Decimal("100000"),  # Large gamma
        )
        limits = {
            "dollar_delta": Decimal("200000"),
        }

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        # new_delta = 195000 + 1000 = 196000... wait let me recalculate
        # delta_change = 100000 × 0.01 × 1 = 1000
        # new_delta = 195000 + 1000 = 196000 < 200000, still within
        # Need higher gamma or different setup
        # Let's use: delta=199000, gamma_dollar=200000
        # delta_change = 200000 × 0.01 = 2000
        # new_delta = 199000 + 2000 = 201000 > 200000

        current2 = _make_current_greeks(
            dollar_delta=Decimal("199000"),
            gamma_dollar=Decimal("200000"),
        )

        result2 = calculate_scenario(
            current=current2,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        assert result2.breach_level == "hard"
        assert "dollar_delta" in result2.breach_dims

    def test_example_from_design_doc(self):
        """Verify example from V2 design document (+1% shock)."""
        from src.greeks.scenario import calculate_scenario

        # From design doc section 3.4
        current = _make_current_greeks(
            dollar_delta=Decimal("50000"),
            gamma_dollar=Decimal("2000"),
            gamma_pnl_1pct=Decimal("100"),
            vega_per_1pct=Decimal("15000"),
            theta_per_day=Decimal("-2800"),
        )
        limits = {"dollar_delta": Decimal("200000")}

        result = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        # Expected from design doc:
        # pnl_from_delta = 50000 × 0.01 × 1 = 500
        # pnl_from_gamma = 100 × 1² = 100
        # pnl_impact = 500 + 100 = 600
        # delta_change = 2000 × 0.01 × 1 = 20
        # new_dollar_delta = 50000 + 20 = 50020

        assert result.pnl_from_delta == Decimal("500")
        assert result.pnl_from_gamma == Decimal("100")
        assert result.pnl_impact == Decimal("600")
        assert result.delta_change == Decimal("20")
        assert result.new_dollar_delta == Decimal("50020")


class TestGetScenarioShocks:
    """Tests for get_scenario_shocks function."""

    def test_returns_standard_scenarios(self):
        """Returns +1%, -1%, +2%, -2% scenarios by default."""
        from src.greeks.scenario import get_scenario_shocks

        current = _make_current_greeks()
        limits = {"dollar_delta": Decimal("200000")}

        result = get_scenario_shocks(
            current=current,
            limits=limits,
        )

        assert "+1%" in result
        assert "-1%" in result
        assert "+2%" in result
        assert "-2%" in result
        assert len(result) == 4

    def test_custom_shock_percentages(self):
        """Can specify custom shock percentages."""
        from src.greeks.scenario import get_scenario_shocks

        current = _make_current_greeks()
        limits = {"dollar_delta": Decimal("200000")}

        result = get_scenario_shocks(
            current=current,
            limits=limits,
            shock_pcts=[Decimal("1"), Decimal("3")],
        )

        assert "+1%" in result
        assert "-1%" in result
        assert "+3%" in result
        assert "-3%" in result
        assert "+2%" not in result

    def test_scenario_results_match_individual_calculations(self):
        """Batch results match individual calculate_scenario calls."""
        from src.greeks.scenario import calculate_scenario, get_scenario_shocks

        current = _make_current_greeks()
        limits = {"dollar_delta": Decimal("200000")}

        batch = get_scenario_shocks(current=current, limits=limits)

        # Compare with individual calculations
        individual_up_1 = calculate_scenario(
            current=current,
            shock_pct=Decimal("1"),
            direction="up",
            limits=limits,
        )

        assert batch["+1%"].pnl_impact == individual_up_1.pnl_impact
        assert batch["+1%"].new_dollar_delta == individual_up_1.new_dollar_delta
