"""Tests for alpha path lint checker.

TDD: These tests are written FIRST and will FAIL until implementation exists.

The alpha path lint checker enforces the RED LINE:
"Constraints NEVER affect alpha calculations."

This means:
- No code in src/strategies/ should import from src/governance/hypothesis/
- No code in src/strategies/ should import from src/governance/constraints/
"""

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


class TestAlphaPathLintImports:
    """Tests that AlphaPathLint can be imported correctly."""

    def test_import_alpha_path_lint(self):
        """AlphaPathLint should be importable from src.governance.lint.alpha_path."""
        from src.governance.lint.alpha_path import AlphaPathLint

        assert AlphaPathLint is not None

    def test_import_lint_result(self):
        """LintResult should be importable from src.governance.lint.models."""
        from src.governance.lint.models import LintResult

        assert LintResult is not None


class TestAlphaPathLintInitialization:
    """Tests for AlphaPathLint initialization."""

    def test_init_with_default_paths(self):
        """AlphaPathLint should initialize with default alpha_path and forbidden_paths."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()
        assert lint.alpha_path == "src/strategies"
        assert "src/governance/hypothesis" in lint.forbidden_paths
        assert "src/governance/constraints" in lint.forbidden_paths

    def test_init_with_custom_alpha_path(self):
        """AlphaPathLint should accept custom alpha_path."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint(alpha_path="custom/alpha/path")
        assert lint.alpha_path == "custom/alpha/path"

    def test_init_with_custom_forbidden_paths(self):
        """AlphaPathLint should accept custom forbidden_paths."""
        from src.governance.lint.alpha_path import AlphaPathLint

        custom_forbidden = ["custom/forbidden/path1", "custom/forbidden/path2"]
        lint = AlphaPathLint(forbidden_paths=custom_forbidden)
        assert lint.forbidden_paths == custom_forbidden

    def test_init_with_both_custom_paths(self):
        """AlphaPathLint should accept both custom alpha_path and forbidden_paths."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint(
            alpha_path="my/alpha",
            forbidden_paths=["my/forbidden1", "my/forbidden2"],
        )
        assert lint.alpha_path == "my/alpha"
        assert lint.forbidden_paths == ["my/forbidden1", "my/forbidden2"]


class TestCheckFileMethod:
    """Tests for the check_file() method."""

    def test_check_file_no_imports_returns_empty(self):
        """check_file() should return empty list for file with no forbidden imports."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import os
import numpy as np
from src.strategies.base import BaseStrategy

def calculate_alpha():
    return 42
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert violations == []
        finally:
            os.unlink(temp_path)

    def test_check_file_detects_hypothesis_import(self):
        """check_file() should detect import from src.governance.hypothesis."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import src.governance.hypothesis
from src.strategies.base import BaseStrategy
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
            assert "src.governance.hypothesis" in violations[0]
            assert temp_path in violations[0]
        finally:
            os.unlink(temp_path)

    def test_check_file_detects_constraints_import(self):
        """check_file() should detect import from src.governance.constraints."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import src.governance.constraints
from src.strategies.base import BaseStrategy
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
            assert "src.governance.constraints" in violations[0]
            assert temp_path in violations[0]
        finally:
            os.unlink(temp_path)

    def test_check_file_detects_from_import_hypothesis(self):
        """check_file() should detect 'from src.governance.hypothesis import X'."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
from src.governance.hypothesis import HypothesisLoader
from src.strategies.base import BaseStrategy
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
            assert "src.governance.hypothesis" in violations[0]
        finally:
            os.unlink(temp_path)

    def test_check_file_detects_from_import_constraints(self):
        """check_file() should detect 'from src.governance.constraints import X'."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
from src.governance.constraints import ConstraintLoader
from src.strategies.base import BaseStrategy
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
            assert "src.governance.constraints" in violations[0]
        finally:
            os.unlink(temp_path)

    def test_check_file_detects_multiple_violations(self):
        """check_file() should detect multiple forbidden imports in one file."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
import src.governance.hypothesis
from src.governance.constraints import ConstraintLoader
from src.governance.hypothesis.models import Hypothesis
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 3
        finally:
            os.unlink(temp_path)

    def test_check_file_detects_nested_module_import(self):
        """check_file() should detect imports from nested forbidden modules."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
