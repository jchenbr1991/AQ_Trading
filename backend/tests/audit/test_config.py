"""Tests for audit tier configuration and value mode rules.

TDD: Write tests FIRST, then implement config to make them pass.
"""

from src.audit.models import AuditEventType, ValueMode


class TestTier0Events:
    """Tests for TIER_0_EVENTS frozenset - sync write events."""

    def test_tier_0_events_is_frozenset(self):
        """TIER_0_EVENTS should be a frozenset."""
        from src.audit.config import TIER_0_EVENTS

        assert isinstance(TIER_0_EVENTS, frozenset)

    def test_tier_0_contains_order_placed(self):
        """ORDER_PLACED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.ORDER_PLACED in TIER_0_EVENTS

    def test_tier_0_contains_order_filled(self):
        """ORDER_FILLED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.ORDER_FILLED in TIER_0_EVENTS

    def test_tier_0_contains_order_cancelled(self):
        """ORDER_CANCELLED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.ORDER_CANCELLED in TIER_0_EVENTS

    def test_tier_0_contains_order_rejected(self):
        """ORDER_REJECTED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.ORDER_REJECTED in TIER_0_EVENTS

    def test_tier_0_contains_config_created(self):
        """CONFIG_CREATED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.CONFIG_CREATED in TIER_0_EVENTS

    def test_tier_0_contains_config_updated(self):
        """CONFIG_UPDATED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.CONFIG_UPDATED in TIER_0_EVENTS

    def test_tier_0_contains_config_deleted(self):
        """CONFIG_DELETED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.CONFIG_DELETED in TIER_0_EVENTS

    def test_tier_0_contains_permission_changed(self):
        """PERMISSION_CHANGED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.PERMISSION_CHANGED in TIER_0_EVENTS

    def test_tier_0_contains_auth_login(self):
        """AUTH_LOGIN requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.AUTH_LOGIN in TIER_0_EVENTS

    def test_tier_0_contains_auth_failed(self):
        """AUTH_FAILED requires sync write."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.AUTH_FAILED in TIER_0_EVENTS

    def test_tier_0_does_not_contain_alert_emitted(self):
        """ALERT_EMITTED should be tier 1, not tier 0."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.ALERT_EMITTED not in TIER_0_EVENTS

    def test_tier_0_does_not_contain_system_started(self):
        """SYSTEM_STARTED should be tier 1, not tier 0."""
        from src.audit.config import TIER_0_EVENTS

        assert AuditEventType.SYSTEM_STARTED not in TIER_0_EVENTS


class TestTier1Events:
    """Tests for TIER_1_EVENTS frozenset - async write events."""

    def test_tier_1_events_is_frozenset(self):
        """TIER_1_EVENTS should be a frozenset."""
        from src.audit.config import TIER_1_EVENTS

        assert isinstance(TIER_1_EVENTS, frozenset)

    def test_tier_1_contains_alert_emitted(self):
        """ALERT_EMITTED is async write."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.ALERT_EMITTED in TIER_1_EVENTS

    def test_tier_1_contains_alert_acknowledged(self):
        """ALERT_ACKNOWLEDGED is async write."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.ALERT_ACKNOWLEDGED in TIER_1_EVENTS

    def test_tier_1_contains_alert_resolved(self):
        """ALERT_RESOLVED is async write."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.ALERT_RESOLVED in TIER_1_EVENTS

    def test_tier_1_contains_health_changed(self):
        """HEALTH_CHANGED is async write."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.HEALTH_CHANGED in TIER_1_EVENTS

    def test_tier_1_contains_system_started(self):
        """SYSTEM_STARTED is async write."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.SYSTEM_STARTED in TIER_1_EVENTS

    def test_tier_1_contains_system_stopped(self):
        """SYSTEM_STOPPED is async write."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.SYSTEM_STOPPED in TIER_1_EVENTS

    def test_tier_1_does_not_contain_order_placed(self):
        """ORDER_PLACED should be tier 0, not tier 1."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.ORDER_PLACED not in TIER_1_EVENTS

    def test_tier_1_does_not_contain_auth_login(self):
        """AUTH_LOGIN should be tier 0, not tier 1."""
        from src.audit.config import TIER_1_EVENTS

        assert AuditEventType.AUTH_LOGIN not in TIER_1_EVENTS


