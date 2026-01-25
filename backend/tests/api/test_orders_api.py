# backend/tests/api/test_orders_api.py
"""Tests for Orders API endpoints."""


class TestClosePosition:
    """Tests for POST /api/orders/close endpoint."""

    async def test_close_position_market_order_success(self, client):
        """POST /api/orders/close with market order returns success."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "order_id" in data
        assert data["order_id"].startswith("ORD-")
        assert "AAPL" in data["message"]

    async def test_close_position_with_integer_quantity(self, client):
        """POST /api/orders/close accepts integer quantity."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "MSFT",
                "quantity": 50,
                "order_type": "market",
                "time_in_force": "DAY",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "order_id" in data

    async def test_close_position_limit_order_requires_price(self, client):
        """POST /api/orders/close with limit order requires limit_price."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "limit",
                "time_in_force": "GTC",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_close_position_limit_order_with_price(self, client):
        """POST /api/orders/close with limit order and price succeeds."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "GOOGL",
                "quantity": 10,
                "order_type": "limit",
                "time_in_force": "GTC",
                "limit_price": 150.50,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "order_id" in data

    async def test_close_position_requires_symbol(self, client):
        """POST /api/orders/close requires symbol field."""
        response = await client.post(
            "/api/orders/close",
            json={
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_close_position_requires_quantity(self, client):
        """POST /api/orders/close requires quantity field."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_close_position_validates_order_type(self, client):
        """POST /api/orders/close validates order_type enum."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "invalid",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 422  # Validation error

    async def test_close_position_validates_time_in_force(self, client):
        """POST /api/orders/close validates time_in_force enum."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "INVALID",
            },
        )

        assert response.status_code == 422  # Validation error


class TestClosePositionStateCheck:
    """Tests for state checking in POST /api/orders/close endpoint."""

    async def test_close_allowed_when_running(self, client):
        """POST /api/orders/close succeeds when state is RUNNING."""
        # Default state is RUNNING
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_close_allowed_when_paused(self, client):
        """POST /api/orders/close succeeds when state is PAUSED."""
        # Pause trading first
        await client.post("/api/risk/pause")

        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    async def test_close_blocked_when_halted(self, client):
        """POST /api/orders/close returns 400 when state is HALTED."""
        # Halt trading first
        await client.post("/api/risk/halt", json={"reason": "Emergency stop"})

        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert "halted" in data["detail"].lower()


class TestClosePositionResponseFormat:
    """Tests for response format of POST /api/orders/close endpoint."""

    async def test_response_contains_order_id(self, client):
        """Response contains order_id with ORD- prefix."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "order_id" in data
        assert data["order_id"].startswith("ORD-")
        assert len(data["order_id"]) > 4  # ORD- plus some ID

    async def test_response_contains_message(self, client):
        """Response contains descriptive message."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "TSLA",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "TSLA" in data["message"]
        assert "close" in data["message"].lower()

    async def test_response_contains_success_flag(self, client):
        """Response contains success boolean flag."""
        response = await client.post(
            "/api/orders/close",
            json={
                "symbol": "AAPL",
                "quantity": "all",
                "order_type": "market",
                "time_in_force": "IOC",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "success" in data
        assert isinstance(data["success"], bool)
        assert data["success"] is True
