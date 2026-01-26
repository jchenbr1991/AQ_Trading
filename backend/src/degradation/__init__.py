"""Graceful degradation module for AQ Trading.

This module provides the core infrastructure for graceful degradation,
including system modes, events, and the trading gate.
"""

from src.degradation.config import (
    DegradationConfig,
    get_config,
    set_config,
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
    # Factory functions
    "create_event",
    # Config functions
    "get_config",
    "set_config",
]
