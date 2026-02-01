# AQ Trading AI Agents - Redis Writer Tool
# T027: Write to allowed Redis keys only
"""Redis writer tool for AI agents.

This tool allows agents to write to specific Redis keys with
strict key prefix restrictions for security.

Only the following key prefixes are allowed:
- risk_bias: For Risk Controller agent
- sentiment: For Analyst agent
- events: For Analyst agent

Usage:
    tool = create_redis_writer_tool()
    result = await tool.execute(
        key="sentiment:AAPL",
        value={"score": 0.75, "source": "news"}
    )
"""

import json
import logging
from datetime import datetime
from typing import Any

from agents.base import Tool
from agents.connections import get_redis_or_none

logger = logging.getLogger(__name__)

# Allowed key prefixes and their descriptions
# NOTE: Role-based validation (which roles can write which keys) is handled
# by PermissionChecker in agents/permissions.py - that is the authoritative
# source. This list is for tool-level validation (basic sanity check).
ALLOWED_KEY_PREFIXES = {
    "risk_bias": "Risk bias adjustment (Risk Controller only)",
    "sentiment": "Sentiment scores by symbol (Analyst only)",
    "events": "Event tags for market events (Analyst only)",
}

# Import PermissionChecker for role-based validation
from agents.permissions import PermissionChecker, AgentRole

_permission_checker = PermissionChecker()

