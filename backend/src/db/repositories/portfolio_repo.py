# backend/src/db/repositories/portfolio_repo.py
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.repositories.base import BaseRepository
from src.models import Account, Position, Transaction, AssetType, TransactionAction


class PortfolioRepository(BaseRepository):
    # === Account Operations ===

    async def create_account(
        self,
        account_id: str,
        broker: str = "futu",
        currency: str = "USD",
    ) -> Account:
        account = Account(
            account_id=account_id,
            broker=broker,
            currency=currency,
        )
        self.session.add(account)
        await self.session.commit()
        await self.session.refresh(account)
        return account

    async def get_account(self, account_id: str) -> Account | None:
        result = await self.session.execute(
            select(Account).where(Account.account_id == account_id)
        )
        return result.scalar_one_or_none()

    async def update_account(
        self,
        account_id: str,
        cash: Decimal | None = None,
        buying_power: Decimal | None = None,
        margin_used: Decimal | None = None,
        total_equity: Decimal | None = None,
        synced_at: datetime | None = None,
    ) -> Account | None:
        account = await self.get_account(account_id)
        if not account:
            return None

        if cash is not None:
            account.cash = cash
        if buying_power is not None:
            account.buying_power = buying_power
        if margin_used is not None:
            account.margin_used = margin_used
        if total_equity is not None:
            account.total_equity = total_equity
        if synced_at is not None:
            account.synced_at = synced_at

        await self.session.commit()
        await self.session.refresh(account)
        return account

    # === Position Operations ===

    async def create_position(
        self,
        account_id: str,
        symbol: str,
        quantity: int,
        avg_cost: Decimal,
        asset_type: AssetType = AssetType.STOCK,
        strategy_id: str | None = None,
        strike: Decimal | None = None,
        expiry=None,
        put_call=None,
    ) -> Position:
        position = Position(
            account_id=account_id,
            symbol=symbol,
            quantity=quantity,
            avg_cost=avg_cost,
            asset_type=asset_type,
            strategy_id=strategy_id,
            strike=strike,
            expiry=expiry,
            put_call=put_call,
        )
        self.session.add(position)
        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def get_position(
        self,
        account_id: str,
        symbol: str,
        strategy_id: str | None = None,
    ) -> Position | None:
        conditions = [
            Position.account_id == account_id,
            Position.symbol == symbol,
        ]
        if strategy_id is not None:
            conditions.append(Position.strategy_id == strategy_id)

        result = await self.session.execute(
            select(Position).where(and_(*conditions))
        )
        return result.scalar_one_or_none()

    async def get_positions(
        self,
        account_id: str,
        strategy_id: str | None = None,
        symbol: str | None = None,
    ) -> list[Position]:
        conditions = [Position.account_id == account_id]

        if strategy_id is not None:
            conditions.append(Position.strategy_id == strategy_id)
        if symbol is not None:
            conditions.append(Position.symbol == symbol)

        result = await self.session.execute(
            select(Position).where(and_(*conditions))
        )
        return list(result.scalars().all())

    async def update_position(
        self,
        account_id: str,
        symbol: str,
        quantity: int | None = None,
        avg_cost: Decimal | None = None,
        current_price: Decimal | None = None,
        strategy_id: str | None = None,
    ) -> Position | None:
        position = await self.get_position(account_id, symbol, strategy_id)
        if not position:
            return None

        if quantity is not None:
            position.quantity = quantity
        if avg_cost is not None:
            position.avg_cost = avg_cost
        if current_price is not None:
            position.current_price = current_price

        await self.session.commit()
        await self.session.refresh(position)
        return position

    async def close_position(
        self,
        account_id: str,
        symbol: str,
        strategy_id: str | None = None,
    ) -> bool:
        conditions = [
            Position.account_id == account_id,
            Position.symbol == symbol,
        ]
        if strategy_id is not None:
            conditions.append(Position.strategy_id == strategy_id)

        result = await self.session.execute(
            delete(Position).where(and_(*conditions))
        )
        await self.session.commit()
        return result.rowcount > 0

    # === Transaction Operations ===

    async def record_transaction(
        self,
        account_id: str,
        symbol: str,
        action: TransactionAction,
        quantity: int,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        realized_pnl: Decimal = Decimal("0"),
        strategy_id: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        executed_at: datetime | None = None,
    ) -> Transaction:
        tx = Transaction(
            account_id=account_id,
            symbol=symbol,
            action=action,
            quantity=quantity,
            price=price,
            commission=commission,
            realized_pnl=realized_pnl,
            strategy_id=strategy_id,
            order_id=order_id,
            broker_order_id=broker_order_id,
            executed_at=executed_at or datetime.utcnow(),
        )
        self.session.add(tx)
        await self.session.commit()
        await self.session.refresh(tx)
        return tx

    async def get_transactions(
        self,
        account_id: str,
        symbol: str | None = None,
        strategy_id: str | None = None,
        limit: int = 100,
    ) -> list[Transaction]:
        conditions = [Transaction.account_id == account_id]

        if symbol is not None:
            conditions.append(Transaction.symbol == symbol)
        if strategy_id is not None:
            conditions.append(Transaction.strategy_id == strategy_id)

        result = await self.session.execute(
            select(Transaction)
            .where(and_(*conditions))
            .order_by(Transaction.executed_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
