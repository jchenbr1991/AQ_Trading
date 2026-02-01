# AQ Trading AI Agents - Connection Management
"""Connection pooling for Redis and Database.

This module provides connection pools that are shared across agent tools,
avoiding the overhead of creating new connections for each operation.

Usage:
    from agents.connections import get_redis_pool, get_db_session

    # Redis
    async with get_redis_pool() as redis:
        await redis.get("key")

    # Database
    async with get_db_session() as session:
        result = await session.execute(...)
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from agents.config import get_redis_config, get_database_url

logger = logging.getLogger(__name__)

# Global connection pools (lazy initialized)
_redis_pool = None
_db_engine = None
_db_session_factory = None


async def _get_redis_pool():
    """Get or create the Redis connection pool."""
    global _redis_pool
    if _redis_pool is None:
        try:
            import redis.asyncio as redis
            _redis_pool = redis.ConnectionPool(**get_redis_config())
            logger.info("Redis connection pool created")
        except ImportError:
            logger.warning("Redis client not available")
            return None
    return _redis_pool


async def _get_db_engine():
    """Get or create the database engine."""
    global _db_engine, _db_session_factory
    if _db_engine is None:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
            from sqlalchemy.orm import sessionmaker

            _db_engine = create_async_engine(
                get_database_url(),
                echo=False,
                pool_pre_ping=True,  # Verify connections are alive
            )
            _db_session_factory = sessionmaker(
                _db_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            logger.info("Database engine created")
        except ImportError:
            logger.warning("SQLAlchemy not available")
            return None, None
    return _db_engine, _db_session_factory


@asynccontextmanager
async def get_redis() -> AsyncGenerator:
    """Get a Redis connection from the pool.

    Yields:
        Redis client instance.

    Raises:
        RuntimeError: If Redis is not available.

    Example:
        async with get_redis() as redis:
            value = await redis.get("key")
    """
    pool = await _get_redis_pool()
    if pool is None:
        raise RuntimeError("Redis not available")

    import redis.asyncio as redis_lib
    client = redis_lib.Redis(connection_pool=pool)
    try:
        yield client
    finally:
        await client.aclose()


@asynccontextmanager
async def get_redis_or_none() -> AsyncGenerator:
    """Get a Redis connection, or None if unavailable.

    This is a convenience method for graceful degradation.

    Yields:
        Redis client instance or None if unavailable.
    """
    try:
        async with get_redis() as client:
            yield client
    except (RuntimeError, ImportError):
        yield None


@asynccontextmanager
async def get_db_session() -> AsyncGenerator:
    """Get a database session.

    Yields:
        AsyncSession instance.

    Raises:
        RuntimeError: If database is not available.

    Example:
        async with get_db_session() as session:
            result = await session.execute(select(Model))
    """
    _, session_factory = await _get_db_engine()
    if session_factory is None:
        raise RuntimeError("Database not available")

    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_db_session_or_none() -> AsyncGenerator:
    """Get a database session, or None if unavailable.

    This is a convenience method for graceful degradation.

    Yields:
        AsyncSession instance or None if unavailable.
    """
    try:
        async with get_db_session() as session:
            yield session
    except (RuntimeError, ImportError):
        yield None


async def close_all_connections() -> None:
    """Close all connection pools.

    Call this during shutdown to cleanly release resources.
    """
    global _redis_pool, _db_engine, _db_session_factory

    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis connection pool closed")

    if _db_engine is not None:
        await _db_engine.dispose()
        _db_engine = None
        _db_session_factory = None
        logger.info("Database engine disposed")