from src.governance.hypothesis.models import Hypothesis
from src.governance.constraints.loader import ConstraintLoader
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 2
            assert any("src.governance.hypothesis" in v for v in violations)
            assert any("src.governance.constraints" in v for v in violations)
        finally:
            os.unlink(temp_path)

    def test_check_file_ignores_similar_module_names(self):
        """check_file() should not flag modules with similar but different names."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
# These should NOT be flagged
from src.governance.models import SomeModel
from src.governance.audit import AuditLogger
import src.governance.cache
from my_app.hypothesis import MyHypothesis
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert violations == []
        finally:
            os.unlink(temp_path)

    def test_check_file_handles_syntax_error(self):
        """check_file() should handle files with syntax errors gracefully."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
def broken_function(
    # Missing closing paren and colon
""")
            f.flush()
            temp_path = f.name

        try:
            # Should not raise, but should return a violation or empty list
            violations = lint.check_file(temp_path)
            # Either returns empty list (ignoring unparseable) or a syntax error violation
            assert isinstance(violations, list)
        finally:
            os.unlink(temp_path)

    def test_check_file_nonexistent_file(self):
        """check_file() should handle non-existent files gracefully."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        # Should not raise an exception
        violations = lint.check_file("/nonexistent/path/file.py")
        assert isinstance(violations, list)


class TestCheckDirectoryMethod:
    """Tests for the check_directory() method."""

    def test_check_directory_scans_all_py_files(self):
        """check_directory() should scan all .py files in directory."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create multiple Python files
            file1 = Path(tmpdir) / "file1.py"
            file2 = Path(tmpdir) / "file2.py"
            file3 = Path(tmpdir) / "file3.txt"  # Not a .py file

            file1.write_text("import os\n")
            file2.write_text("import sys\n")
            file3.write_text("not python\n")

            violations, checked_count = lint.check_directory(tmpdir)
            assert checked_count == 2  # Only .py files
            assert violations == []

    def test_check_directory_recurses_subdirectories(self):
        """check_directory() should recurse into subdirectories."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested structure
            subdir = Path(tmpdir) / "subdir"
            subdir.mkdir()
            subsubdir = subdir / "deeper"
            subsubdir.mkdir()

            (Path(tmpdir) / "root.py").write_text("import os\n")
            (subdir / "sub.py").write_text("import sys\n")
            (subsubdir / "deep.py").write_text("import json\n")

            violations, checked_count = lint.check_directory(tmpdir)
            assert checked_count == 3

    def test_check_directory_ignores_pycache(self):
        """check_directory() should ignore __pycache__ directories."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create __pycache__ directory
            pycache = Path(tmpdir) / "__pycache__"
            pycache.mkdir()

            (Path(tmpdir) / "main.py").write_text("import os\n")
            (pycache / "main.cpython-310.pyc").write_text("bytecode\n")
            (pycache / "cached.py").write_text("import src.governance.hypothesis\n")

            violations, checked_count = lint.check_directory(tmpdir)
            assert checked_count == 1  # Only main.py, not files in __pycache__
            assert violations == []

    def test_check_directory_finds_violations(self):
        """check_directory() should find violations in files."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "clean.py").write_text("import os\n")
            (Path(tmpdir) / "dirty.py").write_text("import src.governance.hypothesis\n")

            violations, checked_count = lint.check_directory(tmpdir)
            assert checked_count == 2
            assert len(violations) == 1
            assert "dirty.py" in violations[0]

    def test_check_directory_empty_directory(self):
        """check_directory() should handle empty directories."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            violations, checked_count = lint.check_directory(tmpdir)
            assert checked_count == 0
            assert violations == []

    def test_check_directory_ignores_init_files_option(self):
        """check_directory() should optionally ignore __init__.py files."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "__init__.py").write_text("import src.governance.hypothesis\n")
            (Path(tmpdir) / "module.py").write_text("import src.governance.hypothesis\n")

            # By default, should check all files including __init__.py
            violations, checked_count = lint.check_directory(tmpdir)
            assert checked_count == 2
            assert len(violations) == 2


class TestRunMethod:
    """Tests for the run() method that returns LintResult."""

    def test_run_returns_lint_result(self):
        """run() should return a LintResult object."""
        from src.governance.lint.alpha_path import AlphaPathLint
        from src.governance.lint.models import LintResult

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "clean.py").write_text("import os\n")
            result = lint.run(tmpdir)

            assert isinstance(result, LintResult)

    def test_run_passed_true_when_no_violations(self):
        """run() should return passed=True when no violations found."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "clean.py").write_text("import os\n")
            (Path(tmpdir) / "also_clean.py").write_text("import sys\n")
            result = lint.run(tmpdir)

            assert result.passed is True
            assert result.violations == []

    def test_run_passed_false_when_violations_found(self):
        """run() should return passed=False when violations found."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "dirty.py").write_text(
                "from src.governance.hypothesis import Hypothesis\n"
            )
            result = lint.run(tmpdir)

            assert result.passed is False
            assert len(result.violations) > 0

    def test_run_violations_contain_file_path(self):
        """run() violations should contain the file path."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            dirty_path = Path(tmpdir) / "my_strategy.py"
            dirty_path.write_text("import src.governance.constraints\n")
            result = lint.run(tmpdir)

            assert len(result.violations) == 1
            assert "my_strategy.py" in result.violations[0]

    def test_run_violations_contain_import_details(self):
        """run() violations should contain details about the forbidden import."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "strategy.py").write_text(
                "from src.governance.hypothesis.loader import HypothesisLoader\n"
            )
            result = lint.run(tmpdir)

            assert len(result.violations) == 1
            assert "src.governance.hypothesis" in result.violations[0]

    def test_run_checked_files_count_accurate(self):
        """run() should return accurate checked_files count."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                (Path(tmpdir) / f"file{i}.py").write_text(f"# file {i}\n")
            # Also add a non-py file that shouldn't be counted
            (Path(tmpdir) / "readme.txt").write_text("not python\n")

            result = lint.run(tmpdir)
            assert result.checked_files == 5

    def test_run_checked_at_is_datetime(self):
        """run() should set checked_at to current datetime."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "file.py").write_text("import os\n")

            before = datetime.now(timezone.utc)
            result = lint.run(tmpdir)
            after = datetime.now(timezone.utc)

            assert result.checked_at is not None
            assert before <= result.checked_at <= after


