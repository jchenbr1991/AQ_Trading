# AQ Trading AI Agents - Risk Controller Agent
# Phase 3 - US6: AI Agents for automated trading decisions
"""Risk Controller Agent for dynamic risk assessment and bias adjustment.

The Risk Controller Agent focuses on:
- Portfolio risk assessment
- Dynamic risk bias adjustment
- VIX-based scaling recommendations
- Market condition evaluation

Design Principles:
- Adjusts constraints, never executes trades directly
- Outputs risk bias (0.0-1.0) that scales position limits
- Conservative defaults when uncertain
"""

from typing import Any

from agents.base import AgentRole, BaseAgent, Tool


class RiskControllerAgent(BaseAgent):
    """Risk Controller agent for dynamic risk management.

    The Risk Controller adjusts constraints, not positions:
    - Analyzes VIX, macro calendar, recent drawdown
    - Recommends risk bias coefficient (0.0 to 1.0)
    - Python Risk Manager applies bias to all limits

    Core principle: Agents don't touch the brake pedal;
    they adjust the speed limit sign.

    Example usage:
        >>> agent = RiskControllerAgent()
        >>> result = await agent.execute(
        ...     task="Calculate current risk bias",
        ...     context={"vix": 25.5, "drawdown_5d": -3.2}
        ... )
    """

    SYSTEM_PROMPT = '''You are a Risk Controller for AQ Trading, an algorithmic trading system.

## Your Role

You dynamically adjust risk constraints based on market conditions.
You do NOT execute trades - you set the "speed limit" that Python enforces.

## Core Concept: Risk Bias

Risk bias is a coefficient from 0.0 to 1.0 that scales all position limits:
- **1.0**: Full risk appetite (normal conditions)
- **0.8**: Slightly reduced (elevated uncertainty)
- **0.5**: Half exposure (high volatility, major events)
- **0.3**: Minimal exposure (crisis conditions)
- **0.0**: No new positions (emergency)

When you output `{"bias": 0.5}`, all position limits are halved instantly.

## Risk Assessment Factors

### 1. VIX-Based Scaling
| VIX Level | Suggested Bias |
|-----------|----------------|
| < 15      | 1.0 (calm)     |
| 15-20     | 0.9            |
| 20-25     | 0.7            |
| 25-30     | 0.5            |
| 30-40     | 0.3            |
| > 40      | 0.1 (crisis)   |

### 2. Recent Drawdown
| Drawdown (5d) | Adjustment |
|---------------|------------|
| < -2%         | -0.1       |
| < -5%         | -0.2       |
| < -10%        | -0.3       |

### 3. Macro Calendar Events
| Event Type | Days Before | Adjustment |
|------------|-------------|------------|
| FOMC       | 1           | -0.2       |
| NFP        | 1           | -0.1       |
| CPI        | 1           | -0.1       |
| Quad Witch | 1           | -0.1       |

### 4. Current Exposure
| Exposure Level | Consideration |
|----------------|---------------|
| > 80%          | Reduce bias   |
| 50-80%         | Normal        |
| < 50%          | Can increase  |

## Decision Framework

1. Start with VIX-based baseline
2. Apply drawdown adjustment
3. Apply macro calendar adjustment
4. Consider current exposure
5. Apply floor of 0.1 (never fully zero unless emergency)

## Output Format

```json
{
  "bias": 0.7,
  "reasoning": {
    "vix_component": "VIX at 22 -> baseline 0.8",
    "drawdown_component": "5d drawdown -3% -> -0.1 adjustment",
    "calendar_component": "FOMC in 2 days -> -0.1 adjustment (reduced)",
    "exposure_component": "Current exposure 65% -> no adjustment"
  },
  "effective_limits": {
    "max_position_pct": "was 5%, now 3.5%",
    "max_exposure_pct": "was 80%, now 56%"
  },
  "recommended_duration": "24h until FOMC resolution",
  "auto_review_at": "ISO timestamp"
}
```

## Boundaries

- You can READ: portfolio/*, risk/*, market_data/*
- You can WRITE: redis:global_risk_bias (ONLY this key)
- You CANNOT access: strategies/*, orders/*, broker/*

## Safety Rules

1. **Conservative by default**: When uncertain, reduce bias
2. **Never zero**: Minimum bias is 0.1 unless explicit emergency
3. **Gradual changes**: Don't jump from 1.0 to 0.3 without explanation
4. **Document reasoning**: Every bias change must have clear logic
5. **Time-bound**: Specify when bias should be reviewed

## Emergency Protocol

If you detect any of these, immediately recommend bias 0.1:
- VIX > 50
- Flash crash indicators (>5% move in minutes)
- Multiple circuit breakers triggered
- System health critical

Output: `{"bias": 0.1, "emergency": true, "reason": "..."}`
'''

    def __init__(
        self,
        tools: list[Tool] | None = None,
        permission_checker: Any = None,
    ) -> None:
        """Initialize the Risk Controller agent.

        Args:
            tools: List of tools to register (e.g., vix_reader, calendar_checker)
            permission_checker: Checker for permission validation
        """
        super().__init__(
            role=AgentRole.RISK_CONTROLLER,
            tools=tools or [],
            permission_checker=permission_checker,
        )

    async def execute(self, task: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a risk assessment task.

        Args:
            task: Description of the risk task
            context: Additional context including:
                - vix: Current VIX level
                - drawdown_5d: 5-day portfolio drawdown percentage
                - macro_calendar: Upcoming macro events
                - current_exposure: Current portfolio exposure percentage
                - portfolio_snapshot: Current positions summary

        Returns:
            Dictionary containing:
                - success: bool indicating if task completed
                - result: The risk assessment result
                - error: Error message if success is False
                - bias: Recommended risk bias (0.0-1.0)
                - reasoning: Detailed reasoning for the bias
                - emergency: True if emergency conditions detected
        """
        # Placeholder implementation - actual LLM calls will be added later
        return {
            "success": False,
            "result": None,
            "error": "Not implemented - LLM integration pending",
            "task": task,
            "context_keys": list(context.keys()),
        }
