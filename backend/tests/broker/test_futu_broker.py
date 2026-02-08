# backend/tests/broker/test_futu_broker.py
"""Tests for FutuBroker adapter — mirrors test_tiger_broker.py structure."""

import asyncio
import logging
import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from src.broker.errors import OrderCancelError, OrderSubmissionError
from src.broker.futu_broker import FUTU_STATUS_MAP, FutuBroker
from src.broker.query import BrokerAccount, BrokerPosition
from src.models.position import AssetType
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


@pytest.fixture
def broker():
    return FutuBroker(host="127.0.0.1", port=11111, trade_env="SIMULATE")


def _make_order(
    *, order_type="limit", limit_price=Decimal("150.00"), side="buy", symbol="AAPL", quantity=100
):
    return Order(
        order_id="aq-ord-001",
        broker_order_id=None,
        strategy_id="test-strat",
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        limit_price=limit_price if order_type == "limit" else None,
        status=OrderStatus.PENDING,
    )


class TestFutuBrokerConstructor:
    def test_valid_construction_simulate(self):
        fb = FutuBroker(host="127.0.0.1", port=11111, trade_env="SIMULATE")
        assert fb._host == "127.0.0.1"
        assert fb._port == 11111
        assert fb._trade_env == "SIMULATE"
        assert fb._connected is False

    def test_valid_construction_real(self):
        fb = FutuBroker(host="127.0.0.1", port=11111, trade_env="REAL")
        assert fb._trade_env == "REAL"

    def test_default_trade_env_is_simulate(self):
        fb = FutuBroker(host="127.0.0.1", port=11111)
        assert fb._trade_env == "SIMULATE"

    def test_raises_for_invalid_trade_env(self):
        with pytest.raises(ValueError, match="trade_env must be"):
            FutuBroker(host="127.0.0.1", port=11111, trade_env="DEV")

    def test_raises_for_empty_host(self):
        with pytest.raises(ValueError, match="host must be non-empty"):
            FutuBroker(host="", port=11111)

    def test_raises_for_invalid_port(self):
        with pytest.raises(ValueError, match="port must be"):
            FutuBroker(host="127.0.0.1", port=-1)

    def test_custom_account_id(self):
        fb = FutuBroker(host="127.0.0.1", port=11111, account_id="ACC001")
        assert fb._account_id == "ACC001"

    def test_unlock_password_stored(self):
        pwd = "test-unlock-val"  # noqa: S105
        fb = FutuBroker(host="127.0.0.1", port=11111, unlock_password=pwd)
        assert fb._unlock_password == pwd

    def test_unlock_password_default_empty(self):
        fb = FutuBroker(host="127.0.0.1", port=11111)
        assert fb._unlock_password == ""


class TestStatusMapping:
    def test_map_has_all_expected_statuses(self):
        expected = {
            "WAITING_SUBMIT",
            "SUBMITTING",
            "SUBMITTED",
            "FILLED_PART",
            "FILLED_ALL",
            "CANCELLED_ALL",
            "FAILED",
            "DISABLED",
            "DELETED",
        }
        assert set(FUTU_STATUS_MAP.keys()) == expected

    def test_waiting_submit(self):
        assert FUTU_STATUS_MAP["WAITING_SUBMIT"] == OrderStatus.PENDING

    def test_submitting(self):
        assert FUTU_STATUS_MAP["SUBMITTING"] == OrderStatus.PENDING

    def test_submitted(self):
        assert FUTU_STATUS_MAP["SUBMITTED"] == OrderStatus.SUBMITTED

    def test_filled_part(self):
        assert FUTU_STATUS_MAP["FILLED_PART"] == OrderStatus.PARTIAL_FILL

    def test_filled_all(self):
        assert FUTU_STATUS_MAP["FILLED_ALL"] == OrderStatus.FILLED

    def test_cancelled_all(self):
        assert FUTU_STATUS_MAP["CANCELLED_ALL"] == OrderStatus.CANCELLED

    def test_failed(self):
        assert FUTU_STATUS_MAP["FAILED"] == OrderStatus.REJECTED

    def test_disabled(self):
        assert FUTU_STATUS_MAP["DISABLED"] == OrderStatus.EXPIRED

    def test_deleted(self):
        assert FUTU_STATUS_MAP["DELETED"] == OrderStatus.EXPIRED

    def test_unknown_status_returns_pending_with_warning(self, broker, caplog):
        with caplog.at_level(logging.WARNING):
            result = broker._map_status("UNKNOWN_STATUS")
        assert result == OrderStatus.PENDING
        assert "Unmapped Futu order status" in caplog.text


