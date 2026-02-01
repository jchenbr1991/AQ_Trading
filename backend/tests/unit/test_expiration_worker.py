"""Tests for ExpirationWorker.

Tests cover:
- Worker initialization with various configurations
- Running expiration checks with and without AlertService
- Severity determination based on days to expiry
- Graceful degradation when AlertService is not available
"""

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.derivatives.expiration_manager import ExpirationAlert
from src.models.derivative_contract import ContractType, PutCall
from src.workers.expiration_worker import (
    DEFAULT_WARNING_DAYS,
    ExpirationWorker,
)


class TestExpirationWorkerInit:
    """Tests for ExpirationWorker initialization."""

    def test_default_warning_days(self):
        """Should default to 5 warning days per SC-011."""
        mock_factory = MagicMock()
        worker = ExpirationWorker(session_factory=mock_factory)
        assert worker.warning_days == DEFAULT_WARNING_DAYS
        assert worker.warning_days == 5

    def test_custom_warning_days(self):
        """Should accept custom warning days."""
        mock_factory = MagicMock()
        worker = ExpirationWorker(session_factory=mock_factory, warning_days=10)
        assert worker.warning_days == 10

    def test_negative_warning_days_raises(self):
        """Should raise ValueError for negative warning days."""
        mock_factory = MagicMock()
        with pytest.raises(ValueError, match="warning_days must be non-negative"):
            ExpirationWorker(session_factory=mock_factory, warning_days=-1)

    def test_zero_warning_days_allowed(self):
        """Should allow zero warning days (check same-day expirations only)."""
        mock_factory = MagicMock()
        worker = ExpirationWorker(session_factory=mock_factory, warning_days=0)
        assert worker.warning_days == 0

    def test_accepts_none_alert_service(self):
        """Should accept None for alert_service (graceful degradation)."""
        mock_factory = MagicMock()
        worker = ExpirationWorker(session_factory=mock_factory, alert_service=None)
        assert worker._alert_service is None

    def test_accepts_alert_service(self):
        """Should accept AlertService instance."""
        mock_factory = MagicMock()
        mock_alert_service = MagicMock()
        worker = ExpirationWorker(
            session_factory=mock_factory,
            alert_service=mock_alert_service,
        )
        assert worker._alert_service is mock_alert_service


class TestRunCheck:
    """Tests for run_check method."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock async session."""
        return AsyncMock()

    @pytest.fixture
    def mock_session_factory(self, mock_session):
        """Create a mock session factory returning async context manager."""
        factory = MagicMock()
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = mock_session
        context_manager.__aexit__.return_value = None
        factory.return_value = context_manager
        return factory

    @pytest.fixture
    def sample_alerts(self):
        """Create sample expiration alerts for testing."""
        return [
            ExpirationAlert(
                symbol="AAPL240119C00150000",
                underlying="AAPL",
                expiry=date.today() + timedelta(days=3),
                days_to_expiry=3,
                contract_type=ContractType.OPTION,
                put_call=PutCall.CALL,
                strike=Decimal("150.00"),
            ),
            ExpirationAlert(
                symbol="ESH24",
                underlying="ES",
                expiry=date.today() + timedelta(days=1),
                days_to_expiry=1,
                contract_type=ContractType.FUTURE,
                put_call=None,
                strike=None,
            ),
        ]

    @pytest.mark.asyncio
    async def test_returns_alerts_from_manager(
        self, mock_session_factory, mock_session, sample_alerts
    ):
        """Should return alerts from ExpirationManager."""
        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = sample_alerts
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(session_factory=mock_session_factory)
            alerts = await worker.run_check()

            assert len(alerts) == 2
            assert alerts[0].symbol == "AAPL240119C00150000"
            assert alerts[1].symbol == "ESH24"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_expirations(self, mock_session_factory, mock_session):
        """Should return empty list when no positions are expiring."""
        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = []
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(session_factory=mock_session_factory)
            alerts = await worker.run_check()

            assert alerts == []

    @pytest.mark.asyncio
    async def test_creates_manager_with_warning_days(self, mock_session_factory, mock_session):
        """Should pass warning_days to ExpirationManager."""
        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = []
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                warning_days=10,
            )
            await worker.run_check()

            MockManager.assert_called_once_with(
                session=mock_session,
                warning_days=10,
            )

    @pytest.mark.asyncio
    async def test_handles_direct_session(self, mock_session, sample_alerts):
        """Should handle session factory returning direct session (not context manager)."""
        # Session without __aenter__ (direct callable)
        mock_session_no_cm = AsyncMock(spec=[])  # No __aenter__
        mock_factory = MagicMock(return_value=mock_session_no_cm)

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = sample_alerts
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(session_factory=mock_factory)
            alerts = await worker.run_check()

            assert len(alerts) == 2


