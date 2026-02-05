"""Tests for constraint allowlist lint checker.

TDD: Write tests FIRST, then implement AllowlistLint to make them pass.

This module tests the AllowlistLint class which validates that:
`lint:constraint_actions_allowlist` - Constraints only use fields from the
allowlisted ConstraintActions fields.

The ALLOWLISTED fields in ConstraintActions are:
- enable_strategy
- pool_bias_multiplier
- veto_downgrade
- risk_budget_multiplier
- holding_extension_days
- add_position_cap_multiplier
- stop_mode

Any other field would be a violation (though Pydantic with extra="forbid" should
also catch this at load time, the lint provides an additional declarative check).
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest


class TestAllowlistLintInitialization:
    """Tests for AllowlistLint initialization and configuration."""

    def test_allowlist_lint_initialization_default(self):
        """AllowlistLint should initialize with default allowlist."""
        from src.governance.lint.allowlist import DEFAULT_ALLOWLIST, AllowlistLint

        lint = AllowlistLint()

        assert lint is not None
        assert hasattr(lint, "allowlist")
        assert lint.allowlist == DEFAULT_ALLOWLIST

    def test_allowlist_lint_initialization_custom_allowlist(self):
        """AllowlistLint should accept custom allowlist configuration."""
        from src.governance.lint.allowlist import AllowlistLint

        custom_allowlist = {"enable_strategy", "pool_bias_multiplier"}

        lint = AllowlistLint(allowlist=custom_allowlist)

        assert lint.allowlist == custom_allowlist

    def test_allowlist_lint_initialization_with_constraints_directory(self):
        """AllowlistLint should accept custom constraints directory."""
        from src.governance.lint.allowlist import AllowlistLint

        with tempfile.TemporaryDirectory() as tmpdir:
            lint = AllowlistLint(constraints_dir=Path(tmpdir))

            assert lint.constraints_dir == Path(tmpdir)

    def test_allowlist_lint_has_default_constraints_directory(self):
        """AllowlistLint should have a default constraints directory."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()

        assert hasattr(lint, "constraints_dir")
        assert lint.constraints_dir is not None
        assert "constraints" in str(lint.constraints_dir).lower()


class TestDefaultAllowlist:
    """Tests for the default allowlist configuration."""

    def test_default_allowlist_matches_openapi_spec(self):
        """DEFAULT_ALLOWLIST should match the OpenAPI spec ConstraintActions fields."""
        from src.governance.lint.allowlist import DEFAULT_ALLOWLIST

        expected_fields = {
            "enable_strategy",
            "pool_bias_multiplier",
            "veto_downgrade",
            "risk_budget_multiplier",
            "holding_extension_days",
            "add_position_cap_multiplier",
            "stop_mode",
        }

        assert DEFAULT_ALLOWLIST == expected_fields

    def test_default_allowlist_is_frozen_set_or_immutable(self):
        """DEFAULT_ALLOWLIST should be immutable to prevent accidental modification."""
        from src.governance.lint.allowlist import DEFAULT_ALLOWLIST

        # Should be a frozenset or set that won't be accidentally modified
        assert isinstance(DEFAULT_ALLOWLIST, set | frozenset)
        # Verify all elements are strings
        assert all(isinstance(field, str) for field in DEFAULT_ALLOWLIST)

    def test_default_allowlist_is_importable(self):
        """DEFAULT_ALLOWLIST should be importable from the allowlist module."""
        from src.governance.lint.allowlist import DEFAULT_ALLOWLIST

        assert DEFAULT_ALLOWLIST is not None


class TestCheckConstraint:
    """Tests for check_constraint() method."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def valid_constraint_yaml(self) -> str:
        """Return a valid constraint YAML using only allowlisted fields."""
        return """
id: valid_constraint
title: Valid Constraint
applies_to:
  symbols:
    - AAPL
activation:
  requires_hypotheses_active: []
actions:
  enable_strategy: true
  pool_bias_multiplier: 1.5
  veto_downgrade: false
  risk_budget_multiplier: 2.0
  holding_extension_days: 5
  add_position_cap_multiplier: 1.2
  stop_mode: wide
"""

    @pytest.fixture
    def partial_constraint_yaml(self) -> str:
        """Return a constraint YAML with only some action fields set."""
        return """
id: partial_constraint
title: Partial Constraint
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  risk_budget_multiplier: 1.5
"""

    @pytest.fixture
    def empty_actions_constraint_yaml(self) -> str:
        """Return a constraint YAML with empty actions."""
        return """
