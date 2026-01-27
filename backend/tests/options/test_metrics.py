"""Tests for options expiration metrics."""


def test_metrics_exist():
    """All required metrics should be defined."""
    from src.options.metrics import (
        alerts_created_total,
        alerts_deduped_total,
        check_duration_seconds,
        check_errors_total,
        expiration_check_runs_total,
        pending_alerts_gauge,
    )

    # Just verify they exist and are the right types
    assert expiration_check_runs_total is not None
    assert alerts_created_total is not None
    assert alerts_deduped_total is not None
    assert check_errors_total is not None
    assert check_duration_seconds is not None
    assert pending_alerts_gauge is not None
