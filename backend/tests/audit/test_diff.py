"""Tests for audit diff computation and redaction utilities.

TDD: Write tests FIRST, then implement diff.py to make them pass.
"""

import json

from src.audit.config import MAX_VALUE_SIZE_BYTES
from src.audit.models import ValueMode


class TestComputeDiffJsonpatch:
    """Tests for compute_diff_jsonpatch function."""

    def test_returns_none_when_no_changes(self):
        """compute_diff_jsonpatch should return None when values are identical."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"name": "test", "value": 100}
        new = {"name": "test", "value": 100}

        result = compute_diff_jsonpatch(old, new)

        assert result is None

    def test_returns_patch_when_value_changed(self):
        """compute_diff_jsonpatch should return JSON Patch when values differ."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"name": "test", "value": 100}
        new = {"name": "test", "value": 200}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        assert isinstance(result, dict)
        assert "patch" in result
        # Should contain an operation to replace /value
        patch_ops = result["patch"]
        assert isinstance(patch_ops, list)
        assert len(patch_ops) == 1
        assert patch_ops[0]["op"] == "replace"
        assert patch_ops[0]["path"] == "/value"
        assert patch_ops[0]["value"] == 200

    def test_returns_patch_for_added_key(self):
        """compute_diff_jsonpatch should detect added keys."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"name": "test"}
        new = {"name": "test", "value": 100}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        assert len(patch_ops) == 1
        assert patch_ops[0]["op"] == "add"
        assert patch_ops[0]["path"] == "/value"
        assert patch_ops[0]["value"] == 100

    def test_returns_patch_for_removed_key(self):
        """compute_diff_jsonpatch should detect removed keys."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"name": "test", "value": 100}
        new = {"name": "test"}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        assert len(patch_ops) == 1
        assert patch_ops[0]["op"] == "remove"
        assert patch_ops[0]["path"] == "/value"

    def test_handles_nested_changes(self):
        """compute_diff_jsonpatch should detect nested dict changes."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"config": {"level": 10, "name": "prod"}}
        new = {"config": {"level": 20, "name": "prod"}}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        assert len(patch_ops) == 1
        assert patch_ops[0]["op"] == "replace"
        assert patch_ops[0]["path"] == "/config/level"
        assert patch_ops[0]["value"] == 20

    def test_handles_old_none(self):
        """compute_diff_jsonpatch should handle old=None (creation)."""
        from src.audit.diff import compute_diff_jsonpatch

        old = None
        new = {"name": "test", "value": 100}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        # When going from None to dict, all keys are adds
        assert len(patch_ops) >= 1

    def test_handles_new_none(self):
        """compute_diff_jsonpatch should handle new=None (deletion)."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"name": "test", "value": 100}
        new = None

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        # When going from dict to None, all keys are removes
        assert len(patch_ops) >= 1

    def test_handles_both_none(self):
        """compute_diff_jsonpatch should return None when both are None."""
        from src.audit.diff import compute_diff_jsonpatch

        result = compute_diff_jsonpatch(None, None)

        assert result is None

    def test_multiple_changes(self):
        """compute_diff_jsonpatch should detect multiple changes."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"a": 1, "b": 2, "c": 3}
        new = {"a": 10, "b": 2, "d": 4}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        # a changed (replace), c removed (remove), d added (add)
        assert len(patch_ops) == 3

    def test_array_changes(self):
        """compute_diff_jsonpatch should detect array changes."""
        from src.audit.diff import compute_diff_jsonpatch

        old = {"items": [1, 2, 3]}
        new = {"items": [1, 2, 3, 4]}

        result = compute_diff_jsonpatch(old, new)

        assert result is not None
        patch_ops = result["patch"]
        assert len(patch_ops) >= 1


class TestRedactSensitiveFields:
    """Tests for redact_sensitive_fields function."""

    def test_returns_none_for_none_input(self):
        """redact_sensitive_fields should return None when data is None."""
        from src.audit.diff import redact_sensitive_fields

        result = redact_sensitive_fields(None, "account")

        assert result is None

    def test_redacts_account_sensitive_fields(self):
        """redact_sensitive_fields should mask account-specific fields."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "name": "trading_account",
            "api_key": "sk_live_abc123xyz789",
            "api_secret": "secret_value_here",
            "password": "mypassword123",
            "token": "bearer_token_here",
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        assert result["name"] == "trading_account"  # Not redacted
        # Redacted fields should be masked (first 2 and last 2 chars)
        assert result["api_key"] == "sk****89"
        assert result["api_secret"] == "se****re"
        assert result["password"] == "my****23"
        assert result["token"] == "be****re"

    def test_redacts_config_sensitive_fields(self):
        """redact_sensitive_fields should mask config-specific fields."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "name": "settings",
            "credentials": "cred_abc123",
            "secret": "mysecretvalue",
            "password": "pass123",
            "key": "apikey_xyz",
        }

        result = redact_sensitive_fields(data, "config")

        assert result is not None
        assert result["name"] == "settings"
        assert result["credentials"] == "cr****23"
        assert result["secret"] == "my****ue"
        assert result["password"] == "pa****23"
        assert result["key"] == "ap****yz"

    def test_redacts_global_sensitive_fields(self):
        """redact_sensitive_fields should mask global fields for any resource type."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "name": "John Doe",
            "email": "john.doe@example.com",
            "phone": "+1-555-123-4567",
            "id_card": "ID123456789",
            "ssn": "123-45-6789",
        }

        result = redact_sensitive_fields(data, "order")  # Any resource type

        assert result is not None
        assert result["name"] == "John Doe"  # Not in global rules
        assert result["email"] == "jo****om"
        assert result["phone"] == "+1****67"
        assert result["id_card"] == "ID****89"
        assert result["ssn"] == "12****89"

    def test_redacts_nested_fields(self):
        """redact_sensitive_fields should handle nested dicts."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "user": {
                "name": "John",
                "email": "john@example.com",
                "credentials": {
                    "api_key": "key_12345678",
                    "password": "secretpass",
                },
            }
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        assert result["user"]["name"] == "John"
        assert result["user"]["email"] == "jo****om"
        assert result["user"]["credentials"]["api_key"] == "ke****78"
        assert result["user"]["credentials"]["password"] == "se****ss"

    def test_handles_short_values(self):
        """redact_sensitive_fields should handle values shorter than 4 chars."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "api_key": "abc",  # Only 3 chars
            "token": "ab",  # Only 2 chars
            "password": "a",  # Only 1 char
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        # Short values should be fully masked
        assert result["api_key"] == "****"
        assert result["token"] == "****"
        assert result["password"] == "****"

    def test_preserves_non_sensitive_fields(self):
        """redact_sensitive_fields should not modify non-sensitive fields."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "account_id": "acc_123",
            "balance": 10000.50,
            "active": True,
            "tags": ["trading", "live"],
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        assert result["account_id"] == "acc_123"
        assert result["balance"] == 10000.50
        assert result["active"] is True
        assert result["tags"] == ["trading", "live"]

    def test_combines_type_specific_and_global_rules(self):
        """redact_sensitive_fields should apply both type-specific and global rules."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "name": "My Account",
            "api_key": "key_12345678",  # account-specific
            "email": "test@example.com",  # global
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        assert result["name"] == "My Account"
        assert result["api_key"] == "ke****78"
        assert result["email"] == "te****om"

    def test_unknown_resource_type_applies_global_only(self):
        """redact_sensitive_fields should apply global rules for unknown resource types."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "name": "Test",
            "email": "test@example.com",
            "custom_field": "value123",
        }

        result = redact_sensitive_fields(data, "unknown_type")

        assert result is not None
        assert result["name"] == "Test"
        assert result["email"] == "te****om"
        assert result["custom_field"] == "value123"

    def test_handles_non_string_sensitive_values(self):
        """redact_sensitive_fields should handle non-string values gracefully."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "password": 12345,  # Number, not string
            "api_key": None,  # None value
            "token": True,  # Boolean
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        # Non-string values should be replaced with ****
        assert result["password"] == "****"
        assert result["api_key"] == "****"
        assert result["token"] == "****"

    def test_handles_list_with_nested_dicts(self):
        """redact_sensitive_fields should handle lists containing dicts."""
        from src.audit.diff import redact_sensitive_fields

        data = {
            "users": [
                {"name": "User1", "email": "user1@example.com"},
                {"name": "User2", "email": "user2@example.com"},
            ]
        }

        result = redact_sensitive_fields(data, "account")

        assert result is not None
        assert result["users"][0]["name"] == "User1"
        assert result["users"][0]["email"] == "us****om"
        assert result["users"][1]["name"] == "User2"
        assert result["users"][1]["email"] == "us****om"


