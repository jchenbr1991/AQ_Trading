"""Tests for degradation configuration."""

import pytest
from src.degradation.config import DegradationConfig, get_config, set_config


class TestDegradationConfig:
    """Tests for DegradationConfig dataclass."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = DegradationConfig()

        # Hysteresis
        assert config.fail_threshold_count == 3
        assert config.fail_threshold_seconds == 5.0
        assert config.recovery_stable_seconds == 10.0
        assert config.min_safe_mode_seconds == 30.0

        # Timeouts
        assert config.broker_timeout_ms == 5000
        assert config.market_data_stale_ms == 10000
        assert config.risk_timeout_ms == 2000

        # Recovery
        assert config.auto_recovery_to_normal is True

        # DB Buffer
        assert config.db_buffer_max_entries == 1000
        assert config.db_buffer_max_bytes == 10_000_000

        # EventBus
        assert config.event_bus_queue_size == 10000
        assert config.event_bus_drop_on_full is True

    def test_config_immutable(self):
        """Config should be a frozen dataclass."""
        config = DegradationConfig()
        with pytest.raises(AttributeError):
            config.fail_threshold_count = 10

    def test_get_config_returns_singleton(self):
        """get_config should return the same instance."""
        # Reset config to ensure clean state
        set_config(DegradationConfig())
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2

    def test_set_config_allows_custom_values(self):
        """set_config should allow setting custom configuration."""
        custom_config = DegradationConfig(
            fail_threshold_count=5,
            broker_timeout_ms=10000,
        )
        set_config(custom_config)
        config = get_config()
        assert config.fail_threshold_count == 5
        assert config.broker_timeout_ms == 10000

    def test_all_hysteresis_settings(self):
        """Test all hysteresis-related settings."""
        config = DegradationConfig()
        assert config.unknown_on_ttl_expiry is True
        assert config.alert_on_unstable is True

    def test_all_timeout_settings(self):
        """Test all timeout-related settings."""
        config = DegradationConfig()
        assert config.risk_timeout_consecutive_count == 3
        assert config.db_timeout_ms == 3000

    def test_all_recovery_settings(self):
        """Test all recovery-related settings."""
        config = DegradationConfig()
        assert config.max_recovery_attempts == 3
        assert config.recovery_backoff_base_ms == 1000

    def test_all_db_buffer_settings(self):
        """Test all DB buffer-related settings."""
        config = DegradationConfig()
        assert config.db_buffer_max_seconds == 60.0
        assert config.db_wal_enabled is True

    def test_all_event_bus_settings(self):
        """Test all EventBus-related settings."""
        config = DegradationConfig()
        assert config.event_bus_publish_timeout_ms == 100

    def test_cache_staleness_settings(self):
        """Test cache staleness thresholds."""
        config = DegradationConfig()
        assert config.position_cache_stale_ms == 30000
        assert config.market_data_cache_stale_ms == 10000

    def test_component_status_ttl(self):
        """Test component status TTL setting."""
        config = DegradationConfig()
        assert config.component_status_ttl_seconds == 30


class TestConfigIntegration:
    """Integration tests for config module."""

    def teardown_method(self):
        """Reset config after each test."""
        set_config(DegradationConfig())

    def test_config_can_be_imported_from_package(self):
        """Config should be importable from degradation package."""
        from src.degradation import DegradationConfig, get_config, set_config

        assert DegradationConfig is not None
        assert get_config is not None
        assert set_config is not None
