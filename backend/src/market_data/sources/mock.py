# backend/src/market_data/sources/mock.py
"""Mock data source with configurable scenarios."""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from random import choice, random, uniform

from src.market_data.models import MarketDataConfig, SymbolScenario
from src.strategies.base import MarketData

# Scenario parameters: (drift, volatility)
SCENARIO_PARAMS: dict[str, tuple[float, float]] = {
    "flat": (0.0, 0.0001),
    "trend_up": (0.0005, 0.001),
    "trend_down": (-0.0005, 0.001),
    "volatile": (0.0, 0.01),
    "jump": (0.0, 0.001),
    "stale": (0.0, 0.001),
}


class MockDataSource:
    """
    Mock data source generating random-walk quotes.

    Supports configurable scenarios per symbol for testing
    different market conditions.
    """

    def __init__(self, config: MarketDataConfig):
        self._config = config
        self._subscribed: set[str] = set()
        self._running = False
        self._prices: dict[str, Decimal] = {}
        self._spread_bps = 5  # 5 basis points spread
        # Stale scenario config
        self._stale_pause_probability = 0.1
        self._stale_pause_duration_ms = (5000, 10000)

    async def start(self) -> None:
        """Start generating quotes."""
        self._running = True
        for symbol in self._subscribed:
            if symbol in self._config.symbols:
                self._prices[symbol] = self._config.symbols[symbol].base_price
            else:
                self._prices[symbol] = Decimal("100.00")

    async def stop(self) -> None:
        """Stop generating quotes."""
        self._running = False

    async def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to symbols. Idempotent."""
        self._subscribed.update(symbols)

    async def quotes(self) -> AsyncIterator[MarketData]:
        """Generate quotes for subscribed symbols."""
        while self._running:
            for symbol in list(self._subscribed):
                if not self._running:
                    break

                scenario = self._get_scenario(symbol)
                scenario_type = scenario.scenario if scenario else "flat"

                # Handle stale scenario - occasionally pause
                if scenario_type == "stale" and random() < self._stale_pause_probability:  # noqa: S311
                    pause_ms = uniform(*self._stale_pause_duration_ms)  # noqa: S311
                    await asyncio.sleep(pause_ms / 1000)
                    if not self._running:
                        break

                quote = self._generate_quote(symbol, scenario)
                yield quote

                interval_ms = (
                    scenario.tick_interval_ms if scenario else self._config.default_tick_interval_ms
                )
                await asyncio.sleep(interval_ms / 1000)

    def _get_scenario(self, symbol: str) -> SymbolScenario | None:
        """Get scenario config for symbol."""
        return self._config.symbols.get(symbol)

    def _generate_quote(self, symbol: str, scenario: SymbolScenario | None) -> MarketData:
        """Generate a single quote using random walk."""
        current_price = self._prices.get(symbol, Decimal("100.00"))

        scenario_type = scenario.scenario if scenario else "flat"
        drift, volatility = SCENARIO_PARAMS.get(scenario_type, (0.0, 0.001))

        # Handle jump scenario specially
        if scenario_type == "jump" and random() < 0.02:  # noqa: S311
            change = choice([-0.05, 0.05])  # noqa: S311
        else:
            change = drift + volatility * uniform(-1, 1)  # noqa: S311

        new_price = current_price * Decimal(1 + change)
        new_price = max(new_price.quantize(Decimal("0.01")), Decimal("0.01"))

        self._prices[symbol] = new_price

        spread = new_price * Decimal(self._spread_bps) / Decimal(10000)
        bid = (new_price - spread / 2).quantize(Decimal("0.01"))
        ask = (new_price + spread / 2).quantize(Decimal("0.01"))

        return MarketData(
            symbol=symbol,
            price=new_price,
            bid=bid,
            ask=ask,
            volume=int(uniform(1000, 100000)),  # noqa: S311
            timestamp=datetime.utcnow(),
        )
