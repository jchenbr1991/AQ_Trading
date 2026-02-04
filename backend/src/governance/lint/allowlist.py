"""Constraint allowlist lint checker.

This module validates that constraint YAML files only use allowlisted action fields.
It enforces the declarative constraint schema defined in the OpenAPI spec.

The DEFAULT_ALLOWLIST contains the ConstraintActions fields that constraints
are allowed to use. Any other field in the actions section is a violation.

Allowlisted action fields:
    - enable_strategy
    - pool_bias_multiplier
    - veto_downgrade
    - risk_budget_multiplier
    - holding_extension_days
    - add_position_cap_multiplier
    - stop_mode

Classes:
    AllowlistLint: Lint checker for constraint action field validation
"""

from collections.abc import Set as AbstractSet
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.governance.lint.models import LintResult

# Default allowlisted action fields from ConstraintActions model
DEFAULT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "enable_strategy",
        "pool_bias_multiplier",
        "veto_downgrade",
        "risk_budget_multiplier",
        "holding_extension_days",
        "add_position_cap_multiplier",
        "stop_mode",
    }
)


class AllowlistLint:
    """Lint checker that validates constraint YAML files use only allowlisted action fields.

    Ensures constraints only use the declared ConstraintActions fields,
    providing an additional declarative check beyond Pydantic validation.

    Attributes:
        allowlist: Set of allowed action field names.
        constraints_dir: Directory containing constraint YAML files.

    Example:
        >>> lint = AllowlistLint()
        >>> result = lint.run()
        >>> if not result.passed:
        ...     print("Violations found:", result.violations)
    """

    DEFAULT_CONSTRAINTS_DIR = Path("config/constraints")

    def __init__(
        self,
        allowlist: AbstractSet[str] | None = None,
        constraints_dir: Path | None = None,
    ) -> None:
        """Initialize the allowlist lint checker.

        Args:
            allowlist: Set of allowed action field names.
                      Defaults to DEFAULT_ALLOWLIST.
            constraints_dir: Directory containing constraint YAML files.
                            Defaults to config/constraints.
        """
        self.allowlist = allowlist if allowlist is not None else DEFAULT_ALLOWLIST
        self.constraints_dir = (
            constraints_dir if constraints_dir is not None else self.DEFAULT_CONSTRAINTS_DIR
        )

    def check_constraint(self, path: str | Path) -> list[str]:
        """Check a single constraint YAML file for non-allowlisted action fields.

        Args:
            path: Path to the constraint YAML file.

        Returns:
            List of violation messages. Empty if no violations found.

        Raises:
            FileNotFoundError: If the constraint file does not exist.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Constraint file not found: {path}")

        violations: list[str] = []

        try:
            content = file_path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
        except yaml.YAMLError as e:
            # Re-raise YAML errors with more context
            raise yaml.YAMLError(f"Failed to parse YAML file {path}: {e}") from e

        if data is None:
            return violations

        constraint_id = data.get("id", str(file_path.name))
        actions = data.get("actions")

        if actions is None or not isinstance(actions, dict):
            return violations

        # Check each action field against allowlist
        for field_name in actions.keys():
            if field_name not in self.allowlist:
                violations.append(
                    f"Constraint '{constraint_id}': non-allowlisted action field '{field_name}'"
                )

        return violations

    def check_directory(self, path: str | Path | None = None) -> LintResult:
        """Check all constraint YAML files in a directory.

        Scans for .yml and .yaml files, excluding files starting with underscore.

        Args:
            path: Directory to check. Defaults to self.constraints_dir.

        Returns:
            LintResult with pass/fail status, violations, and metadata.
        """
        check_path = Path(path) if path is not None else self.constraints_dir
        violations: list[str] = []
        checked_count = 0

        if not check_path.exists():
            return LintResult(
                passed=True,
                violations=[],
                checked_files=0,
                checked_at=datetime.now(timezone.utc),
            )

        # Collect all YAML files
        yaml_files: list[Path] = []
        for pattern in ["*.yml", "*.yaml"]:
            yaml_files.extend(check_path.glob(pattern))

        for yaml_file in yaml_files:
            # Skip files starting with underscore
            if yaml_file.name.startswith("_"):
                continue

            try:
                file_violations = self.check_constraint(yaml_file)
                violations.extend(file_violations)
                checked_count += 1
            except Exception:
                # Skip files that cannot be parsed
                checked_count += 1
                continue

        return LintResult(
            passed=len(violations) == 0,
            violations=violations,
            checked_files=checked_count,
            checked_at=datetime.now(timezone.utc),
        )

    def run(self) -> LintResult:
        """Run the full lint check on the constraints directory.

        Returns:
            LintResult with pass/fail status, violations, and metadata.

        Raises:
            FileNotFoundError: If the constraints directory does not exist.
        """
        if not self.constraints_dir.exists():
            raise FileNotFoundError(f"Constraints directory not found: {self.constraints_dir}")

        return self.check_directory(self.constraints_dir)


__all__ = ["AllowlistLint", "DEFAULT_ALLOWLIST"]
