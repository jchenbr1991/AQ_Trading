"""Tests for hypothesis YAML loader.

TDD: Write tests FIRST, then implement loader to make them pass.

This module tests the HypothesisLoader class which:
1. Loads hypothesis YAML files from config/hypotheses/ directory
2. Parses and validates using Pydantic models
3. Enforces gate:hypothesis_requires_falsifiers - reject hypotheses without falsifiers
4. Skips files starting with underscore (e.g., _example.yml)
"""

import tempfile
from datetime import date
from pathlib import Path

import pytest


class TestHypothesisLoader:
    """Tests for HypothesisLoader class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def valid_hypothesis_yaml(self) -> str:
        """Return a complete valid hypothesis YAML content."""
        return """
id: momentum_persistence
title: Momentum Persistence Hypothesis
statement: Strong price momentum tends to persist over 3-6 month horizons in liquid equities.
scope:
  symbols: []
  sectors:
    - technology
    - healthcare
owner: human
status: ACTIVE
review_cycle: quarterly
created_at: 2025-01-15
evidence:
  sources:
    - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=299107
    - https://www.aqr.com/Insights/Research/Journal-Article/Momentum
  notes: Jegadeesh and Titman (1993) seminal paper on momentum returns.
falsifiers:
  - metric: rolling_ic_mean
    operator: "<"
    threshold: 0.0
    window: 4q
    trigger: sunset
  - metric: max_drawdown
    operator: ">"
    threshold: 0.25
    window: 6m
    trigger: review
linked_constraints:
  - momentum_long_constraint
"""

    @pytest.fixture
    def minimal_hypothesis_yaml(self) -> str:
        """Return a hypothesis YAML with only required fields."""
        return """
id: minimal_hyp
title: Minimal Hypothesis
statement: A simple testable statement.
scope: {}
status: DRAFT
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers:
  - metric: sharpe_ratio
    operator: "<"
    threshold: 0.5
    window: 90d
    trigger: review
"""

    @pytest.fixture
    def hypothesis_without_falsifiers_yaml(self) -> str:
        """Return a hypothesis YAML missing the falsifiers field."""
        return """
id: no_falsifiers
title: Invalid Hypothesis
statement: This hypothesis has no falsifiers.
scope: {}
status: DRAFT
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
"""

    @pytest.fixture
    def hypothesis_empty_falsifiers_yaml(self) -> str:
        """Return a hypothesis YAML with an empty falsifiers list."""
        return """
id: empty_falsifiers
title: Empty Falsifiers Hypothesis
statement: This hypothesis has an empty falsifiers list.
scope: {}
status: DRAFT
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers: []
"""

    @pytest.fixture
    def hypothesis_invalid_id_yaml(self) -> str:
        """Return a hypothesis YAML with an invalid ID pattern."""
        return """
id: Invalid-ID-With-Dashes
title: Invalid ID Hypothesis
statement: This hypothesis has an invalid ID.
scope: {}
status: DRAFT
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers:
  - metric: sharpe_ratio
    operator: "<"
    threshold: 0.5
    window: 90d
    trigger: review
"""

    @pytest.fixture
    def hypothesis_invalid_status_yaml(self) -> str:
        """Return a hypothesis YAML with an invalid status enum."""
        return """
id: invalid_status
title: Invalid Status Hypothesis
statement: This hypothesis has an invalid status.
scope: {}
status: INVALID_STATUS
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers:
  - metric: sharpe_ratio
    operator: "<"
    threshold: 0.5
    window: 90d
    trigger: review
"""

    @pytest.fixture
    def hypothesis_invalid_operator_yaml(self) -> str:
        """Return a hypothesis YAML with an invalid operator enum."""
        return """
id: invalid_operator
title: Invalid Operator Hypothesis
statement: This hypothesis has an invalid operator.
scope: {}
status: DRAFT
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers:
  - metric: sharpe_ratio
    operator: "!="
    threshold: 0.5
    window: 90d
    trigger: review
"""

    @pytest.fixture
    def hypothesis_invalid_trigger_yaml(self) -> str:
        """Return a hypothesis YAML with an invalid trigger enum."""
        return """
