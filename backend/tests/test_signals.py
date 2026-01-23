# backend/tests/test_signals.py
import pytest
from datetime import datetime
from decimal import Decimal

from src.strategies.signals import Signal


class TestSignal:
    def test_signal_creation_with_defaults(self):
        signal = Signal(
            strategy_id="momentum_v1",
            symbol="AAPL",
            action="buy",
            quantity=100,
        )

        assert signal.strategy_id == "momentum_v1"
        assert signal.symbol == "AAPL"
        assert signal.action == "buy"
        assert signal.quantity == 100
        assert signal.order_type == "market"
        assert signal.limit_price is None
        assert signal.reason == ""
        assert isinstance(signal.timestamp, datetime)

    def test_signal_with_limit_order(self):
        signal = Signal(
            strategy_id="mean_rev",
            symbol="TSLA",
            action="sell",
            quantity=50,
            order_type="limit",
            limit_price=Decimal("250.00"),
            reason="Mean reversion target hit",
        )

        assert signal.order_type == "limit"
        assert signal.limit_price == Decimal("250.00")
        assert signal.reason == "Mean reversion target hit"
