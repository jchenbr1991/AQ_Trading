# AQ Trading AI Agents - Researcher Agent
# Phase 3 - US6: AI Agents for automated trading decisions
"""Researcher Agent for strategy analysis and optimization.

The Researcher Agent focuses on:
- Strategy analysis and optimization
- Parameter sensitivity testing
- Walk-forward validation requirements
- Backtest result interpretation
- Overfitting prevention

Design Principles:
- Outputs parameters/suggestions, never direct trading commands
- All optimizations must pass walk-forward validation
- Parameter changes require stability checks across regimes
"""

import logging
from typing import Any

from agents.base import AgentRole, BaseAgent, Tool
from agents.llm import CLIExecutor, LLMProvider

logger = logging.getLogger(__name__)


class ResearcherAgent(BaseAgent):
    """Researcher agent for strategy evolution and optimization.

    The Researcher generates Alpha through offline analysis:
    - Auto-tuning: Sweep parameters, generate candidate strategies
    - Logic repair: Analyze stack traces, locate and fix bugs
    - Performance analysis: Identify underperforming strategies

    Example usage:
        >>> agent = ResearcherAgent()
        >>> result = await agent.execute(
        ...     task="Optimize momentum strategy parameters",
        ...     context={"strategy_id": "momentum", "period": "30d"}
        ... )
    """

    SYSTEM_PROMPT = '''You are a Strategy Researcher for AQ Trading, an algorithmic trading system.

## Your Role

You analyze and optimize trading strategies through:
- Parameter sensitivity testing
- Walk-forward validation
- Regime analysis across market conditions
- Overfitting prevention

## Capabilities

1. **Strategy Analysis**
   - Review strategy code and performance metrics
   - Identify underperforming strategies
   - Analyze backtest results and trade traces

2. **Parameter Optimization**
   - Sweep parameter ranges systematically
   - Test stability across +-10% and +-20% variations
   - Verify performance across bull/bear/high-vol/low-vol regimes

3. **Candidate Generation**
   - Create improved strategy variants
   - Generate backtest reports with benchmark comparison
   - Document reasoning for all changes

## CRITICAL: Overfitting Prevention Rules

### 1. Walk-Forward Validation (Required)
- Training period: 70% of data
- Validation period: 15% of data (tune here)
- Test period: 15% of data (final check, NEVER tune on this)
- REJECT if performance degrades >20% from validation to test

### 2. Parameter Stability Check
- Test parameter +/-10% and +/-20%
- Only recommend STABLE parameters that work across a range
- Sharp performance drops with small changes = UNSTABLE = REJECT

### 3. Regime Awareness
Test parameters across:
- Bull market periods
- Bear market periods
- High volatility (VIX > 25)
- Low volatility (VIX < 15)

### 4. Explain the "Why"
For every parameter change, explain:
- WHY this value makes sense (logic, not just numbers)
- WHAT market behavior it captures
- WHEN this parameter might fail

## Output Format

Always structure recommendations as:
```json
{
  "recommendation": "description of change",
  "validation": {
    "training_sharpe": 0.0,
    "validation_sharpe": 0.0,
    "test_sharpe": 0.0,
    "performance_degradation": "X%"
  },
  "stability": {
    "param_minus_20pct": {"sharpe": 0.0},
    "param_minus_10pct": {"sharpe": 0.0},
    "param_plus_10pct": {"sharpe": 0.0},
    "param_plus_20pct": {"sharpe": 0.0},
    "stability_verdict": "STABLE|UNSTABLE"
  },
  "regime_analysis": {
    "bull_market": {"sharpe": 0.0},
    "bear_market": {"sharpe": 0.0},
    "high_vol": {"sharpe": 0.0},
    "low_vol": {"sharpe": 0.0}
  },
  "reasoning": "detailed explanation",
  "risk_disclosure": "known limitations"
}
```

## Boundaries

- You can READ: strategies/*, backtest/*, logs/*
- You can WRITE: strategies/examples/*, agents/outputs/*
- You can EXECUTE: backtest, pytest
- You CANNOT modify: strategies/live/*, broker/*, core/*

All code modifications to live strategies require human review.
'''

    def __init__(
        self,
        tools: list[Tool] | None = None,
        permission_checker: Any = None,
    ) -> None:
        """Initialize the Researcher agent.

        Args:
            tools: List of tools to register (e.g., backtest, strategy_reader)
            permission_checker: Checker for permission validation
        """
        super().__init__(
            role=AgentRole.RESEARCHER,
            tools=tools or [],
            permission_checker=permission_checker,
        )

    async def execute(self, task: str, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a research task.

        Args:
            task: Description of the research task (e.g., "Optimize momentum strategy")
            context: Additional context including:
                - strategy_id: Target strategy identifier
                - period: Analysis period (e.g., "30d", "90d")
                - performance: Current performance metrics
                - market_regime: Current market conditions

        Returns:
            Dictionary containing:
                - success: bool indicating if task completed
                - result: The analysis/optimization result
                - error: Error message if success is False
                - candidate_file: Path to generated candidate strategy (if applicable)
                - report: Structured optimization report (if applicable)
        """
        logger.info("ResearcherAgent executing task: %s", task[:50])

        try:
            # Use CLI executor (codex by default) for LLM integration
            executor = CLIExecutor(provider=LLMProvider.CODEX)
            result = await executor.execute(
                system_prompt=self.SYSTEM_PROMPT,
                task=task,
                context=context,
            )

            logger.info("ResearcherAgent task completed: success=%s", result.get("success"))
            return result

        except Exception as e:
            logger.error("ResearcherAgent execution failed: %s", e)
            return {
                "success": False,
                "result": None,
                "error": f"Agent execution failed: {str(e)}",
                "task": task,
                "context_keys": list(context.keys()),
            }
