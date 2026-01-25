"""Storage monitoring service for database tables and compression."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TableStats:
    """Statistics for a single table."""

    table_name: str
    row_count: int
    size_bytes: int
    size_pretty: str
    is_hypertable: bool


@dataclass(frozen=True)
class StorageStats:
    """Overall storage statistics."""

    database_size_bytes: int
    database_size_pretty: str
    timestamp: datetime
    tables: list[TableStats]
    compression: dict[str, Any]


class StorageMonitor:
    """Monitor database storage and compression."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_storage_stats(self) -> StorageStats:
        """Get comprehensive storage statistics."""
        # Get database size
        result = await self._session.execute(
            text("""
            SELECT
                pg_database_size(current_database()) as size_bytes,
                pg_size_pretty(pg_database_size(current_database())) as size_pretty
        """)
        )
        row = result.fetchone()
        db_size_bytes = row[0] if row else 0
        db_size_pretty = row[1] if row else "0 bytes"

        # Get table stats
        tables = await self.get_table_stats()

        # Get compression stats
        compression = await self.get_compression_stats()

        return StorageStats(
            database_size_bytes=db_size_bytes,
            database_size_pretty=db_size_pretty,
            timestamp=datetime.now(),
            tables=tables,
            compression=compression,
        )

    async def get_table_stats(self) -> list[TableStats]:
        """Get statistics for each table."""
        # Get all tables with their sizes
        result = await self._session.execute(
            text("""
            SELECT
                relname as table_name,
                n_live_tup as row_count,
                pg_total_relation_size(relid) as size_bytes,
                pg_size_pretty(pg_total_relation_size(relid)) as size_pretty
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(relid) DESC
        """)
        )
        rows = result.fetchall()

        # Check which tables are hypertables (handle case where TimescaleDB not installed)
        hypertable_names: set[str] = set()
        try:
            hypertables_result = await self._session.execute(
                text("""
                SELECT hypertable_name
                FROM timescaledb_information.hypertables
            """)
            )
            hypertable_names = {row[0] for row in hypertables_result.fetchall()}
        except Exception:
            # TimescaleDB not installed or not enabled - this is expected
            logger.debug("TimescaleDB not available, skipping hypertable detection")

        return [
            TableStats(
                table_name=row[0],
                row_count=row[1] or 0,
                size_bytes=row[2] or 0,
                size_pretty=row[3] or "0 bytes",
                is_hypertable=row[0] in hypertable_names,
            )
            for row in rows
        ]

    async def get_compression_stats(self) -> dict[str, Any]:
        """Get compression statistics for hypertables."""
        try:
            result = await self._session.execute(
                text("""
                SELECT
                    hypertable_name,
                    total_chunks,
                    compressed_chunks
                FROM (
                    SELECT
                        hypertable_name,
                        count(*) as total_chunks,
                        count(*) FILTER (WHERE is_compressed) as compressed_chunks
                    FROM timescaledb_information.chunks
                    GROUP BY hypertable_name
                ) chunk_stats
            """)
            )
            rows = result.fetchall()

            stats = {}
            for row in rows:
                stats[row[0]] = {
                    "total_chunks": row[1],
                    "compressed_chunks": row[2],
                    "compression_ratio": None,  # Would need additional queries for size info
                }
            return stats
        except Exception:
            # TimescaleDB not installed or no compression yet - this is expected
            logger.debug("TimescaleDB compression stats not available")
            return {}
