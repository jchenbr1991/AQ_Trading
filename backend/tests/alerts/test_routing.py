"""Tests for alert routing configuration module."""

import os
from unittest.mock import patch

import pytest
from src.alerts.factory import create_alert
from src.alerts.models import AlertType, Severity
from src.alerts.routing import (
    DESTINATION_ENV_MAP,
    RoutingConfig,
    get_destinations_for_alert,
    resolve_destination,
)


class TestDestinationEnvMap:
    """Tests for DESTINATION_ENV_MAP constant."""

    def test_destination_env_map_contains_email_default(self):
        """Should map email:default to ALERT_EMAIL_DEFAULT."""
        assert DESTINATION_ENV_MAP["email:default"] == "ALERT_EMAIL_DEFAULT"

    def test_destination_env_map_contains_email_risk(self):
        """Should map email:risk to ALERT_EMAIL_RISK."""
        assert DESTINATION_ENV_MAP["email:risk"] == "ALERT_EMAIL_RISK"

    def test_destination_env_map_contains_email_ops(self):
        """Should map email:ops to ALERT_EMAIL_OPS."""
        assert DESTINATION_ENV_MAP["email:ops"] == "ALERT_EMAIL_OPS"

    def test_destination_env_map_contains_webhook_default(self):
        """Should map webhook:default to ALERT_WEBHOOK_DEFAULT."""
        assert DESTINATION_ENV_MAP["webhook:default"] == "ALERT_WEBHOOK_DEFAULT"

    def test_destination_env_map_contains_webhook_wecom(self):
        """Should map webhook:wecom to ALERT_WEBHOOK_WECOM."""
        assert DESTINATION_ENV_MAP["webhook:wecom"] == "ALERT_WEBHOOK_WECOM"


class TestRoutingConfig:
    """Tests for RoutingConfig dataclass."""

    def test_default_severity_channels_sev1(self):
        """SEV1 should route to email and webhook by default."""
        config = RoutingConfig()
        assert config.severity_channels[Severity.SEV1] == ["email", "webhook"]

    def test_default_severity_channels_sev2(self):
        """SEV2 should route to webhook by default."""
        config = RoutingConfig()
        assert config.severity_channels[Severity.SEV2] == ["webhook"]

    def test_default_severity_channels_sev3(self):
        """SEV3 should route to nothing (log only) by default."""
        config = RoutingConfig()
        assert config.severity_channels[Severity.SEV3] == []

    def test_default_type_recipients_daily_loss_limit(self):
        """DAILY_LOSS_LIMIT should route to email:risk by default."""
        config = RoutingConfig()
        assert config.type_recipients[AlertType.DAILY_LOSS_LIMIT] == ["email:risk"]

    def test_default_type_recipients_kill_switch_activated(self):
        """KILL_SWITCH_ACTIVATED should route to email:ops and email:risk."""
        config = RoutingConfig()
        assert config.type_recipients[AlertType.KILL_SWITCH_ACTIVATED] == [
            "email:ops",
            "email:risk",
        ]

    def test_default_type_recipients_position_limit_hit(self):
        """POSITION_LIMIT_HIT should route to email:risk by default."""
        config = RoutingConfig()
        assert config.type_recipients[AlertType.POSITION_LIMIT_HIT] == ["email:risk"]

    def test_default_global_recipients(self):
        """Global recipients should include email:default and webhook:default."""
        config = RoutingConfig()
        assert config.global_recipients == ["email:default", "webhook:default"]

    def test_get_channels_for_severity_sev1(self):
        """get_channels_for_severity should return email and webhook for SEV1."""
        config = RoutingConfig()
        assert config.get_channels_for_severity(Severity.SEV1) == ["email", "webhook"]

    def test_get_channels_for_severity_sev2(self):
        """get_channels_for_severity should return webhook for SEV2."""
        config = RoutingConfig()
        assert config.get_channels_for_severity(Severity.SEV2) == ["webhook"]

    def test_get_channels_for_severity_sev3(self):
        """get_channels_for_severity should return empty list for SEV3."""
        config = RoutingConfig()
        assert config.get_channels_for_severity(Severity.SEV3) == []

    def test_get_channels_for_severity_unknown_returns_empty(self):
        """get_channels_for_severity should return empty list for unknown severity."""
        config = RoutingConfig()
        # Manually remove a severity to test fallback
        config.severity_channels.pop(Severity.SEV2, None)
        assert config.get_channels_for_severity(Severity.SEV2) == []

    def test_custom_severity_channels(self):
        """Should be able to override severity_channels."""
        custom_channels = {
            Severity.SEV1: ["email"],
            Severity.SEV2: ["email", "webhook"],
            Severity.SEV3: ["webhook"],
        }
        config = RoutingConfig(severity_channels=custom_channels)
        assert config.severity_channels == custom_channels

    def test_custom_type_recipients(self):
        """Should be able to override type_recipients."""
        custom_recipients = {AlertType.ORDER_REJECTED: ["email:ops"]}
        config = RoutingConfig(type_recipients=custom_recipients)
        assert config.type_recipients == custom_recipients

    def test_custom_global_recipients(self):
        """Should be able to override global_recipients."""
        custom_global = ["webhook:wecom"]
        config = RoutingConfig(global_recipients=custom_global)
        assert config.global_recipients == custom_global

    def test_each_instance_has_independent_defaults(self):
        """Each RoutingConfig instance should have independent default dicts."""
        config1 = RoutingConfig()
        config2 = RoutingConfig()
        config1.severity_channels[Severity.SEV3] = ["email"]
        # config2 should not be affected
        assert config2.severity_channels[Severity.SEV3] == []


