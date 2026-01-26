"""Tests for degradation setup module.

The setup module provides initialization and shutdown functions for all
degradation components, along with getters for accessing them.

Test cases:
- test_init_degradation_returns_services: init_degradation() returns DegradationServices
- test_init_degradation_creates_all_components: All components are created and wired
- test_shutdown_degradation_stops_event_bus: EventBus is stopped on shutdown
- test_get_system_state_returns_service: Getter returns initialized service
- test_get_trading_gate_returns_gate: Getter returns initialized gate
- test_get_event_bus_returns_bus: Getter returns initialized bus
- test_getters_return_none_before_init: Getters return None before initialization
- test_double_init_replaces_services: Calling init twice replaces services
- test_shutdown_before_init_is_safe: Calling shutdown before init is safe
"""

from __future__ import annotations

import pytest
from src.degradation.config import DegradationConfig
from src.degradation.event_bus import EventBus
from src.degradation.models import RecoveryStage, SystemMode

# Import the module we're testing - will be created after tests
from src.degradation.setup import (
    DegradationServices,
    get_event_bus,
    get_system_state,
    get_trading_gate,
    init_degradation,
    shutdown_degradation,
)
from src.degradation.state_service import SystemStateService
from src.degradation.trading_gate import TradingGate


@pytest.fixture
def config() -> DegradationConfig:
    """Test configuration with shorter timeouts."""
    return DegradationConfig(
        min_safe_mode_seconds=1.0,
        recovery_stable_seconds=0.5,
        event_bus_queue_size=100,
    )


@pytest.fixture(autouse=True)
async def cleanup():
    """Clean up global state after each test."""
    yield
    # Ensure shutdown is called after each test to clean up
    await shutdown_degradation()


class TestDegradationServicesDataclass:
    """Tests for DegradationServices dataclass."""

    def test_dataclass_holds_all_services(self, config: DegradationConfig) -> None:
        """DegradationServices should hold all required components."""
        trading_gate = TradingGate()
        event_bus = EventBus(config)
        state_service = SystemStateService(config, trading_gate, event_bus)

        services = DegradationServices(
            config=config,
            event_bus=event_bus,
            trading_gate=trading_gate,
            state_service=state_service,
        )

        assert services.config == config
        assert services.event_bus == event_bus
        assert services.trading_gate == trading_gate
        assert services.state_service == state_service


class TestInitDegradation:
    """Tests for init_degradation() function."""

    @pytest.mark.asyncio
    async def test_init_degradation_returns_services(self, config: DegradationConfig) -> None:
        """init_degradation() should return DegradationServices."""
        services = await init_degradation(config)

        assert isinstance(services, DegradationServices)
        assert services.config == config

    @pytest.mark.asyncio
    async def test_init_degradation_creates_event_bus(self, config: DegradationConfig) -> None:
        """init_degradation() should create and start EventBus."""
        services = await init_degradation(config)

        assert isinstance(services.event_bus, EventBus)
        assert services.event_bus.is_running is True

    @pytest.mark.asyncio
    async def test_init_degradation_creates_trading_gate(self, config: DegradationConfig) -> None:
        """init_degradation() should create TradingGate."""
        services = await init_degradation(config)

        assert isinstance(services.trading_gate, TradingGate)
        # Trading gate starts in RECOVERING mode with CONNECT_BROKER stage
        assert services.trading_gate.mode == SystemMode.RECOVERING
        assert services.trading_gate.stage == RecoveryStage.CONNECT_BROKER

    @pytest.mark.asyncio
    async def test_init_degradation_creates_state_service(self, config: DegradationConfig) -> None:
        """init_degradation() should create SystemStateService."""
        services = await init_degradation(config)

        assert isinstance(services.state_service, SystemStateService)
        # State service starts in RECOVERING mode (cold start)
        assert services.state_service.mode == SystemMode.RECOVERING
        assert services.state_service.stage == RecoveryStage.CONNECT_BROKER

    @pytest.mark.asyncio
    async def test_init_degradation_wires_components(self, config: DegradationConfig) -> None:
        """init_degradation() should wire components together correctly."""
        services = await init_degradation(config)

        # State service should be connected to trading gate
        # When we change mode via state service, gate should update
        assert services.trading_gate.mode == services.state_service.mode

    @pytest.mark.asyncio
    async def test_double_init_replaces_services(self, config: DegradationConfig) -> None:
        """Calling init_degradation() twice should replace services."""
        services1 = await init_degradation(config)
        services2 = await init_degradation(config)

        # Should be different instances
        assert services1 is not services2
        assert services1.event_bus is not services2.event_bus

        # Old event bus should be stopped
        assert services1.event_bus.is_running is False

        # New event bus should be running
        assert services2.event_bus.is_running is True

    @pytest.mark.asyncio
    async def test_init_with_default_config(self) -> None:
        """init_degradation() should work with default config."""
        services = await init_degradation()

        assert isinstance(services, DegradationServices)
        assert isinstance(services.config, DegradationConfig)