id: empty_actions_constraint
title: Empty Actions Constraint
applies_to: {}
activation: {}
actions: {}
"""

    @pytest.fixture
    def invalid_constraint_yaml_unknown_field(self) -> str:
        """Return a constraint YAML with a non-allowlisted field in actions."""
        return """
id: invalid_constraint
title: Invalid Constraint
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  forbidden_custom_field: "should_fail"
  risk_budget_multiplier: 1.5
"""

    @pytest.fixture
    def invalid_constraint_yaml_multiple_unknown_fields(self) -> str:
        """Return a constraint YAML with multiple non-allowlisted fields."""
        return """
id: multiple_invalid_constraint
title: Multiple Invalid Constraint
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  unknown_field_1: true
  unknown_field_2: 123
  another_bad_field: "bad"
"""

    def test_check_constraint_valid_returns_no_violations(
        self, temp_dir: Path, valid_constraint_yaml: str
    ):
        """check_constraint() should return empty violations for valid constraint."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "valid.yml"
        path.write_text(valid_constraint_yaml)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        assert violations == []

    def test_check_constraint_partial_valid_returns_no_violations(
        self, temp_dir: Path, partial_constraint_yaml: str
    ):
        """check_constraint() should pass for constraint with only some action fields."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "partial.yml"
        path.write_text(partial_constraint_yaml)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        assert violations == []

    def test_check_constraint_empty_actions_valid(
        self, temp_dir: Path, empty_actions_constraint_yaml: str
    ):
        """check_constraint() should pass for constraint with empty actions."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "empty_actions.yml"
        path.write_text(empty_actions_constraint_yaml)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        assert violations == []

    def test_check_constraint_detects_unknown_field(
        self, temp_dir: Path, invalid_constraint_yaml_unknown_field: str
    ):
        """check_constraint() should detect non-allowlisted field."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "invalid.yml"
        path.write_text(invalid_constraint_yaml_unknown_field)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        assert len(violations) > 0
        # Violation should mention the constraint ID
        assert any("invalid_constraint" in v for v in violations)
        # Violation should mention the forbidden field
        assert any("forbidden_custom_field" in v for v in violations)

    def test_check_constraint_detects_multiple_unknown_fields(
        self, temp_dir: Path, invalid_constraint_yaml_multiple_unknown_fields: str
    ):
        """check_constraint() should detect all non-allowlisted fields."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "multiple_invalid.yml"
        path.write_text(invalid_constraint_yaml_multiple_unknown_fields)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        # Should have violations for all unknown fields
        assert len(violations) >= 1
        violations_text = " ".join(violations)
        assert "unknown_field_1" in violations_text or "unknown_field" in violations_text.lower()

    def test_check_constraint_violations_contain_constraint_id(
        self, temp_dir: Path, invalid_constraint_yaml_unknown_field: str
    ):
        """Violations should contain the constraint ID for traceability."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "invalid.yml"
        path.write_text(invalid_constraint_yaml_unknown_field)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        assert len(violations) > 0
        # Each violation should mention the constraint ID
        for violation in violations:
            assert "invalid_constraint" in violation

    def test_check_constraint_violations_contain_field_name(
        self, temp_dir: Path, invalid_constraint_yaml_unknown_field: str
    ):
        """Violations should contain the offending field name."""
        from src.governance.lint.allowlist import AllowlistLint

        path = temp_dir / "invalid.yml"
        path.write_text(invalid_constraint_yaml_unknown_field)

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        assert len(violations) > 0
        # Violation should mention the specific field
        assert any("forbidden_custom_field" in v for v in violations)

    def test_check_constraint_with_custom_allowlist(self, temp_dir: Path):
        """check_constraint() should work with custom allowlist."""
        from src.governance.lint.allowlist import AllowlistLint

        # Constraint that would be valid with default allowlist
        yaml_content = """
id: custom_allowlist_test
title: Custom Allowlist Test
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  risk_budget_multiplier: 1.5
"""
        path = temp_dir / "custom.yml"
        path.write_text(yaml_content)

        # With restricted allowlist that doesn't include enable_strategy
        restricted_allowlist = {"risk_budget_multiplier", "pool_bias_multiplier"}
        lint = AllowlistLint(allowlist=restricted_allowlist)
        violations = lint.check_constraint(path)

        # enable_strategy should be a violation now
        assert len(violations) > 0
        assert any("enable_strategy" in v for v in violations)

    def test_check_constraint_file_not_found_raises(self):
        """check_constraint() should raise error for missing file."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()

        with pytest.raises(FileNotFoundError):
            lint.check_constraint(Path("/nonexistent/constraint.yml"))


