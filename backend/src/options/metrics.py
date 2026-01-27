"""Prometheus metrics for options expiration monitoring.

Metrics exported:
- options_expiration_check_runs_total: Counter of check runs by status
- options_expiration_alerts_created_total: Counter of alerts created
- options_expiration_alerts_deduped_total: Counter of deduplicated alerts
- options_expiration_check_errors_total: Counter of errors by type
- options_expiration_check_duration_seconds: Histogram of check duration
- options_expiration_pending_alerts: Gauge of unacknowledged alerts
"""

from prometheus_client import Counter, Gauge, Histogram

# Check execution metrics
expiration_check_runs_total = Counter(
    "options_expiration_check_runs_total",
    "Total number of expiration check runs",
    ["status"],  # success, failed, skipped
)

# Alert creation metrics
alerts_created_total = Counter(
    "options_expiration_alerts_created_total",
    "Total number of expiration alerts created",
)

alerts_deduped_total = Counter(
    "options_expiration_alerts_deduped_total",
    "Total number of deduplicated expiration alerts",
)

# Error metrics
check_errors_total = Counter(
    "options_expiration_check_errors_total",
    "Total number of errors during expiration check",
    ["error_type"],  # missing_expiry, alert_creation, position_processing
)

# Performance metrics
check_duration_seconds = Histogram(
    "options_expiration_check_duration_seconds",
    "Duration of expiration check in seconds",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# Current state metrics
pending_alerts_gauge = Gauge(
    "options_expiration_pending_alerts",
    "Number of pending (unacknowledged) expiration alerts",
)
