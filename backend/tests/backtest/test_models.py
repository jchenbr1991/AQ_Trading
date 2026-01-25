"""Tests for backtest models."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from src.backtest.models import Bar


class TestBar:
    """Tests for Bar dataclass."""

    def test_create_bar(self) -> None:
        """Create bar and verify all fields are set correctly."""
        timestamp = datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc)
        bar = Bar(
            symbol="AAPL",
            timestamp=timestamp,
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        assert bar.symbol == "AAPL"
        assert bar.timestamp == timestamp
        assert bar.open == Decimal("185.50")
        assert bar.high == Decimal("187.25")
        assert bar.low == Decimal("184.00")
        assert bar.close == Decimal("186.75")
        assert bar.volume == 50_000_000
        assert bar.interval == "1d"  # default value

    def test_bar_is_frozen(self) -> None:
        """Verify Bar is immutable - raises AttributeError when modifying."""
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        with pytest.raises(AttributeError):
            bar.symbol = "MSFT"  # type: ignore[misc]

        with pytest.raises(AttributeError):
            bar.close = Decimal("200.00")  # type: ignore[misc]

    def test_bar_requires_timezone_aware_timestamp(self) -> None:
        """Verify timestamp has tzinfo set (not None).

        Timezone-aware timestamps are required to avoid ambiguity in
        backtesting across different market sessions and data sources.
        """
        bar = Bar(
            symbol="AAPL",
            timestamp=datetime(2024, 1, 15, 16, 0, 0, tzinfo=timezone.utc),
            open=Decimal("185.50"),
            high=Decimal("187.25"),
            low=Decimal("184.00"),
            close=Decimal("186.75"),
            volume=50_000_000,
        )

        # Timestamp must be timezone-aware
        assert bar.timestamp.tzinfo is not None