class TestCheckDirectory:
    """Tests for check_directory() method."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def mixed_constraints_dir(self, temp_dir: Path) -> Path:
        """Create a directory with mixed valid/invalid constraint files."""
        # Valid constraint
        valid_yaml = """
id: valid_one
title: Valid One
applies_to: {}
activation: {}
actions:
  enable_strategy: true
"""
        (temp_dir / "valid_one.yml").write_text(valid_yaml)

        # Another valid constraint
        valid_yaml2 = """
id: valid_two
title: Valid Two
applies_to: {}
activation: {}
actions:
  risk_budget_multiplier: 1.5
  stop_mode: baseline
"""
        (temp_dir / "valid_two.yaml").write_text(valid_yaml2)

        # Invalid constraint
        invalid_yaml = """
id: invalid_one
title: Invalid One
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  unknown_bad_field: true
"""
        (temp_dir / "invalid_one.yml").write_text(invalid_yaml)

        # File starting with underscore (should be skipped)
        underscore_yaml = """
id: skipped_example
title: Skipped Example
applies_to: {}
activation: {}
actions:
  this_would_be_invalid: true
"""
        (temp_dir / "_example.yml").write_text(underscore_yaml)

        # Non-YAML file (should be skipped)
        (temp_dir / "readme.txt").write_text("This is not YAML")

        return temp_dir

    def test_check_directory_scans_all_yaml_files(self, mixed_constraints_dir: Path):
        """check_directory() should scan all YAML files in directory."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        result = lint.check_directory(mixed_constraints_dir)

        # Should have scanned 3 YAML files (valid_one.yml, valid_two.yaml, invalid_one.yml)
        # Should NOT have scanned _example.yml or readme.txt
        assert hasattr(result, "checked_files")
        assert result.checked_files == 3

    def test_check_directory_skips_underscore_files(self, mixed_constraints_dir: Path):
        """check_directory() should skip files starting with underscore."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        result = lint.check_directory(mixed_constraints_dir)

        # The _example.yml file has an invalid field, but should be skipped
        # Only invalid_one.yml should produce violations
        if result.violations:
            # Should NOT contain the skipped_example constraint
            violations_text = " ".join(result.violations)
            assert "skipped_example" not in violations_text

    def test_check_directory_returns_all_violations(self, temp_dir: Path):
        """check_directory() should return violations from all files."""
        # Create two invalid constraint files
        invalid1 = """
id: invalid_one
title: Invalid One
applies_to: {}
activation: {}
actions:
  bad_field_one: true
"""
        invalid2 = """
id: invalid_two
title: Invalid Two
applies_to: {}
activation: {}
actions:
  bad_field_two: false
"""
        (temp_dir / "invalid1.yml").write_text(invalid1)
        (temp_dir / "invalid2.yml").write_text(invalid2)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        result = lint.check_directory(temp_dir)

        # Should have violations from both files
        violations_text = " ".join(result.violations)
        assert "invalid_one" in violations_text or "bad_field_one" in violations_text
        assert "invalid_two" in violations_text or "bad_field_two" in violations_text

    def test_check_directory_empty_returns_no_violations(self, temp_dir: Path):
        """check_directory() should return empty violations for empty directory."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        result = lint.check_directory(temp_dir)

        assert result.passed is True
        assert result.violations == []
        assert result.checked_files == 0

    def test_check_directory_handles_both_yml_and_yaml(self, temp_dir: Path):
        """check_directory() should handle both .yml and .yaml extensions."""
        yml_content = """
id: yml_file
title: YML File
applies_to: {}
activation: {}
actions:
  enable_strategy: true
"""
        yaml_content = """
id: yaml_file
title: YAML File
applies_to: {}
activation: {}
actions:
  enable_strategy: true
"""
        (temp_dir / "test.yml").write_text(yml_content)
        (temp_dir / "test.yaml").write_text(yaml_content)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        result = lint.check_directory(temp_dir)

        assert result.checked_files == 2
        assert result.passed is True


