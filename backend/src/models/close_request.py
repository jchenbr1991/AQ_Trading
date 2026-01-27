"""CloseRequest model for tracking position close operations."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class CloseRequestStatus(str, Enum):
    """Status of a close request."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    RETRYABLE = "retryable"
    FAILED = "failed"


class CloseRequest(Base):
    """Tracks a request to close a position.

    Stores order parameters for retry consistency - side/symbol/asset_type
    are captured at creation and not re-derived from position.
    """

    __tablename__ = "close_requests"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(100))
    status: Mapped[CloseRequestStatus] = mapped_column(
        String(20), default=CloseRequestStatus.PENDING
    )

    # Order parameters (stored for retry consistency)
    symbol: Mapped[str] = mapped_column(String(50))
    side: Mapped[str] = mapped_column(String(10))  # "buy" or "sell"
    asset_type: Mapped[str] = mapped_column(String(20))

    # Quantities
    target_qty: Mapped[int] = mapped_column(Integer)
    filled_qty: Mapped[int] = mapped_column(Integer, default=0)
    # NOTE: remaining_qty is computed in PostgreSQL as generated column

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __init__(self, **kwargs):
        """Initialize CloseRequest with defaults for optional fields."""
        # Apply defaults for fields not provided
        kwargs.setdefault("filled_qty", 0)
        kwargs.setdefault("retry_count", 0)
        kwargs.setdefault("max_retries", 3)
        super().__init__(**kwargs)

    @property
    def remaining_qty(self) -> int:
        """Calculate remaining quantity to close."""
        return self.target_qty - self.filled_qty
