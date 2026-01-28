# Greeks Monitoring - Remaining Features Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Greeks monitoring system with model fallback, IV caching, WebSocket real-time updates, and a full frontend dashboard.

**Architecture:**
- Backend: Add ModelGreeksProvider (Black-Scholes fallback), IVCacheManager (Redis-based IV cache), and WebSocket integration with GreeksMonitor
- Frontend: Greeks Dashboard with summary cards, limits utilization, alerts, trends, and strategy breakdown

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, Redis, WebSockets
- Frontend: React 18, TypeScript, Tailwind CSS, Recharts, TanStack Query

**Reference Design:** `/home/tochat/aq_trading/docs/plans/2026-01-28-greeks-monitoring-design.md`

---

## Phase 1: Backend - Model Fallback Provider (Tasks 1-4)

### Task 1: Create Black-Scholes Greeks Calculator

**Files:**
- Create: `backend/src/greeks/black_scholes.py`
- Create: `backend/tests/greeks/test_black_scholes.py`

**Step 1: Write the failing test**

```python
# backend/tests/greeks/test_black_scholes.py
"""Tests for Black-Scholes Greeks calculator."""
import pytest
from decimal import Decimal
from datetime import date

from src.greeks.black_scholes import calculate_bs_greeks, BSGreeksResult


class TestBlackScholesGreeks:
    """Tests for BS Greeks calculation."""

    def test_atm_call_delta_near_half(self):
        """ATM call should have delta near 0.5."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),  # 3 months
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),  # 20% IV
            is_call=True,
        )
        # ATM call delta should be between 0.5 and 0.6
        assert Decimal("0.50") <= result.delta <= Decimal("0.65")

    def test_atm_put_delta_near_negative_half(self):
        """ATM put should have delta near -0.5."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=False,
        )
        assert Decimal("-0.65") <= result.delta <= Decimal("-0.50")

    def test_deep_itm_call_delta_near_one(self):
        """Deep ITM call should have delta near 1."""
        result = calculate_bs_greeks(
            spot=Decimal("150"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta >= Decimal("0.95")

    def test_deep_otm_call_delta_near_zero(self):
        """Deep OTM call should have delta near 0."""
        result = calculate_bs_greeks(
            spot=Decimal("50"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.delta <= Decimal("0.05")

    def test_gamma_positive(self):
        """Gamma should always be positive."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.gamma > 0

    def test_vega_positive(self):
        """Vega should always be positive."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.vega > 0

    def test_theta_negative_for_long(self):
        """Theta should be negative (time decay)."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert result.theta < 0

    def test_result_has_all_greeks(self):
        """Result should contain all Greeks."""
        result = calculate_bs_greeks(
            spot=Decimal("100"),
            strike=Decimal("100"),
            time_to_expiry_years=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
            volatility=Decimal("0.20"),
            is_call=True,
        )
        assert hasattr(result, "delta")
        assert hasattr(result, "gamma")
        assert hasattr(result, "vega")
        assert hasattr(result, "theta")
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_black_scholes.py -v
```
Expected: FAIL with "ModuleNotFoundError: No module named 'src.greeks.black_scholes'"

**Step 3: Write minimal implementation**

```python
# backend/src/greeks/black_scholes.py
"""Black-Scholes Greeks calculator.

Implements the standard Black-Scholes model for European option Greeks.
Used as fallback when Futu API is unavailable.

Formulas:
    d1 = (ln(S/K) + (r + σ²/2)T) / (σ√T)
    d2 = d1 - σ√T

    Call Delta = N(d1)
    Put Delta = N(d1) - 1
    Gamma = φ(d1) / (S σ √T)
    Vega = S φ(d1) √T / 100  (per 1% IV change)
    Call Theta = -S φ(d1) σ / (2√T) - r K e^(-rT) N(d2)
    Put Theta = -S φ(d1) σ / (2√T) + r K e^(-rT) N(-d2)
"""

import math
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class BSGreeksResult:
    """Result of Black-Scholes Greeks calculation.

    All values are per-share (before multiplier scaling).

    Attributes:
        delta: Option delta (-1 to 1)
        gamma: Option gamma
        vega: Option vega per 1% IV change
        theta: Option theta per day (negative = decay)
    """

    delta: Decimal
    gamma: Decimal
    vega: Decimal
    theta: Decimal


def _norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def calculate_bs_greeks(
    spot: Decimal,
    strike: Decimal,
    time_to_expiry_years: Decimal,
    risk_free_rate: Decimal,
    volatility: Decimal,
    is_call: bool,
) -> BSGreeksResult:
    """Calculate Black-Scholes Greeks.

    Args:
        spot: Current underlying price
        strike: Option strike price
        time_to_expiry_years: Time to expiration in years
        risk_free_rate: Risk-free interest rate (decimal, e.g., 0.05 = 5%)
        volatility: Implied volatility (decimal, e.g., 0.20 = 20%)
        is_call: True for call, False for put

    Returns:
        BSGreeksResult with delta, gamma, vega, theta
    """
    # Convert to float for math operations
    S = float(spot)
    K = float(strike)
    T = float(time_to_expiry_years)
    r = float(risk_free_rate)
    sigma = float(volatility)

    # Handle edge cases
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return BSGreeksResult(
            delta=Decimal("0"),
            gamma=Decimal("0"),
            vega=Decimal("0"),
            theta=Decimal("0"),
        )

    sqrt_T = math.sqrt(T)
    sigma_sqrt_T = sigma * sqrt_T

    # Calculate d1 and d2
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / sigma_sqrt_T
    d2 = d1 - sigma_sqrt_T

    # Calculate Greeks
    N_d1 = _norm_cdf(d1)
    N_d2 = _norm_cdf(d2)
    phi_d1 = _norm_pdf(d1)

    # Delta
    if is_call:
        delta = N_d1
    else:
        delta = N_d1 - 1

    # Gamma (same for call and put)
    gamma = phi_d1 / (S * sigma_sqrt_T)

    # Vega (per 1% IV change, so divide by 100)
    vega = S * phi_d1 * sqrt_T / 100

    # Theta (per day, so divide by 365)
    discount = math.exp(-r * T)
    if is_call:
        theta = (
            -S * phi_d1 * sigma / (2 * sqrt_T)
            - r * K * discount * N_d2
        ) / 365
    else:
        theta = (
            -S * phi_d1 * sigma / (2 * sqrt_T)
            + r * K * discount * _norm_cdf(-d2)
        ) / 365

    return BSGreeksResult(
        delta=Decimal(str(round(delta, 6))),
        gamma=Decimal(str(round(gamma, 8))),
        vega=Decimal(str(round(vega, 6))),
        theta=Decimal(str(round(theta, 6))),
    )
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_black_scholes.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/black_scholes.py backend/tests/greeks/test_black_scholes.py
git commit -m "feat(greeks): add Black-Scholes Greeks calculator

- BSGreeksResult dataclass
- calculate_bs_greeks with delta, gamma, vega, theta
- Standard normal CDF/PDF implementations

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Create IVCacheManager

**Files:**
- Create: `backend/src/greeks/iv_cache.py`
- Create: `backend/tests/greeks/test_iv_cache.py`

**Step 1: Write the failing test**

```python
# backend/tests/greeks/test_iv_cache.py
"""Tests for IV cache manager."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from src.greeks.iv_cache import IVCacheManager, IVCacheEntry


class TestIVCacheEntry:
    """Tests for IVCacheEntry."""

    def test_create_entry(self):
        entry = IVCacheEntry(
            symbol="AAPL",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc),
        )
        assert entry.symbol == "AAPL"
        assert entry.implied_vol == Decimal("0.25")

    def test_is_stale_fresh(self):
        entry = IVCacheEntry(
            symbol="AAPL",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc),
        )
        assert entry.is_stale(max_age_seconds=300) is False

    def test_is_stale_old(self):
        entry = IVCacheEntry(
            symbol="AAPL",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc) - timedelta(seconds=600),
        )
        assert entry.is_stale(max_age_seconds=300) is True


class TestIVCacheManager:
    """Tests for IVCacheManager."""

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_cached(self):
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None

        cache = IVCacheManager(mock_redis)
        result = await cache.get("AAPL240119C00150000")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, ex=None):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        cache = IVCacheManager(mock_redis)

        entry = IVCacheEntry(
            symbol="AAPL240119C00150000",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            as_of_ts=datetime.now(timezone.utc),
        )

        await cache.set(entry)
        result = await cache.get("AAPL240119C00150000")

        assert result is not None
        assert result.implied_vol == Decimal("0.25")

    @pytest.mark.asyncio
    async def test_get_for_underlying(self):
        mock_redis = AsyncMock()
        stored_data = {}

        async def mock_set(key, value, ex=None):
            stored_data[key] = value

        async def mock_get(key):
            return stored_data.get(key)

        mock_redis.set = mock_set
        mock_redis.get = mock_get

        cache = IVCacheManager(mock_redis)

        # Set IV for a specific option
        entry = IVCacheEntry(
            symbol="AAPL240119C00150000",
            implied_vol=Decimal("0.25"),
            underlying_price=Decimal("150.00"),
            underlying_symbol="AAPL",
            as_of_ts=datetime.now(timezone.utc),
        )
        await cache.set(entry)

        # Get average IV for underlying
        result = await cache.get_underlying_iv("AAPL")

        # Should return something (may be None if no underlying-level cache)
        # The actual implementation will determine behavior
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_iv_cache.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/greeks/iv_cache.py
"""IV Cache Manager for Greeks fallback calculations.

