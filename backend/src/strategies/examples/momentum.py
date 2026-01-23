# backend/src/strategies/examples/momentum.py
import logging
from collections import defaultdict
from decimal import Decimal

from src.strategies.base import Strategy, MarketData, OrderFill
from src.strategies.context import StrategyContext
from src.strategies.signals import Signal

logger = logging.getLogger(__name__)


class MomentumStrategy(Strategy):
    """
    Simple momentum strategy.

    - Buy when price rises above threshold% from lookback period
    - Sell when price drops below threshold% while holding

    This is an example strategy for testing. Not for live trading.
    """

    def __init__(
        self,
        name: str,
        symbols: list[str],
        lookback_period: int = 20,
        threshold: float = 0.02,
        position_size: int = 100,
    ):
        self.name = name
        self.symbols = symbols
        self.lookback_period = lookback_period
        self.threshold = Decimal(str(threshold))
        self.position_size = position_size
        self._price_history: dict[str, list[Decimal]] = defaultdict(list)

    async def on_market_data(
        self, data: MarketData, context: StrategyContext
    ) -> list[Signal]:
        signals = []

        # Update price history
        history = self._price_history[data.symbol]
        history.append(data.price)
        if len(history) > self.lookback_period:
            history.pop(0)

        # Need full lookback period
        if len(history) < self.lookback_period:
            return []

        # Calculate momentum
        old_price = history[0]
        momentum = (data.price - old_price) / old_price

        # Check current position
        position = await context.get_position(data.symbol)
        has_position = position is not None and position.quantity > 0

        if not has_position and momentum > self.threshold:
            # No position, momentum up -> buy
            signals.append(Signal(
                strategy_id=self.name,
                symbol=data.symbol,
                action="buy",
                quantity=self.position_size,
                reason=f"Momentum {momentum:.2%} > {self.threshold:.2%}",
            ))
        elif has_position and momentum < -self.threshold:
            # Have position, momentum down -> sell
            signals.append(Signal(
                strategy_id=self.name,
                symbol=data.symbol,
                action="sell",
                quantity=position.quantity,
                reason=f"Momentum {momentum:.2%} < -{self.threshold:.2%}",
            ))

        return signals

    async def on_fill(self, fill: OrderFill) -> None:
        logger.info(
            f"[{self.name}] Fill: {fill.action} {fill.quantity} "
            f"{fill.symbol} @ {fill.price}"
        )

    async def on_start(self) -> None:
        logger.info(f"[{self.name}] Starting with symbols: {self.symbols}")
        self._price_history.clear()

    async def on_stop(self) -> None:
        logger.info(f"[{self.name}] Stopping")
