"""Degradation system setup and initialization.

This module provides functions to initialize and access the global degradation
services. The services include:
- EventBus: Non-blocking event propagation
- TradingGate: Permission control for trading operations
- SystemStateService: Central state management (Single Source of Truth)

Usage:
    from src.degradation.setup import (
        init_degradation,
        shutdown_degradation,
        get_system_state,
        get_trading_gate,
        get_event_bus,
    )

    # During startup:
    services = await init_degradation()

    # Later, anywhere in the app:
    state = get_system_state()
    if state:
        print(f"Current mode: {state.mode}")

    gate = get_trading_gate()
    if gate and gate.allows(ActionType.SEND):
        # Proceed with order

    # During shutdown:
    await shutdown_degradation()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.degradation.config import DegradationConfig, get_config
from src.degradation.event_bus import EventBus
from src.degradation.state_service import SystemStateService
from src.degradation.trading_gate import TradingGate

logger = logging.getLogger(__name__)


@dataclass
class DegradationServices:
    """Container for all degradation services.

    This dataclass holds references to all initialized degradation
    components, making it easy to pass them around during initialization.

    Attributes:
        config: The degradation configuration
        event_bus: The EventBus for event propagation
        trading_gate: The TradingGate for permission control
        state_service: The SystemStateService for state management
    """

    config: DegradationConfig
    event_bus: EventBus
    trading_gate: TradingGate
    state_service: SystemStateService


# Global state for services
_services: DegradationServices | None = None


async def init_degradation(
    config: DegradationConfig | None = None,
    fallback_log_path: Path | None = None,
) -> DegradationServices:
    """Initialize all degradation services.

    Creates and wires together all degradation components:
    1. TradingGate - for permission control
    2. EventBus - for event propagation (started automatically)
    3. SystemStateService - for state management

    If called when services are already initialized, the old services
    are shut down and replaced with new ones.

    Args:
        config: Optional configuration. If None, uses default config.
        fallback_log_path: Optional path for EventBus fallback log.

    Returns:
        DegradationServices containing all initialized services.
    """
    global _services

    # Shutdown existing services if any
    if _services is not None:
        logger.info("Replacing existing degradation services")
        await shutdown_degradation()

    # Use provided config or get default
    if config is None:
        config = get_config()

    # Create TradingGate first (no dependencies)
    trading_gate = TradingGate()

    # Create EventBus (depends on config)
    event_bus = EventBus(config=config, fallback_log_path=fallback_log_path)

    # Create SystemStateService (depends on config, trading_gate, event_bus)
    state_service = SystemStateService(
        config=config,
        trading_gate=trading_gate,
        event_bus=event_bus,
    )

    # Start the EventBus
    await event_bus.start()

    # Create services container
    _services = DegradationServices(
        config=config,
        event_bus=event_bus,
        trading_gate=trading_gate,
        state_service=state_service,
    )

    logger.info(
        f"Degradation services initialized: mode={state_service.mode.value}, "
        f"stage={state_service.stage.value if state_service.stage else None}"
    )

    return _services


async def shutdown_degradation() -> None:
    """Shutdown all degradation services.

    Stops the EventBus and clears global state.
    Safe to call multiple times or before initialization.
    """
    global _services

    if _services is None:
        logger.debug("No degradation services to shutdown")
        return

    # Stop EventBus
    await _services.event_bus.stop()

    # Clear global state
    _services = None

    logger.info("Degradation services shutdown complete")


def get_system_state() -> SystemStateService | None:
    """Get the global SystemStateService instance.

    Returns:
        The initialized SystemStateService, or None if not yet initialized.
        Callers should check for None before using.
    """
    if _services is None:
        return None
    return _services.state_service


def get_trading_gate() -> TradingGate | None:
    """Get the global TradingGate instance.

    Returns:
        The initialized TradingGate, or None if not yet initialized.
        Callers should check for None before using.
    """
    if _services is None:
        return None
    return _services.trading_gate


def get_event_bus() -> EventBus | None:
    """Get the global EventBus instance.

    Returns:
        The initialized EventBus, or None if not yet initialized.
        Callers should check for None before using.
    """
    if _services is None:
        return None
    return _services.event_bus
