"""Tests for reconciliation comparison logic."""

from decimal import Decimal

import pytest
from src.broker.query import BrokerAccount, BrokerPosition
from src.models.position import AssetType, Position
from src.reconciliation.comparator import Comparator
from src.reconciliation.models import (
    DiscrepancySeverity,
    DiscrepancyType,
    ReconciliationConfig,
)


@pytest.fixture
def config():
    return ReconciliationConfig(account_id="ACC001")


@pytest.fixture
def comparator(config):
    return Comparator(config)


class TestPositionComparison:
    def test_no_discrepancies_when_matching(self, comparator):
        """Matching positions produce no discrepancies."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150.00"),
                market_value=Decimal("15500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert discrepancies == []

    def test_missing_local_detected(self, comparator):
        """Detects when broker has position we don't."""
        local = []
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("150.00"),
                market_value=Decimal("15500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.MISSING_LOCAL
        assert discrepancies[0].severity == DiscrepancySeverity.CRITICAL
        assert discrepancies[0].symbol == "AAPL"
        assert discrepancies[0].local_value is None
        assert discrepancies[0].broker_value == 100

    def test_missing_broker_detected(self, comparator):
        """Detects when we have position broker doesn't."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = []
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.MISSING_BROKER
        assert discrepancies[0].severity == DiscrepancySeverity.CRITICAL
        assert discrepancies[0].symbol == "AAPL"
        assert discrepancies[0].local_value == 100
        assert discrepancies[0].broker_value is None

    def test_quantity_mismatch_detected(self, comparator):
        """Detects quantity differences."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=90,
                avg_cost=Decimal("150.00"),
                market_value=Decimal("13500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.QUANTITY_MISMATCH
        assert discrepancies[0].severity == DiscrepancySeverity.CRITICAL
        assert discrepancies[0].local_value == 100
        assert discrepancies[0].broker_value == 90

    def test_cost_mismatch_informational(self, comparator):
        """Cost mismatch is INFO severity."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=100,
                avg_cost=Decimal("151.00"),  # Different cost
                market_value=Decimal("15500.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        assert len(discrepancies) == 1
        assert discrepancies[0].type == DiscrepancyType.COST_MISMATCH
        assert discrepancies[0].severity == DiscrepancySeverity.INFO

    def test_multiple_discrepancies(self, comparator):
        """Handles multiple symbols with various issues."""
        local = [
            _make_local_position("AAPL", 100, Decimal("150.00")),
            _make_local_position("GOOG", 50, Decimal("2800.00")),
        ]
        broker = [
            BrokerPosition(
                symbol="AAPL",
                quantity=90,  # Mismatch
                avg_cost=Decimal("150.00"),
                market_value=Decimal("13500.00"),
                asset_type=AssetType.STOCK,
            ),
            BrokerPosition(
                symbol="TSLA",  # Missing local
                quantity=25,
                avg_cost=Decimal("200.00"),
                market_value=Decimal("5000.00"),
                asset_type=AssetType.STOCK,
            ),
        ]
        discrepancies = comparator.compare_positions(local, broker)
        # AAPL quantity mismatch, GOOG missing broker, TSLA missing local
        assert len(discrepancies) == 3


def _make_local_position(symbol: str, quantity: int, avg_cost: Decimal) -> Position:
    """Helper to create Position for tests."""
    pos = Position()
    pos.symbol = symbol
    pos.quantity = quantity
    pos.avg_cost = avg_cost
    pos.asset_type = AssetType.STOCK
    pos.account_id = "ACC001"
    return pos


class TestAccountComparison:
    def test_cash_within_tolerance_ok(self, comparator):
        """Cash difference within tolerance produces no discrepancy."""
        local_cash = Decimal("10000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10000.50"),  # $0.50 diff, within $1 tolerance
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("50000.00"),
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(local_cash, Decimal("50000.00"), broker)
        cash_discrepancies = [d for d in discrepancies if d.type == DiscrepancyType.CASH_MISMATCH]
        assert cash_discrepancies == []

    def test_cash_outside_tolerance_flagged(self, comparator):
        """Cash difference outside tolerance is flagged."""
        local_cash = Decimal("10000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10005.00"),  # $5 diff, outside $1 tolerance
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("50000.00"),
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(local_cash, Decimal("50000.00"), broker)
        cash_discrepancies = [d for d in discrepancies if d.type == DiscrepancyType.CASH_MISMATCH]
        assert len(cash_discrepancies) == 1
        assert cash_discrepancies[0].severity == DiscrepancySeverity.WARNING

    def test_equity_within_tolerance_ok(self, comparator):
        """Equity difference within percentage tolerance produces no discrepancy."""
        local_equity = Decimal("100000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10000.00"),
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("100050.00"),  # 0.05% diff, within 0.1%
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(Decimal("10000.00"), local_equity, broker)
        equity_discrepancies = [
            d for d in discrepancies if d.type == DiscrepancyType.EQUITY_MISMATCH
        ]
        assert equity_discrepancies == []

    def test_equity_outside_tolerance_flagged(self, comparator):
        """Equity difference outside percentage tolerance is flagged."""
        local_equity = Decimal("100000.00")
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10000.00"),
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("100500.00"),  # 0.5% diff, outside 0.1%
            margin_used=Decimal("0.00"),
        )
        discrepancies = comparator.compare_account(Decimal("10000.00"), local_equity, broker)
        equity_discrepancies = [
            d for d in discrepancies if d.type == DiscrepancyType.EQUITY_MISMATCH
        ]
        assert len(equity_discrepancies) == 1
        assert equity_discrepancies[0].severity == DiscrepancySeverity.WARNING

    def test_custom_tolerance(self):
        """Uses custom tolerances from config."""
        config = ReconciliationConfig(
            account_id="ACC001",
            cash_tolerance=Decimal("10.00"),  # $10 tolerance
            equity_tolerance_pct=Decimal("1.0"),  # 1% tolerance
        )
        comp = Comparator(config)
        broker = BrokerAccount(
            account_id="ACC001",
            cash=Decimal("10005.00"),  # Within $10
            buying_power=Decimal("20000.00"),
            total_equity=Decimal("100500.00"),  # Within 1%
            margin_used=Decimal("0.00"),
        )
        discrepancies = comp.compare_account(Decimal("10000.00"), Decimal("100000.00"), broker)
        assert discrepancies == []
