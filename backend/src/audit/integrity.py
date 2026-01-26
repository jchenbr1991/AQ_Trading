"""Audit checksum and chain integrity verification.

This module provides functions for computing and verifying checksums for
audit events, ensuring data integrity and tamper detection.

Functions:
    compute_checksum: Compute SHA256 checksum for an audit event
    verify_checksum: Verify stored checksum matches recomputed value
    verify_chain: Verify integrity of a chain of audit events
"""

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from src.audit.config import CHECKSUM_FIELDS
from src.audit.models import AuditEvent


def _serialize_value(value: Any) -> Any:
    """Serialize a value for canonical JSON representation.

    Args:
        value: The value to serialize.

    Returns:
        A JSON-serializable representation of the value.
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True)
    return value


def compute_checksum(event: AuditEvent, sequence_id: int, prev_checksum: str | None) -> str:
    """Compute SHA256 checksum for an audit event.

    Creates a canonical form dict with CHECKSUM_FIELDS, adds sequence_id
    and prev_checksum, then computes SHA256 hash of the JSON-serialized content.

    Args:
        event: The audit event to compute checksum for.
        sequence_id: The sequence ID of this event in the chain.
        prev_checksum: The checksum of the previous event (None for first event).

    Returns:
        Hex digest of the SHA256 hash.
    """
    # Build canonical content dict from CHECKSUM_FIELDS
    content: dict[str, Any] = {}
    for field in CHECKSUM_FIELDS:
        value = getattr(event, field)
        content[field] = _serialize_value(value)

    # Add chain fields
    content["sequence_id"] = sequence_id
    content["prev_checksum"] = prev_checksum

    # Serialize to JSON with sorted keys for deterministic output
    canonical_json = json.dumps(content, sort_keys=True)

    # Compute SHA256 hash
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def _compute_checksum_from_row(event_row: dict, sequence_id: int, prev_checksum: str | None) -> str:
    """Compute SHA256 checksum from a database row dict.

    Args:
        event_row: Dict containing event data from database.
        sequence_id: The sequence ID of this event in the chain.
        prev_checksum: The checksum of the previous event (None for first event).

    Returns:
        Hex digest of the SHA256 hash.
    """
    content: dict[str, Any] = {}

    for field in CHECKSUM_FIELDS:
        value = event_row.get(field)
        # For dict values (old_value/new_value), serialize with sort_keys
        if isinstance(value, dict):
            content[field] = json.dumps(value, sort_keys=True)
        else:
            content[field] = value

    # Add chain fields
    content["sequence_id"] = sequence_id
    content["prev_checksum"] = prev_checksum

    # Serialize to JSON with sorted keys for deterministic output
    canonical_json = json.dumps(content, sort_keys=True)

    # Compute SHA256 hash
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_checksum(event_row: dict, sequence_id: int, prev_checksum: str | None) -> bool:
    """Verify stored checksum matches recomputed value.

    Recomputes the checksum from the row data and compares with stored checksum.

    Args:
        event_row: Dict containing event data from database, including 'checksum'.
        sequence_id: The sequence ID of this event in the chain.
        prev_checksum: The checksum of the previous event (None for first event).

    Returns:
        True if stored checksum matches recomputed value, False otherwise.
    """
    stored_checksum = event_row.get("checksum")
    computed_checksum = _compute_checksum_from_row(event_row, sequence_id, prev_checksum)
    return stored_checksum == computed_checksum


def verify_chain(events: list[dict]) -> tuple[bool, list[str]]:
    """Verify integrity of a chain of audit events.

    Verifies:
    - sequence_id is monotonically increasing
    - Each event's prev_checksum matches previous event's checksum
    - First event's prev_checksum is None
    - Each event's stored checksum is valid

    Args:
        events: List of event dicts ordered by sequence_id ascending.

    Returns:
        Tuple of (is_valid, list_of_errors).
        is_valid is True if all checks pass, False otherwise.
        list_of_errors contains descriptions of any errors found.
    """
    if not events:
        return True, []

    errors: list[str] = []
    prev_sequence_id: int | None = None
    prev_checksum: str | None = None

    for i, event in enumerate(events):
        sequence_id = event.get("sequence_id")
        stored_checksum = event.get("checksum")
        stored_prev_checksum = event.get("prev_checksum")

        # Check first event has prev_checksum = None
        if i == 0:
            if stored_prev_checksum is not None:
                errors.append(
                    f"First event (sequence_id={sequence_id}) should have "
                    f"prev_checksum=None, got '{stored_prev_checksum}'"
                )

        # Check sequence_id is monotonically increasing
        if prev_sequence_id is not None:
            if sequence_id <= prev_sequence_id:
                errors.append(
                    f"Sequence ID not monotonically increasing: "
                    f"sequence_id={sequence_id} <= prev={prev_sequence_id}"
                )

        # Check prev_checksum matches previous event's checksum
        if i > 0:
            if stored_prev_checksum != prev_checksum:
                errors.append(
                    f"Chain broken at sequence_id={sequence_id}: "
                    f"prev_checksum='{stored_prev_checksum}' doesn't match "
                    f"previous event's checksum='{prev_checksum}'"
                )

        # Verify the event's own checksum
        computed_checksum = _compute_checksum_from_row(event, sequence_id, stored_prev_checksum)
        if stored_checksum != computed_checksum:
            errors.append(
                f"Invalid checksum at sequence_id={sequence_id}: "
                f"stored='{stored_checksum}', computed='{computed_checksum}'"
            )

        # Update for next iteration
        prev_sequence_id = sequence_id
        prev_checksum = stored_checksum

    is_valid = len(errors) == 0
    return is_valid, errors
