# AQ Trading AI Agents - Configuration
"""Centralized configuration for AI agents.

This module provides configuration settings for agent tools,
including database and Redis connection parameters.

Configuration is loaded from environment variables with sensible defaults.

Usage:
    from agents.config import get_config

    config = get_config()
    redis_url = config.redis_url
    db_url = config.database_url
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any


@dataclass(frozen=True)
class AgentConfig:
    """Configuration settings for AI agents.

    All settings can be overridden via environment variables.
    """

    # Redis configuration
    redis_host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    redis_port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    redis_db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    redis_password: str | None = field(default_factory=lambda: os.getenv("REDIS_PASSWORD"))

    # Database configuration
    database_url: str = field(
        default_factory=lambda: os.getenv(
            "DATABASE_URL",
            "sqlite+aiosqlite:///./aq_trading.db"
        )
    )

    # Data paths
    bars_csv_path: str = field(
        default_factory=lambda: os.getenv(
            "BARS_CSV_PATH",
            "backend/data/bars.csv"
        )
    )

    # CLI executor configuration
    cli_timeout: int = field(default_factory=lambda: int(os.getenv("CLI_TIMEOUT", "300")))

    @property
    def redis_url(self) -> str:
        """Build Redis URL from components."""
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache(maxsize=1)
def get_config() -> AgentConfig:
    """Get the agent configuration singleton.

    Returns:
        AgentConfig instance with settings from environment.
    """
    return AgentConfig()


def get_redis_config() -> dict[str, Any]:
    """Get Redis connection parameters as a dict.

    Returns:
        Dictionary suitable for redis.Redis() constructor.
    """
    config = get_config()
    params: dict[str, Any] = {
        "host": config.redis_host,
        "port": config.redis_port,
        "db": config.redis_db,
        "decode_responses": True,
    }
    if config.redis_password:
        params["password"] = config.redis_password
    return params


def get_database_url() -> str:
    """Get the database connection URL.

    Returns:
        SQLAlchemy-compatible database URL.
    """
    return get_config().database_url


def get_bars_csv_path() -> str:
    """Get the path to the bars CSV file.

    Returns:
        Path to bars.csv file.
    """
    return get_config().bars_csv_path
