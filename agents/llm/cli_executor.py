# AQ Trading AI Agents - CLI LLM Executor
"""CLI-based LLM executor for AI agents.

This module provides LLM execution via CLI tools (codex, gemini).
Agents can use this to get intelligent responses without direct API integration.

Usage:
    executor = CLIExecutor(provider="codex")
    result = await executor.execute(
        system_prompt="You are a trading analyst...",
        task="Analyze AAPL price action",
        context={"symbol": "AAPL"}
    )
"""

import asyncio
import json
import logging
import shutil
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Available LLM CLI providers."""

    CODEX = "codex"
    GEMINI = "gemini"


class CLIExecutorError(Exception):
    """Raised when CLI execution fails."""

    pass


class CLIExecutor:
    """Execute LLM calls via CLI tools.

    This executor shells out to codex or gemini CLI to get LLM responses.
    It's a bridge between the agent system and external LLM providers.
    """

    # Timeout for CLI execution (seconds)
    DEFAULT_TIMEOUT = 300

    def __init__(
        self,
        provider: LLMProvider | str = LLMProvider.CODEX,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the CLI executor.

        Args:
            provider: LLM provider to use (codex or gemini)
            timeout: Execution timeout in seconds
        """
        self.provider = LLMProvider(provider) if isinstance(provider, str) else provider
        self.timeout = timeout
        self._validate_cli_available()

    def _validate_cli_available(self) -> None:
        """Check if the CLI tool is available on the system."""
        cli_name = self.provider.value
        if shutil.which(cli_name) is None:
            logger.warning(
                "%s CLI not found in PATH. Agent execution will fail.",
                cli_name,
            )

    def _build_prompt(
        self,
        system_prompt: str,
        task: str,
        context: dict[str, Any],
    ) -> str:
        """Build the full prompt for the LLM.

        Args:
            system_prompt: Agent's system prompt defining its role
            task: The specific task to perform
            context: Additional context for the task

        Returns:
            Formatted prompt string
        """
        context_str = json.dumps(context, indent=2) if context else "{}"

        prompt = f"""## System Instructions

{system_prompt}

## Task

{task}

## Context

```json
{context_str}
```

## Instructions

Analyze the task and context above. Provide your response as a JSON object with:
- "success": true/false
- "result": your analysis or recommendations
- "reasoning": explanation of your approach
- "confidence": 0.0-1.0 confidence score

Respond ONLY with valid JSON, no additional text.
"""
        return prompt

    def _build_command(self, prompt: str) -> list[str]:
        """Build the CLI command to execute.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            Command list for subprocess execution
        """
        if self.provider == LLMProvider.CODEX:
            # Codex uses 'codex review "prompt"' format
            return ["codex", "review", prompt]
        elif self.provider == LLMProvider.GEMINI:
            # Gemini uses 'gemini -p "prompt"' format
            return ["gemini", "-p", prompt]
        else:
            raise CLIExecutorError(f"Unknown provider: {self.provider}")

    async def execute(
        self,
        system_prompt: str,
        task: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute an LLM call via CLI.

        Args:
            system_prompt: Agent's system prompt
            task: Task description
            context: Additional context

        Returns:
            Dictionary with execution result:
            - success: Whether execution succeeded
            - result: LLM response or analysis
            - error: Error message if failed
            - raw_output: Raw CLI output
        """
        context = context or {}

        # Build prompt and command
        prompt = self._build_prompt(system_prompt, task, context)
        command = self._build_command(prompt)

        logger.info("Executing %s CLI for task: %s", self.provider.value, task[:50])

        try:
            # Execute CLI command
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout,
            )

            stdout_str = stdout.decode("utf-8").strip()
            stderr_str = stderr.decode("utf-8").strip()

            if process.returncode != 0:
                logger.error(
                    "%s CLI failed with code %d: %s",
                    self.provider.value,
                    process.returncode,
                    stderr_str,
                )
                return {
                    "success": False,
                    "result": None,
                    "error": f"CLI execution failed: {stderr_str}",
                    "raw_output": stdout_str,
                }

            # Try to parse JSON from output
            result = self._parse_response(stdout_str)
            return result

        except asyncio.TimeoutError:
            logger.error("%s CLI timed out after %ds", self.provider.value, self.timeout)
            # Terminate the subprocess to prevent resource leaks
            try:
                process.kill()
                await process.wait()
            except Exception as kill_error:
                logger.warning("Failed to kill timed-out process: %s", kill_error)
            return {
                "success": False,
                "result": None,
                "error": f"CLI execution timed out after {self.timeout}s",
                "raw_output": None,
            }
        except FileNotFoundError:
            logger.error("%s CLI not found", self.provider.value)
            return {
                "success": False,
                "result": None,
                "error": f"{self.provider.value} CLI not found in PATH",
                "raw_output": None,
            }
        except Exception as e:
            logger.error("Unexpected error executing %s CLI: %s", self.provider.value, e)
            return {
                "success": False,
                "result": None,
                "error": f"Unexpected error: {str(e)}",
                "raw_output": None,
            }

    def _parse_response(self, output: str) -> dict[str, Any]:
        """Parse the CLI output into a structured response.

        Args:
            output: Raw CLI output string

        Returns:
            Parsed response dictionary
        """
        # Try to find JSON in the output
        try:
            # Look for JSON block in output
            json_start = output.find("{")
            json_end = output.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = output[json_start:json_end]
                parsed = json.loads(json_str)

                # Ensure required fields
                return {
                    "success": parsed.get("success", True),
                    "result": parsed.get("result", parsed),
                    "error": parsed.get("error"),
                    "reasoning": parsed.get("reasoning"),
                    "confidence": parsed.get("confidence", 0.5),
                    "raw_output": output,
                }
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse JSON from CLI output: %s", e)
            return {
                "success": False,
                "result": None,
                "error": f"Failed to parse JSON response: {str(e)}",
                "reasoning": None,
                "confidence": 0.0,
                "raw_output": output,
            }

        # No JSON found in output - return as parsing failure
        logger.warning("No JSON found in CLI output")
        return {
            "success": False,
            "result": None,
            "error": "No valid JSON found in CLI response",
            "reasoning": None,
            "confidence": 0.0,
            "raw_output": output,
        }


# Default executor instance
_default_executor: CLIExecutor | None = None


def get_executor(provider: LLMProvider | str = LLMProvider.CODEX) -> CLIExecutor:
    """Get or create a CLI executor instance.

    Args:
        provider: LLM provider to use

    Returns:
        CLIExecutor instance
    """
    global _default_executor
    if _default_executor is None or _default_executor.provider != LLMProvider(provider):
        _default_executor = CLIExecutor(provider=provider)
    return _default_executor
