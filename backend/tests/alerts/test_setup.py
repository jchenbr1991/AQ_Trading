"""Tests for alert system setup module.

TDD tests for init_alert_service and get_alert_service functions.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGetAlertService:
    """Tests for get_alert_service function."""

    def test_get_alert_service_returns_none_before_init(self):
        """get_alert_service returns None before initialization."""
        # Reset the global state
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        from src.alerts.setup import get_alert_service

        result = get_alert_service()
        assert result is None

    def test_get_alert_service_returns_service_after_init(self):
        """get_alert_service returns the service after initialization."""
        import src.alerts.setup
        from src.alerts.service import AlertService

        mock_service = MagicMock(spec=AlertService)
        src.alerts.setup._alert_service = mock_service

        from src.alerts.setup import get_alert_service

        result = get_alert_service()
        assert result is mock_service

        # Clean up
        src.alerts.setup._alert_service = None


class TestInitAlertService:
    """Tests for init_alert_service function."""

    @pytest.mark.asyncio
    async def test_init_creates_alert_repository(self):
        """init_alert_service creates AlertRepository with db_session."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository") as mock_repo_class,
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService") as mock_service_class,
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            mock_repo_class.assert_called_once_with(mock_session)

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_creates_webhook_channel_always(self):
        """init_alert_service always creates webhook channel."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.WebhookChannel") as mock_webhook_class,
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, {}, clear=True),  # No SMTP config
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            mock_webhook_class.assert_called_once()

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_creates_email_channel_when_configured(self):
        """init_alert_service creates email channel when SMTP_HOST is set."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        # Test credentials for SMTP configuration
        test_secret = "test_smtp_secret"  # noqa: S105
        smtp_env = {
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "465",
            "SMTP_SENDER": "alerts@example.com",
            "SMTP_USERNAME": "test_user",
            "SMTP_PASSWORD": test_secret,
        }

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.EmailChannel") as mock_email_class,
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, smtp_env, clear=True),
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            # Verify EmailChannel was called with correct SMTP config
            call_kwargs = mock_email_class.call_args[1]
            assert call_kwargs["smtp_host"] == "smtp.example.com"
            assert call_kwargs["smtp_port"] == 465
            assert call_kwargs["sender"] == "alerts@example.com"
            assert call_kwargs["username"] == "test_user"
            assert "password" in call_kwargs

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_does_not_create_email_channel_without_smtp_host(self):
        """init_alert_service skips email channel when SMTP_HOST not set."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.EmailChannel") as mock_email_class,
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, {}, clear=True),  # No SMTP_HOST
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            mock_email_class.assert_not_called()

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_creates_hub_with_channels(self):
        """init_alert_service creates NotificationHub with configured channels."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository") as mock_repo_class,
            patch("src.alerts.setup.WebhookChannel") as mock_webhook_class,
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo
            mock_webhook = MagicMock()
            mock_webhook_class.return_value = mock_webhook
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            mock_hub_class.assert_called_once_with(
                repository=mock_repo, channels={"webhook": mock_webhook}
            )

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_starts_hub_with_two_workers(self):
        """init_alert_service starts hub with 2 workers."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            mock_hub.start.assert_called_once_with(num_workers=2)

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_creates_alert_service(self):
        """init_alert_service creates AlertService with repo and hub."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository") as mock_repo_class,
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService") as mock_service_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_repo = MagicMock()
            mock_repo_class.return_value = mock_repo
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            mock_service_class.assert_called_once_with(repository=mock_repo, hub=mock_hub)

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_returns_alert_service(self):
        """init_alert_service returns the created AlertService."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService") as mock_service_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            from src.alerts.setup import init_alert_service

            result = await init_alert_service(mock_session)

            assert result is mock_service

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_sets_global_alert_service(self):
        """init_alert_service sets the global _alert_service."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService") as mock_service_class,
            patch.dict(os.environ, {}, clear=True),
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub
            mock_service = MagicMock()
            mock_service_class.return_value = mock_service

            from src.alerts.setup import get_alert_service, init_alert_service

            await init_alert_service(mock_session)

            assert get_alert_service() is mock_service

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_uses_default_smtp_port(self):
        """init_alert_service uses default port 587 when SMTP_PORT not set."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        smtp_env = {
            "SMTP_HOST": "smtp.example.com",
            # No SMTP_PORT - should default to 587
        }

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.EmailChannel") as mock_email_class,
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, smtp_env, clear=True),
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            call_kwargs = mock_email_class.call_args[1]
            assert call_kwargs["smtp_port"] == 587

        # Clean up
        src.alerts.setup._alert_service = None

    @pytest.mark.asyncio
    async def test_init_uses_default_sender(self):
        """init_alert_service uses default sender when SMTP_SENDER not set."""
        import src.alerts.setup

        src.alerts.setup._alert_service = None

        mock_session = MagicMock()

        smtp_env = {
            "SMTP_HOST": "smtp.example.com",
            # No SMTP_SENDER - should default to alerts@localhost
        }

        with (
            patch("src.alerts.setup.AlertRepository"),
            patch("src.alerts.setup.EmailChannel") as mock_email_class,
            patch("src.alerts.setup.WebhookChannel"),
            patch("src.alerts.setup.NotificationHub") as mock_hub_class,
            patch("src.alerts.setup.AlertService"),
            patch.dict(os.environ, smtp_env, clear=True),
        ):
            mock_hub = AsyncMock()
            mock_hub.start = AsyncMock()
            mock_hub_class.return_value = mock_hub

            from src.alerts.setup import init_alert_service

            await init_alert_service(mock_session)

            call_kwargs = mock_email_class.call_args[1]
            assert call_kwargs["sender"] == "alerts@localhost"

        # Clean up
        src.alerts.setup._alert_service = None
