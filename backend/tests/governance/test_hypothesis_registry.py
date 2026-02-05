"""Tests for hypothesis registry.

TDD: Write tests FIRST, then implement registry to make them pass.

This module tests the HypothesisRegistry class which:
1. Stores loaded hypotheses in memory
2. Provides query methods: get by ID, filter by status
3. Supports reloading from disk
4. Tracks active hypotheses efficiently
"""

from datetime import date
from unittest.mock import MagicMock

import pytest


class TestHypothesisRegistryFixtures:
    """Pytest fixtures for HypothesisRegistry tests."""

    @pytest.fixture
    def sample_hypothesis_active(self):
        """Create a sample ACTIVE hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="momentum_persistence",
            title="Momentum Persistence Hypothesis",
            statement="Strong price momentum tends to persist over 3-6 month horizons.",
            scope=HypothesisScope(symbols=[], sectors=["technology"]),
            owner="human",
            status=HypothesisStatus.ACTIVE,
            review_cycle="quarterly",
            created_at=date(2025, 1, 15),
            evidence=Evidence(sources=["https://example.com/paper"], notes="Research paper."),
            falsifiers=[
                Falsifier(
                    metric="rolling_ic_mean",
                    operator=ComparisonOperator.LT,
                    threshold=0.0,
                    window="4q",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=["momentum_constraint"],
        )

    @pytest.fixture
    def sample_hypothesis_draft(self):
        """Create a sample DRAFT hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="value_reversion",
            title="Value Reversion Hypothesis",
            statement="High P/E stocks underperform over long horizons.",
            scope=HypothesisScope(symbols=[], sectors=[]),
            owner="human",
            status=HypothesisStatus.DRAFT,
            review_cycle="yearly",
            created_at=date(2025, 2, 1),
            evidence=Evidence(sources=[], notes=""),
            falsifiers=[
                Falsifier(
                    metric="long_term_alpha",
                    operator=ComparisonOperator.LT,
                    threshold=-0.02,
                    window="5y",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def sample_hypothesis_sunset(self):
        """Create a sample SUNSET hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="mean_reversion_short",
            title="Short-term Mean Reversion",
            statement="Prices revert to mean within 5 days.",
            scope=HypothesisScope(symbols=["AAPL", "MSFT"], sectors=[]),
            owner="human",
            status=HypothesisStatus.SUNSET,
            review_cycle="30d",
            created_at=date(2024, 12, 1),
            evidence=Evidence(sources=[], notes="Failed falsifier check."),
            falsifiers=[
                Falsifier(
                    metric="win_rate",
                    operator=ComparisonOperator.LT,
                    threshold=0.5,
                    window="90d",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=["mean_reversion_constraint"],
        )

    @pytest.fixture
    def sample_hypothesis_rejected(self):
        """Create a sample REJECTED hypothesis for testing."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="calendar_effect",
            title="Calendar Effect Hypothesis",
            statement="January has higher returns than other months.",
            scope=HypothesisScope(symbols=[], sectors=[]),
            owner="human",
            status=HypothesisStatus.REJECTED,
            review_cycle="yearly",
            created_at=date(2024, 1, 1),
            evidence=Evidence(sources=[], notes="Rejected after review."),
            falsifiers=[
                Falsifier(
                    metric="january_alpha",
                    operator=ComparisonOperator.LTE,
                    threshold=0.0,
                    window="3y",
                    trigger=TriggerAction.SUNSET,
                )
            ],
            linked_constraints=[],
        )

    @pytest.fixture
    def sample_hypothesis_active_second(self):
        """Create another ACTIVE hypothesis for testing multiple active hypotheses."""
        from src.governance.hypothesis.models import (
            Evidence,
            Falsifier,
            Hypothesis,
            HypothesisScope,
        )
        from src.governance.models import (
            ComparisonOperator,
            HypothesisStatus,
            TriggerAction,
        )

        return Hypothesis(
            id="quality_factor",
            title="Quality Factor Hypothesis",
            statement="High quality companies outperform over long horizons.",
            scope=HypothesisScope(symbols=[], sectors=["financials", "industrials"]),
            owner="human",
            status=HypothesisStatus.ACTIVE,
            review_cycle="quarterly",
            created_at=date(2025, 1, 20),
            evidence=Evidence(sources=["https://example.com/quality"], notes="Quality research."),
            falsifiers=[
                Falsifier(
                    metric="quality_ic",
                    operator=ComparisonOperator.LT,
                    threshold=0.0,
                    window="1y",
                    trigger=TriggerAction.REVIEW,
                )
            ],
            linked_constraints=["quality_constraint"],
        )


class TestHypothesisRegistryGetById(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.get() method."""

    def test_registry_get_by_id(self, sample_hypothesis_active):
        """get() should return hypothesis by ID when it exists."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)

        result = registry.get("momentum_persistence")

        assert result is not None
        assert result.id == "momentum_persistence"
        assert result.title == "Momentum Persistence Hypothesis"

    def test_registry_get_by_id_not_found(self):
        """get() should return None for unknown ID."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        result = registry.get("nonexistent_hypothesis")

        assert result is None


class TestHypothesisRegistryListAll(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.list_all() method."""

    def test_registry_list_all(
        self,
        sample_hypothesis_active,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
    ):
        """list_all() should return all registered hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)

        result = registry.list_all()

        assert len(result) == 3
        ids = {h.id for h in result}
        assert "momentum_persistence" in ids
        assert "value_reversion" in ids
        assert "mean_reversion_short" in ids

    def test_registry_list_all_empty(self):
        """list_all() should return empty list when registry is empty."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        result = registry.list_all()

        assert result == []


class TestHypothesisRegistryFilterByStatus(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.filter_by_status() method."""

    def test_registry_filter_by_status(
        self,
        sample_hypothesis_active,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
        sample_hypothesis_rejected,
    ):
        """filter_by_status() should return hypotheses matching single status."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.models import HypothesisStatus

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)
        registry.register(sample_hypothesis_rejected)

        # Filter by ACTIVE
        active_results = registry.filter_by_status(HypothesisStatus.ACTIVE)
        assert len(active_results) == 1
        assert active_results[0].id == "momentum_persistence"

        # Filter by DRAFT
        draft_results = registry.filter_by_status(HypothesisStatus.DRAFT)
        assert len(draft_results) == 1
        assert draft_results[0].id == "value_reversion"

        # Filter by SUNSET
        sunset_results = registry.filter_by_status(HypothesisStatus.SUNSET)
        assert len(sunset_results) == 1
        assert sunset_results[0].id == "mean_reversion_short"

        # Filter by REJECTED
        rejected_results = registry.filter_by_status(HypothesisStatus.REJECTED)
        assert len(rejected_results) == 1
        assert rejected_results[0].id == "calendar_effect"

    def test_registry_filter_by_multiple_statuses(
        self,
        sample_hypothesis_active,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
        sample_hypothesis_rejected,
    ):
        """filter_by_status() should return hypotheses matching multiple statuses."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.models import HypothesisStatus

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)
        registry.register(sample_hypothesis_rejected)

        # Filter by ACTIVE and DRAFT
        results = registry.filter_by_status(HypothesisStatus.ACTIVE, HypothesisStatus.DRAFT)
        assert len(results) == 2
        ids = {h.id for h in results}
        assert "momentum_persistence" in ids
        assert "value_reversion" in ids

        # Filter by SUNSET and REJECTED
        inactive_results = registry.filter_by_status(
            HypothesisStatus.SUNSET, HypothesisStatus.REJECTED
        )
        assert len(inactive_results) == 2
        inactive_ids = {h.id for h in inactive_results}
        assert "mean_reversion_short" in inactive_ids
        assert "calendar_effect" in inactive_ids

    def test_registry_filter_by_status_no_matches(self, sample_hypothesis_active):
        """filter_by_status() should return empty list when no hypotheses match."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.models import HypothesisStatus

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)

        results = registry.filter_by_status(HypothesisStatus.REJECTED)

        assert results == []


class TestHypothesisRegistryGetActive(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.get_active() convenience method."""

    def test_registry_get_active_hypotheses(
        self,
        sample_hypothesis_active,
        sample_hypothesis_active_second,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
    ):
        """get_active() should return only ACTIVE hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_active_second)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)

        results = registry.get_active()

        assert len(results) == 2
        ids = {h.id for h in results}
        assert "momentum_persistence" in ids
        assert "quality_factor" in ids
        # Verify none of the non-active hypotheses are included
        assert "value_reversion" not in ids
        assert "mean_reversion_short" not in ids

    def test_registry_get_active_empty(self, sample_hypothesis_draft, sample_hypothesis_sunset):
        """get_active() should return empty list when no ACTIVE hypotheses exist."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)

        results = registry.get_active()

        assert results == []


class TestHypothesisRegistryRegister(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.register() method."""

    def test_registry_register_hypothesis(self, sample_hypothesis_active):
        """register() should add hypothesis to registry."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        registry.register(sample_hypothesis_active)

        assert registry.count() == 1
        assert registry.get("momentum_persistence") is not None

    def test_registry_register_duplicate_id_raises(self, sample_hypothesis_active):
        """register() should raise error for duplicate hypothesis ID."""
        from src.governance.hypothesis.registry import (
            DuplicateHypothesisError,
            HypothesisRegistry,
        )

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)

        with pytest.raises(DuplicateHypothesisError) as exc_info:
            registry.register(sample_hypothesis_active)

        assert "momentum_persistence" in str(exc_info.value)

    def test_registry_register_multiple(self, sample_hypothesis_active, sample_hypothesis_draft):
        """register() should handle multiple different hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)

        assert registry.count() == 2


