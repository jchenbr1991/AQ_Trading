# backend/tests/api/test_storage.py
"""Tests for storage API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from src.main import app
from src.services.storage_monitor import StorageStats, TableStats


class TestStorageEndpoints:
    """Tests for /api/storage endpoints."""

    def test_get_storage_stats_returns_storage_statistics(self):
        """GET /api/storage should return storage statistics."""
        client = TestClient(app)

        mock_stats = StorageStats(
            database_size_bytes=1_000_000,
            database_size_pretty="1 MB",
            timestamp=datetime.now(tz=timezone.utc),
            tables=[
                TableStats(
                    table_name="transactions",
                    row_count=1000,
                    size_bytes=500_000,
                    size_pretty="500 KB",
                    is_hypertable=True,
                ),
                TableStats(
                    table_name="accounts",
                    row_count=50,
                    size_bytes=8000,
                    size_pretty="8 KB",
                    is_hypertable=False,
                ),
            ],
            compression={
                "transactions": {
                    "total_chunks": 10,
                    "compressed_chunks": 8,
                    "compression_ratio": None,
                }
            },
        )

        with patch("src.api.storage.StorageMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.get_storage_stats = AsyncMock(return_value=mock_stats)
            mock_monitor_class.return_value = mock_monitor

            response = client.get("/api/storage")

        assert response.status_code == 200
        data = response.json()
        assert data["database_size_bytes"] == 1_000_000
        assert data["database_size_pretty"] == "1 MB"
        assert "timestamp" in data
        assert len(data["tables"]) == 2
        assert data["tables"][0]["table_name"] == "transactions"
        assert data["tables"][0]["is_hypertable"] is True
        assert data["tables"][1]["table_name"] == "accounts"
        assert data["tables"][1]["is_hypertable"] is False
        assert "compression" in data
        assert "transactions" in data["compression"]

    def test_get_storage_stats_with_empty_database(self):
        """GET /api/storage should handle empty database."""
        client = TestClient(app)

        mock_stats = StorageStats(
            database_size_bytes=0,
            database_size_pretty="0 bytes",
            timestamp=datetime.now(tz=timezone.utc),
            tables=[],
            compression={},
        )

        with patch("src.api.storage.StorageMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.get_storage_stats = AsyncMock(return_value=mock_stats)
            mock_monitor_class.return_value = mock_monitor

            response = client.get("/api/storage")

        assert response.status_code == 200
        data = response.json()
        assert data["database_size_bytes"] == 0
        assert data["tables"] == []
        assert data["compression"] == {}

    def test_get_table_stats_returns_table_list(self):
        """GET /api/storage/tables should return table statistics."""
        client = TestClient(app)

        mock_tables = [
            TableStats(
                table_name="transactions",
                row_count=1000,
                size_bytes=500_000,
                size_pretty="500 KB",
                is_hypertable=True,
            ),
            TableStats(
                table_name="accounts",
                row_count=50,
                size_bytes=8000,
                size_pretty="8 KB",
                is_hypertable=False,
            ),
        ]

        with patch("src.api.storage.StorageMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.get_table_stats = AsyncMock(return_value=mock_tables)
            mock_monitor_class.return_value = mock_monitor

            response = client.get("/api/storage/tables")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["table_name"] == "transactions"
        assert data[0]["row_count"] == 1000
        assert data[0]["size_bytes"] == 500_000
        assert data[0]["size_pretty"] == "500 KB"
        assert data[0]["is_hypertable"] is True
        assert data[1]["table_name"] == "accounts"
        assert data[1]["is_hypertable"] is False

    def test_get_table_stats_with_empty_database(self):
        """GET /api/storage/tables should handle empty database."""
        client = TestClient(app)

        with patch("src.api.storage.StorageMonitor") as mock_monitor_class:
            mock_monitor = AsyncMock()
            mock_monitor.get_table_stats = AsyncMock(return_value=[])
            mock_monitor_class.return_value = mock_monitor

            response = client.get("/api/storage/tables")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
