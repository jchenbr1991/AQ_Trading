# backend/src/strategies/engine.py
import logging
from typing import TYPE_CHECKING, Protocol

from src.strategies.context import StrategyContext
from src.strategies.base import MarketData, OrderFill

if TYPE_CHECKING:
    from src.strategies.registry import StrategyRegistry
    from src.strategies.signals import Signal
    from src.core.portfolio import PortfolioManager

logger = logging.getLogger(__name__)


class RiskManagerProtocol(Protocol):
    """Protocol for Risk Manager dependency."""
    async def evaluate(self, signal: "Signal") -> bool: ...


class StrategyEngine:
    """
    Orchestrates strategy execution.

    - Receives market data from Market Data component
    - Dispatches to subscribed strategies
    - Collects signals and forwards to Risk Manager
    - Notifies strategies of fills
    """

    def __init__(
        self,
        registry: "StrategyRegistry",
        portfolio: "PortfolioManager",
        risk_manager: RiskManagerProtocol,
    ):
        self._registry = registry
        self._portfolio = portfolio
        self._risk_manager = risk_manager
        self._quote_cache: dict[str, MarketData] = {}
        self._running = False

    async def on_market_data(self, data: MarketData) -> None:
        """
        Called by Market Data component when new quote arrives.

        Dispatches to all strategies subscribed to this symbol.
        """
        if not self._running:
            return

        # Update cache
        self._quote_cache[data.symbol] = data

        # Dispatch to subscribed strategies
        for strategy in self._registry.all_strategies():
            if data.symbol not in strategy.symbols:
                continue

            account_id = self._registry.get_account_id(strategy.name)

            # Build context for this strategy
            context = StrategyContext(
                strategy_id=strategy.name,
                account_id=account_id,
                portfolio=self._portfolio,
                quote_cache=self._quote_cache,
            )

            # Get signals with error handling
            try:
                signals = await strategy.on_market_data(data, context)
            except Exception as e:
                logger.error(
                    f"Strategy {strategy.name} error on {data.symbol}: {e}",
                    exc_info=True,
                )
                continue

            # Process signals sequentially through Risk Manager
            for signal in signals:
                try:
                    await self._risk_manager.evaluate(signal)
                except Exception as e:
                    logger.error(
                        f"Risk Manager error for signal from {strategy.name}: {e}",
                        exc_info=True,
                    )

    async def on_fill(self, fill: OrderFill) -> None:
        """
        Called by Order Manager when fill occurs.

        Notifies the strategy that generated the order.
        """
        strategy = self._registry.get_strategy(fill.strategy_id)
        if strategy:
            try:
                await strategy.on_fill(fill)
            except Exception as e:
                logger.error(
                    f"Strategy {fill.strategy_id} on_fill error: {e}",
                    exc_info=True,
                )

    def get_quote(self, symbol: str) -> MarketData | None:
        """Get cached quote for a symbol."""
        return self._quote_cache.get(symbol)

    async def start(self) -> None:
        """Load strategies and start engine."""
        await self._registry.load_strategies()
        self._running = True
        logger.info("Strategy engine started")

    async def stop(self) -> None:
        """Stop engine and shutdown strategies."""
        self._running = False
        await self._registry.shutdown()
        logger.info("Strategy engine stopped")
