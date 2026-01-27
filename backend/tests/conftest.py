import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from src.api.reconciliation import reset_alerts
from src.api.risk import reset_state_manager
from src.db.database import Base, get_session
from src.main import app


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "timescaledb: marks tests as requiring TimescaleDB (skip unless DB available)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip TimescaleDB tests unless running against PostgreSQL with TimescaleDB."""
    # Check if we have a PostgreSQL connection with TimescaleDB
    db_url = os.environ.get("DATABASE_URL", "")
    has_timescaledb = (
        "postgresql" in db_url and os.environ.get("TIMESCALEDB_ENABLED", "").lower() == "true"
    )

    if has_timescaledb:
        # Don't skip timescaledb tests
        return

    skip_timescaledb = pytest.mark.skip(
        reason="TimescaleDB not available (set DATABASE_URL and TIMESCALEDB_ENABLED=true)"
    )
    for item in items:
        if "timescaledb" in item.keywords:
            item.add_marker(skip_timescaledb)


@pytest_asyncio.fixture
async def db_session(request):
    """Database session for unit tests.

    Uses PostgreSQL if DATABASE_URL is set and test requires TimescaleDB,
    otherwise uses in-memory SQLite.
    """
    db_url = os.environ.get("DATABASE_URL", "")
    use_postgres = "postgresql" in db_url and "timescaledb" in request.keywords

    if use_postgres:
        # Use real PostgreSQL for TimescaleDB tests
        engine = create_async_engine(db_url, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            yield session
        await engine.dispose()
    else:
        # Use in-memory SQLite for regular tests
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            yield session

        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    """HTTP client with test database"""
    # Reset state manager for test isolation
    reset_state_manager()
    # Reset reconciliation alerts for test isolation
    reset_alerts()

    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
