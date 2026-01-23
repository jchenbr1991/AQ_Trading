# backend/tests/market_data/test_models.py
"""Tests for market data models."""

from datetime import datetime, timedelta
from decimal import Decimal


class TestQuoteSnapshot:
    def test_create_quote_snapshot(self):
        """QuoteSnapshot holds quote data with system metadata."""
        from src.market_data.models import QuoteSnapshot

        now = datetime.utcnow()
        snapshot = QuoteSnapshot(
            symbol="AAPL",
            price=Decimal("150.25"),
            bid=Decimal("150.20"),
            ask=Decimal("150.30"),
            volume=1000000,
            timestamp=now,
            cached_at=now,
        )

        assert snapshot.symbol == "AAPL"
        assert snapshot.price == Decimal("150.25")
        assert snapshot.bid == Decimal("150.20")
        assert snapshot.ask == Decimal("150.30")
        assert snapshot.volume == 1000000
        assert snapshot.timestamp == now
        assert snapshot.cached_at == now

    def test_is_stale_returns_false_for_fresh_quote(self):
        """Fresh quote is not stale."""
        from src.market_data.models import QuoteSnapshot

        now = datetime.utcnow()
        snapshot = QuoteSnapshot(
            symbol="AAPL",
            price=Decimal("150.00"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            volume=100,
            timestamp=now,
            cached_at=now,
        )

        assert snapshot.is_stale(threshold_ms=5000) is False

    def test_is_stale_returns_true_for_old_quote(self):
        """Old quote is stale based on event-time (timestamp), not cached_at."""
        from src.market_data.models import QuoteSnapshot

        old_time = datetime.utcnow() - timedelta(seconds=10)
        now = datetime.utcnow()
        snapshot = QuoteSnapshot(
            symbol="AAPL",
            price=Decimal("150.00"),
            bid=Decimal("149.90"),
            ask=Decimal("150.10"),
            volume=100,
            timestamp=old_time,  # Event-time is old
            cached_at=now,  # Cached recently, but doesn't matter
        )

        assert snapshot.is_stale(threshold_ms=5000) is True

    def test_from_market_data(self):
        """Create QuoteSnapshot from MarketData."""
        from src.market_data.models import QuoteSnapshot
        from src.strategies.base import MarketData

        now = datetime.utcnow()
        market_data = MarketData(
            symbol="TSLA",
            price=Decimal("250.00"),
            bid=Decimal("249.90"),
            ask=Decimal("250.10"),
            volume=50000,
            timestamp=now,
        )

        snapshot = QuoteSnapshot.from_market_data(market_data)

        assert snapshot.symbol == "TSLA"
        assert snapshot.price == Decimal("250.00")
        assert snapshot.timestamp == now
        assert snapshot.cached_at is not None