class TestEnforceSizeLimit:
    """Tests for enforce_size_limit function."""

    def test_returns_none_for_none_input(self):
        """enforce_size_limit should handle None value."""
        from src.audit.diff import enforce_size_limit

        value, hash_val, mode = enforce_size_limit(None, "order", "order-123")

        assert value is None
        assert hash_val is None
        assert mode == ValueMode.DIFF

    def test_returns_value_when_within_limit(self):
        """enforce_size_limit should return value unchanged when within limit."""
        from src.audit.diff import enforce_size_limit

        small_value = {"name": "test", "data": "x" * 100}

        value, hash_val, mode = enforce_size_limit(small_value, "order", "order-123")

        assert value == small_value
        assert hash_val is None
        assert mode in (ValueMode.DIFF, ValueMode.SNAPSHOT)

    def test_returns_reference_when_exceeds_limit(self):
        """enforce_size_limit should switch to REFERENCE when value exceeds limit."""
        from src.audit.diff import enforce_size_limit

        # Create value larger than MAX_VALUE_SIZE_BYTES (32768)
        large_value = {"data": "x" * 40000}

        value, hash_val, mode = enforce_size_limit(large_value, "order", "order-123")

        assert value is None
        assert hash_val is not None
        assert len(hash_val) == 64  # SHA256 hex digest
        assert mode == ValueMode.REFERENCE

    def test_hash_is_sha256_of_value(self):
        """enforce_size_limit should compute SHA256 hash of serialized value."""
        import hashlib

        from src.audit.diff import enforce_size_limit

        large_value = {"data": "x" * 40000}

        value, hash_val, mode = enforce_size_limit(large_value, "order", "order-123")

        # Verify hash matches
        expected_hash = hashlib.sha256(
            json.dumps(large_value, sort_keys=True).encode("utf-8")
        ).hexdigest()
        assert hash_val == expected_hash

    def test_size_check_uses_json_serialization(self):
        """enforce_size_limit should check size of JSON-serialized value."""
        from src.audit.diff import enforce_size_limit

        # Create value that's just under the limit
        # MAX_VALUE_SIZE_BYTES is 32768
        # JSON adds some overhead for keys and structure
        data_size = MAX_VALUE_SIZE_BYTES - 100  # Leave room for JSON overhead
        small_value = {"data": "x" * data_size}

        # This should be within limit
        value, hash_val, mode = enforce_size_limit(small_value, "order", "order-123")

        # Check actual size
        actual_size = len(json.dumps(small_value).encode("utf-8"))
        if actual_size <= MAX_VALUE_SIZE_BYTES:
            assert value == small_value
            assert hash_val is None
        else:
            assert value is None
            assert hash_val is not None
            assert mode == ValueMode.REFERENCE

    def test_boundary_at_max_size(self):
        """enforce_size_limit should handle values exactly at the limit."""
        from src.audit.diff import enforce_size_limit

        # Create value exactly at the limit
        # We need to account for JSON overhead
        base = {"d": ""}
        base_size = len(json.dumps(base).encode("utf-8"))
        remaining = MAX_VALUE_SIZE_BYTES - base_size
        exactly_at_limit = {"d": "x" * remaining}

        value, hash_val, mode = enforce_size_limit(exactly_at_limit, "order", "order-123")

        # Exactly at limit should be accepted
        actual_size = len(json.dumps(exactly_at_limit).encode("utf-8"))
        assert actual_size == MAX_VALUE_SIZE_BYTES
        assert value == exactly_at_limit
        assert hash_val is None

    def test_returns_diff_mode_by_default(self):
        """enforce_size_limit should return DIFF mode for small values by default."""
        from src.audit.diff import enforce_size_limit

        small_value = {"name": "test"}

        value, hash_val, mode = enforce_size_limit(small_value, "config", "config-123")

        assert mode == ValueMode.DIFF

    def test_empty_dict_returns_value(self):
        """enforce_size_limit should return empty dict unchanged."""
        from src.audit.diff import enforce_size_limit

        empty_value = {}

        value, hash_val, mode = enforce_size_limit(empty_value, "order", "order-123")

        assert value == {}
        assert hash_val is None

    def test_nested_structure_size_check(self):
        """enforce_size_limit should check total serialized size including nested."""
        from src.audit.diff import enforce_size_limit

        # Create deeply nested structure that exceeds limit
        nested = {"level1": {"level2": {"level3": {"data": "x" * 40000}}}}

        value, hash_val, mode = enforce_size_limit(nested, "order", "order-123")

        assert value is None
        assert hash_val is not None
        assert mode == ValueMode.REFERENCE