class TestLintResultModel:
    """Tests for the LintResult model."""

    def test_lint_result_required_fields(self):
        """LintResult should have required fields: passed, violations."""
        from src.governance.lint.models import LintResult

        result = LintResult(passed=True, violations=[])
        assert result.passed is True
        assert result.violations == []

    def test_lint_result_with_violations(self):
        """LintResult should accept violations list."""
        from src.governance.lint.models import LintResult

        violations = [
            "file1.py: imports src.governance.hypothesis",
            "file2.py: imports src.governance.constraints",
        ]
        result = LintResult(passed=False, violations=violations)
        assert result.passed is False
        assert len(result.violations) == 2

    def test_lint_result_checked_files_optional(self):
        """LintResult checked_files should be optional."""
        from src.governance.lint.models import LintResult

        # Without checked_files
        result1 = LintResult(passed=True, violations=[])
        assert result1.checked_files is None or hasattr(result1, "checked_files")

        # With checked_files
        result2 = LintResult(passed=True, violations=[], checked_files=10)
        assert result2.checked_files == 10

    def test_lint_result_checked_at_optional(self):
        """LintResult checked_at should be optional."""
        from src.governance.lint.models import LintResult

        # Without checked_at
        result1 = LintResult(passed=True, violations=[])
        assert result1.checked_at is None or hasattr(result1, "checked_at")

        # With checked_at
        now = datetime.now(timezone.utc)
        result2 = LintResult(passed=True, violations=[], checked_at=now)
        assert result2.checked_at == now

    def test_lint_result_json_serializable(self):
        """LintResult should be JSON serializable."""
        from src.governance.lint.models import LintResult

        now = datetime.now(timezone.utc)
        result = LintResult(
            passed=False,
            violations=["file.py: forbidden import"],
            checked_files=5,
            checked_at=now,
        )

        # Should be able to serialize to dict/JSON
        result_dict = result.model_dump()
        assert result_dict["passed"] is False
        assert len(result_dict["violations"]) == 1
        assert result_dict["checked_files"] == 5


class TestRealWorldScenarios:
    """Integration-style tests with real AST parsing scenarios."""

    def test_complex_file_with_mixed_imports(self):
        """Test file with mix of allowed and forbidden imports."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        code = '''
"""Strategy module with various imports."""

import os
import sys
from typing import List, Dict, Optional

import numpy as np
import pandas as pd

from src.strategies.base import BaseStrategy
from src.strategies.signals import SignalGenerator
from src.governance.models import GovernanceBaseModel  # This is allowed
from src.governance.hypothesis.loader import HypothesisLoader  # FORBIDDEN!
from src.governance.constraints import ConstraintResolver  # FORBIDDEN!

class MyStrategy(BaseStrategy):
    """A strategy that incorrectly imports governance modules."""

    def calculate_alpha(self, data: pd.DataFrame) -> float:
        # Using hypothesis in alpha calculation is forbidden!
        loader = HypothesisLoader()
        return 0.5
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 2
            assert any("hypothesis" in v.lower() for v in violations)
            assert any("constraints" in v.lower() for v in violations)
        finally:
            os.unlink(temp_path)

    def test_aliased_import_detection(self):
        """Test detection of aliased imports."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        code = """
