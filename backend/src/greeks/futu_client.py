# backend/src/greeks/futu_client.py
"""Futu OpenD client for fetching option Greeks.

This module provides the FutuGreeksClient for connecting to Futu OpenD
and fetching option Greeks using the moomoo SDK.

Connection management:
    - Uses OpenQuoteContext for quote data
    - Handles sync→async bridging for use in FastAPI
    - Manages subscriptions and connection lifecycle

Threading:
    - moomoo SDK callbacks run on separate threads
    - Use asyncio.run_coroutine_threadsafe for async bridging
"""

import asyncio
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from functools import partial
from typing import Any

logger = logging.getLogger(__name__)

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds


@dataclass
class FutuOptionGreeks:
    """Raw option Greeks from Futu API.

    Attributes:
        code: Option symbol (e.g., "US.AAPL240119C00150000")
        delta: Option delta (-1 to 1)
        gamma: Option gamma
        vega: Option vega
        theta: Option theta
        implied_volatility: Implied volatility (decimal)
        underlying_price: Current underlying price
    """

    code: str
    delta: Decimal
    gamma: Decimal
    vega: Decimal
    theta: Decimal
    implied_volatility: Decimal
    underlying_price: Decimal


class FutuClientError(Exception):
    """Error from Futu client operations."""

    pass


class FutuConnectionError(FutuClientError):
    """Connection-related error (retryable)."""

    pass


class FutuAPIError(FutuClientError):
    """API call error (may or may not be retryable)."""

    pass


class FutuGreeksClient:
    """Client for fetching option Greeks from Futu OpenD.

    This client manages the connection to Futu OpenD and provides
    methods to fetch option Greeks.

    Usage:
        client = FutuGreeksClient(host="127.0.0.1", port=11111)
        client.connect()
        try:
            greeks = client.get_option_greeks(["US.AAPL240119C00150000"])
        finally:
            client.close()

    Or with context manager:
        with FutuGreeksClient(host="127.0.0.1", port=11111) as client:
            greeks = client.get_option_greeks(["US.AAPL240119C00150000"])

    Attributes:
        _host: Futu OpenD host address
        _port: Futu OpenD port
        _quote_ctx: OpenQuoteContext instance (None when disconnected)
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11111):
        """Initialize the Futu Greeks client.

        Args:
            host: Futu OpenD host address.
            port: Futu OpenD port.
        """
        self._host = host
        self._port = port
        self._quote_ctx: Any = None
        self._connected = False

    def connect(self) -> None:
        """Connect to Futu OpenD.

        Raises:
            FutuClientError: If connection fails or moomoo not installed.
        """
        if self._connected:
            return

        try:
            from moomoo import OpenQuoteContext  # noqa: PLC0415
        except ImportError as e:
            raise FutuClientError(
                "moomoo SDK not installed. Install with: pip install moomoo-api"
            ) from e

        try:
            self._quote_ctx = OpenQuoteContext(host=self._host, port=self._port)
            self._connected = True
            logger.info(f"Connected to Futu OpenD at {self._host}:{self._port}")
        except Exception as e:
            raise FutuClientError(f"Failed to connect to Futu OpenD: {e}") from e

    def close(self) -> None:
        """Close the connection to Futu OpenD."""
        if self._quote_ctx is not None:
            try:
                self._quote_ctx.close()
            except Exception as e:
                logger.warning(f"Error closing Futu connection: {e}")
            finally:
                self._quote_ctx = None
                self._connected = False
                logger.info("Disconnected from Futu OpenD")

    def __enter__(self) -> "FutuGreeksClient":
        """Context manager entry - connect to Futu OpenD."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - close connection."""
        self.close()

    @contextmanager
    def _ensure_connected(self):
        """Ensure we have a valid connection."""
        if not self._connected or self._quote_ctx is None:
            raise FutuClientError("Not connected to Futu OpenD. Call connect() first.")
        yield self._quote_ctx

    def get_option_greeks(self, symbols: list[str]) -> dict[str, FutuOptionGreeks]:
        """Fetch option Greeks for a list of option symbols.

        This method subscribes to the symbols, fetches their quotes,
        and extracts Greeks data.

        Args:
            symbols: List of option symbols (e.g., ["US.AAPL240119C00150000"]).

        Returns:
            Dict mapping symbol to FutuOptionGreeks.
            Symbols without valid Greeks are excluded.

        Raises:
            FutuClientError: If not connected or API call fails.
        """
        if not symbols:
            return {}

        with self._ensure_connected() as quote_ctx:
            try:
                from moomoo import RET_OK, SubType  # noqa: PLC0415
            except ImportError as e:
                raise FutuClientError("moomoo SDK not installed") from e

            # Subscribe to option quotes
            ret, err = quote_ctx.subscribe(symbols, [SubType.QUOTE])
            if ret != RET_OK:
                logger.warning(f"Failed to subscribe to symbols: {err}")
                return {}

            # Fetch quotes
            ret, data = quote_ctx.get_stock_quote(symbols)
            if ret != RET_OK:
                logger.warning(f"Failed to get stock quote: {data}")
                return {}

            # Parse Greeks from quote data
            result: dict[str, FutuOptionGreeks] = {}
            for _, row in data.iterrows():
                code = row.get("code", "")
                if not code:
                    continue

                # Extract Greeks - moomoo returns these fields for options
                delta = row.get("option_delta")
                gamma = row.get("option_gamma")
                vega = row.get("option_vega")
                theta = row.get("option_theta")
                iv = row.get("option_implied_volatility")
                underlying_price = row.get("price")  # Current price

                # Skip if Greeks are missing
                if delta is None or gamma is None or vega is None or theta is None:
                    logger.debug(f"Missing Greeks for {code}, skipping")
                    continue

                result[code] = FutuOptionGreeks(
                    code=code,
                    delta=Decimal(str(delta)) if delta is not None else Decimal("0"),
                    gamma=Decimal(str(gamma)) if gamma is not None else Decimal("0"),
                    vega=Decimal(str(vega)) if vega is not None else Decimal("0"),
                    theta=Decimal(str(theta)) if theta is not None else Decimal("0"),
                    implied_volatility=(Decimal(str(iv)) if iv is not None else Decimal("0")),
                    underlying_price=(
                        Decimal(str(underlying_price))
                        if underlying_price is not None
                        else Decimal("0")
                    ),
                )

            return result

    def get_underlying_price(self, symbols: list[str]) -> dict[str, Decimal]:
        """Fetch current prices for underlying symbols.

        Args:
            symbols: List of underlying symbols (e.g., ["US.AAPL"]).

        Returns:
            Dict mapping symbol to current price.

        Raises:
            FutuClientError: If not connected or API call fails.
        """
        if not symbols:
            return {}

        with self._ensure_connected() as quote_ctx:
            try:
                from moomoo import RET_OK, SubType  # noqa: PLC0415
            except ImportError as e:
                raise FutuClientError("moomoo SDK not installed") from e

            # Subscribe and fetch quotes
            ret, err = quote_ctx.subscribe(symbols, [SubType.QUOTE])
            if ret != RET_OK:
                logger.warning(f"Failed to subscribe to symbols: {err}")
                return {}

            ret, data = quote_ctx.get_stock_quote(symbols)
            if ret != RET_OK:
                logger.warning(f"Failed to get stock quote: {data}")
                return {}

            result: dict[str, Decimal] = {}
            for _, row in data.iterrows():
                code = row.get("code", "")
                price = row.get("last_price")
                if code and price is not None:
                    result[code] = Decimal(str(price))

            return result


