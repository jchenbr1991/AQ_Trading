"""DB buffer with WAL persistence for graceful degradation.

This module provides a buffer for database writes that failed during degraded mode.
Key features:
- Memory explosion protection using json.dumps size for byte calculation
- WAL (Write-Ahead Log) persistence for crash recovery
- Idempotent keys for replay deduplication (resource_type:resource_id:seq_no)
- WAL replay only restores LOCAL state, does NOT trigger external actions

Usage:
    buffer = DBBuffer(config=config, wal_path=Path("/var/data/db.wal"))

    # Add entries when DB writes fail
    entry = BufferEntry(
        resource_type="order",
        resource_id="12345",
        data={"symbol": "AAPL", "qty": 100},
        timestamp=datetime.now(tz=timezone.utc),
        idempotent_key="order:12345:1",
    )
    if not buffer.add(entry):
        # Buffer full - emit DB_BUFFER_OVERFLOW event
        pass

    # When DB recovers, flush buffer
    flushed = await buffer.flush_to_db(db_session)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.degradation.config import DegradationConfig

logger = logging.getLogger(__name__)


@dataclass
class BufferEntry:
    """A single entry in the DB buffer.

    Attributes:
        resource_type: Type of resource (e.g., "order", "position")
        resource_id: Unique identifier for the resource
        data: The data to be written to the database
        timestamp: When the entry was created
        idempotent_key: Unique key for deduplication (format: resource_type:resource_id:seq_no)
    """

    resource_type: str
    resource_id: str
    data: dict[str, Any]
    timestamp: datetime
    idempotent_key: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for WAL serialization."""
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "idempotent_key": self.idempotent_key,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BufferEntry:
        """Create from dictionary (WAL deserialization)."""
        return cls(
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            data=data["data"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            idempotent_key=data["idempotent_key"],
        )


class DBBuffer:
    """Buffer for database writes with WAL persistence.

    This buffer stores database writes that failed during degraded mode.
    It provides:
    - Memory explosion protection using json.dumps size for byte calculation
    - WAL persistence for crash recovery
    - Idempotent key deduplication

    Attributes:
        config: Degradation configuration with buffer limits
        wal_path: Path to WAL file (None to disable WAL)
    """

    def __init__(
        self,
        config: DegradationConfig,
        wal_path: Path | None = None,
    ) -> None:
        """Initialize the DB buffer.

        Args:
            config: Degradation configuration with buffer limits
            wal_path: Path to WAL file (None to disable WAL)
        """
        self._config = config
        self._wal_path = wal_path

        # In-memory storage
        self._entries: list[BufferEntry] = []
        self._idempotent_keys: set[str] = set()
        self._byte_count: int = 0

        # Restore from WAL if exists
        if wal_path is not None:
            self._restore_from_wal()

    @property
    def entry_count(self) -> int:
        """Number of entries in the buffer."""
        return len(self._entries)

    @property
    def byte_count(self) -> int:
        """Total bytes of buffered data (json.dumps serialized size)."""
        return self._byte_count

    @property
    def is_full(self) -> bool:
        """Check if buffer is at capacity.

        Buffer is full when max_entries is reached.
        Note: max_bytes is checked per-add, not here.
        """
        return self._entry_count >= self._config.db_buffer_max_entries

    @property
    def _entry_count(self) -> int:
        """Internal entry count property for is_full check."""
        return len(self._entries)

    def add(self, entry: BufferEntry) -> bool:
        """Add entry to buffer.

        Returns False if buffer is full (max_entries or max_bytes exceeded).
        Uses json.dumps serialization for byte calculation.

        Args:
            entry: The BufferEntry to add

        Returns:
            True if entry was added, False if buffer is full
        """
        # Check for duplicate idempotent key
        if entry.idempotent_key in self._idempotent_keys:
            logger.debug(f"Duplicate idempotent key: {entry.idempotent_key}")
            return True  # Already have this entry, consider it a success

        # Calculate entry size using json.dumps
        serialized = json.dumps(entry.data)
        entry_bytes = len(serialized.encode("utf-8"))

        # Check max_entries limit
        if self._entry_count >= self._config.db_buffer_max_entries:
            logger.warning(f"DB buffer full: max_entries={self._config.db_buffer_max_entries}")
            return False

        # Check max_bytes limit
        if self._byte_count + entry_bytes >= self._config.db_buffer_max_bytes:
            logger.warning(
                f"DB buffer full: max_bytes={self._config.db_buffer_max_bytes}, "
                f"current={self._byte_count}, new_entry={entry_bytes}"
            )
            return False

        # Add to buffer
        self._entries.append(entry)
        self._idempotent_keys.add(entry.idempotent_key)
        self._byte_count += entry_bytes

        # Write to WAL
        self._write_wal(entry)

        logger.debug(
            f"Added entry to buffer: {entry.idempotent_key}, "
            f"entries={self.entry_count}, bytes={self.byte_count}"
        )

        return True

    async def flush_to_db(self, db_session: Any) -> int:
        """Flush buffer to database.

        Args:
            db_session: Database session for writing

        Returns:
            Count of entries flushed
        """
        if not self._entries:
            return 0

        flushed_count = len(self._entries)

        # TODO: Implement actual database write logic
        # For now, we just clear the buffer
        # In production, this would:
        # 1. Group entries by resource_type
        # 2. Batch write to appropriate tables
        # 3. Handle partial failures

        logger.info(f"Flushing {flushed_count} entries to database")

        # Clear buffer
        self._entries.clear()
        self._idempotent_keys.clear()
        self._byte_count = 0

        # Clear WAL
        self._clear_wal()

        return flushed_count

    def _write_wal(self, entry: BufferEntry) -> None:
        """Write entry to WAL file.

        Each entry is written as a single JSON line (JSONL format).

        Args:
            entry: The entry to write
        """
        if self._wal_path is None:
            return

        try:
            with open(self._wal_path, "a", encoding="utf-8") as f:
                line = json.dumps(entry.to_dict())
                f.write(line + "\n")
        except OSError as e:
            logger.error(f"Failed to write WAL: {e}")

    def _read_wal(self) -> list[BufferEntry]:
        """Read entries from WAL file.

        Returns:
            List of BufferEntry objects from WAL
        """
        if self._wal_path is None or not self._wal_path.exists():
            return []

        entries: list[BufferEntry] = []
        try:
            with open(self._wal_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entry = BufferEntry.from_dict(data)
                        entries.append(entry)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.warning(f"Skipping invalid WAL entry: {e}")
        except OSError as e:
            logger.error(f"Failed to read WAL: {e}")

        return entries

    def _restore_from_wal(self) -> None:
        """Restore buffer state from WAL.

        This only restores LOCAL state - it does NOT trigger any external actions.
        Duplicate idempotent keys are deduplicated.
        """
        entries = self._read_wal()

        for entry in entries:
            # Skip duplicates
            if entry.idempotent_key in self._idempotent_keys:
                continue

            # Calculate bytes
            serialized = json.dumps(entry.data)
            entry_bytes = len(serialized.encode("utf-8"))

            # Add to buffer (skip limit checks during restore)
            self._entries.append(entry)
            self._idempotent_keys.add(entry.idempotent_key)
            self._byte_count += entry_bytes

        if entries:
            logger.info(
                f"Restored {len(self._entries)} entries from WAL " f"({self._byte_count} bytes)"
            )

    def _clear_wal(self) -> None:
        """Clear the WAL file after successful flush."""
        if self._wal_path is None:
            return

        try:
            with open(self._wal_path, "w", encoding="utf-8") as f:
                f.truncate(0)
        except OSError as e:
            logger.error(f"Failed to clear WAL: {e}")
