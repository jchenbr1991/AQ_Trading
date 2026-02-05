"""Tests for governance YAML loader utility.

TDD: Write tests FIRST, then implement loader to make them pass.
"""

import tempfile
from pathlib import Path

import pytest
from pydantic import BaseModel


class SampleConfig(BaseModel):
    """Sample Pydantic model for testing YAML loading."""

    id: str
    name: str
    value: int = 0


class StrictConfig(BaseModel):
    """Sample model with strict validation."""

    model_config = {"extra": "forbid"}

    id: str
    required_field: str


class TestYAMLLoader:
    """Tests for YAMLLoader class."""

    @pytest.fixture
    def temp_dir(self) -> Path:
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def sample_yaml_file(self, temp_dir: Path) -> Path:
        """Create a sample YAML file."""
        yaml_content = """
id: test_config
name: Test Config
value: 42
"""
        path = temp_dir / "sample.yml"
        path.write_text(yaml_content)
        return path

    @pytest.fixture
    def multiple_yaml_files(self, temp_dir: Path) -> Path:
        """Create multiple YAML files in a directory."""
        configs = [
            ("config_a.yml", "id: config_a\nname: Config A\nvalue: 1"),
            ("config_b.yml", "id: config_b\nname: Config B\nvalue: 2"),
            ("config_c.yaml", "id: config_c\nname: Config C\nvalue: 3"),
            ("not_yaml.txt", "this is not yaml"),
        ]
        for filename, content in configs:
            (temp_dir / filename).write_text(content)
        return temp_dir

    def test_load_file_success(self, sample_yaml_file: Path):
        """load_file() should successfully parse YAML into Pydantic model."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()
        result = loader.load_file(sample_yaml_file, SampleConfig)

        assert isinstance(result, SampleConfig)
        assert result.id == "test_config"
        assert result.name == "Test Config"
        assert result.value == 42

    def test_load_file_with_defaults(self, temp_dir: Path):
        """load_file() should use default values for optional fields."""
        from src.governance.utils.yaml_loader import YAMLLoader

        yaml_content = """
id: minimal_config
name: Minimal
"""
        path = temp_dir / "minimal.yml"
        path.write_text(yaml_content)

        loader = YAMLLoader()
        result = loader.load_file(path, SampleConfig)

        assert result.id == "minimal_config"
        assert result.name == "Minimal"
        assert result.value == 0  # Default

    def test_load_file_not_found(self):
        """load_file() should raise FileNotFoundError for missing file."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_file(Path("/nonexistent/path.yml"), SampleConfig)

    def test_load_file_invalid_yaml(self, temp_dir: Path):
        """load_file() should raise error for invalid YAML syntax."""
        from src.governance.utils.yaml_loader import YAMLLoader, YAMLLoadError

        yaml_content = """
id: bad_yaml
name: [unclosed bracket
"""
        path = temp_dir / "invalid.yml"
        path.write_text(yaml_content)

        loader = YAMLLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_file(path, SampleConfig)

        assert "YAML" in str(exc_info.value) or "yaml" in str(exc_info.value).lower()

    def test_load_file_validation_error(self, temp_dir: Path):
        """load_file() should raise error when validation fails."""
        from src.governance.utils.yaml_loader import YAMLLoader, YAMLLoadError

        yaml_content = """
id: invalid_config
# missing required 'name' field
"""
        path = temp_dir / "invalid_model.yml"
        path.write_text(yaml_content)

        loader = YAMLLoader()

        with pytest.raises(YAMLLoadError) as exc_info:
            loader.load_file(path, SampleConfig)

        assert "name" in str(exc_info.value).lower()

    def test_load_directory_finds_yml_files(self, multiple_yaml_files: Path):
        """load_directory() should find and load all .yml files."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()
        results = loader.load_directory(multiple_yaml_files, SampleConfig, pattern="*.yml")

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"config_a", "config_b"}

    def test_load_directory_supports_yaml_extension(self, multiple_yaml_files: Path):
        """load_directory() should support .yaml extension pattern."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()
        results = loader.load_directory(multiple_yaml_files, SampleConfig, pattern="*.yaml")

        assert len(results) == 1
        assert results[0].id == "config_c"

    def test_load_directory_all_yaml_files(self, multiple_yaml_files: Path):
        """load_directory() with pattern *.y*ml should find both .yml and .yaml."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()
        # Load both extensions
        yml_results = loader.load_directory(multiple_yaml_files, SampleConfig, pattern="*.yml")
        yaml_results = loader.load_directory(multiple_yaml_files, SampleConfig, pattern="*.yaml")

        all_results = yml_results + yaml_results
        assert len(all_results) == 3

    def test_load_directory_empty(self, temp_dir: Path):
        """load_directory() should return empty list for empty directory."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()
        results = loader.load_directory(temp_dir, SampleConfig)

        assert results == []

    def test_load_directory_nonexistent(self):
        """load_directory() should raise error for nonexistent directory."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()

        with pytest.raises(FileNotFoundError):
            loader.load_directory(Path("/nonexistent/dir"), SampleConfig)

    def test_validate_yaml_returns_empty_for_valid(self, sample_yaml_file: Path):
        """validate_yaml() should return empty list for valid file."""
        from src.governance.utils.yaml_loader import YAMLLoader

        loader = YAMLLoader()
        errors = loader.validate_yaml(sample_yaml_file, SampleConfig)

        assert errors == []

    def test_validate_yaml_returns_errors_for_invalid(self, temp_dir: Path):
        """validate_yaml() should return list of validation errors."""
        from src.governance.utils.yaml_loader import YAMLLoader

        yaml_content = """
