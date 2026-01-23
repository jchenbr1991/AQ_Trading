# backend/tests/test_context.py
import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from src.strategies.context import StrategyContext
from src.strategies.base import MarketData


class TestStrategyContext:
    @pytest.fixture
    def mock_portfolio(self):
        portfolio = AsyncMock()
        return portfolio

    @pytest.fixture
    def quote_cache(self):
        return {
            "AAPL": MarketData(
                symbol="AAPL",
                price=Decimal("185.50"),
                bid=Decimal("185.45"),
                ask=Decimal("185.55"),
                volume=1000000,
                timestamp=datetime.utcnow(),
            ),
            "TSLA": MarketData(
                symbol="TSLA",
                price=Decimal("250.00"),
                bid=Decimal("249.90"),
                ask=Decimal("250.10"),
                volume=500000,
                timestamp=datetime.utcnow(),
            ),
        }

    def test_get_quote_returns_cached_data(self, mock_portfolio, quote_cache):
        context = StrategyContext(
            strategy_id="test_strat",
            account_id="ACC001",
            portfolio=mock_portfolio,
            quote_cache=quote_cache,
        )

        quote = context.get_quote("AAPL")

        assert quote is not None
        assert quote.symbol == "AAPL"
        assert quote.price == Decimal("185.50")

    def test_get_quote_returns_none_for_unknown_symbol(self, mock_portfolio, quote_cache):
        context = StrategyContext(
            strategy_id="test_strat",
            account_id="ACC001",
            portfolio=mock_portfolio,
            quote_cache=quote_cache,
        )

        quote = context.get_quote("UNKNOWN")

        assert quote is None

    async def test_get_position_filters_by_strategy(self, mock_portfolio, quote_cache):
        mock_position = MagicMock()
        mock_position.symbol = "AAPL"
        mock_position.quantity = 100
        mock_portfolio.get_position.return_value = mock_position

        context = StrategyContext(
            strategy_id="test_strat",
            account_id="ACC001",
            portfolio=mock_portfolio,
            quote_cache=quote_cache,
        )

        position = await context.get_position("AAPL")

        assert position.symbol == "AAPL"
        mock_portfolio.get_position.assert_called_once_with(
            "ACC001", "AAPL", "test_strat"
        )
