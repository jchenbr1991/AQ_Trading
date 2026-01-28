"""Tests for Greeks calculator module.

Tests cover:
- PositionInfo dataclass
- RawGreeks dataclass
- convert_to_dollar_greeks function with correct formulas and sign conventions
- FutuGreeksProvider stub
- GreeksCalculator with mock provider and fallback behavior
"""

from decimal import Decimal


class TestPositionInfo:
    """Tests for PositionInfo dataclass."""

    def test_creation_with_all_fields(self):
        """PositionInfo can be created with all required fields."""
        from src.greeks.calculator import PositionInfo

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )

        assert position.position_id == 1
        assert position.symbol == "AAPL240119C00150000"
        assert position.underlying_symbol == "AAPL"
        assert position.quantity == 10
        assert position.multiplier == 100
        assert position.option_type == "call"
        assert position.strike == Decimal("150.00")
        assert position.expiry == "2024-01-19"

    def test_put_option_type(self):
        """PositionInfo can have put option_type."""
        from src.greeks.calculator import PositionInfo

        position = PositionInfo(
            position_id=2,
            symbol="TSLA240119P00200000",
            underlying_symbol="TSLA",
            quantity=-5,
            multiplier=100,
            option_type="put",
            strike=Decimal("200.00"),
            expiry="2024-01-19",
        )

        assert position.option_type == "put"
        assert position.quantity == -5

    def test_short_position_negative_quantity(self):
        """PositionInfo supports negative quantity for short positions."""
        from src.greeks.calculator import PositionInfo

        position = PositionInfo(
            position_id=3,
            symbol="SPY240119C00450000",
            underlying_symbol="SPY",
            quantity=-20,
            multiplier=100,
            option_type="call",
            strike=Decimal("450.00"),
            expiry="2024-01-19",
        )

        assert position.quantity == -20


