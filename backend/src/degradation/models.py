"""Core models for graceful degradation.

This module defines the fundamental data structures used throughout the
degradation system, including system modes, events, and reason codes.

Key design constraints:
- SystemMode has 6 modes with strict priority ordering
- MUST_DELIVER_EVENTS is a frozen whitelist of critical events
- SystemEvent uses dual timestamps: wall time (display) + monotonic (logic)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class SystemMode(str, Enum):
    """System operating modes.

    The system can be in one of 6 modes, ranging from full functionality
    (NORMAL) to complete halt (HALT). Modes are ordered by severity.
    """

    NORMAL = "normal"  # Full functionality
    DEGRADED = "degraded"  # Limited operation
    SAFE_MODE = "safe_mode"  # Protect capital (control plane available)
    SAFE_MODE_DISCONNECTED = "safe_mode_disconnected"  # Protect capital (control plane unavailable)
    HALT = "halt"  # Requires human intervention
    RECOVERING = "recovering"  # Recovery orchestration in progress


# Strict priority ordering (higher number = more severe)
# Used for conflict resolution: take the most severe mode
MODE_PRIORITY: dict[SystemMode, int] = {
    SystemMode.NORMAL: 0,
    SystemMode.RECOVERING: 1,
    SystemMode.DEGRADED: 2,
    SystemMode.SAFE_MODE: 3,
    SystemMode.SAFE_MODE_DISCONNECTED: 4,
    SystemMode.HALT: 5,
}


class SystemLevel(str, Enum):
    """Internal health level for hysteresis tracking.

    Used to implement debouncing/hysteresis to avoid mode flapping.
    UNSTABLE is a warning state that doesn't trigger mode changes.
    """

    HEALTHY = "healthy"  # Normal operation
    UNSTABLE = "unstable"  # Flapping, not yet triggered degradation
    TRIPPED = "tripped"  # Degradation triggered


class RecoveryStage(str, Enum):
    """Recovery orchestration stages.

    Recovery proceeds through these stages in order.
    Each stage has specific permissions for trading actions.
    """

    CONNECT_BROKER = "connect_broker"  # Reconnecting to broker
    CATCHUP_MARKETDATA = "catchup_marketdata"  # Catching up market data
    VERIFY_RISK = "verify_risk"  # Verifying risk parameters
    READY = "ready"  # Ready to transition to NORMAL


class RecoveryTrigger(str, Enum):
    """How recovery was triggered.

    AUTO: Automatic recovery after critical failure resolved
    MANUAL: Operator initiated via API
    COLD_START: System cold start / initial boot
    """

    AUTO = "auto"
    MANUAL = "manual"
    COLD_START = "cold_start"


class EventType(str, Enum):
    """Types of system events.

    FAIL_CRIT: Critical failure requiring immediate action
    FAIL_SUPP: Supplementary/non-critical failure
    RECOVERED: Component has recovered
    HEARTBEAT: Periodic health check
    QUALITY_DEGRADED: Quality has degraded but not failed
    """

    FAIL_CRIT = "fail_crit"
    FAIL_SUPP = "fail_supp"
    RECOVERED = "recovered"
    HEARTBEAT = "heartbeat"
    QUALITY_DEGRADED = "quality_degraded"


class ComponentSource(str, Enum):
    """Source components that can emit events.

    These are the hot-path components that have explicit degradation design.
    """

    BROKER = "broker"
    MARKET_DATA = "market_data"
    RISK = "risk"
    DB = "db"
    ALERTS = "alerts"
    SYSTEM = "system"


class Severity(str, Enum):
    """Event severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ReasonCode(str, Enum):
    """Standardized reason codes for events.

    Each reason code maps to a specific target mode in the decision matrix.
    Format: component.specific_reason
    """

    # Broker
    BROKER_DISCONNECT = "broker.disconnect"
    BROKER_RECONNECTED = "broker.reconnected"
    BROKER_REPORT_MISMATCH = "broker.report_mismatch"

    # Market Data
    MD_STALE = "market_data.stale"
    MD_QUALITY_DEGRADED = "market_data.quality_degraded"

    # Risk
    RISK_TIMEOUT = "risk.timeout"
    RISK_BREACH_HARD = "risk.breach_hard"

    # Position
    POSITION_TRUTH_UNKNOWN = "position.unknown"

    # Database
    DB_WRITE_FAIL = "db.write_fail"
    DB_BUFFER_OVERFLOW = "db.buffer_overflow"

    # Alerts
    ALERTS_CHANNEL_DOWN = "alerts.channel_down"

    # Recovery
    COLD_START = "cold_start"
    RECOVERY_FAILED = "recovery.failed"
    ALL_HEALTHY = "all.healthy"