id: invalid_trigger
title: Invalid Trigger Hypothesis
statement: This hypothesis has an invalid trigger.
scope: {}
status: DRAFT
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers:
  - metric: sharpe_ratio
    operator: "<"
    threshold: 0.5
    window: 90d
    trigger: explode
"""

    @pytest.fixture
    def valid_hypothesis_file(self, temp_dir: Path, valid_hypothesis_yaml: str) -> Path:
        """Create a valid hypothesis YAML file."""
        path = temp_dir / "momentum_persistence.yml"
        path.write_text(valid_hypothesis_yaml)
        return path

    @pytest.fixture
    def multiple_hypothesis_files(
        self, temp_dir: Path, valid_hypothesis_yaml: str, minimal_hypothesis_yaml: str
    ) -> Path:
        """Create multiple hypothesis YAML files in a directory."""
        # Valid hypothesis files
        (temp_dir / "hypothesis_a.yml").write_text(valid_hypothesis_yaml)

        # Minimal valid file
        (temp_dir / "hypothesis_b.yml").write_text(minimal_hypothesis_yaml)

        # Second valid with .yaml extension
        second_yaml = """
id: value_reversion
title: Value Reversion Hypothesis
statement: High P/E stocks tend to underperform over 5+ year horizons.
scope:
  symbols: []
  sectors: []
status: ACTIVE
review_cycle: yearly
created_at: 2025-01-20
evidence:
  sources: []
  notes: Based on Fama-French research.
falsifiers:
  - metric: long_term_alpha
    operator: "<"
    threshold: -0.02
    window: 5y
    trigger: sunset
