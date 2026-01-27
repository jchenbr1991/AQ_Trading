"""Tests for CloseRequest model."""

from uuid import uuid4


def test_close_request_status_enum():
    """CloseRequestStatus should have all required values."""
    from src.models.close_request import CloseRequestStatus

    expected = {"pending", "submitted", "completed", "retryable", "failed"}
    actual = {s.value for s in CloseRequestStatus}
    assert actual == expected


def test_close_request_model_fields():
    """CloseRequest should have all required fields."""
    from src.models.close_request import CloseRequest, CloseRequestStatus

    cr = CloseRequest(
        id=uuid4(),
        position_id=1,
        idempotency_key="test-key",
        status=CloseRequestStatus.PENDING,
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
    )

    assert cr.position_id == 1
    assert cr.idempotency_key == "test-key"
    assert cr.status == CloseRequestStatus.PENDING
    assert cr.symbol == "AAPL"
    assert cr.side == "sell"
    assert cr.asset_type == "option"
    assert cr.target_qty == 100
    assert cr.filled_qty == 0
    assert cr.retry_count == 0
    assert cr.max_retries == 3


def test_close_request_remaining_qty():
    """remaining_qty should be target_qty - filled_qty."""
    from src.models.close_request import CloseRequest, CloseRequestStatus

    cr = CloseRequest(
        id=uuid4(),
        position_id=1,
        idempotency_key="test-key",
        status=CloseRequestStatus.PENDING,
        symbol="AAPL",
        side="sell",
        asset_type="option",
        target_qty=100,
        filled_qty=30,
    )

    assert cr.remaining_qty == 70
