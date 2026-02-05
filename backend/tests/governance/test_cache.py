"""Tests for governance Redis cache wrapper.

TDD: Write tests FIRST, then implement cache to make them pass.
"""

from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel


class SampleModel(BaseModel):
    """Sample Pydantic model for testing cache."""

    name: str
    value: int


class TestGovernanceCache:
    """Tests for GovernanceCache class."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock async Redis client."""
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.set = AsyncMock()
        redis.delete = AsyncMock()
        redis.scan = AsyncMock(return_value=(0, []))
        return redis

    def test_cache_prefix_constant(self):
        """Cache should use 'governance' prefix."""
        from src.governance.cache import GovernanceCache

        assert GovernanceCache.CACHE_PREFIX == "governance"

    def test_default_ttl_constant(self):
        """Default TTL should be 300 seconds (5 minutes)."""
        from src.governance.cache import GovernanceCache

        assert GovernanceCache.DEFAULT_TTL == 300

    def test_key_format(self, mock_redis):
        """Cache key should be formatted as prefix:namespace:key."""
        from src.governance.cache import GovernanceCache

        cache = GovernanceCache(redis=mock_redis)
        key = cache._key("constraints", "AAPL")
        assert key == "governance:constraints:AAPL"

    def test_key_format_with_complex_key(self, mock_redis):
        """Cache key should handle complex keys."""
        from src.governance.cache import GovernanceCache

        cache = GovernanceCache(redis=mock_redis)
        key = cache._key("resolved", "symbol:AAPL:strategy:momentum")
        assert key == "governance:resolved:symbol:AAPL:strategy:momentum"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_not_found(self, mock_redis):
        """get() should return None when key doesn't exist."""
        from src.governance.cache import GovernanceCache

        mock_redis.get.return_value = None
        cache = GovernanceCache(redis=mock_redis)

        result = await cache.get("constraints", "AAPL", SampleModel)
        assert result is None
        mock_redis.get.assert_called_once_with("governance:constraints:AAPL")

    @pytest.mark.asyncio
    async def test_get_deserializes_to_model(self, mock_redis):
        """get() should deserialize JSON to Pydantic model."""
        from src.governance.cache import GovernanceCache

        mock_redis.get.return_value = b'{"name": "test", "value": 42}'
        cache = GovernanceCache(redis=mock_redis)

        result = await cache.get("constraints", "AAPL", SampleModel)

        assert result is not None
        assert isinstance(result, SampleModel)
        assert result.name == "test"
        assert result.value == 42

    @pytest.mark.asyncio
    async def test_set_serializes_model(self, mock_redis):
        """set() should serialize Pydantic model to JSON."""
        from src.governance.cache import GovernanceCache

        cache = GovernanceCache(redis=mock_redis)
        model = SampleModel(name="test", value=42)

        await cache.set("constraints", "AAPL", model)

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "governance:constraints:AAPL"
        # Verify JSON content (order-independent)
        import json

        stored_data = json.loads(call_args[0][1])
        assert stored_data == {"name": "test", "value": 42}
        assert call_args[1]["ex"] == 300  # Default TTL

    @pytest.mark.asyncio
    async def test_set_with_custom_ttl(self, mock_redis):
        """set() should accept custom TTL."""
        from src.governance.cache import GovernanceCache

        cache = GovernanceCache(redis=mock_redis, ttl=600)
        model = SampleModel(name="test", value=42)

        await cache.set("constraints", "AAPL", model)

        call_args = mock_redis.set.call_args
        assert call_args[1]["ex"] == 600

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, mock_redis):
        """delete() should remove the cached value."""
        from src.governance.cache import GovernanceCache

        cache = GovernanceCache(redis=mock_redis)

        await cache.delete("constraints", "AAPL")

        mock_redis.delete.assert_called_once_with("governance:constraints:AAPL")

    @pytest.mark.asyncio
    async def test_invalidate_namespace_deletes_all_matching_keys(self, mock_redis):
        """invalidate_namespace() should delete all keys in namespace."""
        from src.governance.cache import GovernanceCache

        # Simulate scan returning some keys, then empty (end of iteration)
        mock_redis.scan.side_effect = [
            (1, [b"governance:constraints:AAPL", b"governance:constraints:GOOG"]),
            (0, [b"governance:constraints:MSFT"]),
        ]
        mock_redis.delete.return_value = 3

        cache = GovernanceCache(redis=mock_redis)

        count = await cache.invalidate_namespace("constraints")

        assert count == 3
        # Should have called scan with pattern
        mock_redis.scan.assert_called()

    @pytest.mark.asyncio
    async def test_invalidate_namespace_returns_zero_when_empty(self, mock_redis):
        """invalidate_namespace() should return 0 when no keys found."""
        from src.governance.cache import GovernanceCache

        mock_redis.scan.return_value = (0, [])

        cache = GovernanceCache(redis=mock_redis)

        count = await cache.invalidate_namespace("constraints")

        assert count == 0

    @pytest.mark.asyncio
    async def test_get_version_returns_string(self, mock_redis):
        """get_version() should return version hash string."""
        from src.governance.cache import GovernanceCache

        mock_redis.get.return_value = b"abc123def456"
        cache = GovernanceCache(redis=mock_redis)

        version = await cache.get_version("constraints")

        assert version == "abc123def456"
        mock_redis.get.assert_called_once_with("governance:constraints:_version")

    @pytest.mark.asyncio
    async def test_get_version_returns_none_when_not_set(self, mock_redis):
        """get_version() should return None when version not set."""
        from src.governance.cache import GovernanceCache

        mock_redis.get.return_value = None
        cache = GovernanceCache(redis=mock_redis)

        version = await cache.get_version("constraints")

        assert version is None

    @pytest.mark.asyncio
    async def test_set_version_stores_hash(self, mock_redis):
        """set_version() should store version hash."""
        from src.governance.cache import GovernanceCache

        cache = GovernanceCache(redis=mock_redis)

        await cache.set_version("constraints", "abc123def456")

        mock_redis.set.assert_called_once_with(
            "governance:constraints:_version",
            "abc123def456",
        )

    @pytest.mark.asyncio
    async def test_get_handles_invalid_json(self, mock_redis):
        """get() should return None for invalid JSON."""
        from src.governance.cache import GovernanceCache

        mock_redis.get.return_value = b"not valid json"
        cache = GovernanceCache(redis=mock_redis)

        result = await cache.get("constraints", "AAPL", SampleModel)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_handles_validation_error(self, mock_redis):
        """get() should return None when model validation fails."""
        from src.governance.cache import GovernanceCache

        # Valid JSON but missing required field
        mock_redis.get.return_value = b'{"name": "test"}'
        cache = GovernanceCache(redis=mock_redis)

        result = await cache.get("constraints", "AAPL", SampleModel)

        assert result is None


