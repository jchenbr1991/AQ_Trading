# backend/src/market_data/sources/tiger.py
"""Tiger Trading market data source implementing the DataSource protocol.

Wraps the tigeropen PushClient to stream real-time quotes. All Tiger SDK
calls from Tiger's thread are bridged to asyncio via loop.call_soon_threadsafe().
"""

import asyncio
import logging
import os
import stat
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from decimal import Decimal

from src.strategies.base import MarketData

logger = logging.getLogger(__name__)

# Lazy imports for Tiger SDK
TigerOpenClientConfig = None
PushClient = None
Language = None


def _ensure_tiger_imports():
    """Import Tiger SDK symbols on first use (lazy)."""
    global TigerOpenClientConfig, PushClient, Language
    if TigerOpenClientConfig is not None:
        return
    from tigeropen.common.consts import Language as _Language
    from tigeropen.push.push_client import PushClient as _PushClient
    from tigeropen.tiger_open_config import TigerOpenClientConfig as _TigerOpenClientConfig

    TigerOpenClientConfig = _TigerOpenClientConfig
    PushClient = _PushClient
    Language = _Language


class TigerDataSource:
    """Market data source for Tiger Trading via tigeropen PushClient."""

    def __init__(
        self,
        credentials_path: str,
        account_id: str,
        symbols: list[str],
        env: str = "PROD",
        max_symbols: int = 50,
    ) -> None:
        if not os.path.exists(credentials_path):
            raise ValueError(f"Credentials file not found: {credentials_path}")
        file_mode = stat.S_IMODE(os.stat(credentials_path).st_mode)
        if file_mode != 0o600:
            raise ValueError(
                f"Credentials file must have 0600 permissions, got {oct(file_mode)}: "
                f"{credentials_path}"
            )
        if not account_id:
            raise ValueError("account_id must be non-empty")
        if not symbols:
            raise ValueError("symbols must be non-empty")
        if env not in ("PROD", "SANDBOX"):
            raise ValueError(f"env must be 'PROD' or 'SANDBOX', got '{env}'")

        self._credentials_path = credentials_path
        self._account_id = account_id
        self._symbols = list(symbols)
        self._env = env
        self._max_symbols = max_symbols

        self._push_client = None
        self._connected = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._quote_queue: asyncio.Queue[MarketData] = asyncio.Queue()
        self._last_timestamps: dict[str, int] = {}
        self._subscribed_symbols: set[str] = set()

    # ------------------------------------------------------------------
    # DataSource protocol
    # ------------------------------------------------------------------

    async def start(self) -> None:
        _ensure_tiger_imports()
        self._loop = asyncio.get_running_loop()

        client_config = TigerOpenClientConfig(props_path=self._credentials_path)

        self._push_client = PushClient(
            host="openapi-socket.tigerfintech.com",
            port=8885,
            use_ssl=True,
        )
        self._push_client.quote_changed = self._quote_changed
        self._push_client.connect_callback = self._connect_callback
        self._push_client.disconnect_callback = self._disconnect_callback

        await asyncio.to_thread(
            self._push_client.connect, client_config.tiger_id, client_config.private_key
        )

        # Subscribe up to max_symbols
        symbols_to_sub = self._symbols[: self._max_symbols]
        if len(self._symbols) > self._max_symbols:
            skipped = self._symbols[self._max_symbols :]
            logger.warning(
                f"Exceeded max_symbols ({self._max_symbols}), "
                f"skipping {len(skipped)} symbols: {skipped}"
            )

        await asyncio.to_thread(self._push_client.subscribe_quote, symbols_to_sub)
        self._subscribed_symbols = set(symbols_to_sub)
        self._connected = True
        logger.info(f"TigerDataSource started: {len(symbols_to_sub)} symbols subscribed")

    async def stop(self) -> None:
        self._connected = False
        if self._push_client:
            try:
                await asyncio.to_thread(self._push_client.disconnect)
            except Exception:
                logger.debug("Error during PushClient disconnect", exc_info=True)
        self._push_client = None
        logger.info("TigerDataSource stopped")

    async def subscribe(self, symbols: list[str]) -> None:
        new_symbols = [s for s in symbols if s not in self._subscribed_symbols]
        if not new_symbols:
            return

        available = self._max_symbols - len(self._subscribed_symbols)
        if len(new_symbols) > available:
            logger.warning(
                f"max_symbols limit ({self._max_symbols}) reached, "
                f"subscribing only {available} of {len(new_symbols)} new symbols"
            )
            new_symbols = new_symbols[:available]

        if new_symbols and self._push_client:
            await asyncio.to_thread(self._push_client.subscribe_quote, new_symbols)
            self._subscribed_symbols.update(new_symbols)

    async def quotes(self) -> AsyncIterator[MarketData]:
        while True:
            quote = await self._quote_queue.get()
            yield quote

    # ------------------------------------------------------------------
    # Quote callback processing
    # ------------------------------------------------------------------

    def _quote_changed(self, symbol: str, items: list, hour_trading: bool) -> None:
        """Process Tiger quote_changed callback (runs in Tiger's thread)."""
        for item in items:
            try:
                latest_price = item.get("latest_price")
                bid_price = item.get("bid_price")
                ask_price = item.get("ask_price")
                volume = item.get("volume")
                ts_ms = item.get("timestamp")

                # Skip if required field is missing
                if latest_price is None or bid_price is None or ask_price is None:
                    logger.warning(f"Skipping quote for {symbol}: missing required price field")
                    continue
                if ts_ms is None:
                    logger.warning(f"Skipping quote for {symbol}: missing timestamp")
                    continue
                if volume is None:
                    logger.warning(f"Skipping quote for {symbol}: missing volume")
                    continue

                # Dedup by timestamp
                last_ts = self._last_timestamps.get(symbol, 0)
                if ts_ms <= last_ts:
                    continue

                md = MarketData(
                    symbol=symbol,
                    price=Decimal(str(latest_price)),
                    bid=Decimal(str(bid_price)),
                    ask=Decimal(str(ask_price)),
                    volume=int(volume),
                    timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                )

                self._last_timestamps[symbol] = ts_ms

                if self._loop:
                    self._loop.call_soon_threadsafe(self._quote_queue.put_nowait, md)
            except Exception as e:
                logger.error(f"Error processing quote for {symbol}: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # Connection callbacks
    # ------------------------------------------------------------------

    def _connect_callback(self):
        self._connected = True
        logger.info("TigerDataSource PushClient connected")

    def _disconnect_callback(self):
        self._connected = False
        logger.warning("TigerDataSource PushClient disconnected")
        if self._loop:
            self._loop.call_soon_threadsafe(asyncio.ensure_future, self._reconnect())

    async def _reconnect(self) -> None:
        for attempt in range(3):
            delay = 2**attempt  # 1, 2, 4
            logger.info(f"TigerDataSource reconnect attempt {attempt + 1}/3 in {delay}s")
            await asyncio.sleep(delay)
            try:
                _ensure_tiger_imports()
                client_config = TigerOpenClientConfig(props_path=self._credentials_path)
                await asyncio.to_thread(
                    self._push_client.connect,
                    client_config.tiger_id,
                    client_config.private_key,
                )
                # Re-subscribe all symbols
                if self._subscribed_symbols:
                    await asyncio.to_thread(
                        self._push_client.subscribe_quote,
                        list(self._subscribed_symbols),
                    )
                self._connected = True
                logger.info("TigerDataSource reconnection successful")
                return
            except Exception as e:
                logger.error(f"TigerDataSource reconnection failed: {e}")
        logger.error("TigerDataSource max reconnect attempts reached")
