"""Greeks calculator module.

This module provides the GreeksCalculator for fetching raw Greeks from providers
and converting them to dollar terms.

Classes:
    - PositionInfo: Minimal position info needed for Greeks calculation
    - RawGreeks: Raw Greeks from a provider (per-share, not dollarized)
    - FutuGreeksProvider: Fetches Greeks from Futu OpenD API
    - GreeksCalculator: Main calculator with provider fallback support

Functions:
    - convert_to_dollar_greeks: Convert raw per-share Greeks to dollar terms
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol

from src.greeks.models import GreeksDataSource, GreeksModel, PositionGreeks

if TYPE_CHECKING:
    from src.greeks.iv_cache import IVCacheManager

logger = logging.getLogger(__name__)


@dataclass
class PositionInfo:
    """Minimal position info needed for Greeks calculation.

    Attributes:
        position_id: Unique identifier for the position
        symbol: Option symbol (e.g., "AAPL240119C00150000")
        underlying_symbol: Underlying stock symbol (e.g., "AAPL")
        quantity: Position quantity (positive=long, negative=short)
        multiplier: Contract multiplier (US options: 100)
        option_type: "call" or "put"
        strike: Option strike price
        expiry: Expiration date as ISO string (e.g., "2024-01-19")
    """

    position_id: int
    symbol: str
    underlying_symbol: str
    quantity: int
    multiplier: int
    option_type: str  # "call" or "put"
    strike: Decimal
    expiry: str  # ISO date


@dataclass
class RawGreeks:
    """Raw Greeks from a provider (per-share, not dollarized).

    All values are per-share (before multiplier and quantity scaling).

    Attributes:
        delta: Per-share delta (-1 to 1)
        gamma: Per-share gamma
        vega: Per-share vega (per 1% IV)
        theta: Per-share theta (per day)
        implied_vol: Implied volatility (decimal, e.g., 0.25 = 25%)
        underlying_price: Current underlying spot price
    """

    delta: Decimal  # Per-share delta (-1 to 1)
    gamma: Decimal  # Per-share gamma
    vega: Decimal  # Per-share vega (per 1% IV)
    theta: Decimal  # Per-share theta (per day)
    implied_vol: Decimal  # Implied volatility (decimal, e.g., 0.25 = 25%)
    underlying_price: Decimal


class GreeksProvider(Protocol):
    """Protocol for fetching Greeks from a data source."""

    @property
    def source(self) -> GreeksDataSource:
        """The data source identifier."""
        ...

    def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
        """Fetch raw Greeks for positions.

        Args:
            positions: List of PositionInfo to fetch Greeks for.

        Returns:
            Dict mapping position_id to RawGreeks.
        """
        ...


class FutuGreeksProvider:
    """Fetches Greeks from Futu OpenD API.

    Uses SharedFutuClient for connection management with automatic
    reconnection and retry logic.

    Attributes:
        _use_shared: Whether to use the shared client (default True)
        _host: Futu OpenD host address (for non-shared mode)
        _port: Futu OpenD port (for non-shared mode)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 11111,
        use_shared: bool = True,
    ):
        """Initialize the provider.

        Args:
            host: Futu OpenD host address.
            port: Futu OpenD port.
            use_shared: If True, use SharedFutuClient for connection pooling.
        """
        self._host = host
        self._port = port
        self._use_shared = use_shared

        # Configure shared client if using it
        if use_shared:
            from src.greeks.futu_client import SharedFutuClient

            SharedFutuClient.configure(host=host, port=port)

    @property
    def source(self) -> GreeksDataSource:
        """The data source identifier."""
        return GreeksDataSource.FUTU

    def _symbol_to_futu(self, symbol: str, underlying: str) -> str:
        """Convert internal symbol to Futu format.

        Internal: "AAPL240119C00150000"
        Futu: "US.AAPL240119C150000"

        Args:
            symbol: Internal option symbol.
            underlying: Underlying symbol (e.g., "AAPL").

        Returns:
            Futu-formatted symbol.
        """
        # Futu US options format: US.{underlying}{YYMMDD}{C/P}{strike}
        # Internal format: {underlying}{YYMMDD}{C/P}{strike with leading zeros}
        # For now, use a simple prefix approach
        return f"US.{symbol}"

    def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
        """Fetch Greeks from Futu OpenD API.

        Args:
            positions: List of PositionInfo to fetch Greeks for.

        Returns:
            Dict mapping position_id to RawGreeks.
            Positions without valid Greeks are excluded.
        """
        if not positions:
            return {}

        try:
            if self._use_shared:
                from src.greeks.futu_client import SharedFutuClient

                client = SharedFutuClient.get_instance()
            else:
                from src.greeks.futu_client import FutuGreeksClient

                client = FutuGreeksClient(host=self._host, port=self._port)
                client.connect()
        except Exception as e:
            logger.warning(f"Failed to get Futu client: {e}")
            return {}

        try:
            # Build symbol mapping: futu_symbol -> position
            symbol_map: dict[str, PositionInfo] = {}
            futu_symbols: list[str] = []

            for pos in positions:
                futu_sym = self._symbol_to_futu(pos.symbol, pos.underlying_symbol)
                symbol_map[futu_sym] = pos
                futu_symbols.append(futu_sym)

            # Fetch underlying prices for dollar Greeks conversion
            unique_underlyings = list({f"US.{p.underlying_symbol}" for p in positions})
            underlying_prices = client.get_underlying_price(unique_underlyings)

            # Fetch option Greeks
            futu_greeks = client.get_option_greeks(futu_symbols)

            # Convert to RawGreeks
            result: dict[int, RawGreeks] = {}
            for futu_sym, greeks in futu_greeks.items():
                if futu_sym not in symbol_map:
                    continue

                pos = symbol_map[futu_sym]

                # Get underlying price (prefer from underlying quote, fallback to option data)
                underlying_key = f"US.{pos.underlying_symbol}"
                underlying_price = underlying_prices.get(underlying_key, greeks.underlying_price)

                if underlying_price <= 0:
                    logger.warning(f"Invalid underlying price for {pos.symbol}, skipping")
                    continue

                result[pos.position_id] = RawGreeks(
                    delta=greeks.delta,
                    gamma=greeks.gamma,
                    vega=greeks.vega,
                    theta=greeks.theta,
                    implied_vol=greeks.implied_volatility,
                    underlying_price=underlying_price,
                )

            return result

        except Exception as e:
            logger.warning(f"Error fetching Greeks from Futu: {e}")
            return {}
        finally:
            # Only close if not using shared client
            if not self._use_shared:
                try:
                    client.close()
                except Exception as close_err:
                    logger.debug(f"Error closing Futu client: {close_err}")


