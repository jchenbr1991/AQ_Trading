"""Tests for structural filter functionality.

TDD: Write tests FIRST, then implement filters to make them pass.

This module tests:
1. StructuralFilters model creation and validation
2. Each filter type individually
3. Filter combinations
4. Edge cases (empty universe, all symbols excluded)

Requirements from spec.md:
- FR-016: System MUST support structural filters independent of hypotheses:
  - exclude_state_owned_ratio_gte
  - exclude_dividend_yield_gte
  - min_avg_dollar_volume
  - exclude_sectors
  - min_market_cap (additional from data-model.md)
  - max_price (additional from data-model.md)
  - min_price (additional from data-model.md)
"""

from dataclasses import dataclass

import pytest


@dataclass
class SymbolData:
    """Symbol data for structural filter checks.

    This is a simple dataclass used for testing purposes.
    In production, this data would come from a universe data provider.
    """

    symbol: str
    sector: str = ""
    state_owned_ratio: float = 0.0
    dividend_yield: float = 0.0
    avg_dollar_volume: float = 1_000_000.0
    market_cap: float = 1_000_000_000.0
    price: float = 100.0


class TestStructuralFiltersModelCreation:
    """Tests for StructuralFilters Pydantic model creation."""

    def test_structural_filters_creation_empty(self):
        """StructuralFilters should accept empty initialization (all filters off)."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters()

        assert filters.exclude_state_owned_ratio_gte is None
        assert filters.exclude_dividend_yield_gte is None
        assert filters.min_avg_dollar_volume is None
        assert filters.exclude_sectors == []
        assert filters.min_market_cap is None
        assert filters.max_price is None
        assert filters.min_price is None

    def test_structural_filters_creation_full(self):
        """StructuralFilters should accept all filter fields."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(
            exclude_state_owned_ratio_gte=0.5,
            exclude_dividend_yield_gte=0.10,
            min_avg_dollar_volume=100_000_000,
            exclude_sectors=["utilities", "real_estate"],
            min_market_cap=1_000_000_000,
            max_price=500.0,
            min_price=5.0,
        )

        assert filters.exclude_state_owned_ratio_gte == 0.5
        assert filters.exclude_dividend_yield_gte == 0.10
        assert filters.min_avg_dollar_volume == 100_000_000
        assert filters.exclude_sectors == ["utilities", "real_estate"]
        assert filters.min_market_cap == 1_000_000_000
        assert filters.max_price == 500.0
        assert filters.min_price == 5.0

    def test_structural_filters_creation_partial(self):
        """StructuralFilters should accept partial filter specification."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(
            min_avg_dollar_volume=50_000_000,
            exclude_sectors=["materials"],
        )

        assert filters.min_avg_dollar_volume == 50_000_000
        assert filters.exclude_sectors == ["materials"]
        assert filters.exclude_state_owned_ratio_gte is None
        assert filters.min_market_cap is None

    def test_structural_filters_forbids_extra_fields(self):
        """StructuralFilters should reject unknown fields (strict mode)."""
        from pydantic import ValidationError
        from src.governance.pool.models import StructuralFilters

        with pytest.raises(ValidationError) as exc_info:
            StructuralFilters(
                min_avg_dollar_volume=100_000_000,
                unknown_filter=True,  # Should fail
            )

        assert (
            "unknown_filter" in str(exc_info.value).lower()
            or "extra" in str(exc_info.value).lower()
        )


class TestStructuralFiltersValidation:
    """Tests for StructuralFilters field validation."""

    def test_state_owned_ratio_valid_range(self):
        """exclude_state_owned_ratio_gte should accept values 0-1."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_state_owned_ratio_gte=0.0)
        assert filters.exclude_state_owned_ratio_gte == 0.0

        filters = StructuralFilters(exclude_state_owned_ratio_gte=0.5)
        assert filters.exclude_state_owned_ratio_gte == 0.5

        filters = StructuralFilters(exclude_state_owned_ratio_gte=1.0)
        assert filters.exclude_state_owned_ratio_gte == 1.0

    def test_dividend_yield_valid_range(self):
        """exclude_dividend_yield_gte should accept non-negative values."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_dividend_yield_gte=0.0)
        assert filters.exclude_dividend_yield_gte == 0.0

        filters = StructuralFilters(exclude_dividend_yield_gte=0.05)
        assert filters.exclude_dividend_yield_gte == 0.05

        filters = StructuralFilters(exclude_dividend_yield_gte=0.15)
        assert filters.exclude_dividend_yield_gte == 0.15

    def test_min_avg_dollar_volume_non_negative(self):
        """min_avg_dollar_volume should accept non-negative values."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_avg_dollar_volume=0)
        assert filters.min_avg_dollar_volume == 0

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)
        assert filters.min_avg_dollar_volume == 100_000_000

    def test_exclude_sectors_accepts_list(self):
        """exclude_sectors should accept list of sector names."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_sectors=["technology", "healthcare"])
        assert filters.exclude_sectors == ["technology", "healthcare"]

        filters = StructuralFilters(exclude_sectors=[])
        assert filters.exclude_sectors == []

    def test_min_market_cap_non_negative(self):
        """min_market_cap should accept non-negative values."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_market_cap=0)
        assert filters.min_market_cap == 0

        filters = StructuralFilters(min_market_cap=10_000_000_000)
        assert filters.min_market_cap == 10_000_000_000

    def test_price_range_valid(self):
        """min_price and max_price should accept non-negative values."""
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_price=0.0, max_price=1000.0)
        assert filters.min_price == 0.0
        assert filters.max_price == 1000.0


