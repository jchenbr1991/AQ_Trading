# AQ Trading AI Agents - CLI Executor Tests
"""Tests for CLI-based LLM executor.

Following TDD - tests written first to define expected behavior.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from agents.llm import CLIExecutor, CLIExecutorError, LLMProvider, get_executor


class TestLLMProvider:
    """Tests for LLMProvider enum."""

    def test_codex_provider(self):
        """Test CODEX provider value."""
        assert LLMProvider.CODEX.value == "codex"

    def test_gemini_provider(self):
        """Test GEMINI provider value."""
        assert LLMProvider.GEMINI.value == "gemini"


class TestCLIExecutorInit:
    """Tests for CLIExecutor initialization."""

    def test_init_with_codex(self):
        """Test initialization with codex provider."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            executor = CLIExecutor(provider=LLMProvider.CODEX)
            assert executor.provider == LLMProvider.CODEX
            assert executor.timeout == CLIExecutor.DEFAULT_TIMEOUT

    def test_init_with_gemini(self):
        """Test initialization with gemini provider."""
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            executor = CLIExecutor(provider=LLMProvider.GEMINI)
            assert executor.provider == LLMProvider.GEMINI

    def test_init_with_string_provider(self):
        """Test initialization with string provider name."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            executor = CLIExecutor(provider="codex")
            assert executor.provider == LLMProvider.CODEX

    def test_init_with_custom_timeout(self):
        """Test initialization with custom timeout."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            executor = CLIExecutor(provider=LLMProvider.CODEX, timeout=60)
            assert executor.timeout == 60

    def test_init_warns_when_cli_not_found(self, caplog):
        """Test that warning is logged when CLI is not found."""
        with patch("shutil.which", return_value=None):
            import logging
            with caplog.at_level(logging.WARNING):
                executor = CLIExecutor(provider=LLMProvider.CODEX)
                assert "codex CLI not found" in caplog.text


class TestBuildPrompt:
    """Tests for prompt building."""

    @pytest.fixture
    def executor(self):
        with patch("shutil.which", return_value="/usr/bin/codex"):
            return CLIExecutor(provider=LLMProvider.CODEX)

    def test_build_prompt_structure(self, executor):
        """Test that prompt has correct structure."""
        prompt = executor._build_prompt(
            system_prompt="You are a test agent.",
            task="Analyze data",
            context={"symbol": "AAPL"},
        )

        assert "## System Instructions" in prompt
        assert "You are a test agent." in prompt
        assert "## Task" in prompt
        assert "Analyze data" in prompt
        assert "## Context" in prompt
        assert '"symbol": "AAPL"' in prompt

    def test_build_prompt_empty_context(self, executor):
        """Test prompt with empty context."""
        prompt = executor._build_prompt(
            system_prompt="Test agent",
            task="Do something",
            context={},
        )

        assert "{}" in prompt


class TestBuildCommand:
    """Tests for command building."""

    def test_codex_command(self):
        """Test codex command format."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            executor = CLIExecutor(provider=LLMProvider.CODEX)
            command = executor._build_command("test prompt")
            assert command == ["codex", "review", "test prompt"]

    def test_gemini_command(self):
        """Test gemini command format."""
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            executor = CLIExecutor(provider=LLMProvider.GEMINI)
            command = executor._build_command("test prompt")
            assert command == ["gemini", "-p", "test prompt"]


class TestParseResponse:
    """Tests for response parsing."""

    @pytest.fixture
    def executor(self):
        with patch("shutil.which", return_value="/usr/bin/codex"):
            return CLIExecutor(provider=LLMProvider.CODEX)

    def test_parse_valid_json(self, executor):
        """Test parsing valid JSON response."""
        output = '{"success": true, "result": "analysis done", "confidence": 0.9}'
        result = executor._parse_response(output)

        assert result["success"] is True
        assert result["result"] == "analysis done"
        assert result["confidence"] == 0.9

    def test_parse_json_with_surrounding_text(self, executor):
        """Test parsing JSON with surrounding text."""
        output = 'Here is the analysis:\n{"success": true, "result": "done"}\nEnd of response.'
        result = executor._parse_response(output)

        assert result["success"] is True
        assert result["result"] == "done"

    def test_parse_non_json_output(self, executor):
        """Test parsing non-JSON output returns error (expected JSON)."""
        output = "This is just plain text analysis."
        result = executor._parse_response(output)

        # Non-JSON output is treated as a parsing failure
        assert result["success"] is False
        assert result["result"] is None
        assert "No valid JSON" in result["error"]
        assert result["raw_output"] == output

    def test_parse_adds_missing_fields(self, executor):
        """Test that parsing adds default values for missing fields."""
        output = '{"analysis": "complete"}'
        result = executor._parse_response(output)

        assert result["success"] is True
        assert "confidence" in result


class TestExecute:
    """Tests for async execute method."""

    @pytest.fixture
    def executor(self):
        with patch("shutil.which", return_value="/usr/bin/codex"):
            return CLIExecutor(provider=LLMProvider.CODEX, timeout=5)

    @pytest.mark.asyncio
    async def test_execute_success(self, executor):
        """Test successful execution."""
        mock_process = AsyncMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(
                b'{"success": true, "result": "analysis complete"}',
                b"",
            )
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute(
                system_prompt="You are a test agent.",
                task="Analyze data",
                context={"symbol": "AAPL"},
            )

            assert result["success"] is True
            assert result["result"] == "analysis complete"

    @pytest.mark.asyncio
    async def test_execute_cli_failure(self, executor):
        """Test handling of CLI failure."""
        mock_process = AsyncMock()
        mock_process.returncode = 1
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"Command failed")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute(
                system_prompt="Test",
                task="Do something",
                context={},
            )

            assert result["success"] is False
            assert "Command failed" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_timeout(self, executor):
        """Test handling of timeout."""
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await executor.execute(
                system_prompt="Test",
                task="Long task",
                context={},
            )

            assert result["success"] is False
            assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_execute_cli_not_found(self, executor):
        """Test handling when CLI is not found."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("codex not found"),
        ):
            result = await executor.execute(
                system_prompt="Test",
                task="Task",
                context={},
            )

            assert result["success"] is False
            assert "not found" in result["error"]


class TestGetExecutor:
    """Tests for get_executor factory function."""

    def test_get_default_executor(self):
        """Test getting default executor (codex)."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            executor = get_executor()
            assert executor.provider == LLMProvider.CODEX

    def test_get_gemini_executor(self):
        """Test getting gemini executor."""
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            executor = get_executor(provider=LLMProvider.GEMINI)
            assert executor.provider == LLMProvider.GEMINI

    def test_get_executor_returns_same_instance(self):
        """Test that get_executor returns cached instance for same provider."""
        with patch("shutil.which", return_value="/usr/bin/codex"):
            executor1 = get_executor(provider=LLMProvider.CODEX)
            executor2 = get_executor(provider=LLMProvider.CODEX)
            assert executor1 is executor2

    def test_get_executor_different_provider_returns_new_instance(self):
        """Test that different provider returns new instance."""
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            executor1 = get_executor(provider=LLMProvider.CODEX)
        with patch("shutil.which", return_value="/usr/bin/gemini"):
            executor2 = get_executor(provider=LLMProvider.GEMINI)
            # executor2 should be different (new instance for gemini)
            assert executor2.provider == LLMProvider.GEMINI