class TestSubmitOrder:
    async def test_limit_order_places_correctly(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FT-12345" if k == "order_id" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.place_order = MagicMock(return_value=(0, mock_df))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            result = await broker.submit_order(_make_order(order_type="limit"))

        assert result == "FT-12345"

    async def test_market_order_uses_market_type(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FT-67890" if k == "order_id" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.place_order = MagicMock(return_value=(0, mock_df))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            result = await broker.submit_order(_make_order(order_type="market"))

        assert result == "FT-67890"
        call_kwargs = broker._trd_ctx.place_order.call_args[1]
        assert call_kwargs["order_type"] == "MARKET"

    async def test_sell_order_uses_sell_side(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FT-11111" if k == "order_id" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.place_order = MagicMock(return_value=(0, mock_df))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            await broker.submit_order(_make_order(side="sell"))

        call_kwargs = broker._trd_ctx.place_order.call_args[1]
        assert call_kwargs["trd_side"] == "SELL"

    async def test_passes_trd_env_to_place_order(self, broker):
        broker._connected = True
        broker._trd_env = "MOCK_SIMULATE"
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FT-22222" if k == "order_id" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.place_order = MagicMock(return_value=(0, mock_df))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            await broker.submit_order(_make_order())

        call_kwargs = broker._trd_ctx.place_order.call_args[1]
        assert call_kwargs["trd_env"] == "MOCK_SIMULATE"

    async def test_raises_on_futu_api_failure(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.place_order = MagicMock(return_value=(1, "API error"))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
            pytest.raises(OrderSubmissionError),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            await broker.submit_order(_make_order())

    async def test_raises_when_not_connected(self, broker):
        broker._connected = False
        with pytest.raises(OrderSubmissionError, match="Not connected"):
            await broker.submit_order(_make_order())

    async def test_stores_pending_order_mapping(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FT-55555" if k == "order_id" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.place_order = MagicMock(return_value=(0, mock_df))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            await broker.submit_order(_make_order())

        assert "FT-55555" in broker._pending_orders
        assert broker._pending_orders["FT-55555"] == "aq-ord-001"

    async def test_submit_order_round_trip_under_5s(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FT-77777" if k == "order_id" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.place_order = MagicMock(return_value=(0, mock_df))

        with (
            patch("src.broker.futu_broker.TrdSide") as mock_side,
            patch("src.broker.futu_broker.OrderType") as mock_otype,
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_side.BUY = "BUY"
            mock_side.SELL = "SELL"
            mock_otype.NORMAL = "NORMAL"
            mock_otype.MARKET = "MARKET"
            start = time.monotonic()
            await broker.submit_order(_make_order())
            elapsed = time.monotonic() - start

        assert elapsed < 5.0, f"submit_order took {elapsed:.2f}s, exceeds 5s limit"


class TestCancelOrder:
    async def test_cancel_returns_true(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.modify_order = MagicMock(return_value=(0, None))

        with (
            patch("src.broker.futu_broker.ModifyOrderOp") as mock_op,
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_op.CANCEL = "CANCEL"
            result = await broker.cancel_order("FT-12345")

        assert result is True

    async def test_cancel_uses_modify_order_with_cancel_op(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.modify_order = MagicMock(return_value=(0, None))

        with (
            patch("src.broker.futu_broker.ModifyOrderOp") as mock_op,
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_op.CANCEL = "CANCEL"
            await broker.cancel_order("FT-98765")

        call_kwargs = broker._trd_ctx.modify_order.call_args[1]
        assert call_kwargs["modify_order_op"] == "CANCEL"
        assert call_kwargs["order_id"] == "FT-98765"

    async def test_cancel_passes_trd_env(self, broker):
        broker._connected = True
        broker._trd_env = "MOCK_SIMULATE"
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.modify_order = MagicMock(return_value=(0, None))

        with (
            patch("src.broker.futu_broker.ModifyOrderOp") as mock_op,
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            mock_op.CANCEL = "CANCEL"
            await broker.cancel_order("FT-12345")

        call_kwargs = broker._trd_ctx.modify_order.call_args[1]
        assert call_kwargs["trd_env"] == "MOCK_SIMULATE"

    async def test_cancel_raises_on_failure(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.modify_order = MagicMock(return_value=(1, "Cancel failed"))

        with (
            patch("src.broker.futu_broker.ModifyOrderOp") as mock_op,
            patch("src.broker.futu_broker.RET_OK", 0),
            pytest.raises(OrderCancelError),
        ):
            mock_op.CANCEL = "CANCEL"
            await broker.cancel_order("FT-12345")


class TestGetOrderStatus:
    async def test_returns_filled(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FILLED_ALL" if k == "order_status" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.order_list_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            result = await broker.get_order_status("FT-12345")

        assert result == OrderStatus.FILLED

    async def test_returns_submitted(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "SUBMITTED" if k == "order_status" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.order_list_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            result = await broker.get_order_status("FT-12345")

        assert result == OrderStatus.SUBMITTED

    async def test_returns_cancelled(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "CANCELLED_ALL" if k == "order_status" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.order_list_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            result = await broker.get_order_status("FT-12345")

        assert result == OrderStatus.CANCELLED

    async def test_passes_trd_env_to_order_list_query(self, broker):
        broker._connected = True
        broker._trd_env = "MOCK_SIMULATE"
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: "FILLED_ALL" if k == "order_status" else None
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.order_list_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            await broker.get_order_status("FT-12345")

        call_kwargs = broker._trd_ctx.order_list_query.call_args[1]
        assert call_kwargs["trd_env"] == "MOCK_SIMULATE"

    async def test_raises_on_query_failure(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.order_list_query = MagicMock(return_value=(1, "Query failed"))

        with (
            patch("src.broker.futu_broker.RET_OK", 0),
            pytest.raises(BrokerError),
        ):
            await broker.get_order_status("FT-12345")


class TestSubscribeFills:
    async def test_callback_receives_fill(self, broker):
        received = []
        broker.subscribe_fills(lambda fill: received.append(fill))
        fill = OrderFill(
            fill_id="FILL-001",
            order_id="FT-12345",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.50"),
            timestamp=datetime.utcnow(),
        )
        pump_task = asyncio.create_task(broker._fill_pump())
        broker._fill_queue.put_nowait(fill)
        await asyncio.sleep(0.05)
        pump_task.cancel()
        try:
            await pump_task
        except asyncio.CancelledError:
            pass
        assert len(received) == 1
        assert received[0].fill_id == "FILL-001"
        assert received[0].price == Decimal("150.50")

    async def test_subscribe_fills_stores_callback(self, broker):
        cb = MagicMock()
        broker.subscribe_fills(cb)
        assert broker._fill_callback is cb


class TestFillHandler:
    async def test_deal_handler_enqueues_fill(self, broker):
        broker._loop = asyncio.get_running_loop()
        broker._pending_orders = {"FT-12345": "aq-ord-001"}

        # Simulate a fill from the TradeDealHandlerBase callback
        mock_data = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: {
            "order_id": "FT-12345",
            "deal_id": "DEAL-001",
            "code": "US.AAPL",
            "trd_side": "BUY",
            "qty": 100,
            "price": 150.25,
            "create_time": "2024-01-15 10:30:00",
        }.get(k)
        mock_data.iterrows = MagicMock(return_value=iter([(0, mock_row)]))

        broker._on_fill(mock_data)
        await asyncio.sleep(0)  # let call_soon_threadsafe run
        assert not broker._fill_queue.empty()
        fill = broker._fill_queue.get_nowait()
        assert fill.order_id == "FT-12345"
        assert fill.side == "buy"
        assert fill.quantity == 100

    async def test_unknown_fill_logs_warning(self, broker, caplog):
        broker._loop = asyncio.get_running_loop()
        broker._pending_orders = {}

        mock_data = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: {
            "order_id": "FT-99999",
            "deal_id": "DEAL-002",
            "code": "US.TSLA",
            "trd_side": "BUY",
            "qty": 50,
            "price": 200.0,
            "create_time": "2024-01-15 10:30:00",
        }.get(k)
        mock_data.iterrows = MagicMock(return_value=iter([(0, mock_row)]))

        with caplog.at_level(logging.WARNING):
            broker._on_fill(mock_data)
        assert "unknown order" in caplog.text.lower()
        assert broker._fill_queue.empty()

    async def test_sell_fill_maps_side(self, broker):
        broker._loop = asyncio.get_running_loop()
        broker._pending_orders = {"FT-12345": "aq-ord-001"}

        mock_data = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: {
            "order_id": "FT-12345",
            "deal_id": "DEAL-003",
            "code": "US.AAPL",
            "trd_side": "SELL",
            "qty": 50,
            "price": 155.0,
            "create_time": "2024-01-15 10:30:00",
        }.get(k)
        mock_data.iterrows = MagicMock(return_value=iter([(0, mock_row)]))

        broker._on_fill(mock_data)
        await asyncio.sleep(0)
        fill = broker._fill_queue.get_nowait()
        assert fill.side == "sell"


class TestConnectDisconnect:
    async def _connect(self, broker):
        mock_ctx = MagicMock()
        mock_ctx.set_handler = MagicMock()
        with (
            patch("src.broker.futu_broker.OpenSecTradeContext", return_value=mock_ctx),
            patch("src.broker.futu_broker.TrdEnv"),
            patch("src.broker.futu_broker.TrdMarket"),
            patch("src.broker.futu_broker.TradeDealHandlerBase", MagicMock),
            patch("src.broker.futu_broker.TradeOrderHandlerBase", MagicMock),
            patch("src.broker.futu_broker.RET_OK", 0),
        ):
            await broker.connect()
        return mock_ctx

    async def test_connect_sets_connected_true(self, broker):
        mock_ctx = await self._connect(broker)
        assert broker._connected is True
        assert broker._trd_ctx is mock_ctx
        if broker._fill_pump_task:
            broker._fill_pump_task.cancel()
            try:
                await broker._fill_pump_task
            except asyncio.CancelledError:
                pass

    async def test_connect_starts_fill_pump(self, broker):
        await self._connect(broker)
        assert broker._fill_pump_task is not None
        assert not broker._fill_pump_task.done()
        broker._fill_pump_task.cancel()
        try:
            await broker._fill_pump_task
        except asyncio.CancelledError:
            pass

    async def test_disconnect_sets_connected_false(self, broker):
        await self._connect(broker)
        assert broker._connected is True
        await broker.disconnect()
        assert broker._connected is False
        assert broker._trd_ctx is None

    async def test_disconnect_cancels_fill_pump(self, broker):
        await self._connect(broker)
        pump_task = broker._fill_pump_task
        assert pump_task is not None
        await broker.disconnect()
        assert pump_task.done()

    async def test_disconnect_closes_context(self, broker):
        mock_ctx = await self._connect(broker)
        await broker.disconnect()
        mock_ctx.close.assert_called_once()


class TestGetPositions:
    async def test_returns_mapped_positions(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        row1 = MagicMock()
        row1.__getitem__ = lambda s, k: {
            "code": "US.AAPL",
            "qty": 100,
            "cost_price": 150.25,
            "market_val": 15500.00,
        }.get(k)
        row2 = MagicMock()
        row2.__getitem__ = lambda s, k: {
            "code": "US.TSLA",
            "qty": 50,
            "cost_price": 200.50,
            "market_val": 11000.00,
        }.get(k)
        mock_df.iterrows = MagicMock(return_value=iter([(0, row1), (1, row2)]))
        broker._trd_ctx.position_list_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            result = await broker.get_positions("ACC001")

        assert len(result) == 2
        assert isinstance(result[0], BrokerPosition)
        assert result[0].symbol == "AAPL"
        assert result[0].quantity == 100
        assert result[0].avg_cost == Decimal("150.25")
        assert result[0].market_value == Decimal("15500.00")
        assert result[0].asset_type == AssetType.STOCK
        assert result[1].symbol == "TSLA"

    async def test_returns_empty_list_when_no_positions(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_df.iterrows = MagicMock(return_value=iter([]))
        broker._trd_ctx.position_list_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            result = await broker.get_positions("ACC001")

        assert result == []


class TestGetAccount:
    async def test_returns_mapped_account(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()

        mock_df = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda s, k: {
            "cash": 50000.00,
            "power": 100000.00,
            "total_assets": 75000.00,
            "frozen_cash": 25000.00,
        }.get(k)
        mock_df.iloc.__getitem__ = MagicMock(return_value=mock_row)
        broker._trd_ctx.accinfo_query = MagicMock(return_value=(0, mock_df))

        with patch("src.broker.futu_broker.RET_OK", 0):
            result = await broker.get_account("ACC001")

        assert isinstance(result, BrokerAccount)
        assert result.account_id == "ACC001"
        assert result.cash == Decimal("50000.00")
        assert result.buying_power == Decimal("100000.00")
        assert result.total_equity == Decimal("75000.00")
        assert result.margin_used == Decimal("25000.00")

    async def test_raises_on_query_failure(self, broker):
        broker._connected = True
        broker._trd_ctx = MagicMock()
        broker._trd_ctx.accinfo_query = MagicMock(return_value=(1, "Query failed"))

        with (
            patch("src.broker.futu_broker.RET_OK", 0),
            pytest.raises(BrokerError),
        ):
            await broker.get_account("ACC001")


# Need BrokerError import for error-path tests
from src.broker.errors import BrokerError  # noqa: E402