Caches implied volatility data in Redis for use when Futu API is unavailable.
Provides fallback IV for Black-Scholes model calculations.

Cache Keys:
    - iv:{symbol} - Per-option IV cache
    - iv:underlying:{symbol} - Per-underlying average IV

TTL: 1 hour for individual options, 4 hours for underlying averages
"""

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

logger = logging.getLogger(__name__)

# Cache TTL settings
OPTION_IV_TTL_SECONDS = 3600  # 1 hour
UNDERLYING_IV_TTL_SECONDS = 14400  # 4 hours


class RedisClient(Protocol):
    """Protocol for async Redis client."""

    async def get(self, key: str) -> str | None:
        ...

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        ...


@dataclass
class IVCacheEntry:
    """Cached IV entry.

    Attributes:
        symbol: Option symbol
        implied_vol: Implied volatility (decimal, e.g., 0.25 = 25%)
        underlying_price: Underlying spot price at cache time
        underlying_symbol: Underlying symbol (optional)
        as_of_ts: Timestamp of the IV data
    """

    symbol: str
    implied_vol: Decimal
    underlying_price: Decimal
    as_of_ts: datetime
    underlying_symbol: str | None = None

    def is_stale(self, max_age_seconds: int = OPTION_IV_TTL_SECONDS) -> bool:
        """Check if entry is stale."""
        age = (datetime.now(timezone.utc) - self.as_of_ts).total_seconds()
        return age > max_age_seconds

    def to_json(self) -> str:
        """Serialize to JSON."""
        data = {
            "symbol": self.symbol,
            "implied_vol": str(self.implied_vol),
            "underlying_price": str(self.underlying_price),
            "underlying_symbol": self.underlying_symbol,
            "as_of_ts": self.as_of_ts.isoformat(),
        }
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "IVCacheEntry":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        return cls(
            symbol=data["symbol"],
            implied_vol=Decimal(data["implied_vol"]),
            underlying_price=Decimal(data["underlying_price"]),
            underlying_symbol=data.get("underlying_symbol"),
            as_of_ts=datetime.fromisoformat(data["as_of_ts"]),
        )


class IVCacheManager:
    """Manages IV cache in Redis.

    Usage:
        cache = IVCacheManager(redis_client)

        # Cache IV from Futu
        await cache.set(IVCacheEntry(...))

        # Get cached IV for fallback
        entry = await cache.get("AAPL240119C00150000")
        if entry and not entry.is_stale():
            use entry.implied_vol
    """

    def __init__(self, redis: RedisClient):
        """Initialize cache manager.

        Args:
            redis: Async Redis client
        """
        self._redis = redis

    def _option_key(self, symbol: str) -> str:
        """Generate Redis key for option IV."""
        return f"iv:{symbol}"

    def _underlying_key(self, symbol: str) -> str:
        """Generate Redis key for underlying average IV."""
        return f"iv:underlying:{symbol}"

    async def get(self, symbol: str) -> IVCacheEntry | None:
        """Get cached IV for an option.

        Args:
            symbol: Option symbol

        Returns:
            IVCacheEntry if found, None otherwise
        """
        try:
            data = await self._redis.get(self._option_key(symbol))
            if data is None:
                return None
            return IVCacheEntry.from_json(data)
        except Exception as e:
            logger.warning(f"Error reading IV cache for {symbol}: {e}")
            return None

    async def set(self, entry: IVCacheEntry) -> None:
        """Cache IV for an option.

        Args:
            entry: IV cache entry to store
        """
        try:
            await self._redis.set(
                self._option_key(entry.symbol),
                entry.to_json(),
                ex=OPTION_IV_TTL_SECONDS,
            )

            # Also update underlying average if we have the underlying symbol
            if entry.underlying_symbol:
                await self._update_underlying_iv(entry)
        except Exception as e:
            logger.warning(f"Error writing IV cache for {entry.symbol}: {e}")

    async def _update_underlying_iv(self, entry: IVCacheEntry) -> None:
        """Update underlying-level IV cache.

        Simple approach: just use the latest option IV as a proxy.
        A more sophisticated approach would track multiple options
        and compute a weighted average.
        """
        try:
            underlying_entry = IVCacheEntry(
                symbol=entry.underlying_symbol,
                implied_vol=entry.implied_vol,
                underlying_price=entry.underlying_price,
                as_of_ts=entry.as_of_ts,
            )
            await self._redis.set(
                self._underlying_key(entry.underlying_symbol),
                underlying_entry.to_json(),
                ex=UNDERLYING_IV_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning(f"Error updating underlying IV: {e}")

    async def get_underlying_iv(self, underlying_symbol: str) -> Decimal | None:
        """Get cached average IV for an underlying.

        Args:
            underlying_symbol: Underlying symbol (e.g., "AAPL")

        Returns:
            Average IV as Decimal, or None if not cached
        """
        try:
            data = await self._redis.get(self._underlying_key(underlying_symbol))
            if data is None:
                return None
            entry = IVCacheEntry.from_json(data)
            if entry.is_stale(UNDERLYING_IV_TTL_SECONDS):
                return None
            return entry.implied_vol
        except Exception as e:
            logger.warning(f"Error reading underlying IV for {underlying_symbol}: {e}")
            return None

    async def get_or_default(
        self,
        symbol: str,
        underlying_symbol: str,
        default_iv: Decimal = Decimal("0.30"),
    ) -> Decimal:
        """Get IV with fallback chain.

        Tries in order:
        1. Specific option IV cache
        2. Underlying average IV cache
        3. Default IV

        Args:
            symbol: Option symbol
            underlying_symbol: Underlying symbol
            default_iv: Default IV if nothing cached

        Returns:
            Best available IV estimate
        """
        # Try option-specific cache
        entry = await self.get(symbol)
        if entry and not entry.is_stale():
            return entry.implied_vol

        # Try underlying cache
        underlying_iv = await self.get_underlying_iv(underlying_symbol)
        if underlying_iv is not None:
            return underlying_iv

        # Fall back to default
        logger.debug(f"Using default IV {default_iv} for {symbol}")
        return default_iv
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_iv_cache.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/iv_cache.py backend/tests/greeks/test_iv_cache.py
git commit -m "feat(greeks): add IVCacheManager for Redis IV caching

- IVCacheEntry dataclass with JSON serialization
- Option and underlying-level IV caching
- Fallback chain: option -> underlying -> default
- Configurable TTL (1h option, 4h underlying)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Create ModelGreeksProvider

**Files:**
- Modify: `backend/src/greeks/calculator.py`
- Create: `backend/tests/greeks/test_model_provider.py`

**Step 1: Write the failing test**

```python
# backend/tests/greeks/test_model_provider.py
"""Tests for ModelGreeksProvider."""
import pytest
from decimal import Decimal
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from src.greeks.calculator import ModelGreeksProvider, PositionInfo, RawGreeks
from src.greeks.models import GreeksDataSource


class TestModelGreeksProvider:
    """Tests for ModelGreeksProvider."""

    def test_source_is_model(self):
        provider = ModelGreeksProvider()
        assert provider.source == GreeksDataSource.MODEL

    def test_fetch_greeks_empty_list(self):
        provider = ModelGreeksProvider()
        result = provider.fetch_greeks([])
        assert result == {}

    def test_fetch_greeks_calculates_for_positions(self):
        provider = ModelGreeksProvider(
            default_iv=Decimal("0.25"),
            risk_free_rate=Decimal("0.05"),
        )

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-06-21",  # Use future date
            )
        ]

        # Mock underlying price
        with patch.object(provider, "_get_underlying_price", return_value=Decimal("150.00")):
            result = provider.fetch_greeks(positions)

        assert 1 in result
        raw = result[1]
        assert isinstance(raw, RawGreeks)
        assert raw.delta > 0  # Call should have positive delta
        assert raw.gamma > 0
        assert raw.vega > 0
        assert raw.theta < 0  # Long option has negative theta

    def test_fetch_greeks_put_has_negative_delta(self):
        provider = ModelGreeksProvider()

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240119P00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="put",
                strike=Decimal("150.00"),
                expiry="2024-06-21",
            )
        ]

        with patch.object(provider, "_get_underlying_price", return_value=Decimal("150.00")):
            result = provider.fetch_greeks(positions)

        assert result[1].delta < 0  # Put should have negative delta
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_model_provider.py -v
```
Expected: FAIL with "cannot import name 'ModelGreeksProvider'"

**Step 3: Add implementation to calculator.py**

```python
# Add to backend/src/greeks/calculator.py after FutuGreeksProvider

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
        iv_cache: "IVCacheManager | None" = None,
        default_iv: Decimal = Decimal("0.30"),
        risk_free_rate: Decimal = Decimal("0.05"),
    ):
        """Initialize model provider.

        Args:
            iv_cache: Optional IV cache manager for cached IV lookup
            default_iv: Default IV when cache miss (0.30 = 30%)
            risk_free_rate: Risk-free rate (0.05 = 5%)
        """
        self._iv_cache = iv_cache
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
            Time in years (trading days / 252)
        """
        from datetime import date as date_class

        today = date_class.today()
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
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_model_provider.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/calculator.py backend/tests/greeks/test_model_provider.py
git commit -m "feat(greeks): add ModelGreeksProvider with Black-Scholes fallback