class TestHypothesisRegistryUnregister(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.unregister() method."""

    def test_registry_unregister_hypothesis(
        self, sample_hypothesis_active, sample_hypothesis_draft
    ):
        """unregister() should remove hypothesis from registry."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)

        result = registry.unregister("momentum_persistence")

        assert result is True
        assert registry.count() == 1
        assert registry.get("momentum_persistence") is None
        assert registry.get("value_reversion") is not None

    def test_registry_unregister_nonexistent(self):
        """unregister() should return False for nonexistent hypothesis."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        result = registry.unregister("nonexistent_hypothesis")

        assert result is False


class TestHypothesisRegistryReload(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.reload() method."""

    def test_registry_reload_from_loader(self, sample_hypothesis_active, sample_hypothesis_draft):
        """reload() should clear and reload all hypotheses from loader."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        # Create a mock loader
        mock_loader = MagicMock()
        mock_loader.load_all_hypotheses.return_value = [
            sample_hypothesis_active,
            sample_hypothesis_draft,
        ]

        registry = HypothesisRegistry(loader=mock_loader)

        # Reload should populate the registry
        registry.reload()

        assert registry.count() == 2
        assert registry.get("momentum_persistence") is not None
        assert registry.get("value_reversion") is not None
        mock_loader.load_all_hypotheses.assert_called_once()

    def test_registry_reload_clears_existing(
        self, sample_hypothesis_active, sample_hypothesis_draft, sample_hypothesis_sunset
    ):
        """reload() should clear existing hypotheses before loading new ones."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        # Create a mock loader that returns only one hypothesis
        mock_loader = MagicMock()
        mock_loader.load_all_hypotheses.return_value = [sample_hypothesis_active]

        registry = HypothesisRegistry(loader=mock_loader)

        # Manually add some hypotheses
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)
        assert registry.count() == 2

        # Reload should replace with loader's hypotheses
        registry.reload()

        assert registry.count() == 1
        assert registry.get("momentum_persistence") is not None
        assert registry.get("value_reversion") is None
        assert registry.get("mean_reversion_short") is None

    def test_registry_reload_without_loader_raises(self):
        """reload() should raise error when no loader is configured."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()  # No loader

        with pytest.raises(ValueError) as exc_info:
            registry.reload()

        assert "loader" in str(exc_info.value).lower()

    def test_registry_reload_duplicate_id_raises(self, sample_hypothesis_active):
        """reload() should raise DuplicateHypothesisError for duplicate IDs across files."""
        from src.governance.hypothesis.registry import (
            DuplicateHypothesisError,
            HypothesisRegistry,
        )

        # Create a mock loader that returns two hypotheses with the same ID
        mock_loader = MagicMock()
        # Both hypotheses have the same ID "momentum_persistence"
        mock_loader.load_all_hypotheses.return_value = [
            sample_hypothesis_active,
            sample_hypothesis_active,  # Same hypothesis (same ID)
        ]

        registry = HypothesisRegistry(loader=mock_loader)

        with pytest.raises(DuplicateHypothesisError) as exc_info:
            registry.reload()

        assert "momentum_persistence" in str(exc_info.value)
        assert "duplicate" in str(exc_info.value).lower()


class TestHypothesisRegistryCount(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.count() and count_by_status() methods."""

    def test_registry_count(
        self,
        sample_hypothesis_active,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
    ):
        """count() should return total number of hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)

        assert registry.count() == 3

    def test_registry_count_empty(self):
        """count() should return 0 for empty registry."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        assert registry.count() == 0

    def test_registry_count_by_status(
        self,
        sample_hypothesis_active,
        sample_hypothesis_active_second,
        sample_hypothesis_draft,
        sample_hypothesis_sunset,
        sample_hypothesis_rejected,
    ):
        """count_by_status() should return count for specific status."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.models import HypothesisStatus

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)
        registry.register(sample_hypothesis_active_second)
        registry.register(sample_hypothesis_draft)
        registry.register(sample_hypothesis_sunset)
        registry.register(sample_hypothesis_rejected)

        assert registry.count_by_status(HypothesisStatus.ACTIVE) == 2
        assert registry.count_by_status(HypothesisStatus.DRAFT) == 1
        assert registry.count_by_status(HypothesisStatus.SUNSET) == 1
        assert registry.count_by_status(HypothesisStatus.REJECTED) == 1

    def test_registry_count_by_status_zero(self, sample_hypothesis_active):
        """count_by_status() should return 0 when no hypotheses have that status."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.models import HypothesisStatus

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)

        assert registry.count_by_status(HypothesisStatus.REJECTED) == 0


