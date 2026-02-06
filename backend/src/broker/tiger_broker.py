# backend/src/broker/tiger_broker.py
"""Tiger Trading broker adapter implementing the Broker protocol.

Wraps the tigeropen SDK to provide async order execution via the AQ Trading
Broker interface. All synchronous Tiger SDK calls are run in threads via
asyncio.to_thread(). PushClient callbacks from Tiger's thread are bridged
to asyncio via loop.call_soon_threadsafe().
"""

import asyncio
import logging
import os
import stat
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from src.broker.errors import OrderCancelError, OrderSubmissionError
from src.broker.query import BrokerAccount, BrokerPosition
from src.models.position import AssetType
from src.orders.models import Order, OrderStatus
from src.strategies.signals import OrderFill

logger = logging.getLogger(__name__)

# Lazy imports for Tiger SDK -- these are replaced at module level after
# first use or mocked in tests.
TigerOpenClientConfig = None
TradeClient = None
PushClient = None
Language = None
market_order = None
limit_order = None
stock_contract = None


def _ensure_tiger_imports():
    """Import Tiger SDK symbols on first use (lazy)."""
    global TigerOpenClientConfig, TradeClient, PushClient, Language
    global market_order, limit_order, stock_contract
    if TigerOpenClientConfig is not None:
        return
    from tigeropen.common.consts import Language as _Language
    from tigeropen.common.util.contract_utils import stock_contract as _stock_contract
    from tigeropen.common.util.order_utils import limit_order as _limit_order
    from tigeropen.common.util.order_utils import market_order as _market_order
    from tigeropen.push.push_client import PushClient as _PushClient
    from tigeropen.tiger_open_config import TigerOpenClientConfig as _TigerOpenClientConfig
    from tigeropen.trade.trade_client import TradeClient as _TradeClient

    TigerOpenClientConfig = _TigerOpenClientConfig
    TradeClient = _TradeClient
    PushClient = _PushClient
    Language = _Language
    market_order = _market_order
    limit_order = _limit_order
    stock_contract = _stock_contract


TIGER_STATUS_MAP: dict[str, OrderStatus] = {
    "PendingNew": OrderStatus.PENDING,
    "Initial": OrderStatus.SUBMITTED,
    "Submitted": OrderStatus.SUBMITTED,
    "PartiallyFilled": OrderStatus.PARTIAL_FILL,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "PendingCancel": OrderStatus.PENDING,
    "Inactive": OrderStatus.REJECTED,
    "Invalid": OrderStatus.EXPIRED,
}