class ModelGreeksProvider:
    """Calculates Greeks using Black-Scholes model.

    Used as fallback when Futu API is unavailable.
    Can optionally use IVCacheManager for cached IV values.

    Attributes:
        _iv_cache: Optional IV cache manager
        _default_iv: Default IV when no cache available
        _risk_free_rate: Risk-free interest rate
    """

    def __init__(
        self,
        iv_cache: IVCacheManager | None = None,
        default_iv: Decimal = Decimal("0.30"),
        risk_free_rate: Decimal = Decimal("0.05"),
    ):
        """Initialize model provider.

        Args:
            iv_cache: Optional IV cache manager for cached IV lookup
            default_iv: Default IV when cache miss (0.30 = 30%)
            risk_free_rate: Risk-free rate (0.05 = 5%)
        """
        self._iv_cache: Any = iv_cache
        self._default_iv = default_iv
        self._risk_free_rate = risk_free_rate
        self._underlying_prices: dict[str, Decimal] = {}

    @property
    def source(self) -> GreeksDataSource:
        """The data source identifier."""
        return GreeksDataSource.MODEL

    def set_underlying_prices(self, prices: dict[str, Decimal]) -> None:
        """Set underlying prices for calculation.

        Args:
            prices: Dict mapping underlying symbol to price
        """
        self._underlying_prices = prices

    def _get_underlying_price(self, symbol: str) -> Decimal | None:
        """Get underlying price.

        Args:
            symbol: Underlying symbol

        Returns:
            Price or None if not available
        """
        return self._underlying_prices.get(symbol)

    def _parse_expiry(self, expiry: str) -> date:
        """Parse expiry string to date.

        Args:
            expiry: ISO date string (YYYY-MM-DD)

        Returns:
            date object
        """
        return date.fromisoformat(expiry)

    def _time_to_expiry_years(self, expiry_date: date) -> Decimal:
        """Calculate time to expiry in years.

        Args:
            expiry_date: Expiration date

        Returns:
            Time in years (calendar days / 365)
        """
        today = date.today()
        days = (expiry_date - today).days

        if days <= 0:
            return Decimal("0.001")  # Minimum for near-expiry

        # Use 365 for calendar days (standard for options)
        return Decimal(str(days)) / Decimal("365")

    def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
        """Calculate Greeks using Black-Scholes model.

        Args:
            positions: List of PositionInfo to calculate Greeks for.

        Returns:
            Dict mapping position_id to RawGreeks.
        """
        from src.greeks.black_scholes import calculate_bs_greeks

        if not positions:
            return {}

        result: dict[int, RawGreeks] = {}

        for pos in positions:
            # Get underlying price
            underlying_price = self._get_underlying_price(pos.underlying_symbol)
            if underlying_price is None or underlying_price <= 0:
                logger.warning(
                    f"No underlying price for {pos.underlying_symbol}, skipping {pos.symbol}"
                )
                continue

            # Get IV (use default for now, IV cache integration later)
            iv = self._default_iv

            # Calculate time to expiry
            try:
                expiry_date = self._parse_expiry(pos.expiry)
                time_years = self._time_to_expiry_years(expiry_date)
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid expiry {pos.expiry} for {pos.symbol}: {e}")
                continue

            # Calculate Greeks
            try:
                bs_result = calculate_bs_greeks(
                    spot=underlying_price,
                    strike=pos.strike,
                    time_to_expiry_years=time_years,
                    risk_free_rate=self._risk_free_rate,
                    volatility=iv,
                    is_call=(pos.option_type == "call"),
                )

                result[pos.position_id] = RawGreeks(
                    delta=bs_result.delta,
                    gamma=bs_result.gamma,
                    vega=bs_result.vega,
                    theta=bs_result.theta,
                    implied_vol=iv,
                    underlying_price=underlying_price,
                )
            except Exception as e:
                logger.warning(f"Error calculating BS Greeks for {pos.symbol}: {e}")
                continue

        return result