class TestHypothesisRegistryIsEmpty(TestHypothesisRegistryFixtures):
    """Tests for HypothesisRegistry.is_empty() method."""

    def test_registry_is_empty_true(self):
        """is_empty() should return True for empty registry."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        assert registry.is_empty() is True

    def test_registry_is_empty_false(self, sample_hypothesis_active):
        """is_empty() should return False when registry has hypotheses."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()
        registry.register(sample_hypothesis_active)

        assert registry.is_empty() is False


class TestHypothesisRegistryInitialization:
    """Tests for HypothesisRegistry initialization."""

    def test_registry_init_without_loader(self):
        """Registry should initialize without a loader."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        registry = HypothesisRegistry()

        assert registry.is_empty()

    def test_registry_init_with_loader(self):
        """Registry should initialize with a loader but not auto-load."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        mock_loader = MagicMock()

        registry = HypothesisRegistry(loader=mock_loader)

        # Should not auto-load on init
        mock_loader.load_all_hypotheses.assert_not_called()
        assert registry.is_empty()


class TestHypothesisRegistryExports:
    """Test that all required types are exported."""

    def test_hypothesis_registry_importable(self):
        """HypothesisRegistry should be importable from the registry module."""
        from src.governance.hypothesis.registry import HypothesisRegistry

        assert HypothesisRegistry is not None

    def test_duplicate_hypothesis_error_importable(self):
        """DuplicateHypothesisError should be importable from the registry module."""
        from src.governance.hypothesis.registry import DuplicateHypothesisError

        assert DuplicateHypothesisError is not None
        assert issubclass(DuplicateHypothesisError, Exception)

    def test_hypothesis_registry_in_module_exports(self):
        """HypothesisRegistry should eventually be exported from hypothesis __init__."""
        # This test will pass once the registry is implemented and added to __init__.py
        try:
            from src.governance.hypothesis import HypothesisRegistry

            assert HypothesisRegistry is not None
        except ImportError:
            # Expected to fail until registry is implemented
            pytest.skip("HypothesisRegistry not yet exported from hypothesis module")