class ActionType(str, Enum):
    """Trading action types controlled by the TradingGate.

    Each mode has specific permissions for these actions.
    """

    OPEN = "open"  # Open new position
    SEND = "send"  # Send order
    AMEND = "amend"  # Amend existing order
    CANCEL = "cancel"  # Cancel order
    REDUCE_ONLY = "reduce_only"  # Reduce position only
    QUERY = "query"  # Query data (read-only)


# Critical events that MUST be delivered even when EventBus is full.
# Only these events trigger local emergency degradation on bus failure.
# Adding new critical events requires code review.
MUST_DELIVER_EVENTS: frozenset[ReasonCode] = frozenset(
    {
        ReasonCode.BROKER_DISCONNECT,
        ReasonCode.POSITION_TRUTH_UNKNOWN,
        ReasonCode.BROKER_REPORT_MISMATCH,
        ReasonCode.RISK_BREACH_HARD,
    }
)


@dataclass(frozen=True)
class SystemEvent:
    """Represents a system event from a component.

    Uses dual timestamps:
    - event_time_wall: Wall clock time for display/audit (may jump)
    - event_time_mono: Monotonic time for logic/TTL/stale checks (never jumps)

    All judgment logic uses event_time_mono.
    All display/audit/logging uses event_time_wall.
    """

    event_type: EventType
    source: ComponentSource
    severity: Severity
    reason_code: ReasonCode
    event_time_wall: datetime  # For audit/display (may jump)
    event_time_mono: float  # For logic/TTL/stale (monotonic)
    details: dict[str, Any] | None = field(default=None)
    ttl_seconds: int | None = field(default=None)

    def is_critical(self) -> bool:
        """Check if this event is critical (must be delivered).

        Only whitelist events are considered critical. This ensures
        that Alert/Audit/Metric events never trigger local emergency
        degradation on EventBus failure.
        """
        return self.reason_code in MUST_DELIVER_EVENTS

    def is_expired(self) -> bool:
        """Check if this event has expired based on TTL.

        Uses monotonic time to avoid system clock jump issues.
        Events without TTL never expire.
        """
        if self.ttl_seconds is None:
            return False

        elapsed = time.monotonic() - self.event_time_mono
        return elapsed > self.ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Converts enum values to strings and datetime to ISO format.
        """
        return {
            "event_type": self.event_type.value,
            "source": self.source.value,
            "severity": self.severity.value,
            "reason_code": self.reason_code.value,
            "event_time_wall": self.event_time_wall.isoformat(),
            "event_time_mono": self.event_time_mono,
            "details": self.details,
            "ttl_seconds": self.ttl_seconds,
        }


@dataclass
class ModeTransition:
    """Record of a mode transition.

    Captures the full context of a mode change including who/what triggered it.
    """

    from_mode: SystemMode
    to_mode: SystemMode
    reason_code: ReasonCode
    source: ComponentSource
    timestamp_wall: datetime
    timestamp_mono: float
    operator_id: str | None = None
    override_ttl: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Converts enum values to strings and datetime to ISO format.
        """
        return {
            "from_mode": self.from_mode.value,
            "to_mode": self.to_mode.value,
            "reason_code": self.reason_code.value,
            "source": self.source.value,
            "timestamp_wall": self.timestamp_wall.isoformat(),
            "timestamp_mono": self.timestamp_mono,
            "operator_id": self.operator_id,
            "override_ttl": self.override_ttl,
        }


@dataclass
class ComponentStatus:
    """Status of a single component.

    Tracks health state and failure history for hysteresis logic.
    """

    source: ComponentSource
    level: SystemLevel
    last_event: SystemEvent | None
    last_update_mono: float
    consecutive_failures: int = 0
    unstable_since_mono: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization.

        Converts enum values to strings and nested objects to dicts.
        """
        return {
            "source": self.source.value,
            "level": self.level.value,
            "last_event": self.last_event.to_dict() if self.last_event else None,
            "last_update_mono": self.last_update_mono,
            "consecutive_failures": self.consecutive_failures,
            "unstable_since_mono": self.unstable_since_mono,
        }


def create_event(
    event_type: EventType,
    source: ComponentSource,
    severity: Severity,
    reason_code: ReasonCode,
    details: dict[str, Any] | None = None,
    ttl_seconds: int | None = None,
) -> SystemEvent:
    """Create a SystemEvent with current timestamps.

    Factory function that auto-populates wall and monotonic timestamps.

    Args:
        event_type: Type of event (FAIL_CRIT, RECOVERED, etc.)
        source: Component emitting the event
        severity: Severity level
        reason_code: Standardized reason code
        details: Optional additional context
        ttl_seconds: Optional time-to-live in seconds

    Returns:
        A new SystemEvent with current timestamps.
    """
    return SystemEvent(
        event_type=event_type,
        source=source,
        severity=severity,
        reason_code=reason_code,
        event_time_wall=datetime.now(tz=timezone.utc),
        event_time_mono=time.monotonic(),
        details=details,
        ttl_seconds=ttl_seconds,
    )
