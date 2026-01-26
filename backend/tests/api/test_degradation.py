# backend/tests/api/test_degradation.py
"""Tests for Degradation API endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from src.degradation.models import (
    ActionType,
    RecoveryStage,
    SystemMode,
)
from src.degradation.trading_gate import PermissionResult
from src.main import app


@pytest_asyncio.fixture
async def degradation_client():
    """HTTP client for degradation API tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestGetStatus:
    """Tests for GET /api/degradation/status endpoint."""

    @pytest.mark.asyncio
    async def test_get_status_service_not_initialized(self, degradation_client):
        """GET /api/degradation/status returns 503 when service not initialized."""
        with patch("src.api.degradation.get_system_state", return_value=None):
            response = await degradation_client.get("/api/degradation/status")

        assert response.status_code == 503
        assert response.json()["detail"] == "Degradation service not initialized"

    @pytest.mark.asyncio
    async def test_get_status_normal_mode(self, degradation_client):
        """GET /api/degradation/status returns status for normal mode."""
        mock_state = MagicMock()
        mock_state.mode = SystemMode.NORMAL
        mock_state.stage = None
        mock_state.is_force_override = False

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.get("/api/degradation/status")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "normal"
        assert data["stage"] is None
        assert data["is_override"] is False

    @pytest.mark.asyncio
    async def test_get_status_recovering_mode(self, degradation_client):
        """GET /api/degradation/status returns status with recovery stage."""
        mock_state = MagicMock()
        mock_state.mode = SystemMode.RECOVERING
        mock_state.stage = RecoveryStage.VERIFY_RISK
        mock_state.is_force_override = False

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.get("/api/degradation/status")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "recovering"
        assert data["stage"] == "verify_risk"
        assert data["is_override"] is False

    @pytest.mark.asyncio
    async def test_get_status_with_force_override(self, degradation_client):
        """GET /api/degradation/status returns is_override=True when override active."""
        mock_state = MagicMock()
        mock_state.mode = SystemMode.HALT
        mock_state.stage = None
        mock_state.is_force_override = True

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.get("/api/degradation/status")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "halt"
        assert data["is_override"] is True

    @pytest.mark.asyncio
    async def test_get_status_safe_mode_disconnected(self, degradation_client):
        """GET /api/degradation/status returns status for safe_mode_disconnected."""
        mock_state = MagicMock()
        mock_state.mode = SystemMode.SAFE_MODE_DISCONNECTED
        mock_state.stage = None
        mock_state.is_force_override = False

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.get("/api/degradation/status")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "safe_mode_disconnected"


