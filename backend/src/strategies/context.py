# backend/src/strategies/context.py
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.strategies.base import MarketData
    from src.core.portfolio import PortfolioManager
    from src.models import Position


class StrategyContext:
    """
    Read-only view of portfolio for a specific strategy.

    Provides access to:
    - This strategy's positions only (filtered by strategy_id)
    - Cached market quotes (on-demand pull)
    - P&L calculations for this strategy
    """

    def __init__(
        self,
        strategy_id: str,
        account_id: str,
        portfolio: "PortfolioManager",
        quote_cache: dict[str, "MarketData"],
    ):
        self._strategy_id = strategy_id
        self._account_id = account_id
        self._portfolio = portfolio
        self._quote_cache = quote_cache

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def account_id(self) -> str:
        return self._account_id

    def get_quote(self, symbol: str) -> "MarketData | None":
        """Get cached quote for any symbol."""
        return self._quote_cache.get(symbol)

    async def get_position(self, symbol: str) -> "Position | None":
        """Get this strategy's position in a symbol."""
        return await self._portfolio.get_position(
            self._account_id, symbol, self._strategy_id
        )

    async def get_my_positions(self) -> list["Position"]:
        """Get all positions owned by this strategy."""
        return await self._portfolio.get_positions(
            account_id=self._account_id,
            strategy_id=self._strategy_id,
        )

    async def get_my_pnl(self) -> Decimal:
        """Get unrealized P&L for this strategy's positions."""
        return await self._portfolio.calculate_unrealized_pnl(
            account_id=self._account_id,
            strategy_id=self._strategy_id,
        )
