"""Idempotency service for API request deduplication.

This module provides the IdempotencyService class that stores and retrieves
idempotency keys with their associated response data. Keys expire after
a configurable TTL (default: 24 hours).
"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class IdempotencyService:
    """Persistent idempotency key storage with TTL.

    Used to ensure API endpoints like close_position are idempotent.
    Duplicate requests with the same idempotency key return cached responses.
    """

    def __init__(self, session: AsyncSession):
        """Initialize service with database session.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self.session = session

    async def store_key(
        self,
        key: str,
        resource_type: str,
        resource_id: str,
        response_data: dict,
        ttl_hours: int = 24,
    ) -> None:
        """Store an idempotency key and its response data.

        Uses INSERT ... ON CONFLICT DO NOTHING to handle race conditions.

        Args:
            key: The idempotency key (typically from Idempotency-Key header)
            resource_type: Type of resource (e.g., "close_position", "acknowledge_alert")
            resource_id: ID of the affected resource
            response_data: The response to cache for duplicate requests
            ttl_hours: Time-to-live in hours (default: 24)
        """
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        sql = text("""
            INSERT INTO idempotency_keys (key, resource_type, resource_id, response_data, expires_at)
            VALUES (:key, :resource_type, :resource_id, :response_data, :expires_at)
            ON CONFLICT (key) DO NOTHING
        """)

        await self.session.execute(
            sql,
            {
                "key": key,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "response_data": json.dumps(response_data),
                "expires_at": expires_at,
            },
        )
        await self.session.commit()

    async def get_cached_response(self, key: str) -> tuple[bool, dict | None]:
        """Get cached response for an idempotency key.

        Only returns data if the key exists AND has not expired.

        Args:
            key: The idempotency key to look up

        Returns:
            Tuple of (exists, response_data):
                - (True, dict) if key exists and not expired
                - (False, None) if key doesn't exist or is expired
        """
        sql = text("""
            SELECT response_data
            FROM idempotency_keys
            WHERE key = :key AND expires_at > NOW()
        """)

        result = await self.session.execute(sql, {"key": key})
        row = result.fetchone()

        if row is None:
            return (False, None)

        response_data = json.loads(row[0])
        return (True, response_data)

    async def cleanup_expired(self) -> int:
        """Delete expired idempotency keys.

        Should be called periodically by a cleanup job.

        Returns:
            Number of deleted keys
        """
        sql = text("""
            DELETE FROM idempotency_keys
            WHERE expires_at <= NOW()
        """)

        result = await self.session.execute(sql)
        await self.session.commit()
        return result.rowcount
