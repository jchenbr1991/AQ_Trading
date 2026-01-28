"""Tests for Black-Scholes Greeks calculator."""

from decimal import Decimal

from src.greeks.black_scholes import calculate_bs_greeks


class TestBlackScholesGreeks:
    """Tests for BS Greeks calculation."""

    def test_atm_call_delta_near_half(self):
        """ATM call should have delta near 0.5."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),  # 3 months
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),  # 20% IV
            is_call=True,
        )
        # ATM call delta should be between 0.5 and 0.6
        assert Decimal("0.50") <= result.delta <= Decimal("0.65")

    def test_atm_put_delta_near_negative_half(self):
        """ATM put should have delta near -0.5.

        Note: With positive risk-free rate, ATM put delta is slightly above -0.5
        due to forward price adjustment. For r=5%, T=0.25, delta is around -0.43.
        """
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=False,
        )
        # ATM put delta should be between -0.50 and -0.35 (accounting for r > 0)
        assert Decimal("-0.50") <= result.delta <= Decimal("-0.35")

    def test_deep_itm_call_delta_near_one(self):
        """Deep ITM call should have delta near 1."""
        result = calculate_bs_greeks(
            spot=Decimal("150"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta >= Decimal("0.95")

    def test_deep_otm_call_delta_near_zero(self):
        """Deep OTM call should have delta near 0."""
        result = calculate_bs_greeks(
            spot=Decimal("50"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta <= Decimal("0.05")

    def test_gamma_positive(self):
        """Gamma should always be positive."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.gamma > 0

    def test_vega_positive(self):
        """Vega should always be positive."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.vega > 0

    def test_theta_negative_for_long(self):
        """Theta should be negative (time decay)."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.theta < 0

    def test_result_has_all_greeks(self):
        """Result should contain all Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert hasattr(result, "delta")
        assert hasattr(result, "gamma")
        assert hasattr(result, "vega")
        assert hasattr(result, "theta")


class TestBlackScholesEdgeCases:
    """Tests for edge case handling in BS Greeks calculation."""

    def test_zero_time_to_expiry_returns_zeros(self):
        """Time to expiry <= 0 should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_negative_time_to_expiry_returns_zeros(self):
        """Negative time to expiry should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("-0.1"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_zero_volatility_returns_zeros(self):
        """Zero volatility should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_negative_volatility_returns_zeros(self):
        """Negative volatility should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("-0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_zero_spot_returns_zeros(self):
        """Zero spot price should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("0"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_negative_spot_returns_zeros(self):
        """Negative spot price should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("-100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_zero_strike_returns_zeros(self):
        """Zero strike price should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("0"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")

    def test_negative_strike_returns_zeros(self):
        """Negative strike price should return zeroed Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("-100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta == Decimal("0")
        assert result.gamma == Decimal("0")
        assert result.vega == Decimal("0")
        assert result.theta == Decimal("0")
