"""Tests for StorageMonitor service."""

from dataclasses import FrozenInstanceError
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from src.services.storage_monitor import StorageMonitor, StorageStats, TableStats


class TestStorageStatsModel:
    def test_storage_stats_creation(self):
        """StorageStats model should be created correctly."""
        stats = StorageStats(
            database_size_bytes=1_000_000,
            database_size_pretty="1 MB",
            timestamp=datetime.now(),
            tables=[],
            compression={},
        )
        assert stats.database_size_bytes == 1_000_000
        assert stats.database_size_pretty == "1 MB"

    def test_storage_stats_is_frozen(self):
        """StorageStats should be immutable."""
        stats = StorageStats(
            database_size_bytes=1_000_000,
            database_size_pretty="1 MB",
            timestamp=datetime.now(),
            tables=[],
            compression={},
        )
        with pytest.raises(FrozenInstanceError):
            stats.database_size_bytes = 2_000_000


class TestTableStatsModel:
    def test_table_stats_creation(self):
        """TableStats model should be created correctly."""
        stats = TableStats(
            table_name="transactions",
            row_count=10000,
            size_bytes=500_000,
            size_pretty="500 KB",
            is_hypertable=True,
        )
        assert stats.table_name == "transactions"
        assert stats.is_hypertable is True

    def test_table_stats_is_frozen(self):
        """TableStats should be immutable."""
        stats = TableStats(
            table_name="transactions",
            row_count=10000,
            size_bytes=500_000,
            size_pretty="500 KB",
            is_hypertable=True,
        )
        with pytest.raises(FrozenInstanceError):
            stats.row_count = 20000


class TestStorageMonitor:
    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        session = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_get_storage_stats_returns_stats(self, mock_session):
        """Should return storage statistics."""
        # Mock database size query
        db_size_result = MagicMock()
        db_size_result.fetchone.return_value = (1000000, "1 MB")

        # Mock table stats query
        table_stats_result = MagicMock()
        table_stats_result.fetchall.return_value = [
            ("transactions", 100, 50000, "50 KB"),
            ("accounts", 10, 8000, "8 KB"),
        ]

        # Mock hypertables query (empty)
        hypertables_result = MagicMock()
        hypertables_result.fetchall.return_value = []

        # Configure execute to return different results
        mock_session.execute = AsyncMock(
            side_effect=[
                db_size_result,
                table_stats_result,
                hypertables_result,
                MagicMock(fetchall=MagicMock(return_value=[])),  # compression stats
            ]
        )

        monitor = StorageMonitor(mock_session)
        stats = await monitor.get_storage_stats()

        assert isinstance(stats, StorageStats)
        assert stats.database_size_bytes == 1000000
        assert stats.database_size_pretty == "1 MB"
        assert len(stats.tables) == 2
        assert stats.timestamp is not None

    @pytest.mark.asyncio
    async def test_get_table_stats_returns_list(self, mock_session):
        """Should return stats for each table."""
        # Mock table stats query
        table_stats_result = MagicMock()
        table_stats_result.fetchall.return_value = [
            ("transactions", 100, 50000, "50 KB"),
        ]

        # Mock hypertables query
        hypertables_result = MagicMock()
        hypertables_result.fetchall.return_value = [("transactions",)]

        mock_session.execute = AsyncMock(
            side_effect=[
                table_stats_result,
                hypertables_result,
            ]
        )

        monitor = StorageMonitor(mock_session)
        tables = await monitor.get_table_stats()

        assert isinstance(tables, list)
        assert len(tables) == 1
        assert tables[0].table_name == "transactions"
        assert tables[0].is_hypertable is True

    @pytest.mark.asyncio
    async def test_get_compression_stats_handles_no_timescaledb(self, mock_session):
        """Should return empty dict if TimescaleDB not available."""
        mock_session.execute = AsyncMock(side_effect=Exception("relation does not exist"))

        monitor = StorageMonitor(mock_session)
        compression = await monitor.get_compression_stats()

        assert isinstance(compression, dict)
        assert len(compression) == 0

    @pytest.mark.asyncio
    async def test_get_compression_stats_returns_chunk_info(self, mock_session):
        """Should return compression stats for hypertables."""
        compression_result = MagicMock()
        compression_result.fetchall.return_value = [
            ("transactions", 10, 8),  # 10 total chunks, 8 compressed
            ("market_data", 5, 5),  # 5 total chunks, 5 compressed
        ]

        mock_session.execute = AsyncMock(return_value=compression_result)

        monitor = StorageMonitor(mock_session)
        compression = await monitor.get_compression_stats()

        assert isinstance(compression, dict)
        assert "transactions" in compression
        assert compression["transactions"]["total_chunks"] == 10
        assert compression["transactions"]["compressed_chunks"] == 8
        assert "market_data" in compression

    @pytest.mark.asyncio
    async def test_get_table_stats_handles_null_values(self, mock_session):
        """Should handle NULL values in database response."""
        # Mock table stats query with None values
        table_stats_result = MagicMock()
        table_stats_result.fetchall.return_value = [
            ("empty_table", None, None, None),
        ]

        # Mock hypertables query (empty)
        hypertables_result = MagicMock()
        hypertables_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[
                table_stats_result,
                hypertables_result,
            ]
        )

        monitor = StorageMonitor(mock_session)
        tables = await monitor.get_table_stats()

        assert len(tables) == 1
        assert tables[0].row_count == 0
        assert tables[0].size_bytes == 0
        assert tables[0].size_pretty == "0 bytes"

    @pytest.mark.asyncio
    async def test_get_storage_stats_handles_empty_database(self, mock_session):
        """Should handle empty database gracefully."""
        # Mock database size query returning None
        db_size_result = MagicMock()
        db_size_result.fetchone.return_value = None

        # Mock empty table stats
        table_stats_result = MagicMock()
        table_stats_result.fetchall.return_value = []

        # Mock hypertables query (empty)
        hypertables_result = MagicMock()
        hypertables_result.fetchall.return_value = []

        mock_session.execute = AsyncMock(
            side_effect=[
                db_size_result,
                table_stats_result,
                hypertables_result,
                MagicMock(fetchall=MagicMock(return_value=[])),
            ]
        )

        monitor = StorageMonitor(mock_session)
        stats = await monitor.get_storage_stats()

        assert stats.database_size_bytes == 0
        assert stats.database_size_pretty == "0 bytes"
        assert len(stats.tables) == 0
