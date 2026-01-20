"""
Notification data models for Platform God.

Defines the core data structures for notification delivery, tracking,
and management.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NotificationType(Enum):
    """Types of notifications that can be sent."""

    ALERT = "alert"
    WARNING = "warning"
    INFO = "info"
    SUCCESS = "success"
    ERROR = "error"


class NotificationSeverity(Enum):
    """Severity levels for notifications."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class NotificationChannelType(Enum):
    """Available notification delivery channels."""

    WEBHOOK = "webhook"
    CONSOLE = "console"
    EMAIL = "email"
    SLACK = "slack"


class NotificationStatus(Enum):
    """Delivery status of a notification."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"


class NotificationPriority(Enum):
    """Priority levels for notification queueing."""

    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    BULK = 4


@dataclass
class DeliveryResult:
    """Result of a notification delivery attempt."""

    success: bool
    channel: str
    notification_id: str
    error_message: str | None = None
    status_code: int | None = None
    response_body: str | None = None
    delivered_at: str = field(default_factory=lambda: _iso_timestamp())
    retryable: bool = True


class NotificationChannel(BaseModel):
    """Configuration for a notification channel."""

    name: str = Field(description="Unique channel identifier")
    type: NotificationChannelType = Field(description="Channel type")
    enabled: bool = Field(default=True, description="Whether channel is active")
    config: dict[str, Any] = Field(default_factory=dict, description="Channel-specific config")
    rate_limit: int | None = Field(default=None, description="Max messages per minute")
    retry_attempts: int = Field(default=3, description="Max retry attempts")
    timeout_seconds: int = Field(default=30, description="Request timeout")

    def is_available(self) -> bool:
        """Check if channel is available for delivery."""
        return self.enabled


class NotificationTemplate(BaseModel):
    """Template for notification messages."""

    name: str = Field(description="Template identifier")
    title_template: str = Field(description="Title template with {{vars}}")
    body_template: str = Field(description="Body template with {{vars}}")
    notification_type: NotificationType = Field(default=NotificationType.INFO)
    default_severity: NotificationSeverity = Field(default=NotificationSeverity.INFO)
    required_vars: list[str] = Field(default_factory=list, description="Variables that must be provided")
    optional_vars: list[str] = Field(default_factory=list, description="Optional variables")
    metadata: dict[str, Any] = Field(default_factory=dict)

    def render(self, variables: dict[str, Any]) -> tuple[str, str]:
        """
        Render the template with provided variables.

        Returns:
            Tuple of (rendered_title, rendered_body)
        """
        # Validate required variables
        missing = [v for v in self.required_vars if v not in variables]
        if missing:
            raise ValueError(f"Missing required template variables: {missing}")

        # Render title
        rendered_title = self._render_template(self.title_template, variables)

        # Render body
        rendered_body = self._render_template(self.body_template, variables)

        return rendered_title, rendered_body

    @staticmethod
    def _render_template(template: str, variables: dict[str, Any]) -> str:
        """Replace {{var}} placeholders with values."""
        result = template
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))
        return result


class Notification(BaseModel):
    """A notification to be delivered."""

    notification_id: str = Field(
        default_factory=lambda: f"notif-{uuid.uuid4().hex[:16]}",
        description="Unique notification identifier"
    )
    title: str = Field(description="Notification title")
    message: str = Field(description="Notification body/message")
    notification_type: NotificationType = Field(default=NotificationType.INFO)
    severity: NotificationSeverity = Field(default=NotificationSeverity.INFO)
    priority: NotificationPriority = Field(default=NotificationPriority.MEDIUM)

    # Context references
    run_id: str | None = Field(default=None, description="Associated run ID")
    project_id: int | None = Field(default=None, description="Associated project ID")
    finding_id: str | None = Field(default=None, description="Associated finding ID")
    agent_name: str | None = Field(default=None, description="Agent that triggered notification")

    # Delivery configuration
    channels: list[str] = Field(default_factory=list, description="Channel names to send to")
    template_name: str | None = Field(default=None, description="Template used if any")
    variables: dict[str, Any] = Field(default_factory=dict, description="Template variables used")

    # Metadata and expiry
    metadata: dict[str, Any] = Field(default_factory=dict)
    expires_at: str | None = Field(default=None, description="ISO timestamp when notification expires")
    created_at: str = Field(default_factory=lambda: _iso_timestamp())

    # Delivery tracking
    status: NotificationStatus = Field(default=NotificationStatus.PENDING)
    retry_count: int = Field(default=0)
    last_retry_at: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    delivery_results: dict[str, DeliveryResult] = Field(
        default_factory=dict,
        description="Channel name -> delivery result"
    )

    def is_expired(self) -> bool:
        """Check if notification has expired."""
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expiry
        except ValueError:
            return False

    def should_retry(self, max_retries: int = 3) -> bool:
        """Check if notification should be retried."""
        return (
            self.status == NotificationStatus.FAILED
            and self.retry_count < max_retries
        )

    def mark_sent(self, channel: str, result: DeliveryResult | None = None) -> None:
        """Mark notification as sent to a channel."""
        if result:
            self.delivery_results[channel] = result
        if not self.delivery_results:
            self.status = NotificationStatus.SENT

    def mark_failed(self, channel: str, error: str, retryable: bool = True) -> None:
        """Mark notification as failed for a channel."""
        self.delivery_results[channel] = DeliveryResult(
            success=False,
            channel=channel,
            notification_id=self.notification_id,
            error_message=error,
            retryable=retryable,
        )
        self.error_message = error
        self.status = NotificationStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        """Convert notification to dictionary for storage/serialization."""
        return {
            "notification_id": self.notification_id,
            "title": self.title,
            "message": self.message,
            "notification_type": self.notification_type.value,
            "severity": self.severity.value,
            "run_id": self.run_id,
            "project_id": self.project_id,
            "finding_id": self.finding_id,
            "channels": json.dumps(self.channels),
            "sent_at": self.created_at,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "last_retry_at": self.last_retry_at,
            "error_message": self.error_message,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
            "expires_at": self.expires_at,
        }


class NotificationBatch(BaseModel):
    """A batch of notifications for bulk processing."""

    batch_id: str = Field(
        default_factory=lambda: f"batch-{uuid.uuid4().hex[:12]}",
        description="Unique batch identifier"
    )
    notifications: list[Notification] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: _iso_timestamp())
    metadata: dict[str, Any] = Field(default_factory=dict)

    def add(self, notification: Notification) -> None:
        """Add a notification to the batch."""
        self.notifications.append(notification)

    def is_empty(self) -> bool:
        """Check if batch is empty."""
        return len(self.notifications) == 0

    def size(self) -> int:
        """Get number of notifications in batch."""
        return len(self.notifications)


class NotificationFilter(BaseModel):
    """Filter for querying notifications."""

    run_id: str | None = None
    project_id: int | None = None
    finding_id: str | None = None
    notification_types: list[NotificationType] | None = None
    severities: list[NotificationSeverity] | None = None
    statuses: list[NotificationStatus] | None = None
    agent_name: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    limit: int = 100
    offset: int = 0

    def matches(self, notification: Notification) -> bool:
        """Check if notification matches this filter."""
        if self.run_id and notification.run_id != self.run_id:
            return False
        if self.project_id is not None and notification.project_id != self.project_id:
            return False
        if self.finding_id and notification.finding_id != self.finding_id:
            return False
        if self.notification_types and notification.notification_type not in self.notification_types:
            return False
        if self.severities and notification.severity not in self.severities:
            return False
        if self.statuses and notification.status not in self.statuses:
            return False
        if self.agent_name and notification.agent_name != self.agent_name:
            return False
        return True


def _iso_timestamp() -> str:
    """Return current ISO8601 timestamp in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Need to import at module level for to_dict()
import json
