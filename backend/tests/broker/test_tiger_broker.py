# backend/tests/broker/test_tiger_broker.py
"""Tests for TigerBroker adapter -- Phase 3 of Tiger Broker Adapter spec."""

import asyncio
import logging
import os
import time
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from src.broker.errors import OrderCancelError, OrderSubmissionError
from src.broker.query import BrokerAccount, BrokerPosition
from src.broker.tiger_broker import TIGER_STATUS_MAP, TigerBroker
from src.models.position import AssetType
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill


@pytest.fixture
def cred_file(tmp_path):
    p = tmp_path / "tiger_credentials.props"
    p.write_text("tiger_id=TEST\naccount=TEST123\n")
    os.chmod(p, 0o600)
    return str(p)


@pytest.fixture
def bad_perms_file(tmp_path):
    p = tmp_path / "bad_perms.pem"
    p.write_text("fake key")
    os.chmod(p, 0o644)
    return str(p)


@pytest.fixture
def broker(cred_file):
    return TigerBroker(credentials_path=cred_file, account_id="TEST123", env="SANDBOX")


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


class TestTigerBrokerConstructor:
    def test_valid_construction(self, cred_file):
        tb = TigerBroker(credentials_path=cred_file, account_id="ACC001", env="PROD")
        assert tb._credentials_path == cred_file
        assert tb._account_id == "ACC001"
        assert tb._env == "PROD"
        assert tb._connected is False

    def test_valid_sandbox_env(self, cred_file):
        tb = TigerBroker(credentials_path=cred_file, account_id="ACC001", env="SANDBOX")
        assert tb._env == "SANDBOX"

    def test_raises_for_missing_credentials(self, tmp_path):
        with pytest.raises(ValueError, match="Credentials file not found"):
            TigerBroker(credentials_path=str(tmp_path / "nonexistent.pem"), account_id="ACC001")

    def test_raises_for_wrong_permissions(self, bad_perms_file):
        with pytest.raises(ValueError, match="0600 permissions"):
            TigerBroker(credentials_path=bad_perms_file, account_id="ACC001")

    def test_raises_for_empty_account_id(self, cred_file):
        with pytest.raises(ValueError, match="account_id must be non-empty"):
            TigerBroker(credentials_path=cred_file, account_id="")

    def test_raises_for_invalid_env(self, cred_file):
        with pytest.raises(ValueError, match="env must be"):
            TigerBroker(credentials_path=cred_file, account_id="ACC001", env="DEV")


class TestStatusMapping:
    def test_map_has_all_nine_statuses(self):
        expected = {
            "PendingNew",
            "Initial",
            "Submitted",
            "PartiallyFilled",
            "Filled",
            "Cancelled",
            "PendingCancel",
            "Inactive",
            "Invalid",
        }
        assert set(TIGER_STATUS_MAP.keys()) == expected

    def test_pending_new(self):
        assert TIGER_STATUS_MAP["PendingNew"] == OrderStatus.PENDING

    def test_initial(self):
        assert TIGER_STATUS_MAP["Initial"] == OrderStatus.SUBMITTED

    def test_submitted(self):
        assert TIGER_STATUS_MAP["Submitted"] == OrderStatus.SUBMITTED

    def test_partially_filled(self):
        assert TIGER_STATUS_MAP["PartiallyFilled"] == OrderStatus.PARTIAL_FILL

    def test_filled(self):
        assert TIGER_STATUS_MAP["Filled"] == OrderStatus.FILLED

    def test_cancelled(self):
        assert TIGER_STATUS_MAP["Cancelled"] == OrderStatus.CANCELLED

    def test_pending_cancel(self):
        assert TIGER_STATUS_MAP["PendingCancel"] == OrderStatus.PENDING

    def test_inactive(self):
        assert TIGER_STATUS_MAP["Inactive"] == OrderStatus.REJECTED

    def test_invalid(self):
        assert TIGER_STATUS_MAP["Invalid"] == OrderStatus.EXPIRED

    def test_unknown_status_returns_pending_with_warning(self, broker, caplog):
        with caplog.at_level(logging.WARNING):
            result = broker._map_status("UnknownStatus")
        assert result == OrderStatus.PENDING
        assert "Unmapped Tiger order status" in caplog.text