import src.governance.hypothesis as hyp
from src.governance.constraints import ConstraintLoader as CL
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 2
        finally:
            os.unlink(temp_path)

    def test_conditional_import_detection(self):
        """Test detection of imports inside if blocks."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        code = """
import os

if os.environ.get("DEBUG"):
    from src.governance.hypothesis import HypothesisLoader

def main():
    try:
        import src.governance.constraints
    except ImportError:
        pass
"""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            # Should detect both forbidden imports regardless of context
            assert len(violations) == 2
        finally:
            os.unlink(temp_path)

    def test_string_import_not_detected(self):
        """Test that string mentions of imports are not flagged."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        code = '''
# This is a comment about src.governance.hypothesis
docstring = """
This module should not import from src.governance.constraints
"""
log_message = "Do not use src.governance.hypothesis in alpha path"
'''

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            # String mentions should not be flagged, only actual imports
            assert violations == []
        finally:
            os.unlink(temp_path)

    def test_run_on_actual_strategies_directory(self):
        """Test running lint on the actual strategies directory."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        # Run on the real strategies directory
        strategies_path = Path(__file__).parent.parent.parent.parent.parent / "src" / "strategies"

        if strategies_path.exists():
            result = lint.run(str(strategies_path))
            # The actual codebase should pass the lint check
            assert result.passed is True, f"Violations found: {result.violations}"
            assert result.checked_files > 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_file(self):
        """Test handling of empty Python file."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert violations == []
        finally:
            os.unlink(temp_path)

    def test_file_with_only_comments(self):
        """Test handling of file with only comments."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
# This is a comment
# Another comment
# import src.governance.hypothesis  # commented out import
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert violations == []
        finally:
            os.unlink(temp_path)

    def test_file_with_docstring_only(self):
        """Test handling of file with only a docstring."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write('"""This module does something."""\n')
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert violations == []
        finally:
            os.unlink(temp_path)

    def test_unicode_in_file(self):
        """Test handling of files with unicode characters."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write('''
# -*- coding: utf-8 -*-
"""Module with unicode: \u00e9\u00e0\u00fc\u4e2d\u6587"""
import src.governance.hypothesis  # violation
message = "Hello \u4e16\u754c"
''')
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
        finally:
            os.unlink(temp_path)

    def test_deeply_nested_directory(self):
        """Test scanning deeply nested directory structure."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create deeply nested structure
            deep_path = Path(tmpdir)
            for i in range(5):
                deep_path = deep_path / f"level{i}"
                deep_path.mkdir()
                (deep_path / f"module{i}.py").write_text("import os\n")

            # Add a violation at the deepest level
            (deep_path / "violator.py").write_text("import src.governance.hypothesis\n")

            result = lint.run(tmpdir)
            assert result.checked_files == 6  # 5 level modules + 1 violator
            assert result.passed is False
            assert len(result.violations) == 1
            assert "violator.py" in result.violations[0]


class TestViolationMessageFormat:
    """Tests for violation message format."""

    def test_violation_includes_line_number(self):
        """Violation message should include line number."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
# Line 1
# Line 2
import src.governance.hypothesis  # Line 4
""")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
            # Violation should mention line 4
            assert "4" in violations[0] or "line" in violations[0].lower()
        finally:
            os.unlink(temp_path)

    def test_violation_format_readable(self):
        """Violation message should be human-readable."""
        from src.governance.lint.alpha_path import AlphaPathLint

        lint = AlphaPathLint()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("from src.governance.constraints.loader import ConstraintLoader\n")
            f.flush()
            temp_path = f.name

        try:
            violations = lint.check_file(temp_path)
            assert len(violations) == 1
            # Message should be understandable
            violation = violations[0]
            assert temp_path in violation or os.path.basename(temp_path) in violation
            assert "src.governance.constraints" in violation
        finally:
            os.unlink(temp_path)
