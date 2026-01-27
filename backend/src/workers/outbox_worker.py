"""Outbox worker for processing async events."""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.close_request import CloseRequest, CloseRequestStatus
from src.models.outbox import OutboxEvent, OutboxEventStatus
from src.models.position import Position, PositionStatus

logger = logging.getLogger(__name__)


class OrderManager(Protocol):
    """Protocol for order submission."""

    async def submit_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        order_type: str,
        limit_price: Decimal,
        close_request_id: str | None = None,
    ) -> Any: ...


class MarketData(Protocol):
    """Protocol for market data."""

    async def get_quote(self, symbol: str) -> Any: ...


class OutboxWorker:
    """Worker for processing outbox events."""

    MAX_RETRIES = 3
    QUOTE_TIMEOUT = 5.0

    def __init__(
        self,
        session: AsyncSession,
        order_manager: OrderManager,
        market_data: MarketData,
    ):
        self.session = session
        self.order_manager = order_manager
        self.market_data = market_data

    async def process_event(self, event: OutboxEvent) -> None:
        """Process a single outbox event."""
        try:
            if event.event_type == "SUBMIT_CLOSE_ORDER":
                await self._handle_submit_close_order(event.payload)

            # Mark completed
            event.status = OutboxEventStatus.COMPLETED
            event.processed_at = datetime.now(timezone.utc)
            await self.session.commit()

        except Exception as e:
            logger.exception(f"Outbox event {event.id} failed: {e}")
            event.retry_count += 1

            if event.retry_count >= self.MAX_RETRIES:
                event.status = OutboxEventStatus.FAILED
                await self._handle_failure(event, str(e))
            else:
                event.status = OutboxEventStatus.PENDING  # Reset for retry

            await self.session.commit()
            raise

    async def _handle_submit_close_order(self, payload: dict[str, Any]) -> None:
        """Submit close order to broker."""
        close_request_id = payload["close_request_id"]

        # Check if already processed (idempotent)
        result = await self.session.execute(
            select(CloseRequest).where(CloseRequest.id == UUID(close_request_id))
        )
        close_request = result.scalar_one_or_none()

        if not close_request or close_request.status != CloseRequestStatus.PENDING:
            logger.info(f"CloseRequest {close_request_id} already processed, skipping")
            return

        # Get quote for aggressive limit order
        try:
            quote = await asyncio.wait_for(
                self.market_data.get_quote(payload["symbol"]),
                timeout=self.QUOTE_TIMEOUT,
            )
        except TimeoutError as e:
            raise RuntimeError("Market data timeout, will retry") from e

        # Price sanity check
        if quote.bid <= 0 or quote.ask <= 0:
            raise RuntimeError(f"Invalid quote: bid={quote.bid}, ask={quote.ask}")

        # Calculate limit price
        spread_pct = (quote.ask - quote.bid) / quote.bid if quote.bid > 0 else float("inf")

        if spread_pct > 0.20:  # >20% spread
            logger.warning(f"Wide spread {spread_pct:.1%} for {payload['symbol']}")
            if hasattr(quote, "last") and quote.last > 0:
                multiplier = Decimal("0.90") if payload["side"] == "sell" else Decimal("1.10")
                limit_price = Decimal(str(quote.last)) * multiplier
            else:
                raise RuntimeError(f"Cannot price order: bad quote for {payload['symbol']}")
        elif payload["side"] == "sell":
            limit_price = Decimal(str(quote.bid)) * Decimal("0.95")
        else:
            limit_price = Decimal(str(quote.ask)) * Decimal("1.05")

        # Minimum price
        limit_price = max(limit_price, Decimal("0.01"))

        # Submit order
        order = await self.order_manager.submit_order(
            symbol=payload["symbol"],
            side=payload["side"],
            qty=payload["qty"],
            order_type="limit",
            limit_price=limit_price,
            close_request_id=close_request_id,
        )

        # Update close request
        if hasattr(order, "status") and order.status == "REJECTED":
            close_request.status = CloseRequestStatus.FAILED
            close_request.completed_at = datetime.now(timezone.utc)

            # Rollback position
            pos_result = await self.session.execute(
                select(Position).where(Position.id == close_request.position_id)
            )
            position = pos_result.scalar_one_or_none()
            if position:
                position.status = PositionStatus.CLOSE_FAILED
                position.active_close_request_id = None
        else:
            close_request.status = CloseRequestStatus.SUBMITTED
            close_request.submitted_at = datetime.now(timezone.utc)

    async def _handle_failure(self, event: OutboxEvent, error: str) -> None:
        """Handle permanent failure after max retries."""
        logger.error(f"Outbox event {event.id} failed permanently: {error}")

        # Update close request if applicable
        if event.event_type == "SUBMIT_CLOSE_ORDER":
            close_request_id = event.payload.get("close_request_id")
            if close_request_id:
                result = await self.session.execute(
                    select(CloseRequest).where(CloseRequest.id == UUID(close_request_id))
                )
                close_request = result.scalar_one_or_none()
                if close_request:
                    close_request.status = CloseRequestStatus.FAILED
                    close_request.completed_at = datetime.now(timezone.utc)

                    # Update position
                    pos_result = await self.session.execute(
                        select(Position).where(Position.id == close_request.position_id)
                    )
                    position = pos_result.scalar_one_or_none()
                    if position:
                        position.status = PositionStatus.CLOSE_FAILED
                        position.active_close_request_id = None
