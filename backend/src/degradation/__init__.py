"""Graceful degradation module for AQ Trading.

This module provides the core infrastructure for graceful degradation,
including system modes, events, the event bus, and the trading gate.
"""

from src.degradation.breakers import (
    BreakerState,
    BrokerBreaker,
    CircuitBreaker,
    DBBreaker,
    MarketDataBreaker,
    RiskBreaker,
)
from src.degradation.cache import (
    CachedData,
    DataCache,
)
from src.degradation.config import (
    DegradationConfig,
    get_config,
    set_config,
)
from src.degradation.db_buffer import (
    BufferEntry,
    DBBuffer,
)
from src.degradation.event_bus import (
    EventBus,
    EventHandler,
)
from src.degradation.models import (
    MODE_PRIORITY,
    MUST_DELIVER_EVENTS,
    ActionType,
    ComponentSource,
    ComponentStatus,
    EventType,
    ModeTransition,
    ReasonCode,
    RecoveryStage,
    RecoveryTrigger,
    Severity,
    SystemEvent,
    SystemLevel,
    SystemMode,
    create_event,
)
from src.degradation.recovery import (
    STAGE_ORDER,
    RecoveryOrchestrator,
)
from src.degradation.state_service import (
    DECISION_MATRIX,
    SystemStateService,
)
from src.degradation.trading_gate import (
    PermissionResult,
    TradingGate,
)

__all__ = [
    # Enums
    "SystemMode",
    "SystemLevel",
    "RecoveryStage",
    "RecoveryTrigger",
    "EventType",
    "ComponentSource",
    "Severity",
    "ReasonCode",
    "ActionType",
    # Constants
    "MODE_PRIORITY",
    "MUST_DELIVER_EVENTS",
    # Dataclasses
    "SystemEvent",
    "ModeTransition",
    "ComponentStatus",
    "DegradationConfig",
    # Classes
    "EventBus",
    "TradingGate",
    "PermissionResult",
    # Protocols
    "EventHandler",
    # Factory functions
    "create_event",
    # Config functions
    "get_config",
    "set_config",
    # State service
    "DECISION_MATRIX",
    "SystemStateService",
    # Circuit breakers
    "BreakerState",
    "CircuitBreaker",
    "BrokerBreaker",
    "MarketDataBreaker",
    "RiskBreaker",
    "DBBreaker",
    # Recovery orchestrator
    "RecoveryOrchestrator",
    "STAGE_ORDER",
    # DB Buffer
    "BufferEntry",
    "DBBuffer",
    # Cache with staleness
    "CachedData",
    "DataCache",
]
