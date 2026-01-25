# backend/src/api/storage.py
"""Storage monitoring API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_session
from src.services.storage_monitor import StorageMonitor

router = APIRouter(prefix="/api/storage", tags=["storage"])


class TableStatsResponse(BaseModel):
    """Table statistics response."""

    table_name: str
    row_count: int
    size_bytes: int
    size_pretty: str
    is_hypertable: bool


class StorageStatsResponse(BaseModel):
    """Storage statistics response."""

    database_size_bytes: int
    database_size_pretty: str
    timestamp: datetime
    tables: list[TableStatsResponse]
    compression: dict[str, Any]


@router.get("", response_model=StorageStatsResponse)
async def get_storage_stats(
    session: AsyncSession = Depends(get_session),
) -> StorageStatsResponse:
    """Get comprehensive storage statistics."""
    monitor = StorageMonitor(session)
    stats = await monitor.get_storage_stats()

    return StorageStatsResponse(
        database_size_bytes=stats.database_size_bytes,
        database_size_pretty=stats.database_size_pretty,
        timestamp=stats.timestamp,
        tables=[
            TableStatsResponse(
                table_name=t.table_name,
                row_count=t.row_count,
                size_bytes=t.size_bytes,
                size_pretty=t.size_pretty,
                is_hypertable=t.is_hypertable,
            )
            for t in stats.tables
        ],
        compression=stats.compression,
    )


@router.get("/tables", response_model=list[TableStatsResponse])
async def get_table_stats(
    session: AsyncSession = Depends(get_session),
) -> list[TableStatsResponse]:
    """Get statistics for each table."""
    monitor = StorageMonitor(session)
    tables = await monitor.get_table_stats()

    return [
        TableStatsResponse(
            table_name=t.table_name,
            row_count=t.row_count,
            size_bytes=t.size_bytes,
            size_pretty=t.size_pretty,
            is_hypertable=t.is_hypertable,
        )
        for t in tables
    ]