class TestSubmitOrder:
    async def test_limit_order_creates_correct_objects(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        mock_tiger_order = MagicMock()
        mock_tiger_order.id = 12345
        mock_lo = MagicMock(return_value=mock_tiger_order)
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.limit_order", mock_lo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
        ):
            broker._trade_client.place_order = MagicMock(return_value=None)
            result = await broker.submit_order(_make_order(order_type="limit"))
        assert result == "12345"
        mock_sc.assert_called_once_with(symbol="AAPL", currency="USD")
        mock_lo.assert_called_once()
        kw = mock_lo.call_args[1]
        assert kw["action"] == "BUY"
        assert kw["quantity"] == 100
        assert kw["limit_price"] == 150.0

    async def test_market_order_creates_market_order(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        mock_tiger_order = MagicMock()
        mock_tiger_order.id = 67890
        mock_mo = MagicMock(return_value=mock_tiger_order)
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.market_order", mock_mo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
        ):
            broker._trade_client.place_order = MagicMock(return_value=None)
            result = await broker.submit_order(_make_order(order_type="market"))
        assert result == "67890"
        mock_mo.assert_called_once()

    async def test_sell_order_uses_sell_action(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        mock_tiger_order = MagicMock()
        mock_tiger_order.id = 11111
        mock_lo = MagicMock(return_value=mock_tiger_order)
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.limit_order", mock_lo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
        ):
            broker._trade_client.place_order = MagicMock(return_value=None)
            await broker.submit_order(_make_order(order_type="limit", side="sell"))
        assert mock_lo.call_args[1]["action"] == "SELL"

    async def test_returns_string_order_id(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        mock_tiger_order = MagicMock()
        mock_tiger_order.id = 12345
        mock_lo = MagicMock(return_value=mock_tiger_order)
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.limit_order", mock_lo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
        ):
            broker._trade_client.place_order = MagicMock(return_value=None)
            result = await broker.submit_order(_make_order())
        assert isinstance(result, str)
        assert result == "12345"

    async def test_raises_on_tiger_api_failure(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        broker._trade_client.place_order = MagicMock(side_effect=RuntimeError("Tiger API error"))
        mock_lo = MagicMock(return_value=MagicMock(id=99999))
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.limit_order", mock_lo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
            pytest.raises(OrderSubmissionError),
        ):
            await broker.submit_order(_make_order())

    async def test_raises_when_not_connected(self, broker):
        broker._connected = False
        with pytest.raises(OrderSubmissionError, match="Not connected"):
            await broker.submit_order(_make_order())

    async def test_stores_pending_order_mapping(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        mock_tiger_order = MagicMock()
        mock_tiger_order.id = 55555
        mock_lo = MagicMock(return_value=mock_tiger_order)
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.limit_order", mock_lo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
        ):
            broker._trade_client.place_order = MagicMock(return_value=None)
            await broker.submit_order(_make_order())
        assert "55555" in broker._pending_orders
        assert broker._pending_orders["55555"] == "aq-ord-001"

    async def test_submit_order_round_trip_under_5s(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        mock_tiger_order = MagicMock()
        mock_tiger_order.id = 77777
        mock_lo = MagicMock(return_value=mock_tiger_order)
        mock_sc = MagicMock(return_value=MagicMock())
        with (
            patch("src.broker.tiger_broker.limit_order", mock_lo),
            patch("src.broker.tiger_broker.stock_contract", mock_sc),
        ):
            broker._trade_client.place_order = MagicMock(return_value=None)
            start = time.monotonic()
            await broker.submit_order(_make_order())
            elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"submit_order took {elapsed:.2f}s, exceeds 5s limit"


class TestCancelOrder:
    async def test_cancel_returns_true(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        broker._trade_client.cancel_order = MagicMock(return_value=None)
        result = await broker.cancel_order("12345")
        assert result is True

    async def test_cancel_raises_on_failure(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        broker._trade_client.cancel_order = MagicMock(side_effect=RuntimeError("Cancel failed"))
        with pytest.raises(OrderCancelError):
            await broker.cancel_order("12345")

    async def test_cancel_passes_int_id(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        broker._trade_client.cancel_order = MagicMock(return_value=None)
        await broker.cancel_order("98765")
        broker._trade_client.cancel_order.assert_called_once_with(id=98765)


class TestGetOrderStatus:
    async def test_returns_filled(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        m = MagicMock()
        m.status = "Filled"
        broker._trade_client.get_order = MagicMock(return_value=m)
        assert await broker.get_order_status("12345") == OrderStatus.FILLED

    async def test_returns_submitted(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        m = MagicMock()
        m.status = "Submitted"
        broker._trade_client.get_order = MagicMock(return_value=m)
        assert await broker.get_order_status("12345") == OrderStatus.SUBMITTED

    async def test_returns_cancelled(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        m = MagicMock()
        m.status = "Cancelled"
        broker._trade_client.get_order = MagicMock(return_value=m)
        assert await broker.get_order_status("12345") == OrderStatus.CANCELLED

    async def test_passes_int_id(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        m = MagicMock()
        m.status = "Filled"
        broker._trade_client.get_order = MagicMock(return_value=m)
        await broker.get_order_status("54321")
        broker._trade_client.get_order.assert_called_once_with(id=54321)


class TestSubscribeFills:
    async def test_callback_receives_fill(self, broker):
        received = []
        broker.subscribe_fills(lambda fill: received.append(fill))
        fill = OrderFill(
            fill_id="FILL-001",
            order_id="12345",
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

    async def test_unknown_fill_logs_warning(self, broker, caplog):
        broker._loop = asyncio.get_running_loop()
        broker._pending_orders = {}
        data = {
            "id": "99999",
            "exec_id": "EXEC-001",
            "symbol": "TSLA",
            "action": "BUY",
            "filled_quantity": 50,
            "avg_fill_price": 200.0,
        }
        with caplog.at_level(logging.WARNING):
            broker._on_transaction_changed("tiger_id", data)
        assert "unknown order" in caplog.text.lower()
        assert broker._fill_queue.empty()

    async def test_known_fill_enqueued(self, broker):
        broker._loop = asyncio.get_running_loop()
        broker._pending_orders = {"12345": "aq-ord-001"}
        data = {
            "id": "12345",
            "exec_id": "EXEC-002",
            "symbol": "AAPL",
            "action": "BUY",
            "filled_quantity": 100,
            "avg_fill_price": 150.25,
        }
        broker._on_transaction_changed("tiger_id", data)
        await asyncio.sleep(0)  # let call_soon_threadsafe callback run
        assert not broker._fill_queue.empty()
        fill = broker._fill_queue.get_nowait()
        assert fill.order_id == "12345"
        assert fill.side == "buy"
        assert fill.quantity == 100
        assert fill.price == Decimal("150.25")

    async def test_sell_fill_maps_side(self, broker):
        broker._loop = asyncio.get_running_loop()
        broker._pending_orders = {"12345": "aq-ord-001"}
        data = {
            "id": "12345",
            "exec_id": "EXEC-003",
            "symbol": "AAPL",
            "action": "SELL",
            "filled_quantity": 50,
            "avg_fill_price": 155.0,
        }
        broker._on_transaction_changed("tiger_id", data)
        await asyncio.sleep(0)  # let call_soon_threadsafe callback run
        fill = broker._fill_queue.get_nowait()
        assert fill.side == "sell"

    async def test_subscribe_fills_stores_callback(self, broker):
        cb = MagicMock()
        broker.subscribe_fills(cb)
        assert broker._fill_callback is cb


class TestOnOrderChanged:
    """_on_order_changed cleans up _pending_orders on terminal states."""

    def test_filled_order_removed_from_pending(self, broker):
        broker._pending_orders = {"12345": "aq-ord-001", "67890": "aq-ord-002"}
        broker._on_order_changed("tiger_id", {"id": "12345", "status": "Filled"})
        assert "12345" not in broker._pending_orders
        assert "67890" in broker._pending_orders

    def test_cancelled_order_removed_from_pending(self, broker):
        broker._pending_orders = {"12345": "aq-ord-001"}
        broker._on_order_changed("tiger_id", {"id": "12345", "status": "Cancelled"})
        assert "12345" not in broker._pending_orders

    def test_non_terminal_status_keeps_pending(self, broker):
        broker._pending_orders = {"12345": "aq-ord-001"}
        broker._on_order_changed("tiger_id", {"id": "12345", "status": "Submitted"})
        assert "12345" in broker._pending_orders

    def test_unknown_order_does_not_crash(self, broker):
        broker._pending_orders = {}
        broker._on_order_changed("tiger_id", {"id": "99999", "status": "Filled"})
        # Should not raise


class TestConnectDisconnect:
    async def _connect(self, broker):
        mc = MagicMock()
        mc.tiger_id = "TID"
        mc.private_key = "PKEY"
        mc.language = None
        mp = MagicMock()
        mt = MagicMock()
        with (
            patch("src.broker.tiger_broker.TigerOpenClientConfig", return_value=mc),
            patch("src.broker.tiger_broker.TradeClient", return_value=mt),
            patch("src.broker.tiger_broker.PushClient", return_value=mp),
            patch("src.broker.tiger_broker.Language"),
        ):
            await broker.connect()
        return mp, mt

    async def test_connect_sets_connected_true(self, broker):
        mp, mt = await self._connect(broker)
        assert broker._connected is True
        assert broker._trade_client is mt
        assert broker._push_client is mp
        if broker._fill_pump_task:
            broker._fill_pump_task.cancel()
            try:
                await broker._fill_pump_task
            except asyncio.CancelledError:
                pass

    async def test_connect_subscribes(self, broker):
        mp, _ = await self._connect(broker)
        mp.connect.assert_called_once_with("TID", "PKEY")
        mp.subscribe_order.assert_called_once_with(account="TEST123")
        mp.subscribe_transaction.assert_called_once_with(account="TEST123")
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
        assert broker._trade_client is None
        assert broker._push_client is None

    async def test_disconnect_cancels_fill_pump(self, broker):
        await self._connect(broker)
        pump_task = broker._fill_pump_task
        assert pump_task is not None
        await broker.disconnect()
        assert pump_task.done()

    async def test_disconnect_calls_push_disconnect(self, broker):
        mp, _ = await self._connect(broker)
        await broker.disconnect()
        mp.disconnect.assert_called_once()


class TestRateLimitRetry:
    async def test_retries_on_rate_limit(self, broker):
        call_count = 0

        def flaky(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RuntimeError("rate limit exceeded")
            return "success"

        result = await broker._retry_on_rate_limit(flaky)
        assert result == "success"
        assert call_count == 3

    async def test_raises_non_rate_limit_immediately(self, broker):
        def fail(*a, **kw):
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            await broker._retry_on_rate_limit(fail)

    async def test_passes_through_on_first_success(self, broker):
        call_count = 0

        def ok(*a, **kw):
            nonlocal call_count
            call_count += 1
            return 42

        result = await broker._retry_on_rate_limit(ok)
        assert result == 42
        assert call_count == 1


class TestReconnection:
    def test_on_connect_sets_connected(self, broker):
        broker._on_connect()
        assert broker._connected is True

    def test_on_disconnect_sets_not_connected(self, broker):
        broker._connected = True
        broker._on_disconnect()
        assert broker._connected is False


# ---------------------------------------------------------------------------
# T043: get_positions
# ---------------------------------------------------------------------------


class TestGetPositions:
    """get_positions delegates to TradeClient.get_positions and maps to BrokerPosition."""

    async def test_returns_mapped_positions(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()

        pos1 = MagicMock()
        pos1.contract = MagicMock()
        pos1.contract.symbol = "AAPL"
        pos1.quantity = 100
        pos1.average_cost = 150.25
        pos1.market_value = 15500.00

        pos2 = MagicMock()
        pos2.contract = MagicMock()
        pos2.contract.symbol = "TSLA"
        pos2.quantity = 50
        pos2.average_cost = 200.50
        pos2.market_value = 11000.00

        broker._trade_client.get_positions = MagicMock(return_value=[pos1, pos2])

        result = await broker.get_positions("TEST123")

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
        broker._trade_client = MagicMock()
        broker._trade_client.get_positions = MagicMock(return_value=[])

        result = await broker.get_positions("TEST123")

        assert result == []

    async def test_passes_account_id(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()
        broker._trade_client.get_positions = MagicMock(return_value=[])

        await broker.get_positions("ACC999")

        broker._trade_client.get_positions.assert_called_once_with(account="ACC999")


# ---------------------------------------------------------------------------
# T044: get_account
# ---------------------------------------------------------------------------


class TestGetAccount:
    """get_account delegates to TradeClient.get_assets and maps to BrokerAccount."""

    async def test_returns_mapped_account(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()

        assets = MagicMock()
        assets.summary = MagicMock()
        assets.summary.cash = 50000.00
        assets.summary.buying_power = 100000.00
        assets.summary.net_liquidation = 75000.00
        assets.summary.initial_margin_requirement = 25000.00

        broker._trade_client.get_assets = MagicMock(return_value=assets)

        result = await broker.get_account("TEST123")

        assert isinstance(result, BrokerAccount)
        assert result.account_id == "TEST123"
        assert result.cash == Decimal("50000.00")
        assert result.buying_power == Decimal("100000.00")
        assert result.total_equity == Decimal("75000.00")
        assert result.margin_used == Decimal("25000.00")

    async def test_passes_account_id(self, broker):
        broker._connected = True
        broker._trade_client = MagicMock()

        assets = MagicMock()
        assets.summary = MagicMock()
        assets.summary.cash = 0
        assets.summary.buying_power = 0
        assets.summary.net_liquidation = 0
        assets.summary.initial_margin_requirement = 0

        broker._trade_client.get_assets = MagicMock(return_value=assets)

        await broker.get_account("ACC999")

        broker._trade_client.get_assets.assert_called_once_with(account="ACC999")
