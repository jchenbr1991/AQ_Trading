"""Tests for AssignmentHandler service.

Tests cover:
- FR-018: System handles options assignment/exercise
- ITM/OTM status calculation for calls and puts
- Assignment estimation with resulting stock positions
"""

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal
from enum import Enum
from unittest.mock import MagicMock

import pytest
from src.derivatives.assignment_handler import (
    AssignmentDirection,
    AssignmentEstimate,
    AssignmentHandler,
)
from src.models.derivative_contract import ContractType, DerivativeContract, PutCall


class TestAssignmentEstimateModel:
    """Tests for AssignmentEstimate dataclass."""

    def test_assignment_estimate_creation(self):
        """AssignmentEstimate should be created with all required fields."""
        estimate = AssignmentEstimate(
            option_symbol="AAPL240119C00150000",
            is_itm=True,
            resulting_shares=100,
            cash_impact=Decimal("-15000.00"),
            direction=AssignmentDirection.BUY,
        )
        assert estimate.option_symbol == "AAPL240119C00150000"
        assert estimate.is_itm is True
        assert estimate.resulting_shares == 100
        assert estimate.cash_impact == Decimal("-15000.00")
        assert estimate.direction == AssignmentDirection.BUY

    def test_assignment_estimate_is_frozen(self):
        """AssignmentEstimate should be immutable."""
        estimate = AssignmentEstimate(
            option_symbol="AAPL240119C00150000",
            is_itm=True,
            resulting_shares=100,
            cash_impact=Decimal("-15000.00"),
            direction=AssignmentDirection.BUY,
        )
        with pytest.raises(FrozenInstanceError):
            estimate.is_itm = False

    def test_assignment_estimate_otm_call(self):
        """AssignmentEstimate for OTM option should have zero shares and cash impact."""
        estimate = AssignmentEstimate(
            option_symbol="AAPL240119C00150000",
            is_itm=False,
            resulting_shares=0,
            cash_impact=Decimal("0.00"),
            direction=AssignmentDirection.BUY,
        )
        assert estimate.is_itm is False
        assert estimate.resulting_shares == 0
        assert estimate.cash_impact == Decimal("0.00")


class TestAssignmentDirection:
    """Tests for AssignmentDirection enum."""

    def test_direction_values(self):
        """AssignmentDirection should have BUY and SELL values."""
        assert AssignmentDirection.BUY.value == "BUY"
        assert AssignmentDirection.SELL.value == "SELL"

    def test_direction_is_enum(self):
        """AssignmentDirection should be an Enum."""
        assert issubclass(AssignmentDirection, Enum)


class TestAssignmentHandlerInit:
    """Tests for AssignmentHandler initialization."""

    def test_init_with_session(self):
        """AssignmentHandler should initialize with a session."""
        mock_session = MagicMock()
        handler = AssignmentHandler(session=mock_session)
        assert handler._session is mock_session

    def test_default_multiplier(self):
        """AssignmentHandler should default to 100 shares per contract."""
        mock_session = MagicMock()
        handler = AssignmentHandler(session=mock_session)
        assert handler._multiplier == 100

    def test_custom_multiplier(self):
        """AssignmentHandler should accept custom multiplier."""
        mock_session = MagicMock()
        handler = AssignmentHandler(session=mock_session, multiplier=10)
        assert handler._multiplier == 10


