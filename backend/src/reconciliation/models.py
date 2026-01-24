"""Reconciliation data models."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4


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


@dataclass
class ReconciliationConfig:
    """Configuration for reconciliation service."""

    account_id: str
    interval_seconds: int = 300  # 5 minutes default
    post_fill_delay_seconds: float = 5.0  # Debounce after fills
    cash_tolerance: Decimal = field(default_factory=lambda: Decimal("1.00"))
    equity_tolerance_pct: Decimal = field(default_factory=lambda: Decimal("0.1"))
    enabled: bool = True


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""

    account_id: str
    timestamp: datetime
    is_clean: bool  # No discrepancies found
    discrepancies: list[Discrepancy]
    positions_checked: int
    duration_ms: float
    context: dict[str, Any]  # Trigger context
    run_id: UUID = field(default_factory=uuid4)  # Unique ID for correlation
