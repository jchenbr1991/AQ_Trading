"""
Redis key schema for agent outputs and caching.

Key naming convention:
- Use colons (:) as namespace separators
- Use lowercase with underscores for multi-word keys
- Use {placeholder} syntax for dynamic values

Key patterns:
- risk_bias          - Risk bias multiplier (float)
- sentiment:{symbol} - Sentiment score per symbol (float, -1.0 to 1.0)
- agent_result:{id}  - Cached agent result (JSON)

Note: Keys follow the spec convention from research.md where agents write
to plain keys (risk_bias, sentiment:*) and trading path reads them directly.
"""


class AgentKeys:
    """Redis key patterns for agent-related data."""

    # Risk bias multiplier applied to position sizing
    # Value: float (e.g., 0.8 for 20% reduction, 1.2 for 20% increase)
    # TTL: None (persistent until updated)
    RISK_BIAS = "risk_bias"

    # Sentiment score per symbol
    # Value: float (-1.0 = very bearish, 0.0 = neutral, 1.0 = very bullish)
    # TTL: Configurable, typically 1 hour
    SENTIMENT_PREFIX = "sentiment"

    # Cached agent result by ID
    # Value: JSON serialized AgentResult
    # TTL: Configurable, typically 24 hours
    RESULT_PREFIX = "agent_result"

    @classmethod
    def sentiment(cls, symbol: str) -> str:
        """Get the Redis key for a symbol's sentiment score.

        Args:
            symbol: The trading symbol (e.g., 'AAPL', 'SPY')

        Returns:
            Redis key string (e.g., 'agent:sentiment:AAPL')
        """
        return f"{cls.SENTIMENT_PREFIX}:{symbol.upper()}"

    @classmethod
    def result(cls, result_id: str) -> str:
        """Get the Redis key for a cached agent result.

        Args:
            result_id: The UUID of the agent result

        Returns:
            Redis key string (e.g., 'agent:result:550e8400-e29b-41d4-a716-446655440000')
        """
        return f"{cls.RESULT_PREFIX}:{result_id}"


# Default TTL values (in seconds)
class AgentKeyTTL:
    """Default TTL values for agent Redis keys."""

    # Sentiment scores expire after 1 hour
    SENTIMENT = 3600

    # Cached results expire after 24 hours
    RESULT = 86400

    # Risk bias has no TTL (persistent)
    RISK_BIAS = None
