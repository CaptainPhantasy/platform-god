"""
Console notification channel.

Outputs notifications to the console with formatted output.
Useful for development, testing, and local debugging.
"""

import json
import sys

from pydantic import BaseModel

from platform_god.notifications.channels.base import BaseChannel
from platform_god.notifications.models import (
    DeliveryResult,
    NotificationSeverity,
    NotificationType,
)


class ConsoleChannelConfig(BaseModel):
    """Configuration for console channel."""

    # Base settings
    enabled: bool = True
    timeout_seconds: int = 30
    max_retries: int = 3
    rate_limit_per_minute: int | None = None

    output_stream: str = "stdout"  # "stdout" or "stderr"
    colorize: bool = True
    include_timestamp: bool = True
    include_metadata: bool = False
    format_type: str = "pretty"  # "pretty", "json", "compact"


class ConsoleChannel(BaseChannel):
    """
    Notification delivery to console output.

    Features:
    - Color-coded output by severity
    - Multiple output formats (pretty, JSON, compact)
    - Optional stderr output for errors
    - Thread-safe via file locking
    """

    channel_type = "console"

    # ANSI color codes
    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "red": "\033[31m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "blue": "\033[34m",
        "magenta": "\033[35m",
        "cyan": "\033[36m",
        "white": "\033[37m",
    }

    # Severity to color mapping
    SEVERITY_COLORS = {
        NotificationSeverity.CRITICAL: "red",
        NotificationSeverity.HIGH: "red",
        NotificationSeverity.MEDIUM: "yellow",
        NotificationSeverity.LOW: "blue",
        NotificationSeverity.INFO: "cyan",
    }

    # Notification type to symbol mapping
    TYPE_SYMBOLS = {
        NotificationType.ALERT: "",
        NotificationType.WARNING: "",
        NotificationType.INFO: "",
        NotificationType.SUCCESS: "",
        NotificationType.ERROR: "",
    }

    def __init__(self, config: ConsoleChannelConfig | None = None):
        """
        Initialize console channel.

        Args:
            config: Console channel configuration
        """
        from platform_god.notifications.channels.base import ChannelConfig

        if config is None:
            config = ConsoleChannelConfig()

        base_config = ChannelConfig(
            enabled=config.enabled,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
        super().__init__(base_config)
        self.console_config: ConsoleChannelConfig = config

    def validate_config(self) -> bool:
        """Validate console configuration."""
        if self.console_config.output_stream not in ("stdout", "stderr"):
            return False
        if self.console_config.format_type not in ("pretty", "json", "compact"):
            return False
        return True

    def deliver(self, notification: "Notification") -> DeliveryResult:
        """
        Deliver notification to console.

        Args:
            notification: Notification to deliver

        Returns:
            DeliveryResult (console delivery always succeeds)
        """
        if not self.validate_config():
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message="Invalid console configuration",
                retryable=False,
            )

        try:
            output = self._format_notification(notification)
            stream = sys.stderr if self.console_config.output_stream == "stderr" else sys.stdout

            # Write output (thread-safe for file objects)
            stream.write(output + "\n")
            stream.flush()

            self._log_delivery(notification, True)
            return DeliveryResult(
                success=True,
                channel=self.channel_type,
                notification_id=notification.notification_id,
            )

        except Exception as e:
            self._log_delivery(notification, False, str(e))
            return DeliveryResult(
                success=False,
                channel=self.channel_type,
                notification_id=notification.notification_id,
                error_message=str(e),
                retryable=False,
            )

    def _format_notification(self, notification: "Notification") -> str:
        """Format notification based on configured format type."""
        format_type = self.console_config.format_type

        if format_type == "json":
            return self._format_json(notification)
        elif format_type == "compact":
            return self._format_compact(notification)
        else:
            return self._format_pretty(notification)

    def _format_pretty(self, notification: "Notification") -> str:
        """Format notification with pretty printing."""
        lines = []
        config = self.console_config

        # Header with timestamp
        if config.include_timestamp:
            timestamp = notification.created_at
            lines.append(f"{self._colorize('gray', f'[{timestamp}]')}")

        # Icon and title
        icon = self._get_icon(notification)
        color = self._get_severity_color(notification.severity)
        title_line = self._colorize(color, f"{icon} {notification.title}")
        lines.append(self._colorize("bold", title_line))

        # Separator
        lines.append(self._colorize("gray", "-" * 60))

        # Message body
        lines.append(notification.message)

        # Context information
        context_parts = []
        if notification.run_id:
            context_parts.append(f"Run: {notification.run_id}")
        if notification.agent_name:
            context_parts.append(f"Agent: {notification.agent_name}")
        if notification.project_id:
            context_parts.append(f"Project: {notification.project_id}")
        if notification.finding_id:
            context_parts.append(f"Finding: {notification.finding_id}")

        if context_parts:
            lines.append("")
            lines.append(self._colorize("gray", " | ".join(context_parts)))

        # Metadata
        if config.include_metadata and notification.metadata:
            lines.append("")
            metadata_str = json.dumps(notification.metadata, indent=2)
            lines.append(self._colorize("gray", metadata_str))

        return "\n".join(lines)

    def _format_compact(self, notification: "Notification") -> str:
        """Format notification in compact single-line format."""
        config = self.console_config
        parts = []

        if config.include_timestamp:
            parts.append(f"[{notification.created_at}]")

        parts.append(f"[{notification.severity.value.upper()}]")
        parts.append(f"[{notification.notification_type.value}]")

        if notification.agent_name:
            parts.append(f"{notification.agent_name}:")

        parts.append(notification.title)

        return " ".join(parts)

    def _format_json(self, notification: "Notification") -> str:
        """Format notification as JSON."""
        payload = self.prepare_payload(notification)

        # Add console-specific fields
        payload["console_output"] = {
            "stream": self.console_config.output_stream,
            "colorize": self.console_config.colorize,
        }

        return json.dumps(payload, indent=2)

    def _get_severity_color(self, severity: NotificationSeverity) -> str:
        """Get ANSI color for severity level."""
        if not self.console_config.colorize:
            return ""
        return self.SEVERITY_COLORS.get(severity, "white")

    def _get_icon(self, notification: "Notification") -> str:
        """Get icon symbol for notification."""
        if not self.console_config.colorize:
            return "*"

        # Map notification type to emoji/icon
        type_icons = {
            NotificationType.ALERT: "",
            NotificationType.ERROR: "",
            NotificationType.WARNING: "",
            NotificationType.SUCCESS: "",
            NotificationType.INFO: "",
        }

        return type_icons.get(notification.notification_type, "")

    def _colorize(self, color_name: str, text: str) -> str:
        """Apply ANSI color to text."""
        if not self.console_config.colorize or color_name == "gray":
            if color_name == "gray" and self.console_config.colorize:
                return f"\033[90m{text}\033[0m"
            return text

        color_code = self.COLORS.get(color_name, "")
        if color_code:
            return f"{color_code}{text}{self.COLORS['reset']}"
        return text


# Import type hint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_god.notifications.models import Notification
