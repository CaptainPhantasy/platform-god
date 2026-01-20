"""
Base channel class for notification delivery.

All notification channels must inherit from BaseChannel and implement
the deliver() method.
"""

import json
import threading
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ChannelConfig(BaseModel):
    """Base configuration for notification channels."""

    enabled: bool = True
    timeout_seconds: int = 30
    max_retries: int = 3
    rate_limit_per_minute: int | None = None
    metadata: dict[str, Any] = {}

    model_config = {"arbitrary_types_allowed": True}


class RateLimiter:
    """
    Thread-safe rate limiter for notification channels.

    Uses token bucket algorithm for rate limiting.
    """

    def __init__(self, max_tokens: int, refill_interval_seconds: float = 60.0):
        """
        Initialize rate limiter.

        Args:
            max_tokens: Maximum number of tokens (requests per interval)
            refill_interval_seconds: Time in seconds to refill all tokens
        """
        self.max_tokens = max_tokens
        self.refill_interval = refill_interval_seconds
        self.tokens = max_tokens
        self.last_refill_time = 0.0
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        import time

        now = time.time()
        elapsed = now - self.last_refill_time
        if elapsed >= self.refill_interval:
            # Full refill
            self.tokens = self.max_tokens
            self.last_refill_time = now
        else:
            # Partial refill based on elapsed time
            refill_amount = int((elapsed / self.refill_interval) * self.max_tokens)
            self.tokens = min(self.max_tokens, self.tokens + refill_amount)
            self.last_refill_time = now

    def acquire(self, tokens: int = 1) -> bool:
        """
        Try to acquire tokens for a request.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens were acquired, False if rate limited
        """
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_available_tokens(self) -> int:
        """Get current available tokens."""
        with self._lock:
            self._refill()
            return self.tokens


class BaseChannel(ABC):
    """
    Abstract base class for notification channels.

    All channels must implement:
    - deliver(): Send the notification
    - validate_config(): Check configuration validity
    """

    channel_type: str = "base"

    def __init__(self, config: ChannelConfig | None = None):
        """
        Initialize the channel.

        Args:
            config: Channel configuration
        """
        self.config = config or ChannelConfig()
        self._rate_limiter: RateLimiter | None = None

        if self.config.rate_limit_per_minute:
            self._rate_limiter = RateLimiter(
                max_tokens=self.config.rate_limit_per_minute,
                refill_interval_seconds=60.0,
            )

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Validate channel configuration.

        Returns:
            True if configuration is valid
        """
        pass

    @abstractmethod
    def deliver(self, notification: "Notification") -> "DeliveryResult":
        """
        Deliver a notification through this channel.

        Args:
            notification: Notification to deliver

        Returns:
            DeliveryResult with delivery status
        """
        pass

    def is_enabled(self) -> bool:
        """Check if channel is enabled."""
        return self.config.enabled

    def is_rate_limited(self) -> bool:
        """Check if channel is currently rate limited."""
        if self._rate_limiter is None:
            return False
        return not self._rate_limiter.acquire()

    def prepare_payload(self, notification: "Notification") -> dict[str, Any]:
        """
        Prepare a standardized payload for the notification.

        Args:
            notification: Notification to prepare

        Returns:
            Dictionary payload suitable for most channels
        """
        return {
            "id": notification.notification_id,
            "title": notification.title,
            "message": notification.message,
            "type": notification.notification_type.value,
            "severity": notification.severity.value,
            "priority": notification.priority.value,
            "timestamp": notification.created_at,
            "run_id": notification.run_id,
            "project_id": notification.project_id,
            "finding_id": notification.finding_id,
            "agent_name": notification.agent_name,
            "metadata": notification.metadata,
        }

    def _log_delivery(
        self,
        notification: "Notification",
        success: bool,
        error: str | None = None,
    ) -> None:
        """
        Log delivery attempt for debugging/auditing.

        Args:
            notification: Notification that was delivered
            success: Whether delivery succeeded
            error: Error message if failed
        """
        log_entry = {
            "channel": self.channel_type,
            "notification_id": notification.notification_id,
            "success": success,
            "error": error,
            "timestamp": self._get_timestamp(),
        }

        # In production, this would go to a structured logger
        # For now, just format as a string
        if success:
            print(f"[NOTIFICATION DELIVERED] {json.dumps(log_entry)}")
        else:
            print(f"[NOTIFICATION FAILED] {json.dumps(log_entry)}")

    @staticmethod
    def _get_timestamp() -> str:
        """Get current ISO timestamp."""
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Import type hints - done at end to avoid circular imports
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_god.notifications.models import Notification, DeliveryResult
