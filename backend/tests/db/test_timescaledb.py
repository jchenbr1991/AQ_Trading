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
    # Check compression is enabled on the hypertable
    result = await db_session.execute(
        text("""
            SELECT compression_enabled
            FROM timescaledb_information.hypertables
            WHERE hypertable_name = 'transactions_new'
        """)
    )
    row = result.fetchone()
    assert row is not None
    assert row[0] is True, "Compression should be enabled"

    # Check segmentby columns are configured (account_id, symbol)
    result = await db_session.execute(
        text("""
            SELECT attname
            FROM timescaledb_information.compression_settings
            WHERE hypertable_name = 'transactions_new'
            AND segmentby_column_index IS NOT NULL
            ORDER BY segmentby_column_index
        """)
    )
    segmentby_cols = [row[0] for row in result.fetchall()]
    assert segmentby_cols == [
        "account_id",
        "symbol",
    ], f"Expected segmentby columns, got {segmentby_cols}"

    # Check orderby column is configured (executed_at DESC)
    result = await db_session.execute(
        text("""
            SELECT attname, orderby_asc
            FROM timescaledb_information.compression_settings
            WHERE hypertable_name = 'transactions_new'
            AND orderby_column_index IS NOT NULL
            ORDER BY orderby_column_index
        """)
    )
    orderby_rows = result.fetchall()
    assert len(orderby_rows) == 1
    assert orderby_rows[0][0] == "executed_at"
    assert orderby_rows[0][1] is False, "executed_at should be ordered DESC"
