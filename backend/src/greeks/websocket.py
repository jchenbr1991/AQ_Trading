"""WebSocket manager for real-time Greeks updates.

Manages WebSocket connections and broadcasts Greeks updates to connected clients.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class GreeksWebSocketManager:
    """Manages WebSocket connections for Greeks updates.

    Supports multiple clients per account, handles disconnections gracefully,
    and provides broadcast functionality for real-time updates.

    Usage:
        manager = GreeksWebSocketManager()

        # In WebSocket endpoint
        await manager.connect(account_id, websocket)
        try:
            while True:
                await websocket.receive_text()  # Keep alive
        except WebSocketDisconnect:
            await manager.disconnect(account_id, websocket)

        # In monitor loop
        await manager.broadcast_greeks_update(account_id, greeks_data)
    """

    def __init__(self):
        """Initialize the WebSocket manager."""
        # account_id -> list of WebSocket connections
        self._connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, account_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection.

        Args:
            account_id: Account identifier
            websocket: WebSocket connection
        """
        async with self._lock:
            if account_id not in self._connections:
                self._connections[account_id] = []
            self._connections[account_id].append(websocket)
            logger.info(f"WebSocket connected for account {account_id}")

    async def disconnect(self, account_id: str, websocket: WebSocket) -> None:
        """Remove a WebSocket connection.

        Args:
            account_id: Account identifier
            websocket: WebSocket connection to remove
        """
        async with self._lock:
            if account_id in self._connections:
                try:
                    self._connections[account_id].remove(websocket)
                except ValueError:
                    pass  # Already removed

                # Clean up empty lists
                if not self._connections[account_id]:
                    del self._connections[account_id]

                logger.info(f"WebSocket disconnected for account {account_id}")

    async def broadcast_greeks_update(
        self,
        account_id: str,
        data: dict[str, Any],
    ) -> None:
        """Broadcast Greeks update to all connected clients for an account.

        Args:
            account_id: Account identifier
            data: Greeks data to broadcast
        """
        if account_id not in self._connections:
            return

        message = {
            "type": "greeks_update",
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }

        # Get connections snapshot to avoid modification during iteration
        async with self._lock:
            connections = list(self._connections.get(account_id, []))

        # Broadcast to all connections
        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Error sending to WebSocket: {e}")
                disconnected.append(websocket)

        # Clean up disconnected clients
        for websocket in disconnected:
            await self.disconnect(account_id, websocket)

    async def broadcast_alert(
        self,
        account_id: str,
        alert: dict[str, Any],
    ) -> None:
        """Broadcast a new alert to all connected clients.

        Args:
            account_id: Account identifier
            alert: Alert data to broadcast
        """
        if account_id not in self._connections:
            return

        message = {
            "type": "greeks_alert",
            "account_id": account_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "alert": alert,
        }

        async with self._lock:
            connections = list(self._connections.get(account_id, []))

        disconnected = []
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            await self.disconnect(account_id, websocket)

    def get_connection_count(self, account_id: str) -> int:
        """Get number of connected clients for an account.

        Args:
            account_id: Account identifier

        Returns:
            Number of connected WebSocket clients
        """
        return len(self._connections.get(account_id, []))


# Global instance for use across the application
greeks_ws_manager = GreeksWebSocketManager()