class TestRunMethod:
    """Tests for run() method that returns LintResult."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_run_returns_lint_result(self, temp_dir: Path):
        """run() should return a LintResult object."""
        from src.governance.lint.allowlist import AllowlistLint
        from src.governance.lint.models import LintResult

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert isinstance(result, LintResult)

    def test_run_lint_result_has_passed_field(self, temp_dir: Path):
        """LintResult from run() should have passed field."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert hasattr(result, "passed")
        assert isinstance(result.passed, bool)

    def test_run_lint_result_has_violations_field(self, temp_dir: Path):
        """LintResult from run() should have violations field."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert hasattr(result, "violations")
        assert isinstance(result.violations, list)

    def test_run_lint_result_has_checked_files_field(self, temp_dir: Path):
        """LintResult from run() should have checked_files field."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert hasattr(result, "checked_files")
        assert isinstance(result.checked_files, int)

    def test_run_lint_result_has_checked_at_field(self, temp_dir: Path):
        """LintResult from run() should have checked_at timestamp field."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert hasattr(result, "checked_at")
        assert isinstance(result.checked_at, datetime)

    def test_run_passed_true_when_all_valid(self, temp_dir: Path):
        """run() should return passed=True when all constraints are valid."""
        valid_yaml = """
id: valid_constraint
title: Valid Constraint
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  risk_budget_multiplier: 1.5
"""
        (temp_dir / "valid.yml").write_text(valid_yaml)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert result.passed is True
        assert result.violations == []

    def test_run_passed_false_when_violations(self, temp_dir: Path):
        """run() should return passed=False when violations are found."""
        invalid_yaml = """
id: invalid_constraint
title: Invalid Constraint
applies_to: {}
activation: {}
actions:
  enable_strategy: true
  unknown_forbidden_field: true
"""
        (temp_dir / "invalid.yml").write_text(invalid_yaml)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert result.passed is False
        assert len(result.violations) > 0

    def test_run_passed_true_for_empty_directory(self, temp_dir: Path):
        """run() should return passed=True for empty directory (no violations)."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=temp_dir)
        result = lint.run()

        assert result.passed is True
        assert result.violations == []
        assert result.checked_files == 0


class TestLintResultModel:
    """Tests for LintResult Pydantic model."""

    def test_lint_result_model_importable(self):
        """LintResult model should be importable from lint.models."""
        from src.governance.lint.models import LintResult

        assert LintResult is not None

    def test_lint_result_required_fields(self):
        """LintResult should require passed and violations fields."""
        from src.governance.lint.models import LintResult

        # Should work with required fields
        result = LintResult(passed=True, violations=[])
        assert result.passed is True
        assert result.violations == []

    def test_lint_result_with_all_fields(self):
        """LintResult should accept all fields per OpenAPI spec."""
        from src.governance.lint.models import LintResult

        now = datetime.now()
        result = LintResult(
            passed=False,
            violations=["error 1", "error 2"],
            checked_files=5,
            checked_at=now,
        )

        assert result.passed is False
        assert result.violations == ["error 1", "error 2"]
        assert result.checked_files == 5
        assert result.checked_at == now

    def test_lint_result_checked_files_optional(self):
        """checked_files should be optional in LintResult."""
        from src.governance.lint.models import LintResult

        result = LintResult(passed=True, violations=[])
        # Should not raise, checked_files is optional
        assert hasattr(result, "checked_files")

    def test_lint_result_checked_at_optional(self):
        """checked_at should be optional in LintResult."""
        from src.governance.lint.models import LintResult

        result = LintResult(passed=True, violations=[])
        # Should not raise, checked_at is optional
        assert hasattr(result, "checked_at")

    def test_lint_result_violations_is_list_of_strings(self):
        """violations field should be a list of strings."""

        from src.governance.lint.models import LintResult

        # Valid: list of strings
        result = LintResult(passed=False, violations=["error1", "error2"])
        assert all(isinstance(v, str) for v in result.violations)


