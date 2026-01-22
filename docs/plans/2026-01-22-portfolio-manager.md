# Portfolio Manager Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Portfolio Manager - the foundation for position tracking, account sync, and transaction ledger.

**Architecture:** Pydantic models for data, SQLAlchemy for persistence, async repository pattern for data access. Portfolio Manager is a stateless service that reads/writes through repositories.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, PostgreSQL, pytest, alembic

---

## Task 1: Initialize Backend Project Structure

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/__init__.py`
- Create: `backend/src/main.py`
- Create: `backend/src/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

**Step 1: Create pyproject.toml with dependencies**

```toml
[project]
name = "aq-trading"
version = "0.1.0"
description = "Algorithmic trading system"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "sqlalchemy[asyncio]>=2.0.25",
    "asyncpg>=0.29.0",
    "alembic>=1.13.0",
    "redis>=5.0.0",
    "httpx>=0.26.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/aq_trading"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Futu
    futu_host: str = "127.0.0.1"
    futu_port: int = 11111

    # App
    debug: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
```

**Step 3: Create main.py stub**

```python
from fastapi import FastAPI

app = FastAPI(title="AQ Trading", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**Step 4: Create conftest.py with test fixtures**

```python
import pytest
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.db.database import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session():
    """In-memory SQLite for tests"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()
```

**Step 5: Verify structure**

Run: `ls -la backend/src/ backend/tests/`
Expected: All files present

**Step 6: Commit**

```bash
git add backend/
git commit -m "feat: initialize backend project structure"
```

---

## Task 2: Create Database Models

**Files:**
- Create: `backend/src/db/__init__.py`
- Create: `backend/src/db/database.py`
- Create: `backend/src/models/__init__.py`
- Create: `backend/src/models/account.py`
- Create: `backend/src/models/position.py`
- Create: `backend/src/models/transaction.py`

**Step 1: Create database.py with Base and engine**

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from src.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session
```

**Step 2: Create account.py model**

```python
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, Numeric, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    broker: Mapped[str] = mapped_column(String(20), default="futu")
    currency: Mapped[str] = mapped_column(String(10), default="USD")

    # Balances
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    buying_power: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    margin_used: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    total_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

**Step 3: Create position.py model**

```python
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from sqlalchemy import String, Numeric, DateTime, Date, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class AssetType(str, Enum):
    STOCK = "stock"
    OPTION = "option"
    FUTURE = "future"


class PutCall(str, Enum):
    PUT = "put"
    CALL = "call"


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(50), ForeignKey("accounts.account_id"), index=True)

    # Identification
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    asset_type: Mapped[AssetType] = mapped_column(String(20), default=AssetType.STOCK)

    # Strategy tagging
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Position data
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    current_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Options-specific (nullable for stocks)
    strike: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    expiry: Mapped[date | None] = mapped_column(Date, nullable=True)
    put_call: Mapped[PutCall | None] = mapped_column(String(10), nullable=True)

    # Timestamps
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def market_value(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return self.quantity * self.current_price * multiplier

    @property
    def unrealized_pnl(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return (self.current_price - self.avg_cost) * self.quantity * multiplier
```

**Step 4: Create transaction.py model**

```python
from datetime import datetime
from decimal import Decimal
from enum import Enum
from sqlalchemy import String, Numeric, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class TransactionAction(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    FEE = "fee"
    INTEREST = "interest"
    TRANSFER = "transfer"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(50), ForeignKey("accounts.account_id"), index=True)

    # Transaction details
    symbol: Mapped[str] = mapped_column(String(50), index=True)
    action: Mapped[TransactionAction] = mapped_column(String(20))
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # P&L
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))

    # Strategy tagging
    strategy_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    # Order reference
    order_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Timestamps
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    @property
    def total_value(self) -> Decimal:
        return self.quantity * self.price
```

**Step 5: Create models __init__.py**

```python
from src.models.account import Account
from src.models.position import Position, AssetType, PutCall
from src.models.transaction import Transaction, TransactionAction

__all__ = [
    "Account",
    "Position",
    "AssetType",
    "PutCall",
    "Transaction",
    "TransactionAction",
]
```

**Step 6: Commit**

```bash
git add backend/src/db/ backend/src/models/
git commit -m "feat: add database models for Account, Position, Transaction"
```

---

## Task 3: Create Pydantic Schemas

**Files:**
- Create: `backend/src/schemas/__init__.py`
- Create: `backend/src/schemas/account.py`
- Create: `backend/src/schemas/position.py`
- Create: `backend/src/schemas/transaction.py`

**Step 1: Create account.py schemas**

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel


class AccountBase(BaseModel):
    account_id: str
    broker: str = "futu"
    currency: str = "USD"


class AccountCreate(AccountBase):
    pass


class AccountUpdate(BaseModel):
    cash: Decimal | None = None
    buying_power: Decimal | None = None
    margin_used: Decimal | None = None
    total_equity: Decimal | None = None


class AccountRead(AccountBase):
    id: int
    cash: Decimal
    buying_power: Decimal
    margin_used: Decimal
    total_equity: Decimal
    created_at: datetime
    updated_at: datetime
    synced_at: datetime | None

    class Config:
        from_attributes = True
```

**Step 2: Create position.py schemas**

```python
from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, computed_field

from src.models.position import AssetType, PutCall


class PositionBase(BaseModel):
    symbol: str
    asset_type: AssetType = AssetType.STOCK
    strategy_id: str | None = None


class PositionCreate(PositionBase):
    account_id: str
    quantity: int
    avg_cost: Decimal
    strike: Decimal | None = None
    expiry: date | None = None
    put_call: PutCall | None = None


class PositionUpdate(BaseModel):
    quantity: int | None = None
    avg_cost: Decimal | None = None
    current_price: Decimal | None = None


class PositionRead(PositionBase):
    id: int
    account_id: str
    quantity: int
    avg_cost: Decimal
    current_price: Decimal
    strike: Decimal | None
    expiry: date | None
    put_call: PutCall | None
    opened_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def market_value(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return self.quantity * self.current_price * multiplier

    @computed_field
    @property
    def unrealized_pnl(self) -> Decimal:
        multiplier = 100 if self.asset_type == AssetType.OPTION else 1
        return (self.current_price - self.avg_cost) * self.quantity * multiplier

    class Config:
        from_attributes = True
```

**Step 3: Create transaction.py schemas**

```python
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel

from src.models.transaction import TransactionAction


class TransactionBase(BaseModel):
    symbol: str
    action: TransactionAction
    quantity: int
    price: Decimal


class TransactionCreate(TransactionBase):
    account_id: str
    commission: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    strategy_id: str | None = None
    order_id: str | None = None
    broker_order_id: str | None = None
    executed_at: datetime | None = None


class TransactionRead(TransactionBase):
    id: int
    account_id: str
    commission: Decimal
    realized_pnl: Decimal
    strategy_id: str | None
    order_id: str | None
    executed_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True
```

**Step 4: Create schemas __init__.py**

```python
from src.schemas.account import AccountCreate, AccountRead, AccountUpdate
from src.schemas.position import PositionCreate, PositionRead, PositionUpdate
from src.schemas.transaction import TransactionCreate, TransactionRead

__all__ = [
    "AccountCreate",
    "AccountRead",
    "AccountUpdate",
    "PositionCreate",
    "PositionRead",
    "PositionUpdate",
    "TransactionCreate",
    "TransactionRead",
]
```

**Step 5: Commit**

```bash
git add backend/src/schemas/
git commit -m "feat: add Pydantic schemas for API"
```

---

## Task 4: Create Repository Layer

**Files:**
- Create: `backend/src/db/repositories/__init__.py`
- Create: `backend/src/db/repositories/base.py`
- Create: `backend/src/db/repositories/portfolio_repo.py`
- Create: `backend/tests/test_portfolio_repo.py`

**Step 1: Write failing test for portfolio repository**

```python
# backend/tests/test_portfolio_repo.py
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_portfolio_repo.py -v`
Expected: FAIL with "No module named 'src.db.repositories'"

**Step 3: Create base.py repository base class**

```python
# backend/src/db/repositories/base.py
from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    def __init__(self, session: AsyncSession):
        self.session = session
```

**Step 4: Create portfolio_repo.py**

```python
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
        expiry = None,
        put_call = None,
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
```

**Step 5: Create repositories __init__.py**

```python
from src.db.repositories.portfolio_repo import PortfolioRepository

__all__ = ["PortfolioRepository"]
```

**Step 6: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_portfolio_repo.py -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add backend/src/db/repositories/ backend/tests/test_portfolio_repo.py
git commit -m "feat: add PortfolioRepository with account, position, transaction ops"
```

---

## Task 5: Implement Portfolio Manager Service

**Files:**
- Create: `backend/src/core/__init__.py`
- Create: `backend/src/core/portfolio.py`
- Create: `backend/tests/test_portfolio_manager.py`

**Step 1: Write failing test for PortfolioManager**

```python
# backend/tests/test_portfolio_manager.py
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
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_portfolio_manager.py -v`
Expected: FAIL with "No module named 'src.core.portfolio'"

**Step 3: Implement PortfolioManager**

```python
# backend/src/core/portfolio.py
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from src.db.repositories.portfolio_repo import PortfolioRepository
from src.models import Position, Account, Transaction, AssetType, TransactionAction


class RedisClient(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> None: ...


class PortfolioManager:
    """
    Manages portfolio state: positions, accounts, transactions.

    This is intentionally passive - it tracks state but doesn't make
    trading decisions. Strategies and Risk Manager read from it.
    """

    def __init__(self, repo: PortfolioRepository, redis: RedisClient | None = None):
        self.repo = repo
        self.redis = redis

    # === Account Operations ===

    async def get_account(self, account_id: str) -> Account | None:
        return await self.repo.get_account(account_id)

    async def sync_account(
        self,
        account_id: str,
        cash: Decimal,
        buying_power: Decimal,
        margin_used: Decimal,
        total_equity: Decimal,
    ) -> Account:
        """Update account balances from broker sync."""
        account = await self.repo.get_account(account_id)
        if not account:
            account = await self.repo.create_account(account_id)

        return await self.repo.update_account(
            account_id=account_id,
            cash=cash,
            buying_power=buying_power,
            margin_used=margin_used,
            total_equity=total_equity,
            synced_at=datetime.utcnow(),
        )

    # === Position Operations ===

    async def get_positions(
        self,
        account_id: str,
        strategy_id: str | None = None,
        symbol: str | None = None,
    ) -> list[Position]:
        """Get positions, optionally filtered by strategy or symbol."""
        return await self.repo.get_positions(
            account_id=account_id,
            strategy_id=strategy_id,
            symbol=symbol,
        )

    async def get_position(
        self,
        account_id: str,
        symbol: str,
        strategy_id: str | None = None,
    ) -> Position | None:
        """Get a specific position."""
        return await self.repo.get_position(account_id, symbol, strategy_id)

    async def get_exposure(self, account_id: str, symbol: str) -> Decimal:
        """Get current exposure (market value) for a symbol."""
        positions = await self.repo.get_positions(account_id=account_id, symbol=symbol)
        return sum(p.market_value for p in positions)

    # === Fill Recording ===

    async def record_fill(
        self,
        account_id: str,
        symbol: str,
        side: str,  # "buy" or "sell"
        quantity: int,
        price: Decimal,
        commission: Decimal = Decimal("0"),
        strategy_id: str | None = None,
        order_id: str | None = None,
        broker_order_id: str | None = None,
        asset_type: AssetType = AssetType.STOCK,
        strike: Decimal | None = None,
        expiry=None,
        put_call=None,
    ) -> Position | None:
        """
        Record an order fill - updates positions and creates transaction.

        Returns the updated/created position, or None if position was closed.
        """
        is_buy = side.lower() == "buy"
        action = TransactionAction.BUY if is_buy else TransactionAction.SELL

        # Get existing position
        existing = await self.repo.get_position(account_id, symbol, strategy_id)

        realized_pnl = Decimal("0")

        if existing is None:
            # New position
            if is_buy:
                position = await self.repo.create_position(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=quantity,
                    avg_cost=price,
                    asset_type=asset_type,
                    strategy_id=strategy_id,
                    strike=strike,
                    expiry=expiry,
                    put_call=put_call,
                )
            else:
                # Short position (selling without existing)
                position = await self.repo.create_position(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=-quantity,
                    avg_cost=price,
                    asset_type=asset_type,
                    strategy_id=strategy_id,
                    strike=strike,
                    expiry=expiry,
                    put_call=put_call,
                )
        else:
            # Update existing position
            if is_buy:
                new_quantity = existing.quantity + quantity
            else:
                new_quantity = existing.quantity - quantity

            if new_quantity == 0:
                # Position closed
                multiplier = 100 if existing.asset_type == AssetType.OPTION else 1
                realized_pnl = (price - existing.avg_cost) * existing.quantity * multiplier
                await self.repo.close_position(account_id, symbol, strategy_id)
                position = None
            elif (existing.quantity > 0 and new_quantity < 0) or (existing.quantity < 0 and new_quantity > 0):
                # Position flipped - close old, open new
                multiplier = 100 if existing.asset_type == AssetType.OPTION else 1
                realized_pnl = (price - existing.avg_cost) * existing.quantity * multiplier
                await self.repo.close_position(account_id, symbol, strategy_id)
                position = await self.repo.create_position(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=new_quantity,
                    avg_cost=price,
                    asset_type=asset_type,
                    strategy_id=strategy_id,
                )
            else:
                # Position increased or partially closed
                if is_buy and existing.quantity > 0:
                    # Adding to long position - calculate new avg cost
                    total_cost = (existing.avg_cost * existing.quantity) + (price * quantity)
                    new_avg_cost = total_cost / new_quantity
                elif not is_buy and existing.quantity > 0:
                    # Reducing long position - calculate realized P&L
                    multiplier = 100 if existing.asset_type == AssetType.OPTION else 1
                    realized_pnl = (price - existing.avg_cost) * quantity * multiplier
                    new_avg_cost = existing.avg_cost
                else:
                    new_avg_cost = existing.avg_cost

                position = await self.repo.update_position(
                    account_id=account_id,
                    symbol=symbol,
                    quantity=new_quantity,
                    avg_cost=new_avg_cost,
                    strategy_id=strategy_id,
                )

        # Record transaction
        await self.repo.record_transaction(
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
        )

        return position

    # === P&L Calculation ===

    async def calculate_unrealized_pnl(
        self,
        account_id: str,
        strategy_id: str | None = None,
    ) -> Decimal:
        """Calculate unrealized P&L using current prices from Redis."""
        positions = await self.repo.get_positions(
            account_id=account_id,
            strategy_id=strategy_id,
        )

        total_pnl = Decimal("0")

        for position in positions:
            # Try to get current price from Redis
            current_price = position.current_price
            if self.redis:
                price_str = await self.redis.get(f"quote:{position.symbol}:price")
                if price_str:
                    current_price = Decimal(price_str)

            multiplier = 100 if position.asset_type == AssetType.OPTION else 1
            pnl = (current_price - position.avg_cost) * position.quantity * multiplier
            total_pnl += pnl

        return total_pnl

    async def calculate_realized_pnl(
        self,
        account_id: str,
        strategy_id: str | None = None,
    ) -> Decimal:
        """Sum realized P&L from transactions."""
        transactions = await self.repo.get_transactions(
            account_id=account_id,
            strategy_id=strategy_id,
            limit=10000,  # Get all
        )
        return sum(tx.realized_pnl for tx in transactions)

    # === Utility ===

    async def update_prices(self, account_id: str, prices: dict[str, Decimal]) -> None:
        """Bulk update current prices for positions."""
        positions = await self.repo.get_positions(account_id=account_id)
        for position in positions:
            if position.symbol in prices:
                await self.repo.update_position(
                    account_id=account_id,
                    symbol=position.symbol,
                    current_price=prices[position.symbol],
                )
```

**Step 4: Create core __init__.py**

```python
from src.core.portfolio import PortfolioManager

__all__ = ["PortfolioManager"]
```

**Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_portfolio_manager.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/core/ backend/tests/test_portfolio_manager.py
git commit -m "feat: add PortfolioManager service with fill recording and P&L calculation"
```

---

## Task 6: Set Up Alembic Migrations

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/001_initial.py`

**Step 1: Initialize alembic config**

```ini
# backend/alembic.ini
[alembic]
script_location = alembic
prepend_sys_path = .
sqlalchemy.url = postgresql+asyncpg://postgres:postgres@localhost:5432/aq_trading

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

**Step 2: Create alembic directory and env.py**

```bash
mkdir -p backend/alembic/versions
```

```python
# backend/alembic/env.py
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from src.db.database import Base
from src.models import Account, Position, Transaction  # Import all models

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

**Step 3: Create initial migration**

```python
# backend/alembic/versions/001_initial.py
"""Initial migration - accounts, positions, transactions