class AsyncFutuGreeksClient:
    """Async wrapper for FutuGreeksClient.

    Provides async methods for use in FastAPI/asyncio contexts.
    Runs blocking operations in a thread pool.

    Usage:
        async with AsyncFutuGreeksClient(host="127.0.0.1", port=11111) as client:
            greeks = await client.get_option_greeks(["US.AAPL240119C00150000"])
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 11111):
        """Initialize async client.

        Args:
            host: Futu OpenD host address.
            port: Futu OpenD port.
        """
        self._sync_client = FutuGreeksClient(host, port)
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> None:
        """Connect to Futu OpenD asynchronously."""
        self._loop = asyncio.get_running_loop()
        await self._loop.run_in_executor(None, self._sync_client.connect)

    async def close(self) -> None:
        """Close connection asynchronously."""
        if self._loop:
            await self._loop.run_in_executor(None, self._sync_client.close)

    async def __aenter__(self) -> "AsyncFutuGreeksClient":
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def get_option_greeks(self, symbols: list[str]) -> dict[str, FutuOptionGreeks]:
        """Fetch option Greeks asynchronously.

        Args:
            symbols: List of option symbols.

        Returns:
            Dict mapping symbol to FutuOptionGreeks.
        """
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return await self._loop.run_in_executor(
            None, partial(self._sync_client.get_option_greeks, symbols)
        )

    async def get_underlying_price(self, symbols: list[str]) -> dict[str, Decimal]:
        """Fetch underlying prices asynchronously.

        Args:
            symbols: List of underlying symbols.

        Returns:
            Dict mapping symbol to price.
        """
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return await self._loop.run_in_executor(
            None, partial(self._sync_client.get_underlying_price, symbols)
        )


class SharedFutuClient:
    """Thread-safe shared Futu client with connection pooling.

    Provides a singleton-like pattern for sharing a Futu connection
    across multiple callers. Handles automatic reconnection on failure.

    Usage:
        client = SharedFutuClient.get_instance()
        greeks = client.get_option_greeks(symbols)

    Or configure once at startup:
        SharedFutuClient.configure(host="127.0.0.1", port=11111)
        client = SharedFutuClient.get_instance()
    """

    _instance: "SharedFutuClient | None" = None
    _lock = threading.Lock()
    _host: str = "127.0.0.1"
    _port: int = 11111

    def __init__(self):
        """Initialize shared client (use get_instance instead)."""
        self._client: FutuGreeksClient | None = None
        self._client_lock = threading.Lock()
        self._last_error_time: float = 0
        self._error_count: int = 0

    @classmethod
    def configure(cls, host: str = "127.0.0.1", port: int = 11111) -> None:
        """Configure the shared client settings.

        Call this before get_instance() to set connection parameters.

        Args:
            host: Futu OpenD host address.
            port: Futu OpenD port.
        """
        with cls._lock:
            cls._host = host
            cls._port = port
            # Reset instance if config changes
            if cls._instance is not None:
                cls._instance.close()
                cls._instance = None

    @classmethod
    def get_instance(cls) -> "SharedFutuClient":
        """Get the shared client instance.

        Returns:
            SharedFutuClient instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_client(self) -> FutuGreeksClient:
        """Get or create the underlying client with reconnection logic."""
        with self._client_lock:
            # Check if we should back off due to recent errors
            if self._error_count > 0:
                backoff_time = min(30, 2**self._error_count)
                if time.time() - self._last_error_time < backoff_time:
                    raise FutuConnectionError(f"Connection in backoff period ({backoff_time}s)")

            if self._client is None or not self._client._connected:
                try:
                    self._client = FutuGreeksClient(host=self._host, port=self._port)
                    self._client.connect()
                    # Reset error tracking on successful connect
                    self._error_count = 0
                except Exception as e:
                    self._error_count += 1
                    self._last_error_time = time.time()
                    raise FutuConnectionError(f"Failed to connect: {e}") from e

            return self._client

    def get_option_greeks(
        self,
        symbols: list[str],
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> dict[str, FutuOptionGreeks]:
        """Fetch option Greeks with automatic retry.

        Args:
            symbols: List of option symbols.
            max_retries: Maximum retry attempts on transient failures.

        Returns:
            Dict mapping symbol to FutuOptionGreeks.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                client = self._get_client()
                return client.get_option_greeks(symbols)
            except FutuConnectionError:
                # Connection error - force reconnect on next attempt
                with self._client_lock:
                    if self._client:
                        try:
                            self._client.close()
                        except Exception as close_err:
                            logger.debug(f"Error closing client during retry: {close_err}")
                        self._client = None
                last_error = FutuConnectionError("Connection failed")
                if attempt < max_retries - 1:
                    time.sleep(DEFAULT_RETRY_DELAY * (attempt + 1))
            except Exception as e:
                last_error = e
                break

        logger.warning(f"Failed to get option Greeks after {max_retries} attempts: {last_error}")
        return {}

    def get_underlying_price(
        self,
        symbols: list[str],
        max_retries: int = DEFAULT_MAX_RETRIES,
    ) -> dict[str, Decimal]:
        """Fetch underlying prices with automatic retry.

        Args:
            symbols: List of underlying symbols.
            max_retries: Maximum retry attempts.

        Returns:
            Dict mapping symbol to price.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                client = self._get_client()
                return client.get_underlying_price(symbols)
            except FutuConnectionError:
                with self._client_lock:
                    if self._client:
                        try:
                            self._client.close()
                        except Exception as close_err:
                            logger.debug(f"Error closing client during retry: {close_err}")
                        self._client = None
                last_error = FutuConnectionError("Connection failed")
                if attempt < max_retries - 1:
                    time.sleep(DEFAULT_RETRY_DELAY * (attempt + 1))
            except Exception as e:
                last_error = e
                break

        logger.warning(
            f"Failed to get underlying prices after {max_retries} attempts: {last_error}"
        )
        return {}

    def close(self) -> None:
        """Close the shared client connection."""
        with self._client_lock:
            if self._client:
                try:
                    self._client.close()
                except Exception as e:
                    logger.debug(f"Error closing shared client: {e}")
                self._client = None

    @classmethod
    def shutdown(cls) -> None:
        """Shutdown the shared client instance.

        Call this at application shutdown to cleanly close connections.
        """
        with cls._lock:
            if cls._instance:
                cls._instance.close()
                cls._instance = None
