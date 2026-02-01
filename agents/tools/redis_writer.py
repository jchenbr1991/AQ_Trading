# AQ Trading AI Agents - Redis Writer Tool
# T027: Write to allowed Redis keys only
"""Redis writer tool for AI agents.

This tool allows agents to write to specific Redis keys with
strict key prefix restrictions for security.

Only the following key prefixes are allowed:
- risk_bias: For Risk Controller agent
- sentiment: For Analyst agent

Usage:
    tool = create_redis_writer_tool()
    result = await tool.execute(
        key="sentiment:AAPL",
        value={"score": 0.75, "source": "news"}
    )
"""

from typing import Any

from agents.base import Tool


# Allowed key prefixes and their descriptions
ALLOWED_KEY_PREFIXES = {
    "risk_bias": "Risk bias adjustment (Risk Controller only)",
    "sentiment": "Sentiment scores by symbol (Analyst only)",
    "events": "Event tags for market events (Analyst only)",
}


class RedisKeyValidationError(Exception):
    """Raised when attempting to write to a disallowed Redis key."""

    def __init__(self, key: str, allowed_prefixes: list[str]) -> None:
        self.key = key
        self.allowed_prefixes = allowed_prefixes
        super().__init__(
            f"Key '{key}' is not allowed. "
            f"Allowed prefixes: {allowed_prefixes}"
        )


def validate_key_prefix(key: str) -> bool:
    """Check if a Redis key has an allowed prefix.

    Args:
        key: The Redis key to validate

    Returns:
        True if the key starts with an allowed prefix
    """
    return any(
        key == prefix or key.startswith(f"{prefix}:")
        for prefix in ALLOWED_KEY_PREFIXES.keys()
    )


async def write_redis(
    key: str,
    value: Any,
    ttl: int | None = None,
) -> dict[str, Any]:
    """Write a value to Redis with key prefix validation.

    This function enforces strict key prefix restrictions. Only keys
    starting with allowed prefixes (risk_bias, sentiment) can be written.

    Args:
        key: Redis key to write to (must start with allowed prefix)
        value: Value to store (will be JSON-serialized)
        ttl: Optional time-to-live in seconds

    Returns:
        Dictionary containing:
        - status: 'success', 'error', or 'not_implemented'
        - key: The key that was written to
        - ttl: TTL if set
        - error: Error message if status is 'error'

    Raises:
        RedisKeyValidationError: If key doesn't have an allowed prefix

    Example:
        >>> result = await write_redis(
        ...     key="sentiment:AAPL",
        ...     value={"score": 0.75},
        ...     ttl=3600
        ... )
        >>> result["status"]
        'not_implemented'
    """
    # Validate key prefix
    if not key:
        return {
            "status": "error",
            "error": "Key is required",
        }

    if not validate_key_prefix(key):
        allowed = list(ALLOWED_KEY_PREFIXES.keys())
        return {
            "status": "error",
            "error": f"Key '{key}' is not allowed. Must start with: {allowed}",
            "allowed_prefixes": allowed,
        }

    # Placeholder implementation
    # TODO: Integrate with Redis service
    return {
        "status": "not_implemented",
        "key": key,
        "value_type": type(value).__name__,
        "ttl": ttl,
        "message": "Redis service integration pending",
    }


async def write_risk_bias(
    value: float,
    reason: str | None = None,
) -> dict[str, Any]:
    """Write a risk bias value to Redis.

    Convenience function for writing the risk_bias key.

    Args:
        value: Risk bias value (typically -1.0 to 1.0)
        reason: Optional reason for the bias change

    Returns:
        Dictionary containing the write result.

    Example:
        >>> result = await write_risk_bias(value=-0.5, reason="VIX elevated")
        >>> result["status"]
        'not_implemented'
    """
    return await write_redis(
        key="risk_bias",
        value={
            "bias": value,
            "reason": reason,
        },
    )


async def write_sentiment(
    symbol: str,
    score: float,
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a sentiment score for a symbol to Redis.

    Convenience function for writing sentiment:* keys.

    Args:
        symbol: Ticker symbol (e.g., "AAPL")
        score: Sentiment score (typically -1.0 to 1.0)
        source: Source of the sentiment (e.g., "news", "social")
        metadata: Additional metadata about the sentiment

    Returns:
        Dictionary containing the write result.

    Example:
        >>> result = await write_sentiment(
        ...     symbol="AAPL",
        ...     score=0.75,
        ...     source="news"
        ... )
        >>> result["status"]
        'not_implemented'
    """
    return await write_redis(
        key=f"sentiment:{symbol}",
        value={
            "score": score,
            "source": source,
            "metadata": metadata or {},
        },
    )


def create_redis_writer_tool() -> Tool:
    """Create and return the Redis writer tool.

    Returns:
        Tool instance configured for Redis write operations.

    The tool requires the following permissions:
    - redis:risk_bias: Write risk bias (Risk Controller)
    - redis:sentiment:*: Write sentiment scores (Analyst)
    """
    return Tool(
        name="redis_write",
        description="Write values to allowed Redis keys. Only keys starting with "
        "'risk_bias' or 'sentiment' are permitted. Enforces strict key validation.",
        execute=write_redis,
        required_permissions=["redis:*"],
    )


def create_risk_bias_tool() -> Tool:
    """Create and return the risk bias tool.

    Returns:
        Tool instance configured for risk bias updates.

    The tool requires the following permissions:
    - redis:risk_bias: Write risk bias value
    """
    return Tool(
        name="risk_bias",
        description="Update the risk bias value. Used by Risk Controller agent "
        "to adjust portfolio risk appetite based on market conditions.",
        execute=write_risk_bias,
        required_permissions=["redis:risk_bias"],
    )


def create_sentiment_tool() -> Tool:
    """Create and return the sentiment writer tool.

    Returns:
        Tool instance configured for sentiment updates.

    The tool requires the following permissions:
    - redis:sentiment:*: Write sentiment scores
    """
    return Tool(
        name="sentiment",
        description="Update sentiment score for a symbol. Used by Analyst agent "
        "to store analyzed sentiment from news and social sources.",
        execute=write_sentiment,
        required_permissions=["redis:sentiment:*"],
    )
