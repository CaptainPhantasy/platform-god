"""
Notification channel implementations for Platform God.

Provides delivery mechanisms for various notification channels including
webhooks, console output, email, and Slack integrations.
"""

from platform_god.notifications.channels.base import BaseChannel
from platform_god.notifications.channels.webhook import WebhookChannel
from platform_god.notifications.channels.console import ConsoleChannel, ConsoleChannelConfig
from platform_god.notifications.channels.email import EmailChannel
from platform_god.notifications.channels.slack import SlackChannel

__all__ = [
    "BaseChannel",
    "WebhookChannel",
    "ConsoleChannel",
    "ConsoleChannelConfig",
    "EmailChannel",
    "SlackChannel",
]

# Channel type registry
CHANNEL_REGISTRY: dict[str, type[BaseChannel]] = {
    "webhook": WebhookChannel,
    "console": ConsoleChannel,
    "email": EmailChannel,
    "slack": SlackChannel,
}


def get_channel(channel_type: str) -> type[BaseChannel] | None:
    """Get channel class by type identifier."""
    return CHANNEL_REGISTRY.get(channel_type.lower())


def register_channel(channel_type: str, channel_class: type[BaseChannel]) -> None:
    """Register a custom channel type."""
    CHANNEL_REGISTRY[channel_type.lower()] = channel_class


# Import type hints for type checking
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_god.notifications.models import DeliveryResult
    from platform_god.notifications.models import Notification

    __all__ = [  # type: ignore
        "BaseChannel",
        "WebhookChannel",
        "ConsoleChannel",
        "EmailChannel",
        "SlackChannel",
        "Notification",
        "DeliveryResult",
    ]