class TestGovernanceCacheIntegration:
    """Integration tests for GovernanceCache (require actual Redis)."""

    @pytest.fixture
    async def real_cache(self):
        """Create a GovernanceCache backed by real Redis, with cleanup."""
        from redis.asyncio import Redis
        from src.governance.cache import GovernanceCache

        redis_client = Redis.from_url("redis://localhost:6379", decode_responses=False)
        cache = GovernanceCache(redis=redis_client, ttl=10)
        yield cache
        # Cleanup: remove any keys created during the test
        await cache.invalidate_namespace("test_integration")
        await redis_client.aclose()

    @pytest.mark.asyncio
    async def test_round_trip_with_real_redis(self, real_cache):
        """Full round-trip: set, get, delete against actual Redis."""
        model = SampleModel(name="integration", value=99)

        # Set
        await real_cache.set("test_integration", "key1", model)

        # Get
        result = await real_cache.get("test_integration", "key1", SampleModel)
        assert result is not None
        assert result.name == "integration"
        assert result.value == 99

        # Delete
        await real_cache.delete("test_integration", "key1")
        after_delete = await real_cache.get("test_integration", "key1", SampleModel)
        assert after_delete is None

    @pytest.mark.asyncio
    async def test_version_round_trip_with_real_redis(self, real_cache):
        """Version set/get round-trip against actual Redis."""
        await real_cache.set_version("test_integration", "v1_abc123")
        version = await real_cache.get_version("test_integration")
        assert version == "v1_abc123"

        # Update version
        await real_cache.set_version("test_integration", "v2_def456")
        version = await real_cache.get_version("test_integration")
        assert version == "v2_def456"

    @pytest.mark.asyncio
    async def test_invalidate_namespace_with_real_redis(self, real_cache):
        """Namespace invalidation against actual Redis."""
        m1 = SampleModel(name="a", value=1)
        m2 = SampleModel(name="b", value=2)

        await real_cache.set("test_integration", "k1", m1)
        await real_cache.set("test_integration", "k2", m2)

        # Both keys exist
        assert await real_cache.get("test_integration", "k1", SampleModel) is not None
        assert await real_cache.get("test_integration", "k2", SampleModel) is not None

        # Invalidate namespace
        count = await real_cache.invalidate_namespace("test_integration")
        assert count >= 2

        # Both keys gone
        assert await real_cache.get("test_integration", "k1", SampleModel) is None
        assert await real_cache.get("test_integration", "k2", SampleModel) is None
