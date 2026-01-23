import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from src.core.portfolio import PortfolioManager
from src.models import Position, AssetType, TransactionAction
from src.schemas import PositionRead


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    return redis


@pytest.fixture
def portfolio_manager(mock_repo, mock_redis):
    return PortfolioManager(repo=mock_repo, redis=mock_redis)


class TestRecordFill:
    async def test_record_fill_opens_new_position(self, portfolio_manager, mock_repo):
        mock_repo.get_position.return_value = None
        mock_repo.create_position.return_value = Position(
            id=1,
            account_id="ACC001",
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150"),
            current_price=Decimal("150"),
            asset_type=AssetType.STOCK,
        )

        result = await portfolio_manager.record_fill(
            account_id="ACC001",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("1.00"),
            strategy_id="momentum_v1",
        )

        assert result.symbol == "AAPL"
        assert result.quantity == 100
        mock_repo.create_position.assert_called_once()
        mock_repo.record_transaction.assert_called_once()

    async def test_record_fill_increases_existing_position(self, portfolio_manager, mock_repo):
        existing = Position(
            id=1,
            account_id="ACC001",
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150"),
            current_price=Decimal("150"),
            asset_type=AssetType.STOCK,
            strategy_id="momentum_v1",
        )
        mock_repo.get_position.return_value = existing
        mock_repo.update_position.return_value = existing

        await portfolio_manager.record_fill(
            account_id="ACC001",
            symbol="AAPL",
            side="buy",
            quantity=50,
            price=Decimal("160.00"),
            strategy_id="momentum_v1",
        )

        # Should update with new avg cost
        mock_repo.update_position.assert_called_once()
        call_args = mock_repo.update_position.call_args
        assert call_args.kwargs["quantity"] == 150  # 100 + 50

    async def test_record_fill_closes_position(self, portfolio_manager, mock_repo):
        existing = Position(
            id=1,
            account_id="ACC001",
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150"),
            current_price=Decimal("160"),
            asset_type=AssetType.STOCK,
        )
        mock_repo.get_position.return_value = existing
        mock_repo.close_position.return_value = True

        await portfolio_manager.record_fill(
            account_id="ACC001",
            symbol="AAPL",
            side="sell",
            quantity=100,
            price=Decimal("160.00"),
        )

        mock_repo.close_position.assert_called_once()
        # Should record realized P&L
        tx_call = mock_repo.record_transaction.call_args
        assert tx_call.kwargs["realized_pnl"] == Decimal("1000")  # (160-150) * 100


class TestGetPositions:
    async def test_get_positions_with_strategy_filter(self, portfolio_manager, mock_repo):
        mock_repo.get_positions.return_value = [
            Position(
                id=1, account_id="ACC001", symbol="AAPL",
                quantity=100, avg_cost=Decimal("150"), current_price=Decimal("160"),
                asset_type=AssetType.STOCK, strategy_id="strat_a",
            )
        ]

        positions = await portfolio_manager.get_positions("ACC001", strategy_id="strat_a")

        assert len(positions) == 1
        mock_repo.get_positions.assert_called_with(
            account_id="ACC001", strategy_id="strat_a", symbol=None
        )


class TestCalculatePnL:
    async def test_calculate_unrealized_pnl(self, portfolio_manager, mock_repo, mock_redis):
        mock_repo.get_positions.return_value = [
            Position(
                id=1, account_id="ACC001", symbol="AAPL",
                quantity=100, avg_cost=Decimal("150"), current_price=Decimal("150"),
                asset_type=AssetType.STOCK,
            ),
            Position(
                id=2, account_id="ACC001", symbol="TSLA",
                quantity=50, avg_cost=Decimal("200"), current_price=Decimal("200"),
                asset_type=AssetType.STOCK,
            ),
        ]
        # Mock Redis prices
        mock_redis.get = AsyncMock(side_effect=lambda k: {
            "quote:AAPL:price": "160.00",
            "quote:TSLA:price": "220.00",
        }.get(k))

        pnl = await portfolio_manager.calculate_unrealized_pnl("ACC001")

        # AAPL: (160-150) * 100 = 1000
        # TSLA: (220-200) * 50 = 1000
        assert pnl == Decimal("2000")
