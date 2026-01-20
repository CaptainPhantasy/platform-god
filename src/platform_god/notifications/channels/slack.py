"""
Slack notification channel.

Delivers notifications to Slack via Incoming Webhooks.
This is a template implementation that can be extended with
full Slack API integration.
"""

import json
from typing import Any

import requests
from pydantic import BaseModel

from platform_god.notifications.channels.base import BaseChannel
from platform_god.notifications.models import (
    DeliveryResult,
    NotificationSeverity,
    NotificationType,
)


class SlackChannelConfig(BaseModel):
    """Configuration for Slack channel."""

    # Base settings
    enabled: bool = True
    max_retries: int = 3
    rate_limit_per_minute: int | None = None

    webhook_url: str = ""
    username: str = "Platform God"
    icon_emoji: str = ":robot_face:"
    channel: str = ""  # Override default webhook channel
    timeout_seconds: int = 30

    # Formatting options
    use_attachments: bool = True
    include_footer: bool = True
    include_fields: bool = True

    # Color mappings for severity
    color_critical: str = "#FF0000"
    color_high: str = "#FF6600"
    color_medium: str = "#FFCC00"
    color_low: str = "#0066FF"
    color_info: str = "#808080"
    color_success: str = "#00CC00"


class SlackChannel(BaseChannel):
    """
    Notification delivery via Slack Incoming Webhooks.

    Features:
    - Incoming webhook delivery
    - Rich formatting with attachments
    - Color-coded messages by severity
    - Custom username and icon
    - Channel override support

    Note: This is a template implementation using Incoming Webhooks.
    For production use, consider:
    - Using Slack API tokens for more features
    - Implementing rate limiting (Slack has limits)
    - Adding thread support
    - Adding user/channel mentions
    """

    channel_type = "slack"

    # Severity to color mapping
    SEVERITY_COLORS = {
        NotificationSeverity.CRITICAL: "danger",
        NotificationSeverity.HIGH: "danger",
        NotificationSeverity.MEDIUM: "warning",
        NotificationSeverity.LOW: "good",
        NotificationSeverity.INFO: None,
    }

    def __init__(self, config: SlackChannelConfig):
        """
        Initialize Slack channel.

        Args:
            config: Slack channel configuration
        """
        from platform_god.notifications.channels.base import ChannelConfig

        base_config = ChannelConfig(
            enabled=config.enabled,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
        super().__init__(base_config)
        self.slack_config: SlackChannelConfig = config

    def validate_config(self) -> bool:
        """Validate Slack configuration."""
        if not self.slack_config.webhook_url:
            return False

        if not self.slack_config.webhook_url.startswith(
            ("https://hooks.slack.com/", "https://hooks.slack-test.com/")
        ):
            return False

        return True

    def _get_color_for_severity(self, severity: NotificationSeverity) -> str | None:
        """Get Slack attachment color for severity."""
        config = self.slack_config

        # Return custom colors if set
        color_map = {
            NotificationSeverity.CRITICAL: config.color_critical,
            NotificationSeverity.HIGH: config.color_high,
            NotificationSeverity.MEDIUM: config.color_medium,
            NotificationSeverity.LOW: config.color_low,
            NotificationSeverity.INFO: config.color_info,
        }

        return color_map.get(severity)

    def _prepare_attachment(self, notification: "Notification") -> dict[str, Any]:
        """Prepare Slack attachment for notification."""
        attachment: dict[str, Any] = {
            "title": notification.title,
            "text": notification.message,
            "color": self._get_color_for_severity(notification.severity),
            "ts": self._parse_timestamp(notification.created_at),
        }

        # Add footer if enabled
        if self.slack_config.include_footer:
            footer_parts = ["Platform God"]
            if notification.agent_name:
                footer_parts.append(f"Agent: {notification.agent_name}")
            if notification.run_id:
                footer_parts.append(f"Run: {notification.run_id[:8]}")
            attachment["footer"] = " | ".join(footer_parts)

        # Add fields if enabled
        if self.slack_config.include_fields:
            fields = []

            if notification.run_id:
                fields.append({
                    "title": "Run ID",
                    "value": f"`{notification.run_id}`",
                    "short": True,
                })

            if notification.agent_name:
                fields.append({
                    "title": "Agent",
                    "value": notification.agent_name,
                    "short": True,
                })

            if notification.project_id:
                fields.append({
                    "title": "Project ID",
                    "value": str(notification.project_id),
                    "short": True,
                })

            if notification.finding_id:
                fields.append({
                    "title": "Finding ID",
                    "value": f"`{notification.finding_id}`",
                    "short": True,
                })

            if notification.severity != NotificationSeverity.INFO:
                fields.append({
                    "title": "Severity",
                    "value": notification.severity.value.upper(),
                    "short": True,
                })

            if fields:
                attachment["fields"] = fields

        return attachment

    def _prepare_simple_message(self, notification: "Notification") -> dict[str, Any]:
        """Prepare simple Slack message without attachments."""
        # Choose icon based on notification type
        icons = {
            NotificationType.ALERT: ":warning:",
            NotificationType.ERROR: ":x:",
            NotificationType.WARNING: ":warning:",
            NotificationType.SUCCESS: ":white_check_mark:",
            NotificationType.INFO: ":information_source:",
        }

        icon = icons.get(notification.notification_type, ":information_source:")

        lines = [
            f"{icon} *{notification.title}*",
            "",
            notification.message,
        ]

        # Add context
        if notification.run_id or notification.agent_name:
            context_parts = []
            if notification.agent_name:
                context_parts.append(f"Agent: {notification.agent_name}")
            if notification.run_id:
                context_parts.append(f"Run: `{notification.run_id}`")

            if context_parts:
                lines.append("")
                lines.append("_" + " | ".join(context_parts) + "_")

        return {
            "text": "\n".join(lines),
        }

    def _prepare_payload(self, notification: "Notification") -> dict[str, Any]:
        """Prepare complete Slack webhook payload."""
        payload: dict[str, Any] = {
            "username": self.slack_config.username,
            "icon_emoji": self.slack_config.icon_emoji,
        }

        # Override channel if specified
        if self.slack_config.channel:
            payload["channel"] = self.slack_config.channel

        # Use attachments if enabled
        if self.slack_config.use_attachments:
            payload["attachments"] = [self._prepare_attachment(notification)]
        else:
            payload.update(self._prepare_simple_message(notification))

        # Add metadata as attachment if present
        if notification.metadata:
            # Ensure attachments is a list
            attachments_list = payload.get("attachments")
            if not isinstance(attachments_list, list):
                attachments_list = []
                payload["attachments"] = attachments_list

            metadata_attachment = {
                "title": "Metadata",
                "text": f"```{json.dumps(notification.metadata, indent=2)}```",
                "color": "#808080",
            }
            attachments_list.append(metadata_attachment)

        return payload

    def _parse_timestamp(self, iso_timestamp: str) -> int:
        """Parse ISO timestamp to Unix timestamp."""
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (ValueError, AttributeError):
            return 0

    def deliver(self, notification: "Notification") -> DeliveryResult:
        """
        Deliver notification via Slack webhook.

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
                error_message="Invalid Slack configuration",
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

        url = self.slack_config.webhook_url
        payload = self._prepare_payload(notification)
        timeout = self.slack_config.timeout_seconds

        try:
            response = requests.post(
                url,
                json=payload,
                timeout=timeout,
            )

            # Slack returns 200 OK even on errors, check response body
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("ok") is not False:
                    self._log_delivery(notification, True)
                    return DeliveryResult(
                        success=True,
                        channel=self.channel_type,
                        notification_id=notification.notification_id,
                        status_code=response.status_code,
                    )
                else:
                    error = response_data.get("error", "Unknown Slack error")
                    return DeliveryResult(
                        success=False,
                        channel=self.channel_type,
                        notification_id=notification.notification_id,
                        error_message=f"Slack error: {error}",
                        retryable=False,
                    )
            else:
                error = f"HTTP {response.status_code}: {response.text[:200]}"
                return DeliveryResult(
                    success=False,
                    channel=self.channel_type,
                    notification_id=notification.notification_id,
                    error_message=error,
                    status_code=response.status_code,
                    retryable=response.status_code >= 500,  # Retry on server errors
                )

        except requests.exceptions.Timeout:
            error = f"Request timeout after {timeout}s"
            self._log_delivery(notification, False, error)
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=True,
            )

        except requests.exceptions.ConnectionError as e:
            error = f"Connection error: {e}"
            self._log_delivery(notification, False, error)
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=error,
                retryable=True,
            )

        except requests.exceptions.RequestException as e:
            error = f"Request error: {e}"
            self._log_delivery(notification, False, error)
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


# Import type hint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_god.notifications.models import Notification
