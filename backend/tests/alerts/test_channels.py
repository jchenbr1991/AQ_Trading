"""Tests for notification channels.

TDD: These tests are written FIRST before the implementation.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from src.alerts.models import AlertEvent, AlertType, Severity

# Test fixtures for SMTP authentication (not real credentials)
TEST_SMTP_USER = "user"
TEST_SMTP_CRED = "test-cred-1234"


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""

    def test_delivery_result_success_only(self):
        """DeliveryResult with only success field."""
        from src.alerts.channels import DeliveryResult

        result = DeliveryResult(success=True)
        assert result.success is True
        assert result.response_code is None
        assert result.error_message is None

    def test_delivery_result_all_fields(self):
        """DeliveryResult with all fields populated."""
        from src.alerts.channels import DeliveryResult

        result = DeliveryResult(
            success=False,
            response_code=500,
            error_message="Internal server error",
        )
        assert result.success is False
        assert result.response_code == 500
        assert result.error_message == "Internal server error"

    def test_delivery_result_success_with_code(self):
        """DeliveryResult success with response code."""
        from src.alerts.channels import DeliveryResult

        result = DeliveryResult(success=True, response_code=250)
        assert result.success is True
        assert result.response_code == 250
        assert result.error_message is None


class TestNotificationChannel:
    """Tests for NotificationChannel abstract base class."""

    def test_notification_channel_is_abstract(self):
        """NotificationChannel should be abstract and not instantiable."""
        from src.alerts.channels import NotificationChannel

        with pytest.raises(TypeError):
            NotificationChannel()

    def test_notification_channel_requires_send_method(self):
        """Subclasses must implement send method."""
        from src.alerts.channels import NotificationChannel

        class IncompleteChannel(NotificationChannel):
            pass

        with pytest.raises(TypeError):
            IncompleteChannel()


def _create_test_alert(
    alert_type: AlertType = AlertType.ORDER_REJECTED,
    severity: Severity = Severity.SEV1,
    summary: str = "Test alert",
) -> AlertEvent:
    """Create a test alert event."""
    return AlertEvent(
        alert_id=uuid4(),
        type=alert_type,
        severity=severity,
        event_timestamp=datetime(2026, 1, 25, 12, 0, 0, tzinfo=timezone.utc),
        fingerprint="test:fingerprint",
        entity_ref=None,
        summary=summary,
        details={"key": "value"},
    )


class TestEmailChannel:
    """Tests for EmailChannel notification channel."""

    def test_email_channel_initialization(self):
        """EmailChannel should initialize with SMTP settings."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
            username=TEST_SMTP_USER,
            password=TEST_SMTP_CRED,
            use_tls=True,
        )

        assert channel.smtp_host == "smtp.example.com"
        assert channel.smtp_port == 587
        assert channel.sender == "alerts@example.com"
        assert channel.username == TEST_SMTP_USER
        assert channel.password == TEST_SMTP_CRED
        assert channel.use_tls is True

    def test_email_channel_default_tls(self):
        """EmailChannel should default to use_tls=True."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
        )

        assert channel.use_tls is True

    def test_email_channel_optional_credentials(self):
        """EmailChannel should allow None for username/password."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="localhost",
            smtp_port=25,
            sender="alerts@localhost",
            username=None,
            password=None,
            use_tls=False,
        )

        assert channel.username is None
        assert channel.password is None

    @pytest.mark.asyncio
    async def test_email_channel_send_success(self):
        """EmailChannel.send should return success on successful delivery."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
            username=TEST_SMTP_USER,
            password=TEST_SMTP_CRED,
        )

        alert = _create_test_alert()

        with patch("src.alerts.channels.aiosmtplib.send") as mock_send:
            mock_send.return_value = ({}, "OK")

            result = await channel.send(alert, "recipient@example.com")

            assert result.success is True
            assert result.response_code == 250

            # Verify send was called
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["hostname"] == "smtp.example.com"
            assert call_kwargs["port"] == 587
            assert call_kwargs["username"] == TEST_SMTP_USER
            assert call_kwargs["password"] == TEST_SMTP_CRED
            assert call_kwargs["start_tls"] is True

    @pytest.mark.asyncio
    async def test_email_channel_send_subject_format_sev1(self):
        """Email subject should be '[SEV1] {summary}' for critical alerts."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
        )

        alert = _create_test_alert(severity=Severity.SEV1, summary="Critical issue")

        with patch("src.alerts.channels.aiosmtplib.send") as mock_send:
            mock_send.return_value = ({}, "OK")

            await channel.send(alert, "recipient@example.com")

            # Get the message argument
            call_args = mock_send.call_args
            message = call_args.kwargs["message"]
            assert "[SEV1] Critical issue" in message["Subject"]

    @pytest.mark.asyncio
    async def test_email_channel_send_subject_format_sev2(self):
        """Email subject should be '[SEV2] {summary}' for warning alerts."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
        )

        alert = _create_test_alert(severity=Severity.SEV2, summary="Warning issue")

        with patch("src.alerts.channels.aiosmtplib.send") as mock_send:
            mock_send.return_value = ({}, "OK")

            await channel.send(alert, "recipient@example.com")

            call_args = mock_send.call_args
            message = call_args.kwargs["message"]
            assert "[SEV2] Warning issue" in message["Subject"]

    @pytest.mark.asyncio
    async def test_email_channel_send_subject_format_sev3(self):
        """Email subject should be '[SEV3] {summary}' for info alerts."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
        )

        alert = _create_test_alert(severity=Severity.SEV3, summary="Info message")

        with patch("src.alerts.channels.aiosmtplib.send") as mock_send:
            mock_send.return_value = ({}, "OK")

            await channel.send(alert, "recipient@example.com")

            call_args = mock_send.call_args
            message = call_args.kwargs["message"]
            assert "[SEV3] Info message" in message["Subject"]

    @pytest.mark.asyncio
    async def test_email_channel_send_smtp_error(self):
        """EmailChannel.send should return failure on SMTP error."""
        import aiosmtplib
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="smtp.example.com",
            smtp_port=587,
            sender="alerts@example.com",
        )

        alert = _create_test_alert()

        with patch("src.alerts.channels.aiosmtplib.send") as mock_send:
            mock_send.side_effect = aiosmtplib.SMTPException("Connection refused")

            result = await channel.send(alert, "recipient@example.com")

            assert result.success is False
            assert result.error_message == "Connection refused"

    @pytest.mark.asyncio
    async def test_email_channel_send_without_auth(self):
        """EmailChannel.send should work without authentication."""
        from src.alerts.channels import EmailChannel

        channel = EmailChannel(
            smtp_host="localhost",
            smtp_port=25,
            sender="alerts@localhost",
            username=None,
            password=None,
            use_tls=False,
        )

        alert = _create_test_alert()

        with patch("src.alerts.channels.aiosmtplib.send") as mock_send:
            mock_send.return_value = ({}, "OK")

            result = await channel.send(alert, "recipient@localhost")

            assert result.success is True
            call_kwargs = mock_send.call_args.kwargs
            assert call_kwargs["username"] is None
            assert call_kwargs["password"] is None
            assert call_kwargs["start_tls"] is False


