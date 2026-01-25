# backend/tests/api/test_risk_api.py
"""Tests for Risk API endpoints."""


class TestGetState:
    """Tests for GET /api/risk/state endpoint."""

    async def test_get_state_returns_current_state(self, client):
        """GET /api/risk/state returns current trading state."""
        response = await client.get("/api/risk/state")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RUNNING"
        assert "since" in data
        assert data["changed_by"] == "system"
        assert data["can_resume"] is True

    async def test_get_state_after_pause(self, client):
        """GET /api/risk/state reflects state changes."""
        # Pause first
        await client.post("/api/risk/pause")

        response = await client.get("/api/risk/state")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "PAUSED"
        assert data["can_resume"] is True


class TestHalt:
    """Tests for POST /api/risk/halt endpoint."""

    async def test_halt_requires_reason(self, client):
        """POST /api/risk/halt requires reason in request body."""
        response = await client.post("/api/risk/halt", json={})

        assert response.status_code == 422  # Validation error

    async def test_halt_success(self, client):
        """POST /api/risk/halt halts trading with reason."""
        response = await client.post("/api/risk/halt", json={"reason": "Emergency stop requested"})

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "HALTED"

    async def test_halt_updates_state(self, client):
        """POST /api/risk/halt changes state to HALTED."""
        await client.post("/api/risk/halt", json={"reason": "Test halt"})

        response = await client.get("/api/risk/state")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "HALTED"
        assert data["reason"] == "Test halt"
        assert data["can_resume"] is False
        assert data["changed_by"] == "api"


class TestPause:
    """Tests for POST /api/risk/pause endpoint."""

    async def test_pause_success(self, client):
        """POST /api/risk/pause pauses trading."""
        response = await client.post("/api/risk/pause")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "PAUSED"

    async def test_pause_updates_state(self, client):
        """POST /api/risk/pause changes state to PAUSED."""
        await client.post("/api/risk/pause")

        response = await client.get("/api/risk/state")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "PAUSED"
        assert data["can_resume"] is True
        assert data["changed_by"] == "api"

    async def test_pause_with_optional_reason(self, client):
        """POST /api/risk/pause accepts optional reason."""
        response = await client.post("/api/risk/pause", json={"reason": "Lunch break"})

        assert response.status_code == 200

        state_response = await client.get("/api/risk/state")
        data = state_response.json()
        assert data["reason"] == "Lunch break"


class TestResume:
    """Tests for POST /api/risk/resume endpoint."""

    async def test_resume_from_paused(self, client):
        """POST /api/risk/resume resumes from PAUSED state."""
        # Pause first
        await client.post("/api/risk/pause")

        response = await client.post("/api/risk/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "RUNNING"

    async def test_resume_from_running(self, client):
        """POST /api/risk/resume from RUNNING state succeeds."""
        response = await client.post("/api/risk/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "RUNNING"

    async def test_resume_from_halted_without_enable(self, client):
        """POST /api/risk/resume from HALTED without enable returns 400."""
        # Halt first
        await client.post("/api/risk/halt", json={"reason": "Test halt"})

        response = await client.post("/api/risk/resume")

        assert response.status_code == 400
        data = response.json()
        assert "cannot resume" in data["detail"].lower()

    async def test_resume_from_halted_after_enable(self, client):
        """POST /api/risk/resume from HALTED after enable_resume succeeds."""
        # Halt
        await client.post("/api/risk/halt", json={"reason": "Test halt"})
        # Enable resume
        await client.post("/api/risk/enable-resume")

        response = await client.post("/api/risk/resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "RUNNING"


class TestEnableResume:
    """Tests for POST /api/risk/enable-resume endpoint."""

    async def test_enable_resume_on_halted(self, client):
        """POST /api/risk/enable-resume enables resume on HALTED state."""
        # Halt first
        await client.post("/api/risk/halt", json={"reason": "Test halt"})

        response = await client.post("/api/risk/enable-resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "HALTED"

        # Verify can_resume is now True
        state_response = await client.get("/api/risk/state")
        state_data = state_response.json()
        assert state_data["can_resume"] is True

    async def test_enable_resume_on_non_halted_is_noop(self, client):
        """POST /api/risk/enable-resume on non-HALTED state is a no-op."""
        # Pause first (not halt)
        await client.post("/api/risk/pause")

        response = await client.post("/api/risk/enable-resume")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["state"] == "PAUSED"


class TestStateIsolation:
    """Tests for state isolation between tests."""

    async def test_state_is_fresh_for_each_test(self, client):
        """Each test starts with a fresh RUNNING state."""
        response = await client.get("/api/risk/state")

        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "RUNNING"
