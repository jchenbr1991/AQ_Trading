"""Constraint YAML loader with validation.

This module provides the ConstraintLoader class for loading constraint
YAML files from the config/constraints/ directory into validated
Constraint Pydantic models.

Classes:
    ConstraintLoader: Load constraint YAML files with validation

Example:
    >>> from pathlib import Path
    >>> from src.governance.constraints.loader import ConstraintLoader
    >>> loader = ConstraintLoader()
    >>> constraint = loader.load_constraint(Path("config/constraints/momentum.yml"))
    >>> all_constraints = loader.load_all_constraints()
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.governance.constraints.models import Constraint
from src.governance.utils.yaml_loader import YAMLLoader

logger = logging.getLogger(__name__)


class ConstraintLoader:
    """Load constraint YAML files with validation.

    Provides methods for loading single constraint files, entire directories,
    and validating constraint YAML without fully loading.

    Attributes:
        default_constraints_dir: Default directory for constraint YAML files.

    Example:
        >>> loader = ConstraintLoader()
        >>> constraint = loader.load_constraint(Path("config/constraints/example.yml"))
        >>> errors = loader.validate_constraint(Path("config/constraints/example.yml"))
    """

    default_constraints_dir: Path = Path("config/constraints")

    def __init__(self, constraints_dir: str | Path | None = None) -> None:
        """Initialize the ConstraintLoader.

        Args:
            constraints_dir: Optional custom directory for constraint files.
                            Uses default_constraints_dir if None.
        """
        if constraints_dir is not None:
            self.default_constraints_dir = Path(constraints_dir)
        self._yaml_loader = YAMLLoader()

    def load_constraint(self, path: str | Path) -> Constraint:
        """Load a single constraint YAML file.

        Loads the YAML file and validates it against the Constraint model.

        Args:
            path: Path to the constraint YAML file.

        Returns:
            Validated Constraint model instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            YAMLLoadError: If YAML parsing or validation fails.
        """
        path = Path(path)
        return self._yaml_loader.load_file(path, Constraint)

    def load_all_constraints(self, directory: str | Path | None = None) -> list[Constraint]:
        """Load all constraint YAML files from a directory.

        Loads all .yml and .yaml files from the specified directory,
        skipping files that start with an underscore (e.g., _example.yml).

        Args:
            directory: Optional directory path. Uses default_constraints_dir if None.

        Returns:
            List of validated Constraint model instances.

        Raises:
            FileNotFoundError: If the directory doesn't exist.
        """
        target_dir = Path(directory) if directory is not None else self.default_constraints_dir

        if not target_dir.exists():
            raise FileNotFoundError(f"Directory not found: {target_dir}")

        if not target_dir.is_dir():
            raise FileNotFoundError(f"Path is not a directory: {target_dir}")

        constraints: list[Constraint] = []

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

            constraint = self.load_constraint(yaml_file)
            constraints.append(constraint)
            logger.debug(f"Loaded constraint: {constraint.id} from {yaml_file}")

        return constraints

    def validate_constraint(self, path: str | Path) -> list[str]:
        """Validate a constraint YAML file without loading.

        Performs the same validation as load_constraint() but returns errors
        as a list of strings instead of raising exceptions.

        Args:
            path: Path to the constraint YAML file.

        Returns:
            List of error messages (empty if valid).
        """
        path = Path(path)
        return self._yaml_loader.validate_yaml(path, Constraint)


__all__ = ["ConstraintLoader"]
