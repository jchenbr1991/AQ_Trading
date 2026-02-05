"""Factor YAML loader with failure rule validation.

This module provides the FactorLoader class for loading factor definitions
from YAML files or dicts, enforcing gate:factor_requires_failure_rule.

Classes:
    FactorLoader: Load factor definitions with mandatory failure rule validation

Example:
    >>> from src.governance.factors.loader import FactorLoader
    >>> loader = FactorLoader()
    >>> factor = loader.load_factor({"id": "momentum", ...})
    >>> factors = loader.load_factors_from_yaml("config/factors/momentum.yml")
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import ValidationError

from src.governance.factors.models import Factor

logger = logging.getLogger(__name__)


class FactorLoader:
    """Load factor definitions with mandatory failure rule validation.

    Enforces gate:factor_requires_failure_rule -- every factor must have
    at least one failure rule. Factors without failure rules are rejected
    at load time with a clear error message.

    Example:
        >>> loader = FactorLoader()
        >>> factor = loader.load_factor({"id": "momentum", "name": "Momentum", ...})
        >>> factors = loader.load_factors_from_yaml("config/factors/")
    """

    def load_factor(self, data: dict) -> Factor:
        """Validate and create a Factor from a dict.

        Enforces gate:factor_requires_failure_rule by checking that
        failure_rules is present and non-empty before model validation.

        Args:
            data: Dictionary with factor fields.

        Returns:
            Validated Factor model instance.

        Raises:
            ValueError: If failure_rules is missing or empty
                (gate:factor_requires_failure_rule).
            ValidationError: If model validation fails for other reasons.
        """
        # gate:factor_requires_failure_rule - check before Pydantic validation
        failure_rules = data.get("failure_rules")
        if failure_rules is None or (isinstance(failure_rules, list) and len(failure_rules) == 0):
            raise ValueError(
                "gate:factor_requires_failure_rule - "
                "Factor must have at least 1 failure rule. "
                f"Factor '{data.get('id', '<unknown>')}' has no failure rules."
            )

        try:
            return Factor.model_validate(data)
        except ValidationError:
            raise

    def load_factors_from_yaml(self, path: str) -> list[Factor]:
        """Load factors from a YAML file or directory.

        If path points to a file, loads a single factor from it.
        If path points to a directory, loads all .yml and .yaml files,
        skipping files that start with an underscore (e.g., _example.yml).

        Args:
            path: Path to a YAML file or directory containing factor YAML files.

        Returns:
            List of validated Factor model instances.

        Raises:
            FileNotFoundError: If the path doesn't exist.
            ValueError: If any factor fails gate:factor_requires_failure_rule.
        """
        p = Path(path)

        if not p.exists():
            raise FileNotFoundError(f"Factor path not found: {path}")

        if p.is_file():
            return [self._load_from_file(p)]

        # Directory mode
        factors: list[Factor] = []
        yaml_files: list[Path] = []
        yaml_files.extend(p.glob("*.yml"))
        yaml_files.extend(p.glob("*.yaml"))
        yaml_files = sorted(set(yaml_files))

        for yaml_file in yaml_files:
            # Skip underscore-prefixed files
            if yaml_file.name.startswith("_"):
                logger.debug(f"Skipping underscore-prefixed file: {yaml_file}")
                continue

            if not yaml_file.is_file():
                continue

            factor = self._load_from_file(yaml_file)
            factors.append(factor)
            logger.debug(f"Loaded factor: {factor.id} from {yaml_file}")

        return factors

    def _load_from_file(self, path: Path) -> Factor:
        """Load a single factor from a YAML file.

        Args:
            path: Path to the YAML file.

        Returns:
            Validated Factor model instance.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If gate:factor_requires_failure_rule fails.
        """
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {path}")

        content = path.read_text(encoding="utf-8")
        data = yaml.safe_load(content)

        if data is None:
            data = {}

        return self.load_factor(data)


__all__ = ["FactorLoader"]