class TigerBroker:
    """Broker adapter for Tiger Trading via tigeropen SDK."""

    def __init__(
        self,
        credentials_path: str,
        account_id: str,
        env: str = "PROD",
        max_reconnect_attempts: int = 3,
    ) -> None:
        if not os.path.exists(credentials_path):
            raise ValueError(f"Credentials file not found: {credentials_path}")
        file_stat = os.stat(credentials_path)
        file_mode = stat.S_IMODE(file_stat.st_mode)
        if file_mode != 0o600:
            raise ValueError(
                f"Credentials file must have 0600 permissions, got {oct(file_mode)}: "
                f"{credentials_path}"
            )
        if not account_id:
            raise ValueError("account_id must be non-empty")
        if env not in ("PROD", "SANDBOX"):
            raise ValueError(f"env must be 'PROD' or 'SANDBOX', got '{env}'")

        self._credentials_path = credentials_path
        self._account_id = account_id
        self._env = env
        self._max_reconnect_attempts = max_reconnect_attempts

        self._trade_client = None
        self._push_client = None
        self._connected = False
        self._fill_callback: Callable[[OrderFill], None] | None = None
        self._fill_queue: asyncio.Queue[OrderFill] = asyncio.Queue()
        self._fill_pump_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_orders: dict[str, str] = {}  # tiger_order_id -> aq_order_id

    # ------------------------------------------------------------------
    # Status mapping
    # ------------------------------------------------------------------

    def _map_status(self, tiger_status: str) -> OrderStatus:
        status = TIGER_STATUS_MAP.get(tiger_status)
        if status is None:
            logger.warning(f"Unmapped Tiger order status: {tiger_status}, defaulting to PENDING")
            return OrderStatus.PENDING
        return status

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        _ensure_tiger_imports()
        self._loop = asyncio.get_running_loop()

        client_config = TigerOpenClientConfig(props_path=self._credentials_path)
        client_config.language = Language.en_US

        self._trade_client = TradeClient(client_config)
        self._push_client = PushClient(
            host="openapi-socket.tigerfintech.com",
            port=8885,
            use_ssl=True,
        )
        self._push_client.order_changed = self._on_order_changed
        self._push_client.transaction_changed = self._on_transaction_changed
        self._push_client.connect_callback = self._on_connect
        self._push_client.disconnect_callback = self._on_disconnect

        await asyncio.to_thread(
            self._push_client.connect, client_config.tiger_id, client_config.private_key
        )
        await asyncio.to_thread(self._push_client.subscribe_order, account=self._account_id)
        await asyncio.to_thread(self._push_client.subscribe_transaction, account=self._account_id)

        self._connected = True
        self._fill_pump_task = asyncio.create_task(self._fill_pump())
        logger.info(f"TigerBroker connected: account={self._account_id}, env={self._env}")

    async def disconnect(self) -> None:
        self._connected = False
        if self._fill_pump_task:
            self._fill_pump_task.cancel()
            try:
                await self._fill_pump_task
            except asyncio.CancelledError:
                pass
        if self._push_client:
            try:
                await asyncio.to_thread(self._push_client.disconnect)
            except Exception:
                logger.debug("Error during PushClient disconnect", exc_info=True)
        self._trade_client = None
        self._push_client = None
        logger.info("TigerBroker disconnected")

    # ------------------------------------------------------------------
    # Broker protocol
    # ------------------------------------------------------------------

    async def submit_order(self, order: Order) -> str:
        if not self._connected:
            raise OrderSubmissionError("Not connected to Tiger", symbol=order.symbol)

        contract = stock_contract(symbol=order.symbol, currency="USD")

        if order.order_type == "market":
            tiger_order = market_order(
                account=self._account_id,
                contract=contract,
                action="BUY" if order.side == "buy" else "SELL",
                quantity=order.quantity,
            )
        else:
            tiger_order = limit_order(
                account=self._account_id,
                contract=contract,
                action="BUY" if order.side == "buy" else "SELL",
                quantity=order.quantity,
                limit_price=float(order.limit_price),
            )

        try:
            await self._retry_on_rate_limit(self._trade_client.place_order, tiger_order)
            tiger_order_id = str(tiger_order.id)
            self._pending_orders[tiger_order_id] = order.order_id
            return tiger_order_id
        except Exception as e:
            if isinstance(e, OrderSubmissionError):
                raise
            raise OrderSubmissionError(str(e), symbol=order.symbol) from e

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await self._retry_on_rate_limit(
                self._trade_client.cancel_order, id=int(broker_order_id)
            )
            return True
        except Exception as e:
            if isinstance(e, OrderCancelError):
                raise
            raise OrderCancelError(str(e), broker_order_id=broker_order_id) from e

    async def get_order_status(self, broker_order_id: str) -> OrderStatus:
        order = await self._retry_on_rate_limit(
            self._trade_client.get_order, id=int(broker_order_id)
        )
        return self._map_status(order.status)

    def subscribe_fills(self, callback: Callable[[OrderFill], None]) -> None:
        self._fill_callback = callback

    # ------------------------------------------------------------------
    # BrokerQuery protocol
    # ------------------------------------------------------------------

    async def get_positions(self, account_id: str) -> list[BrokerPosition]:
        positions = await self._retry_on_rate_limit(
            self._trade_client.get_positions, account=account_id
        )
        return [
            BrokerPosition(
                symbol=p.contract.symbol,
                quantity=int(p.quantity),
                avg_cost=Decimal(str(p.average_cost)),
                market_value=Decimal(str(p.market_value)),
                asset_type=AssetType.STOCK,
            )
            for p in positions
        ]

    async def get_account(self, account_id: str) -> BrokerAccount:
        assets = await self._retry_on_rate_limit(self._trade_client.get_assets, account=account_id)
        return BrokerAccount(
            account_id=account_id,
            cash=Decimal(str(assets.summary.cash)),
            buying_power=Decimal(str(assets.summary.buying_power)),
            total_equity=Decimal(str(assets.summary.net_liquidation)),
            margin_used=Decimal(str(assets.summary.initial_margin_requirement)),
        )

    # ------------------------------------------------------------------
    # Fill pump and PushClient callbacks
    # ------------------------------------------------------------------

    async def _fill_pump(self) -> None:
        try:
            while True:
                fill = await self._fill_queue.get()
                if self._fill_callback:
                    self._fill_callback(fill)
        except asyncio.CancelledError:
            pass

    def _on_transaction_changed(self, tiger_id, data):
        try:
            tiger_order_id = str(data.get("id", ""))
            if tiger_order_id not in self._pending_orders:
                logger.warning(f"Fill for unknown order: {tiger_order_id}")
                return

            # Use broker timestamp if available, fall back to local time
            ts_ms = data.get("timestamp")
            if ts_ms:
                fill_timestamp = datetime.fromtimestamp(
                    ts_ms / 1000, tz=__import__("datetime").timezone.utc
                )
            else:
                fill_timestamp = datetime.utcnow()

            fill = OrderFill(
                fill_id=str(data.get("exec_id", data.get("id", ""))),
                order_id=tiger_order_id,
                symbol=data.get("symbol", ""),
                side="buy" if data.get("action", "").upper() == "BUY" else "sell",
                quantity=int(data.get("filled_quantity", 0)),
                price=Decimal(str(data.get("avg_fill_price", 0))),
                timestamp=fill_timestamp,
            )

            if self._loop:
                self._loop.call_soon_threadsafe(self._fill_queue.put_nowait, fill)
        except Exception as e:
            logger.error(f"Error processing fill: {e}", exc_info=True)

    def _on_order_changed(self, tiger_id, data):
        logger.debug(f"Order status changed: {data}")
        # Clean up _pending_orders when order reaches terminal state
        tiger_order_id = str(data.get("id", ""))
        status = data.get("status", "")
        if status in ("Filled", "Cancelled", "Inactive", "Invalid"):
            self._pending_orders.pop(tiger_order_id, None)

    def _on_connect(self):
        self._connected = True
        logger.info("TigerBroker PushClient connected")

    def _on_disconnect(self):
        self._connected = False
        logger.warning("TigerBroker PushClient disconnected")
        if self._loop:
            self._loop.call_soon_threadsafe(asyncio.ensure_future, self._reconnect())

    # ------------------------------------------------------------------
    # Reconnection and rate-limit retry
    # ------------------------------------------------------------------

    async def _reconnect(self) -> None:
        for attempt in range(self._max_reconnect_attempts):
            delay = 2**attempt
            logger.info(
                f"Reconnection attempt {attempt + 1}/{self._max_reconnect_attempts} in {delay}s"
            )
            await asyncio.sleep(delay)
            try:
                await self.connect()
                logger.info("Reconnection successful")
                return
            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
        logger.error("Max reconnection attempts reached, giving up")

    async def _retry_on_rate_limit(self, func, *args, **kwargs):
        for attempt in range(3):
            try:
                return await asyncio.to_thread(func, *args, **kwargs)
            except Exception as e:
                error_str = str(e).lower()
                if "rate" in error_str or "limit" in error_str or "too many" in error_str:
                    if attempt < 2:
                        delay = 2**attempt
                        logger.warning(
                            f"Rate limit hit, retrying in {delay}s (attempt {attempt + 1}/3)"
                        )
                        await asyncio.sleep(delay)
                        continue
                raise
        raise RuntimeError("Max retries exceeded")
