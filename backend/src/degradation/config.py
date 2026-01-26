"""Degradation configuration.

All thresholds for graceful degradation must come from this config.
Hardcoding thresholds in code is PROHIBITED.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DegradationConfig:
    """Configuration for graceful degradation.

    All graceful degradation thresholds MUST come from this config.
    Hardcoding thresholds in code is PROHIBITED.
    """

    # Hysteresis settings
    fail_threshold_count: int = 3
    fail_threshold_seconds: float = 5.0
    recovery_stable_seconds: float = 10.0
    min_safe_mode_seconds: float = 30.0
    unknown_on_ttl_expiry: bool = True
    alert_on_unstable: bool = True

    # Component timeouts
    broker_timeout_ms: int = 5000
    market_data_stale_ms: int = 10000
    risk_timeout_ms: int = 2000
    risk_timeout_consecutive_count: int = 3
    db_timeout_ms: int = 3000

    # Recovery settings
    max_recovery_attempts: int = 3
    recovery_backoff_base_ms: int = 1000
    auto_recovery_to_normal: bool = True

    # DB Buffer settings
    db_buffer_max_entries: int = 1000
    db_buffer_max_bytes: int = 10_000_000
    db_buffer_max_seconds: float = 60.0
    db_wal_enabled: bool = True

    # EventBus settings
    event_bus_queue_size: int = 10000
    event_bus_publish_timeout_ms: int = 100
    event_bus_drop_on_full: bool = True

    # Cache staleness thresholds
    position_cache_stale_ms: int = 30000
    market_data_cache_stale_ms: int = 10000

    # Default TTL for component status
    component_status_ttl_seconds: int = 30


# Global config instance
_config: DegradationConfig | None = None


def get_config() -> DegradationConfig:
    """Get the global degradation config instance.

    Returns:
        The global DegradationConfig singleton instance.
    """
    global _config
    if _config is None:
        _config = DegradationConfig()
    return _config


def set_config(config: DegradationConfig) -> None:
    """Set the global degradation config (for testing).

    Args:
        config: The configuration instance to set as global.
    """
    global _config
    _config = config
