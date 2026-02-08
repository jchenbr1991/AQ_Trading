# backend/src/broker/futu_broker.py
"""Futu (moomoo) broker adapter implementing the Broker protocol.

Wraps the moomoo (futu-api) SDK to provide async order execution via the
AQ Trading Broker interface. All synchronous Futu SDK calls are run in
threads via asyncio.to_thread(). TradeDealHandlerBase callbacks from Futu's
thread are bridged to asyncio via loop.call_soon_threadsafe().

Connects to a locally running OpenD gateway (default 127.0.0.1:11111).
Defaults to TrdEnv.SIMULATE (模拟盘).
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from src.broker.errors import BrokerError, OrderCancelError, OrderSubmissionError
from src.broker.query import BrokerAccount, BrokerPosition
from src.models.position import AssetType
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill

logger = logging.getLogger(__name__)

# Lazy imports for Futu SDK -- replaced at module level after first use
# or mocked in tests.
OpenSecTradeContext = None
TrdEnv = None
TrdMarket = None
TrdSide = None
OrderType = None
ModifyOrderOp = None
RET_OK = None
TradeDealHandlerBase = None
TradeOrderHandlerBase = None


def _ensure_futu_imports():
    """Import Futu SDK symbols on first use (lazy)."""
    global OpenSecTradeContext, TrdEnv, TrdMarket, TrdSide, OrderType
    global ModifyOrderOp, RET_OK, TradeDealHandlerBase, TradeOrderHandlerBase
    if OpenSecTradeContext is not None:
        return
    from moomoo import (  # noqa: I001
        ModifyOrderOp as _ModifyOrderOp,
        OpenSecTradeContext as _OpenSecTradeContext,
        OrderType as _OrderType,
        RET_OK as _RET_OK,
        TradeDealHandlerBase as _TradeDealHandlerBase,
        TradeOrderHandlerBase as _TradeOrderHandlerBase,
        TrdEnv as _TrdEnv,
        TrdMarket as _TrdMarket,
        TrdSide as _TrdSide,
    )

    OpenSecTradeContext = _OpenSecTradeContext
    TrdEnv = _TrdEnv
    TrdMarket = _TrdMarket
    TrdSide = _TrdSide
    OrderType = _OrderType
    ModifyOrderOp = _ModifyOrderOp
    RET_OK = _RET_OK
    TradeDealHandlerBase = _TradeDealHandlerBase
    TradeOrderHandlerBase = _TradeOrderHandlerBase


FUTU_STATUS_MAP: dict[str, OrderStatus] = {
    "WAITING_SUBMIT": OrderStatus.PENDING,
    "SUBMITTING": OrderStatus.PENDING,
    "SUBMITTED": OrderStatus.SUBMITTED,
    "FILLED_PART": OrderStatus.PARTIAL_FILL,
    "FILLED_ALL": OrderStatus.FILLED,
    "CANCELLED_ALL": OrderStatus.CANCELLED,
    "FAILED": OrderStatus.REJECTED,
    "DISABLED": OrderStatus.EXPIRED,
    "DELETED": OrderStatus.EXPIRED,
}


class FutuBroker:
    """Broker adapter for Futu (moomoo) via futu-api SDK."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        trade_env: str = "SIMULATE",
        account_id: str = "",
        unlock_password: str = "",
    ) -> None:
        if not host:
            raise ValueError("host must be non-empty")
        if port < 0 or port > 65535:
            raise ValueError(f"port must be 0-65535, got {port}")
        if trade_env not in ("SIMULATE", "REAL"):
            raise ValueError(f"trade_env must be 'SIMULATE' or 'REAL', got '{trade_env}'")

        self._host = host
        self._port = port
        self._trade_env = trade_env
        self._account_id = account_id
        self._unlock_password = unlock_password

        self._trd_ctx = None
        self._trd_env = None  # Resolved SDK TrdEnv enum, set during connect()
        self._connected = False
        self._fill_callback: Callable[[OrderFill], None] | None = None
        self._fill_queue: asyncio.Queue[OrderFill] = asyncio.Queue()
        self._fill_pump_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_orders: dict[str, str] = {}  # futu_order_id -> aq_order_id

    # ------------------------------------------------------------------
    # Status mapping
    # ------------------------------------------------------------------

    def _map_status(self, futu_status: str) -> OrderStatus:
        status = FUTU_STATUS_MAP.get(futu_status)
        if status is None:
            logger.warning(f"Unmapped Futu order status: {futu_status}, defaulting to PENDING")
            return OrderStatus.PENDING
        return status

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        _ensure_futu_imports()
        self._loop = asyncio.get_running_loop()

        self._trd_env = TrdEnv.SIMULATE if self._trade_env == "SIMULATE" else TrdEnv.REAL

        self._trd_ctx = await asyncio.to_thread(
            OpenSecTradeContext,
            host=self._host,
            port=self._port,
            filter_trdmarket=TrdMarket.US,
        )

        # Register fill and order handlers
        self._trd_ctx.set_handler(self._make_fill_handler())
        self._trd_ctx.set_handler(self._make_order_handler())

        if self._trade_env == "REAL":
            ret, data = await asyncio.to_thread(self._trd_ctx.unlock_trade, self._unlock_password)
            if ret != RET_OK:
                raise BrokerError(f"Failed to unlock trade: {data}")

        self._connected = True
        self._fill_pump_task = asyncio.create_task(self._fill_pump())
        logger.info(f"FutuBroker connected: host={self._host}:{self._port}, env={self._trade_env}")

    async def disconnect(self) -> None:
        self._connected = False
        if self._fill_pump_task:
            self._fill_pump_task.cancel()
            try:
                await self._fill_pump_task
            except asyncio.CancelledError:
                pass
        if self._trd_ctx:
            try:
                await asyncio.to_thread(self._trd_ctx.close)
            except Exception:
                logger.debug("Error during OpenSecTradeContext close", exc_info=True)
        self._trd_ctx = None
        logger.info("FutuBroker disconnected")

    # ------------------------------------------------------------------
    # Broker protocol
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> str:
        if not self._connected:
            raise OrderSubmissionError("Not connected to Futu", symbol=order.symbol)

        trd_side = TrdSide.BUY if order.side == "buy" else TrdSide.SELL
        order_type = OrderType.MARKET if order.order_type == "market" else OrderType.NORMAL

        kwargs = {
            "price": float(order.limit_price) if order.limit_price else 0.0,
            "qty": order.quantity,
            "code": f"US.{order.symbol}",
            "trd_side": trd_side,
            "order_type": order_type,
            "trd_env": self._trd_env,
        }
        if self._account_id and self._account_id.isdigit():
            kwargs["acc_id"] = int(self._account_id)

        try:
            ret, data = await asyncio.to_thread(self._trd_ctx.place_order, **kwargs)
            if ret != RET_OK:
                raise OrderSubmissionError(str(data), symbol=order.symbol)
            futu_order_id = str(data.iloc[0]["order_id"])
            self._pending_orders[futu_order_id] = order.order_id
            return futu_order_id
        except Exception as e:
            if isinstance(e, OrderSubmissionError):
                raise
            raise OrderSubmissionError(str(e), symbol=order.symbol) from e

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            ret, data = await asyncio.to_thread(
                self._trd_ctx.modify_order,
                modify_order_op=ModifyOrderOp.CANCEL,
                order_id=broker_order_id,
                qty=0,
                price=0,
                trd_env=self._trd_env,
            )
            if ret != RET_OK:
                raise OrderCancelError(str(data), broker_order_id=broker_order_id)
            return True
        except Exception as e:
            if isinstance(e, OrderCancelError):
                raise
            raise OrderCancelError(str(e), broker_order_id=broker_order_id) from e

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        ret, data = await asyncio.to_thread(
            self._trd_ctx.order_list_query,
            order_id=broker_order_id,
            trd_env=self._trd_env,
        )
        if ret != RET_OK:
            raise BrokerError(f"Failed to query order {broker_order_id}: {data}")
        futu_status = str(data.iloc[0]["order_status"])
        return self._map_status(futu_status)

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        self._fill_callback = callback

    # ------------------------------------------------------------------
    # BrokerQuery protocol
    # ------------------------------------------------------------------

    async def get_positions(self, account_id: str) -> list[BrokerPosition]:
        kwargs = {"trd_env": self._trd_env}
        acc = account_id or self._account_id
        if acc and acc.isdigit():
            kwargs["acc_id"] = int(acc)
        ret, data = await asyncio.to_thread(self._trd_ctx.position_list_query, **kwargs)
        if ret != RET_OK:
            raise BrokerError(f"Failed to query positions: {data}")
        positions = []
        for _, row in data.iterrows():
            code = str(row["code"])
            # Strip market prefix (e.g. "US.AAPL" -> "AAPL")
            symbol = code.split(".")[-1] if "." in code else code
            positions.append(
                BrokerPosition(
                    symbol=symbol,
                    quantity=int(row["qty"]),
                    avg_cost=Decimal(str(row["cost_price"])),
                    market_value=Decimal(str(row["market_val"])),
                    asset_type=AssetType.STOCK,
                )
            )
        return positions

    async def get_account(self, account_id: str) -> BrokerAccount:
        kwargs = {"trd_env": self._trd_env}
        acc = account_id or self._account_id
        if acc and acc.isdigit():
            kwargs["acc_id"] = int(acc)
        ret, data = await asyncio.to_thread(self._trd_ctx.accinfo_query, **kwargs)
        if ret != RET_OK:
            raise BrokerError(f"Failed to query account: {data}")
        row = data.iloc[0]
        return BrokerAccount(
            account_id=account_id,
            cash=Decimal(str(row["cash"])),
            buying_power=Decimal(str(row["power"])),
            total_equity=Decimal(str(row["total_assets"])),
            margin_used=Decimal(str(row["frozen_cash"])),
        )

    # ------------------------------------------------------------------
    # Fill pump and handler factories
    # ------------------------------------------------------------------

    async def _fill_pump(self) -> None:
        try:
            while True:
                fill = await self._fill_queue.get()
                if self._fill_callback:
                    self._fill_callback(fill)
        except asyncio.CancelledError:
            pass

    def _on_fill(self, data) -> None:
        """Process fill data from TradeDealHandlerBase callback."""
        try:
            for _, row in data.iterrows():
                futu_order_id = str(row["order_id"])
                if futu_order_id not in self._pending_orders:
                    logger.warning(f"Fill for unknown order: {futu_order_id}")
                    continue

                code = str(row["code"])
                symbol = code.split(".")[-1] if "." in code else code
                trd_side = str(row["trd_side"])

                fill = OrderFill(
                    fill_id=str(row["deal_id"]),
                    order_id=futu_order_id,
                    symbol=symbol,
                    side="buy" if trd_side.upper() == "BUY" else "sell",
                    quantity=int(row["qty"]),
                    price=Decimal(str(row["price"])),
                    timestamp=datetime.utcnow(),
                )

                if self._loop:
                    self._loop.call_soon_threadsafe(self._fill_queue.put_nowait, fill)
        except Exception as e:
            logger.error(f"Error processing fill: {e}", exc_info=True)

    def _on_order_update(self, data) -> None:
        """Process order updates from TradeOrderHandlerBase callback."""
        try:
            for _, row in data.iterrows():
                futu_order_id = str(row["order_id"])
                status = str(row["order_status"])
                logger.debug(f"Order status changed: {futu_order_id} -> {status}")
                if status in ("FILLED_ALL", "CANCELLED_ALL", "FAILED", "DISABLED", "DELETED"):
                    self._pending_orders.pop(futu_order_id, None)
        except Exception as e:
            logger.error(f"Error processing order update: {e}", exc_info=True)

    def _make_fill_handler(self):
        """Create a TradeDealHandlerBase subclass bound to this broker."""
        broker = self

        class _FillHandler(TradeDealHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret, data = super().on_recv_rsp(rsp_pb)
                if ret == RET_OK:
                    broker._on_fill(data)
                return ret, data

        return _FillHandler()

    def _make_order_handler(self):
        """Create a TradeOrderHandlerBase subclass bound to this broker."""
        broker = self

        class _OrderHandler(TradeOrderHandlerBase):
            def on_recv_rsp(self, rsp_pb):
                ret, data = super().on_recv_rsp(rsp_pb)
                if ret == RET_OK:
                    broker._on_order_update(data)
                return ret, data

        return _OrderHandler()