class TestAlertEmission:
    """Tests for alert emission functionality."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        mock_session = AsyncMock()
        factory = MagicMock()
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = mock_session
        context_manager.__aexit__.return_value = None
        factory.return_value = context_manager
        return factory

    @pytest.fixture
    def mock_alert_service(self):
        """Create a mock AlertService."""
        service = AsyncMock()
        service.emit.return_value = True
        return service

    @pytest.mark.asyncio
    async def test_emits_alerts_when_service_configured(
        self, mock_session_factory, mock_alert_service
    ):
        """Should emit alerts via AlertService when configured."""
        alert = ExpirationAlert(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=3),
            days_to_expiry=3,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            mock_alert_service.emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_alert_contains_required_details(self, mock_session_factory, mock_alert_service):
        """Should include required details in emitted alert."""
        alert = ExpirationAlert(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=3),
            days_to_expiry=3,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            # Get the alert event that was passed to emit()
            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]

            # Check required fields
            assert "position_id" in alert_event.details
            assert "threshold_days" in alert_event.details
            assert alert_event.details["threshold_days"] == 5
            assert alert_event.details["days_to_expiry"] == 3

    @pytest.mark.asyncio
    async def test_logs_when_no_alert_service(self, mock_session_factory, caplog):
        """Should log warnings when no AlertService configured."""
        alert = ExpirationAlert(
            symbol="AAPL240119C00150000",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=3),
            days_to_expiry=3,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=None,
            )

            import logging

            with caplog.at_level(logging.INFO):
                await worker.run_check()

            # Should log the expiration warning
            assert "EXPIRATION WARNING" in caplog.text or "AAPL240119C00150000" in caplog.text


class TestSeverityDetermination:
    """Tests for severity determination based on days to expiry."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        mock_session = AsyncMock()
        factory = MagicMock()
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = mock_session
        context_manager.__aexit__.return_value = None
        factory.return_value = context_manager
        return factory

    @pytest.fixture
    def mock_alert_service(self):
        """Create a mock AlertService."""
        service = AsyncMock()
        service.emit.return_value = True
        return service

    @pytest.mark.asyncio
    async def test_sev1_for_0_days(self, mock_session_factory, mock_alert_service):
        """Should use SEV1 for same-day expiration."""
        alert = ExpirationAlert(
            symbol="AAPL_0D",
            underlying="AAPL",
            expiry=date.today(),
            days_to_expiry=0,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            from src.alerts.models import Severity

            assert alert_event.severity == Severity.SEV1

    @pytest.mark.asyncio
    async def test_sev1_for_1_day(self, mock_session_factory, mock_alert_service):
        """Should use SEV1 for 1 day to expiry."""
        alert = ExpirationAlert(
            symbol="AAPL_1D",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=1),
            days_to_expiry=1,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            from src.alerts.models import Severity

            assert alert_event.severity == Severity.SEV1

    @pytest.mark.asyncio
    async def test_sev2_for_2_days(self, mock_session_factory, mock_alert_service):
        """Should use SEV2 for 2 days to expiry."""
        alert = ExpirationAlert(
            symbol="AAPL_2D",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=2),
            days_to_expiry=2,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            from src.alerts.models import Severity

            assert alert_event.severity == Severity.SEV2

    @pytest.mark.asyncio
    async def test_sev2_for_3_days(self, mock_session_factory, mock_alert_service):
        """Should use SEV2 for 3 days to expiry."""
        alert = ExpirationAlert(
            symbol="AAPL_3D",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=3),
            days_to_expiry=3,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            from src.alerts.models import Severity

            assert alert_event.severity == Severity.SEV2

    @pytest.mark.asyncio
    async def test_sev3_for_4_plus_days(self, mock_session_factory, mock_alert_service):
        """Should use SEV3 for 4+ days to expiry."""
        alert = ExpirationAlert(
            symbol="AAPL_4D",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=4),
            days_to_expiry=4,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            from src.alerts.models import Severity

            assert alert_event.severity == Severity.SEV3

    @pytest.mark.asyncio
    async def test_sev3_for_5_days(self, mock_session_factory, mock_alert_service):
        """Should use SEV3 for exactly 5 days to expiry."""
        alert = ExpirationAlert(
            symbol="AAPL_5D",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=5),
            days_to_expiry=5,
            contract_type=ContractType.OPTION,
            put_call=PutCall.CALL,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            from src.alerts.models import Severity

            assert alert_event.severity == Severity.SEV3


class TestContractTypes:
    """Tests for different contract types."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        mock_session = AsyncMock()
        factory = MagicMock()
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = mock_session
        context_manager.__aexit__.return_value = None
        factory.return_value = context_manager
        return factory

    @pytest.fixture
    def mock_alert_service(self):
        """Create a mock AlertService."""
        service = AsyncMock()
        service.emit.return_value = True
        return service

    @pytest.mark.asyncio
    async def test_option_alert_includes_put_call(self, mock_session_factory, mock_alert_service):
        """Option alerts should include put/call designation."""
        alert = ExpirationAlert(
            symbol="AAPL240119P00150000",
            underlying="AAPL",
            expiry=date.today() + timedelta(days=3),
            days_to_expiry=3,
            contract_type=ContractType.OPTION,
            put_call=PutCall.PUT,
            strike=Decimal("150.00"),
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            assert "put" in alert_event.summary.lower()
            assert alert_event.details["put_call"] == "put"

    @pytest.mark.asyncio
    async def test_future_alert_has_null_put_call(self, mock_session_factory, mock_alert_service):
        """Future alerts should have null put_call in details."""
        alert = ExpirationAlert(
            symbol="ESH24",
            underlying="ES",
            expiry=date.today() + timedelta(days=3),
            days_to_expiry=3,
            contract_type=ContractType.FUTURE,
            put_call=None,
            strike=None,
        )

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = [alert]
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            await worker.run_check()

            call_args = mock_alert_service.emit.call_args
            alert_event = call_args[0][0]
            assert alert_event.details["put_call"] is None
            assert alert_event.details["strike"] is None


class TestErrorHandling:
    """Tests for error handling scenarios."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        mock_session = AsyncMock()
        factory = MagicMock()
        context_manager = AsyncMock()
        context_manager.__aenter__.return_value = mock_session
        context_manager.__aexit__.return_value = None
        factory.return_value = context_manager
        return factory

    @pytest.mark.asyncio
    async def test_raises_on_manager_error(self, mock_session_factory):
        """Should raise exception when ExpirationManager fails."""
        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.side_effect = RuntimeError("Database error")
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(session_factory=mock_session_factory)

            with pytest.raises(RuntimeError, match="Database error"):
                await worker.run_check()

    @pytest.mark.asyncio
    async def test_continues_on_alert_emit_failure(self, mock_session_factory):
        """Should continue processing when individual alert emission fails."""
        alerts = [
            ExpirationAlert(
                symbol="AAPL_1",
                underlying="AAPL",
                expiry=date.today() + timedelta(days=3),
                days_to_expiry=3,
                contract_type=ContractType.OPTION,
                put_call=PutCall.CALL,
                strike=Decimal("150.00"),
            ),
            ExpirationAlert(
                symbol="AAPL_2",
                underlying="AAPL",
                expiry=date.today() + timedelta(days=4),
                days_to_expiry=4,
                contract_type=ContractType.OPTION,
                put_call=PutCall.CALL,
                strike=Decimal("160.00"),
            ),
        ]

        mock_alert_service = AsyncMock()
        # First emit fails, second succeeds
        mock_alert_service.emit.side_effect = [
            Exception("Emit failed"),
            True,
        ]

        with patch("src.workers.expiration_worker.ExpirationManager") as MockManager:
            mock_manager_instance = AsyncMock()
            mock_manager_instance.check_expirations.return_value = alerts
            MockManager.return_value = mock_manager_instance

            worker = ExpirationWorker(
                session_factory=mock_session_factory,
                alert_service=mock_alert_service,
            )
            result = await worker.run_check()

            # Should still return all alerts despite emission failure
            assert len(result) == 2
            # Both emits were attempted
            assert mock_alert_service.emit.call_count == 2
