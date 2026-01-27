"""Tests for OutboxEvent model."""


def test_outbox_event_status_enum():
    """OutboxEventStatus should have all required values."""
    from src.models.outbox import OutboxEventStatus

    expected = {"pending", "processing", "completed", "failed"}
    actual = {s.value for s in OutboxEventStatus}
    assert actual == expected


def test_outbox_event_model_fields():
    """OutboxEvent should have all required fields."""
    from src.models.outbox import OutboxEvent, OutboxEventStatus

    event = OutboxEvent(
        event_type="SUBMIT_CLOSE_ORDER",
        payload={"close_request_id": "abc123", "symbol": "AAPL"},
    )

    assert event.event_type == "SUBMIT_CLOSE_ORDER"
    assert event.payload["symbol"] == "AAPL"
    assert event.status == OutboxEventStatus.PENDING
    assert event.retry_count == 0
