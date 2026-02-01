# AQ Trading AI Agents - Volatility Tests
"""Tests for the volatility module.

Tests cover:
- VIX regime classification
- Risk scaling calculations
- Drawdown scaling
"""

import pytest

from agents.tools.volatility import (
    classify_vix_regime,
    get_vix_risk_scaling,
    get_drawdown_scaling,
    calculate_risk_scaling,
)


class TestVixClassification:
    """Tests for VIX regime classification."""

    def test_none_returns_none(self):
        """None VIX value returns None."""
        assert classify_vix_regime(None) is None

    def test_low_regime(self):
        """VIX below 15 is 'low'."""
        assert classify_vix_regime(10.0) == "low"
        assert classify_vix_regime(14.9) == "low"

    def test_normal_regime(self):
        """VIX 15-20 is 'normal'."""
        assert classify_vix_regime(15.0) == "normal"
        assert classify_vix_regime(19.9) == "normal"

    def test_elevated_regime(self):
        """VIX 20-30 is 'elevated'."""
        assert classify_vix_regime(20.0) == "elevated"
        assert classify_vix_regime(29.9) == "elevated"

    def test_high_regime(self):
        """VIX 30-40 is 'high'."""
        assert classify_vix_regime(30.0) == "high"
        assert classify_vix_regime(39.9) == "high"

    def test_extreme_regime(self):
        """VIX >= 40 is 'extreme'."""
        assert classify_vix_regime(40.0) == "extreme"
        assert classify_vix_regime(80.0) == "extreme"


class TestVixRiskScaling:
    """Tests for VIX-based risk scaling."""

    def test_none_returns_one(self):
        """None VIX returns scaling of 1.0."""
        assert get_vix_risk_scaling(None) == 1.0

    def test_low_vix_full_scale(self):
        """Low VIX gets full scaling."""
        assert get_vix_risk_scaling(10.0) == 1.0

    def test_elevated_vix_reduced(self):
        """Elevated VIX reduces scaling."""
        assert get_vix_risk_scaling(25.0) == 0.5

    def test_extreme_vix_minimal(self):
        """Extreme VIX gets minimal scaling."""
        assert get_vix_risk_scaling(50.0) == 0.1


class TestDrawdownScaling:
    """Tests for drawdown-based risk scaling."""

    def test_no_drawdown_full_scale(self):
        """Zero drawdown returns 1.0."""
        assert get_drawdown_scaling(0.0) == 1.0

    def test_negative_drawdown_full_scale(self):
        """Negative drawdown (profit) returns 1.0."""
        assert get_drawdown_scaling(-5.0) == 1.0

    def test_below_first_threshold_full_scale(self):
        """Drawdown below 5% returns 1.0."""
        assert get_drawdown_scaling(3.0) == 1.0
        assert get_drawdown_scaling(4.9) == 1.0

    def test_at_five_percent(self):
        """5% drawdown returns 0.9."""
        assert get_drawdown_scaling(5.0) == 0.9

    def test_between_five_and_ten(self):
        """Drawdown 5-10% returns 0.9."""
        assert get_drawdown_scaling(7.0) == 0.9
        assert get_drawdown_scaling(9.9) == 0.9

    def test_at_ten_percent(self):
        """10% drawdown returns 0.7."""
        assert get_drawdown_scaling(10.0) == 0.7

    def test_twelve_percent(self):
        """12% drawdown (between 10-15%) returns 0.7."""
        assert get_drawdown_scaling(12.0) == 0.7

    def test_at_fifteen_percent(self):
        """15% drawdown returns 0.5."""
        assert get_drawdown_scaling(15.0) == 0.5

    def test_at_twenty_percent(self):
        """20% drawdown returns 0.25."""
        assert get_drawdown_scaling(20.0) == 0.25

    def test_beyond_max_threshold(self):
        """Beyond 20% drawdown returns 0.25."""
        assert get_drawdown_scaling(25.0) == 0.25
        assert get_drawdown_scaling(50.0) == 0.25


class TestCombinedRiskScaling:
    """Tests for combined risk scaling."""

    def test_normal_conditions(self):
        """Normal conditions return 1.0."""
        assert calculate_risk_scaling(vix=15.0, drawdown_pct=0.0) == 0.8

    def test_takes_minimum(self):
        """Combined scaling is minimum of VIX and drawdown scaling."""
        # VIX elevated (0.5) vs drawdown 8% (0.9) -> takes 0.5
        assert calculate_risk_scaling(vix=25.0, drawdown_pct=8.0) == 0.5

    def test_drawdown_dominates(self):
        """Drawdown can dominate when worse than VIX."""
        # VIX normal (0.8) vs drawdown 15% (0.5) -> takes 0.5
        assert calculate_risk_scaling(vix=18.0, drawdown_pct=15.0) == 0.5
