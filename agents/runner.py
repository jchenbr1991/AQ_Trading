# AQ Trading AI Agents - Runner Module
# This module is invoked by AgentDispatcher as a subprocess
"""Agent runner for subprocess execution.

This module is invoked by the AgentDispatcher to run agent tasks
in isolated subprocesses. It reads task input from stdin and
writes results to stdout as JSON.

Usage (invoked by dispatcher):
    python -m agents.runner --role researcher < task.json > result.json
"""

import argparse
import json
import logging
import sys
from typing import Any

# Configure logging to stderr to keep stdout clean for JSON output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def get_agent_for_role(role: str) -> Any:
    """Get the agent class for a given role.

    Args:
        role: Agent role name (researcher, analyst, risk_controller, ops)

    Returns:
        Agent instance for the role

    Raises:
        ValueError: If role is not recognized
    """
    from agents.prompts import (
        AnalystAgent,
        OpsAgent,
        ResearcherAgent,
        RiskControllerAgent,
    )

    agents = {
        "researcher": ResearcherAgent,
        "analyst": AnalystAgent,
        "risk_controller": RiskControllerAgent,
        "ops": OpsAgent,
    }

    if role not in agents:
        raise ValueError(f"Unknown agent role: {role}")

    return agents[role]()


def run_agent(role: str, task: str, context: dict[str, Any]) -> dict[str, Any]:
    """Run an agent task and return the result.

    Args:
        role: Agent role name
        task: Task description
        context: Additional context for the task

    Returns:
        Agent result as a dictionary
    """
    logger.info(f"Running agent: role={role}, task={task[:50]}...")

    try:
        agent = get_agent_for_role(role)
        result = agent.execute(task, context)
        logger.info(f"Agent {role} completed successfully")
        return result
    except Exception as e:
        logger.error(f"Agent {role} failed: {e}")
        return {
            "success": False,
            "error": str(e),
            "error_type": type(e).__name__,
        }


def main() -> None:
    """Main entry point for the agent runner."""
    parser = argparse.ArgumentParser(description="Run an AI agent task")
    parser.add_argument(
        "--role",
        required=True,
        choices=["researcher", "analyst", "risk_controller", "ops"],
        help="Agent role to run",
    )
    args = parser.parse_args()

    # Read task input from stdin
    try:
        input_data = json.load(sys.stdin)
        task = input_data.get("task", "")
        context = input_data.get("context", {})
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        result = {"success": False, "error": f"Invalid JSON input: {e}"}
        print(json.dumps(result))
        sys.exit(1)

    # Run the agent
    result = run_agent(args.role, task, context)

    # Output result as JSON to stdout
    print(json.dumps(result))


if __name__ == "__main__":
    main()