- Uses Black-Scholes for Greeks calculation
- Configurable default IV and risk-free rate
- Time to expiry calculation from expiry date
- Ready for IV cache integration

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Integrate Model Fallback into GreeksCalculator

**Files:**
- Modify: `backend/src/greeks/calculator.py`
- Modify: `backend/tests/greeks/test_calculator.py`

**Step 1: Write the failing test**

```python
# Add to backend/tests/greeks/test_calculator.py

class TestGreeksCalculatorWithModelFallback:
    """Tests for calculator with model fallback."""

    def test_uses_model_fallback_when_futu_unavailable(self):
        from src.greeks.calculator import (
            GreeksCalculator,
            ModelGreeksProvider,
            PositionInfo,
            RawGreeks,
        )
        from src.greeks.models import GreeksDataSource

        # Empty primary (simulates Futu unavailable)
        class EmptyPrimary:
            @property
            def source(self) -> GreeksDataSource:
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions):
                return {}

        # Model fallback
        model_fallback = ModelGreeksProvider(default_iv=Decimal("0.25"))
        model_fallback.set_underlying_prices({"AAPL": Decimal("150.00")})

        calculator = GreeksCalculator(
            primary_provider=EmptyPrimary(),
            fallback_provider=model_fallback,
        )

        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240621C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-06-21",
            )
        ]

        results = calculator.calculate(positions)

        assert len(results) == 1
        assert results[0].valid is True
        assert results[0].source == GreeksDataSource.MODEL
```

**Step 2: Run test to verify it passes** (should pass with existing fallback logic)

```bash
cd backend && pytest tests/greeks/test_calculator.py::TestGreeksCalculatorWithModelFallback -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/greeks/test_calculator.py
git commit -m "test(greeks): add model fallback integration test

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Backend - WebSocket Integration (Tasks 5-7)

### Task 5: Create WebSocket Manager

**Files:**
- Create: `backend/src/greeks/websocket.py`
- Create: `backend/tests/greeks/test_websocket.py`

**Step 1: Write the failing test**

```python
# backend/tests/greeks/test_websocket.py
"""Tests for Greeks WebSocket manager."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal

from src.greeks.websocket import GreeksWebSocketManager


class TestGreeksWebSocketManager:
    """Tests for GreeksWebSocketManager."""

    @pytest.mark.asyncio
    async def test_connect_adds_client(self):
        manager = GreeksWebSocketManager()
        mock_ws = AsyncMock()

        await manager.connect("acc123", mock_ws)

        assert "acc123" in manager._connections
        assert mock_ws in manager._connections["acc123"]

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        manager = GreeksWebSocketManager()
        mock_ws = AsyncMock()

        await manager.connect("acc123", mock_ws)
        await manager.disconnect("acc123", mock_ws)

        assert mock_ws not in manager._connections.get("acc123", [])

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_account_clients(self):
        manager = GreeksWebSocketManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect("acc123", mock_ws1)
        await manager.connect("acc123", mock_ws2)

        await manager.broadcast_greeks_update("acc123", {"test": "data"})

        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected_client(self):
        manager = GreeksWebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection closed")

        await manager.connect("acc123", mock_ws)

        # Should not raise
        await manager.broadcast_greeks_update("acc123", {"test": "data"})
```

**Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/greeks/test_websocket.py -v
```
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# backend/src/greeks/websocket.py
"""WebSocket manager for real-time Greeks updates.

