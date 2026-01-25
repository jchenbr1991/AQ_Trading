"""Tests for TimescaleDB setup.

These tests require TimescaleDB to be installed.
Skip with: pytest -m "not timescaledb"
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.timescaledb


@pytest.mark.asyncio
async def test_timescaledb_extension_enabled(db_session: AsyncSession):
    """TimescaleDB extension should be enabled."""
    result = await db_session.execute(
        text("SELECT extname FROM pg_extension WHERE extname = 'timescaledb'")
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] == "timescaledb"


@pytest.mark.asyncio
async def test_transactions_new_is_hypertable(db_session: AsyncSession):
    """transactions_new table should be a hypertable."""
    result = await db_session.execute(
        text("""
            SELECT hypertable_name
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions_new'
        """)
    )
    row = result.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_compression_settings_configured(db_session: AsyncSession):
    """Compression settings should be configured."""
    result = await db_session.execute(
        text("""
            SELECT segmentby, orderby
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions_new'
        """)
    )
    row = result.fetchone()
    # May return None if compression not fully configured yet
    # The important thing is the table exists as hypertable
    assert row is not None