class TestTiersNoOverlap:
    """Tests to ensure tiers don't overlap."""

    def test_tier_0_and_tier_1_have_no_overlap(self):
        """TIER_0_EVENTS and TIER_1_EVENTS should be disjoint."""
        from src.audit.config import TIER_0_EVENTS, TIER_1_EVENTS

        overlap = TIER_0_EVENTS & TIER_1_EVENTS
        assert len(overlap) == 0, f"Tiers overlap on: {overlap}"


class TestValueModeConfig:
    """Tests for VALUE_MODE_CONFIG dict."""

    def test_value_mode_config_is_dict(self):
        """VALUE_MODE_CONFIG should be a dict."""
        from src.audit.config import VALUE_MODE_CONFIG

        assert isinstance(VALUE_MODE_CONFIG, dict)

    def test_config_updated_uses_diff_mode(self):
        """CONFIG_UPDATED should use DIFF mode."""
        from src.audit.config import VALUE_MODE_CONFIG

        assert VALUE_MODE_CONFIG.get(AuditEventType.CONFIG_UPDATED) == ValueMode.DIFF

    def test_permission_changed_uses_diff_mode(self):
        """PERMISSION_CHANGED should use DIFF mode."""
        from src.audit.config import VALUE_MODE_CONFIG

        assert VALUE_MODE_CONFIG.get(AuditEventType.PERMISSION_CHANGED) == ValueMode.DIFF

    def test_order_placed_uses_snapshot_mode(self):
        """ORDER_PLACED should use SNAPSHOT mode."""
        from src.audit.config import VALUE_MODE_CONFIG

        assert VALUE_MODE_CONFIG.get(AuditEventType.ORDER_PLACED) == ValueMode.SNAPSHOT

    def test_order_filled_uses_snapshot_mode(self):
        """ORDER_FILLED should use SNAPSHOT mode."""
        from src.audit.config import VALUE_MODE_CONFIG

        assert VALUE_MODE_CONFIG.get(AuditEventType.ORDER_FILLED) == ValueMode.SNAPSHOT

    def test_order_cancelled_uses_snapshot_mode(self):
        """ORDER_CANCELLED should use SNAPSHOT mode."""
        from src.audit.config import VALUE_MODE_CONFIG

        assert VALUE_MODE_CONFIG.get(AuditEventType.ORDER_CANCELLED) == ValueMode.SNAPSHOT


