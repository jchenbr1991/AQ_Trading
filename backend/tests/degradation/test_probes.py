"""Tests for component health probes.

Component probes provide health checking interfaces for recovery orchestration.
Each Hot Path component provides a probe interface that can be queried for health
status and triggered to restore ready state.

Test cases:
- test_health_signal_creation: HealthSignal dataclass creation and defaults
- test_probe_protocol_interface: ComponentProbe protocol compliance
- test_broker_probe_health_check: BrokerProbe health check returns HealthSignal
- test_probe_latency_tracking: Probes track latency in health checks
- test_ensure_ready_returns_bool: ensure_ready returns boolean success
"""

from __future__ import annotations

import asyncio
import time

import pytest


class TestHealthSignalCreation:
    """Tests for HealthSignal dataclass creation."""

    def test_health_signal_creation(self) -> None:
        """HealthSignal can be created with minimal args."""
        from src.degradation.probes import HealthSignal

        signal = HealthSignal(healthy=True)

        assert signal.healthy is True
        assert signal.latency_ms is None
        assert signal.message is None
        assert signal.timestamp_mono is not None

    def test_health_signal_with_all_fields(self) -> None:
        """HealthSignal can be created with all fields."""
        from src.degradation.probes import HealthSignal

        before = time.monotonic()
        signal = HealthSignal(
            healthy=False,
            latency_ms=42.5,
            message="Connection timeout",
        )
        after = time.monotonic()

        assert signal.healthy is False
        assert signal.latency_ms == 42.5
        assert signal.message == "Connection timeout"
        assert before <= signal.timestamp_mono <= after

    def test_health_signal_unhealthy(self) -> None:
        """HealthSignal can represent unhealthy state."""
        from src.degradation.probes import HealthSignal

        signal = HealthSignal(
            healthy=False,
            message="Broker disconnected",
        )

        assert signal.healthy is False
        assert signal.message == "Broker disconnected"

    def test_health_signal_timestamp_auto_populated(self) -> None:
        """HealthSignal timestamp_mono is auto-populated."""
        from src.degradation.probes import HealthSignal

        before = time.monotonic()
        signal = HealthSignal(healthy=True)
        after = time.monotonic()

        assert before <= signal.timestamp_mono <= after


class TestProbeProtocolInterface:
    """Tests for ComponentProbe protocol interface."""

    def test_probe_protocol_interface(self) -> None:
        """ComponentProbe protocol defines the expected interface."""
        from src.degradation.probes import ComponentProbe

        # Verify Protocol has required methods
        assert hasattr(ComponentProbe, "health_check")
        assert hasattr(ComponentProbe, "ensure_ready")
        assert hasattr(ComponentProbe, "get_last_update_mono")

    def test_broker_probe_implements_protocol(self) -> None:
        """BrokerProbe implements ComponentProbe protocol."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()

        # Check it has all required methods
        assert hasattr(probe, "health_check")
        assert hasattr(probe, "ensure_ready")
        assert hasattr(probe, "get_last_update_mono")

    def test_market_data_probe_implements_protocol(self) -> None:
        """MarketDataProbe implements ComponentProbe protocol."""
        from src.degradation.probes import MarketDataProbe

        probe = MarketDataProbe()

        assert hasattr(probe, "health_check")
        assert hasattr(probe, "ensure_ready")
        assert hasattr(probe, "get_last_update_mono")

    def test_risk_probe_implements_protocol(self) -> None:
        """RiskProbe implements ComponentProbe protocol."""
        from src.degradation.probes import RiskProbe

        probe = RiskProbe()

        assert hasattr(probe, "health_check")
        assert hasattr(probe, "ensure_ready")
        assert hasattr(probe, "get_last_update_mono")


class TestBrokerProbeHealthCheck:
    """Tests for BrokerProbe health check."""

    @pytest.mark.asyncio
    async def test_broker_probe_health_check(self) -> None:
        """BrokerProbe health_check returns HealthSignal."""
        from src.degradation.probes import BrokerProbe, HealthSignal

        probe = BrokerProbe()
        signal = await probe.health_check()

        assert isinstance(signal, HealthSignal)
        assert isinstance(signal.healthy, bool)

    @pytest.mark.asyncio
    async def test_broker_probe_health_check_returns_healthy_by_default(self) -> None:
        """BrokerProbe health_check returns healthy by default (simulated)."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        signal = await probe.health_check()

        assert signal.healthy is True

    @pytest.mark.asyncio
    async def test_market_data_probe_health_check(self) -> None:
        """MarketDataProbe health_check returns HealthSignal."""
        from src.degradation.probes import HealthSignal, MarketDataProbe

        probe = MarketDataProbe()
        signal = await probe.health_check()

        assert isinstance(signal, HealthSignal)

    @pytest.mark.asyncio
    async def test_risk_probe_health_check(self) -> None:
        """RiskProbe health_check returns HealthSignal."""
        from src.degradation.probes import HealthSignal, RiskProbe

        probe = RiskProbe()
        signal = await probe.health_check()

        assert isinstance(signal, HealthSignal)