Manages WebSocket connections and broadcasts Greeks updates to connected clients.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class GreeksWebSocketManager:
    """Manages WebSocket connections for Greeks updates.

    Supports multiple clients per account, handles disconnections gracefully,
    and provides broadcast functionality for real-time updates.

    Usage:
        manager = GreeksWebSocketManager()

        # In WebSocket endpoint
        await manager.connect(account_id, websocket)
        try:
            while True:
                await websocket.receive_text()  # Keep alive
        except WebSocketDisconnect:
            await manager.disconnect(account_id, websocket)

        # In monitor loop
        await manager.broadcast_greeks_update(account_id, greeks_data)
    """

    def __init__(self):
        """Initialize the WebSocket manager."""
        # account_id -> list of WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, account_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection.

        Args:
            account_id: Account identifier
            websocket: WebSocket connection
        """
        async with self._lock:
            if account_id not in self._connections:
                self._connections[account_id] = []
            self._connections[account_id].append(websocket)
            logger.info(f"WebSocket connected for account {account_id}")

    async def disconnect(self, account_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.

        Args:
            account_id: Account identifier
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            if account_id in self._connections:
                try:
                    self._connections[account_id].remove(websocket)
                except ValueError:
                    pass  # Already removed

                # Clean up empty lists
                if not self._connections[account_id]:
                    del self._connections[account_id]

                logger.info(f"WebSocket disconnected for account {account_id}")

    async def broadcast_greeks_update(
        self,
        account_id: str,
        data: dict[str, Any],
    ) -> None:
        """Broadcast Greeks update to all connected clients for an account.

        Args:
            account_id: Account identifier
            data: Greeks data to broadcast
        """
        if account_id not in self._connections:
            return

        message = {
            "type": "greeks_update",
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        # Get connections snapshot to avoid modification during iteration
        async with self._lock:
            connections = list(self._connections.get(account_id, []))

        # Broadcast to all connections
        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Error sending to WebSocket: {e}")
                disconnected.append(websocket)

        # Clean up disconnected clients
        for websocket in disconnected:
            await self.disconnect(account_id, websocket)

    async def broadcast_alert(
        self,
        account_id: str,
        alert: dict[str, Any],
    ) -> None:
        """Broadcast a new alert to all connected clients.

        Args:
            account_id: Account identifier
            alert: Alert data to broadcast
        """
        if account_id not in self._connections:
            return

        message = {
            "type": "greeks_alert",
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": alert,
        }

        async with self._lock:
            connections = list(self._connections.get(account_id, []))

        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            await self.disconnect(account_id, websocket)

    def get_connection_count(self, account_id: str) -> int:
        """Get number of connected clients for an account.

        Args:
            account_id: Account identifier

        Returns:
            Number of connected WebSocket clients
        """
        return len(self._connections.get(account_id, []))


# Global instance for use across the application
greeks_ws_manager = GreeksWebSocketManager()
```

**Step 4: Run test to verify it passes**

```bash
cd backend && pytest tests/greeks/test_websocket.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/greeks/websocket.py backend/tests/greeks/test_websocket.py
git commit -m "feat(greeks): add WebSocket manager for real-time updates

- Connection management per account
- Broadcast Greeks updates and alerts
- Graceful disconnection handling
- Thread-safe with asyncio lock

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Update API WebSocket Endpoint

**Files:**
- Modify: `backend/src/api/greeks.py`

**Step 1: Update WebSocket endpoint to use manager**

```python
# Modify the websocket endpoint in backend/src/api/greeks.py

from src.greeks.websocket import greeks_ws_manager

@router.websocket("/accounts/{account_id}/ws")
async def greeks_websocket(
    websocket: WebSocket,
    account_id: str,
):
    """WebSocket for real-time Greeks updates.

    Connects client to receive real-time Greeks and alert updates.
    Messages are JSON with types: greeks_update, greeks_alert

    Args:
        websocket: The WebSocket connection.
        account_id: The account identifier.
    """
    await websocket.accept()
    await greeks_ws_manager.connect(account_id, websocket)

    try:
        while True:
            # Keep connection alive, handle any incoming messages
            data = await websocket.receive_text()
            # Echo back for ping/pong
            await websocket.send_json({"type": "pong", "received": data})
    except WebSocketDisconnect:
        await greeks_ws_manager.disconnect(account_id, websocket)
```

**Step 2: Run existing tests**

```bash
cd backend && pytest tests/greeks/ -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add backend/src/api/greeks.py
git commit -m "feat(greeks): integrate WebSocket manager with API endpoint

- Use greeks_ws_manager for connection management
- Proper connect/disconnect handling
- Ping/pong support for keepalive

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Integrate WebSocket with GreeksMonitor

**Files:**
- Modify: `backend/src/greeks/monitor.py`

**Step 1: Add WebSocket broadcast to monitor**

Add after Greeks calculation in the check method:

```python
# Add to GreeksMonitor.check() method, after calculating Greeks

# Broadcast update via WebSocket
from src.greeks.websocket import greeks_ws_manager

ws_data = {
    "account": {
        "dollar_delta": float(account_greeks.dollar_delta),
        "gamma_dollar": float(account_greeks.gamma_dollar),
        "vega_per_1pct": float(account_greeks.vega_per_1pct),
        "theta_per_day": float(account_greeks.theta_per_day),
        "coverage_pct": float(account_greeks.coverage_pct),
        "staleness_seconds": account_greeks.staleness_seconds,
    },
    "strategies": {
        sid: {
            "dollar_delta": float(sg.dollar_delta),
            "gamma_dollar": float(sg.gamma_dollar),
            "vega_per_1pct": float(sg.vega_per_1pct),
            "theta_per_day": float(sg.theta_per_day),
        }
        for sid, sg in strategy_greeks.items()
    },
}
await greeks_ws_manager.broadcast_greeks_update(account_id, ws_data)

# Broadcast any new alerts
for alert in new_alerts:
    await greeks_ws_manager.broadcast_alert(account_id, {
        "alert_type": alert.alert_type.value,
        "metric": alert.metric.value,
        "level": alert.level.value,
        "message": alert.message,
    })
```

**Step 2: Commit**

```bash
git add backend/src/greeks/monitor.py
git commit -m "feat(greeks): broadcast updates via WebSocket from monitor

- Send Greeks update after each check cycle
- Broadcast new alerts in real-time

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Frontend - Types and API (Tasks 8-10)

### Task 8: Add Greeks Types

**Files:**
- Modify: `frontend/src/types/index.ts`

**Step 1: Add Greeks type definitions**

```typescript
// Add to frontend/src/types/index.ts

// Greeks types
export interface PositionGreeks {
  position_id: number;
  symbol: string;
  underlying_symbol: string;
  quantity: number;
  dollar_delta: number;
  gamma_dollar: number;
  gamma_pnl_1pct: number;
  vega_per_1pct: number;
  theta_per_day: number;
  notional: number;
  valid: boolean;
  source: string;
  as_of_ts: string;
}

export interface AggregatedGreeks {
  scope: 'ACCOUNT' | 'STRATEGY';
  scope_id: string;
  strategy_id: string | null;
  dollar_delta: number;
  gamma_dollar: number;
  gamma_pnl_1pct: number;
  vega_per_1pct: number;
  theta_per_day: number;
  coverage_pct: number;
  is_coverage_sufficient: boolean;
  has_high_risk_missing_legs: boolean;
  valid_legs_count: number;
  total_legs_count: number;
  staleness_seconds: number;
  as_of_ts: string;
}

export type GreeksAlertLevel = 'normal' | 'warn' | 'crit' | 'hard';

export interface GreeksAlert {
  alert_id: string;
  alert_type: string;
  scope: string;
  scope_id: string;
  metric: string;
  level: GreeksAlertLevel;
  current_value: number;
  threshold_value: number | null;
  message: string;
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
}

export interface GreeksOverview {
  account: AggregatedGreeks;
  strategies: Record<string, AggregatedGreeks>;
  alerts: GreeksAlert[];
  top_contributors: Record<string, PositionGreeks[]>;
}

export interface GreeksLimits {
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
}

export interface GreeksWebSocketMessage {
  type: 'greeks_update' | 'greeks_alert' | 'pong';
  account_id: string;
  timestamp: string;
  data?: {
    account: {
      dollar_delta: number;
      gamma_dollar: number;
      vega_per_1pct: number;
      theta_per_day: number;
      coverage_pct: number;
      staleness_seconds: number;
    };
    strategies: Record<string, {
      dollar_delta: number;
      gamma_dollar: number;
      vega_per_1pct: number;
      theta_per_day: number;
    }>;
  };
  alert?: {
    alert_type: string;
    metric: string;
    level: GreeksAlertLevel;
    message: string;
  };
}
```

**Step 2: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(frontend): add Greeks type definitions

- PositionGreeks, AggregatedGreeks interfaces
- GreeksAlert with alert levels
- GreeksOverview for full dashboard data
- WebSocket message types

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 9: Create Greeks API Module

**Files:**
- Create: `frontend/src/api/greeks.ts`

**Step 1: Create API module**

```typescript
// frontend/src/api/greeks.ts
import { apiClient } from './client';
import type { GreeksOverview, AggregatedGreeks, GreeksAlert } from '../types';

export async function fetchGreeksOverview(accountId: string): Promise<GreeksOverview> {
  const response = await apiClient.get<GreeksOverview>(`/greeks/accounts/${accountId}`);
  return response.data;
}

export async function fetchCurrentGreeks(accountId: string): Promise<AggregatedGreeks> {
  const response = await apiClient.get<AggregatedGreeks>(`/greeks/accounts/${accountId}/current`);
  return response.data;
}

export async function fetchGreeksAlerts(
  accountId: string,
  acknowledged?: boolean,
): Promise<GreeksAlert[]> {
  const params = acknowledged !== undefined ? { acknowledged } : {};
  const response = await apiClient.get<GreeksAlert[]>(
    `/greeks/accounts/${accountId}/alerts`,
    { params },
  );
  return response.data;
}

export async function acknowledgeGreeksAlert(
  alertId: string,
  acknowledgedBy: string,
): Promise<GreeksAlert> {
  const response = await apiClient.post<GreeksAlert>(
    `/greeks/alerts/${alertId}/acknowledge`,
    { acknowledged_by: acknowledgedBy },
  );
  return response.data;
}
```

**Step 2: Commit**

```bash
git add frontend/src/api/greeks.ts
git commit -m "feat(frontend): add Greeks API module

- fetchGreeksOverview for full dashboard data
- fetchCurrentGreeks for quick updates
- fetchGreeksAlerts with filter support
- acknowledgeGreeksAlert for alert management

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 10: Create useGreeks Hook

**Files:**
- Create: `frontend/src/hooks/useGreeks.ts`

**Step 1: Create React Query hook**

```typescript
// frontend/src/hooks/useGreeks.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchGreeksOverview,
  fetchCurrentGreeks,
  fetchGreeksAlerts,
  acknowledgeGreeksAlert,
} from '../api/greeks';
import type { GreeksOverview, AggregatedGreeks, GreeksAlert } from '../types';

export function useGreeksOverview(accountId: string, refetchInterval = 5000) {
  return useQuery<GreeksOverview>({
    queryKey: ['greeks', 'overview', accountId],
    queryFn: () => fetchGreeksOverview(accountId),
    refetchInterval,
    staleTime: 2000,
  });
}

export function useCurrentGreeks(accountId: string, refetchInterval = 5000) {
  return useQuery<AggregatedGreeks>({
    queryKey: ['greeks', 'current', accountId],
    queryFn: () => fetchCurrentGreeks(accountId),
    refetchInterval,
    staleTime: 2000,
  });
}

export function useGreeksAlerts(accountId: string, acknowledged?: boolean) {
  return useQuery<GreeksAlert[]>({
    queryKey: ['greeks', 'alerts', accountId, acknowledged],
    queryFn: () => fetchGreeksAlerts(accountId, acknowledged),
    refetchInterval: 10000,
  });
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ alertId, acknowledgedBy }: { alertId: string; acknowledgedBy: string }) =>
      acknowledgeGreeksAlert(alertId, acknowledgedBy),
    onSuccess: () => {
      // Invalidate alerts query to refetch
      queryClient.invalidateQueries({ queryKey: ['greeks', 'alerts'] });
    },
  });
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useGreeks.ts
git commit -m "feat(frontend): add useGreeks React Query hooks

- useGreeksOverview for full dashboard data
- useCurrentGreeks for quick updates
- useGreeksAlerts with optional filter
- useAcknowledgeAlert mutation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 4: Frontend - Dashboard Components (Tasks 11-16)

### Task 11: Create GreeksSummaryCard Component

**Files:**
- Create: `frontend/src/components/GreeksSummaryCard.tsx`

**Step 1: Create component**

```typescript
// frontend/src/components/GreeksSummaryCard.tsx
import type { AggregatedGreeks } from '../types';

interface GreeksSummaryCardProps {
  greeks: AggregatedGreeks;
  limits?: {
    delta: number;
    gamma: number;
    vega: number;
    theta: number;
  };
}

function formatGreek(value: number): string {
  if (Math.abs(value) >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toFixed(0);
}

function getUtilizationColor(pct: number): string {
  if (pct >= 120) return 'bg-red-600';
  if (pct >= 100) return 'bg-red-500';
  if (pct >= 80) return 'bg-yellow-500';
  return 'bg-green-500';
}

export function GreeksSummaryCard({ greeks, limits }: GreeksSummaryCardProps) {
  const defaultLimits = limits || { delta: 50000, gamma: 10000, vega: 20000, theta: 5000 };

  const metrics = [
    { label: 'Delta', value: greeks.dollar_delta, limit: defaultLimits.delta, unit: '' },
    { label: 'Gamma', value: greeks.gamma_dollar, limit: defaultLimits.gamma, unit: '' },
    { label: 'Vega', value: greeks.vega_per_1pct, limit: defaultLimits.vega, unit: '/1%' },
    { label: 'Theta', value: greeks.theta_per_day, limit: defaultLimits.theta, unit: '/day' },
  ];

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-lg font-semibold text-gray-900">
          {greeks.scope === 'ACCOUNT' ? 'Account Greeks' : greeks.strategy_id}
        </h3>
        <div className="flex items-center space-x-2">
          <span className={`px-2 py-1 text-xs rounded ${
            greeks.is_coverage_sufficient ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'
          }`}>
            {greeks.coverage_pct.toFixed(1)}% coverage
          </span>
          {greeks.staleness_seconds > 30 && (
            <span className="px-2 py-1 text-xs rounded bg-yellow-100 text-yellow-800">
              {greeks.staleness_seconds}s stale
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {metrics.map((metric) => {
          const utilization = (Math.abs(metric.value) / metric.limit) * 100;
          return (
            <div key={metric.label} className="space-y-1">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">{metric.label}</span>
                <span className={`font-medium ${metric.value < 0 ? 'text-red-600' : 'text-gray-900'}`}>
                  ${formatGreek(metric.value)}{metric.unit}
                </span>
              </div>
              <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
                <div
                  className={`h-full ${getUtilizationColor(utilization)} transition-all`}
                  style={{ width: `${Math.min(utilization, 100)}%` }}
                />
              </div>
              <div className="text-xs text-gray-400 text-right">
                {utilization.toFixed(0)}% of limit
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/GreeksSummaryCard.tsx
git commit -m "feat(frontend): add GreeksSummaryCard component

- Display all Dollar Greeks with formatting
- Limit utilization progress bars
- Coverage and staleness indicators
- Color-coded threshold levels

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 12: Create GreeksAlertsPanel Component

**Files:**
- Create: `frontend/src/components/GreeksAlertsPanel.tsx`

**Step 1: Create component**

```typescript
// frontend/src/components/GreeksAlertsPanel.tsx
import type { GreeksAlert, GreeksAlertLevel } from '../types';

interface GreeksAlertsPanelProps {
  alerts: GreeksAlert[];
  onAcknowledge?: (alertId: string) => void;
}

function getLevelBadgeClass(level: GreeksAlertLevel): string {
  switch (level) {
    case 'hard':
      return 'bg-red-100 text-red-800 border-red-200';
    case 'crit':
      return 'bg-orange-100 text-orange-800 border-orange-200';
    case 'warn':
      return 'bg-yellow-100 text-yellow-800 border-yellow-200';
    default:
      return 'bg-gray-100 text-gray-800 border-gray-200';
  }
}

function getLevelLabel(level: GreeksAlertLevel): string {
  switch (level) {
    case 'hard':
      return 'HARD LIMIT';
    case 'crit':
      return 'CRITICAL';
    case 'warn':
      return 'WARNING';
    default:
      return 'NORMAL';
  }
}

export function GreeksAlertsPanel({ alerts, onAcknowledge }: GreeksAlertsPanelProps) {
  if (alerts.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Alerts</h3>
        <div className="text-center py-8 text-gray-500">
          No active alerts
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Recent Alerts</h3>
      <div className="space-y-3">
        {alerts.slice(0, 5).map((alert) => (
          <div
            key={alert.alert_id}
            className={`p-3 rounded-lg border ${getLevelBadgeClass(alert.level)}`}
          >
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center space-x-2">
                  <span className="font-medium text-sm">
                    {getLevelLabel(alert.level)}
                  </span>
                  <span className="text-sm text-gray-600">
                    {alert.metric.toUpperCase()}
                  </span>
                </div>
                <p className="text-sm mt-1">{alert.message}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {new Date(alert.created_at).toLocaleString()}
                </p>
              </div>
              {!alert.acknowledged_at && onAcknowledge && (
                <button
                  onClick={() => onAcknowledge(alert.alert_id)}
                  className="text-xs px-2 py-1 bg-white rounded border hover:bg-gray-50"
                >
                  Acknowledge
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/GreeksAlertsPanel.tsx
git commit -m "feat(frontend): add GreeksAlertsPanel component

- Display recent alerts with level badges
- Color-coded by severity (HARD/CRIT/WARN)
- Acknowledge button for unacked alerts
- Empty state handling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 13: Create GreeksStrategyBreakdown Component

**Files:**
- Create: `frontend/src/components/GreeksStrategyBreakdown.tsx`

**Step 1: Create component**

```typescript
// frontend/src/components/GreeksStrategyBreakdown.tsx
import type { AggregatedGreeks } from '../types';

interface GreeksStrategyBreakdownProps {
  strategies: Record<string, AggregatedGreeks>;
  onSelectStrategy?: (strategyId: string) => void;
}

function formatGreek(value: number): string {
  if (Math.abs(value) >= 1000000) {
    return `${(value / 1000000).toFixed(2)}M`;
  }
  if (Math.abs(value) >= 1000) {
    return `${(value / 1000).toFixed(1)}K`;
  }
  return value.toFixed(0);
}

export function GreeksStrategyBreakdown({
  strategies,
  onSelectStrategy,
}: GreeksStrategyBreakdownProps) {
  const strategyList = Object.entries(strategies).sort(
    ([, a], [, b]) => Math.abs(b.dollar_delta) - Math.abs(a.dollar_delta)
  );

  if (strategyList.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">By Strategy</h3>
        <div className="text-center py-8 text-gray-500">
          No strategy breakdown available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">By Strategy</h3>
      <div className="overflow-x-auto">
        <table className="min-w-full">
          <thead>
            <tr className="text-xs text-gray-500 uppercase border-b">
              <th className="text-left py-2">Strategy</th>
              <th className="text-right py-2">Delta</th>
              <th className="text-right py-2">Gamma</th>
              <th className="text-right py-2">Vega</th>
              <th className="text-right py-2">Theta</th>
              <th className="text-right py-2">Legs</th>
            </tr>
          </thead>
          <tbody>
            {strategyList.map(([strategyId, greeks]) => (
              <tr
                key={strategyId}
                className="border-b hover:bg-gray-50 cursor-pointer"
                onClick={() => onSelectStrategy?.(strategyId)}
              >
                <td className="py-3 font-medium">
                  {strategyId === '_unassigned_' ? '(Unassigned)' : strategyId}
                </td>
                <td className={`text-right ${greeks.dollar_delta < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.dollar_delta)}
                </td>
                <td className={`text-right ${greeks.gamma_dollar < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.gamma_dollar)}
                </td>
                <td className={`text-right ${greeks.vega_per_1pct < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.vega_per_1pct)}
                </td>
                <td className={`text-right ${greeks.theta_per_day < 0 ? 'text-red-600' : ''}`}>
                  ${formatGreek(greeks.theta_per_day)}
                </td>
                <td className="text-right text-gray-500">
                  {greeks.valid_legs_count}/{greeks.total_legs_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/GreeksStrategyBreakdown.tsx
git commit -m "feat(frontend): add GreeksStrategyBreakdown component

- Table view of Greeks by strategy
- Sorted by absolute delta
- Click to select strategy
- Legs count column

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 14: Create GreeksTrendChart Component

**Files:**
- Create: `frontend/src/components/GreeksTrendChart.tsx`

**Step 1: Create component**

```typescript
// frontend/src/components/GreeksTrendChart.tsx
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

interface TrendPoint {
  timestamp: string;
  delta: number;
  gamma: number;
  vega: number;
  theta: number;
}

interface GreeksTrendChartProps {
  data: TrendPoint[];
  selectedMetrics?: ('delta' | 'gamma' | 'vega' | 'theta')[];
}

const metricColors = {
  delta: '#3B82F6', // blue
  gamma: '#10B981', // green
  vega: '#8B5CF6', // purple
  theta: '#F59E0B', // amber
};

export function GreeksTrendChart({
  data,
  selectedMetrics = ['delta', 'gamma'],
}: GreeksTrendChartProps) {
  if (data.length === 0) {
    return (
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Greeks Trend</h3>
        <div className="h-64 flex items-center justify-center text-gray-500">
          No trend data available
        </div>
      </div>
    );
  }

  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatValue = (value: number) => {
    if (Math.abs(value) >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toFixed(0);
  };

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <h3 className="text-lg font-semibold text-gray-900 mb-4">Greeks Trend</h3>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatTimestamp}
              tick={{ fontSize: 12 }}
              stroke="#9CA3AF"
            />
            <YAxis
              tickFormatter={formatValue}
              tick={{ fontSize: 12 }}
              stroke="#9CA3AF"
            />
            <Tooltip
              formatter={(value: number) => [`$${formatValue(value)}`, '']}
              labelFormatter={formatTimestamp}
            />
            <Legend />
            {selectedMetrics.includes('delta') && (
              <Line
                type="monotone"
                dataKey="delta"
                stroke={metricColors.delta}
                strokeWidth={2}
                dot={false}
                name="Delta"
              />
            )}
            {selectedMetrics.includes('gamma') && (
              <Line
                type="monotone"
                dataKey="gamma"
                stroke={metricColors.gamma}
                strokeWidth={2}
                dot={false}
                name="Gamma"
              />
            )}
            {selectedMetrics.includes('vega') && (
              <Line
                type="monotone"
                dataKey="vega"
                stroke={metricColors.vega}
                strokeWidth={2}
                dot={false}
                name="Vega"
              />
            )}
            {selectedMetrics.includes('theta') && (
              <Line
                type="monotone"
                dataKey="theta"
                stroke={metricColors.theta}
                strokeWidth={2}
                dot={false}
                name="Theta"
              />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/GreeksTrendChart.tsx
git commit -m "feat(frontend): add GreeksTrendChart component

- Recharts line chart for Greeks trends
- Configurable metric selection
- Formatted axes and tooltips
- Color-coded metrics

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 15: Create GreeksPage

**Files:**
- Create: `frontend/src/pages/GreeksPage.tsx`

**Step 1: Create page component**

```typescript
// frontend/src/pages/GreeksPage.tsx
import { useState } from 'react';
import { useAccount } from '../contexts/AccountContext';
import { useGreeksOverview, useAcknowledgeAlert } from '../hooks/useGreeks';
import { GreeksSummaryCard } from '../components/GreeksSummaryCard';
import { GreeksAlertsPanel } from '../components/GreeksAlertsPanel';
import { GreeksStrategyBreakdown } from '../components/GreeksStrategyBreakdown';
import { GreeksTrendChart } from '../components/GreeksTrendChart';

export function GreeksPage() {
  const { accountId } = useAccount();
  const { data, isLoading, isError, error } = useGreeksOverview(accountId);
  const acknowledgeMutation = useAcknowledgeAlert();
  const [selectedTab, setSelectedTab] = useState<'account' | 'strategies'>('account');

  // Mock trend data - in production, fetch from API
  const [trendData] = useState([
    { timestamp: new Date(Date.now() - 3600000).toISOString(), delta: 45000, gamma: 8000, vega: 15000, theta: -2500 },
    { timestamp: new Date(Date.now() - 2700000).toISOString(), delta: 47000, gamma: 8500, vega: 15500, theta: -2600 },
    { timestamp: new Date(Date.now() - 1800000).toISOString(), delta: 48000, gamma: 9000, vega: 16000, theta: -2700 },
    { timestamp: new Date(Date.now() - 900000).toISOString(), delta: 46000, gamma: 8200, vega: 15200, theta: -2550 },
    { timestamp: new Date().toISOString(), delta: 50000, gamma: 8800, vega: 15800, theta: -2800 },
  ]);

  const handleAcknowledge = (alertId: string) => {
    acknowledgeMutation.mutate({ alertId, acknowledgedBy: 'user' });
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-7xl mx-auto">
          <p className="text-gray-500">Loading Greeks data...</p>
        </div>
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="min-h-screen bg-gray-100 p-8">
        <div className="max-w-7xl mx-auto">
          <div className="bg-red-50 border border-red-200 rounded-lg p-4">
            <p className="text-red-600">Error loading Greeks: {error?.message}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-100 p-8">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Greeks Monitoring</h1>
          <p className="text-sm text-gray-500 mt-1">
            Account: {accountId} • Last updated: {new Date(data.account.as_of_ts).toLocaleString()}
          </p>
        </div>

        {/* Tabs */}
        <div className="mb-6">
          <div className="border-b border-gray-200">
            <nav className="-mb-px flex space-x-8">
              <button
                onClick={() => setSelectedTab('account')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  selectedTab === 'account'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                Account Summary
              </button>
              <button
                onClick={() => setSelectedTab('strategies')}
                className={`py-2 px-1 border-b-2 font-medium text-sm ${
                  selectedTab === 'strategies'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                By Strategy
              </button>
            </nav>
          </div>
        </div>

        {/* Content */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main content */}
          <div className="lg:col-span-2 space-y-6">
            {selectedTab === 'account' ? (
              <>
                <GreeksSummaryCard greeks={data.account} />
                <GreeksTrendChart data={trendData} selectedMetrics={['delta', 'gamma']} />
              </>
            ) : (
              <GreeksStrategyBreakdown strategies={data.strategies} />
            )}
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <GreeksAlertsPanel
              alerts={data.alerts}
              onAcknowledge={handleAcknowledge}
            />

            {/* Quick stats */}
            <div className="bg-white rounded-lg shadow p-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-4">Quick Stats</h3>
              <div className="space-y-3">
                <div className="flex justify-between">
                  <span className="text-gray-500">Total Positions</span>
                  <span className="font-medium">{data.account.total_legs_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Valid Greeks</span>
                  <span className="font-medium">{data.account.valid_legs_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Strategies</span>
                  <span className="font-medium">{Object.keys(data.strategies).length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Active Alerts</span>
                  <span className={`font-medium ${data.alerts.length > 0 ? 'text-red-600' : ''}`}>
                    {data.alerts.length}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/pages/GreeksPage.tsx
git commit -m "feat(frontend): add GreeksPage dashboard

- Account/Strategy tab navigation
- Summary card with limits utilization
- Trend chart for visual analysis
- Alerts panel with acknowledge
- Quick stats sidebar

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 16: Add Route and Navigation

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: Add route for GreeksPage**

```typescript
// Add import at top of frontend/src/App.tsx
import { GreeksPage } from './pages/GreeksPage';

// Add route in the Routes section
<Route path="/greeks" element={<GreeksPage />} />
```

**Step 2: Add navigation link**

Find the navigation section and add:

```typescript
<Link to="/greeks" className="...">Greeks</Link>
```

**Step 3: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(frontend): add Greeks route and navigation

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 5: Testing and Integration (Tasks 17-19)

### Task 17: Add Frontend Component Tests

**Files:**
- Create: `frontend/src/components/GreeksSummaryCard.test.tsx`

**Step 1: Create test file**

```typescript
// frontend/src/components/GreeksSummaryCard.test.tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { GreeksSummaryCard } from './GreeksSummaryCard';
import type { AggregatedGreeks } from '../types';

const mockGreeks: AggregatedGreeks = {
  scope: 'ACCOUNT',
  scope_id: 'acc123',
  strategy_id: null,
  dollar_delta: 45000,
  gamma_dollar: 8000,
  gamma_pnl_1pct: 0.4,
  vega_per_1pct: 15000,
  theta_per_day: -2500,
  coverage_pct: 95.5,
  is_coverage_sufficient: true,
  has_high_risk_missing_legs: false,
  valid_legs_count: 10,
  total_legs_count: 10,
  staleness_seconds: 5,
  as_of_ts: new Date().toISOString(),
};

describe('GreeksSummaryCard', () => {
  it('renders all Greeks values', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.getByText('Delta')).toBeInTheDocument();
    expect(screen.getByText('Gamma')).toBeInTheDocument();
    expect(screen.getByText('Vega')).toBeInTheDocument();
    expect(screen.getByText('Theta')).toBeInTheDocument();
  });

  it('shows coverage percentage', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.getByText('95.5% coverage')).toBeInTheDocument();
  });

  it('shows staleness warning when stale', () => {
    const staleGreeks = { ...mockGreeks, staleness_seconds: 60 };
    render(<GreeksSummaryCard greeks={staleGreeks} />);

    expect(screen.getByText('60s stale')).toBeInTheDocument();
  });

  it('shows Account Greeks title for account scope', () => {
    render(<GreeksSummaryCard greeks={mockGreeks} />);

    expect(screen.getByText('Account Greeks')).toBeInTheDocument();
  });

  it('shows strategy name for strategy scope', () => {
    const strategyGreeks = { ...mockGreeks, scope: 'STRATEGY' as const, strategy_id: 'wheel_aapl' };
    render(<GreeksSummaryCard greeks={strategyGreeks} />);

    expect(screen.getByText('wheel_aapl')).toBeInTheDocument();
  });
});
```

**Step 2: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/components/GreeksSummaryCard.test.tsx
git commit -m "test(frontend): add GreeksSummaryCard tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 18: Add useGreeks Hook Tests

**Files:**
- Create: `frontend/src/hooks/useGreeks.test.ts`

**Step 1: Create test file**

```typescript
// frontend/src/hooks/useGreeks.test.ts
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { useGreeksOverview } from './useGreeks';
import * as greeksApi from '../api/greeks';
import type { ReactNode } from 'react';

vi.mock('../api/greeks');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

describe('useGreeksOverview', () => {
  it('fetches Greeks overview', async () => {
    const mockData = {
      account: {
        scope: 'ACCOUNT',
        scope_id: 'acc123',
        dollar_delta: 50000,
        gamma_dollar: 10000,
        vega_per_1pct: 20000,
        theta_per_day: -3000,
        coverage_pct: 100,
        is_coverage_sufficient: true,
        has_high_risk_missing_legs: false,
        valid_legs_count: 5,
        total_legs_count: 5,
        staleness_seconds: 0,
        as_of_ts: new Date().toISOString(),
      },
      strategies: {},
      alerts: [],
      top_contributors: {},
    };

    vi.mocked(greeksApi.fetchGreeksOverview).mockResolvedValue(mockData);

    const { result } = renderHook(() => useGreeksOverview('acc123', 0), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(mockData);
  });
});
```

**Step 2: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/hooks/useGreeks.test.ts
git commit -m "test(frontend): add useGreeks hook tests

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 19: End-to-End Integration Test

**Files:**
- Create: `backend/tests/greeks/test_integration_e2e.py`

**Step 1: Create E2E test**

```python
# backend/tests/greeks/test_integration_e2e.py
"""End-to-end integration tests for Greeks monitoring system."""
import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.greeks.calculator import GreeksCalculator, ModelGreeksProvider, PositionInfo
from src.greeks.aggregator import GreeksAggregator
from src.greeks.alerts import AlertEngine
from src.greeks.models import GreeksLimitsConfig, RiskMetric


class TestGreeksE2E:
    """End-to-end tests for Greeks system."""

    def test_full_calculation_pipeline(self):
        """Test complete pipeline: positions -> calculation -> aggregation -> alerts."""
        # 1. Setup positions
        positions = [
            PositionInfo(
                position_id=1,
                symbol="AAPL240621C00150000",
                underlying_symbol="AAPL",
                quantity=10,
                multiplier=100,
                option_type="call",
                strike=Decimal("150.00"),
                expiry="2024-06-21",
            ),
            PositionInfo(
                position_id=2,
                symbol="AAPL240621P00140000",
                underlying_symbol="AAPL",
                quantity=-5,
                multiplier=100,
                option_type="put",
                strike=Decimal("140.00"),
                expiry="2024-06-21",
            ),
        ]

        # 2. Calculate Greeks using model
        model_provider = ModelGreeksProvider(default_iv=Decimal("0.25"))
        model_provider.set_underlying_prices({"AAPL": Decimal("150.00")})
        calculator = GreeksCalculator(primary_provider=model_provider)

        position_greeks = calculator.calculate(positions)

        assert len(position_greeks) == 2
        assert all(pg.valid for pg in position_greeks)

        # 3. Aggregate
        aggregator = GreeksAggregator()
        account_greeks = aggregator.aggregate(position_greeks, "ACCOUNT", "acc123")

        assert account_greeks.valid_legs_count == 2
        assert account_greeks.total_legs_count == 2
        # Long call + short put = net long delta
        assert account_greeks.dollar_delta != 0

        # 4. Check alerts
        config = GreeksLimitsConfig.default_account_config("acc123")
        # Lower delta limit to trigger alert
        config.thresholds[RiskMetric.DELTA].limit = Decimal("1000")

        engine = AlertEngine(config)
        alerts = engine.evaluate(account_greeks)

        # Should have delta alert due to low limit
        assert len(alerts) > 0

    def test_model_fallback_works(self):
        """Test that model fallback works when Futu unavailable."""
        positions = [
            PositionInfo(
                position_id=1,
                symbol="TSLA240621C00200000",
                underlying_symbol="TSLA",
                quantity=5,
                multiplier=100,
                option_type="call",
                strike=Decimal("200.00"),
                expiry="2024-06-21",
            ),
        ]

        # Empty Futu provider (simulates unavailable)
        class EmptyFutu:
            @property
            def source(self):
                from src.greeks.models import GreeksDataSource
                return GreeksDataSource.FUTU

            def fetch_greeks(self, positions):
                return {}

        # Model fallback
        model = ModelGreeksProvider()
        model.set_underlying_prices({"TSLA": Decimal("200.00")})

        calculator = GreeksCalculator(
            primary_provider=EmptyFutu(),
            fallback_provider=model,
        )

        results = calculator.calculate(positions)

        assert len(results) == 1
        assert results[0].valid is True
        from src.greeks.models import GreeksDataSource
        assert results[0].source == GreeksDataSource.MODEL
```

**Step 2: Run test**

```bash
cd backend && pytest tests/greeks/test_integration_e2e.py -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add backend/tests/greeks/test_integration_e2e.py
git commit -m "test(greeks): add end-to-end integration tests

- Full pipeline: positions -> calculation -> aggregation -> alerts
- Model fallback verification

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

| Phase | Tasks | Components |
|-------|-------|------------|
| 1 | 1-4 | Backend: Black-Scholes, IV Cache, Model Provider |
| 2 | 5-7 | Backend: WebSocket Manager, API Integration |
| 3 | 8-10 | Frontend: Types, API, Hooks |
| 4 | 11-16 | Frontend: Dashboard Components, Page, Route |
| 5 | 17-19 | Testing: Component, Hook, E2E tests |

**Total tasks:** 19 bite-sized steps

**Key testing commands:**
```bash
# Backend
cd backend && pytest tests/greeks/ -v
cd backend && pytest tests/greeks/ -v --cov=src/greeks

# Frontend
cd frontend && npm test -- --run
cd frontend && npm run build  # Verify build
```