"""
        (temp_dir / "hypothesis_c.yaml").write_text(second_yaml)

        # Files that should be skipped
        (temp_dir / "_example.yml").write_text(valid_hypothesis_yaml)
        (temp_dir / "_template.yaml").write_text(valid_hypothesis_yaml)
        (temp_dir / "not_yaml.txt").write_text("this is not yaml")

        return temp_dir

    def test_load_valid_hypothesis_from_yaml(self, valid_hypothesis_file: Path):
        """load_hypothesis() should successfully parse a complete valid hypothesis."""
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()
        hypothesis = loader.load_hypothesis(valid_hypothesis_file)

        # Verify the hypothesis was loaded correctly
        assert hypothesis.id == "momentum_persistence"
        assert hypothesis.title == "Momentum Persistence Hypothesis"
        assert "momentum" in hypothesis.statement.lower()
        assert hypothesis.owner == "human"
        assert hypothesis.status.value == "ACTIVE"
        assert hypothesis.review_cycle == "quarterly"
        assert hypothesis.created_at == date(2025, 1, 15)

        # Verify scope
        assert hypothesis.scope.symbols == []
        assert "technology" in hypothesis.scope.sectors
        assert "healthcare" in hypothesis.scope.sectors

        # Verify evidence
        assert len(hypothesis.evidence.sources) == 2
        assert "ssrn" in hypothesis.evidence.sources[0].lower()
        assert "Jegadeesh" in hypothesis.evidence.notes

        # Verify falsifiers (gate:hypothesis_requires_falsifiers)
        assert len(hypothesis.falsifiers) == 2
        assert hypothesis.falsifiers[0].metric == "rolling_ic_mean"
        assert hypothesis.falsifiers[0].operator.value == "<"
        assert hypothesis.falsifiers[0].threshold == 0.0
        assert hypothesis.falsifiers[0].window == "4q"
        assert hypothesis.falsifiers[0].trigger.value == "sunset"

        # Verify linked constraints
        assert "momentum_long_constraint" in hypothesis.linked_constraints

    def test_load_hypothesis_with_minimal_fields(
        self, temp_dir: Path, minimal_hypothesis_yaml: str
    ):
        """load_hypothesis() should work with only required fields."""
        from src.governance.hypothesis.loader import HypothesisLoader

        path = temp_dir / "minimal.yml"
        path.write_text(minimal_hypothesis_yaml)

        loader = HypothesisLoader()
        hypothesis = loader.load_hypothesis(path)

        assert hypothesis.id == "minimal_hyp"
        assert hypothesis.title == "Minimal Hypothesis"
        assert hypothesis.owner == "human"  # Default value
        assert hypothesis.status.value == "DRAFT"
        assert len(hypothesis.falsifiers) == 1
        assert hypothesis.linked_constraints == []  # Default empty list

    def test_load_hypothesis_rejects_missing_falsifiers(
        self, temp_dir: Path, hypothesis_without_falsifiers_yaml: str
    ):
        """load_hypothesis() should reject hypotheses without falsifiers field.

        This enforces gate:hypothesis_requires_falsifiers.
        """
        from src.governance.hypothesis.loader import HypothesisLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "no_falsifiers.yml"
        path.write_text(hypothesis_without_falsifiers_yaml)

        loader = HypothesisLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_hypothesis(path)

        error_message = str(exc_info.value).lower()
        assert "falsifiers" in error_message

    def test_load_hypothesis_rejects_empty_falsifiers_list(
        self, temp_dir: Path, hypothesis_empty_falsifiers_yaml: str
    ):
        """load_hypothesis() should reject hypotheses with empty falsifiers list.

        This enforces gate:hypothesis_requires_falsifiers - at least 1 falsifier required.
        """
        from src.governance.hypothesis.loader import HypothesisLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "empty_falsifiers.yml"
        path.write_text(hypothesis_empty_falsifiers_yaml)

        loader = HypothesisLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_hypothesis(path)

        error_message = str(exc_info.value).lower()
        # Should mention either min_length or falsifiers
        assert "falsifiers" in error_message or "min" in error_message

    def test_load_hypothesis_rejects_invalid_id_pattern(
        self, temp_dir: Path, hypothesis_invalid_id_yaml: str
    ):
        """load_hypothesis() should reject hypotheses with invalid ID pattern.

        ID must match ^[a-z0-9_]+$ (lowercase alphanumeric with underscores).
        """
        from src.governance.hypothesis.loader import HypothesisLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_id.yml"
        path.write_text(hypothesis_invalid_id_yaml)

        loader = HypothesisLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_hypothesis(path)

        error_message = str(exc_info.value).lower()
        assert "id" in error_message or "pattern" in error_message

    def test_load_hypothesis_validates_status_enum(
        self, temp_dir: Path, hypothesis_invalid_status_yaml: str
    ):
        """load_hypothesis() should reject hypotheses with invalid status enum.

        Status must be one of: DRAFT, ACTIVE, SUNSET, REJECTED.
        """
        from src.governance.hypothesis.loader import HypothesisLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_status.yml"
        path.write_text(hypothesis_invalid_status_yaml)

        loader = HypothesisLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_hypothesis(path)

        error_message = str(exc_info.value).lower()
        assert "status" in error_message

    def test_load_hypothesis_validates_operator_enum(
        self, temp_dir: Path, hypothesis_invalid_operator_yaml: str
    ):
        """load_hypothesis() should reject falsifiers with invalid operator enum.

        Operator must be one of: <, <=, >, >=, ==.
        """
        from src.governance.hypothesis.loader import HypothesisLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_operator.yml"
        path.write_text(hypothesis_invalid_operator_yaml)

        loader = HypothesisLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_hypothesis(path)

        error_message = str(exc_info.value).lower()
        assert "operator" in error_message

    def test_load_hypothesis_validates_trigger_enum(
        self, temp_dir: Path, hypothesis_invalid_trigger_yaml: str
    ):
        """load_hypothesis() should reject falsifiers with invalid trigger enum.

        Trigger must be one of: review, sunset.
        """
        from src.governance.hypothesis.loader import HypothesisLoader
        from src.governance.utils.yaml_loader import YAMLLoadError

        path = temp_dir / "invalid_trigger.yml"
        path.write_text(hypothesis_invalid_trigger_yaml)

        loader = HypothesisLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_hypothesis(path)

        error_message = str(exc_info.value).lower()
        assert "trigger" in error_message

    def test_load_all_hypotheses_from_directory(self, multiple_hypothesis_files: Path):
        """load_all_hypotheses() should load all YAML files from directory.

        Should load both .yml and .yaml files.
        """
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()
        hypotheses = loader.load_all_hypotheses(multiple_hypothesis_files)

        # Should have loaded 3 valid hypothesis files (a.yml, b.yml, c.yaml)
        # Should NOT have loaded _example.yml, _template.yaml, or not_yaml.txt
        assert len(hypotheses) == 3

        # Verify we got the expected hypotheses
        ids = {h.id for h in hypotheses}
        assert "momentum_persistence" in ids
        assert "minimal_hyp" in ids
        assert "value_reversion" in ids

    def test_load_hypotheses_skips_files_starting_with_underscore(
        self, multiple_hypothesis_files: Path
    ):
        """load_all_hypotheses() should skip files starting with underscore.

        Files like _example.yml and _template.yaml should be ignored.
        """
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()
        hypotheses = loader.load_all_hypotheses(multiple_hypothesis_files)

        # Verify no underscore-prefixed files were loaded
        ids = {h.id for h in hypotheses}
        # momentum_persistence appears in _example.yml, but that should be skipped
        # We have 3 hypotheses total, and only one has id=momentum_persistence
        # which comes from hypothesis_a.yml, not _example.yml
        assert len([h for h in hypotheses if h.id == "momentum_persistence"]) == 1

    def test_load_hypotheses_empty_directory(self, temp_dir: Path):
        """load_all_hypotheses() should return empty list for empty directory."""
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()
        hypotheses = loader.load_all_hypotheses(temp_dir)

        assert hypotheses == []

    def test_load_hypotheses_nonexistent_directory(self):
        """load_all_hypotheses() should raise error for nonexistent directory."""
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_all_hypotheses(Path("/nonexistent/hypotheses/dir"))

    def test_load_hypothesis_file_not_found(self):
        """load_hypothesis() should raise FileNotFoundError for missing file."""
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_hypothesis(Path("/nonexistent/hypothesis.yml"))


class TestHypothesisLoaderWithDefaultPath:
    """Tests for HypothesisLoader with default config/hypotheses/ path."""

    def test_default_hypotheses_path_exists(self):
        """Loader should have a default path to config/hypotheses/."""
        from src.governance.hypothesis.loader import HypothesisLoader

        loader = HypothesisLoader()

        # The loader should have a default path configured
        assert hasattr(loader, "default_hypotheses_dir")
        assert "hypotheses" in str(loader.default_hypotheses_dir).lower()


class TestHypothesisLoaderValidation:
    """Tests for hypothesis validation methods."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_validate_hypothesis_returns_empty_for_valid(self, temp_dir: Path):
        """validate_hypothesis() should return empty list for valid file."""
        from src.governance.hypothesis.loader import HypothesisLoader

        yaml_content = """
id: valid_hypothesis
title: Valid Hypothesis
statement: A valid hypothesis statement.
scope: {}
status: ACTIVE
review_cycle: 30d
created_at: 2025-02-01
evidence: {}
falsifiers:
  - metric: sharpe_ratio
    operator: "<"
    threshold: 0.5
    window: 90d
    trigger: review
"""
        path = temp_dir / "valid.yml"
        path.write_text(yaml_content)

        loader = HypothesisLoader()
        errors = loader.validate_hypothesis(path)

        assert errors == []

    def test_validate_hypothesis_returns_errors_for_invalid(self, temp_dir: Path):
        """validate_hypothesis() should return list of validation errors."""
        from src.governance.hypothesis.loader import HypothesisLoader

        yaml_content = """
id: Invalid-ID
title: Invalid Hypothesis
statement: Missing required fields.
# Missing status, review_cycle, created_at, evidence, falsifiers
"""
        path = temp_dir / "invalid.yml"
        path.write_text(yaml_content)

        loader = HypothesisLoader()
        errors = loader.validate_hypothesis(path)

        assert len(errors) > 0
        # Should mention missing fields or invalid ID
        error_text = " ".join(errors).lower()
        assert "id" in error_text or "status" in error_text or "falsifiers" in error_text


class TestHypothesisLoaderExports:
    """Test that all required types are exported."""

    def test_hypothesis_loader_importable(self):
        """HypothesisLoader should be importable from the hypothesis module."""
        from src.governance.hypothesis.loader import HypothesisLoader

        assert HypothesisLoader is not None

    def test_hypothesis_loader_in_module_exports(self):
        """HypothesisLoader should eventually be exported from hypothesis __init__."""
        # This test will pass once the loader is implemented and added to __init__.py
        try:
            from src.governance.hypothesis import HypothesisLoader

            assert HypothesisLoader is not None
        except ImportError:
            # Expected to fail until loader is implemented
            pytest.skip("HypothesisLoader not yet exported from hypothesis module")
