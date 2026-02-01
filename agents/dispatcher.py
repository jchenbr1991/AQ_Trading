"""Agent Dispatcher for managing AI agent lifecycle.

This module provides the AgentDispatcher class for spawning, monitoring,
and terminating AI agent subprocesses. Agents run as sidecars and NEVER
in the trading hot path.
"""

import json
import logging
import subprocess
import sys
from typing import Any, Protocol

try:
    # When running from backend directory
    from src.models.agent_result import AgentResult, AgentRole
except ImportError:
    # When running from project root
    from backend.src.models.agent_result import AgentResult, AgentRole

logger = logging.getLogger(__name__)

# Default timeout for agent execution (5 minutes)
DEFAULT_TIMEOUT_SECONDS = 300


class SessionFactory(Protocol):
    """Protocol for database session factory."""

    def __call__(self) -> Any: ...


class PermissionChecker(Protocol):
    """Protocol for checking agent permissions."""

    def can_execute(self, role: AgentRole, task: str, context: dict[str, Any]) -> bool: ...


class AgentDispatcher:
    """Dispatcher for managing AI agent lifecycle.

    Responsibilities:
    - Spawn agent subprocesses based on role
    - Monitor agent execution
    - Capture results to AgentResult table
    - Graceful degradation when agents fail
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        permission_checker: PermissionChecker | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        """Initialize the dispatcher.

        Args:
            session_factory: Factory for creating database sessions
            permission_checker: Optional checker for agent permissions
            timeout_seconds: Timeout for agent execution in seconds
        """
        self.session_factory = session_factory
        self.permission_checker = permission_checker
        self.timeout_seconds = timeout_seconds

    def dispatch(
        self,
        role: AgentRole,
        task: str,
        context: dict[str, Any],
    ) -> AgentResult:
        """Dispatch a task to an agent.

        This is the main entry point for running agent tasks. It:
        1. Checks permissions (if checker provided)
        2. Creates an AgentResult record
        3. Spawns the agent subprocess
        4. Waits for completion and captures output
        5. Updates the result record

        Args:
            role: The agent role to dispatch to
            task: Description of the task to perform
            context: Additional context data for the agent

        Returns:
            AgentResult with the outcome of the agent execution
        """
        # Permission check
        if self.permission_checker is not None:
            if not self.permission_checker.can_execute(role, task, context):
                logger.warning(f"Permission denied for {role.value} agent: {task}")
                return self._create_error_result(
                    role, task, context, "Permission denied"
                )

        # Create result record before spawning
        result_record = AgentResult(
            role=role,
            task=task,
            context=context,
            success=False,
        )

        try:
            # Spawn agent subprocess
            process = self._spawn_agent(role, task, context)

            # Wait for completion and capture output
            output = self._wait_and_capture(process, result_record)

            # Update result with success
            result_record.complete(result=output)
            logger.info(f"Agent {role.value} completed task: {task}")

        except subprocess.TimeoutExpired as e:
            error_msg = f"Agent timeout after {self.timeout_seconds}s"
            logger.error(f"Agent {role.value} timed out: {task}")
            result_record.complete(error=error_msg)
            # Try to terminate the process
            try:
                if e.args and hasattr(e.args[0], 'kill'):
                    e.args[0].kill()
            except Exception:
                pass

        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error: {str(e)}"
            logger.error(f"Agent {role.value} subprocess error: {error_msg}")
            result_record.complete(error=error_msg)

        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON output: {str(e)}"
            logger.error(f"Agent {role.value} output parse error: {error_msg}")
            result_record.complete(error=error_msg)

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.exception(f"Agent {role.value} failed unexpectedly")
            result_record.complete(error=error_msg)

        # Persist the result
        self._persist_result(result_record)

        return result_record

    def _spawn_agent(
        self,
        role: AgentRole,
        task: str,
        context: dict[str, Any],
    ) -> subprocess.Popen:
        """Spawn an agent subprocess.

        Args:
            role: The agent role
            task: The task description
            context: Context data for the agent

        Returns:
            The subprocess.Popen object
        """
        # Prepare agent input as JSON
        agent_input = json.dumps({
            "role": role.value,
            "task": task,
            "context": context,
        })

        # Build command - use Python to run the agent runner
        # The actual agent implementation is in agents/runner.py
        cmd = [
            sys.executable,
            "-m",
            "agents.runner",
            "--role",
            role.value,
        ]

        logger.debug(f"Spawning agent: {' '.join(cmd)}")

        # Spawn subprocess with stdin pipe for input
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Write input to stdin
        if process.stdin:
            process.stdin.write(agent_input)
            process.stdin.close()

        return process

    def _wait_and_capture(
        self,
        process: subprocess.Popen,
        result_record: AgentResult,
    ) -> dict[str, Any]:
        """Wait for agent completion and capture output.

        Args:
            process: The subprocess to wait for
            result_record: The result record to update

        Returns:
            The parsed output dictionary

        Raises:
            subprocess.TimeoutExpired: If the agent times out
            subprocess.SubprocessError: If the agent fails
            json.JSONDecodeError: If output is not valid JSON
        """
        try:
            stdout, stderr = process.communicate(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()  # Clean up
            raise

        # Check return code
        if process.returncode != 0:
            error_detail = stderr.strip() if stderr else f"Exit code {process.returncode}"
            raise subprocess.SubprocessError(f"Agent failed: {error_detail}")

        # Parse JSON output
        if not stdout.strip():
            return {"output": None, "message": "No output"}

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError as e:
            # Re-raise with context so caller can mark as failure
            raise json.JSONDecodeError(
                f"Agent output is not valid JSON: {stdout[:200]}",
                stdout,
                e.pos,
            ) from e

        return output

    def _persist_result(self, result_record: AgentResult) -> None:
        """Persist the agent result to the database.

        Args:
            result_record: The result to persist
        """
        try:
            session = self.session_factory()
            session.add(result_record)
            session.commit()
        except Exception as e:
            logger.error(f"Failed to persist agent result: {e}")
            # Don't re-raise - graceful degradation

    def _create_error_result(
        self,
        role: AgentRole,
        task: str,
        context: dict[str, Any],
        error: str,
    ) -> AgentResult:
        """Create an error result without spawning an agent.

        Args:
            role: The agent role
            task: The task description
            context: The context data
            error: The error message

        Returns:
            An AgentResult with the error
        """
        result = AgentResult(
            role=role,
            task=task,
            context=context,
            success=False,
        )
        result.complete(error=error)
        self._persist_result(result)
        return result
