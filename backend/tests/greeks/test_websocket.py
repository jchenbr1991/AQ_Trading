"""Tests for Greeks WebSocket manager."""

from unittest.mock import AsyncMock

import pytest
from src.greeks.websocket import GreeksWebSocketManager


class TestGreeksWebSocketManager:
    """Tests for GreeksWebSocketManager."""

    @pytest.mark.asyncio
    async def test_connect_adds_client(self):
        manager = GreeksWebSocketManager()
        mock_ws = AsyncMock()

        await manager.connect("acc123", mock_ws)

        assert "acc123" in manager._connections
        assert mock_ws in manager._connections["acc123"]

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self):
        manager = GreeksWebSocketManager()
        mock_ws = AsyncMock()

        await manager.connect("acc123", mock_ws)
        await manager.disconnect("acc123", mock_ws)

        assert mock_ws not in manager._connections.get("acc123", [])

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all_account_clients(self):
        manager = GreeksWebSocketManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect("acc123", mock_ws1)
        await manager.connect("acc123", mock_ws2)

        await manager.broadcast_greeks_update("acc123", {"test": "data"})

        mock_ws1.send_json.assert_called_once()
        mock_ws2.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_handles_disconnected_client(self):
        manager = GreeksWebSocketManager()
        mock_ws = AsyncMock()
        mock_ws.send_json.side_effect = Exception("Connection closed")

        await manager.connect("acc123", mock_ws)

        # Should not raise
        await manager.broadcast_greeks_update("acc123", {"test": "data"})
