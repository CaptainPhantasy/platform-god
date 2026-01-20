"""
Webhook notification channel.

Delivers notifications via HTTP/HTTPS webhooks with support for
various authentication methods and retry logic.
"""

import json
import threading
import time
from typing import Any

import requests
from pydantic import BaseModel

from platform_god.notifications.channels.base import BaseChannel
from platform_god.notifications.models import DeliveryResult


class WebhookChannelConfig(BaseModel):
    """Configuration for webhook channel."""

    url: str
    method: str = "POST"
    headers: dict[str, str] = {}
    auth_type: str = "none"  # "none", "basic", "bearer", "header"
    auth_username: str | None = None
    auth_password: str | None = None
    auth_token: str | None = None
    auth_header_name: str = "Authorization"
    verify_ssl: bool = True
    enabled: bool = True
    timeout_seconds: int = 30
    max_retries: int = 3
    retry_backoff_ms: int = 1000
    payload_format: str = "json"  # "json", "form", "text"
    rate_limit_per_minute: int | None = None


class WebhookChannel(BaseChannel):
    """
    Notification delivery via HTTP webhooks.

    Supports:
    - Multiple authentication methods (basic, bearer token, custom header)
    - SSL verification control
    - Configurable retry with exponential backoff
    - Rate limiting
    - Thread-safe delivery
    """

    channel_type = "webhook"

    def __init__(self, config: WebhookChannelConfig):
        """
        Initialize webhook channel.

        Args:
            config: Webhook channel configuration
        """
        from platform_god.notifications.channels.base import ChannelConfig

        # Convert to base config for parent
        base_config = ChannelConfig(
            enabled=config.enabled,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
            rate_limit_per_minute=config.rate_limit_per_minute,
        )
        super().__init__(base_config)
        self.webhook_config: WebhookChannelConfig = config
        self._session_lock = threading.Lock()
        self._session: requests.Session | None = None

    def validate_config(self) -> bool:
        """Validate webhook configuration."""
        if not self.webhook_config.url:
            return False

        if not self.webhook_config.url.startswith(("http://", "https://")):
            return False

        if self.webhook_config.method not in ("POST", "PUT", "PATCH"):
            return False

        if self.webhook_config.auth_type == "basic":
            if not self.webhook_config.auth_username or not self.webhook_config.auth_password:
                return False
        elif self.webhook_config.auth_type == "bearer":
            if not self.webhook_config.auth_token:
                return False
        elif self.webhook_config.auth_type == "header":
            if not self.webhook_config.auth_token or not self.webhook_config.auth_header_name:
                return False

        return True

    def _get_session(self) -> requests.Session:
        """Get or create thread-local requests session."""
        if self._session is None:
            with self._session_lock:
                if self._session is None:
                    self._session = requests.Session()
        return self._session

    def _prepare_auth(self) -> tuple[Any, ...] | None:
        """Prepare authentication tuple for requests."""
        auth_type = self.webhook_config.auth_type

        if auth_type == "basic":
            return (
                self.webhook_config.auth_username,
                self.webhook_config.auth_password,
            )
        return None

    def _prepare_headers(self) -> dict[str, str]:
        """Prepare headers for webhook request."""
        headers = self.webhook_config.headers.copy()

        # Add content-type based on format
        if self.webhook_config.payload_format == "json":
            headers.setdefault("Content-Type", "application/json")
        elif self.webhook_config.payload_format == "form":
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            headers.setdefault("Content-Type", "text/plain")

        # Add auth header if using bearer or custom header
        auth_type = self.webhook_config.auth_type
        if auth_type == "bearer":
            header_name = self.webhook_config.auth_header_name
            headers[header_name] = f"Bearer {self.webhook_config.auth_token}"
        elif auth_type == "header":
            header_name = self.webhook_config.auth_header_name
            headers[header_name] = self.webhook_config.auth_token

        return headers

    def _prepare_payload(self, notification: "Notification") -> Any:
        """Prepare request body based on configured format."""
        base_payload = self.prepare_payload(notification)

        format_type = self.webhook_config.payload_format

        if format_type == "json":
            return json.dumps(base_payload)
        elif format_type == "form":
            # Flatten the payload for form encoding
            return {
                "id": notification.notification_id,
                "title": notification.title,
                "message": notification.message,
                "type": notification.notification_type.value,
                "severity": notification.severity.value,
                "timestamp": notification.created_at,
            }
        else:  # text
            return f"{notification.title}\n\n{notification.message}"

    def deliver(self, notification: "Notification") -> DeliveryResult:
        """
        Deliver notification via webhook.

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
                error_message="Invalid webhook configuration",
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

        url = self.webhook_config.url
        method = self.webhook_config.method
        auth = self._prepare_auth()
        headers = self._prepare_headers()
        payload = self._prepare_payload(notification)
        verify_ssl = self.webhook_config.verify_ssl
        timeout = self.webhook_config.timeout_seconds

        last_error = None

        for attempt in range(self.webhook_config.max_retries):
            try:
                response = self._get_session().request(
                    method=method,
                    url=url,
                    data=payload,
                    headers=headers,
                    auth=auth,
                    verify=verify_ssl,
                    timeout=timeout,
                )

                # Consider 2xx and 3xx as success
                if 200 <= response.status_code < 400:
                    self._log_delivery(notification, True)
                    return DeliveryResult(
                        success=True,
                        channel=self.channel_type,
                        notification_id=notification.notification_id,
                        status_code=response.status_code,
                        response_body=response.text[:1000] if response.text else None,
                    )
                else:
                    last_error = f"HTTP {response.status_code}: {response.text[:200]}"

                    # Don't retry on client errors (4xx)
                    if 400 <= response.status_code < 500:
                        return DeliveryResult(
                            success=False,
                            channel=self.channel_type,
                            notification_id=notification.notification_id,
                            error_message=last_error,
                            status_code=response.status_code,
                            retryable=False,
                        )

            except requests.exceptions.Timeout:
                last_error = f"Request timeout after {timeout}s"
            except requests.exceptions.SSLError as e:
                last_error = f"SSL error: {e}"
                # Don't retry SSL errors
                self._log_delivery(notification, False, last_error)
                return DeliveryResult(
                    success=False,
                    channel=self.channel_type,
                    notification_id=notification.notification_id,
                    error_message=last_error,
                    retryable=False,
                )
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {e}"
            except requests.exceptions.RequestException as e:
                last_error = f"Request error: {e}"
            except Exception as e:
                last_error = f"Unexpected error: {e}"

            # Backoff before retry
            if attempt < self.webhook_config.max_retries - 1:
                backoff = self.webhook_config.retry_backoff_ms * (2**attempt) / 1000
                time.sleep(backoff)

        self._log_delivery(notification, False, last_error)
        return DeliveryResult(
            success=False,
            channel=self.channel_type,
            notification_id=notification.notification_id,
            error_message=last_error or "Unknown error",
            retryable=True,
        )

    def close(self) -> None:
        """Close the requests session."""
        if self._session:
            self._session.close()
            self._session = None


# Import type hint
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from platform_god.notifications.models import Notification
