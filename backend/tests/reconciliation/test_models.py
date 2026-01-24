"""Tests for reconciliation models."""

from datetime import datetime
from decimal import Decimal

from src.reconciliation.models import (
    DEFAULT_SEVERITY_MAP,
    Discrepancy,
    DiscrepancySeverity,
    DiscrepancyType,
)


class TestDiscrepancyType:
    def test_missing_local_value(self):
        assert DiscrepancyType.MISSING_LOCAL.value == "missing_local"

    def test_missing_broker_value(self):
        assert DiscrepancyType.MISSING_BROKER.value == "missing_broker"

    def test_quantity_mismatch_value(self):
        assert DiscrepancyType.QUANTITY_MISMATCH.value == "quantity_mismatch"

    def test_cost_mismatch_value(self):
        assert DiscrepancyType.COST_MISMATCH.value == "cost_mismatch"

    def test_cash_mismatch_value(self):
        assert DiscrepancyType.CASH_MISMATCH.value == "cash_mismatch"

    def test_equity_mismatch_value(self):
        assert DiscrepancyType.EQUITY_MISMATCH.value == "equity_mismatch"


class TestDiscrepancySeverity:
    def test_info_value(self):
        assert DiscrepancySeverity.INFO.value == "info"

    def test_warning_value(self):
        assert DiscrepancySeverity.WARNING.value == "warning"

    def test_critical_value(self):
        assert DiscrepancySeverity.CRITICAL.value == "critical"


class TestDiscrepancy:
    def test_create_discrepancy(self):
        d = Discrepancy(
            type=DiscrepancyType.QUANTITY_MISMATCH,
            severity=DiscrepancySeverity.CRITICAL,
            symbol="AAPL",
            local_value=100,
            broker_value=90,
            timestamp=datetime(2026, 1, 24, 10, 0, 0),
            account_id="ACC001",
        )
        assert d.type == DiscrepancyType.QUANTITY_MISMATCH
        assert d.severity == DiscrepancySeverity.CRITICAL
        assert d.symbol == "AAPL"
        assert d.local_value == 100
        assert d.broker_value == 90
        assert d.account_id == "ACC001"

    def test_account_level_discrepancy_symbol_none(self):
        d = Discrepancy(
            type=DiscrepancyType.CASH_MISMATCH,
            severity=DiscrepancySeverity.WARNING,
            symbol=None,
            local_value=Decimal("10000.00"),
            broker_value=Decimal("10005.00"),
            timestamp=datetime.utcnow(),
            account_id="ACC001",
        )
        assert d.symbol is None


class TestDefaultSeverityMap:
    def test_cost_mismatch_is_info(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.COST_MISMATCH] == DiscrepancySeverity.INFO

    def test_cash_mismatch_is_warning(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.CASH_MISMATCH] == DiscrepancySeverity.WARNING

    def test_equity_mismatch_is_warning(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.EQUITY_MISMATCH] == DiscrepancySeverity.WARNING

    def test_quantity_mismatch_is_critical(self):
        assert (
            DEFAULT_SEVERITY_MAP[DiscrepancyType.QUANTITY_MISMATCH] == DiscrepancySeverity.CRITICAL
        )

    def test_missing_local_is_critical(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_LOCAL] == DiscrepancySeverity.CRITICAL

    def test_missing_broker_is_critical(self):
        assert DEFAULT_SEVERITY_MAP[DiscrepancyType.MISSING_BROKER] == DiscrepancySeverity.CRITICAL