class TestRawGreeks:
    """Tests for RawGreeks dataclass."""

    def test_creation_with_all_fields(self):
        """RawGreeks can be created with all fields."""
        from src.greeks.calculator import RawGreeks

        raw = RawGreeks(
            delta=Decimal("0.55"),
            gamma=Decimal("0.025"),
            vega=Decimal("0.35"),
            theta=Decimal("-0.05"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        assert raw.delta == Decimal("0.55")
        assert raw.gamma == Decimal("0.025")
        assert raw.vega == Decimal("0.35")
        assert raw.theta == Decimal("-0.05")
        assert raw.implied_vol == Decimal("0.25")
        assert raw.underlying_price == Decimal("150.00")

    def test_delta_range_positive(self):
        """RawGreeks can have delta from 0 to 1 for calls."""
        from src.greeks.calculator import RawGreeks

        raw = RawGreeks(
            delta=Decimal("0.95"),
            gamma=Decimal("0.01"),
            vega=Decimal("0.10"),
            theta=Decimal("-0.02"),
            implied_vol=Decimal("0.30"),
            underlying_price=Decimal("100.00"),
        )

        assert raw.delta == Decimal("0.95")

    def test_delta_range_negative(self):
        """RawGreeks can have delta from -1 to 0 for puts."""
        from src.greeks.calculator import RawGreeks

        raw = RawGreeks(
            delta=Decimal("-0.45"),
            gamma=Decimal("0.025"),
            vega=Decimal("0.35"),
            theta=Decimal("-0.05"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        assert raw.delta == Decimal("-0.45")


class TestConvertToDollarGreeks:
    """Tests for convert_to_dollar_greeks function."""

    def test_dollar_delta_formula_long_call(self):
        """dollar_delta = delta x quantity x multiplier x underlying_price.

        Long 10 calls with delta=0.5, multiplier=100, underlying=$150
        dollar_delta = 0.5 * 10 * 100 * 150 = 75000
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.dollar_delta == Decimal("75000")

    def test_dollar_delta_formula_short_call(self):
        """Short positions have negative quantity, resulting in negative dollar_delta.

        Short 5 calls with delta=0.6, multiplier=100, underlying=$200
        dollar_delta = 0.6 * (-5) * 100 * 200 = -60000
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=2,
            symbol="TSLA240119C00200000",
            underlying_symbol="TSLA",
            quantity=-5,
            multiplier=100,
            option_type="call",
            strike=Decimal("200.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.6"),
            gamma=Decimal("0.015"),
            vega=Decimal("0.40"),
            theta=Decimal("-0.06"),
            implied_vol=Decimal("0.30"),
            underlying_price=Decimal("200.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.dollar_delta == Decimal("-60000")

    def test_dollar_delta_formula_long_put(self):
        """Long put has negative delta per share.

        Long 10 puts with delta=-0.4, multiplier=100, underlying=$100
        dollar_delta = -0.4 * 10 * 100 * 100 = -40000
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=3,
            symbol="SPY240119P00400000",
            underlying_symbol="SPY",
            quantity=10,
            multiplier=100,
            option_type="put",
            strike=Decimal("400.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("-0.4"),
            gamma=Decimal("0.018"),
            vega=Decimal("0.50"),
            theta=Decimal("-0.08"),
            implied_vol=Decimal("0.20"),
            underlying_price=Decimal("100.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.dollar_delta == Decimal("-40000")

    def test_dollar_delta_formula_short_put(self):
        """Short put has positive dollar_delta (negative delta x negative quantity).

        Short 5 puts with delta=-0.5, multiplier=100, underlying=$150
        dollar_delta = -0.5 * (-5) * 100 * 150 = 37500
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=4,
            symbol="AAPL240119P00140000",
            underlying_symbol="AAPL",
            quantity=-5,
            multiplier=100,
            option_type="put",
            strike=Decimal("140.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("-0.5"),
            gamma=Decimal("0.022"),
            vega=Decimal("0.35"),
            theta=Decimal("-0.05"),
            implied_vol=Decimal("0.28"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.dollar_delta == Decimal("37500")

    def test_gamma_dollar_formula(self):
        """gamma_dollar = gamma x quantity x multiplier x underlying_price^2.

        Long 10 contracts, gamma=0.02, multiplier=100, underlying=$150
        gamma_dollar = 0.02 * 10 * 100 * 150^2 = 0.02 * 10 * 100 * 22500 = 450000
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.gamma_dollar == Decimal("450000")

    def test_gamma_pnl_1pct_formula(self):
        """gamma_pnl_1pct = 0.5 x gamma x quantity x multiplier x (0.01 x underlying_price)^2.

        Long 10 contracts, gamma=0.02, multiplier=100, underlying=$150
        gamma_pnl_1pct = 0.5 * 0.02 * 10 * 100 * (0.01 * 150)^2
                       = 0.5 * 0.02 * 10 * 100 * 1.5^2
                       = 0.5 * 0.02 * 10 * 100 * 2.25
                       = 22.5
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.gamma_pnl_1pct == Decimal("22.5")

    def test_gamma_pnl_1pct_much_smaller_than_gamma_dollar(self):
        """gamma_pnl_1pct should be approximately 5000x smaller than gamma_dollar for typical stocks.

        For a $100 stock:
        gamma_dollar = gamma * qty * mult * price^2 = gamma * qty * mult * 10000
        gamma_pnl_1pct = 0.5 * gamma * qty * mult * (0.01 * 100)^2 = 0.5 * gamma * qty * mult * 1
                       = gamma * qty * mult * 0.5

        Ratio: gamma_dollar / gamma_pnl_1pct = 10000 / 0.5 = 20000

        For $150 stock:
        gamma_dollar = gamma * qty * mult * 22500
        gamma_pnl_1pct = 0.5 * gamma * qty * mult * 2.25
        Ratio: 22500 / 1.125 = 20000
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="TEST",
            underlying_symbol="TEST",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("100.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("100.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        # gamma_dollar = 0.02 * 10 * 100 * 100^2 = 200000
        # gamma_pnl_1pct = 0.5 * 0.02 * 10 * 100 * 1 = 10
        # Ratio = 20000 (gamma_pnl_1pct is 20000x smaller)
        ratio = result.gamma_dollar / result.gamma_pnl_1pct
        assert ratio == Decimal("20000")

    def test_gamma_sign_convention_long(self):
        """Long positions have positive gamma (profit from volatility)."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.gamma_dollar > 0
        assert result.gamma_pnl_1pct > 0

    def test_gamma_sign_convention_short(self):
        """Short positions have negative gamma (hurt by volatility)."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=2,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=-10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.gamma_dollar < 0
        assert result.gamma_pnl_1pct < 0

    def test_vega_per_1pct_formula(self):
        """vega_per_1pct = vega x quantity x multiplier.

        Long 10 contracts, vega=0.30, multiplier=100
        vega_per_1pct = 0.30 * 10 * 100 = 300
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.vega_per_1pct == Decimal("300")

    def test_theta_per_day_formula(self):
        """theta_per_day = theta x quantity x multiplier.

        Long 10 contracts, theta=-0.04, multiplier=100
        theta_per_day = -0.04 * 10 * 100 = -40
        """
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.theta_per_day == Decimal("-40")

    def test_theta_sign_convention_short(self):
        """Short positions have positive theta (profit from time decay)."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=-10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        # theta = -0.04 * (-10) * 100 = 40 (positive = profit from decay)
        assert result.theta_per_day > 0

    def test_result_includes_position_info(self):
        """Result PositionGreeks includes position identification fields."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=42,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.position_id == 42
        assert result.symbol == "AAPL240119C00150000"
        assert result.underlying_symbol == "AAPL"
        assert result.quantity == 10
        assert result.multiplier == 100
        assert result.option_type == "call"
        assert result.strike == Decimal("150.00")
        assert result.expiry == "2024-01-19"
        assert result.underlying_price == Decimal("150.00")

    def test_result_includes_source(self):
        """Result PositionGreeks includes source from input."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.source == GreeksDataSource.FUTU

    def test_result_includes_model_when_provided(self):
        """Result PositionGreeks includes model when provided."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource, GreeksModel

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(
            position, raw, GreeksDataSource.MODEL, model=GreeksModel.BS
        )

        assert result.source == GreeksDataSource.MODEL
        assert result.model == GreeksModel.BS

    def test_result_valid_is_true(self):
        """Result PositionGreeks has valid=True by default."""
        from src.greeks.calculator import PositionInfo, RawGreeks, convert_to_dollar_greeks
        from src.greeks.models import GreeksDataSource

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )
        raw = RawGreeks(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.30"),
            theta=Decimal("-0.04"),
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
        )

        result = convert_to_dollar_greeks(position, raw, GreeksDataSource.FUTU)

        assert result.valid is True


class TestFutuGreeksProvider:
    """Tests for FutuGreeksProvider stub."""

    def test_source_is_futu(self):
        """FutuGreeksProvider.source returns GreeksDataSource.FUTU."""
        from src.greeks.calculator import FutuGreeksProvider
        from src.greeks.models import GreeksDataSource

        provider = FutuGreeksProvider()

        assert provider.source == GreeksDataSource.FUTU

    def test_fetch_greeks_returns_empty_dict(self):
        """FutuGreeksProvider.fetch_greeks returns empty dict (stub)."""
        from src.greeks.calculator import FutuGreeksProvider, PositionInfo

        provider = FutuGreeksProvider()
        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-01-19",
            )
        ]

        result = provider.fetch_greeks(positions)

        assert result == {}

    def test_fetch_greeks_with_empty_list(self):
        """FutuGreeksProvider.fetch_greeks handles empty list."""
        from src.greeks.calculator import FutuGreeksProvider

        provider = FutuGreeksProvider()

        result = provider.fetch_greeks([])

        assert result == {}


class TestGreeksProviderProtocol:
    """Tests for GreeksProvider protocol."""

    def test_protocol_exists(self):
        """GreeksProvider protocol exists."""
        from src.greeks.calculator import GreeksProvider

        assert hasattr(GreeksProvider, "__protocol_attrs__") or isinstance(GreeksProvider, type)

    def test_futu_provider_conforms_to_protocol(self):
        """FutuGreeksProvider conforms to GreeksProvider protocol."""
        from src.greeks.calculator import FutuGreeksProvider

        provider = FutuGreeksProvider()

        # Check that it has the required methods/properties
        assert hasattr(provider, "source")
        assert hasattr(provider, "fetch_greeks")
        assert callable(provider.fetch_greeks)


class TestGreeksCalculator:
    """Tests for GreeksCalculator class."""

    def test_creation_with_default_provider(self):
        """GreeksCalculator can be created with default provider."""
        from src.greeks.calculator import FutuGreeksProvider, GreeksCalculator

        calculator = GreeksCalculator()

        assert calculator._primary is not None
        assert isinstance(calculator._primary, FutuGreeksProvider)

    def test_creation_with_custom_primary_provider(self):
        """GreeksCalculator can be created with custom primary provider."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class MockProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.MODEL

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {}

        mock_provider = MockProvider()
        calculator = GreeksCalculator(primary_provider=mock_provider)

        assert calculator._primary is mock_provider

    def test_creation_with_fallback_provider(self):
        """GreeksCalculator can be created with fallback provider."""
        from src.greeks.calculator import FutuGreeksProvider, GreeksCalculator

        fallback = FutuGreeksProvider()
        calculator = GreeksCalculator(fallback_provider=fallback)

        assert calculator._fallback is fallback

    def test_calculate_with_mock_provider(self):
        """GreeksCalculator.calculate works with mock provider."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class MockProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {
                    1: RawGreeks(
                        delta=Decimal("0.5"),
                        gamma=Decimal("0.02"),
                        vega=Decimal("0.30"),
                        theta=Decimal("-0.04"),
                        implied_vol=Decimal("0.25"),
                        underlying_price=Decimal("150.00"),
                    )
                }

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-01-19",
            )
        ]

        calculator = GreeksCalculator(primary_provider=MockProvider())
        results = calculator.calculate(positions)

        assert len(results) == 1
        assert results[0].position_id == 1
        assert results[0].dollar_delta == Decimal("75000")
        assert results[0].valid is True

    def test_calculate_marks_positions_without_greeks_as_invalid(self):
        """Positions without Greeks from any provider are marked invalid."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class EmptyProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {}  # Returns nothing

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-01-19",
            )
        ]

        calculator = GreeksCalculator(primary_provider=EmptyProvider())
        results = calculator.calculate(positions)

        assert len(results) == 1
        assert results[0].position_id == 1
        assert results[0].valid is False

    def test_calculate_fallback_when_primary_fails(self):
        """Calculator uses fallback provider when primary doesn't return Greeks."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class EmptyPrimary:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {}

        class FallbackProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.MODEL

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {
                    1: RawGreeks(
                        delta=Decimal("0.45"),
                        gamma=Decimal("0.018"),
                        vega=Decimal("0.28"),
                        theta=Decimal("-0.035"),
                        implied_vol=Decimal("0.22"),
                        underlying_price=Decimal("150.00"),
                    )
                }

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-01-19",
            )
        ]

        calculator = GreeksCalculator(
            primary_provider=EmptyPrimary(),
            fallback_provider=FallbackProvider(),
        )
        results = calculator.calculate(positions)

        assert len(results) == 1
        assert results[0].valid is True
        assert results[0].source == GreeksDataSource.MODEL
        # delta * qty * mult * price = 0.45 * 10 * 100 * 150 = 67500
        assert results[0].dollar_delta == Decimal("67500")

    def test_calculate_partial_primary_with_fallback(self):
        """Primary returns some positions, fallback handles the rest."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class PartialPrimary:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                # Only returns position 1, not position 2
                return {
                    1: RawGreeks(
                        delta=Decimal("0.5"),
                        gamma=Decimal("0.02"),
                        vega=Decimal("0.30"),
                        theta=Decimal("-0.04"),
                        implied_vol=Decimal("0.25"),
                        underlying_price=Decimal("150.00"),
                    )
                }

        class FallbackProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.MODEL

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                # Returns for position 2
                return {
                    2: RawGreeks(
                        delta=Decimal("0.6"),
                        gamma=Decimal("0.015"),
                        vega=Decimal("0.40"),
                        theta=Decimal("-0.06"),
                        implied_vol=Decimal("0.30"),
                        underlying_price=Decimal("200.00"),
                    )
                }

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-01-19",
            ),
            PositionInfo(
                position_id=2,
                symbol="TSLA240119C00200000",
                underlying_symbol="TSLA",
                quantity=5,
                multiplier=100,
                option_type="call",
                strike=Decimal("200.00"),
                expiry="2024-01-19",
            ),
        ]

        calculator = GreeksCalculator(
            primary_provider=PartialPrimary(),
            fallback_provider=FallbackProvider(),
        )
        results = calculator.calculate(positions)

        assert len(results) == 2

        # Position 1 from primary
        pos1 = next(r for r in results if r.position_id == 1)
        assert pos1.valid is True
        assert pos1.source == GreeksDataSource.FUTU

        # Position 2 from fallback
        pos2 = next(r for r in results if r.position_id == 2)
        assert pos2.valid is True
        assert pos2.source == GreeksDataSource.MODEL

    def test_calculate_empty_positions_list(self):
        """GreeksCalculator.calculate handles empty list."""
        from src.greeks.calculator import GreeksCalculator

        calculator = GreeksCalculator()
        results = calculator.calculate([])

        assert results == []

    def test_calculate_single_position(self):
        """GreeksCalculator.calculate_single works for single position."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class MockProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {
                    1: RawGreeks(
                        delta=Decimal("0.5"),
                        gamma=Decimal("0.02"),
                        vega=Decimal("0.30"),
                        theta=Decimal("-0.04"),
                        implied_vol=Decimal("0.25"),
                        underlying_price=Decimal("150.00"),
                    )
                }

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )

        calculator = GreeksCalculator(primary_provider=MockProvider())
        result = calculator.calculate_single(position)

        assert result.position_id == 1
        assert result.valid is True
        assert result.dollar_delta == Decimal("75000")

    def test_calculate_single_invalid_position(self):
        """GreeksCalculator.calculate_single returns invalid result when no Greeks available."""
        from src.greeks.calculator import GreeksCalculator, PositionInfo, RawGreeks
        from src.greeks.models import GreeksDataSource

        class EmptyProvider:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
                return {}

        position = PositionInfo(
            position_id=1,
            symbol="AAPL240119C00150000",
            underlying_symbol="AAPL",
            quantity=10,
            multiplier=100,
            option_type="call",
            strike=Decimal("150.00"),
            expiry="2024-01-19",
        )

        calculator = GreeksCalculator(primary_provider=EmptyProvider())
        result = calculator.calculate_single(position)

        assert result.position_id == 1
        assert result.valid is False
