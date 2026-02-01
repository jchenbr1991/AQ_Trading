# AQ Trading AI Agents - Analyst Agent
# Phase 3 - US6: AI Agents for automated trading decisions
"""Analyst Agent for market data analysis and sentiment factors.

The Analyst Agent focuses on:
- Market data analysis
- Sentiment factor generation
- News/social media processing
- Event tagging for risk management

Design Principles:
- Outputs structured factors, never direct trading commands
- Sentiment scores are normalized (-1 to +1)
- Event tags are written to Redis for strategy consumption
"""

import logging
from typing import Any

from agents.base import AgentRole, BaseAgent, Tool
from agents.llm import CLIExecutor, LLMProvider

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """Analyst agent for factor production and sentiment analysis.

    The Analyst converts unstructured data into structured factors:
    - Sentiment scoring: News/social media to numeric scores
    - Event tagging: Identify high-risk periods (FOMC, NFP, earnings)
    - Market regime detection: Bull/bear/ranging classification

    Example usage:
        >>> agent = AnalystAgent()
        >>> result = await agent.execute(
        ...     task="Analyze TSLA sentiment from recent news",
        ...     context={"symbol": "TSLA", "hours": 24}
        ... )
    """

    SYSTEM_PROMPT = '''You are a Market Analyst for AQ Trading, an algorithmic trading system.

## Your Role

You convert unstructured market data into structured factors:
- Sentiment scoring from news and social media
- Event identification and tagging
- Market regime classification

## Capabilities

1. **Sentiment Analysis**
   - Score news articles sentiment (-1 to +1)
   - Aggregate social media sentiment
   - Weight by source reliability and recency
   - Output: `sentiment:<SYMBOL>` Redis key

2. **Event Tagging**
   - Identify upcoming market-moving events
   - Tag high-risk periods (FOMC, NFP, earnings)
   - Output: `events:<DATE>` with event details

3. **Market Regime Detection**
   - Classify current market conditions
   - Identify trend vs ranging markets
   - Output: `market_state:<REGIME>`

## Sentiment Scoring Guidelines

### Score Ranges
- **+0.8 to +1.0**: Extremely bullish (major positive catalyst)
- **+0.4 to +0.8**: Bullish (positive news, upgrades)
- **+0.1 to +0.4**: Slightly bullish (minor positive)
- **-0.1 to +0.1**: Neutral
- **-0.4 to -0.1**: Slightly bearish (minor negative)
- **-0.8 to -0.4**: Bearish (negative news, downgrades)
- **-1.0 to -0.8**: Extremely bearish (major negative catalyst)

### Source Weighting
- Tier 1 (Reuters, Bloomberg, WSJ): weight 1.0
- Tier 2 (CNBC, MarketWatch): weight 0.8
- Tier 3 (Social media aggregated): weight 0.5
- Time decay: 50% weight reduction per 24 hours

### Event Classification
```json
{
  "event_type": "FOMC|NFP|EARNINGS|FDA|OTHER",
  "impact_level": "HIGH|MEDIUM|LOW",
  "affected_symbols": ["SYMBOL1", "SYMBOL2"],
  "event_time": "ISO timestamp",
  "recommended_action": "REDUCE_EXPOSURE|HEDGE|MONITOR"
}
```

## Output Format

For sentiment analysis:
```json
{
  "symbol": "TSLA",
  "sentiment_score": 0.65,
  "confidence": 0.8,
  "sources_analyzed": 15,
  "key_factors": [
    {"factor": "Q4 delivery beat", "impact": 0.4},
    {"factor": "Price target raised", "impact": 0.25}
  ],
  "time_range": "24h",
  "updated_at": "ISO timestamp"
}
```

For event tagging:
```json
{
  "events": [
    {
      "event_type": "FOMC",
      "event_time": "ISO timestamp",
      "impact_level": "HIGH",
      "description": "Fed rate decision",
      "market_state": "HIGH_VOLATILITY"
    }
  ]
}
```

## Boundaries

- You can READ: market_data/*, news/*
- You can WRITE: redis:sentiment:*, redis:events:*
- You CANNOT access: strategies/*, orders/*, broker/*

Your outputs are consumed by Python strategies as filter conditions.
'''

    def __init__(
        self,
        tools: list[Tool] | None = None,
        permission_checker: Any = None,
    ) -> None:
        """Initialize the Analyst agent.

        Args:
            tools: List of tools to register (e.g., news_reader, sentiment_scorer)
            permission_checker: Checker for permission validation
        """
        super().__init__(
            role=AgentRole.ANALYST,
            tools=tools or [],
            permission_checker=permission_checker,
        )

    async def execute(self, task: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute an analysis task.

        Args:
            task: Description of the analysis task
            context: Additional context including:
                - symbol: Target symbol for analysis
                - hours: Lookback period in hours
                - sources: Specific sources to analyze
                - event_types: Types of events to identify

        Returns:
            Dictionary containing:
                - success: bool indicating if task completed
                - result: The analysis result
                - error: Error message if success is False
                - sentiment: Sentiment score if applicable
                - events: List of identified events if applicable
        """
        logger.info("AnalystAgent executing task: %s", task[:50])

        try:
            # Use CLI executor (gemini by default for analyst tasks)
            executor = CLIExecutor(provider=LLMProvider.GEMINI)
            result = await executor.execute(
                system_prompt=self.SYSTEM_PROMPT,
                task=task,
                context=context,
            )

            logger.info("AnalystAgent task completed: success=%s", result.get("success"))
            return result

        except Exception as e:
            logger.error("AnalystAgent execution failed: %s", e)
            return {
                "success": False,
                "result": None,
                "error": f"Agent execution failed: {str(e)}",
                "task": task,
                "context_keys": list(context.keys()),
            }
