"""Reconciliation data models."""

from enum import Enum


class DiscrepancyType(str, Enum):
    """Types of discrepancies between local and broker state."""

    MISSING_LOCAL = "missing_local"  # Broker has position we don't
    MISSING_BROKER = "missing_broker"  # We have position broker doesn't
    QUANTITY_MISMATCH = "quantity_mismatch"
    COST_MISMATCH = "cost_mismatch"  # Informational only
    CASH_MISMATCH = "cash_mismatch"
    EQUITY_MISMATCH = "equity_mismatch"


class DiscrepancySeverity(str, Enum):
    """Severity levels for discrepancies."""

    INFO = "info"  # Informational, no action needed
    WARNING = "warning"  # Attention needed, not critical
    CRITICAL = "critical"  # Immediate attention required
