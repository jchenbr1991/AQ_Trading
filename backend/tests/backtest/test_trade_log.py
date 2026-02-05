"""Tests for complete trade log verification (FR-025).

Verifies that trade records include:
- timestamp
- prices (entry/exit)
- quantities
- factor scores at entry/exit
- attribution data

See specs/002-minimal-mvp-trading/data-model.md for Trade model specification.
"""

from datetime import datetime, timezone
from decimal import Decimal

from src.backtest.models import Trade


class TestTradeLogCompleteness:
    """Tests for FR-025: Complete trade log requirements."""

    def test_trade_has_timestamp(self) -> None:
        """Trade record must include timestamp (fill time)."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.timestamp is not None
        assert isinstance(trade.timestamp, datetime)
        assert trade.timestamp.tzinfo is not None  # Must be timezone-aware

    def test_trade_has_signal_bar_timestamp(self) -> None:
        """Trade record must include signal_bar_timestamp (when signal was generated)."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.signal_bar_timestamp is not None
        assert isinstance(trade.signal_bar_timestamp, datetime)
        # Signal must be before trade execution
        assert trade.signal_bar_timestamp < trade.timestamp

    def test_trade_has_prices(self) -> None:
        """Trade record must include prices (gross_price, fill_price, slippage)."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.gross_price is not None
        assert isinstance(trade.gross_price, Decimal)
        assert trade.fill_price is not None
        assert isinstance(trade.fill_price, Decimal)
        assert trade.slippage is not None
        assert isinstance(trade.slippage, Decimal)

    def test_trade_fill_price_buy_includes_slippage(self) -> None:
        """For buy trades, fill_price = gross_price + slippage."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        # Buy: fill_price = gross_price + slippage (pays more)
        expected_fill = Decimal("150.00") + Decimal("0.075")
        assert trade.fill_price == expected_fill

    def test_trade_fill_price_sell_includes_slippage(self) -> None:
        """For sell trades, fill_price = gross_price - slippage."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160.00"),
            slippage=Decimal("0.080"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        # Sell: fill_price = gross_price - slippage (receives less)
        expected_fill = Decimal("160.00") - Decimal("0.080")
        assert trade.fill_price == expected_fill

    def test_trade_has_quantity(self) -> None:
        """Trade record must include quantity."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.quantity is not None
        assert isinstance(trade.quantity, int)
        assert trade.quantity > 0

    def test_trade_has_entry_factors(self) -> None:
        """Trade record must include entry_factors for attribution."""
        entry_factors = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.021"),
            "composite": Decimal("0.028"),
        }
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            entry_factors=entry_factors,
        )

        assert trade.entry_factors is not None
        assert isinstance(trade.entry_factors, dict)
        assert "momentum_factor" in trade.entry_factors
        assert "breakout_factor" in trade.entry_factors
        assert "composite" in trade.entry_factors

    def test_trade_has_exit_factors(self) -> None:
        """Trade record must include exit_factors for attribution."""
        exit_factors = {
            "momentum_factor": Decimal("-0.015"),
            "breakout_factor": Decimal("-0.010"),
            "composite": Decimal("-0.025"),
        }
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160.00"),
            slippage=Decimal("0.080"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            exit_factors=exit_factors,
        )

        assert trade.exit_factors is not None
        assert isinstance(trade.exit_factors, dict)
        assert "momentum_factor" in trade.exit_factors

    def test_trade_has_attribution(self) -> None:
        """Trade record must include attribution (PnL by factor)."""
        attribution = {
            "momentum_factor": Decimal("500.00"),
            "breakout_factor": Decimal("300.00"),
        }
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160.00"),
            slippage=Decimal("0.080"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            attribution=attribution,
        )

        assert trade.attribution is not None
        assert isinstance(trade.attribution, dict)
        assert "momentum_factor" in trade.attribution
        assert "breakout_factor" in trade.attribution

    def test_trade_has_commission(self) -> None:
        """Trade record must include commission."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.commission is not None
        assert isinstance(trade.commission, Decimal)
        assert trade.commission >= Decimal("0")

    def test_trade_has_symbol(self) -> None:
        """Trade record must include symbol."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.symbol is not None
        assert isinstance(trade.symbol, str)
        assert len(trade.symbol) > 0

    def test_trade_has_side(self) -> None:
        """Trade record must include side (buy or sell)."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.side is not None
        assert trade.side in ("buy", "sell")

    def test_trade_has_trade_id(self) -> None:
        """Trade record must include trade_id (unique identifier)."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.trade_id is not None
        assert isinstance(trade.trade_id, str)
        assert len(trade.trade_id) > 0


class TestTradeLogDefaultValues:
    """Tests for default values in Trade model."""

    def test_entry_factors_default_empty(self) -> None:
        """entry_factors defaults to empty dict."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.entry_factors == {}

    def test_exit_factors_default_empty(self) -> None:
        """exit_factors defaults to empty dict."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160.00"),
            slippage=Decimal("0.080"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.exit_factors == {}

    def test_attribution_default_empty(self) -> None:
        """attribution defaults to empty dict."""
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160.00"),
            slippage=Decimal("0.080"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
        )

        assert trade.attribution == {}


class TestTradeLogFactorScores:
    """Tests for factor scores in trade log (FR-025)."""

    def test_factor_scores_are_decimal(self) -> None:
        """Factor scores must be Decimal type."""
        entry_factors = {
            "momentum_factor": Decimal("0.035"),
            "breakout_factor": Decimal("0.021"),
        }
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="buy",
            quantity=100,
            gross_price=Decimal("150.00"),
            slippage=Decimal("0.075"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            entry_factors=entry_factors,
        )

        for factor_name, factor_value in trade.entry_factors.items():
            assert isinstance(factor_value, Decimal), f"{factor_name} should be Decimal"

    def test_attribution_values_are_decimal(self) -> None:
        """Attribution values must be Decimal type."""
        attribution = {
            "momentum_factor": Decimal("500.00"),
            "breakout_factor": Decimal("300.00"),
        }
        trade = Trade(
            trade_id="test-001",
            timestamp=datetime(2024, 1, 16, 9, 30, 0, tzinfo=timezone.utc),
            symbol="AAPL",
            side="sell",
            quantity=100,
            gross_price=Decimal("160.00"),
            slippage=Decimal("0.080"),
            commission=Decimal("0.50"),
            signal_bar_timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            attribution=attribution,
        )

        for factor_name, attr_value in trade.attribution.items():
            assert isinstance(attr_value, Decimal), f"{factor_name} attribution should be Decimal"
