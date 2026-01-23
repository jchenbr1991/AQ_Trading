import pytest
from decimal import Decimal

from src.db.repositories.portfolio_repo import PortfolioRepository
from src.models import Account, Position, Transaction, AssetType, TransactionAction


@pytest.fixture
def repo(db_session):
    return PortfolioRepository(db_session)


class TestAccountOperations:
    async def test_create_account(self, repo):
        account = await repo.create_account("ACC001", broker="futu", currency="USD")

        assert account.account_id == "ACC001"
        assert account.broker == "futu"
        assert account.currency == "USD"

    async def test_get_account(self, repo):
        await repo.create_account("ACC001")

        account = await repo.get_account("ACC001")

        assert account is not None
        assert account.account_id == "ACC001"

    async def test_update_account_balances(self, repo):
        await repo.create_account("ACC001")

        await repo.update_account(
            "ACC001",
            cash=Decimal("10000"),
            buying_power=Decimal("8000"),
            total_equity=Decimal("15000"),
        )

        account = await repo.get_account("ACC001")
        assert account.cash == Decimal("10000")
        assert account.buying_power == Decimal("8000")


class TestPositionOperations:
    async def test_create_position(self, repo):
        await repo.create_account("ACC001")

        position = await repo.create_position(
            account_id="ACC001",
            symbol="AAPL",
            quantity=100,
            avg_cost=Decimal("150.00"),
            strategy_id="momentum_v1",
        )

        assert position.symbol == "AAPL"
        assert position.quantity == 100
        assert position.strategy_id == "momentum_v1"

    async def test_get_positions_by_strategy(self, repo):
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"), strategy_id="strat_a")
        await repo.create_position("ACC001", "TSLA", 50, Decimal("200"), strategy_id="strat_b")
        await repo.create_position("ACC001", "GOOGL", 25, Decimal("100"), strategy_id="strat_a")

        positions = await repo.get_positions(account_id="ACC001", strategy_id="strat_a")

        assert len(positions) == 2
        symbols = {p.symbol for p in positions}
        assert symbols == {"AAPL", "GOOGL"}

    async def test_update_position_quantity(self, repo):
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"))

        await repo.update_position("ACC001", "AAPL", quantity=150, avg_cost=Decimal("155"))

        position = await repo.get_position("ACC001", "AAPL")
        assert position.quantity == 150
        assert position.avg_cost == Decimal("155")

    async def test_close_position(self, repo):
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"))

        await repo.close_position("ACC001", "AAPL")

        position = await repo.get_position("ACC001", "AAPL")
        assert position is None


class TestTransactionOperations:
    async def test_record_transaction(self, repo):
        await repo.create_account("ACC001")

        tx = await repo.record_transaction(
            account_id="ACC001",
            symbol="AAPL",
            action=TransactionAction.BUY,
            quantity=100,
            price=Decimal("150.00"),
            commission=Decimal("1.00"),
            strategy_id="momentum_v1",
        )

        assert tx.symbol == "AAPL"
        assert tx.action == TransactionAction.BUY
        assert tx.quantity == 100

    async def test_get_transactions_by_symbol(self, repo):
        await repo.create_account("ACC001")
        await repo.record_transaction("ACC001", "AAPL", TransactionAction.BUY, 100, Decimal("150"))
        await repo.record_transaction("ACC001", "AAPL", TransactionAction.SELL, 50, Decimal("160"))
        await repo.record_transaction("ACC001", "TSLA", TransactionAction.BUY, 25, Decimal("200"))

        transactions = await repo.get_transactions(account_id="ACC001", symbol="AAPL")

        assert len(transactions) == 2