class TestForceOverride:
    """Tests for POST /api/degradation/force endpoint."""

    @pytest.mark.asyncio
    async def test_force_override_service_not_initialized(self, degradation_client):
        """POST /api/degradation/force returns 503 when service not initialized."""
        with patch("src.api.degradation.get_system_state", return_value=None):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "halt",
                    "ttl_seconds": 300,
                    "operator_id": "admin-1",
                    "reason": "Emergency intervention",
                },
            )

        assert response.status_code == 503
        assert response.json()["detail"] == "Degradation service not initialized"

    @pytest.mark.asyncio
    async def test_force_override_success(self, degradation_client):
        """POST /api/degradation/force successfully forces mode."""
        mock_state = MagicMock()
        mock_state.force_mode = AsyncMock()
        mock_state.mode = SystemMode.HALT

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "halt",
                    "ttl_seconds": 300,
                    "operator_id": "admin-1",
                    "reason": "Emergency intervention",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "halt"
        assert data["ttl_seconds"] == 300
        assert data["operator_id"] == "admin-1"

        mock_state.force_mode.assert_called_once_with(
            mode=SystemMode.HALT,
            ttl_seconds=300,
            operator_id="admin-1",
            reason="Emergency intervention",
        )

    @pytest.mark.asyncio
    async def test_force_override_invalid_mode(self, degradation_client):
        """POST /api/degradation/force returns 422 for invalid mode."""
        mock_state = MagicMock()
        mock_state.force_mode = AsyncMock()

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "invalid_mode",
                    "ttl_seconds": 300,
                    "operator_id": "admin-1",
                    "reason": "Test",
                },
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_force_override_missing_fields(self, degradation_client):
        """POST /api/degradation/force returns 422 for missing required fields."""
        mock_state = MagicMock()
        mock_state.force_mode = AsyncMock()

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "halt",
                    # Missing ttl_seconds, operator_id, reason
                },
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_force_override_negative_ttl(self, degradation_client):
        """POST /api/degradation/force returns 422 for negative TTL."""
        mock_state = MagicMock()
        mock_state.force_mode = AsyncMock()

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "halt",
                    "ttl_seconds": -100,
                    "operator_id": "admin-1",
                    "reason": "Test",
                },
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_force_override_empty_operator_id(self, degradation_client):
        """POST /api/degradation/force returns 422 for empty operator_id."""
        mock_state = MagicMock()
        mock_state.force_mode = AsyncMock()

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "halt",
                    "ttl_seconds": 300,
                    "operator_id": "",
                    "reason": "Test",
                },
            )

        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_force_override_to_normal_mode(self, degradation_client):
        """POST /api/degradation/force can force to normal mode."""
        mock_state = MagicMock()
        mock_state.force_mode = AsyncMock()
        mock_state.mode = SystemMode.NORMAL

        with patch("src.api.degradation.get_system_state", return_value=mock_state):
            response = await degradation_client.post(
                "/api/degradation/force",
                json={
                    "mode": "normal",
                    "ttl_seconds": 60,
                    "operator_id": "admin-1",
                    "reason": "Resume normal operations",
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["mode"] == "normal"


class TestGetPermissions:
    """Tests for GET /api/degradation/permissions endpoint."""

    @pytest.mark.asyncio
    async def test_get_permissions_service_not_initialized(self, degradation_client):
        """GET /api/degradation/permissions returns 503 when service not initialized."""
        with patch("src.api.degradation.get_trading_gate", return_value=None):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 503
        assert response.json()["detail"] == "Degradation service not initialized"

    @pytest.mark.asyncio
    async def test_get_permissions_normal_mode(self, degradation_client):
        """GET /api/degradation/permissions returns all allowed in normal mode."""
        mock_gate = MagicMock()
        mock_gate.mode = SystemMode.NORMAL
        mock_gate.stage = None

        # In normal mode, all actions are allowed
        def mock_check_permission(action):
            return PermissionResult(allowed=True, restricted=False, warning=None, local_only=False)

        mock_gate.check_permission = mock_check_permission

        with patch("src.api.degradation.get_trading_gate", return_value=mock_gate):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "normal"
        assert data["stage"] is None
        assert data["permissions"]["open"]["allowed"] is True
        assert data["permissions"]["send"]["allowed"] is True
        assert data["permissions"]["amend"]["allowed"] is True
        assert data["permissions"]["cancel"]["allowed"] is True
        assert data["permissions"]["reduce_only"]["allowed"] is True
        assert data["permissions"]["query"]["allowed"] is True

    @pytest.mark.asyncio
    async def test_get_permissions_halt_mode(self, degradation_client):
        """GET /api/degradation/permissions returns only query allowed in halt mode."""
        mock_gate = MagicMock()
        mock_gate.mode = SystemMode.HALT
        mock_gate.stage = None

        def mock_check_permission(action):
            # In halt mode, only query is allowed
            if action == ActionType.QUERY:
                return PermissionResult(
                    allowed=True, restricted=False, warning=None, local_only=False
                )
            return PermissionResult(allowed=False, restricted=False, warning=None, local_only=False)

        mock_gate.check_permission = mock_check_permission

        with patch("src.api.degradation.get_trading_gate", return_value=mock_gate):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "halt"
        assert data["permissions"]["open"]["allowed"] is False
        assert data["permissions"]["send"]["allowed"] is False
        assert data["permissions"]["amend"]["allowed"] is False
        assert data["permissions"]["cancel"]["allowed"] is False
        assert data["permissions"]["reduce_only"]["allowed"] is False
        assert data["permissions"]["query"]["allowed"] is True

    @pytest.mark.asyncio
    async def test_get_permissions_safe_mode_with_warning(self, degradation_client):
        """GET /api/degradation/permissions returns warnings in safe mode."""
        mock_gate = MagicMock()
        mock_gate.mode = SystemMode.SAFE_MODE
        mock_gate.stage = None

        def mock_check_permission(action):
            # In safe mode, cancel has a warning
            if action == ActionType.CANCEL:
                return PermissionResult(
                    allowed=True,
                    restricted=False,
                    warning="Cancel is best-effort; broker connection may be unstable",
                    local_only=False,
                )
            elif action in (ActionType.REDUCE_ONLY, ActionType.QUERY):
                return PermissionResult(
                    allowed=True, restricted=False, warning=None, local_only=False
                )
            return PermissionResult(allowed=False, restricted=False, warning=None, local_only=False)

        mock_gate.check_permission = mock_check_permission

        with patch("src.api.degradation.get_trading_gate", return_value=mock_gate):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "safe_mode"
        assert data["permissions"]["cancel"]["allowed"] is True
        assert "best-effort" in data["permissions"]["cancel"]["warning"]

    @pytest.mark.asyncio
    async def test_get_permissions_recovering_mode(self, degradation_client):
        """GET /api/degradation/permissions returns recovery stage permissions."""
        mock_gate = MagicMock()
        mock_gate.mode = SystemMode.RECOVERING
        mock_gate.stage = RecoveryStage.VERIFY_RISK

        def mock_check_permission(action):
            # In VERIFY_RISK stage, query and cancel are allowed
            if action in (ActionType.QUERY, ActionType.CANCEL):
                return PermissionResult(
                    allowed=True, restricted=False, warning=None, local_only=False
                )
            return PermissionResult(allowed=False, restricted=False, warning=None, local_only=False)

        mock_gate.check_permission = mock_check_permission

        with patch("src.api.degradation.get_trading_gate", return_value=mock_gate):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "recovering"
        assert data["stage"] == "verify_risk"
        assert data["permissions"]["query"]["allowed"] is True
        assert data["permissions"]["cancel"]["allowed"] is True
        assert data["permissions"]["open"]["allowed"] is False

    @pytest.mark.asyncio
    async def test_get_permissions_with_restricted_flag(self, degradation_client):
        """GET /api/degradation/permissions returns restricted flag in degraded mode."""
        mock_gate = MagicMock()
        mock_gate.mode = SystemMode.DEGRADED
        mock_gate.stage = None

        def mock_check_permission(action):
            # In degraded mode, open is restricted
            if action == ActionType.OPEN:
                return PermissionResult(
                    allowed=True, restricted=True, warning=None, local_only=False
                )
            return PermissionResult(allowed=True, restricted=False, warning=None, local_only=False)

        mock_gate.check_permission = mock_check_permission

        with patch("src.api.degradation.get_trading_gate", return_value=mock_gate):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "degraded"
        assert data["permissions"]["open"]["allowed"] is True
        assert data["permissions"]["open"]["restricted"] is True

    @pytest.mark.asyncio
    async def test_get_permissions_local_only_flag(self, degradation_client):
        """GET /api/degradation/permissions returns local_only flag when disconnected."""
        mock_gate = MagicMock()
        mock_gate.mode = SystemMode.SAFE_MODE_DISCONNECTED
        mock_gate.stage = None

        def mock_check_permission(action):
            # In disconnected mode, query is local only
            if action == ActionType.QUERY:
                return PermissionResult(
                    allowed=True, restricted=False, warning=None, local_only=True
                )
            return PermissionResult(allowed=False, restricted=False, warning=None, local_only=False)

        mock_gate.check_permission = mock_check_permission

        with patch("src.api.degradation.get_trading_gate", return_value=mock_gate):
            response = await degradation_client.get("/api/degradation/permissions")

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "safe_mode_disconnected"
        assert data["permissions"]["query"]["allowed"] is True
        assert data["permissions"]["query"]["local_only"] is True
