"""Hypothesis Registry for in-memory hypothesis management.

This module provides the HypothesisRegistry class for storing, querying,
and managing Hypothesis objects in memory. It supports reloading from
disk via a HypothesisLoader.

Classes:
    DuplicateHypothesisError: Raised when registering a hypothesis with duplicate ID
    HypothesisRegistry: In-memory registry for hypothesis management

Example:
    >>> from src.governance.hypothesis.registry import HypothesisRegistry
    >>> from src.governance.hypothesis.loader import HypothesisLoader
    >>> loader = HypothesisLoader()
    >>> registry = HypothesisRegistry(loader=loader)
    >>> registry.reload()  # Load all hypotheses from disk
    >>> active = registry.get_active()  # Get all active hypotheses
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.governance.hypothesis.models import Hypothesis
from src.governance.models import HypothesisStatus

if TYPE_CHECKING:
    from src.governance.hypothesis.loader import HypothesisLoader

logger = logging.getLogger(__name__)


class DuplicateHypothesisError(Exception):
    """Raised when attempting to register a hypothesis with a duplicate ID.

    This error is raised by HypothesisRegistry.register() when a hypothesis
    with the same ID already exists in the registry.

    Attributes:
        hypothesis_id: The ID that caused the duplicate error.
    """

    def __init__(self, hypothesis_id: str) -> None:
        """Initialize the error with the duplicate hypothesis ID.

        Args:
            hypothesis_id: The ID that already exists in the registry.
        """
        self.hypothesis_id = hypothesis_id
        super().__init__(f"Hypothesis with ID '{hypothesis_id}' already exists in registry")


class HypothesisRegistry:
    """In-memory registry for hypothesis management.

    Stores loaded hypotheses in memory and provides efficient query methods
    for retrieving hypotheses by ID or filtering by status. Supports
    reloading from disk via an optional HypothesisLoader.

    The registry tracks active hypotheses efficiently by maintaining
    a dictionary indexed by hypothesis ID.

    Attributes:
        _hypotheses: Internal dict storing hypotheses by ID.
        _loader: Optional loader for reloading from disk.

    Example:
        >>> registry = HypothesisRegistry()
        >>> registry.register(hypothesis)
        >>> active = registry.get_active()
        >>> registry.filter_by_status(HypothesisStatus.DRAFT, HypothesisStatus.ACTIVE)
    """

    def __init__(self, loader: HypothesisLoader | None = None) -> None:
        """Initialize registry with optional loader for reload functionality.

        The registry starts empty and does not auto-load hypotheses from the
        loader on initialization. Call reload() explicitly to load hypotheses.

        Args:
            loader: Optional HypothesisLoader for reload functionality.
        """
        self._hypotheses: dict[str, Hypothesis] = {}
        self._loader = loader

    def get(self, hypothesis_id: str) -> Hypothesis | None:
        """Get hypothesis by ID.

        Args:
            hypothesis_id: The unique identifier of the hypothesis.

        Returns:
            The Hypothesis if found, None otherwise.
        """
        return self._hypotheses.get(hypothesis_id)

    def list_all(self) -> list[Hypothesis]:
        """List all registered hypotheses.

        Returns:
            List of all hypotheses in the registry.
        """
        return list(self._hypotheses.values())

    def filter_by_status(self, *statuses: HypothesisStatus) -> list[Hypothesis]:
        """Filter hypotheses by one or more statuses.

        Args:
            *statuses: One or more HypothesisStatus values to filter by.

        Returns:
            List of hypotheses matching any of the provided statuses.
        """
        status_set = set(statuses)
        return [h for h in self._hypotheses.values() if h.status in status_set]

    def get_active(self) -> list[Hypothesis]:
        """Get all ACTIVE hypotheses.

        Convenience method equivalent to filter_by_status(HypothesisStatus.ACTIVE).

        Returns:
            List of all hypotheses with ACTIVE status.
        """
        return self.filter_by_status(HypothesisStatus.ACTIVE)

    def register(self, hypothesis: Hypothesis) -> None:
        """Register a hypothesis.

        Adds the hypothesis to the registry. The hypothesis must have a unique
        ID - attempting to register a hypothesis with an existing ID raises
        DuplicateHypothesisError.

        Args:
            hypothesis: The hypothesis to register.

        Raises:
            DuplicateHypothesisError: If a hypothesis with the same ID exists.
        """
        if hypothesis.id in self._hypotheses:
            raise DuplicateHypothesisError(hypothesis.id)
        self._hypotheses[hypothesis.id] = hypothesis
        logger.debug(f"Registered hypothesis: {hypothesis.id}")

    def unregister(self, hypothesis_id: str) -> bool:
        """Remove hypothesis from registry.

        Args:
            hypothesis_id: The ID of the hypothesis to remove.

        Returns:
            True if the hypothesis was removed, False if not found.
        """
        if hypothesis_id in self._hypotheses:
            del self._hypotheses[hypothesis_id]
            logger.debug(f"Unregistered hypothesis: {hypothesis_id}")
            return True
        return False

    def reload(self) -> None:
        """Reload all hypotheses from loader.

        Clears the registry and loads all hypotheses from the configured
        loader. This replaces any manually registered hypotheses.

        Raises:
            ValueError: If no loader is configured.
        """
        if self._loader is None:
            raise ValueError(
                "Cannot reload: no loader configured. "
                "Initialize registry with a HypothesisLoader to enable reload."
            )

        # Clear existing hypotheses
        self._hypotheses.clear()

        # Load all hypotheses from loader and check for duplicates
        hypotheses = self._loader.load_all_hypotheses()
        for hypothesis in hypotheses:
            if hypothesis.id in self._hypotheses:
                raise DuplicateHypothesisError(
                    f"Duplicate hypothesis ID '{hypothesis.id}' found during reload. "
                    f"Each hypothesis must have a unique ID."
                )
            self._hypotheses[hypothesis.id] = hypothesis
            logger.debug(f"Loaded hypothesis: {hypothesis.id}")

        logger.info(f"Reloaded {len(self._hypotheses)} hypotheses from loader")

    def count(self) -> int:
        """Count total registered hypotheses.

        Returns:
            The total number of hypotheses in the registry.
        """
        return len(self._hypotheses)

    def count_by_status(self, status: HypothesisStatus) -> int:
        """Count hypotheses with specific status.

        Args:
            status: The status to count.

        Returns:
            The number of hypotheses with the specified status.
        """
        return sum(1 for h in self._hypotheses.values() if h.status == status)

    def is_empty(self) -> bool:
        """Check if registry is empty.

        Returns:
            True if the registry has no hypotheses, False otherwise.
        """
        return len(self._hypotheses) == 0


__all__ = [
    "DuplicateHypothesisError",
    "HypothesisRegistry",
]
