import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


def _utc_now() -> datetime:
    """Return current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class AgentRole(str, Enum):
    RESEARCHER = "researcher"
    ANALYST = "analyst"
    RISK_CONTROLLER = "risk_controller"
    OPS = "ops"


class AgentResult(Base):
    __tablename__ = "agent_results"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Required fields
    role: Mapped[AgentRole] = mapped_column(String(30), nullable=False, index=True)
    task: Mapped[str] = mapped_column(String(500), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    # Result fields
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timing fields (timezone-aware to match migration's TIMESTAMP(timezone=True))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utc_now, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def complete(self, result: dict[str, Any] | None = None, error: str | None = None) -> None:
        """Mark the agent result as completed."""
        self.completed_at = _utc_now()
        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

        if error:
            self.error = error
            self.success = False
        else:
            self.result = result
            self.success = True
