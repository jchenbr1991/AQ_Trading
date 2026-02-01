"""Tests for AgentDispatcher."""

import json
import subprocess
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import sys
import os

# Add backend to path for tests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.models.agent_result import AgentResult, AgentRole
from agents.dispatcher import AgentDispatcher, DEFAULT_TIMEOUT_SECONDS


class TestAgentDispatcherInit:
    """Tests for AgentDispatcher initialization."""

    def test_init_with_session_factory(self):
        """Dispatcher initializes with session factory."""
        session_factory = MagicMock()
        dispatcher = AgentDispatcher(session_factory)

        assert dispatcher.session_factory is session_factory
        assert dispatcher.permission_checker is None
        assert dispatcher.timeout_seconds == DEFAULT_TIMEOUT_SECONDS

    def test_init_with_permission_checker(self):
        """Dispatcher initializes with permission checker."""
        session_factory = MagicMock()
        permission_checker = MagicMock()
        dispatcher = AgentDispatcher(session_factory, permission_checker)

        assert dispatcher.permission_checker is permission_checker

    def test_init_with_custom_timeout(self):
        """Dispatcher accepts custom timeout."""
        session_factory = MagicMock()
        dispatcher = AgentDispatcher(session_factory, timeout_seconds=60)

        assert dispatcher.timeout_seconds == 60


