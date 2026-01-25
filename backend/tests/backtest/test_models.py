"""Tests for backtest models."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from src.backtest.models import Bar, Trade


class TestBar:
    """Tests for Bar dataclass."""

    def test_create_bar(self) -> None:
        """Create bar and verify all fields are set correctly."""
        timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        bar = Bar(
            symbol="AAPL",
            timestamp=timestamp,
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        assert bar.symbol == "AAPL"
        assert bar.timestamp == timestamp
        assert bar.open == Decimal("185.50")
        assert bar.high == Decimal("187.25")
        assert bar.low == Decimal("184.00")
        assert bar.close == Decimal("186.75")
        assert bar.volume == 50_000_000
        assert bar.interval == "1d"  # default value

    def test_bar_is_frozen(self) -> None:
        """Verify Bar is immutable - raises AttributeError when modifying."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        with pytest.raises(AttributeError):
            bar.symbol = "MSFT"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            bar.close = Decimal("200.00")  # type: ignore[misc]

    def test_bar_requires_timezone_aware_timestamp(self) -> None:
        """Verify timestamp has tzinfo set (not None).

        Timezone-aware timestamps are required to avoid ambiguity in
        backtesting across different market sessions and data sources.
        """
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        # Timestamp must be timezone-aware
        assert bar.timestamp.tzinfo is not None


class TestTrade:
    """Tests for Trade dataclass."""

    def test_create_buy_trade(self) -> None:
        """Create buy trade, verify fill_price = gross + slippage."""
        signal_time = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        fill_time = datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc)

        trade = Trade(
            trade_id="550e8400-e29b-41d4-a716-446655440000",
            timestamp=fill_time,
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("185.50"),
            slippage=Decimal("0.05"),
            commission=Decimal("1.00"),
            signal_bar_timestamp=signal_time,
        )

        assert trade.trade_id == "550e8400-e29b-41d4-a716-446655440000"
        assert trade.timestamp == fill_time
        assert trade.symbol == "AAPL"
        assert trade.side == "buy"
        assert trade.quantity == 100
        assert trade.gross_price == Decimal("185.50")
        assert trade.slippage == Decimal("0.05")
        # For buy trades: fill_price = gross_price + slippage
        assert trade.fill_price == Decimal("185.55")
        assert trade.commission == Decimal("1.00")
        assert trade.signal_bar_timestamp == signal_time

    def test_create_sell_trade(self) -> None:
        """Create sell trade, verify fill_price = gross - slippage."""
        signal_time = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        fill_time = datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc)

        trade = Trade(
            trade_id="550e8400-e29b-41d4-a716-446655440001",
            timestamp=fill_time,
            symbol="MSFT",
            side="sell",
            quantity=50,
            gross_price=Decimal("400.00"),
            slippage=Decimal("0.10"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=signal_time,
        )

        assert trade.trade_id == "550e8400-e29b-41d4-a716-446655440001"
        assert trade.timestamp == fill_time
        assert trade.symbol == "MSFT"
        assert trade.side == "sell"
        assert trade.quantity == 50
        assert trade.gross_price == Decimal("400.00")
        assert trade.slippage == Decimal("0.10")
        # For sell trades: fill_price = gross_price - slippage
        assert trade.fill_price == Decimal("399.90")
        assert trade.commission == Decimal("0.50")
        assert trade.signal_bar_timestamp == signal_time