class TestShutdownDegradation:
    """Tests for shutdown_degradation() function."""

    @pytest.mark.asyncio
    async def test_shutdown_stops_event_bus(self, config: DegradationConfig) -> None:
        """shutdown_degradation() should stop the EventBus."""
        services = await init_degradation(config)
        event_bus = services.event_bus
        assert event_bus.is_running is True

        await shutdown_degradation()

        assert event_bus.is_running is False

    @pytest.mark.asyncio
    async def test_shutdown_clears_global_state(self, config: DegradationConfig) -> None:
        """shutdown_degradation() should clear global state."""
        await init_degradation(config)
        assert get_system_state() is not None

        await shutdown_degradation()

        assert get_system_state() is None
        assert get_trading_gate() is None
        assert get_event_bus() is None

    @pytest.mark.asyncio
    async def test_shutdown_before_init_is_safe(self) -> None:
        """shutdown_degradation() should be safe to call before init."""
        # This should not raise
        await shutdown_degradation()

        # Getters should still return None
        assert get_system_state() is None
        assert get_trading_gate() is None
        assert get_event_bus() is None

    @pytest.mark.asyncio
    async def test_double_shutdown_is_safe(self, config: DegradationConfig) -> None:
        """shutdown_degradation() should be safe to call twice."""
        await init_degradation(config)

        await shutdown_degradation()
        await shutdown_degradation()  # Should not raise

        assert get_system_state() is None


class TestGetSystemState:
    """Tests for get_system_state() function."""

    @pytest.mark.asyncio
    async def test_get_system_state_returns_service(self, config: DegradationConfig) -> None:
        """get_system_state() should return the initialized service."""
        services = await init_degradation(config)

        result = get_system_state()

        assert result is services.state_service
        assert isinstance(result, SystemStateService)

    @pytest.mark.asyncio
    async def test_get_system_state_returns_none_before_init(self) -> None:
        """get_system_state() should return None before initialization."""
        # Ensure clean state
        await shutdown_degradation()

        result = get_system_state()

        assert result is None


class TestGetTradingGate:
    """Tests for get_trading_gate() function."""

    @pytest.mark.asyncio
    async def test_get_trading_gate_returns_gate(self, config: DegradationConfig) -> None:
        """get_trading_gate() should return the initialized gate."""
        services = await init_degradation(config)

        result = get_trading_gate()

        assert result is services.trading_gate
        assert isinstance(result, TradingGate)

    @pytest.mark.asyncio
    async def test_get_trading_gate_returns_none_before_init(self) -> None:
        """get_trading_gate() should return None before initialization."""
        # Ensure clean state
        await shutdown_degradation()

        result = get_trading_gate()

        assert result is None


class TestGetEventBus:
    """Tests for get_event_bus() function."""

    @pytest.mark.asyncio
    async def test_get_event_bus_returns_bus(self, config: DegradationConfig) -> None:
        """get_event_bus() should return the initialized bus."""
        services = await init_degradation(config)

        result = get_event_bus()

        assert result is services.event_bus
        assert isinstance(result, EventBus)

    @pytest.mark.asyncio
    async def test_get_event_bus_returns_none_before_init(self) -> None:
        """get_event_bus() should return None before initialization."""
        # Ensure clean state
        await shutdown_degradation()

        result = get_event_bus()

        assert result is None


class TestIntegration:
    """Integration tests for the setup module."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, config: DegradationConfig) -> None:
        """Test full init/use/shutdown lifecycle."""
        # Initialize
        services = await init_degradation(config)

        # Verify all services are accessible
        assert get_system_state() is services.state_service
        assert get_trading_gate() is services.trading_gate
        assert get_event_bus() is services.event_bus

        # Verify event bus is running
        assert services.event_bus.is_running is True

        # Shutdown
        await shutdown_degradation()

        # Verify cleanup
        assert get_system_state() is None
        assert get_trading_gate() is None
        assert get_event_bus() is None
