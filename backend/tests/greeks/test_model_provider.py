"""Tests for ModelGreeksProvider."""

from decimal import Decimal
from unittest.mock import patch

from src.greeks.calculator import ModelGreeksProvider, PositionInfo, RawGreeks
from src.greeks.models import GreeksDataSource


class TestModelGreeksProvider:
    """Tests for ModelGreeksProvider."""

    def test_source_is_model(self):
        provider = ModelGreeksProvider()
        assert provider.source == GreeksDataSource.MODEL

    def test_fetch_greeks_empty_list(self):
        provider = ModelGreeksProvider()
        result = provider.fetch_greeks([])
        assert result == {}

    def test_fetch_greeks_calculates_for_positions(self):
        provider = ModelGreeksProvider(
            default_iv=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
        )

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-06-21",  # Use future date
            )
        ]

        # Mock underlying price
        with patch.object(provider, "_get_underlying_price", return_value=Decimal("150.00")):
            result = provider.fetch_greeks(positions)

        assert 1 in result
        raw = result[1]
        assert isinstance(raw, RawGreeks)
        assert raw.delta > 0  # Call should have positive delta
        assert raw.gamma > 0
        assert raw.vega > 0
        assert raw.theta < 0  # Long option has negative theta

    def test_fetch_greeks_put_has_negative_delta(self):
        provider = ModelGreeksProvider()

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119P00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="put",
                strike=Decimal("150.00"),
                expiry="2024-06-21",
            )
        ]

        with patch.object(provider, "_get_underlying_price", return_value=Decimal("150.00")):
            result = provider.fetch_greeks(positions)

        assert result[1].delta < 0  # Put should have negative delta
