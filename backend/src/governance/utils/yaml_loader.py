"""YAML loader utility with Pydantic integration.

This module provides utilities for loading YAML configuration files into
Pydantic models with proper validation and error handling.

Classes:
    YAMLLoader: Load YAML files into Pydantic models
    YAMLLoadError: Exception raised when YAML loading fails

Example:
    >>> from pathlib import Path
    >>> loader = YAMLLoader()
    >>> hypothesis = loader.load_file(Path("config/hypotheses/example.yml"), Hypothesis)
    >>> all_hypotheses = loader.load_directory(Path("config/hypotheses"), Hypothesis)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class YAMLLoadError(Exception):
    """Exception raised when YAML loading or validation fails.

    Attributes:
        message: Human-readable error description
        path: Path to the file that failed to load
    """

    def __init__(self, message: str, path: Path) -> None:
        """Initialize the error.

        Args:
            message: Human-readable error description
            path: Path to the file that failed to load
        """
        self.message = message
        self.path = path
        super().__init__(f"{message} ({path})")


class YAMLLoader:
    """Load YAML files into Pydantic models with validation.

    Provides methods for loading single files, entire directories,
    and validating YAML without fully loading.

    Example:
        >>> loader = YAMLLoader()
        >>> config = loader.load_file(Path("config.yml"), ConfigModel)
        >>> errors = loader.validate_yaml(Path("config.yml"), ConfigModel)
    """

    def load_file(self, path: Path, model_cls: type[T]) -> T:
        """Load a single YAML file into a Pydantic model.

        Args:
            path: Path to the YAML file
            model_cls: Pydantic model class to deserialize into

        Returns:
            Validated Pydantic model instance

        Raises:
            FileNotFoundError: If the file doesn't exist
            YAMLLoadError: If YAML parsing or model validation fails
        """
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {path}")

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if data is None:
                data = {}

            return model_cls.model_validate(data)

        except yaml.YAMLError as e:
            raise YAMLLoadError(f"YAML syntax error: {e}", path) from e
        except ValidationError as e:
            # Format validation errors nicely
            error_messages = []
            for error in e.errors():
                loc = ".".join(str(loc) for loc in error["loc"])
                msg = error["msg"]
                error_messages.append(f"{loc}: {msg}")
            raise YAMLLoadError(f"Validation failed: {'; '.join(error_messages)}", path) from e

    def load_directory(
        self, directory: Path, model_cls: type[T], pattern: str = "*.yml"
    ) -> list[T]:
        """Load all matching YAML files in a directory.

        Args:
            directory: Directory containing YAML files
            model_cls: Pydantic model class to deserialize into
            pattern: Glob pattern for matching files (default: "*.yml")

        Returns:
            List of validated Pydantic model instances

        Raises:
            FileNotFoundError: If the directory doesn't exist
            YAMLLoadError: If any file fails to load (fails fast)
        """
        if not directory.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not directory.is_dir():
            raise FileNotFoundError(f"Path is not a directory: {directory}")

        results: list[T] = []
        for yaml_file in sorted(directory.glob(pattern)):
            if yaml_file.is_file():
                model = self.load_file(yaml_file, model_cls)
                results.append(model)

        return results

    def validate_yaml(self, path: Path, model_cls: type[T]) -> list[str]:
        """Validate YAML file without loading.

        Performs the same validation as load_file() but returns errors
        as a list of strings instead of raising exceptions.

        Args:
            path: Path to the YAML file
            model_cls: Pydantic model class to validate against

        Returns:
            List of error messages (empty if valid)
        """
        if not path.exists():
            return [f"File not found: {path}"]

        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)

            if data is None:
                data = {}

            model_cls.model_validate(data)
            return []

        except yaml.YAMLError as e:
            return [f"YAML syntax error: {e}"]
        except ValidationError as e:
            errors = []
            for error in e.errors():
                loc = ".".join(str(loc) for loc in error["loc"])
                msg = error["msg"]
                errors.append(f"{loc}: {msg}")
            return errors


__all__ = ["YAMLLoader", "YAMLLoadError"]
