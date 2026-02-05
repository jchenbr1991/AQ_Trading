"""Alpha path lint checker.

This module enforces the RED LINE: "Constraints NEVER affect alpha calculations."

The AlphaPathLint class uses AST to detect imports from forbidden paths in alpha code.
This prevents code in src/strategies/ from importing governance modules that could
influence alpha calculations.

Forbidden imports:
    - src.governance.hypothesis (hypothesis management)
    - src.governance.constraints (constraint resolution)

Classes:
    AlphaPathLint: Lint checker for forbidden imports in alpha path
"""

import ast
from datetime import datetime, timezone
from pathlib import Path

from src.governance.lint.models import LintResult


class AlphaPathLint:
    """Lint checker that detects forbidden imports in alpha path.

    Enforces the governance red line by preventing alpha code (strategies)
    from importing governance modules (hypothesis, constraints).

    Attributes:
        alpha_path: Path to the alpha code directory (default: src/strategies).
        forbidden_paths: List of module paths that should not be imported.

    Example:
        >>> lint = AlphaPathLint()
        >>> result = lint.run("/path/to/src/strategies")
        >>> if not result.passed:
        ...     print("Violations found:", result.violations)
    """

    DEFAULT_ALPHA_PATH = "src/strategies"
    DEFAULT_FORBIDDEN_PATHS = [
        "src/governance/hypothesis",
        "src/governance/constraints",
    ]

    def __init__(
        self,
        alpha_path: str | None = None,
        forbidden_paths: list[str] | None = None,
    ) -> None:
        """Initialize the alpha path lint checker.

        Args:
            alpha_path: Path to the alpha code directory.
                       Defaults to "src/strategies".
            forbidden_paths: List of module paths that should not be imported.
                            Defaults to hypothesis and constraints modules.
        """
        self.alpha_path = alpha_path if alpha_path is not None else self.DEFAULT_ALPHA_PATH
        self.forbidden_paths = (
            forbidden_paths if forbidden_paths is not None else self.DEFAULT_FORBIDDEN_PATHS
        )

    def _normalize_module_path(self, module_name: str) -> str:
        """Normalize a module name to path format (dots to slashes).

        Args:
            module_name: Module name like "src.governance.hypothesis".

        Returns:
            Normalized path like "src/governance/hypothesis".
        """
        return module_name.replace(".", "/")

    def _is_forbidden_import(self, module_name: str) -> bool:
        """Check if a module name matches any forbidden path.

        Args:
            module_name: Full module name from import statement.

        Returns:
            True if the module matches a forbidden path.
        """
        normalized = self._normalize_module_path(module_name)
        for forbidden in self.forbidden_paths:
            # Check if the normalized module starts with the forbidden path
            if normalized == forbidden or normalized.startswith(f"{forbidden}/"):
                return True
        return False

    def _check_imported_names_from_parent(
        self, parent_module: str, imported_names: list[str]
    ) -> list[str]:
        """Check if importing specific names from a parent module is forbidden.

        This catches patterns like `from src.governance import constraints`
        where the parent module itself isn't forbidden but the imported name
        would result in access to a forbidden module.

        Args:
            parent_module: The parent module path (e.g., "src.governance").
            imported_names: List of names being imported.

        Returns:
            List of forbidden module paths that would be accessed.
        """
        forbidden_accessed = []
        normalized_parent = self._normalize_module_path(parent_module)

        for name in imported_names:
            # Construct the full module path as if the name were a submodule
            full_path = f"{normalized_parent}/{name}"
            for forbidden in self.forbidden_paths:
                if full_path == forbidden or full_path.startswith(f"{forbidden}/"):
                    forbidden_accessed.append(f"{parent_module}.{name}")
        return forbidden_accessed

    def check_file(self, path: str) -> list[str]:
        """Check a single Python file for forbidden imports.

        Uses AST parsing to detect import statements. This catches both:
        - `import src.governance.hypothesis`
        - `from src.governance.hypothesis import X`

        Args:
            path: Path to the Python file to check.

        Returns:
            List of violation messages. Empty if no violations found.
        """
        violations: list[str] = []

        try:
            file_path = Path(path)
            if not file_path.exists():
                return violations

            content = file_path.read_text(encoding="utf-8")
            tree = ast.parse(content)
        except SyntaxError:
            # Skip files with syntax errors
            return violations
        except Exception:
            # Skip files that cannot be read/parsed
            return violations

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # Handle: import src.governance.hypothesis
                for alias in node.names:
                    if self._is_forbidden_import(alias.name):
                        violations.append(f"{path}:{node.lineno}: forbidden import '{alias.name}'")
            elif isinstance(node, ast.ImportFrom):
                # Handle: from src.governance.hypothesis import X
                if node.module and self._is_forbidden_import(node.module):
                    violations.append(
                        f"{path}:{node.lineno}: forbidden import from '{node.module}'"
                    )
                # Also check: from src.governance import constraints
                # This catches imports from parent modules that access forbidden submodules
                elif node.module:
                    imported_names = [alias.name for alias in node.names]
                    forbidden_accessed = self._check_imported_names_from_parent(
                        node.module, imported_names
                    )
                    for forbidden_module in forbidden_accessed:
                        violations.append(
                            f"{path}:{node.lineno}: forbidden import '{forbidden_module}' via parent module"
                        )

        return violations

    def check_directory(self, path: str) -> tuple[list[str], int]:
        """Check all Python files in a directory for forbidden imports.

        Recursively scans the directory for .py files, excluding __pycache__
        directories.

        Args:
            path: Path to the directory to check.

        Returns:
            Tuple of (violations list, count of checked files).
        """
        violations: list[str] = []
        checked_count = 0

        dir_path = Path(path)
        if not dir_path.exists():
            return violations, checked_count

        for py_file in dir_path.rglob("*.py"):
            # Skip __pycache__ directories
            if "__pycache__" in py_file.parts:
                continue

            file_violations = self.check_file(str(py_file))
            violations.extend(file_violations)
            checked_count += 1

        return violations, checked_count

    def run(self, path: str | None = None) -> LintResult:
        """Run the full lint check and return a LintResult.

        Args:
            path: Path to check. Defaults to self.alpha_path.

        Returns:
            LintResult with pass/fail status, violations, and metadata.
        """
        check_path = path if path is not None else self.alpha_path
        violations, checked_count = self.check_directory(check_path)

        return LintResult(
            passed=len(violations) == 0,
            violations=violations,
            checked_files=checked_count,
            checked_at=datetime.now(timezone.utc),
        )


__all__ = ["AlphaPathLint"]
