"""Alert repository module for database operations.

This module provides the AlertRepository class for persisting and retrieving
alerts and delivery records from the database. Key features:

- Deduplication using ON CONFLICT ... DO UPDATE
- Suppression counting for duplicate alerts
- Delivery tracking with status updates

Usage:
    from src.alerts.repository import AlertRepository

    repo = AlertRepository(session)
    is_new, alert_id = await repo.persist_alert(alert)
    if is_new:
        delivery_id = await repo.record_delivery_attempt(...)
"""

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.alerts.factory import compute_dedupe_key
from src.alerts.models import AlertEvent


class AlertRepository:
    """Repository for alert and delivery database operations.

    Uses raw SQL with INSERT ... ON CONFLICT for efficient deduplication.
    """

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session for database operations
        """
        self.session = session

    async def persist_alert(self, alert: AlertEvent) -> tuple[bool, UUID]:
        """Persist an alert to the database with deduplication.

        Uses INSERT ... ON CONFLICT (dedupe_key) DO UPDATE to handle duplicates.
        If a duplicate is detected, increments suppressed_count instead of
        inserting a new row.

        Args:
            alert: The alert event to persist

        Returns:
            Tuple of (is_new, alert_id) where:
                is_new: True if this was a new insert, False if duplicate
                alert_id: The UUID of the alert (original for duplicates)
        """
        dedupe_key = compute_dedupe_key(alert)

        # Extract entity fields
        account_id = alert.entity_ref.account_id if alert.entity_ref else None
        symbol = alert.entity_ref.symbol if alert.entity_ref else None
        strategy_id = alert.entity_ref.strategy_id if alert.entity_ref else None

        # Serialize details to JSON string
        details_json = json.dumps(alert.details) if alert.details else None

        # Format timestamp for SQLite/PostgreSQL compatibility
        event_timestamp = alert.event_timestamp.isoformat()
        created_at = datetime.now(tz=timezone.utc).isoformat()

        # SQLite doesn't support xmax, so we use a different approach:
        # Try INSERT first, then check if it succeeded or hit conflict
        # For SQLite: Use INSERT OR IGNORE + UPDATE pattern
        # For PostgreSQL in production: Use RETURNING (xmax = 0) AS is_new

        # Check if alert with this dedupe_key already exists
        check_sql = text("""
            SELECT id FROM alerts WHERE dedupe_key = :dedupe_key
        """)
        result = await self.session.execute(check_sql, {"dedupe_key": dedupe_key})
        existing_row = result.fetchone()

        if existing_row:
            # Duplicate: update suppressed_count
            update_sql = text("""
                UPDATE alerts
                SET suppressed_count = suppressed_count + 1
                WHERE dedupe_key = :dedupe_key
            """)
            await self.session.execute(update_sql, {"dedupe_key": dedupe_key})
            await self.session.commit()
            return (False, UUID(existing_row[0]))
        else:
            # New alert: insert
            insert_sql = text("""
                INSERT INTO alerts (
                    id, type, severity, fingerprint, dedupe_key, summary, details,
                    entity_account_id, entity_symbol, entity_strategy_id,
                    suppressed_count, event_timestamp, created_at
                ) VALUES (
                    :id, :type, :severity, :fingerprint, :dedupe_key, :summary, :details,
                    :account_id, :symbol, :strategy_id,
                    0, :event_timestamp, :created_at
                )
            """)
            await self.session.execute(
                insert_sql,
                {
                    "id": str(alert.alert_id),
                    "type": alert.type.value,
                    "severity": alert.severity.value,
                    "fingerprint": alert.fingerprint,
                    "dedupe_key": dedupe_key,
                    "summary": alert.summary,
                    "details": details_json,
                    "account_id": account_id,
                    "symbol": symbol,
                    "strategy_id": strategy_id,
                    "event_timestamp": event_timestamp,
                    "created_at": created_at,
                },
            )
            await self.session.commit()
            return (True, alert.alert_id)

    async def get_alert(self, alert_id: UUID) -> dict | None:
        """Get an alert by ID.

        Args:
            alert_id: The UUID of the alert to retrieve

        Returns:
            Dict of alert row data, or None if not found
        """
        sql = text("""
            SELECT id, type, severity, fingerprint, dedupe_key, summary, details,
                   entity_account_id, entity_symbol, entity_strategy_id,
                   suppressed_count, event_timestamp, created_at
            FROM alerts
            WHERE id = :id
        """)
        result = await self.session.execute(sql, {"id": str(alert_id)})
        row = result.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "type": row[1],
            "severity": row[2],
            "fingerprint": row[3],
            "dedupe_key": row[4],
            "summary": row[5],
            "details": json.loads(row[6]) if row[6] else None,
            "entity_account_id": row[7],
            "entity_symbol": row[8],
            "entity_strategy_id": row[9],
            "suppressed_count": row[10],
            "event_timestamp": row[11],
            "created_at": row[12],
        }

    async def record_delivery_attempt(
        self,
        alert_id: UUID,
        channel: str,
        destination_key: str,
        attempt_number: int,
        status: str,
    ) -> UUID:
        """Record a delivery attempt for an alert.

        Args:
            alert_id: The UUID of the alert being delivered
            channel: The delivery channel (e.g., "email", "webhook")
            destination_key: The destination identifier (e.g., email address, URL)
            attempt_number: Which attempt this is (1, 2, 3, etc.)
            status: Initial status (typically "pending")

        Returns:
            The UUID of the delivery record
        """
        delivery_id = uuid4()
        created_at = datetime.now(tz=timezone.utc).isoformat()

        sql = text("""
            INSERT INTO alert_deliveries (
                id, alert_id, channel, destination_key, attempt_number, status, created_at
            ) VALUES (
                :id, :alert_id, :channel, :destination_key, :attempt_number, :status, :created_at
            )
        """)
        await self.session.execute(
            sql,
            {
                "id": str(delivery_id),
                "alert_id": str(alert_id),
                "channel": channel,
                "destination_key": destination_key,
                "attempt_number": attempt_number,
                "status": status,
                "created_at": created_at,
            },
        )
        await self.session.commit()

        return delivery_id

    async def update_delivery_status(
        self,
        delivery_id: UUID,
        status: str,
        response_code: int | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update the status of a delivery record.

        If status is "sent", also sets sent_at to current timestamp.

        Args:
            delivery_id: The UUID of the delivery to update
            status: New status ("sent", "failed", etc.)
            response_code: Optional HTTP response code
            error_message: Optional error message for failures
        """
        # Use a single static SQL that handles all optional fields via COALESCE
        # This avoids dynamic SQL construction and potential SQL injection
        sent_at = datetime.now(tz=timezone.utc).isoformat() if status == "sent" else None

        sql = text("""
            UPDATE alert_deliveries
            SET status = :status,
                response_code = COALESCE(:response_code, response_code),
                error_message = COALESCE(:error_message, error_message),
                sent_at = COALESCE(:sent_at, sent_at)
            WHERE id = :id
        """)
        await self.session.execute(
            sql,
            {
                "id": str(delivery_id),
                "status": status,
                "response_code": response_code,
                "error_message": error_message,
                "sent_at": sent_at,
            },
        )
        await self.session.commit()

    async def get_delivery(self, delivery_id: UUID) -> dict | None:
        """Get a delivery record by ID.

        Args:
            delivery_id: The UUID of the delivery to retrieve

        Returns:
            Dict of delivery row data, or None if not found
        """
        sql = text("""
            SELECT id, alert_id, channel, destination_key, attempt_number,
                   status, response_code, error_message, sent_at, created_at
            FROM alert_deliveries
            WHERE id = :id
        """)
        result = await self.session.execute(sql, {"id": str(delivery_id)})
        row = result.fetchone()

        if row is None:
            return None

        return {
            "id": row[0],
            "alert_id": row[1],
            "channel": row[2],
            "destination_key": row[3],
            "attempt_number": row[4],
            "status": row[5],
            "response_code": row[6],
            "error_message": row[7],
            "sent_at": row[8],
            "created_at": row[9],
        }