class TestWebhookChannel:
    """Tests for WebhookChannel notification channel."""

    def test_webhook_channel_initialization_default(self):
        """WebhookChannel should initialize with default timeout."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel()
        assert channel.timeout_seconds == 10.0

    def test_webhook_channel_initialization_custom_timeout(self):
        """WebhookChannel should accept custom timeout."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel(timeout_seconds=30.0)
        assert channel.timeout_seconds == 30.0

    @pytest.mark.asyncio
    async def test_webhook_channel_send_success(self):
        """WebhookChannel.send should return success on 2xx response."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel()
        alert = _create_test_alert()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await channel.send(alert, "https://hooks.slack.com/test")

            assert result.success is True
            assert result.response_code == 200

    @pytest.mark.asyncio
    async def test_webhook_channel_send_payload_format_sev1(self):
        """WebhookChannel.send should post correct Slack-compatible payload for SEV1."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel()
        alert = _create_test_alert(
            alert_type=AlertType.KILL_SWITCH_ACTIVATED,
            severity=Severity.SEV1,
            summary="Kill switch activated!",
        )

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            await channel.send(alert, "https://hooks.slack.com/test")

            # Verify the payload
            call_args = mock_client.post.call_args
            url = call_args.args[0]
            json_payload = call_args.kwargs["json"]

            assert url == "https://hooks.slack.com/test"
            # Should have fire emoji for SEV1
            assert "[SEV1]" in json_payload["text"]
            assert "Kill switch activated!" in json_payload["text"]

            # Check attachments
            attachments = json_payload["attachments"]
            assert len(attachments) == 1
            assert attachments[0]["color"] == "#ff0000"  # Red for SEV1

            fields = attachments[0]["fields"]
            type_field = next(f for f in fields if f["title"] == "Type")
            time_field = next(f for f in fields if f["title"] == "Time")

            assert type_field["value"] == "kill_switch_activated"
            assert type_field["short"] is True
            assert "2026-01-25" in time_field["value"]
            assert time_field["short"] is True

    @pytest.mark.asyncio
    async def test_webhook_channel_send_payload_format_sev2(self):
        """WebhookChannel.send should use yellow color for SEV2."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel()
        alert = _create_test_alert(severity=Severity.SEV2, summary="Warning")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            await channel.send(alert, "https://hooks.slack.com/test")

            call_args = mock_client.post.call_args
            json_payload = call_args.kwargs["json"]

            assert json_payload["attachments"][0]["color"] == "#ffcc00"

    @pytest.mark.asyncio
    async def test_webhook_channel_send_payload_format_sev3(self):
        """WebhookChannel.send should use yellow color for SEV3 (non-critical)."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel()
        alert = _create_test_alert(severity=Severity.SEV3, summary="Info")

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            await channel.send(alert, "https://hooks.slack.com/test")

            call_args = mock_client.post.call_args
            json_payload = call_args.kwargs["json"]

            # SEV3 should also use yellow (non-critical)
            assert json_payload["attachments"][0]["color"] == "#ffcc00"

    @pytest.mark.asyncio
    async def test_webhook_channel_send_timeout_error(self):
        """WebhookChannel.send should handle timeout gracefully."""
        import httpx
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel(timeout_seconds=1.0)
        alert = _create_test_alert()

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await channel.send(alert, "https://hooks.slack.com/test")

            assert result.success is False
            assert "timed out" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_webhook_channel_send_http_error(self):
        """WebhookChannel.send should handle HTTP errors gracefully."""
        import httpx
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel()
        alert = _create_test_alert()

        mock_response = AsyncMock()
        mock_response.status_code = 500

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.HTTPStatusError(
                "Server error",
                request=MagicMock(),
                response=mock_response,
            )
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            result = await channel.send(alert, "https://hooks.slack.com/test")

            assert result.success is False
            assert result.response_code == 500

    @pytest.mark.asyncio
    async def test_webhook_channel_uses_timeout(self):
        """WebhookChannel.send should use configured timeout."""
        from src.alerts.channels import WebhookChannel

        channel = WebhookChannel(timeout_seconds=15.0)
        alert = _create_test_alert()

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        with patch("src.alerts.channels.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client_class.return_value = mock_client

            await channel.send(alert, "https://hooks.slack.com/test")

            # Verify timeout was passed to client
            mock_client_class.assert_called_once()
            call_kwargs = mock_client_class.call_args.kwargs
            assert call_kwargs["timeout"] == 15.0
