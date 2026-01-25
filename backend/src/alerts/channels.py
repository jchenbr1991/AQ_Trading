"""Notification channel implementations for the alert system.

This module provides:
- DeliveryResult: Result dataclass for notification delivery
- NotificationChannel: Abstract base class for notification channels
- EmailChannel: SMTP-based email notification channel
- WebhookChannel: HTTP webhook notification channel (Slack-compatible)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from email.message import EmailMessage

import aiosmtplib
import httpx

from src.alerts.models import AlertEvent, Severity


@dataclass
class DeliveryResult:
    """Result of a notification delivery attempt.

    Attributes:
        success: Whether the delivery succeeded
        response_code: HTTP status code or SMTP response code (if applicable)
        error_message: Error message if delivery failed
    """

    success: bool
    response_code: int | None = None
    error_message: str | None = None


class NotificationChannel(ABC):
    """Abstract base class for notification channels.

    All notification channels must implement the send() method.
    """

    @abstractmethod
    async def send(self, alert: AlertEvent, destination: str) -> DeliveryResult:
        """Send a notification for the given alert.

        Args:
            alert: The alert event to notify about
            destination: Channel-specific destination (email address, webhook URL, etc.)

        Returns:
            DeliveryResult indicating success or failure
        """
        pass


class EmailChannel(NotificationChannel):
    """SMTP-based email notification channel.

    Sends email notifications with subject format "[SEV{n}] {summary}".
    """

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        sender: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
    ):
        """Initialize the email channel.

        Args:
            smtp_host: SMTP server hostname
            smtp_port: SMTP server port
            sender: Sender email address
            username: SMTP authentication username (optional)
            password: SMTP authentication password (optional)
            use_tls: Whether to use STARTTLS (default: True)
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.username = username
        self.password = password
        self.use_tls = use_tls

    async def send(self, alert: AlertEvent, destination: str) -> DeliveryResult:
        """Send an email notification.

        Args:
            alert: The alert event to notify about
            destination: Recipient email address

        Returns:
            DeliveryResult with success=True and response_code=250 on success,
            or success=False with error_message on failure
        """
        # Format subject with severity
        severity_name = f"SEV{alert.severity.value}"
        subject = f"[{severity_name}] {alert.summary}"

        # Build email message
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = destination

        # Build body with alert details
        body_lines = [
            f"Alert: {alert.summary}",
            f"Type: {alert.type.value}",
            f"Severity: {severity_name}",
            f"Time: {alert.event_timestamp.isoformat()}",
            f"Alert ID: {alert.alert_id}",
        ]

        if alert.entity_ref:
            if alert.entity_ref.account_id:
                body_lines.append(f"Account: {alert.entity_ref.account_id}")
            if alert.entity_ref.symbol:
                body_lines.append(f"Symbol: {alert.entity_ref.symbol}")
            if alert.entity_ref.strategy_id:
                body_lines.append(f"Strategy: {alert.entity_ref.strategy_id}")
            if alert.entity_ref.run_id:
                body_lines.append(f"Run ID: {alert.entity_ref.run_id}")

        if alert.details:
            body_lines.append("\nDetails:")
            for key, value in alert.details.items():
                body_lines.append(f"  {key}: {value}")

        message.set_content("\n".join(body_lines))

        try:
            await aiosmtplib.send(
                message=message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                username=self.username,
                password=self.password,
                start_tls=self.use_tls,
            )
            return DeliveryResult(success=True, response_code=250)
        except aiosmtplib.SMTPException as e:
            return DeliveryResult(success=False, error_message=str(e))


class WebhookChannel(NotificationChannel):
    """HTTP webhook notification channel.

    Sends Slack-compatible JSON payloads via POST request.
    """

    # Emoji mapping for severity levels
    SEVERITY_EMOJI = {
        Severity.SEV1: ":fire:",
        Severity.SEV2: ":warning:",
        Severity.SEV3: ":information_source:",
    }

    def __init__(self, timeout_seconds: float = 10.0):
        """Initialize the webhook channel.

        Args:
            timeout_seconds: HTTP request timeout (default: 10.0 seconds)
        """
        self.timeout_seconds = timeout_seconds

    async def send(self, alert: AlertEvent, destination: str) -> DeliveryResult:
        """Send a webhook notification.

        Args:
            alert: The alert event to notify about
            destination: Webhook URL

        Returns:
            DeliveryResult with success=True and HTTP status code on success,
            or success=False with error details on failure
        """
        severity_name = f"SEV{alert.severity.value}"
        emoji = self.SEVERITY_EMOJI.get(alert.severity, "")

        # Build Slack-compatible payload
        payload = {
            "text": f"{emoji} [{severity_name}] {alert.summary}",
            "attachments": [
                {
                    "color": "#ff0000" if alert.severity == Severity.SEV1 else "#ffcc00",
                    "fields": [
                        {
                            "title": "Type",
                            "value": alert.type.value,
                            "short": True,
                        },
                        {
                            "title": "Time",
                            "value": alert.event_timestamp.isoformat(),
                            "short": True,
                        },
                    ],
                }
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(destination, json=payload)
                response.raise_for_status()
                return DeliveryResult(success=True, response_code=response.status_code)
        except httpx.TimeoutException:
            return DeliveryResult(
                success=False,
                error_message="Request timed out",
            )
        except httpx.HTTPStatusError as e:
            return DeliveryResult(
                success=False,
                response_code=e.response.status_code,
                error_message=str(e),
            )
        except httpx.RequestError as e:
            return DeliveryResult(
                success=False,
                error_message=str(e),
            )
