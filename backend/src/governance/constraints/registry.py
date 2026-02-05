"""Constraint Registry for in-memory constraint management.

This module provides the ConstraintRegistry class for storing, querying,
and managing Constraint objects in memory. It supports lazy loading and
reloading from disk via a ConstraintLoader.

Classes:
    DuplicateConstraintError: Raised when registering a constraint with duplicate ID
    ConstraintRegistry: In-memory registry for constraint management

Example:
    >>> from src.governance.constraints.registry import ConstraintRegistry
    >>> from src.governance.constraints.loader import ConstraintLoader
    >>> loader = ConstraintLoader()
    >>> registry = ConstraintRegistry(loader=loader)
    >>> registry.reload()  # Load all constraints from disk
    >>> constraints = registry.filter_by_symbol("AAPL")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.governance.constraints.models import Constraint

if TYPE_CHECKING:
    from src.governance.constraints.loader import ConstraintLoader

logger = logging.getLogger(__name__)


class DuplicateConstraintError(Exception):
    """Raised when attempting to register a constraint with a duplicate ID.

    This error is raised by ConstraintRegistry.register() or reload() when
    a constraint with the same ID already exists in the registry.

    Attributes:
        constraint_id: The ID that caused the duplicate error.
    """

    def __init__(self, constraint_id: str) -> None:
        """Initialize the error with the duplicate constraint ID.

        Args:
            constraint_id: The ID that already exists in the registry.
        """
        self.constraint_id = constraint_id
        super().__init__(f"Constraint with ID '{constraint_id}' already exists in registry")


class ConstraintRegistry:
    """In-memory registry for constraint management.

    Stores loaded constraints in memory and provides efficient query methods
    for retrieving constraints by ID or filtering by symbol/strategy. Supports
    lazy loading and reloading from disk via an optional ConstraintLoader.

    The registry tracks constraints efficiently by maintaining a dictionary
    indexed by constraint ID.

    Attributes:
        _constraints: Internal dict storing constraints by ID.
        _loader: Optional loader for loading/reloading from disk.
        _loaded: Flag indicating whether constraints have been loaded.

    Example:
        >>> registry = ConstraintRegistry()
        >>> registry.register(constraint)
        >>> by_symbol = registry.filter_by_symbol("AAPL")
        >>> by_strategy = registry.filter_by_strategy("momentum_strategy")
    """

    def __init__(self, loader: ConstraintLoader | None = None) -> None:
        """Initialize registry with optional loader for reload functionality.

        The registry starts empty and supports lazy loading - constraints are
        not loaded until first access if a loader is provided.

        Args:
            loader: Optional ConstraintLoader for load/reload functionality.
        """
        self._constraints: dict[str, Constraint] = {}
        self._loader = loader
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Ensure constraints are loaded (lazy loading).

        If a loader is configured and constraints haven't been loaded yet,
        this method loads them. If no loader is configured, this is a no-op.
        """
        if not self._loaded and self._loader is not None:
            self._load_from_loader()
            self._loaded = True

    def _load_from_loader(self) -> None:
        """Load constraints from the configured loader.

        Internal method that loads all constraints from the loader and
        adds them to the registry. Checks for duplicate IDs.

        Raises:
            DuplicateConstraintError: If duplicate constraint IDs are found.
        """
        if self._loader is None:
            return

        constraints = self._loader.load_all_constraints()
        for constraint in constraints:
            if constraint.id in self._constraints:
                raise DuplicateConstraintError(constraint.id)
            self._constraints[constraint.id] = constraint
            logger.debug(f"Loaded constraint: {constraint.id}")

        logger.info(f"Loaded {len(self._constraints)} constraints from loader")

    def get(self, constraint_id: str) -> Constraint | None:
        """Get constraint by ID.

        Triggers lazy loading if a loader is configured.

        Args:
            constraint_id: The unique identifier of the constraint.

        Returns:
            The Constraint if found, None otherwise.
        """
        self._ensure_loaded()
        return self._constraints.get(constraint_id)

    def list_all(self) -> list[Constraint]:
        """List all registered constraints.

        Triggers lazy loading if a loader is configured.

        Returns:
            List of all constraints in the registry.
        """
        self._ensure_loaded()
        return list(self._constraints.values())

    def filter_by_symbol(self, symbol: str) -> list[Constraint]:
        """Filter constraints that apply to a symbol.

        A constraint applies to a symbol if:
        - The constraint's applies_to.symbols list is empty (applies to all), OR
        - The symbol is in the constraint's applies_to.symbols list

        Triggers lazy loading if a loader is configured.

        Args:
            symbol: The stock symbol to filter by.

        Returns:
            List of constraints that apply to the symbol.
        """
        self._ensure_loaded()
        return [
            c
            for c in self._constraints.values()
            if not c.applies_to.symbols or symbol in c.applies_to.symbols
        ]

    def filter_by_strategy(self, strategy_id: str) -> list[Constraint]:
        """Filter constraints that apply to a strategy.

        A constraint applies to a strategy if:
        - The constraint's applies_to.strategies list is empty (applies to all), OR
        - The strategy_id is in the constraint's applies_to.strategies list

        Triggers lazy loading if a loader is configured.

        Args:
            strategy_id: The strategy identifier to filter by.

        Returns:
            List of constraints that apply to the strategy.
        """
        self._ensure_loaded()
        return [
            c
            for c in self._constraints.values()
            if not c.applies_to.strategies or strategy_id in c.applies_to.strategies
        ]

    def register(self, constraint: Constraint) -> None:
        """Register a constraint.

        Adds the constraint to the registry. The constraint must have a unique
        ID - attempting to register a constraint with an existing ID raises
        DuplicateConstraintError.

        Note: This marks the registry as loaded to prevent lazy loading from
        overwriting manually registered constraints.

        Args:
            constraint: The constraint to register.

        Raises:
            DuplicateConstraintError: If a constraint with the same ID exists.
        """
        # Mark as loaded to prevent lazy loading from overwriting
        self._loaded = True

        if constraint.id in self._constraints:
            raise DuplicateConstraintError(constraint.id)
        self._constraints[constraint.id] = constraint
        logger.debug(f"Registered constraint: {constraint.id}")

    def unregister(self, constraint_id: str) -> bool:
        """Remove constraint from registry.

        Args:
            constraint_id: The ID of the constraint to remove.

        Returns:
            True if the constraint was removed, False if not found.
        """
        self._ensure_loaded()
        if constraint_id in self._constraints:
            del self._constraints[constraint_id]
            logger.debug(f"Unregistered constraint: {constraint_id}")
            return True
        return False

    def reload(self) -> None:
        """Reload all constraints from loader.

        Clears the registry and loads all constraints from the configured
        loader. This replaces any manually registered constraints.

        Raises:
            ValueError: If no loader is configured.
            DuplicateConstraintError: If duplicate constraint IDs are found.
        """
        if self._loader is None:
            raise ValueError(
                "Cannot reload: no loader configured. "
                "Initialize registry with a ConstraintLoader to enable reload."
            )

        # Clear existing constraints
        self._constraints.clear()

        # Load all constraints from loader and check for duplicates
        constraints = self._loader.load_all_constraints()
        for constraint in constraints:
            if constraint.id in self._constraints:
                raise DuplicateConstraintError(constraint.id)
            self._constraints[constraint.id] = constraint
            logger.debug(f"Loaded constraint: {constraint.id}")

        self._loaded = True
        logger.info(f"Reloaded {len(self._constraints)} constraints from loader")

    def count(self) -> int:
        """Count total registered constraints.

        Triggers lazy loading if a loader is configured.

        Returns:
            The total number of constraints in the registry.
        """
        self._ensure_loaded()
        return len(self._constraints)

    def is_empty(self) -> bool:
        """Check if registry is empty.

        Triggers lazy loading if a loader is configured.

        Returns:
            True if the registry has no constraints, False otherwise.
        """
        self._ensure_loaded()
        return len(self._constraints) == 0


__all__ = [
    "DuplicateConstraintError",
    "ConstraintRegistry",
]