Revision ID: 001
Create Date: 2026-01-22
"""
from alembic import op
import sqlalchemy as sa

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(50), unique=True, index=True, nullable=False),
        sa.Column('broker', sa.String(20), nullable=False, server_default='futu'),
        sa.Column('currency', sa.String(10), nullable=False, server_default='USD'),
        sa.Column('cash', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('buying_power', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('margin_used', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('total_equity', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Positions table
    op.create_table(
        'positions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(50), sa.ForeignKey('accounts.account_id'), index=True, nullable=False),
        sa.Column('symbol', sa.String(50), index=True, nullable=False),
        sa.Column('asset_type', sa.String(20), nullable=False, server_default='stock'),
        sa.Column('strategy_id', sa.String(50), index=True, nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_cost', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('current_price', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('strike', sa.Numeric(18, 4), nullable=True),
        sa.Column('expiry', sa.Date(), nullable=True),
        sa.Column('put_call', sa.String(10), nullable=True),
        sa.Column('opened_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # Transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('account_id', sa.String(50), sa.ForeignKey('accounts.account_id'), index=True, nullable=False),
        sa.Column('symbol', sa.String(50), index=True, nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('price', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('commission', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('realized_pnl', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('strategy_id', sa.String(50), index=True, nullable=True),
        sa.Column('order_id', sa.String(50), index=True, nullable=True),
        sa.Column('broker_order_id', sa.String(50), nullable=True),
        sa.Column('executed_at', sa.DateTime(), index=True, nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('transactions')
    op.drop_table('positions')
    op.drop_table('accounts')
```

**Step 4: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add alembic migrations for portfolio tables"
```

---

## Task 7: Create API Routes

**Files:**
- Create: `backend/src/api/__init__.py`
- Create: `backend/src/api/routes/__init__.py`
- Create: `backend/src/api/routes/portfolio.py`
- Modify: `backend/src/main.py`

**Step 1: Create portfolio.py API routes**

```python
# backend/src/api/routes/portfolio.py
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.db.repositories.portfolio_repo import PortfolioRepository
from src.core.portfolio import PortfolioManager
from src.schemas import AccountRead, PositionRead, TransactionRead

router = APIRouter(prefix="/portfolio", tags=["portfolio"])


async def get_portfolio_manager(session: AsyncSession = Depends(get_session)):
    repo = PortfolioRepository(session)
    return PortfolioManager(repo=repo, redis=None)  # TODO: inject Redis


@router.get("/accounts/{account_id}", response_model=AccountRead)
async def get_account(
    account_id: str,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    account = await pm.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/accounts/{account_id}/positions", response_model=list[PositionRead])
async def get_positions(
    account_id: str,
    strategy_id: str | None = None,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    positions = await pm.get_positions(account_id, strategy_id=strategy_id)
    return positions


@router.get("/accounts/{account_id}/positions/{symbol}", response_model=PositionRead)
async def get_position(
    account_id: str,
    symbol: str,
    strategy_id: str | None = None,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    position = await pm.get_position(account_id, symbol, strategy_id)
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.get("/accounts/{account_id}/pnl")
async def get_pnl(
    account_id: str,
    strategy_id: str | None = None,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    unrealized = await pm.calculate_unrealized_pnl(account_id, strategy_id)
    realized = await pm.calculate_realized_pnl(account_id, strategy_id)
    return {
        "unrealized_pnl": unrealized,
        "realized_pnl": realized,
        "total_pnl": unrealized + realized,
    }


@router.get("/accounts/{account_id}/exposure/{symbol}")
async def get_exposure(
    account_id: str,
    symbol: str,
    pm: PortfolioManager = Depends(get_portfolio_manager),
):
    exposure = await pm.get_exposure(account_id, symbol)
    return {"symbol": symbol, "exposure": exposure}
```

**Step 2: Create routes __init__.py**

```python
from src.api.routes.portfolio import router as portfolio_router

__all__ = ["portfolio_router"]
```

**Step 3: Update main.py to include routes**

```python
# backend/src/main.py
from fastapi import FastAPI

from src.api.routes import portfolio_router

app = FastAPI(title="AQ Trading", version="0.1.0")

# Include routers
app.include_router(portfolio_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "healthy"}
```

**Step 4: Commit**

```bash
git add backend/src/api/ backend/src/main.py
git commit -m "feat: add portfolio API routes"
```

---

## Task 8: Update conftest.py and Add Integration Tests

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_api_portfolio.py`

**Step 1: Update conftest.py for aiosqlite**

```python
# backend/tests/conftest.py
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.db.database import Base, get_session
from src.main import app


@pytest.fixture(scope="session")
def event_loop():
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite for unit tests"""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """HTTP client with test database"""
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
```

**Step 2: Create API integration tests**

```python
# backend/tests/test_api_portfolio.py
import pytest
from decimal import Decimal

