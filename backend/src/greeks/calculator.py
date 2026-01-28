"""Greeks calculator module.

This module provides the GreeksCalculator for fetching raw Greeks from providers
and converting them to dollar terms.

Classes:
    - PositionInfo: Minimal position info needed for Greeks calculation
    - RawGreeks: Raw Greeks from a provider (per-share, not dollarized)
    - FutuGreeksProvider: Stub implementation for Futu API integration
    - GreeksCalculator: Main calculator with provider fallback support

Functions:
    - convert_to_dollar_greeks: Convert raw per-share Greeks to dollar terms
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from src.greeks.models import GreeksDataSource, GreeksModel, PositionGreeks


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
    """Fetches Greeks from Futu API.

    This is a stub - actual Futu integration will be added later.
    """

    @property
    def source(self) -> GreeksDataSource:
        """The data source identifier."""
        return GreeksDataSource.FUTU

    def fetch_greeks(self, positions: list[PositionInfo]) -> dict[int, RawGreeks]:
        """Stub: Returns empty dict. Real implementation uses FutuClient.

        Args:
            positions: List of PositionInfo to fetch Greeks for.

        Returns:
            Empty dict (stub implementation).
        """
        # TODO: Integrate with FutuClient to fetch real Greeks
        return {}


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
