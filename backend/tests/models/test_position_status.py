"""Tests for PositionStatus enum."""

from src.models.position import PositionStatus


def test_position_status_has_close_retryable():
    """PositionStatus should have CLOSE_RETRYABLE value."""
    assert PositionStatus.CLOSE_RETRYABLE == "close_retryable"


def test_position_status_has_close_failed():
    """PositionStatus should have CLOSE_FAILED value."""
    assert PositionStatus.CLOSE_FAILED == "close_failed"


def test_all_position_statuses():
    """PositionStatus should have all 5 values."""
    expected = {"open", "closing", "closed", "close_retryable", "close_failed"}
    actual = {s.value for s in PositionStatus}
    assert actual == expected


def test_position_has_active_close_request_id():
    """Position should have active_close_request_id field."""
    from src.models.position import Position

    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        quantity=100,
    )
    assert hasattr(pos, "active_close_request_id")
    assert pos.active_close_request_id is None


def test_position_has_closed_at():
    """Position should have closed_at field."""
    from src.models.position import Position

    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        quantity=100,
    )
    assert hasattr(pos, "closed_at")
    assert pos.closed_at is None


# --- Additional coverage tests ---


def test_position_status_is_str_enum():
    """PositionStatus should be usable as string via .value and equality."""
    # Can compare directly to string (str mixin)
    assert PositionStatus.CLOSE_RETRYABLE == "close_retryable"
    # Get value via .value property
    assert PositionStatus.CLOSE_RETRYABLE.value == "close_retryable"
    # Can be compared to strings
    status = PositionStatus.CLOSING
    assert status == "closing"


def test_position_active_close_request_id_can_be_set():
    """Position.active_close_request_id should accept UUID values."""
    from uuid import uuid4

    from src.models.position import Position

    test_uuid = uuid4()
    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        quantity=100,
        active_close_request_id=test_uuid,
    )
    assert pos.active_close_request_id == test_uuid


def test_position_closed_at_can_be_set():
    """Position.closed_at should accept datetime values."""
    from datetime import datetime

    from src.models.position import Position

    now = datetime.utcnow()
    pos = Position(
        account_id="ACC001",
        symbol="AAPL",
        quantity=100,
        closed_at=now,
    )
    assert pos.closed_at == now
