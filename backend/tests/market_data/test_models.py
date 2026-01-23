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


class TestSymbolScenario:
    def test_create_symbol_scenario(self):
        """SymbolScenario configures per-symbol behavior."""
        from src.market_data.models import SymbolScenario

        scenario = SymbolScenario(
            symbol="AAPL",
            scenario="volatile",
            base_price=Decimal("150.00"),
            tick_interval_ms=50,
        )

        assert scenario.symbol == "AAPL"
        assert scenario.scenario == "volatile"
        assert scenario.base_price == Decimal("150.00")
        assert scenario.tick_interval_ms == 50

    def test_default_tick_interval(self):
        """SymbolScenario has default tick interval."""
        from src.market_data.models import SymbolScenario

        scenario = SymbolScenario(
            symbol="SPY",
            scenario="flat",
            base_price=Decimal("450.00"),
        )

        assert scenario.tick_interval_ms == 100


class TestFaultConfig:
    def test_default_values(self):
        """FaultConfig has sensible defaults (disabled)."""
        from src.market_data.models import FaultConfig

        config = FaultConfig()

        assert config.enabled is False
        assert config.delay_probability == 0.0
        assert config.delay_ms_range == (100, 500)
        assert config.duplicate_probability == 0.0
        assert config.out_of_order_probability == 0.0
        assert config.out_of_order_offset_ms == 200
        assert config.stale_window_probability == 0.0
        assert config.stale_window_duration_ms == (2000, 5000)

    def test_custom_fault_config(self):
        """FaultConfig accepts custom values."""
        from src.market_data.models import FaultConfig

        config = FaultConfig(
            enabled=True,
            delay_probability=0.1,
            duplicate_probability=0.05,
        )

        assert config.enabled is True
        assert config.delay_probability == 0.1
        assert config.duplicate_probability == 0.05