def convert_to_dollar_greeks(
    position: PositionInfo,
    raw: RawGreeks,
    source: GreeksDataSource,
    model: GreeksModel | None = None,
) -> PositionGreeks:
    """Convert raw per-share Greeks to dollar terms.

    Formulas:
    - dollar_delta = delta x quantity x multiplier x underlying_price
    - gamma_dollar = gamma x quantity x multiplier x underlying_price^2
    - gamma_pnl_1pct = 0.5 x gamma x quantity x multiplier x (0.01 x underlying_price)^2
    - vega_per_1pct = vega x quantity x multiplier (already per 1% IV)
    - theta_per_day = theta x quantity x multiplier

    Sign convention:
    - Long call: positive delta, positive gamma
    - Short call: negative delta, negative gamma
    - quantity sign handles direction

    Args:
        position: The position info.
        raw: Raw Greeks from provider.
        source: Data source identifier.
        model: Calculation model used (optional).

    Returns:
        PositionGreeks with dollar-denominated values.
    """
    qty = Decimal(position.quantity)
    mult = Decimal(position.multiplier)
    price = raw.underlying_price

    # Calculate dollar Greeks
    dollar_delta = raw.delta * qty * mult * price
    gamma_dollar = raw.gamma * qty * mult * price * price
    gamma_pnl_1pct = Decimal("0.5") * raw.gamma * qty * mult * (Decimal("0.01") * price) ** 2
    vega_per_1pct = raw.vega * qty * mult
    theta_per_day = raw.theta * qty * mult

    return PositionGreeks(
        position_id=position.position_id,
        symbol=position.symbol,
        underlying_symbol=position.underlying_symbol,
        quantity=position.quantity,
        multiplier=position.multiplier,
        underlying_price=price,
        option_type=position.option_type,  # type: ignore
        strike=position.strike,
        expiry=position.expiry,
        dollar_delta=dollar_delta,
        gamma_dollar=gamma_dollar,
        gamma_pnl_1pct=gamma_pnl_1pct,
        vega_per_1pct=vega_per_1pct,
        theta_per_day=theta_per_day,
        source=source,
        model=model,
        valid=True,
    )


