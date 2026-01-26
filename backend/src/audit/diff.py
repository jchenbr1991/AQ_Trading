"""Audit diff computation and redaction utilities.

This module provides functions for computing diffs between values and
redacting sensitive information for audit logging:
- compute_diff_jsonpatch: Compute JSON Patch (RFC 6902) between two values
- redact_sensitive_fields: Mask sensitive fields based on redaction rules
- enforce_size_limit: Check value size and auto-switch to reference mode if needed

Functions:
    compute_diff_jsonpatch: Compute JSON Patch format diff between old and new values
    redact_sensitive_fields: Apply redaction rules to mask sensitive data
    enforce_size_limit: Enforce max size limit, switching to hash reference if exceeded
"""

import copy
import hashlib
import json
from typing import Any

import jsonpatch

from src.audit.config import MAX_VALUE_SIZE_BYTES, REDACTION_RULES
from src.audit.models import ValueMode


def compute_diff_jsonpatch(old: dict | None, new: dict | None) -> dict | None:
    """Compute JSON Patch format diff between two values.

    Uses the jsonpatch library to compute RFC 6902 compliant JSON Patch
    representing the changes from old to new.

    Args:
        old: The original value (None for creation).
        new: The new value (None for deletion).

    Returns:
        A dict containing {"patch": [operations]} if there are changes,
        None if the values are identical.
    """
    # Handle None cases
    if old is None and new is None:
        return None

    # Treat None as empty dict for diff computation
    old_val = old if old is not None else {}
    new_val = new if new is not None else {}

    # Compute the patch
    patch = jsonpatch.make_patch(old_val, new_val)

    # If no operations, values are identical
    if not patch.patch:
        return None

    return {"patch": patch.patch}


def _mask_value(value: str) -> str:
    """Mask a sensitive string value, keeping first 2 and last 2 chars.

    Args:
        value: The string value to mask.

    Returns:
        Masked string with first 2 and last 2 characters visible,
        or "****" if the value is too short.
    """
    if len(value) < 4:
        return "****"
    return f"{value[:2]}****{value[-2:]}"


def _redact_value(value: Any, sensitive_fields: set[str], key: str) -> Any:
    """Recursively redact sensitive fields in a value.

    Args:
        value: The value to redact (can be dict, list, or primitive).
        sensitive_fields: Set of field names to redact.
        key: The current key name (for checking if this field should be redacted).

    Returns:
        The redacted value.
    """
    if isinstance(value, dict):
        return {k: _redact_value(v, sensitive_fields, k) for k, v in value.items()}
    elif isinstance(value, list):
        return [_redact_value(item, sensitive_fields, key) for item in value]
    else:
        # Check if the key should be redacted
        if key in sensitive_fields:
            if isinstance(value, str):
                return _mask_value(value)
            else:
                # Non-string sensitive values are fully masked
                return "****"
        return value


def redact_sensitive_fields(data: dict | None, resource_type: str) -> dict | None:
    """Apply redaction rules to mask sensitive fields in data.

    Applies both resource-type-specific rules and global rules ("*")
    to mask sensitive information before storing in audit logs.

    Args:
        data: The dict data to redact (None returns None).
        resource_type: The resource type to look up redaction rules for.

    Returns:
        A copy of the data with sensitive fields masked,
        or None if data was None.
    """
    if data is None:
        return None

    # Build set of sensitive fields to redact
    sensitive_fields: set[str] = set()

    # Add resource-type-specific rules
    if resource_type in REDACTION_RULES:
        sensitive_fields.update(REDACTION_RULES[resource_type])

    # Add global rules
    if "*" in REDACTION_RULES:
        sensitive_fields.update(REDACTION_RULES["*"])

    # Deep copy to avoid modifying original
    result = copy.deepcopy(data)

    # Redact recursively
    return {k: _redact_value(v, sensitive_fields, k) for k, v in result.items()}


def enforce_size_limit(
    value: dict | None,
    resource_type: str,
    resource_id: str,
) -> tuple[dict | None, str | None, ValueMode]:
    """Enforce maximum size limit on audit value, switching to reference if needed.

    Checks if the JSON-serialized value exceeds MAX_VALUE_SIZE_BYTES.
    If it does, returns a SHA256 hash reference instead of the value.

    Args:
        value: The dict value to check (None is handled gracefully).
        resource_type: The resource type (for context).
        resource_id: The resource ID (for context).

    Returns:
        Tuple of (value, hash, mode):
        - If within limit: (value, None, ValueMode.DIFF)
        - If exceeds limit: (None, sha256_hash, ValueMode.REFERENCE)
        - If value is None: (None, None, ValueMode.DIFF)
    """
    if value is None:
        return (None, None, ValueMode.DIFF)

    # Serialize to JSON to check size
    serialized = json.dumps(value, sort_keys=True).encode("utf-8")
    size = len(serialized)

    if size <= MAX_VALUE_SIZE_BYTES:
        # Within limit - return value unchanged
        return (value, None, ValueMode.DIFF)
    else:
        # Exceeds limit - switch to reference mode
        value_hash = hashlib.sha256(serialized).hexdigest()
        return (None, value_hash, ValueMode.REFERENCE)