# Default TTL values in seconds
DEFAULT_TTL = {
    "sentiment": 3600,  # 1 hour
    "events": 86400,    # 24 hours
    "risk_bias": None,  # Persistent
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
    """Check if a Redis key has an allowed prefix (basic sanity check).

    NOTE: This is a basic format validation. For role-based access control,
    use validate_key_for_role() which delegates to PermissionChecker.

    Args:
        key: The Redis key to validate

    Returns:
        True if the key starts with an allowed prefix
    """
    return any(
        key == prefix or key.startswith(f"{prefix}:")
        for prefix in ALLOWED_KEY_PREFIXES.keys()
    )


def validate_key_for_role(key: str, role: AgentRole) -> bool:
    """Validate if a role can write to a specific Redis key.

    This uses the centralized PermissionChecker as the authoritative source
    for role-based access control.

    Args:
        key: The Redis key to write to
        role: The agent role attempting the write

    Returns:
        True if the role is allowed to write to the key
    """
    # PermissionChecker expects "redis:key" format
    resource = f"redis:{key}"
    return _permission_checker.can_write(role, resource)


def get_ttl_for_key(key: str) -> int | None:
    """Get the default TTL for a key based on its prefix."""
    for prefix, ttl in DEFAULT_TTL.items():
        if key == prefix or key.startswith(f"{prefix}:"):
            return ttl
    return None


async def write_redis(
    key: str,
    value: Any,
    ttl: int | None = None,
) -> dict[str, Any]:
    """Write a value to Redis with key prefix validation.

    This function enforces strict key prefix restrictions. Only keys
    starting with allowed prefixes (risk_bias, sentiment, events) can be written.

    Args:
        key: Redis key to write to (must start with allowed prefix)
        value: Value to store (will be JSON-serialized)
        ttl: Optional time-to-live in seconds (uses default if not specified)

    Returns:
        Dictionary containing:
        - status: 'success' or 'error'
        - key: The key that was written to
        - ttl: TTL if set
        - error: Error message if status is 'error'

    Note:
        Invalid keys return an error dictionary rather than raising an exception.
        This allows callers to handle validation failures gracefully.

    Example:
        >>> result = await write_redis(
        ...     key="sentiment:AAPL",
        ...     value={"score": 0.75},
        ...     ttl=3600
        ... )
        >>> result["status"]
        'success'
    """
    # Validate key
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

    try:
        async with get_redis_or_none() as client:
            if client is None:
                logger.warning("Redis not available")
                return {
                    "status": "error",
                    "error": "Redis not available",
                    "key": key,
                }

            # Serialize value to JSON
            json_value = json.dumps(value)

            # Use provided TTL or default for key type
            effective_ttl = ttl if ttl is not None else get_ttl_for_key(key)

            # Write to Redis
            if effective_ttl:
                await client.setex(key, effective_ttl, json_value)
            else:
                await client.set(key, json_value)

            logger.info("Redis write: key=%s, ttl=%s", key, effective_ttl)

            return {
                "status": "success",
                "key": key,
                "ttl": effective_ttl,
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error("Redis write failed: %s", e)
        return {
            "status": "error",
            "error": f"Write failed: {str(e)}",
            "key": key,
        }


async def write_risk_bias(
    value: float,
    reason: str | None = None,
) -> dict[str, Any]:
    """Write a risk bias value to Redis.

    Convenience function for writing the risk_bias key.
    The value is stored as a plain float string per Redis schema,
    as RiskManager expects to call float() on the raw value.

    Args:
        value: Risk bias value (0.0 to 1.0, where 1.0 = full risk appetite)
        reason: Optional reason for the bias change (logged, not stored)

    Returns:
        Dictionary containing the write result.

    Example:
        >>> result = await write_risk_bias(value=0.5, reason="VIX elevated")
        >>> result["status"]
        'success'
    """
    # Validate bias value
    if not 0.0 <= value <= 1.0:
        return {
            "status": "error",
            "error": f"Risk bias must be between 0.0 and 1.0, got {value}",
        }

    if reason:
        logger.info("Writing risk_bias=%s, reason=%s", value, reason)

    try:
        async with get_redis_or_none() as client:
            if client is None:
                logger.warning("Redis not available")
                return {
                    "status": "error",
                    "error": "Redis not available",
                    "key": "risk_bias",
                }

            # Write as plain float string per Redis schema
            # RiskManager.get_risk_bias() calls float() on this value
            await client.set("risk_bias", str(value))

            logger.info("Redis write: key=risk_bias, value=%s", value)

            return {
                "status": "success",
                "key": "risk_bias",
                "value": value,
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error("Redis write failed: %s", e)
        return {
            "status": "error",
            "error": f"Write failed: {str(e)}",
            "key": "risk_bias",
        }


async def write_sentiment(
    symbol: str,
    score: float,
    source: str | None = None,
    confidence: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write a sentiment score for a symbol to Redis.

    Convenience function for writing sentiment:* keys.
    The value is stored as a plain float string per Redis schema,
    as downstream consumers expect to call float() on the raw value.

    Args:
        symbol: Ticker symbol (e.g., "AAPL")
        score: Sentiment score (-1.0 to 1.0)
        source: Source of the sentiment (e.g., "news", "social") - logged only
        confidence: Confidence level (0.0 to 1.0) - logged only
        metadata: Additional metadata about the sentiment - logged only

    Returns:
        Dictionary containing the write result.

    Example:
        >>> result = await write_sentiment(
        ...     symbol="AAPL",
        ...     score=0.75,
        ...     source="news",
        ...     confidence=0.8
        ... )
        >>> result["status"]
        'success'
    """
    # Validate score range
    if not -1.0 <= score <= 1.0:
        return {
            "status": "error",
            "error": f"Sentiment score must be between -1.0 and 1.0, got {score}",
        }

    if not symbol:
        return {
            "status": "error",
            "error": "Symbol is required",
        }

    key = f"sentiment:{symbol.upper()}"

    if source or confidence:
        logger.info(
            "Writing sentiment: symbol=%s, score=%s, source=%s, confidence=%s",
            symbol.upper(), score, source, confidence
        )

    try:
        async with get_redis_or_none() as client:
            if client is None:
                logger.warning("Redis not available")
                return {
                    "status": "error",
                    "error": "Redis not available",
                    "key": key,
                }

            # Write as plain float string per Redis schema
            # Downstream consumers call float() on this value
            ttl = DEFAULT_TTL.get("sentiment")
            if ttl:
                await client.setex(key, ttl, str(score))
            else:
                await client.set(key, str(score))

            logger.info("Redis write: key=%s, value=%s, ttl=%s", key, score, ttl)

            return {
                "status": "success",
                "key": key,
                "value": score,
                "symbol": symbol.upper(),
                "ttl": ttl,
                "timestamp": datetime.now().isoformat(),
            }

    except Exception as e:
        logger.error("Redis write failed: %s", e)
        return {
            "status": "error",
            "error": f"Write failed: {str(e)}",
            "key": key,
        }


async def write_event(
    event_type: str,
    event_date: str,
    symbols: list[str] | None = None,
    impact_level: str = "medium",
    description: str | None = None,
) -> dict[str, Any]:
    """Write a market event to Redis.

    Args:
        event_type: Type of event (e.g., "FOMC", "NFP", "EARNINGS")
        event_date: Event date in YYYY-MM-DD format
        symbols: Affected symbols (if any)
        impact_level: Expected impact ("low", "medium", "high")
        description: Event description

    Returns:
        Dictionary containing the write result.
    """
    if not event_type:
        return {
            "status": "error",
            "error": "Event type is required",
        }

    return await write_redis(
        key=f"events:{event_date}",
        value={
            "event_type": event_type,
            "event_date": event_date,
            "symbols": symbols or [],
            "impact_level": impact_level,
            "description": description,
            "created_at": datetime.now().isoformat(),
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
        "'risk_bias', 'sentiment', or 'events' are permitted. Enforces strict key validation.",
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
        description="Update the risk bias value (0.0-1.0). Used by Risk Controller agent "
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
        description="Update sentiment score (-1.0 to 1.0) for a symbol. Used by Analyst agent "
        "to store analyzed sentiment from news and social sources.",
        execute=write_sentiment,
        required_permissions=["redis:sentiment:*"],
    )
