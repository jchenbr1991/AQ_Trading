"""Tests for bar loader implementations."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from src.backtest.bar_loader import CSVBarLoader

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_BARS_CSV = FIXTURES_DIR / "sample_bars.csv"


class TestCSVBarLoader:
    """Tests for CSVBarLoader."""

    @pytest.mark.asyncio
    async def test_load_all_bars(self) -> None:
        """Load all 5 bars from sample CSV."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)

        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        assert len(bars) == 5

        # Verify first bar
        assert bars[0].symbol == "AAPL"
        assert bars[0].open == Decimal("150.00")
        assert bars[0].high == Decimal("152.00")
        assert bars[0].low == Decimal("149.00")
        assert bars[0].close == Decimal("151.00")
        assert bars[0].volume == 1000000

        # Verify last bar
        assert bars[4].symbol == "AAPL"
        assert bars[4].open == Decimal("154.50")
        assert bars[4].close == Decimal("155.00")
        assert bars[4].volume == 1050000

    @pytest.mark.asyncio
    async def test_load_date_range(self) -> None:
        """Filter bars by date range - only bars within range are returned."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)

        # Load only bars from Jan 3-7 (should get 3 bars: Jan 3, 6, 7)
        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 3),
            end_date=date(2025, 1, 7),
        )

        assert len(bars) == 3

        # First bar should be Jan 3
        assert bars[0].timestamp.date() == date(2025, 1, 3)
        assert bars[0].close == Decimal("152.50")

        # Last bar should be Jan 7
        assert bars[2].timestamp.date() == date(2025, 1, 7)
        assert bars[2].close == Decimal("154.50")

    @pytest.mark.asyncio
    async def test_bars_are_sorted_ascending(self) -> None:
        """Verify bars are returned in chronological order (oldest first)."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)

        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        # Verify bars are sorted by timestamp ascending
        for i in range(len(bars) - 1):
            assert bars[i].timestamp < bars[i + 1].timestamp, (
                f"Bar at index {i} ({bars[i].timestamp}) should be before "
                f"bar at index {i + 1} ({bars[i + 1].timestamp})"
            )

    @pytest.mark.asyncio
    async def test_bars_are_timezone_aware(self) -> None:
        """Verify all loaded bars have timezone-aware timestamps."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)

        bars = await loader.load(
            symbol="AAPL",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        assert len(bars) > 0, "Expected at least one bar"

        for bar in bars:
            assert (
                bar.timestamp.tzinfo is not None
            ), f"Bar timestamp {bar.timestamp} must be timezone-aware"

    @pytest.mark.asyncio
    async def test_load_wrong_symbol_returns_empty(self) -> None:
        """Loading a symbol not in the CSV returns an empty list."""
        loader = CSVBarLoader(SAMPLE_BARS_CSV)

        bars = await loader.load(
            symbol="MSFT",  # Not in our sample CSV
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        assert bars == []
