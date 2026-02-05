# backend/src/universe/static.py
"""Static universe loader from YAML configuration files.

This module provides functionality to load universe configurations from YAML files,
supporting the definition of tradeable asset universes for strategy execution.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Universe:
    """Universe of tradeable symbols.

    A Universe defines a collection of tradeable assets that a strategy
    can operate on. Universes can be enabled/disabled via the active flag.

    Attributes:
        name: Universe identifier (unique name).
        symbols: List of ticker symbols in this universe.
        active: Whether the universe is currently enabled for trading.
    """

    name: str
    symbols: list[str] = field(default_factory=list)
    active: bool = True


class UniverseNotFoundError(Exception):
    """Raised when a requested universe is not found in the configuration."""

    pass


class UniverseConfigError(Exception):
    """Raised when there is an error in the universe configuration."""

    pass


class StaticUniverseLoader:
    """Loads universe configurations from YAML files.

    This loader reads universe definitions from a YAML configuration file
    and provides methods to retrieve universe objects and symbol lists.

    Example YAML format:
        universe:
          name: mvp-universe
          symbols:
            - MU
            - GLD
            - GOOG
          active: true

    Or multiple universes:
        universes:
          - name: tech-universe
            symbols: [AAPL, GOOG, MSFT]
            active: true
          - name: commodities
            symbols: [GLD, SLV, USO]
            active: false
    """

    def __init__(self, config_path: Path | str) -> None:
        """Initialize the loader with a configuration file path.

        Args:
            config_path: Path to the YAML configuration file.
        """
        self._config_path = Path(config_path)
        self._universes: dict[str, Universe] | None = None

    def _load_config(self) -> dict[str, Universe]:
        """Load and parse the YAML configuration file.

        Returns:
            Dictionary mapping universe names to Universe objects.

        Raises:
            UniverseConfigError: If the configuration file cannot be parsed.
        """
        if self._universes is not None:
            return self._universes

        self._universes = {}

        if not self._config_path.exists():
            # Return empty dict for missing config file (graceful handling)
            return self._universes

        try:
            with open(self._config_path) as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise UniverseConfigError(f"Failed to parse YAML config: {e}") from e
        except OSError as e:
            raise UniverseConfigError(f"Failed to read config file: {e}") from e

        if config is None:
            # Empty YAML file
            return self._universes

        # Handle single universe format: universe: {...}
        if "universe" in config:
            universe = self._parse_universe(config["universe"])
            self._universes[universe.name] = universe

        # Handle multiple universes format: universes: [...]
        if "universes" in config:
            for universe_data in config["universes"]:
                universe = self._parse_universe(universe_data)
                self._universes[universe.name] = universe

        return self._universes

    def _parse_universe(self, data: dict[str, Any]) -> Universe:
        """Parse a single universe from configuration data.

        Args:
            data: Dictionary with universe configuration.

        Returns:
            Universe object.

        Raises:
            UniverseConfigError: If required fields are missing.
        """
        if "name" not in data:
            raise UniverseConfigError("Universe configuration missing 'name' field")

        name = data["name"]
        symbols = data.get("symbols", [])
        active = data.get("active", True)

        # Ensure symbols is a list
        if not isinstance(symbols, list):
            symbols = [symbols] if symbols else []

        # Ensure all symbols are strings
        symbols = [str(s) for s in symbols]

        return Universe(name=name, symbols=symbols, active=active)

    def load(self, universe_name: str | None = None) -> Universe | None:
        """Load a universe by name.

        If name is None, loads the first/default universe from the configuration.

        Args:
            universe_name: Name of the universe to load, or None for default.

        Returns:
            Universe object if found, None otherwise.
        """
        universes = self._load_config()

        if not universes:
            return None

        if universe_name is None:
            # Return the first universe as default
            return next(iter(universes.values()))

        return universes.get(universe_name)

    def get_symbols(self, universe_name: str | None = None) -> list[str]:
        """Get symbols for a universe.

        Args:
            universe_name: Name of the universe, or None for default.

        Returns:
            List of symbols in the universe, or empty list if not found.
        """
        universe = self.load(universe_name)
        if universe is None:
            return []
        return universe.symbols

    def list_universes(self) -> list[str]:
        """List all available universe names.

        Returns:
            List of universe names in the configuration.
        """
        universes = self._load_config()
        return list(universes.keys())

    def load_all(self) -> list[Universe]:
        """Load all universes from the configuration.

        Returns:
            List of all Universe objects.
        """
        universes = self._load_config()
        return list(universes.values())

    def load_active(self) -> list[Universe]:
        """Load only active universes.

        Returns:
            List of Universe objects where active=True.
        """
        universes = self._load_config()
        return [u for u in universes.values() if u.active]

    def reload(self) -> None:
        """Force reload of the configuration file.

        Clears the cached configuration and reloads from disk.
        """
        self._universes = None
        self._load_config()