class TestCalculateItmStatus:
    """Tests for calculate_itm_status method."""

    @pytest.fixture
    def handler(self):
        """Create an AssignmentHandler with mock session."""
        mock_session = MagicMock()
        return AssignmentHandler(session=mock_session)

    def test_call_itm_when_price_above_strike(self, handler):
        """Call option should be ITM when underlying price > strike."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("155.00")

        is_itm = handler.calculate_itm_status(option, underlying_price)

        assert is_itm is True

    def test_call_otm_when_price_below_strike(self, handler):
        """Call option should be OTM when underlying price < strike."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("145.00")

        is_itm = handler.calculate_itm_status(option, underlying_price)

        assert is_itm is False

    def test_call_atm_is_not_itm(self, handler):
        """Call option should be OTM (not ITM) when underlying price = strike."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("150.00")

        is_itm = handler.calculate_itm_status(option, underlying_price)

        assert is_itm is False

    def test_put_itm_when_price_below_strike(self, handler):
        """Put option should be ITM when underlying price < strike."""
        option = DerivativeContract(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.PUT,
        )
        underlying_price = Decimal("145.00")

        is_itm = handler.calculate_itm_status(option, underlying_price)

        assert is_itm is True

    def test_put_otm_when_price_above_strike(self, handler):
        """Put option should be OTM when underlying price > strike."""
        option = DerivativeContract(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.PUT,
        )
        underlying_price = Decimal("155.00")

        is_itm = handler.calculate_itm_status(option, underlying_price)

        assert is_itm is False

    def test_put_atm_is_not_itm(self, handler):
        """Put option should be OTM (not ITM) when underlying price = strike."""
        option = DerivativeContract(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.PUT,
        )
        underlying_price = Decimal("150.00")

        is_itm = handler.calculate_itm_status(option, underlying_price)

        assert is_itm is False

    def test_raises_for_contract_without_strike(self, handler):
        """Should raise ValueError for contracts without strike price."""
        future = DerivativeContract(
            symbol="ESH24",
            underlying="ES",
            contract_type=ContractType.FUTURE,
            expiry=date.today(),
            strike=None,
            put_call=None,
        )

        with pytest.raises(ValueError, match="Option must have a strike price"):
            handler.calculate_itm_status(future, Decimal("5000.00"))

    def test_raises_for_contract_without_put_call(self, handler):
        """Should raise ValueError for contracts without put_call type."""
        option = DerivativeContract(
            symbol="AAPL240119X00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=None,
        )

        with pytest.raises(ValueError, match="Option must have a put_call type"):
            handler.calculate_itm_status(option, Decimal("155.00"))


class TestEstimateAssignment:
    """Tests for estimate_assignment method."""

    @pytest.fixture
    def handler(self):
        """Create an AssignmentHandler with mock session."""
        mock_session = MagicMock()
        return AssignmentHandler(session=mock_session)

    def test_itm_call_results_in_buy_shares(self, handler):
        """ITM call exercise should result in buying shares."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("160.00")
        quantity = 1

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.option_symbol == "AAPL240119C00150000"
        assert estimate.is_itm is True
        assert estimate.resulting_shares == 100  # 1 contract * 100 shares
        assert estimate.cash_impact == Decimal("-15000.00")  # -150 * 100
        assert estimate.direction == AssignmentDirection.BUY

    def test_itm_put_results_in_sell_shares(self, handler):
        """ITM put exercise should result in selling shares."""
        option = DerivativeContract(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.PUT,
        )
        underlying_price = Decimal("140.00")
        quantity = 1

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.option_symbol == "AAPL240119P00150000"
        assert estimate.is_itm is True
        assert estimate.resulting_shares == 100  # 1 contract * 100 shares
        assert estimate.cash_impact == Decimal("15000.00")  # +150 * 100
        assert estimate.direction == AssignmentDirection.SELL

    def test_otm_call_no_shares(self, handler):
        """OTM call should result in zero shares (expires worthless)."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("145.00")
        quantity = 1

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.is_itm is False
        assert estimate.resulting_shares == 0
        assert estimate.cash_impact == Decimal("0.00")
        assert estimate.direction == AssignmentDirection.BUY  # Direction still BUY for call

    def test_otm_put_no_shares(self, handler):
        """OTM put should result in zero shares (expires worthless)."""
        option = DerivativeContract(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.PUT,
        )
        underlying_price = Decimal("155.00")
        quantity = 1

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.is_itm is False
        assert estimate.resulting_shares == 0
        assert estimate.cash_impact == Decimal("0.00")
        assert estimate.direction == AssignmentDirection.SELL  # Direction still SELL for put

    def test_multiple_contracts(self, handler):
        """Should calculate shares for multiple contracts."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("160.00")
        quantity = 5

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.resulting_shares == 500  # 5 contracts * 100 shares
        assert estimate.cash_impact == Decimal("-75000.00")  # -150 * 500

    def test_zero_quantity(self, handler):
        """Should handle zero quantity gracefully."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("160.00")
        quantity = 0

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.resulting_shares == 0
        assert estimate.cash_impact == Decimal("0.00")

    def test_negative_quantity_raises(self, handler):
        """Should raise ValueError for negative quantity."""
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )

        with pytest.raises(ValueError, match="Quantity must be non-negative"):
            handler.estimate_assignment(option, Decimal("160.00"), -1)

    def test_custom_multiplier(self):
        """Should use custom multiplier for share calculation."""
        mock_session = MagicMock()
        handler = AssignmentHandler(session=mock_session, multiplier=10)

        option = DerivativeContract(
            symbol="MINI_AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("160.00")
        quantity = 1

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.resulting_shares == 10  # 1 contract * 10 shares
        assert estimate.cash_impact == Decimal("-1500.00")  # -150 * 10

    def test_high_strike_put_cash_impact(self, handler):
        """ITM put should calculate correct cash impact with high strike."""
        option = DerivativeContract(
            symbol="AMZN240119P00500000",
            underlying="AMZN",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("500.00"),
            put_call=PutCall.PUT,
        )
        underlying_price = Decimal("450.00")
        quantity = 2

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.is_itm is True
        assert estimate.resulting_shares == 200  # 2 contracts * 100 shares
        assert estimate.cash_impact == Decimal("100000.00")  # +500 * 200
        assert estimate.direction == AssignmentDirection.SELL

    def test_fractional_strike_price(self, handler):
        """Should handle fractional strike prices correctly."""
        option = DerivativeContract(
            symbol="AAPL240119C00152500",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("152.50"),
            put_call=PutCall.CALL,
        )
        underlying_price = Decimal("160.00")
        quantity = 1

        estimate = handler.estimate_assignment(option, underlying_price, quantity)

        assert estimate.resulting_shares == 100
        assert estimate.cash_impact == Decimal("-15250.00")  # -152.50 * 100


class TestAcceptanceCriteria:
    """Tests verifying acceptance criteria from spec.md."""

    @pytest.fixture
    def handler(self):
        """Create an AssignmentHandler with mock session."""
        mock_session = MagicMock()
        return AssignmentHandler(session=mock_session)

    def test_fr018_handles_options_assignment(self, handler):
        """FR-018: System handles options assignment/exercise.

        Verifies that the system can calculate ITM status and estimate
        the resulting position from options exercise.
        """
        # ITM Call - should be exercised
        call_option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )

        # ITM Put - should be exercised
        put_option = DerivativeContract(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.PUT,
        )

        # Price where call is ITM but put is OTM
        price = Decimal("160.00")

        call_estimate = handler.estimate_assignment(call_option, price, 1)
        put_estimate = handler.estimate_assignment(put_option, price, 1)

        # Call should be exercised (ITM)
        assert call_estimate.is_itm is True
        assert call_estimate.resulting_shares == 100
        assert call_estimate.direction == AssignmentDirection.BUY

        # Put should expire worthless (OTM)
        assert put_estimate.is_itm is False
        assert put_estimate.resulting_shares == 0

    def test_fr018_itm_otm_calculation(self, handler):
        """FR-018: Correctly calculates ITM/OTM status.

        Verifies ITM logic:
        - Call ITM when underlying_price > strike
        - Put ITM when underlying_price < strike
        """
        strike = Decimal("100.00")
        call_option = DerivativeContract(
            symbol="TEST_CALL",
            underlying="TEST",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=strike,
            put_call=PutCall.CALL,
        )
        put_option = DerivativeContract(
            symbol="TEST_PUT",
            underlying="TEST",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=strike,
            put_call=PutCall.PUT,
        )

        # Test ITM scenarios
        assert handler.calculate_itm_status(call_option, Decimal("110.00")) is True
        assert handler.calculate_itm_status(put_option, Decimal("90.00")) is True

        # Test OTM scenarios
        assert handler.calculate_itm_status(call_option, Decimal("90.00")) is False
        assert handler.calculate_itm_status(put_option, Decimal("110.00")) is False

        # Test ATM (not ITM)
        assert handler.calculate_itm_status(call_option, Decimal("100.00")) is False
        assert handler.calculate_itm_status(put_option, Decimal("100.00")) is False

    def test_fr018_uses_standard_multiplier(self, handler):
        """FR-018: Uses standard options multiplier of 100 shares per contract.

        Verifies that the default multiplier is 100 shares per contract
        as per standard options conventions.
        """
        option = DerivativeContract(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            contract_type=ContractType.OPTION,
            expiry=date.today(),
            strike=Decimal("150.00"),
            put_call=PutCall.CALL,
        )

        # 1 contract = 100 shares
        estimate_1 = handler.estimate_assignment(option, Decimal("160.00"), 1)
        assert estimate_1.resulting_shares == 100

        # 10 contracts = 1000 shares
        estimate_10 = handler.estimate_assignment(option, Decimal("160.00"), 10)
        assert estimate_10.resulting_shares == 1000