class TestStructuralFiltersExports:
    """Test that StructuralFilters is properly exported."""

    def test_structural_filters_importable(self):
        """StructuralFilters should be importable from pool.models."""
        from src.governance.pool.models import StructuralFilters

        assert StructuralFilters is not None

    def test_structural_filters_inherits_governance_base(self):
        """StructuralFilters should inherit from GovernanceBaseModel."""
        from src.governance.models import GovernanceBaseModel
        from src.governance.pool.models import StructuralFilters

        assert issubclass(StructuralFilters, GovernanceBaseModel)


class TestStructuralFilterApplicatorFixtures:
    """Pytest fixtures for filter applicator tests."""

    @pytest.fixture
    def sample_universe(self):
        """Create a sample universe of symbol data."""
        return [
            SymbolData(
                symbol="AAPL",
                sector="technology",
                state_owned_ratio=0.0,
                dividend_yield=0.005,
                avg_dollar_volume=5_000_000_000,
                market_cap=3_000_000_000_000,
                price=180.0,
            ),
            SymbolData(
                symbol="MSFT",
                sector="technology",
                state_owned_ratio=0.0,
                dividend_yield=0.008,
                avg_dollar_volume=4_000_000_000,
                market_cap=2_800_000_000_000,
                price=400.0,
            ),
            SymbolData(
                symbol="JPM",
                sector="financials",
                state_owned_ratio=0.0,
                dividend_yield=0.025,
                avg_dollar_volume=2_000_000_000,
                market_cap=500_000_000_000,
                price=200.0,
            ),
            SymbolData(
                symbol="XYZ",
                sector="materials",
                state_owned_ratio=0.0,
                dividend_yield=0.01,
                avg_dollar_volume=50_000,  # Very low volume
                market_cap=10_000_000,  # Small cap
                price=5.0,
            ),
            SymbolData(
                symbol="STATEOWN",
                sector="utilities",
                state_owned_ratio=0.8,  # State-owned
                dividend_yield=0.03,
                avg_dollar_volume=500_000_000,
                market_cap=50_000_000_000,
                price=45.0,
            ),
            SymbolData(
                symbol="HIGHDIV",
                sector="utilities",
                state_owned_ratio=0.1,
                dividend_yield=0.12,  # High dividend yield
                avg_dollar_volume=200_000_000,
                market_cap=30_000_000_000,
                price=25.0,
            ),
            SymbolData(
                symbol="PENNY",
                sector="technology",
                state_owned_ratio=0.0,
                dividend_yield=0.0,
                avg_dollar_volume=100_000_000,
                market_cap=50_000_000,
                price=0.50,  # Penny stock
            ),
            SymbolData(
                symbol="EXPENSIVE",
                sector="consumer",
                state_owned_ratio=0.0,
                dividend_yield=0.001,
                avg_dollar_volume=1_000_000_000,
                market_cap=800_000_000_000,
                price=3500.0,  # Very expensive
            ),
        ]


