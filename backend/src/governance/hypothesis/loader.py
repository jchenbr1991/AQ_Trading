"""Hypothesis YAML loader with validation.

This module provides the HypothesisLoader class for loading hypothesis
YAML files from the config/hypotheses/ directory into validated
Hypothesis Pydantic models.

Classes:
    HypothesisLoader: Load hypothesis YAML files with validation

Example:
    >>> from pathlib import Path
    >>> from src.governance.hypothesis.loader import HypothesisLoader
    >>> loader = HypothesisLoader()
    >>> hypothesis = loader.load_hypothesis(Path("config/hypotheses/momentum.yml"))
    >>> all_hypotheses = loader.load_all_hypotheses()
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.governance.hypothesis.models import Hypothesis
from src.governance.utils.yaml_loader import YAMLLoader, YAMLLoadError

logger = logging.getLogger(__name__)


class HypothesisLoader:
    """Load hypothesis YAML files with validation.

    Provides methods for loading single hypothesis files, entire directories,
    and validating hypothesis YAML without fully loading.

    The loader enforces gate:hypothesis_requires_falsifiers by catching
    Pydantic validation errors for missing/empty falsifiers and re-raising
    with a clear error message.

    Attributes:
        default_hypotheses_dir: Default directory for hypothesis YAML files.

    Example:
        >>> loader = HypothesisLoader()
        >>> hypothesis = loader.load_hypothesis(Path("config/hypotheses/example.yml"))
        >>> errors = loader.validate_hypothesis(Path("config/hypotheses/example.yml"))
    """

    default_hypotheses_dir: Path = Path("config/hypotheses")

    def __init__(self, hypotheses_dir: Path | None = None) -> None:
        """Initialize the HypothesisLoader.

        Args:
            hypotheses_dir: Optional custom directory for hypothesis files.
                           Uses default_hypotheses_dir if None.
        """
        if hypotheses_dir is not None:
            self.default_hypotheses_dir = hypotheses_dir
        self._yaml_loader = YAMLLoader()

    def load_hypothesis(self, path: Path) -> Hypothesis:
        """Load a single hypothesis YAML file.

        Loads the YAML file and validates it against the Hypothesis model.
        Enforces gate:hypothesis_requires_falsifiers by catching validation
        errors and providing clear error messages.

        Args:
            path: Path to the hypothesis YAML file.

        Returns:
            Validated Hypothesis model instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            YAMLLoadError: If YAML parsing or validation fails,
                          including missing falsifiers (gate enforcement).
        """
        try:
            return self._yaml_loader.load_file(path, Hypothesis)
        except YAMLLoadError as e:
            # Re-raise with enhanced message for falsifiers requirement
            error_lower = str(e).lower()
            if "falsifiers" in error_lower and (
                "min" in error_lower or "field required" in error_lower
            ):
                raise YAMLLoadError(
                    "gate:hypothesis_requires_falsifiers - "
                    "Hypothesis must have at least 1 falsifier. "
                    f"Original error: {e.message}",
                    path,
                ) from e
            raise

    def load_all_hypotheses(self, directory: Path | None = None) -> list[Hypothesis]:
        """Load all hypothesis YAML files from a directory.

        Loads all .yml and .yaml files from the specified directory,
        skipping files that start with an underscore (e.g., _example.yml).

        Args:
            directory: Optional directory path. Uses default_hypotheses_dir if None.

        Returns:
            List of validated Hypothesis model instances.

        Raises:
            FileNotFoundError: If the directory doesn't exist.
        """
        target_dir = directory if directory is not None else self.default_hypotheses_dir

        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {target_dir}")

        if not target_dir.is_dir():
            raise FileNotFoundError(f"Path is not a directory: {target_dir}")

        hypotheses: list[Hypothesis] = []

        # Load both .yml and .yaml files
        yaml_files: list[Path] = []
        yaml_files.extend(target_dir.glob("*.yml"))
        yaml_files.extend(target_dir.glob("*.yaml"))

        # Sort for consistent ordering
        yaml_files = sorted(set(yaml_files))

        for yaml_file in yaml_files:
            # Skip files starting with underscore
            if yaml_file.name.startswith("_"):
                logger.debug(f"Skipping underscore-prefixed file: {yaml_file}")
                continue

            # Skip non-files (shouldn't happen with glob, but be safe)
            if not yaml_file.is_file():
                continue

            hypothesis = self.load_hypothesis(yaml_file)
            hypotheses.append(hypothesis)
            logger.debug(f"Loaded hypothesis: {hypothesis.id} from {yaml_file}")

        return hypotheses

    def validate_hypothesis(self, path: Path) -> list[str]:
        """Validate a hypothesis YAML file without loading.

        Performs the same validation as load_hypothesis() but returns errors
        as a list of strings instead of raising exceptions.

        Args:
            path: Path to the hypothesis YAML file.

        Returns:
            List of error messages (empty if valid).
        """
        return self._yaml_loader.validate_yaml(path, Hypothesis)


__all__ = ["HypothesisLoader"]