id: invalid
# missing required 'name' field
value: not_a_number
"""
        path = temp_dir / "invalid.yml"
        path.write_text(yaml_content)

        loader = YAMLLoader()
        errors = loader.validate_yaml(path, SampleConfig)

        assert len(errors) > 0
        # Should mention missing field or type error
        error_text = " ".join(errors).lower()
        assert "name" in error_text or "value" in error_text

    def test_validate_yaml_returns_errors_for_yaml_syntax(self, temp_dir: Path):
        """validate_yaml() should return YAML syntax errors."""
        from src.governance.utils.yaml_loader import YAMLLoader

        yaml_content = """
id: bad
name: [unclosed
"""
        path = temp_dir / "syntax_error.yml"
        path.write_text(yaml_content)

        loader = YAMLLoader()
        errors = loader.validate_yaml(path, SampleConfig)

        assert len(errors) > 0

    def test_validate_yaml_handles_extra_fields_with_strict_model(self, temp_dir: Path):
        """validate_yaml() should catch extra fields when model forbids them."""
        from src.governance.utils.yaml_loader import YAMLLoader

        yaml_content = """
id: strict_test
required_field: present
extra_field: should_fail
"""
        path = temp_dir / "extra_field.yml"
        path.write_text(yaml_content)

        loader = YAMLLoader()
        errors = loader.validate_yaml(path, StrictConfig)

        assert len(errors) > 0
        assert "extra_field" in " ".join(errors).lower()

    def test_load_file_handles_unicode(self, temp_dir: Path):
        """load_file() should handle unicode characters in YAML."""
        from src.governance.utils.yaml_loader import YAMLLoader

        yaml_content = """
id: unicode_test
name: 测试配置 (Test Config)
value: 100
"""
        path = temp_dir / "unicode.yml"
        path.write_text(yaml_content, encoding="utf-8")

        loader = YAMLLoader()
        result = loader.load_file(path, SampleConfig)

        assert result.id == "unicode_test"
        assert "测试" in result.name


class TestYAMLLoadError:
    """Tests for YAMLLoadError exception."""

    def test_yaml_load_error_message(self):
        """YAMLLoadError should have descriptive message."""
        from src.governance.utils.yaml_loader import YAMLLoadError

        error = YAMLLoadError("Test error", Path("/test/path.yml"))

        assert "Test error" in str(error)
        assert "/test/path.yml" in str(error)

    def test_yaml_load_error_has_path(self):
        """YAMLLoadError should have path attribute."""
        from src.governance.utils.yaml_loader import YAMLLoadError

        error = YAMLLoadError("message", Path("/test/path.yml"))

        assert error.path == Path("/test/path.yml")


class TestAllExports:
    """Test that all required types are exported."""

    def test_all_exports_available(self):
        """YAMLLoader and YAMLLoadError should be importable."""
        from src.governance.utils.yaml_loader import YAMLLoader, YAMLLoadError

        assert YAMLLoader is not None
        assert YAMLLoadError is not None
