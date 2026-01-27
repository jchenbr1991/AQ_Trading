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
