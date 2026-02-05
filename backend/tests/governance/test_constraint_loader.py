"""Tests for constraint YAML loader.

TDD: Write tests FIRST, then implement loader to make them pass.

This module tests the ConstraintLoader class which:
1. Loads constraint YAML files from config/constraints/ directory
2. Parses and validates using Pydantic models
3. Enforces field validation (risk_budget_multiplier >= 1, pool_bias_multiplier > 0, etc.)
4. Skips files starting with underscore (e.g., _example.yml)
5. Validates linked_hypothesis activation requirements
"""

import tempfile
from pathlib import Path

import pytest


class TestConstraintLoader:
    """Tests for ConstraintLoader class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def valid_constraint_yaml(self) -> str:
        """Return a complete valid constraint YAML content."""
        return """
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

    @pytest.fixture
    def minimal_constraint_yaml(self) -> str:
        """Return a constraint YAML with only required fields."""
        return """
id: minimal_constraint
title: Minimal Constraint
applies_to: {}
activation: {}
actions: {}
"""

    @pytest.fixture
    def constraint_with_nullable_actions_yaml(self) -> str:
        """Return a constraint YAML with nullable action fields."""
        return """
id: nullable_actions_constraint
title: Nullable Actions Constraint
applies_to:
  symbols: []
activation:
  requires_hypotheses_active: []
  disabled_if_falsified: false
actions:
  enable_strategy: null
  pool_bias_multiplier: null
  risk_budget_multiplier: null
priority: 100
"""

    @pytest.fixture
    def constraint_invalid_id_yaml(self) -> str:
        """Return a constraint YAML with an invalid ID pattern."""
        return """
id: Invalid-ID-With-Dashes
title: Invalid ID Constraint
applies_to: {}
activation: {}
actions: {}
"""

    @pytest.fixture
    def constraint_missing_id_yaml(self) -> str:
        """Return a constraint YAML missing the required id field."""
        return """
title: No ID Constraint
applies_to: {}
activation: {}
actions: {}
"""

    @pytest.fixture
    def constraint_missing_title_yaml(self) -> str:
        """Return a constraint YAML missing the required title field."""
        return """
id: no_title_constraint
applies_to: {}
activation: {}
actions: {}
"""

    @pytest.fixture
    def constraint_missing_applies_to_yaml(self) -> str:
        """Return a constraint YAML missing the required applies_to field."""
        return """
id: no_applies_to
title: No Applies To Constraint
activation: {}
actions: {}
"""

    @pytest.fixture
    def constraint_missing_activation_yaml(self) -> str:
        """Return a constraint YAML missing the required activation field."""
        return """
id: no_activation
title: No Activation Constraint
applies_to: {}
actions: {}
"""

    @pytest.fixture
    def constraint_missing_actions_yaml(self) -> str:
        """Return a constraint YAML missing the required actions field."""
        return """
id: no_actions
title: No Actions Constraint
applies_to: {}
activation: {}
"""

    @pytest.fixture
    def constraint_invalid_risk_budget_multiplier_yaml(self) -> str:
        """Return a constraint YAML with risk_budget_multiplier < 1."""
        return """
id: invalid_risk_budget
title: Invalid Risk Budget Constraint
applies_to: {}
activation: {}
actions:
  risk_budget_multiplier: 0.5
"""

    @pytest.fixture
    def constraint_invalid_pool_bias_multiplier_yaml(self) -> str:
        """Return a constraint YAML with pool_bias_multiplier <= 0."""
        return """
id: invalid_pool_bias
title: Invalid Pool Bias Constraint
applies_to: {}
activation: {}
actions:
  pool_bias_multiplier: 0.0
"""

    @pytest.fixture
    def constraint_invalid_pool_bias_negative_yaml(self) -> str:
        """Return a constraint YAML with pool_bias_multiplier < 0."""
        return """
id: invalid_pool_bias_negative
title: Invalid Pool Bias Negative Constraint
applies_to: {}
activation: {}
actions:
  pool_bias_multiplier: -1.0
"""

    @pytest.fixture
    def constraint_invalid_add_position_cap_multiplier_yaml(self) -> str:
        """Return a constraint YAML with add_position_cap_multiplier <= 0."""
        return """
id: invalid_position_cap
title: Invalid Position Cap Constraint
applies_to: {}
activation: {}
actions:
  add_position_cap_multiplier: 0.0
"""

    @pytest.fixture
    def constraint_invalid_holding_extension_days_yaml(self) -> str:
        """Return a constraint YAML with holding_extension_days < 0."""
        return """
id: invalid_holding_days
title: Invalid Holding Days Constraint
applies_to: {}
activation: {}
actions:
  holding_extension_days: -5
"""

    @pytest.fixture
    def constraint_invalid_stop_mode_yaml(self) -> str:
        """Return a constraint YAML with invalid stop_mode enum."""
        return """
id: invalid_stop_mode
title: Invalid Stop Mode Constraint
applies_to: {}
activation: {}
actions:
  stop_mode: invalid_mode
"""

    @pytest.fixture
    def constraint_invalid_max_position_pct_too_high_yaml(self) -> str:
        """Return a constraint YAML with max_position_pct > 1."""
        return """
id: invalid_position_pct_high
title: Invalid Position Pct Too High Constraint
applies_to: {}
activation: {}
actions: {}
guardrails:
  max_position_pct: 1.5
"""

    @pytest.fixture
    def constraint_invalid_max_position_pct_negative_yaml(self) -> str:
        """Return a constraint YAML with max_position_pct < 0."""
        return """
id: invalid_position_pct_negative
title: Invalid Position Pct Negative Constraint
applies_to: {}
activation: {}
actions: {}
guardrails:
  max_position_pct: -0.1
"""

    @pytest.fixture
    def constraint_invalid_priority_yaml(self) -> str:
        """Return a constraint YAML with priority < 1."""
        return """
id: invalid_priority
title: Invalid Priority Constraint
applies_to: {}
activation: {}
actions: {}
priority: 0
"""

    @pytest.fixture
    def valid_constraint_file(self, temp_dir: Path, valid_constraint_yaml: str) -> Path:
        """Create a valid constraint YAML file."""
        path = temp_dir / "momentum_long_constraint.yml"
        path.write_text(valid_constraint_yaml)
        return path

    @pytest.fixture
    def multiple_constraint_files(
        self, temp_dir: Path, valid_constraint_yaml: str, minimal_constraint_yaml: str
    ) -> Path:
        """Create multiple constraint YAML files in a directory."""
        # Valid constraint files
        (temp_dir / "constraint_a.yml").write_text(valid_constraint_yaml)

        # Minimal valid file
        (temp_dir / "constraint_b.yml").write_text(minimal_constraint_yaml)

        # Second valid with .yaml extension
        second_yaml = """
id: value_reversion_constraint
title: Value Reversion Constraint
applies_to:
  symbols: []
  strategies:
    - value_strategy
activation:
  requires_hypotheses_active:
    - value_reversion
  disabled_if_falsified: true
actions:
  risk_budget_multiplier: 1.5
priority: 75
"""
        (temp_dir / "constraint_c.yaml").write_text(second_yaml)

        # Files that should be skipped
        (temp_dir / "_example.yml").write_text(valid_constraint_yaml)
        (temp_dir / "_template.yaml").write_text(valid_constraint_yaml)
        (temp_dir / "not_yaml.txt").write_text("this is not yaml")

        return temp_dir

    # =========================================================================
    # Test: Loader Initialization
    # =========================================================================

    def test_constraint_loader_initialization(self):
        """ConstraintLoader should initialize with default constraints directory."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()

        assert loader is not None
        assert hasattr(loader, "default_constraints_dir")
        assert "constraints" in str(loader.default_constraints_dir).lower()

    def test_constraint_loader_custom_directory(self, temp_dir: Path):
        """ConstraintLoader should accept custom constraints directory."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader(constraints_dir=temp_dir)

        assert loader.default_constraints_dir == temp_dir

    # =========================================================================
    # Test: Loading Single Constraint
    # =========================================================================

    def test_load_valid_constraint_from_yaml(self, valid_constraint_file: Path):
        """load_constraint() should successfully parse a complete valid constraint."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()
        constraint = loader.load_constraint(valid_constraint_file)

        # Verify the constraint was loaded correctly
        assert constraint.id == "momentum_long_constraint"
        assert constraint.title == "Momentum Long Constraint"
        assert constraint.priority == 50

        # Verify applies_to
        assert "AAPL" in constraint.applies_to.symbols
        assert "MSFT" in constraint.applies_to.symbols
        assert "momentum_strategy" in constraint.applies_to.strategies

        # Verify activation
        assert "momentum_persistence" in constraint.activation.requires_hypotheses_active
        assert constraint.activation.disabled_if_falsified is True

        # Verify actions
        assert constraint.actions.enable_strategy is True
        assert constraint.actions.pool_bias_multiplier == 1.5
        assert constraint.actions.veto_downgrade is False
        assert constraint.actions.risk_budget_multiplier == 2.0
        assert constraint.actions.holding_extension_days == 5
        assert constraint.actions.add_position_cap_multiplier == 1.2
        assert constraint.actions.stop_mode.value == "wide"

        # Verify guardrails
        assert constraint.guardrails.max_position_pct == 0.05
        assert constraint.guardrails.max_gross_exposure_delta == 0.1
        assert constraint.guardrails.max_drawdown_addon == 0.02

    def test_load_constraint_with_minimal_fields(
        self, temp_dir: Path, minimal_constraint_yaml: str
    ):
        """load_constraint() should work with only required fields."""
        from src.governance.constraints.loader import ConstraintLoader

        path = temp_dir / "minimal.yml"
        path.write_text(minimal_constraint_yaml)

        loader = ConstraintLoader()
        constraint = loader.load_constraint(path)

        assert constraint.id == "minimal_constraint"
        assert constraint.title == "Minimal Constraint"
        assert constraint.priority == 100  # Default value

    def test_load_constraint_with_nullable_actions(
        self, temp_dir: Path, constraint_with_nullable_actions_yaml: str
    ):
        """load_constraint() should handle nullable action fields."""
        from src.governance.constraints.loader import ConstraintLoader

        path = temp_dir / "nullable.yml"
        path.write_text(constraint_with_nullable_actions_yaml)

        loader = ConstraintLoader()
        constraint = loader.load_constraint(path)

        assert constraint.actions.enable_strategy is None
        assert constraint.actions.pool_bias_multiplier is None
        assert constraint.actions.risk_budget_multiplier is None

    # =========================================================================
    # Test: Validation - Invalid ID Pattern
    # =========================================================================

    def test_load_constraint_rejects_invalid_id_pattern(
        self, temp_dir: Path, constraint_invalid_id_yaml: str
    ):
        """load_constraint() should reject constraints with invalid ID pattern.

        ID must match ^[a-z0-9_]+$ (lowercase alphanumeric with underscores).
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_id.yml"
        path.write_text(constraint_invalid_id_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "id" in error_message or "pattern" in error_message

    # =========================================================================
    # Test: Validation - Missing Required Fields
    # =========================================================================

    def test_load_constraint_rejects_missing_id(
        self, temp_dir: Path, constraint_missing_id_yaml: str
    ):
        """load_constraint() should reject constraints missing the id field."""
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "missing_id.yml"
        path.write_text(constraint_missing_id_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "id" in error_message or "required" in error_message

    def test_load_constraint_rejects_missing_title(
        self, temp_dir: Path, constraint_missing_title_yaml: str
    ):
        """load_constraint() should reject constraints missing the title field."""
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "missing_title.yml"
        path.write_text(constraint_missing_title_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "title" in error_message or "required" in error_message

    def test_load_constraint_rejects_missing_applies_to(
        self, temp_dir: Path, constraint_missing_applies_to_yaml: str
    ):
        """load_constraint() should reject constraints missing the applies_to field."""
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "missing_applies_to.yml"
        path.write_text(constraint_missing_applies_to_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "applies_to" in error_message or "required" in error_message

    def test_load_constraint_rejects_missing_activation(
        self, temp_dir: Path, constraint_missing_activation_yaml: str
    ):
        """load_constraint() should reject constraints missing the activation field."""
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "missing_activation.yml"
        path.write_text(constraint_missing_activation_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "activation" in error_message or "required" in error_message

    def test_load_constraint_rejects_missing_actions(
        self, temp_dir: Path, constraint_missing_actions_yaml: str
    ):
        """load_constraint() should reject constraints missing the actions field."""
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "missing_actions.yml"
        path.write_text(constraint_missing_actions_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "actions" in error_message or "required" in error_message

    # =========================================================================
    # Test: Validation - ConstraintActions Field Validation
    # =========================================================================

    def test_load_constraint_rejects_risk_budget_multiplier_less_than_1(
        self, temp_dir: Path, constraint_invalid_risk_budget_multiplier_yaml: str
    ):
        """load_constraint() should reject risk_budget_multiplier < 1.

        risk_budget_multiplier must be >= 1 per OpenAPI spec.
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_risk_budget.yml"
        path.write_text(constraint_invalid_risk_budget_multiplier_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "risk_budget_multiplier" in error_message
            or "greater" in error_message
            or "minimum" in error_message
        )

    def test_load_constraint_rejects_pool_bias_multiplier_zero(
        self, temp_dir: Path, constraint_invalid_pool_bias_multiplier_yaml: str
    ):
        """load_constraint() should reject pool_bias_multiplier <= 0.

        pool_bias_multiplier must be > 0 per OpenAPI spec (exclusiveMinimum: 0).
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_pool_bias.yml"
        path.write_text(constraint_invalid_pool_bias_multiplier_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "pool_bias_multiplier" in error_message
            or "greater" in error_message
            or "exclusive" in error_message
        )

    def test_load_constraint_rejects_pool_bias_multiplier_negative(
        self, temp_dir: Path, constraint_invalid_pool_bias_negative_yaml: str
    ):
        """load_constraint() should reject pool_bias_multiplier < 0."""
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_pool_bias_negative.yml"
        path.write_text(constraint_invalid_pool_bias_negative_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "pool_bias_multiplier" in error_message
            or "greater" in error_message
            or "exclusive" in error_message
        )

    def test_load_constraint_rejects_add_position_cap_multiplier_zero(
        self, temp_dir: Path, constraint_invalid_add_position_cap_multiplier_yaml: str
    ):
        """load_constraint() should reject add_position_cap_multiplier <= 0.

        add_position_cap_multiplier must be > 0 per OpenAPI spec (exclusiveMinimum: 0).
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_position_cap.yml"
        path.write_text(constraint_invalid_add_position_cap_multiplier_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "add_position_cap_multiplier" in error_message
            or "greater" in error_message
            or "exclusive" in error_message
        )

    def test_load_constraint_rejects_negative_holding_extension_days(
        self, temp_dir: Path, constraint_invalid_holding_extension_days_yaml: str
    ):
        """load_constraint() should reject holding_extension_days < 0.

        holding_extension_days must be >= 0 per OpenAPI spec.
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_holding_days.yml"
        path.write_text(constraint_invalid_holding_extension_days_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "holding_extension_days" in error_message
            or "greater" in error_message
            or "minimum" in error_message
        )

    def test_load_constraint_rejects_invalid_stop_mode(
        self, temp_dir: Path, constraint_invalid_stop_mode_yaml: str
    ):
        """load_constraint() should reject invalid stop_mode enum values.

        stop_mode must be one of: baseline, wide, fundamental_guarded.
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_stop_mode.yml"
        path.write_text(constraint_invalid_stop_mode_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert "stop_mode" in error_message

    # =========================================================================
    # Test: Validation - ConstraintGuardrails Field Validation
    # =========================================================================

    def test_load_constraint_rejects_max_position_pct_greater_than_1(
        self, temp_dir: Path, constraint_invalid_max_position_pct_too_high_yaml: str
    ):
        """load_constraint() should reject max_position_pct > 1.

        max_position_pct must be between 0 and 1 per OpenAPI spec.
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_position_pct_high.yml"
        path.write_text(constraint_invalid_max_position_pct_too_high_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "max_position_pct" in error_message
            or "maximum" in error_message
            or "less" in error_message
        )

    def test_load_constraint_rejects_max_position_pct_negative(
        self, temp_dir: Path, constraint_invalid_max_position_pct_negative_yaml: str
    ):
        """load_constraint() should reject max_position_pct < 0.

        max_position_pct must be between 0 and 1 per OpenAPI spec.
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_position_pct_negative.yml"
        path.write_text(constraint_invalid_max_position_pct_negative_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "max_position_pct" in error_message
            or "minimum" in error_message
            or "greater" in error_message
        )

    def test_load_constraint_rejects_invalid_priority(
        self, temp_dir: Path, constraint_invalid_priority_yaml: str
    ):
        """load_constraint() should reject priority < 1.

        priority must be >= 1 per OpenAPI spec.
        """
        from src.governance.constraints.loader import ConstraintLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_priority.yml"
        path.write_text(constraint_invalid_priority_yaml)

        loader = ConstraintLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_constraint(path)

        error_message = str(exc_info.value).lower()
        assert (
            "priority" in error_message or "minimum" in error_message or "greater" in error_message
        )

    # =========================================================================
    # Test: Loading All Constraints from Directory
    # =========================================================================

    def test_load_all_constraints_from_directory(self, multiple_constraint_files: Path):
        """load_all_constraints() should load all YAML files from directory.

        Should load both .yml and .yaml files.
        """
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()
        constraints = loader.load_all_constraints(multiple_constraint_files)

        # Should have loaded 3 valid constraint files (a.yml, b.yml, c.yaml)
        # Should NOT have loaded _example.yml, _template.yaml, or not_yaml.txt
        assert len(constraints) == 3

        # Verify we got the expected constraints
        ids = {c.id for c in constraints}
        assert "momentum_long_constraint" in ids
        assert "minimal_constraint" in ids
        assert "value_reversion_constraint" in ids

    def test_load_constraints_skips_files_starting_with_underscore(
        self, multiple_constraint_files: Path
    ):
        """load_all_constraints() should skip files starting with underscore.

        Files like _example.yml and _template.yaml should be ignored.
        """
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()
        constraints = loader.load_all_constraints(multiple_constraint_files)

        # Verify no underscore-prefixed files were loaded
        ids = {c.id for c in constraints}
        # momentum_long_constraint appears in _example.yml, but that should be skipped
        # We have 3 constraints total, and only one has id=momentum_long_constraint
        # which comes from constraint_a.yml, not _example.yml
        assert len([c for c in constraints if c.id == "momentum_long_constraint"]) == 1

    def test_load_constraints_empty_directory(self, temp_dir: Path):
        """load_all_constraints() should return empty list for empty directory."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()
        constraints = loader.load_all_constraints(temp_dir)

        assert constraints == []

    def test_load_constraints_nonexistent_directory(self):
        """load_all_constraints() should raise error for nonexistent directory."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_all_constraints(Path("/nonexistent/constraints/dir"))

    def test_load_constraint_file_not_found(self):
        """load_constraint() should raise FileNotFoundError for missing file."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_constraint(Path("/nonexistent/constraint.yml"))


class TestConstraintLoaderWithDefaultPath:
    """Tests for ConstraintLoader with default config/constraints/ path."""

    def test_default_constraints_path_exists(self):
        """Loader should have a default path to config/constraints/."""
        from src.governance.constraints.loader import ConstraintLoader

        loader = ConstraintLoader()

        # The loader should have a default path configured
        assert hasattr(loader, "default_constraints_dir")
        assert "constraints" in str(loader.default_constraints_dir).lower()


class TestConstraintLoaderValidation:
    """Tests for constraint validation methods."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_validate_constraint_returns_empty_for_valid(self, temp_dir: Path):
        """validate_constraint() should return empty list for valid file."""
        from src.governance.constraints.loader import ConstraintLoader

        yaml_content = """
id: valid_constraint
title: Valid Constraint
applies_to:
  symbols: []
activation:
  requires_hypotheses_active: []
actions:
  risk_budget_multiplier: 1.5
priority: 100
"""
        path = temp_dir / "valid.yml"
        path.write_text(yaml_content)

        loader = ConstraintLoader()
        errors = loader.validate_constraint(path)

        assert errors == []

    def test_validate_constraint_returns_errors_for_invalid(self, temp_dir: Path):
        """validate_constraint() should return list of validation errors."""
        from src.governance.constraints.loader import ConstraintLoader

        yaml_content = """
id: Invalid-ID
title: Invalid Constraint
# Missing required fields: applies_to, activation, actions
"""
        path = temp_dir / "invalid.yml"
        path.write_text(yaml_content)

        loader = ConstraintLoader()
        errors = loader.validate_constraint(path)

        assert len(errors) > 0
        # Should mention missing fields or invalid ID
        error_text = " ".join(errors).lower()
        assert (
            "id" in error_text
            or "applies_to" in error_text
            or "activation" in error_text
            or "actions" in error_text
        )


class TestConstraintLoaderExports:
    """Test that all required types are exported."""

    def test_constraint_loader_importable(self):
        """ConstraintLoader should be importable from the constraints module."""
        from src.governance.constraints.loader import ConstraintLoader

        assert ConstraintLoader is not None

    def test_constraint_loader_in_module_exports(self):
        """ConstraintLoader should eventually be exported from constraints __init__."""
        # This test will pass once the loader is implemented and added to __init__.py
        try:
            from src.governance.constraints import ConstraintLoader

            assert ConstraintLoader is not None
        except ImportError:
            # Expected to fail until loader is implemented
            pytest.skip("ConstraintLoader not yet exported from constraints module")


class TestConstraintModels:
    """Tests for Constraint Pydantic models."""

    def test_constraint_model_importable(self):
        """Constraint model should be importable from constraints.models."""
        from src.governance.constraints.models import Constraint

        assert Constraint is not None

    def test_constraint_applies_to_model_importable(self):
        """ConstraintAppliesTo model should be importable."""
        from src.governance.constraints.models import ConstraintAppliesTo

        assert ConstraintAppliesTo is not None

    def test_constraint_activation_model_importable(self):
        """ConstraintActivation model should be importable."""
        from src.governance.constraints.models import ConstraintActivation

        assert ConstraintActivation is not None

    def test_constraint_actions_model_importable(self):
        """ConstraintActions model should be importable."""
        from src.governance.constraints.models import ConstraintActions

        assert ConstraintActions is not None

    def test_constraint_guardrails_model_importable(self):
        """ConstraintGuardrails model should be importable."""
        from src.governance.constraints.models import ConstraintGuardrails

        assert ConstraintGuardrails is not None

    def test_constraint_id_pattern_validation(self):
        """Constraint id must match ^[a-z0-9_]+$ pattern."""
        from pydantic import ValidationError
        from src.governance.constraints.models import Constraint

        # Valid IDs
        valid_ids = ["test_constraint", "constraint123", "a_b_c_1_2_3"]
        for valid_id in valid_ids:
            constraint = Constraint(
                id=valid_id,
                title="Test",
                applies_to={},
                activation={},
                actions={},
            )
            assert constraint.id == valid_id

        # Invalid IDs should raise ValidationError
        invalid_ids = ["Invalid-ID", "UPPERCASE", "spaces not allowed", "special@char"]
        for invalid_id in invalid_ids:
            with pytest.raises(ValidationError):
                Constraint(
                    id=invalid_id,
                    title="Test",
                    applies_to={},
                    activation={},
                    actions={},
                )

    def test_constraint_actions_risk_budget_multiplier_validation(self):
        """risk_budget_multiplier must be >= 1."""
        from pydantic import ValidationError
        from src.governance.constraints.models import ConstraintActions

        # Valid: >= 1
        actions = ConstraintActions(risk_budget_multiplier=1.0)
        assert actions.risk_budget_multiplier == 1.0

        actions = ConstraintActions(risk_budget_multiplier=2.5)
        assert actions.risk_budget_multiplier == 2.5

        # Invalid: < 1
        with pytest.raises(ValidationError):
            ConstraintActions(risk_budget_multiplier=0.5)

    def test_constraint_actions_pool_bias_multiplier_validation(self):
        """pool_bias_multiplier must be > 0 (exclusive minimum)."""
        from pydantic import ValidationError
        from src.governance.constraints.models import ConstraintActions

        # Valid: > 0
        actions = ConstraintActions(pool_bias_multiplier=0.1)
        assert actions.pool_bias_multiplier == 0.1

        actions = ConstraintActions(pool_bias_multiplier=1.5)
        assert actions.pool_bias_multiplier == 1.5

        # Invalid: <= 0
        with pytest.raises(ValidationError):
            ConstraintActions(pool_bias_multiplier=0.0)

        with pytest.raises(ValidationError):
            ConstraintActions(pool_bias_multiplier=-1.0)

    def test_constraint_actions_add_position_cap_multiplier_validation(self):
        """add_position_cap_multiplier must be > 0 (exclusive minimum)."""
        from pydantic import ValidationError
        from src.governance.constraints.models import ConstraintActions

        # Valid: > 0
        actions = ConstraintActions(add_position_cap_multiplier=0.5)
        assert actions.add_position_cap_multiplier == 0.5

        # Invalid: <= 0
        with pytest.raises(ValidationError):
            ConstraintActions(add_position_cap_multiplier=0.0)

        with pytest.raises(ValidationError):
            ConstraintActions(add_position_cap_multiplier=-0.5)

    def test_constraint_actions_holding_extension_days_validation(self):
        """holding_extension_days must be >= 0."""
        from pydantic import ValidationError
        from src.governance.constraints.models import ConstraintActions

        # Valid: >= 0
        actions = ConstraintActions(holding_extension_days=0)
        assert actions.holding_extension_days == 0

        actions = ConstraintActions(holding_extension_days=10)
        assert actions.holding_extension_days == 10

        # Invalid: < 0
        with pytest.raises(ValidationError):
            ConstraintActions(holding_extension_days=-1)

    def test_constraint_guardrails_max_position_pct_validation(self):
        """max_position_pct must be between 0 and 1 (inclusive)."""
        from pydantic import ValidationError
        from src.governance.constraints.models import ConstraintGuardrails

        # Valid: 0 <= value <= 1
        guardrails = ConstraintGuardrails(max_position_pct=0.0)
        assert guardrails.max_position_pct == 0.0

        guardrails = ConstraintGuardrails(max_position_pct=0.5)
        assert guardrails.max_position_pct == 0.5

        guardrails = ConstraintGuardrails(max_position_pct=1.0)
        assert guardrails.max_position_pct == 1.0

        # Invalid: < 0 or > 1
        with pytest.raises(ValidationError):
            ConstraintGuardrails(max_position_pct=-0.1)

        with pytest.raises(ValidationError):
            ConstraintGuardrails(max_position_pct=1.5)

    def test_constraint_priority_validation(self):
        """priority must be >= 1."""
        from pydantic import ValidationError
        from src.governance.constraints.models import Constraint

        # Valid: >= 1
        constraint = Constraint(
            id="test",
            title="Test",
            applies_to={},
            activation={},
            actions={},
            priority=1,
        )
        assert constraint.priority == 1

        constraint = Constraint(
            id="test",
            title="Test",
            applies_to={},
            activation={},
            actions={},
            priority=100,
        )
        assert constraint.priority == 100

        # Invalid: < 1
        with pytest.raises(ValidationError):
            Constraint(
                id="test",
                title="Test",
                applies_to={},
                activation={},
                actions={},
                priority=0,
            )


class TestConstraintLinkedHypotheses:
    """Tests for constraint-hypothesis linking."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_constraint_with_requires_hypotheses_active(self, temp_dir: Path):
        """Constraint activation.requires_hypotheses_active should link to hypotheses."""
        from src.governance.constraints.loader import ConstraintLoader

        yaml_content = """
id: linked_constraint
title: Linked Constraint
applies_to:
  strategies:
    - momentum_strategy
activation:
  requires_hypotheses_active:
    - momentum_hypothesis
    - value_hypothesis
  disabled_if_falsified: true
actions:
  enable_strategy: true
"""
        path = temp_dir / "linked.yml"
        path.write_text(yaml_content)

        loader = ConstraintLoader()
        constraint = loader.load_constraint(path)

        assert len(constraint.activation.requires_hypotheses_active) == 2
        assert "momentum_hypothesis" in constraint.activation.requires_hypotheses_active
        assert "value_hypothesis" in constraint.activation.requires_hypotheses_active
        assert constraint.activation.disabled_if_falsified is True

    def test_constraint_disabled_if_falsified_defaults_true(self, temp_dir: Path):
        """activation.disabled_if_falsified should default to True."""
        from src.governance.constraints.loader import ConstraintLoader

        yaml_content = """
id: default_falsified
title: Default Falsified Constraint
applies_to: {}
activation:
  requires_hypotheses_active:
    - some_hypothesis
actions: {}
"""
        path = temp_dir / "default_falsified.yml"
        path.write_text(yaml_content)

        loader = ConstraintLoader()
        constraint = loader.load_constraint(path)

        # Default should be True per OpenAPI spec
        assert constraint.activation.disabled_if_falsified is True

    def test_constraint_with_disabled_if_falsified_false(self, temp_dir: Path):
        """activation.disabled_if_falsified can be explicitly set to False."""
        from src.governance.constraints.loader import ConstraintLoader

        yaml_content = """
id: explicit_not_falsified
title: Explicit Not Falsified Constraint
applies_to: {}
activation:
  requires_hypotheses_active: []
  disabled_if_falsified: false
actions: {}
"""
        path = temp_dir / "explicit_not_falsified.yml"
        path.write_text(yaml_content)

        loader = ConstraintLoader()
        constraint = loader.load_constraint(path)

        assert constraint.activation.disabled_if_falsified is False