class TestAgentDispatcherDispatch:
    """Tests for AgentDispatcher.dispatch method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock session."""
        session = MagicMock()
        return session

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Create a mock session factory."""
        return MagicMock(return_value=mock_session)

    @pytest.fixture
    def dispatcher(self, mock_session_factory):
        """Create a dispatcher with mocked dependencies."""
        return AgentDispatcher(mock_session_factory, timeout_seconds=10)

    def test_dispatch_permission_denied(self, mock_session_factory):
        """Dispatch returns error when permission denied."""
        permission_checker = MagicMock()
        permission_checker.can_execute.return_value = False

        dispatcher = AgentDispatcher(mock_session_factory, permission_checker)
        result = dispatcher.dispatch(
            AgentRole.RESEARCHER,
            "analyze market",
            {"symbol": "AAPL"},
        )

        assert result.success is False
        assert result.error == "Permission denied"
        permission_checker.can_execute.assert_called_once_with(
            AgentRole.RESEARCHER, "analyze market", {"symbol": "AAPL"}
        )

    @patch("agents.dispatcher.subprocess.Popen")
    def test_dispatch_success(self, mock_popen, dispatcher, mock_session):
        """Dispatch returns success when agent completes."""
        # Mock successful subprocess
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            json.dumps({"analysis": "bullish"}),
            "",
        )
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        result = dispatcher.dispatch(
            AgentRole.ANALYST,
            "analyze AAPL",
            {"symbol": "AAPL"},
        )

        assert result.success is True
        assert result.result == {"analysis": "bullish"}
        assert result.error is None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("agents.dispatcher.subprocess.Popen")
    def test_dispatch_agent_failure(self, mock_popen, dispatcher, mock_session):
        """Dispatch handles agent failure gracefully."""
        # Mock failed subprocess
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "Agent crashed")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        result = dispatcher.dispatch(
            AgentRole.RISK_CONTROLLER,
            "check risk",
            {},
        )

        assert result.success is False
        assert "Agent failed" in result.error
        assert "Agent crashed" in result.error
        # Result should still be persisted
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @patch("agents.dispatcher.subprocess.Popen")
    def test_dispatch_timeout(self, mock_popen, dispatcher, mock_session):
        """Dispatch handles timeout gracefully."""
        # Mock timeout
        mock_process = MagicMock()
        mock_process.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="test", timeout=10
        )
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        result = dispatcher.dispatch(
            AgentRole.OPS,
            "deploy",
            {},
        )

        assert result.success is False
        assert "timeout" in result.error.lower()
        mock_process.kill.assert_called_once()

    @patch("agents.dispatcher.subprocess.Popen")
    def test_dispatch_invalid_json_output(self, mock_popen, dispatcher, mock_session):
        """Dispatch handles invalid JSON output."""
        # Mock process with non-JSON output
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("not valid json", "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        result = dispatcher.dispatch(
            AgentRole.RESEARCHER,
            "research",
            {},
        )

        # Should still succeed with raw output captured
        assert result.success is True
        assert result.result == {"raw_output": "not valid json"}

    @patch("agents.dispatcher.subprocess.Popen")
    def test_dispatch_empty_output(self, mock_popen, dispatcher, mock_session):
        """Dispatch handles empty output."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("", "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        result = dispatcher.dispatch(
            AgentRole.ANALYST,
            "analyze",
            {},
        )

        assert result.success is True
        assert result.result == {"output": None, "message": "No output"}

    @patch("agents.dispatcher.subprocess.Popen")
    def test_dispatch_persists_result_on_db_error(self, mock_popen, mock_session_factory):
        """Dispatch degrades gracefully on DB errors."""
        # Make session commit fail
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("DB connection lost")
        mock_session_factory.return_value = mock_session

        dispatcher = AgentDispatcher(mock_session_factory)

        # Mock successful subprocess
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ('{"ok": true}', "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        # Should not raise, graceful degradation
        result = dispatcher.dispatch(
            AgentRole.RESEARCHER,
            "test",
            {},
        )

        # Result is still returned even if DB fails
        assert result.success is True


class TestAgentDispatcherSpawnAgent:
    """Tests for AgentDispatcher._spawn_agent method."""

    @pytest.fixture
    def dispatcher(self):
        """Create a dispatcher."""
        return AgentDispatcher(MagicMock())

    @patch("agents.dispatcher.subprocess.Popen")
    def test_spawn_agent_command(self, mock_popen, dispatcher):
        """Spawn agent uses correct command."""
        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        dispatcher._spawn_agent(
            AgentRole.ANALYST,
            "analyze market",
            {"symbol": "AAPL"},
        )

        # Check the command includes the role
        call_args = mock_popen.call_args
        cmd = call_args[0][0]
        assert "-m" in cmd
        assert "agents.runner" in cmd
        assert "--role" in cmd
        assert "analyst" in cmd

    @patch("agents.dispatcher.subprocess.Popen")
    def test_spawn_agent_input_json(self, mock_popen, dispatcher):
        """Spawn agent sends JSON input to stdin."""
        mock_process = MagicMock()
        mock_stdin = MagicMock()
        mock_process.stdin = mock_stdin
        mock_popen.return_value = mock_process

        dispatcher._spawn_agent(
            AgentRole.RESEARCHER,
            "research TSLA",
            {"symbol": "TSLA", "depth": 5},
        )

        # Check stdin received JSON
        written_data = mock_stdin.write.call_args[0][0]
        parsed = json.loads(written_data)
        assert parsed["role"] == "researcher"
        assert parsed["task"] == "research TSLA"
        assert parsed["context"] == {"symbol": "TSLA", "depth": 5}
        mock_stdin.close.assert_called_once()


class TestAgentDispatcherWaitAndCapture:
    """Tests for AgentDispatcher._wait_and_capture method."""

    @pytest.fixture
    def dispatcher(self):
        """Create a dispatcher."""
        return AgentDispatcher(MagicMock(), timeout_seconds=5)

    def test_wait_and_capture_success(self, dispatcher):
        """Wait and capture parses JSON output."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            '{"result": "success", "data": [1, 2, 3]}',
            "",
        )

        result_record = AgentResult(
            role=AgentRole.ANALYST,
            task="test",
            context={},
        )

        output = dispatcher._wait_and_capture(mock_process, result_record)

        assert output == {"result": "success", "data": [1, 2, 3]}
        mock_process.communicate.assert_called_once_with(timeout=5)

    def test_wait_and_capture_timeout(self, dispatcher):
        """Wait and capture raises on timeout."""
        mock_process = MagicMock()
        mock_process.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="test", timeout=5
        )

        result_record = AgentResult(
            role=AgentRole.ANALYST,
            task="test",
            context={},
        )

        with pytest.raises(subprocess.TimeoutExpired):
            dispatcher._wait_and_capture(mock_process, result_record)

        mock_process.kill.assert_called_once()

    def test_wait_and_capture_failure(self, dispatcher):
        """Wait and capture raises on non-zero exit."""
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = ("", "Error: something went wrong")

        result_record = AgentResult(
            role=AgentRole.ANALYST,
            task="test",
            context={},
        )

        with pytest.raises(subprocess.SubprocessError) as exc_info:
            dispatcher._wait_and_capture(mock_process, result_record)

        assert "something went wrong" in str(exc_info.value)


class TestAgentRoleRouting:
    """Tests for routing tasks to correct agent roles."""

    @pytest.fixture
    def dispatcher(self):
        """Create a dispatcher."""
        return AgentDispatcher(MagicMock())

    @patch("agents.dispatcher.subprocess.Popen")
    def test_researcher_role(self, mock_popen, dispatcher):
        """Researcher role is correctly passed to subprocess."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("{}", "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        dispatcher.dispatch(AgentRole.RESEARCHER, "task", {})

        cmd = mock_popen.call_args[0][0]
        assert "researcher" in cmd

    @patch("agents.dispatcher.subprocess.Popen")
    def test_analyst_role(self, mock_popen, dispatcher):
        """Analyst role is correctly passed to subprocess."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("{}", "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        dispatcher.dispatch(AgentRole.ANALYST, "task", {})

        cmd = mock_popen.call_args[0][0]
        assert "analyst" in cmd

    @patch("agents.dispatcher.subprocess.Popen")
    def test_risk_controller_role(self, mock_popen, dispatcher):
        """Risk controller role is correctly passed to subprocess."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("{}", "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        dispatcher.dispatch(AgentRole.RISK_CONTROLLER, "task", {})

        cmd = mock_popen.call_args[0][0]
        assert "risk_controller" in cmd

    @patch("agents.dispatcher.subprocess.Popen")
    def test_ops_role(self, mock_popen, dispatcher):
        """Ops role is correctly passed to subprocess."""
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = ("{}", "")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        dispatcher.dispatch(AgentRole.OPS, "task", {})

        cmd = mock_popen.call_args[0][0]
        assert "ops" in cmd


class TestGracefulDegradation:
    """Tests for graceful degradation (FR-021)."""

    @patch("agents.dispatcher.subprocess.Popen")
    def test_system_survives_agent_crash(self, mock_popen):
        """System continues operating when agent crashes."""
        mock_session = MagicMock()
        dispatcher = AgentDispatcher(MagicMock(return_value=mock_session))

        # Simulate agent crash
        mock_process = MagicMock()
        mock_process.returncode = -9  # SIGKILL
        mock_process.communicate.return_value = ("", "Segmentation fault")
        mock_process.stdin = MagicMock()
        mock_popen.return_value = mock_process

        # Should not raise - graceful degradation
        result = dispatcher.dispatch(AgentRole.RESEARCHER, "crash", {})

        assert result.success is False
        assert result.error is not None

    @patch("agents.dispatcher.subprocess.Popen")
    def test_system_survives_subprocess_error(self, mock_popen):
        """System continues when subprocess fails to spawn."""
        mock_session = MagicMock()
        dispatcher = AgentDispatcher(MagicMock(return_value=mock_session))

        # Simulate spawn failure
        mock_popen.side_effect = OSError("No such file or directory")

        # Should not raise - graceful degradation
        result = dispatcher.dispatch(AgentRole.ANALYST, "fail", {})

        assert result.success is False
        assert "Unexpected error" in result.error

    def test_system_survives_db_failure(self):
        """System continues when database is unavailable."""
        mock_session = MagicMock()
        mock_session.commit.side_effect = Exception("Connection refused")
        dispatcher = AgentDispatcher(MagicMock(return_value=mock_session))

        # Mock permission checker to deny (simpler path that still tests DB failure)
        permission_checker = MagicMock()
        permission_checker.can_execute.return_value = False
        dispatcher.permission_checker = permission_checker

        # Should not raise - graceful degradation
        result = dispatcher.dispatch(AgentRole.OPS, "deploy", {})

        # Result returned even if not persisted
        assert result is not None
        assert result.success is False