class TestResolveDestination:
    """Tests for resolve_destination function."""

    def test_resolve_destination_returns_env_value(self):
        """Should return environment variable value when set."""
        with patch.dict(os.environ, {"ALERT_EMAIL_DEFAULT": "alerts@example.com"}):
            result = resolve_destination("email:default")
            assert result == "alerts@example.com"

    def test_resolve_destination_returns_none_when_env_not_set(self):
        """Should return None when environment variable is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure the env var is not set
            os.environ.pop("ALERT_EMAIL_DEFAULT", None)
            result = resolve_destination("email:default")
            assert result is None

    def test_resolve_destination_unknown_key_returns_none(self):
        """Should return None for unknown destination key."""
        result = resolve_destination("unknown:key")
        assert result is None

    def test_resolve_destination_email_risk(self):
        """Should resolve email:risk from ALERT_EMAIL_RISK."""
        with patch.dict(os.environ, {"ALERT_EMAIL_RISK": "risk@example.com"}):
            result = resolve_destination("email:risk")
            assert result == "risk@example.com"

    def test_resolve_destination_email_ops(self):
        """Should resolve email:ops from ALERT_EMAIL_OPS."""
        with patch.dict(os.environ, {"ALERT_EMAIL_OPS": "ops@example.com"}):
            result = resolve_destination("email:ops")
            assert result == "ops@example.com"

    def test_resolve_destination_webhook_default(self):
        """Should resolve webhook:default from ALERT_WEBHOOK_DEFAULT."""
        with patch.dict(os.environ, {"ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default"}):
            result = resolve_destination("webhook:default")
            assert result == "https://hooks.example.com/default"

    def test_resolve_destination_webhook_wecom(self):
        """Should resolve webhook:wecom from ALERT_WEBHOOK_WECOM."""
        with patch.dict(os.environ, {"ALERT_WEBHOOK_WECOM": "https://hooks.example.com/wecom"}):
            result = resolve_destination("webhook:wecom")
            assert result == "https://hooks.example.com/wecom"


class TestGetDestinationsForAlert:
    """Tests for get_destinations_for_alert function."""

    def test_sev1_alert_routes_to_email_and_webhook(self):
        """SEV1 alert should route to both email and webhook channels."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_DEFAULT": "alerts@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.DB_WRITE_FAIL,  # Not in type_recipients
                severity=Severity.SEV1,
                summary="Database write failed",
            )
            destinations = get_destinations_for_alert(alert)
            # Should have email and webhook from global_recipients
            assert ("email", "alerts@example.com") in destinations
            assert ("webhook", "https://hooks.example.com/default") in destinations

    def test_sev2_alert_routes_to_webhook_only(self):
        """SEV2 alert should route to webhook only (not email)."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_DEFAULT": "alerts@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.ORDER_REJECTED,  # Not in type_recipients
                severity=Severity.SEV2,
                summary="Order rejected",
            )
            destinations = get_destinations_for_alert(alert)
            # Should only have webhook
            assert ("webhook", "https://hooks.example.com/default") in destinations
            # Email should not be included (SEV2 doesn't enable email channel)
            assert ("email", "alerts@example.com") not in destinations

    def test_sev3_alert_routes_nowhere(self):
        """SEV3 alert should not route anywhere (log only)."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_DEFAULT": "alerts@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.ORDER_FILLED,  # Not in type_recipients
                severity=Severity.SEV3,
                summary="Order filled",
            )
            destinations = get_destinations_for_alert(alert)
            # No channels enabled for SEV3
            assert destinations == []

    def test_alert_with_type_recipients_includes_them(self):
        """Alert with type in type_recipients should include those destinations."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_DEFAULT": "alerts@example.com",
                "ALERT_EMAIL_RISK": "risk@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.DAILY_LOSS_LIMIT,
                severity=Severity.SEV1,
                summary="Daily loss limit breached",
            )
            destinations = get_destinations_for_alert(alert)
            # Should have email:risk from type_recipients
            assert ("email", "risk@example.com") in destinations
            # Plus global recipients (email and webhook enabled for SEV1)
            assert ("email", "alerts@example.com") in destinations
            assert ("webhook", "https://hooks.example.com/default") in destinations

    def test_kill_switch_includes_ops_and_risk(self):
        """KILL_SWITCH_ACTIVATED should include both ops and risk emails."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_DEFAULT": "alerts@example.com",
                "ALERT_EMAIL_OPS": "ops@example.com",
                "ALERT_EMAIL_RISK": "risk@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.KILL_SWITCH_ACTIVATED,
                severity=Severity.SEV1,
                summary="Kill switch activated",
            )
            destinations = get_destinations_for_alert(alert)
            # type_recipients for KILL_SWITCH_ACTIVATED
            assert ("email", "ops@example.com") in destinations
            assert ("email", "risk@example.com") in destinations
            # global recipients
            assert ("email", "alerts@example.com") in destinations
            assert ("webhook", "https://hooks.example.com/default") in destinations

    def test_unresolved_destinations_are_skipped(self):
        """Destinations that cannot be resolved should be skipped."""
        with patch.dict(
            os.environ,
            {
                # Only set webhook, not email
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
            clear=True,
        ):
            # Make sure email env vars are not set
            os.environ.pop("ALERT_EMAIL_DEFAULT", None)
            os.environ.pop("ALERT_EMAIL_RISK", None)

            alert = create_alert(
                type=AlertType.DAILY_LOSS_LIMIT,
                severity=Severity.SEV1,
                summary="Daily loss limit breached",
            )
            destinations = get_destinations_for_alert(alert)
            # Only webhook should be present since emails aren't configured
            assert ("webhook", "https://hooks.example.com/default") in destinations
            # No email destinations since they couldn't be resolved
            for channel, _addr in destinations:
                if channel == "email":
                    pytest.fail("Email destination should not be present")

    def test_uses_default_config_when_none_provided(self):
        """Should use default RoutingConfig when none provided."""
        with patch.dict(
            os.environ,
            {
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.ORDER_REJECTED,
                severity=Severity.SEV2,
                summary="Order rejected",
            )
            # Call without config parameter
            destinations = get_destinations_for_alert(alert)
            assert ("webhook", "https://hooks.example.com/default") in destinations

    def test_uses_custom_config_when_provided(self):
        """Should use custom RoutingConfig when provided."""
        with patch.dict(
            os.environ,
            {
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
                "ALERT_WEBHOOK_WECOM": "https://hooks.example.com/wecom",
            },
        ):
            # Custom config that enables webhook for SEV3
            custom_config = RoutingConfig(
                severity_channels={
                    Severity.SEV1: ["webhook"],
                    Severity.SEV2: ["webhook"],
                    Severity.SEV3: ["webhook"],  # Enable webhook for SEV3
                },
                type_recipients={},
                global_recipients=["webhook:wecom"],
            )
            alert = create_alert(
                type=AlertType.ORDER_FILLED,
                severity=Severity.SEV3,
                summary="Order filled",
            )
            destinations = get_destinations_for_alert(alert, config=custom_config)
            # Should have webhook:wecom since we enabled webhook for SEV3
            assert ("webhook", "https://hooks.example.com/wecom") in destinations

    def test_no_duplicate_destinations(self):
        """Should not return duplicate destination tuples."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_DEFAULT": "alerts@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            # Create config where email:default appears in both global and type recipients
            custom_config = RoutingConfig(
                severity_channels={
                    Severity.SEV1: ["email", "webhook"],
                },
                type_recipients={
                    AlertType.DB_WRITE_FAIL: ["email:default"],  # Duplicate of global
                },
                global_recipients=["email:default", "webhook:default"],
            )
            alert = create_alert(
                type=AlertType.DB_WRITE_FAIL,
                severity=Severity.SEV1,
                summary="Database write failed",
            )
            destinations = get_destinations_for_alert(alert, config=custom_config)
            # Count occurrences of email:alerts@example.com
            email_count = sum(
                1 for ch, addr in destinations if ch == "email" and addr == "alerts@example.com"
            )
            assert email_count == 1

    def test_channel_filter_applies_to_type_recipients(self):
        """Type recipients should be filtered by enabled channels."""
        with patch.dict(
            os.environ,
            {
                "ALERT_EMAIL_RISK": "risk@example.com",
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            # DAILY_LOSS_LIMIT has email:risk in type_recipients
            # But SEV2 only enables webhook channel
            alert = create_alert(
                type=AlertType.DAILY_LOSS_LIMIT,
                severity=Severity.SEV2,  # Only webhook enabled
                summary="Daily loss limit",
            )
            destinations = get_destinations_for_alert(alert)
            # email:risk should NOT be included since email channel not enabled for SEV2
            assert ("email", "risk@example.com") not in destinations
            # webhook should be included
            assert ("webhook", "https://hooks.example.com/default") in destinations

    def test_returns_list_of_tuples(self):
        """Should return a list of (channel_type, resolved_destination) tuples."""
        with patch.dict(
            os.environ,
            {
                "ALERT_WEBHOOK_DEFAULT": "https://hooks.example.com/default",
            },
        ):
            alert = create_alert(
                type=AlertType.ORDER_REJECTED,
                severity=Severity.SEV2,
                summary="Order rejected",
            )
            destinations = get_destinations_for_alert(alert)
            assert isinstance(destinations, list)
            for item in destinations:
                assert isinstance(item, tuple)
                assert len(item) == 2
                channel, address = item
                assert isinstance(channel, str)
                assert isinstance(address, str)
