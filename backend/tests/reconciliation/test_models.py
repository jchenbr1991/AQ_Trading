"""Tests for reconciliation models."""

from src.reconciliation.models import DiscrepancySeverity, DiscrepancyType


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
