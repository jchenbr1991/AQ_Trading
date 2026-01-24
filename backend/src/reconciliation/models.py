"""Reconciliation data models."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


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


@dataclass
class Discrepancy:
    """A single discrepancy between local and broker state."""

    type: DiscrepancyType
    severity: DiscrepancySeverity
    symbol: str | None  # None for account-level discrepancies
    local_value: Any
    broker_value: Any
    timestamp: datetime
    account_id: str


# Default severity mapping based on discrepancy type
DEFAULT_SEVERITY_MAP: dict[DiscrepancyType, DiscrepancySeverity] = {
    DiscrepancyType.COST_MISMATCH: DiscrepancySeverity.INFO,
    DiscrepancyType.CASH_MISMATCH: DiscrepancySeverity.WARNING,
    DiscrepancyType.EQUITY_MISMATCH: DiscrepancySeverity.WARNING,
    DiscrepancyType.QUANTITY_MISMATCH: DiscrepancySeverity.CRITICAL,
    DiscrepancyType.MISSING_LOCAL: DiscrepancySeverity.CRITICAL,
    DiscrepancyType.MISSING_BROKER: DiscrepancySeverity.CRITICAL,
}
