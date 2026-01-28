# backend/tests/greeks/test_futu_client.py
"""Tests for Futu Greeks client."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from src.greeks.futu_client import (
    AsyncFutuGreeksClient,
    FutuClientError,
    FutuGreeksClient,
    FutuOptionGreeks,
    SharedFutuClient,
)


class TestFutuOptionGreeks:
    """Tests for FutuOptionGreeks dataclass."""

    def test_creates_with_all_fields(self):
        """Test creating FutuOptionGreeks with all fields."""
        greeks = FutuOptionGreeks(
            code="US.AAPL240119C00150000",
            delta=Decimal("0.65"),
            gamma=Decimal("0.02"),
            vega=Decimal("0.15"),
            theta=Decimal("-0.05"),
            implied_volatility=Decimal("0.25"),
            underlying_price=Decimal("150.50"),
        )

        assert greeks.code == "US.AAPL240119C00150000"
        assert greeks.delta == Decimal("0.65")
        assert greeks.gamma == Decimal("0.02")
        assert greeks.vega == Decimal("0.15")
        assert greeks.theta == Decimal("-0.05")
        assert greeks.implied_volatility == Decimal("0.25")
        assert greeks.underlying_price == Decimal("150.50")


class TestFutuGreeksClient:
    """Tests for FutuGreeksClient."""

    def test_init_sets_host_and_port(self):
        """Test initialization sets host and port."""
        client = FutuGreeksClient(host="192.168.1.1", port=22222)
        assert client._host == "192.168.1.1"
        assert client._port == 22222
        assert client._connected is False

    def test_connect_without_moomoo_raises_error(self):
        """Test connect raises error when moomoo not installed."""
        client = FutuGreeksClient()

        with patch.dict("sys.modules", {"moomoo": None}):
            with pytest.raises(FutuClientError, match="moomoo SDK not installed"):
                client.connect()

    @patch("src.greeks.futu_client.FutuGreeksClient.connect")
    def test_context_manager_connects_and_closes(self, mock_connect):
        """Test context manager calls connect and close."""
        client = FutuGreeksClient()
        client._connected = True

        with patch.object(client, "close") as mock_close:
            with client as ctx:
                assert ctx is client
                mock_connect.assert_called_once()
            mock_close.assert_called_once()

    def test_get_option_greeks_empty_symbols_returns_empty(self):
        """Test get_option_greeks with empty list returns empty dict."""
        client = FutuGreeksClient()
        client._connected = True
        client._quote_ctx = MagicMock()

        result = client.get_option_greeks([])
        assert result == {}

    def test_get_option_greeks_not_connected_raises(self):
        """Test get_option_greeks raises when not connected."""
        client = FutuGreeksClient()

        with pytest.raises(FutuClientError, match="Not connected"):
            client.get_option_greeks(["US.AAPL240119C00150000"])

    def test_get_option_greeks_parses_response(self):
        """Test get_option_greeks parses API response correctly."""
        # Create mock moomoo module
        mock_moomoo = MagicMock()
        mock_moomoo.RET_OK = 0
        mock_moomoo.SubType = MagicMock()

        client = FutuGreeksClient()
        client._connected = True

        # Create mock quote context
        mock_ctx = MagicMock()
        client._quote_ctx = mock_ctx

        # Mock subscribe success
        mock_ctx.subscribe.return_value = (0, None)

        # Mock quote data with Greeks
        quote_data = pd.DataFrame(
            [
                {
                    "code": "US.AAPL240119C00150000",
                    "option_delta": 0.65,
                    "option_gamma": 0.02,
                    "option_vega": 0.15,
                    "option_theta": -0.05,
                    "option_implied_volatility": 0.25,
                    "price": 5.50,
                }
            ]
        )
        mock_ctx.get_stock_quote.return_value = (0, quote_data)

        # Patch the moomoo import inside the method
        with patch.dict("sys.modules", {"moomoo": mock_moomoo}):
            result = client.get_option_greeks(["US.AAPL240119C00150000"])

        assert len(result) == 1
        assert "US.AAPL240119C00150000" in result

        greeks = result["US.AAPL240119C00150000"]
        assert greeks.delta == Decimal("0.65")
        assert greeks.gamma == Decimal("0.02")
        assert greeks.vega == Decimal("0.15")
        assert greeks.theta == Decimal("-0.05")
        assert greeks.implied_volatility == Decimal("0.25")
        assert greeks.underlying_price == Decimal("5.5")

    def test_get_option_greeks_skips_missing_data(self):
        """Test get_option_greeks skips symbols with missing Greeks."""
        mock_moomoo = MagicMock()
        mock_moomoo.RET_OK = 0
        mock_moomoo.SubType = MagicMock()

        client = FutuGreeksClient()
        client._connected = True

        mock_ctx = MagicMock()
        client._quote_ctx = mock_ctx
        mock_ctx.subscribe.return_value = (0, None)

        # Quote data with missing gamma
        quote_data = pd.DataFrame(
            [
                {
                    "code": "US.AAPL240119C00150000",
                    "option_delta": 0.65,
                    "option_gamma": None,  # Missing
                    "option_vega": 0.15,
                    "option_theta": -0.05,
                    "option_implied_volatility": 0.25,
                    "price": 5.50,
                }
            ]
        )
        mock_ctx.get_stock_quote.return_value = (0, quote_data)

        with patch.dict("sys.modules", {"moomoo": mock_moomoo}):
            result = client.get_option_greeks(["US.AAPL240119C00150000"])

        assert len(result) == 0

    def test_get_underlying_price_parses_response(self):
        """Test get_underlying_price parses API response correctly."""
        mock_moomoo = MagicMock()
        mock_moomoo.RET_OK = 0
        mock_moomoo.SubType = MagicMock()

        client = FutuGreeksClient()
        client._connected = True

        mock_ctx = MagicMock()
        client._quote_ctx = mock_ctx
        mock_ctx.subscribe.return_value = (0, None)

        quote_data = pd.DataFrame(
            [
                {"code": "US.AAPL", "last_price": 150.50},
                {"code": "US.TSLA", "last_price": 250.25},
            ]
        )
        mock_ctx.get_stock_quote.return_value = (0, quote_data)

        with patch.dict("sys.modules", {"moomoo": mock_moomoo}):
            result = client.get_underlying_price(["US.AAPL", "US.TSLA"])

        assert len(result) == 2
        assert result["US.AAPL"] == Decimal("150.5")
        assert result["US.TSLA"] == Decimal("250.25")


class TestSharedFutuClient:
    """Tests for SharedFutuClient singleton pattern."""

    def setup_method(self):
        """Reset shared client before each test."""
        SharedFutuClient._instance = None

    def teardown_method(self):
        """Clean up after each test."""
        SharedFutuClient.shutdown()

    def test_configure_sets_host_and_port(self):
        """Test configure sets connection parameters."""
        SharedFutuClient.configure(host="192.168.1.1", port=22222)
        assert SharedFutuClient._host == "192.168.1.1"
        assert SharedFutuClient._port == 22222

    def test_get_instance_returns_singleton(self):
        """Test get_instance returns same instance."""
        instance1 = SharedFutuClient.get_instance()
        instance2 = SharedFutuClient.get_instance()
        assert instance1 is instance2

    def test_configure_resets_instance(self):
        """Test configure resets existing instance."""
        instance1 = SharedFutuClient.get_instance()
        SharedFutuClient.configure(host="new-host", port=33333)
        instance2 = SharedFutuClient.get_instance()
        assert instance1 is not instance2

    def test_get_option_greeks_with_connection_failure(self):
        """Test get_option_greeks returns empty on connection failure."""
        client = SharedFutuClient.get_instance()

        # Force connection failure by not having moomoo installed
        with patch.dict("sys.modules", {"moomoo": None}):
            result = client.get_option_greeks(["US.AAPL240119C00150000"])

        assert result == {}

    def test_shutdown_closes_connection(self):
        """Test shutdown closes the client connection."""
        instance = SharedFutuClient.get_instance()
        instance._client = MagicMock()

        SharedFutuClient.shutdown()

        assert SharedFutuClient._instance is None


class TestAsyncFutuGreeksClient:
    """Tests for AsyncFutuGreeksClient."""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async context manager connects and closes."""
        with patch.object(FutuGreeksClient, "connect") as mock_connect:
            with patch.object(FutuGreeksClient, "close") as mock_close:
                async with AsyncFutuGreeksClient() as client:
                    assert client is not None
                    mock_connect.assert_called_once()
                mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_option_greeks_async(self):
        """Test get_option_greeks runs in executor."""
        mock_greeks = {
            "US.AAPL": FutuOptionGreeks(
                code="US.AAPL",
                delta=Decimal("0.5"),
                gamma=Decimal("0.01"),
                vega=Decimal("0.1"),
                theta=Decimal("-0.02"),
                implied_volatility=Decimal("0.3"),
                underlying_price=Decimal("150"),
            )
        }

        client = AsyncFutuGreeksClient()
        with patch.object(client._sync_client, "get_option_greeks", return_value=mock_greeks):
            result = await client.get_option_greeks(["US.AAPL"])

        assert result == mock_greeks
