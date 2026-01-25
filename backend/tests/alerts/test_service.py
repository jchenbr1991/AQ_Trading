"""Tests for AlertService entry point.

TDD tests for the AlertService class which is the main entry point
for emitting alerts in the system.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.alerts.factory import create_alert
from src.alerts.models import RECOVERY_TYPES, AlertType, Severity


class TestAlertServiceInit:
    """Tests for AlertService initialization."""

    def test_init_stores_repository_and_hub(self):
        """AlertService stores repository and hub references."""
        from src.alerts.service import AlertService

        mock_repo = MagicMock()
        mock_hub = MagicMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        assert service._repo is mock_repo
        assert service._hub is mock_hub


class TestAlertServiceEmit:
    """Tests for AlertService.emit() method."""

    @pytest.mark.asyncio
    async def test_emit_validates_alert_first(self):
        """emit() calls validate_alert before persisting."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        with patch("src.alerts.service.validate_alert") as mock_validate:
            await service.emit(alert)

        mock_validate.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_emit_persists_alert(self):
        """emit() calls repository.persist_alert."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        alert_id = uuid4()
        mock_repo.persist_alert = AsyncMock(return_value=(True, alert_id))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        await service.emit(alert)

        mock_repo.persist_alert.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_emit_returns_true_on_success(self):
        """emit() returns True when alert processed successfully."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        result = await service.emit(alert)

        assert result is True

    @pytest.mark.asyncio
    async def test_emit_enqueues_new_alert(self):
        """emit() enqueues alert when is_new=True."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(return_value=True)

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        await service.emit(alert)

        mock_hub.enqueue.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_emit_does_not_enqueue_duplicate_alert(self):
        """emit() does not enqueue when is_new=False (duplicate)."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(False, uuid4()))  # is_new=False
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(return_value=True)

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        result = await service.emit(alert)

        assert result is True
        mock_hub.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_enqueues_recovery_type_even_if_duplicate(self):
        """emit() enqueues recovery type alerts even when is_new=False."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(False, uuid4()))  # is_new=False
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(return_value=True)

        service = AlertService(repository=mock_repo, hub=mock_hub)

        # COMPONENT_RECOVERED is a recovery type
        alert = create_alert(
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV3,
            summary="Component recovered",
        )

        # Verify COMPONENT_RECOVERED is indeed a recovery type
        assert AlertType.COMPONENT_RECOVERED in RECOVERY_TYPES

        await service.emit(alert)

        # Should enqueue even though is_new=False
        mock_hub.enqueue.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_emit_with_send_false_does_not_enqueue(self):
        """emit(send=False) persists but does not enqueue."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        result = await service.emit(alert, send=False)

        assert result is True
        mock_repo.persist_alert.assert_called_once()
        mock_hub.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_logs_debug_on_deduplication(self, caplog):
        """emit() logs debug message when alert is deduplicated."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(False, uuid4()))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        with caplog.at_level(logging.DEBUG, logger="src.alerts.service"):
            await service.emit(alert)

        assert "deduplicated" in caplog.text.lower()


class TestAlertServiceEmitExceptions:
    """Tests for exception handling in AlertService.emit()."""

    @pytest.mark.asyncio
    async def test_emit_returns_false_on_validation_error(self, caplog):
        """emit() returns False when validation fails."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        with patch(
            "src.alerts.service.validate_alert",
            side_effect=ValueError("Invalid timestamp"),
        ):
            with caplog.at_level(logging.ERROR, logger="src.alerts.service"):
                result = await service.emit(alert)

        assert result is False
        assert "error" in caplog.text.lower()
        mock_repo.persist_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_emit_returns_false_on_repository_error(self, caplog):
        """emit() returns False when repository raises exception."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(side_effect=Exception("DB error"))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        with caplog.at_level(logging.ERROR, logger="src.alerts.service"):
            result = await service.emit(alert)

        assert result is False
        assert "error" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_emit_returns_false_on_hub_error(self, caplog):
        """emit() returns False when hub raises exception."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(side_effect=Exception("Queue error"))

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        with caplog.at_level(logging.ERROR, logger="src.alerts.service"):
            result = await service.emit(alert)

        assert result is False
        assert "error" in caplog.text.lower()

    @pytest.mark.asyncio
    async def test_emit_never_raises_exceptions(self):
        """emit() never raises exceptions, always returns bool."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(side_effect=RuntimeError("Unexpected"))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test alert",
        )

        # Should not raise
        result = await service.emit(alert)
        assert result is False


class TestAlertServiceDeduplicationLogic:
    """Tests for deduplication decision logic."""

    @pytest.mark.asyncio
    async def test_is_new_true_enqueues(self):
        """When is_new=True, alert is enqueued."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(True, uuid4()))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(return_value=True)

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )

        await service.emit(alert)

        mock_hub.enqueue.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_new_false_non_recovery_does_not_enqueue(self):
        """When is_new=False and not recovery type, alert is not enqueued."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(False, uuid4()))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        # Non-recovery type
        alert = create_alert(
            type=AlertType.ORDER_REJECTED,
            severity=Severity.SEV2,
            summary="Test",
        )
        assert alert.type not in RECOVERY_TYPES

        await service.emit(alert)

        mock_hub.enqueue.assert_not_called()

    @pytest.mark.asyncio
    async def test_is_new_false_recovery_type_enqueues(self):
        """When is_new=False but recovery type, alert is enqueued."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        mock_repo.persist_alert = AsyncMock(return_value=(False, uuid4()))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(return_value=True)

        service = AlertService(repository=mock_repo, hub=mock_hub)

        # Recovery type
        alert = create_alert(
            type=AlertType.COMPONENT_RECOVERED,
            severity=Severity.SEV3,
            summary="Recovered",
        )
        assert alert.type in RECOVERY_TYPES

        await service.emit(alert)

        mock_hub.enqueue.assert_called_once()


class TestAlertServiceIntegration:
    """Integration-style tests for AlertService behavior."""

    @pytest.mark.asyncio
    async def test_full_emit_flow_new_alert(self):
        """Full flow: validate -> persist -> enqueue for new alert."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        alert_id = uuid4()
        mock_repo.persist_alert = AsyncMock(return_value=(True, alert_id))
        mock_hub = AsyncMock()
        mock_hub.enqueue = AsyncMock(return_value=True)

        service = AlertService(repository=mock_repo, hub=mock_hub)

        alert = create_alert(
            type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Kill switch activated",
            account_id="ACC001",
        )

        result = await service.emit(alert)

        assert result is True
        mock_repo.persist_alert.assert_called_once_with(alert)
        mock_hub.enqueue.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_full_emit_flow_persist_only(self):
        """Full flow with send=False: validate -> persist (no enqueue)."""
        from src.alerts.service import AlertService

        mock_repo = AsyncMock()
        alert_id = uuid4()
        mock_repo.persist_alert = AsyncMock(return_value=(True, alert_id))
        mock_hub = AsyncMock()

        service = AlertService(repository=mock_repo, hub=mock_hub)

        # ALERT_DELIVERY_FAILED should be emitted with send=False
        alert = create_alert(
            type=AlertType.ALERT_DELIVERY_FAILED,
            severity=Severity.SEV1,
            summary="Delivery failed",
        )

        result = await service.emit(alert, send=False)

        assert result is True
        mock_repo.persist_alert.assert_called_once_with(alert)
        mock_hub.enqueue.assert_not_called()