class TestAllowlistLintExports:
    """Tests for module exports."""

    def test_allowlist_lint_importable_from_allowlist_module(self):
        """AllowlistLint should be importable from src.governance.lint.allowlist."""
        from src.governance.lint.allowlist import AllowlistLint

        assert AllowlistLint is not None

    def test_default_allowlist_importable_from_allowlist_module(self):
        """DEFAULT_ALLOWLIST should be importable from src.governance.lint.allowlist."""
        from src.governance.lint.allowlist import DEFAULT_ALLOWLIST

        assert DEFAULT_ALLOWLIST is not None

    def test_lint_result_importable_from_models(self):
        """LintResult should be importable from src.governance.lint.models."""
        from src.governance.lint.models import LintResult

        assert LintResult is not None


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_check_constraint_with_null_actions(self, temp_dir: Path):
        """check_constraint() should handle constraint with null action values."""
        yaml_content = """
id: null_actions_constraint
title: Null Actions Constraint
applies_to: {}
activation: {}
actions:
  enable_strategy: null
  pool_bias_multiplier: null
  risk_budget_multiplier: null
"""
        path = temp_dir / "null_actions.yml"
        path.write_text(yaml_content)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        # null values for allowlisted fields should not be violations
        assert violations == []

    def test_check_constraint_malformed_yaml(self, temp_dir: Path):
        """check_constraint() should handle malformed YAML gracefully."""
        yaml_content = """
id: malformed
title: Malformed
applies_to: {}
activation: {}
actions:
  this is not valid yaml: [
"""
        path = temp_dir / "malformed.yml"
        path.write_text(yaml_content)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()

        # Should either raise an appropriate error or report violation
        # Not crash unexpectedly
        try:
            violations = lint.check_constraint(path)
            # If it returns violations, that's acceptable
            assert isinstance(violations, list)
        except Exception as e:
            # If it raises an error, should be a reasonable one
            assert "yaml" in str(e).lower() or "parse" in str(e).lower()

    def test_check_constraint_missing_actions_section(self, temp_dir: Path):
        """check_constraint() should handle constraint missing actions section."""
        yaml_content = """
id: no_actions
title: No Actions
applies_to: {}
activation: {}
"""
        path = temp_dir / "no_actions.yml"
        path.write_text(yaml_content)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()

        # Should handle missing actions gracefully
        # Either return no violations (nothing to check) or report appropriately
        try:
            violations = lint.check_constraint(path)
            # No actions = no violations for allowlist check
            assert violations == []
        except Exception as e:
            # Or could raise validation error
            assert "actions" in str(e).lower() or "required" in str(e).lower()

    def test_nonexistent_directory_raises_error(self):
        """run() should raise error for nonexistent directory."""
        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(constraints_dir=Path("/nonexistent/constraints/dir"))

        with pytest.raises(FileNotFoundError):
            lint.run()

    def test_allowlist_empty_set_rejects_all_fields(self, temp_dir: Path):
        """Empty allowlist should reject all action fields."""
        yaml_content = """
id: any_actions
title: Any Actions
applies_to: {}
activation: {}
actions:
  enable_strategy: true
"""
        path = temp_dir / "any_actions.yml"
        path.write_text(yaml_content)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint(allowlist=set())  # Empty allowlist
        violations = lint.check_constraint(path)

        # enable_strategy should be rejected since allowlist is empty
        assert len(violations) > 0
        assert any("enable_strategy" in v for v in violations)


class TestIntegrationWithConstraintModels:
    """Tests ensuring AllowlistLint works with actual constraint model fields."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_allowlist_covers_all_constraint_actions_fields(self):
        """DEFAULT_ALLOWLIST should cover exactly the ConstraintActions model fields."""
        from src.governance.lint.allowlist import DEFAULT_ALLOWLIST

        # These are the exact fields from ConstraintActions per OpenAPI spec
        expected_constraint_actions_fields = {
            "enable_strategy",
            "pool_bias_multiplier",
            "veto_downgrade",
            "risk_budget_multiplier",
            "holding_extension_days",
            "add_position_cap_multiplier",
            "stop_mode",
        }

        assert DEFAULT_ALLOWLIST == expected_constraint_actions_fields

    def test_check_real_constraint_structure(self, temp_dir: Path):
        """Test with a constraint that matches the real YAML structure."""
        # This matches the structure from test_constraint_loader.py fixtures
        yaml_content = """
id: momentum_long_constraint
title: Momentum Long Constraint
applies_to:
  symbols:
    - AAPL
    - MSFT
  strategies:
    - momentum_strategy
activation:
  requires_hypotheses_active:
    - momentum_persistence
  disabled_if_falsified: true
actions:
  enable_strategy: true
  pool_bias_multiplier: 1.5
  veto_downgrade: false
  risk_budget_multiplier: 2.0
  holding_extension_days: 5
  add_position_cap_multiplier: 1.2
  stop_mode: wide
guardrails:
  max_position_pct: 0.05
  max_gross_exposure_delta: 0.1
  max_drawdown_addon: 0.02
priority: 50
"""
        path = temp_dir / "real_constraint.yml"
        path.write_text(yaml_content)

        from src.governance.lint.allowlist import AllowlistLint

        lint = AllowlistLint()
        violations = lint.check_constraint(path)

        # This is a valid constraint using only allowlisted action fields
        assert violations == []