class TestProbeLatencyTracking:
    """Tests for probe latency tracking."""

    @pytest.mark.asyncio
    async def test_probe_latency_tracking(self) -> None:
        """Probes track latency in health checks."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        signal = await probe.health_check()

        # Latency should be recorded (non-negative number)
        assert signal.latency_ms is not None
        assert signal.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_probe_latency_is_reasonable(self) -> None:
        """Probe latency should be a reasonable value."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        signal = await probe.health_check()

        # Latency should not be astronomically large for a quick check
        assert signal.latency_ms is not None
        assert signal.latency_ms < 10000  # Less than 10 seconds

    @pytest.mark.asyncio
    async def test_market_data_probe_tracks_latency(self) -> None:
        """MarketDataProbe tracks latency."""
        from src.degradation.probes import MarketDataProbe

        probe = MarketDataProbe()
        signal = await probe.health_check()

        assert signal.latency_ms is not None
        assert signal.latency_ms >= 0


class TestEnsureReadyReturnsBool:
    """Tests for ensure_ready method."""

    @pytest.mark.asyncio
    async def test_ensure_ready_returns_bool(self) -> None:
        """ensure_ready returns boolean success."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        result = await probe.ensure_ready()

        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_ensure_ready_returns_true_by_default(self) -> None:
        """ensure_ready returns True by default (simulated success)."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        result = await probe.ensure_ready()

        assert result is True

    @pytest.mark.asyncio
    async def test_market_data_probe_ensure_ready(self) -> None:
        """MarketDataProbe ensure_ready returns bool."""
        from src.degradation.probes import MarketDataProbe

        probe = MarketDataProbe()
        result = await probe.ensure_ready()

        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_risk_probe_ensure_ready(self) -> None:
        """RiskProbe ensure_ready returns bool."""
        from src.degradation.probes import RiskProbe

        probe = RiskProbe()
        result = await probe.ensure_ready()

        assert isinstance(result, bool)


class TestGetLastUpdateMono:
    """Tests for get_last_update_mono method."""

    def test_get_last_update_mono_returns_float(self) -> None:
        """get_last_update_mono returns monotonic timestamp."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        result = probe.get_last_update_mono()

        assert isinstance(result, float)

    def test_get_last_update_mono_initial_value(self) -> None:
        """get_last_update_mono returns initial timestamp."""
        from src.degradation.probes import BrokerProbe

        before = time.monotonic()
        probe = BrokerProbe()
        after = time.monotonic()

        result = probe.get_last_update_mono()

        # Initial value should be around creation time
        assert before <= result <= after

    @pytest.mark.asyncio
    async def test_get_last_update_mono_updates_after_health_check(self) -> None:
        """get_last_update_mono updates after successful health check."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        initial = probe.get_last_update_mono()

        # Small delay to ensure monotonic time advances
        await asyncio.sleep(0.01)

        await probe.health_check()
        after = probe.get_last_update_mono()

        assert after >= initial

    @pytest.mark.asyncio
    async def test_get_last_update_mono_updates_after_ensure_ready(self) -> None:
        """get_last_update_mono updates after successful ensure_ready."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe()
        initial = probe.get_last_update_mono()

        await asyncio.sleep(0.01)

        await probe.ensure_ready()
        after = probe.get_last_update_mono()

        assert after >= initial


class TestProbeWithSimulatedFailure:
    """Tests for probes with simulated failures."""

    @pytest.mark.asyncio
    async def test_broker_probe_can_simulate_failure(self) -> None:
        """BrokerProbe can be configured to simulate failure."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe(simulate_healthy=False)
        signal = await probe.health_check()

        assert signal.healthy is False

    @pytest.mark.asyncio
    async def test_ensure_ready_can_fail(self) -> None:
        """ensure_ready can return False when unable to restore."""
        from src.degradation.probes import BrokerProbe

        probe = BrokerProbe(simulate_ready=False)
        result = await probe.ensure_ready()

        assert result is False

    @pytest.mark.asyncio
    async def test_market_data_probe_can_simulate_failure(self) -> None:
        """MarketDataProbe can simulate failure."""
        from src.degradation.probes import MarketDataProbe

        probe = MarketDataProbe(simulate_healthy=False)
        signal = await probe.health_check()

        assert signal.healthy is False

    @pytest.mark.asyncio
    async def test_risk_probe_can_simulate_failure(self) -> None:
        """RiskProbe can simulate failure."""
        from src.degradation.probes import RiskProbe

        probe = RiskProbe(simulate_healthy=False)
        signal = await probe.health_check()

        assert signal.healthy is False
