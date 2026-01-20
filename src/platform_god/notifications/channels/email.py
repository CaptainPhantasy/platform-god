"""
Email notification channel.

Delivers notifications via email with template support.
This is a template implementation that can be extended with
actual email delivery service integration.
"""

import smtplib
import threading
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from typing import Any

from pydantic import BaseModel

from platform_god.notifications.channels.base import BaseChannel
from platform_god.notifications.models import DeliveryResult


class EmailChannelConfig(BaseModel):
    """Configuration for email channel."""

    # Base settings
    enabled: bool = True
    timeout_seconds: int = 30
    max_retries: int = 3
    rate_limit_per_minute: int | None = None

    # SMTP settings
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    smtp_username: str | None = None
    smtp_password: str | None = None

    # Email settings
    from_address: str = "notifications@platformgod.local"
    from_name: str = "Platform God"
    to_addresses: list[str] = []
    cc_addresses: list[str] = []
    bcc_addresses: list[str] = []

    # Template settings
    subject_template: str = "{{title}}"
    body_template: str = "{{message}}"
    use_html: bool = False
    html_template: str = "<html><body><h1>{{title}}</h1><p>{{message}}</p></body></html>"


class EmailChannel(BaseChannel):
    """
    Notification delivery via email.

    Features:
    - SMTP delivery with TLS support
    - Authentication
    - Multiple recipients (to, cc, bcc)
    - Plain text and HTML support
    - Thread-safe delivery
    - Connection pooling

    Note: This is a template implementation. For production use,
    consider using dedicated email services like SendGrid, AWS SES,
    or Mailgun for better reliability and deliverability.
    """

    channel_type = "email"

    def __init__(self, config: EmailChannelConfig):
        """
        Initialize email channel.

        Args:
            config: Email channel configuration
        """
        from platform_god.notifications.channels.base import ChannelConfig

        base_config = ChannelConfig(
            enabled=config.enabled,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
        super().__init__(base_config)
        self.email_config: EmailChannelConfig = config
        self._connection_lock = threading.Lock()
        self._connection: smtplib.SMTP | None = None

    def validate_config(self) -> bool:
        """Validate email configuration."""
        if not self.email_config.smtp_host:
            return False

        if not self.email_config.from_address:
            return False

        if not self.email_config.to_addresses:
            return False

        # Validate email addresses format
        all_addresses = (
            self.email_config.to_addresses
            + self.email_config.cc_addresses
            + self.email_config.bcc_addresses
        )

        for addr in all_addresses:
            if "@" not in addr:
                return False

        return True

    def _get_connection(self) -> smtplib.SMTP:
        """Get or create SMTP connection."""
        if self._connection is None:
            with self._connection_lock:
                if self._connection is None:
                    config = self.email_config
                    self._connection = smtplib.SMTP(
                        config.smtp_host,
                        config.smtp_port,
                        timeout=config.timeout_seconds,
                    )

                    if config.smtp_use_tls:
                        self._connection.starttls()

                    if config.smtp_username and config.smtp_password:
                        self._connection.login(
                            config.smtp_username,
                            config.smtp_password,
                        )

        return self._connection

    def _render_template(self, template: str, variables: dict[str, Any]) -> str:
        """Render template with variables."""
        result = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))
        return result

    def _prepare_message(self, notification: "Notification") -> EmailMessage:
        """Prepare email message from notification."""
        config = self.email_config

        # Create message
        msg = EmailMessage()

        # Set recipients
        msg["To"] = ", ".join(config.to_addresses)
        if config.cc_addresses:
            msg["Cc"] = ", ".join(config.cc_addresses)
        if config.bcc_addresses:
            msg["Bcc"] = ", ".join(config.bcc_addresses)

        # Set sender
        msg["From"] = formataddr((config.from_name, config.from_address))

        # Set subject
        subject_vars = {
            "title": notification.title,
            "type": notification.notification_type.value,
            "severity": notification.severity.value,
            "agent_name": notification.agent_name or "Unknown",
            "run_id": notification.run_id or "N/A",
        }
        msg["Subject"] = self._render_template(config.subject_template, subject_vars)

        # Set date
        msg["Date"] = formatdate(localtime=True)

        # Prepare template variables
        template_vars = {
            "title": notification.title,
            "message": notification.message,
            "type": notification.notification_type.value,
            "severity": notification.severity.value,
            "agent_name": notification.agent_name or "N/A",
            "run_id": notification.run_id or "N/A",
            "project_id": notification.project_id or "N/A",
            "finding_id": notification.finding_id or "N/A",
            "created_at": notification.created_at,
            **notification.metadata,
        }

        # Set body
        if config.use_html and config.html_template:
            body = self._render_template(config.html_template, template_vars)
            msg.set_content(body, subtype="html")
        else:
            body = self._render_template(config.body_template, template_vars)
            msg.set_content(body)

        # Add custom headers
        msg["X-Notification-ID"] = notification.notification_id
        msg["X-Notification-Type"] = notification.notification_type.value
        msg["X-Notification-Severity"] = notification.severity.value

        if notification.run_id:
            msg["X-Run-ID"] = notification.run_id

        return msg

    def deliver(self, notification: "Notification") -> DeliveryResult:
        """
        Deliver notification via email.

        Args:
            notification: Notification to deliver

        Returns:
            DeliveryResult with delivery status
        """
        if not self.validate_config():
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message="Invalid email configuration",
                retryable=False,
            )

        if self.is_rate_limited():
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message="Rate limit exceeded",
                retryable=True,
            )

        try:
            # Prepare message
            message = self._prepare_message(notification)

            # Get all recipients (to + cc + bcc)
            all_recipients = (
                self.email_config.to_addresses
                + self.email_config.cc_addresses
                + self.email_config.bcc_addresses
            )

            # Send message
            connection = self._get_connection()
            connection.send_message(message, to_addrs=all_recipients)

            self._log_delivery(notification, True)
            return DeliveryResult(
                success=True,
                channel=self.channel_type,
                notification_id=notification.notification_id,
            )

        except smtplib.SMTPAuthenticationError as e:
            error = f"SMTP authentication failed: {e}"
            self._log_delivery(notification, False, error)
            self._close_connection()  # Force reconnect on retry
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=False,
            )

        except smtplib.SMTPRecipientsRefused as e:
            error = f"Recipients refused: {e}"
            self._log_delivery(notification, False, error)
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=False,
            )

        except smtplib.SMTPException as e:
            error = f"SMTP error: {e}"
            self._log_delivery(notification, False, error)
            self._close_connection()  # Force reconnect on retry
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=True,
            )

        except (OSError, TimeoutError) as e:
            error = f"Connection error: {e}"
            self._log_delivery(notification, False, error)
            self._close_connection()  # Force reconnect on retry
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=True,
            )

        except Exception as e:
            error = f"Unexpected error: {e}"
            self._log_delivery(notification, False, error)
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=False,
            )

    def _close_connection(self) -> None:
        """Close SMTP connection if open."""
        if self._connection is not None:
            try:
                self._connection.quit()
            except Exception:
                pass
            self._connection = None

    def close(self) -> None:
        """Close channel and cleanup resources."""
        self._close_connection()


# Import type hint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_god.notifications.models import Notification