def _create_invalid_position_greeks(
    position: PositionInfo,
    source: GreeksDataSource,
) -> PositionGreeks:
    """Create a PositionGreeks object marked as invalid.

    Used when no Greeks data is available for a position.

    Args:
        position: The position info.
        source: Data source identifier (for tracking).

    Returns:
        PositionGreeks with valid=False and zero values.
    """
    return PositionGreeks(
        position_id=position.position_id,
        symbol=position.symbol,
        underlying_symbol=position.underlying_symbol,
        quantity=position.quantity,
        multiplier=position.multiplier,
        underlying_price=Decimal("0"),
        option_type=position.option_type,  # type: ignore
        strike=position.strike,
        expiry=position.expiry,
        dollar_delta=Decimal("0"),
        gamma_dollar=Decimal("0"),
        gamma_pnl_1pct=Decimal("0"),
        vega_per_1pct=Decimal("0"),
        theta_per_day=Decimal("0"),
        source=source,
        model=None,
        valid=False,
        quality_warnings=["No Greeks data available"],
    )


class GreeksCalculator:
    """Calculates position Greeks using configured providers.

    Supports fallback: Try primary provider first, fall back to fallback if needed.

    Attributes:
        _primary: Primary Greeks provider.
        _fallback: Optional fallback provider.
    """

    def __init__(
        self,
        primary_provider: GreeksProvider | None = None,
        fallback_provider: GreeksProvider | None = None,
    ):
        """Initialize the calculator with providers.

        Args:
            primary_provider: Primary Greeks provider (defaults to FutuGreeksProvider).
            fallback_provider: Optional fallback provider.
        """
        self._primary: GreeksProvider = primary_provider or FutuGreeksProvider()
        self._fallback: GreeksProvider | None = fallback_provider

    def calculate(self, positions: list[PositionInfo]) -> list[PositionGreeks]:
        """Calculate Greeks for all positions.

        1. Fetch from primary provider
        2. For positions without Greeks, try fallback
        3. Mark positions without any Greeks as invalid

        Args:
            positions: List of PositionInfo to calculate Greeks for.

        Returns:
            List of PositionGreeks with calculated values.
        """
        if not positions:
            return []

        results: list[PositionGreeks] = []

        # Step 1: Fetch from primary provider
        primary_greeks = self._primary.fetch_greeks(positions)

        # Track which positions still need Greeks
        missing_positions: list[PositionInfo] = []
        for position in positions:
            if position.position_id in primary_greeks:
                # Convert to dollar Greeks
                raw = primary_greeks[position.position_id]
                result = convert_to_dollar_greeks(position, raw, self._primary.source)
                results.append(result)
            else:
                missing_positions.append(position)

        # Step 2: Try fallback for missing positions
        if missing_positions and self._fallback is not None:
            fallback_greeks = self._fallback.fetch_greeks(missing_positions)
            remaining_missing: list[PositionInfo] = []

            for position in missing_positions:
                if position.position_id in fallback_greeks:
                    raw = fallback_greeks[position.position_id]
                    result = convert_to_dollar_greeks(position, raw, self._fallback.source)
                    results.append(result)
                else:
                    remaining_missing.append(position)

            missing_positions = remaining_missing

        # Step 3: Mark remaining positions as invalid
        for position in missing_positions:
            result = _create_invalid_position_greeks(position, self._primary.source)
            results.append(result)

        return results

    def calculate_single(self, position: PositionInfo) -> PositionGreeks:
        """Calculate Greeks for a single position.

        Args:
            position: The PositionInfo to calculate Greeks for.

        Returns:
            PositionGreeks with calculated values.
        """
        results = self.calculate([position])
        return results[0]
