"""Redis cache wrapper for governance resolved constraints.

This module provides a typed cache interface for storing and retrieving
governance-related data (resolved constraints, version hashes) with
automatic serialization to/from Pydantic models.

Classes:
    GovernanceCache: Redis cache wrapper with Pydantic model serialization

Example:
    >>> from redis.asyncio import Redis
    >>> redis = Redis.from_url("redis://localhost:6379")
    >>> cache = GovernanceCache(redis=redis)
    >>> await cache.set("constraints", "AAPL", resolved_constraints)
    >>> cached = await cache.get("constraints", "AAPL", ResolvedConstraints)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, TypeVar

from pydantic import BaseModel, ValidationError

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GovernanceCache:
    """Redis cache wrapper for governance resolved constraints.

    Provides typed get/set operations with automatic Pydantic model
    serialization. All keys are namespaced under the 'governance' prefix.

    Attributes:
        CACHE_PREFIX: Static prefix for all governance cache keys
        DEFAULT_TTL: Default time-to-live in seconds (5 minutes)

    Args:
        redis: Async Redis client instance
        ttl: Time-to-live for cached values in seconds (default: 300)
    """

    CACHE_PREFIX = "governance"
    DEFAULT_TTL = 300  # 5 minutes

    def __init__(self, redis: Redis, ttl: int = DEFAULT_TTL) -> None:
        """Initialize the cache with a Redis client.

        Args:
            redis: Async Redis client instance
            ttl: Time-to-live for cached values in seconds
        """
        self.redis = redis
        self.ttl = ttl

    def _key(self, namespace: str, key: str) -> str:
        """Build a fully-qualified cache key.

        Args:
            namespace: The namespace (e.g., 'constraints', 'resolved')
            key: The specific key within the namespace

        Returns:
            Fully-qualified key in format: governance:{namespace}:{key}
        """
        return f"{self.CACHE_PREFIX}:{namespace}:{key}"

    async def get(self, namespace: str, key: str, model_cls: type[T]) -> T | None:
        """Get cached value and deserialize to Pydantic model.

        Args:
            namespace: The namespace (e.g., 'constraints', 'resolved')
            key: The specific key within the namespace
            model_cls: Pydantic model class to deserialize into

        Returns:
            Deserialized model instance, or None if not found or invalid
        """
        cache_key = self._key(namespace, key)
        try:
            data = await self.redis.get(cache_key)
            if data is None:
                return None

            # Decode bytes to string if necessary
            if isinstance(data, bytes):
                data = data.decode("utf-8")

            # Parse JSON and validate with Pydantic
            parsed = json.loads(data)
            return model_cls.model_validate(parsed)

        except json.JSONDecodeError:
            logger.warning("Invalid JSON in cache key %s", cache_key)
            return None
        except ValidationError as e:
            logger.warning("Validation error for cache key %s: %s", cache_key, e)
            return None

    async def set(self, namespace: str, key: str, value: BaseModel) -> None:
        """Cache a Pydantic model with TTL.

        Args:
            namespace: The namespace (e.g., 'constraints', 'resolved')
            key: The specific key within the namespace
            value: Pydantic model instance to cache
        """
        cache_key = self._key(namespace, key)
        # Serialize to JSON string
        data = value.model_dump_json()
        await self.redis.set(cache_key, data, ex=self.ttl)

    async def delete(self, namespace: str, key: str) -> None:
        """Delete a cached value.

        Args:
            namespace: The namespace
            key: The specific key within the namespace
        """
        cache_key = self._key(namespace, key)
        await self.redis.delete(cache_key)

    async def invalidate_namespace(self, namespace: str) -> int:
        """Invalidate all keys in a namespace.

        Scans for all keys matching the namespace pattern and deletes them.

        Args:
            namespace: The namespace to invalidate

        Returns:
            Count of deleted keys
        """
        pattern = f"{self.CACHE_PREFIX}:{namespace}:*"
        keys_to_delete: list[bytes] = []

        # Use SCAN to iterate through keys (safer than KEYS for production)
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor=cursor, match=pattern)
            keys_to_delete.extend(keys)
            if cursor == 0:
                break

        if not keys_to_delete:
            return 0

        # Delete all found keys
        return await self.redis.delete(*keys_to_delete)

    async def get_version(self, namespace: str) -> str | None:
        """Get current version hash for a namespace.

        Version hashes are stored under a special '_version' key within
        each namespace to track when cached data needs invalidation.

        Args:
            namespace: The namespace to get version for

        Returns:
            Version hash string, or None if not set
        """
        cache_key = self._key(namespace, "_version")
        data = await self.redis.get(cache_key)
        if data is None:
            return None
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return data

    async def set_version(self, namespace: str, version: str) -> None:
        """Set version hash for a namespace.

        Version hashes don't have TTL - they persist until explicitly
        updated on config change.

        Args:
            namespace: The namespace to set version for
            version: Version hash string (typically a content hash)
        """
        cache_key = self._key(namespace, "_version")
        # No TTL for version - persists until explicitly updated
        await self.redis.set(cache_key, version)


__all__ = ["GovernanceCache"]