class TestStructuralFilterApplicator(TestStructuralFilterApplicatorFixtures):
    """Tests for structural filter application logic."""

    def test_applicator_no_filters_passes_all(self, sample_universe):
        """Filter applicator with no filters should pass all symbols."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters()  # No filters

        passed, excluded = apply_structural_filters(sample_universe, filters)

        assert len(passed) == len(sample_universe)
        assert len(excluded) == 0

    def test_applicator_min_volume_filter(self, sample_universe):
        """Filter applicator should exclude symbols below min volume."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # XYZ has 50K volume, should be excluded
        assert "XYZ" in excluded_symbols
        assert "XYZ" not in passed_symbols

        # AAPL has 5B volume, should pass
        assert "AAPL" in passed_symbols

    def test_applicator_state_owned_filter(self, sample_universe):
        """Filter applicator should exclude state-owned symbols."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_state_owned_ratio_gte=0.5)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # STATEOWN has 0.8 ratio, should be excluded
        assert "STATEOWN" in excluded_symbols
        assert "STATEOWN" not in passed_symbols

        # AAPL has 0.0 ratio, should pass
        assert "AAPL" in passed_symbols

    def test_applicator_dividend_yield_filter(self, sample_universe):
        """Filter applicator should exclude high dividend yield symbols."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_dividend_yield_gte=0.10)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # HIGHDIV has 0.12 yield, should be excluded
        assert "HIGHDIV" in excluded_symbols
        assert "HIGHDIV" not in passed_symbols

        # AAPL has 0.005 yield, should pass
        assert "AAPL" in passed_symbols

    def test_applicator_sector_exclusion_filter(self, sample_universe):
        """Filter applicator should exclude specified sectors."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_sectors=["utilities", "materials"])

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # STATEOWN, HIGHDIV are utilities, should be excluded
        assert "STATEOWN" in excluded_symbols
        assert "HIGHDIV" in excluded_symbols

        # XYZ is materials, should be excluded
        assert "XYZ" in excluded_symbols

        # AAPL is technology, should pass
        assert "AAPL" in passed_symbols

    def test_applicator_market_cap_filter(self, sample_universe):
        """Filter applicator should exclude symbols below min market cap."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_market_cap=100_000_000_000)  # 100B

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # AAPL: 3T, MSFT: 2.8T, JPM: 500B, EXPENSIVE: 800B should pass
        assert "AAPL" in passed_symbols
        assert "MSFT" in passed_symbols
        assert "JPM" in passed_symbols
        assert "EXPENSIVE" in passed_symbols

        # XYZ: 10M, PENNY: 50M, STATEOWN: 50B, HIGHDIV: 30B should fail
        assert "XYZ" in excluded_symbols
        assert "PENNY" in excluded_symbols
        assert "STATEOWN" in excluded_symbols
        assert "HIGHDIV" in excluded_symbols

    def test_applicator_min_price_filter(self, sample_universe):
        """Filter applicator should exclude symbols below min price."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_price=10.0)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # PENNY: $0.50, XYZ: $5 should be excluded
        assert "PENNY" in excluded_symbols
        assert "XYZ" in excluded_symbols

        # AAPL: $180 should pass
        assert "AAPL" in passed_symbols

    def test_applicator_max_price_filter(self, sample_universe):
        """Filter applicator should exclude symbols above max price."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(max_price=500.0)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # EXPENSIVE: $3500 should be excluded
        assert "EXPENSIVE" in excluded_symbols

        # AAPL: $180, MSFT: $400 should pass
        assert "AAPL" in passed_symbols
        assert "MSFT" in passed_symbols

    def test_applicator_price_range_filter(self, sample_universe):
        """Filter applicator should exclude symbols outside price range."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_price=20.0, max_price=300.0)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # PENNY: $0.50, XYZ: $5 should be excluded (below min)
        assert "PENNY" in excluded_symbols
        assert "XYZ" in excluded_symbols

        # MSFT: $400, EXPENSIVE: $3500 should be excluded (above max)
        assert "MSFT" in excluded_symbols
        assert "EXPENSIVE" in excluded_symbols

        # AAPL: $180, JPM: $200 should pass
        assert "AAPL" in passed_symbols
        assert "JPM" in passed_symbols


class TestStructuralFilterApplicatorCombinations(TestStructuralFilterApplicatorFixtures):
    """Tests for combined structural filter application."""

    def test_applicator_multiple_filters_and(self, sample_universe):
        """Multiple filters should be applied with AND logic."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(
            min_avg_dollar_volume=100_000_000,  # Excludes XYZ
            exclude_sectors=["utilities"],  # Excludes STATEOWN, HIGHDIV
            min_price=10.0,  # Excludes PENNY
            max_price=500.0,  # Excludes EXPENSIVE
        )

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}

        # Should only pass: AAPL, MSFT, JPM
        assert passed_symbols == {"AAPL", "MSFT", "JPM"}

    def test_applicator_comprehensive_filters(self, sample_universe):
        """Comprehensive filters should work correctly together."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(
            exclude_state_owned_ratio_gte=0.5,
            exclude_dividend_yield_gte=0.10,
            min_avg_dollar_volume=100_000_000,
            exclude_sectors=["materials"],
            min_market_cap=100_000_000_000,
            min_price=10.0,
            max_price=500.0,
        )

        passed, excluded = apply_structural_filters(sample_universe, filters)

        passed_symbols = {sd.symbol for sd in passed}

        # AAPL: passes all (tech, 0%, 0.5%, 5B vol, 3T cap, $180)
        # MSFT: fails max_price ($400 is within 500, so passes) - passes all
        # JPM: passes all (financials, 0%, 2.5%, 2B vol, 500B cap, $200)
        # XYZ: fails volume (50K), sector (materials), market_cap, min_price
        # STATEOWN: fails state_owned (0.8), market_cap (50B)
        # HIGHDIV: fails dividend (0.12), market_cap (30B)
        # PENNY: fails volume, market_cap, min_price ($0.50)
        # EXPENSIVE: fails max_price ($3500)

        assert "AAPL" in passed_symbols
        assert "MSFT" in passed_symbols
        assert "JPM" in passed_symbols
        assert "XYZ" not in passed_symbols
        assert "STATEOWN" not in passed_symbols
        assert "HIGHDIV" not in passed_symbols
        assert "PENNY" not in passed_symbols
        assert "EXPENSIVE" not in passed_symbols


class TestStructuralFilterApplicatorExclusionReasons(TestStructuralFilterApplicatorFixtures):
    """Tests for exclusion reason tracking."""

    def test_applicator_returns_exclusion_reasons(self, sample_universe):
        """Filter applicator should return reasons for exclusions."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        # excluded should be list of (symbol_data, reason) tuples
        assert len(excluded) > 0

        # Find XYZ exclusion
        xyz_exclusions = [(sd, reason) for sd, reason in excluded if sd.symbol == "XYZ"]
        assert len(xyz_exclusions) == 1

        sd, reason = xyz_exclusions[0]
        assert "volume" in reason.lower() or "min_avg_dollar_volume" in reason

    def test_applicator_tracks_first_failed_filter(self, sample_universe):
        """Filter applicator should track the first filter that failed."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(
            min_avg_dollar_volume=100_000_000,
            exclude_sectors=["materials"],
        )

        passed, excluded = apply_structural_filters(sample_universe, filters)

        # XYZ fails both volume and sector
        xyz_exclusions = [(sd, reason) for sd, reason in excluded if sd.symbol == "XYZ"]
        assert len(xyz_exclusions) == 1

        # Should have at least one reason
        sd, reason = xyz_exclusions[0]
        assert reason is not None
        assert len(reason) > 0


class TestStructuralFilterApplicatorEdgeCases(TestStructuralFilterApplicatorFixtures):
    """Tests for edge cases in filter application."""

    def test_applicator_empty_universe(self):
        """Filter applicator should handle empty universe."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)

        passed, excluded = apply_structural_filters([], filters)

        assert len(passed) == 0
        assert len(excluded) == 0

    def test_applicator_all_excluded(self, sample_universe):
        """Filter applicator should handle all symbols being excluded."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        # Filter that excludes everything
        filters = StructuralFilters(min_avg_dollar_volume=1_000_000_000_000_000)

        passed, excluded = apply_structural_filters(sample_universe, filters)

        assert len(passed) == 0
        assert len(excluded) == len(sample_universe)

    def test_applicator_boundary_values(self):
        """Filter applicator should handle boundary values correctly."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        # Symbol exactly at threshold
        universe = [
            SymbolData(symbol="EXACT", avg_dollar_volume=100_000_000),
            SymbolData(symbol="BELOW", avg_dollar_volume=99_999_999),
            SymbolData(symbol="ABOVE", avg_dollar_volume=100_000_001),
        ]

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)

        passed, excluded = apply_structural_filters(universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # EXACT (exactly at threshold) should pass (>=)
        assert "EXACT" in passed_symbols
        # ABOVE should pass
        assert "ABOVE" in passed_symbols
        # BELOW should fail
        assert "BELOW" in excluded_symbols

    def test_applicator_state_owned_boundary(self):
        """State-owned filter should handle boundary values correctly."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        universe = [
            SymbolData(symbol="EXACT", state_owned_ratio=0.5),
            SymbolData(symbol="BELOW", state_owned_ratio=0.49),
            SymbolData(symbol="ABOVE", state_owned_ratio=0.51),
        ]

        filters = StructuralFilters(exclude_state_owned_ratio_gte=0.5)

        passed, excluded = apply_structural_filters(universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # EXACT (exactly at threshold) should be excluded (>=)
        assert "EXACT" in excluded_symbols
        # BELOW should pass
        assert "BELOW" in passed_symbols
        # ABOVE should be excluded
        assert "ABOVE" in excluded_symbols

    def test_applicator_dividend_yield_boundary(self):
        """Dividend yield filter should handle boundary values correctly."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        universe = [
            SymbolData(symbol="EXACT", dividend_yield=0.10),
            SymbolData(symbol="BELOW", dividend_yield=0.099),
            SymbolData(symbol="ABOVE", dividend_yield=0.101),
        ]

        filters = StructuralFilters(exclude_dividend_yield_gte=0.10)

        passed, excluded = apply_structural_filters(universe, filters)

        passed_symbols = {sd.symbol for sd in passed}
        excluded_symbols = {item[0].symbol for item in excluded}

        # EXACT (exactly at threshold) should be excluded (>=)
        assert "EXACT" in excluded_symbols
        # BELOW should pass
        assert "BELOW" in passed_symbols
        # ABOVE should be excluded
        assert "ABOVE" in excluded_symbols

    def test_applicator_empty_sector_list(self, sample_universe):
        """Empty exclude_sectors list should not exclude any sectors."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        filters = StructuralFilters(exclude_sectors=[])

        passed, excluded = apply_structural_filters(sample_universe, filters)

        # Should not exclude anything due to sector
        sector_exclusions = [item for item in excluded if "sector" in item[1].lower()]
        assert len(sector_exclusions) == 0

    def test_applicator_case_sensitivity_sectors(self, sample_universe):
        """Sector exclusion should handle case sensitivity appropriately."""
        from src.governance.pool.filters import apply_structural_filters
        from src.governance.pool.models import StructuralFilters

        # Test with different case
        filters = StructuralFilters(exclude_sectors=["Technology"])

        passed, excluded = apply_structural_filters(sample_universe, filters)

        # Depending on implementation, may or may not exclude technology
        # This test documents expected behavior
        # Implementation should decide: case-sensitive or case-insensitive


class TestStructuralFilterApplicatorExports:
    """Test that filter applicator is properly exported."""

    def test_apply_structural_filters_importable(self):
        """apply_structural_filters should be importable from pool.filters."""
        from src.governance.pool.filters import apply_structural_filters

        assert apply_structural_filters is not None
        assert callable(apply_structural_filters)


class TestStructuralFiltersIntegration:
    """Integration tests for structural filters with pool builder."""

    def test_filters_work_with_pool_builder(self):
        """StructuralFilters should integrate with PoolBuilder."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.pool.builder import PoolBuilder
        from src.governance.pool.models import StructuralFilters

        universe = [
            SymbolData(symbol="HIGH_VOL", avg_dollar_volume=1_000_000_000),
            SymbolData(symbol="LOW_VOL", avg_dollar_volume=1_000),
        ]

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)

        registry = HypothesisRegistry()
        builder = PoolBuilder(hypothesis_registry=registry)

        result = builder.build(universe=universe, filters=filters)

        assert "HIGH_VOL" in result.symbols
        assert "LOW_VOL" not in result.symbols

    def test_filters_audit_trail_in_pool(self):
        """Filter exclusions should appear in pool audit trail."""
        from src.governance.hypothesis.registry import HypothesisRegistry
        from src.governance.pool.builder import PoolBuilder
        from src.governance.pool.models import StructuralFilters

        universe = [
            SymbolData(symbol="INCLUDED", avg_dollar_volume=1_000_000_000),
            SymbolData(symbol="EXCLUDED", avg_dollar_volume=1_000),
        ]

        filters = StructuralFilters(min_avg_dollar_volume=100_000_000)

        registry = HypothesisRegistry()
        builder = PoolBuilder(hypothesis_registry=registry)

        result = builder.build(universe=universe, filters=filters)

        # Find audit entry for EXCLUDED
        excluded_entries = [e for e in result.audit_trail if e.symbol == "EXCLUDED"]
        assert len(excluded_entries) >= 1
        assert excluded_entries[0].action == "excluded"
