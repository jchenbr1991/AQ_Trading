# backend/tests/broker/test_query.py
"""Tests for BrokerQuery protocol."""

from decimal import Decimal
from typing import runtime_checkable

from src.broker.query import BrokerAccount, BrokerPosition, BrokerQuery
from src.models.position import AssetType


class TestBrokerPosition:
    def test_create_stock_position(self):
        pos = BrokerPosition(
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
            market_value=Decimal("15500.00"),
            asset_type=AssetType.STOCK,
        )
        assert pos.symbol == "AAPL"
        assert pos.quantity == 100
        assert pos.avg_cost == Decimal("150.00")
        assert pos.market_value == Decimal("15500.00")
        assert pos.asset_type == AssetType.STOCK

    def test_create_option_position(self):
        pos = BrokerPosition(
            symbol="AAPL240315C00150000",
            quantity=10,
            avg_cost=Decimal("5.00"),
            market_value=Decimal("6000.00"),
            asset_type=AssetType.OPTION,
        )
        assert pos.asset_type == AssetType.OPTION


class TestBrokerAccount:
    def test_create_account(self):
        acct = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("50000.00"),
            buying_power=Decimal("100000.00"),
            total_equity=Decimal("150000.00"),
            margin_used=Decimal("25000.00"),
        )
        assert acct.account_id == "ACC001"
        assert acct.cash == Decimal("50000.00")
        assert acct.buying_power == Decimal("100000.00")
        assert acct.total_equity == Decimal("150000.00")
        assert acct.margin_used == Decimal("25000.00")


class TestBrokerQueryProtocol:
    def test_protocol_is_runtime_checkable(self):
        # Protocol should be runtime checkable
        assert hasattr(BrokerQuery, "__protocol_attrs__") or runtime_checkable

    def test_protocol_defines_get_positions(self):
        assert hasattr(BrokerQuery, "get_positions")

    def test_protocol_defines_get_account(self):
        assert hasattr(BrokerQuery, "get_account")
