"""OutboxEvent model for reliable async event processing."""

from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class OutboxEventStatus(str, Enum):
    """Status of an outbox event."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutboxEvent(Base):
    """Event in the outbox for reliable async processing.

    Uses the Outbox Pattern to ensure exactly-once delivery of events
    even when the system crashes between database commit and external call.
    """

    __tablename__ = "outbox_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[OutboxEventStatus] = mapped_column(String(20), default=OutboxEventStatus.PENDING)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    def __init__(self, **kwargs):
        """Initialize OutboxEvent with defaults for optional fields."""
        # Apply defaults for fields not provided
        kwargs.setdefault("status", OutboxEventStatus.PENDING)
        kwargs.setdefault("retry_count", 0)
        super().__init__(**kwargs)