from src.db.repositories.portfolio_repo import PortfolioRepository


class TestPortfolioAPI:
    async def test_get_account_not_found(self, client):
        response = await client.get("/api/portfolio/accounts/ACC001")
        assert response.status_code == 404

    async def test_get_account_success(self, client, db_session):
        # Setup
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.update_account("ACC001", cash=Decimal("10000"))

        response = await client.get("/api/portfolio/accounts/ACC001")

        assert response.status_code == 200
        data = response.json()
        assert data["account_id"] == "ACC001"
        assert data["cash"] == "10000.0000"

    async def test_get_positions_empty(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")

        response = await client.get("/api/portfolio/accounts/ACC001/positions")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_positions_with_data(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"))
        await repo.create_position("ACC001", "TSLA", 50, Decimal("200"))

        response = await client.get("/api/portfolio/accounts/ACC001/positions")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    async def test_get_positions_filtered_by_strategy(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"), strategy_id="strat_a")
        await repo.create_position("ACC001", "TSLA", 50, Decimal("200"), strategy_id="strat_b")

        response = await client.get("/api/portfolio/accounts/ACC001/positions?strategy_id=strat_a")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "AAPL"

    async def test_get_pnl(self, client, db_session):
        repo = PortfolioRepository(db_session)
        await repo.create_account("ACC001")
        await repo.create_position("ACC001", "AAPL", 100, Decimal("150"))

        response = await client.get("/api/portfolio/accounts/ACC001/pnl")

        assert response.status_code == 200
        data = response.json()
        assert "unrealized_pnl" in data
        assert "realized_pnl" in data
        assert "total_pnl" in data
```

**Step 3: Add aiosqlite to dev dependencies**

Add to `backend/pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=4.1.0",
    "aiosqlite>=0.19.0",
]
```

**Step 4: Run all tests**

Run: `cd backend && pip install -e ".[dev]" && python -m pytest -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/tests/ backend/pyproject.toml
git commit -m "test: add portfolio API integration tests"
```

---

## Summary

After completing all tasks, you will have:

1. **Backend project structure** with FastAPI, SQLAlchemy async, Pydantic v2
2. **Database models**: Account, Position, Transaction with strategy tagging
3. **Pydantic schemas** for API serialization
4. **PortfolioRepository** for data access
5. **PortfolioManager** service with:
   - `record_fill()` - updates positions on order fills
   - `get_positions()` - with strategy filtering
   - `calculate_unrealized_pnl()` - using Redis prices
   - `calculate_realized_pnl()` - from transaction history
6. **Alembic migrations** for PostgreSQL
7. **REST API routes** for portfolio access
8. **Unit and integration tests**

**Next steps after this plan:**
- Add Redis integration for price caching
- Add Futu broker client for `sync_with_broker()`
- Implement Reconciliation service