class TestChecksumFields:
    """Tests for CHECKSUM_FIELDS list."""

    def test_checksum_fields_is_list(self):
        """CHECKSUM_FIELDS should be a list."""
        from src.audit.config import CHECKSUM_FIELDS

        assert isinstance(CHECKSUM_FIELDS, list)

    def test_checksum_fields_contains_event_id(self):
        """CHECKSUM_FIELDS should include event_id."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "event_id" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_timestamp(self):
        """CHECKSUM_FIELDS should include timestamp."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "timestamp" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_event_type(self):
        """CHECKSUM_FIELDS should include event_type."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "event_type" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_actor_id(self):
        """CHECKSUM_FIELDS should include actor_id."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "actor_id" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_resource_type(self):
        """CHECKSUM_FIELDS should include resource_type."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "resource_type" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_resource_id(self):
        """CHECKSUM_FIELDS should include resource_id."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "resource_id" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_old_value(self):
        """CHECKSUM_FIELDS should include old_value."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "old_value" in CHECKSUM_FIELDS

    def test_checksum_fields_contains_new_value(self):
        """CHECKSUM_FIELDS should include new_value."""
        from src.audit.config import CHECKSUM_FIELDS

        assert "new_value" in CHECKSUM_FIELDS


class TestRedactionRules:
    """Tests for REDACTION_RULES dict."""

    def test_redaction_rules_is_dict(self):
        """REDACTION_RULES should be a dict."""
        from src.audit.config import REDACTION_RULES

        assert isinstance(REDACTION_RULES, dict)

    def test_account_redaction_has_api_key(self):
        """Account resources should redact api_key."""
        from src.audit.config import REDACTION_RULES

        assert "api_key" in REDACTION_RULES.get("account", [])

    def test_account_redaction_has_api_secret(self):
        """Account resources should redact api_secret."""
        from src.audit.config import REDACTION_RULES

        assert "api_secret" in REDACTION_RULES.get("account", [])

    def test_account_redaction_has_password(self):
        """Account resources should redact password."""
        from src.audit.config import REDACTION_RULES

        assert "password" in REDACTION_RULES.get("account", [])

    def test_account_redaction_has_token(self):
        """Account resources should redact token."""
        from src.audit.config import REDACTION_RULES

        assert "token" in REDACTION_RULES.get("account", [])

    def test_config_redaction_has_credentials(self):
        """Config resources should redact credentials."""
        from src.audit.config import REDACTION_RULES

        assert "credentials" in REDACTION_RULES.get("config", [])

    def test_config_redaction_has_secret(self):
        """Config resources should redact secret."""
        from src.audit.config import REDACTION_RULES

        assert "secret" in REDACTION_RULES.get("config", [])

    def test_config_redaction_has_password(self):
        """Config resources should redact password."""
        from src.audit.config import REDACTION_RULES

        assert "password" in REDACTION_RULES.get("config", [])

    def test_config_redaction_has_key(self):
        """Config resources should redact key."""
        from src.audit.config import REDACTION_RULES

        assert "key" in REDACTION_RULES.get("config", [])

    def test_global_redaction_has_email(self):
        """Global rules should redact email."""
        from src.audit.config import REDACTION_RULES

        assert "email" in REDACTION_RULES.get("*", [])

    def test_global_redaction_has_phone(self):
        """Global rules should redact phone."""
        from src.audit.config import REDACTION_RULES

        assert "phone" in REDACTION_RULES.get("*", [])

    def test_global_redaction_has_id_card(self):
        """Global rules should redact id_card."""
        from src.audit.config import REDACTION_RULES

        assert "id_card" in REDACTION_RULES.get("*", [])

    def test_global_redaction_has_ssn(self):
        """Global rules should redact ssn."""
        from src.audit.config import REDACTION_RULES

        assert "ssn" in REDACTION_RULES.get("*", [])


class TestConstants:
    """Tests for size limit constants."""

    def test_max_value_size_bytes(self):
        """MAX_VALUE_SIZE_BYTES should be 32768."""
        from src.audit.config import MAX_VALUE_SIZE_BYTES

        assert MAX_VALUE_SIZE_BYTES == 32768

    def test_max_metadata_size_bytes(self):
        """MAX_METADATA_SIZE_BYTES should be 8192."""
        from src.audit.config import MAX_METADATA_SIZE_BYTES

        assert MAX_METADATA_SIZE_BYTES == 8192


class TestGetTierFunction:
    """Tests for get_tier() helper function."""

    def test_get_tier_returns_0_for_tier_0_event(self):
        """get_tier should return 0 for tier 0 events."""
        from src.audit.config import get_tier

        assert get_tier(AuditEventType.ORDER_PLACED) == 0

    def test_get_tier_returns_0_for_auth_login(self):
        """get_tier should return 0 for AUTH_LOGIN."""
        from src.audit.config import get_tier

        assert get_tier(AuditEventType.AUTH_LOGIN) == 0

    def test_get_tier_returns_0_for_config_updated(self):
        """get_tier should return 0 for CONFIG_UPDATED."""
        from src.audit.config import get_tier

        assert get_tier(AuditEventType.CONFIG_UPDATED) == 0

    def test_get_tier_returns_1_for_tier_1_event(self):
        """get_tier should return 1 for tier 1 events."""
        from src.audit.config import get_tier

        assert get_tier(AuditEventType.ALERT_EMITTED) == 1

    def test_get_tier_returns_1_for_system_started(self):
        """get_tier should return 1 for SYSTEM_STARTED."""
        from src.audit.config import get_tier

        assert get_tier(AuditEventType.SYSTEM_STARTED) == 1

    def test_get_tier_returns_1_for_health_changed(self):
        """get_tier should return 1 for HEALTH_CHANGED."""
        from src.audit.config import get_tier

        assert get_tier(AuditEventType.HEALTH_CHANGED) == 1

    def test_get_tier_returns_1_for_unknown_event(self):
        """get_tier should return 1 (async) for events not in either tier."""
        from src.audit.config import get_tier

        # ORDER_ACKNOWLEDGED is not in tier 0 or tier 1 explicitly
        assert get_tier(AuditEventType.ORDER_ACKNOWLEDGED) == 1


class TestGetValueModeFunction:
    """Tests for get_value_mode() helper function."""

    def test_get_value_mode_returns_diff_for_config_updated(self):
        """get_value_mode should return DIFF for CONFIG_UPDATED."""
        from src.audit.config import get_value_mode

        assert get_value_mode(AuditEventType.CONFIG_UPDATED) == ValueMode.DIFF

    def test_get_value_mode_returns_diff_for_permission_changed(self):
        """get_value_mode should return DIFF for PERMISSION_CHANGED."""
        from src.audit.config import get_value_mode

        assert get_value_mode(AuditEventType.PERMISSION_CHANGED) == ValueMode.DIFF

    def test_get_value_mode_returns_snapshot_for_order_placed(self):
        """get_value_mode should return SNAPSHOT for ORDER_PLACED."""
        from src.audit.config import get_value_mode

        assert get_value_mode(AuditEventType.ORDER_PLACED) == ValueMode.SNAPSHOT

    def test_get_value_mode_returns_snapshot_for_order_filled(self):
        """get_value_mode should return SNAPSHOT for ORDER_FILLED."""
        from src.audit.config import get_value_mode

        assert get_value_mode(AuditEventType.ORDER_FILLED) == ValueMode.SNAPSHOT

    def test_get_value_mode_returns_snapshot_for_order_cancelled(self):
        """get_value_mode should return SNAPSHOT for ORDER_CANCELLED."""
        from src.audit.config import get_value_mode

        assert get_value_mode(AuditEventType.ORDER_CANCELLED) == ValueMode.SNAPSHOT

    def test_get_value_mode_returns_diff_as_default(self):
        """get_value_mode should return DIFF as default for unconfigured events."""
        from src.audit.config import get_value_mode

        # ALERT_EMITTED is not explicitly configured, should default to DIFF
        assert get_value_mode(AuditEventType.ALERT_EMITTED) == ValueMode.DIFF


class TestIsSyncRequiredFunction:
    """Tests for is_sync_required() helper function."""

    def test_is_sync_required_true_for_tier_0_event(self):
        """is_sync_required should return True for tier 0 events."""
        from src.audit.config import is_sync_required

        assert is_sync_required(AuditEventType.ORDER_PLACED) is True

    def test_is_sync_required_true_for_auth_failed(self):
        """is_sync_required should return True for AUTH_FAILED."""
        from src.audit.config import is_sync_required

        assert is_sync_required(AuditEventType.AUTH_FAILED) is True

    def test_is_sync_required_true_for_config_deleted(self):
        """is_sync_required should return True for CONFIG_DELETED."""
        from src.audit.config import is_sync_required

        assert is_sync_required(AuditEventType.CONFIG_DELETED) is True

    def test_is_sync_required_false_for_tier_1_event(self):
        """is_sync_required should return False for tier 1 events."""
        from src.audit.config import is_sync_required

        assert is_sync_required(AuditEventType.ALERT_EMITTED) is False

    def test_is_sync_required_false_for_system_stopped(self):
        """is_sync_required should return False for SYSTEM_STOPPED."""
        from src.audit.config import is_sync_required

        assert is_sync_required(AuditEventType.SYSTEM_STOPPED) is False

    def test_is_sync_required_false_for_unknown_event(self):
        """is_sync_required should return False for uncategorized events."""
        from src.audit.config import is_sync_required

        # AUTH_LOGOUT is not in tier 0
        assert is_sync_required(AuditEventType.AUTH_LOGOUT) is False