class TestIntegration:
    """Integration tests combining diff and redaction."""

    def test_redact_then_diff(self):
        """Test typical flow: redact sensitive data, then compute diff."""
        from src.audit.diff import compute_diff_jsonpatch, redact_sensitive_fields

        old = {
            "name": "My Config",
            "api_key": "old_key_12345",
            "value": 100,
        }
        new = {
            "name": "My Config",
            "api_key": "new_key_67890",
            "value": 200,
        }

        # First redact
        old_redacted = redact_sensitive_fields(old, "config")
        new_redacted = redact_sensitive_fields(new, "config")

        # Then diff
        diff = compute_diff_jsonpatch(old_redacted, new_redacted)

        assert diff is not None
        patch_ops = diff["patch"]
        # Should see changes to api_key (redacted) and value
        assert len(patch_ops) == 2

    def test_diff_with_size_limit_check(self):
        """Test computing diff and checking size limit."""
        from src.audit.diff import compute_diff_jsonpatch, enforce_size_limit

        old = {"value": 1}
        new = {"value": 2, "large_field": "x" * 40000}

        diff = compute_diff_jsonpatch(old, new)

        # The new value is large
        value, hash_val, mode = enforce_size_limit(new, "order", "order-123")

        assert value is None
        assert hash_val is not None
        assert mode == ValueMode.REFERENCE
