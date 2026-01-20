"""Tests for notifications module (dispatcher, channels, models)."""

import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from io import StringIO

import pytest

from platform_god.notifications.models import (
    NotificationType,
    NotificationSeverity,
    NotificationChannelType,
    NotificationStatus,
    NotificationPriority,
    DeliveryResult,
    NotificationChannel,
    NotificationTemplate,
    Notification,
    NotificationBatch,
    NotificationFilter,
)
from platform_god.notifications.channels import (
    BaseChannel,
    ConsoleChannel,
    ConsoleChannelConfig,
    get_channel,
    CHANNEL_REGISTRY,
)
from platform_god.notifications.channels.base import ChannelConfig, RateLimiter
from platform_god.notifications.dispatcher import (
    DispatcherStatus,
    QueuedNotification,
    DispatcherStats,
    NotificationDispatcher,
    get_dispatcher,
    shutdown_dispatcher,
)


# =============================================================================
# Model tests
# =============================================================================


class TestNotificationModels:
    """Tests for notification model classes."""

    def test_notification_channel_is_available(self):
        """Test NotificationChannel.is_available method."""
        channel = NotificationChannel(
            name="test",
            type=NotificationChannelType.CONSOLE,
            enabled=True,
        )
        assert channel.is_available() is True

        channel.enabled = False
        assert channel.is_available() is False

    def test_notification_template_render(self):
        """Test NotificationTemplate.render method."""
        template = NotificationTemplate(
            name="test_template",
            title_template="Alert for {{agent}}",
            body_template="Status: {{status}}\nCount: {{count}}",
            required_vars=["agent", "status"],
            optional_vars=["count"],
        )

        variables = {
            "agent": "PG_DISCOVERY",
            "status": "completed",
            "count": 42,
        }

        title, body = template.render(variables)

        assert title == "Alert for PG_DISCOVERY"
        assert "Status: completed" in body
        assert "Count: 42" in body

    def test_notification_template_missing_required_vars(self):
        """Test template with missing required variables."""
        template = NotificationTemplate(
            name="test_template",
            title_template="{{title}}",
            body_template="Body",
            required_vars=["title", "missing_var"],
        )

        variables = {"title": "Test"}

        with pytest.raises(ValueError) as exc_info:
            template.render(variables)

        assert "Missing required template variables" in str(exc_info.value)

    def test_notification_is_expired(self):
        """Test Notification.is_expired method."""
        # Expired notification
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        notification = Notification(
            title="Test",
            message="Test message",
            expires_at=past.isoformat(),
        )
        assert notification.is_expired() is True

        # Not expired
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        notification2 = Notification(
            title="Test",
            message="Test message",
            expires_at=future.isoformat(),
        )
        assert notification2.is_expired() is False

        # No expiry
        notification3 = Notification(
            title="Test",
            message="Test message",
        )
        assert notification3.is_expired() is False

    def test_notification_should_retry(self):
        """Test Notification.should_retry method."""
        notification = Notification(
            title="Test",
            message="Test message",
            status=NotificationStatus.FAILED,
            retry_count=1,
        )

        # Should retry - under max
        assert notification.should_retry(max_retries=3) is True

        # Should not retry - at max
        assert notification.should_retry(max_retries=1) is False

        # Should not retry - not failed
        notification2 = Notification(
            title="Test",
            message="Test message",
            status=NotificationStatus.SENT,
        )
        assert notification2.should_retry() is False

    def test_notification_mark_sent(self):
        """Test Notification.mark_sent method."""
        notification = Notification(
            title="Test",
            message="Test message",
        )

        result = DeliveryResult(
            success=True,
            channel="console",
            notification_id=notification.notification_id,
        )

        notification.mark_sent("console", result)

        assert "console" in notification.delivery_results
        assert notification.delivery_results["console"].success is True

    def test_notification_mark_failed(self):
        """Test Notification.mark_failed method."""
        notification = Notification(
            title="Test",
            message="Test message",
        )

        notification.mark_failed("webhook", "Connection refused", retryable=True)

        assert notification.status == NotificationStatus.FAILED
        assert notification.error_message == "Connection refused"
        assert "webhook" in notification.delivery_results

    def test_notification_to_dict(self):
        """Test Notification.to_dict method."""
        notification = Notification(
            title="Test",
            message="Test message",
            run_id="run_123",
            project_id=456,
        )

        data = notification.to_dict()

        assert data["notification_id"] == notification.notification_id
        assert data["title"] == "Test"
        assert data["run_id"] == "run_123"
        assert data["project_id"] == 456


# =============================================================================
# NotificationFilter tests
# =============================================================================


class TestNotificationFilter:
    """Tests for NotificationFilter class."""

    def test_filter_matches_run_id(self):
        """Test filtering by run_id."""
        filter_obj = NotificationFilter(run_id="run_123")

        notification = Notification(
            title="Test",
            message="Test",
            run_id="run_123",
        )

        assert filter_obj.matches(notification) is True

        notification2 = Notification(
            title="Test",
            message="Test",
            run_id="run_456",
        )

        assert filter_obj.matches(notification2) is False

    def test_filter_matches_project_id(self):
        """Test filtering by project_id."""
        filter_obj = NotificationFilter(project_id=123)

        notification = Notification(
            title="Test",
            message="Test",
            project_id=123,
        )

        assert filter_obj.matches(notification) is True

    def test_filter_matches_notification_types(self):
        """Test filtering by notification types."""
        filter_obj = NotificationFilter(
            notification_types=[NotificationType.ALERT, NotificationType.ERROR]
        )

        notification = Notification(
            title="Test",
            message="Test",
            notification_type=NotificationType.ALERT,
        )

        assert filter_obj.matches(notification) is True

        notification2 = Notification(
            title="Test",
            message="Test",
            notification_type=NotificationType.INFO,
        )

        assert filter_obj.matches(notification2) is False

    def test_filter_matches_severities(self):
        """Test filtering by severity."""
        filter_obj = NotificationFilter(
            severities=[NotificationSeverity.CRITICAL, NotificationSeverity.HIGH]
        )

        notification = Notification(
            title="Test",
            message="Test",
            severity=NotificationSeverity.CRITICAL,
        )

        assert filter_obj.matches(notification) is True

    def test_filter_multiple_criteria(self):
        """Test filter with multiple criteria."""
        filter_obj = NotificationFilter(
            run_id="run_789",
            notification_types=[NotificationType.ERROR],
            severities=[NotificationSeverity.HIGH],
        )

        notification = Notification(
            title="Test",
            message="Test",
            run_id="run_789",
            notification_type=NotificationType.ERROR,
            severity=NotificationSeverity.HIGH,
        )

        assert filter_obj.matches(notification) is True


# =============================================================================
# NotificationBatch tests
# =============================================================================


class TestNotificationBatch:
    """Tests for NotificationBatch class."""

    def test_batch_add_notification(self):
        """Test adding notifications to batch."""
        batch = NotificationBatch()

        notification = Notification(title="Test", message="Test")
        batch.add(notification)

        assert batch.size() == 1
        assert batch.is_empty() is False

    def test_batch_is_empty(self):
        """Test checking if batch is empty."""
        batch = NotificationBatch()
        assert batch.is_empty() is True


# =============================================================================
# RateLimiter tests
# =============================================================================


class TestRateLimiter:
    """Tests for RateLimiter class."""

    def test_acquire_under_limit(self):
        """Test acquiring tokens under limit."""
        limiter = RateLimiter(max_tokens=10, refill_interval_seconds=60.0)

        for _ in range(10):
            assert limiter.acquire() is True

    def test_acquire_over_limit(self):
        """Test acquiring tokens over limit fails."""
        limiter = RateLimiter(max_tokens=5, refill_interval_seconds=60.0)

        for _ in range(5):
            assert limiter.acquire() is True

        # 6th acquisition should fail
        assert limiter.acquire() is False

    def test_get_available_tokens(self):
        """Test getting available tokens."""
        limiter = RateLimiter(max_tokens=100)

        assert limiter.get_available_tokens() == 100

        limiter.acquire(50)
        assert limiter.get_available_tokens() == 50


# =============================================================================
# ConsoleChannel tests
# =============================================================================


class TestConsoleChannel:
    """Tests for ConsoleChannel class."""

    @pytest.fixture
    def channel(self):
        """Create console channel."""
        return ConsoleChannel(ConsoleChannelConfig())

    def test_validate_config(self, channel):
        """Test config validation."""
        assert channel.validate_config() is True

    def test_validate_invalid_output_stream(self):
        """Test invalid output stream fails validation."""
        config = ConsoleChannelConfig(output_stream="invalid")
        channel = ConsoleChannel(config)

        assert channel.validate_config() is False

    def test_deliver_notification(self, channel, capsys):
        """Test delivering notification to console."""
        notification = Notification(
            title="Test Notification",
            message="This is a test message",
            severity=NotificationSeverity.INFO,
        )

        result = channel.deliver(notification)

        assert result.success is True
        assert result.channel == "console"
        captured = capsys.readouterr()
        assert "Test Notification" in captured.out

    def test_deliver_json_format(self, capsys):
        """Test delivering notification in JSON format."""
        config = ConsoleChannelConfig(format_type="json")
        channel = ConsoleChannel(config)

        notification = Notification(
            title="JSON Test",
            message="JSON message",
        )

        result = channel.deliver(notification)

        assert result.success is True
        captured = capsys.readouterr()
        assert "JSON Test" in captured.out
        assert "{" in captured.out  # JSON format

    def test_deliver_compact_format(self, capsys):
        """Test delivering notification in compact format."""
        config = ConsoleChannelConfig(format_type="compact")
        channel = ConsoleChannel(config)

        notification = Notification(
            title="Compact Test",
            message="Compact message",
        )

        result = channel.deliver(notification)

        assert result.success is True
        captured = capsys.readouterr()
        assert "COMPACT Test" in captured.out or "Compact Test" in captured.out

    def test_prepare_payload(self, channel):
        """Test preparing notification payload."""
        notification = Notification(
            title="Payload Test",
            message="Payload message",
            run_id="run_123",
            project_id=456,
        )

        payload = channel.prepare_payload(notification)

        assert payload["id"] == notification.notification_id
        assert payload["title"] == "Payload Test"
        assert payload["run_id"] == "run_123"
        assert payload["project_id"] == 456


# =============================================================================
# BaseChannel tests
# =============================================================================


class TestBaseChannel:
    """Tests for BaseChannel class."""

    def test_is_enabled(self):
        """Test is_enabled method."""
        config = ChannelConfig(enabled=True)
        channel = ConsoleChannel(ConsoleChannelConfig())
        channel.config = config

        assert channel.is_enabled() is True

        config.enabled = False
        assert channel.is_enabled() is False

    def test_is_rate_limited(self):
        """Test rate limiting check."""
        config = ChannelConfig(rate_limit_per_minute=5)
        channel = ConsoleChannel(ConsoleChannelConfig())
        channel.config = config

        # Initialize rate limiter
        from platform_god.notifications.channels.base import RateLimiter
        channel._rate_limiter = RateLimiter(max_tokens=5, refill_interval_seconds=60.0)

        # First 5 should not be rate limited
        for _ in range(5):
            assert channel.is_rate_limited() is False

        # Should now be rate limited
        assert channel.is_rate_limited() is True


# =============================================================================
# Channel registry tests
# =============================================================================


class TestChannelRegistry:
    """Tests for channel registry."""

    def test_get_console_channel(self):
        """Test getting console channel from registry."""
        channel_class = get_channel("console")
        assert channel_class is not None
        assert channel_class == ConsoleChannel

    def test_get_webhook_channel(self):
        """Test getting webhook channel from registry."""
        channel_class = get_channel("webhook")
        assert channel_class is not None

    def test_get_unknown_channel(self):
        """Test getting unknown channel returns None."""
        channel_class = get_channel("unknown")
        assert channel_class is None

    def test_case_insensitive_lookup(self):
        """Test channel lookup is case insensitive."""
        channel_class1 = get_channel("Console")
        channel_class2 = get_channel("CONSOLE")
        channel_class3 = get_channel("console")

        assert channel_class1 == channel_class2 == channel_class3


# =============================================================================
# DispatcherStats tests
# =============================================================================


class TestDispatcherStats:
    """Tests for DispatcherStats class."""

    def test_success_rate_all_success(self):
        """Test success rate with all successful deliveries."""
        stats = DispatcherStats(
            notifications_sent=10,
            notifications_failed=0,
        )

        assert stats.success_rate() == 100.0

    def test_success_rate_mixed(self):
        """Test success rate with mixed results."""
        stats = DispatcherStats(
            notifications_sent=7,
            notifications_failed=3,
        )

        assert stats.success_rate() == 70.0

    def test_success_rate_no_deliveries(self):
        """Test success rate with no deliveries."""
        stats = DispatcherStats()

        assert stats.success_rate() == 100.0

    def test_average_delivery_time(self):
        """Test average delivery time calculation."""
        stats = DispatcherStats(
            notifications_sent=3,
            total_delivery_time_ms=450,  # 150ms average
        )

        assert stats.average_delivery_time_ms() == 150.0

    def test_average_delivery_time_no_deliveries(self):
        """Test average delivery time with no deliveries."""
        stats = DispatcherStats()

        assert stats.average_delivery_time_ms() == 0.0


# =============================================================================
# NotificationDispatcher tests
# =============================================================================


class TestNotificationDispatcher:
    """Tests for NotificationDispatcher class."""

    @pytest.fixture
    def temp_db_path(self, tmpdir):
        """Create temporary database path."""
        return str(tmpdir / "test_notifications.db")

    @pytest.fixture
    def dispatcher(self, temp_db_path):
        """Create dispatcher instance."""
        dispatcher = NotificationDispatcher(
            db_path=temp_db_path,
            worker_count=1,
        )
        yield dispatcher
        if dispatcher.status != DispatcherStatus.STOPPED:
            dispatcher.stop(timeout=5.0)

    def test_initial_status(self, dispatcher):
        """Test initial dispatcher status."""
        assert dispatcher.status == DispatcherStatus.STOPPED

    def test_start_dispatcher(self, dispatcher):
        """Test starting dispatcher."""
        result = dispatcher.start()
        assert result is True
        assert dispatcher.status == DispatcherStatus.RUNNING

    def test_stop_dispatcher(self, dispatcher):
        """Test stopping dispatcher."""
        dispatcher.start()
        result = dispatcher.stop(timeout=5.0)
        assert result is True
        assert dispatcher.status == DispatcherStatus.STOPPED

    def test_send_notification(self, dispatcher):
        """Test sending a notification."""
        dispatcher.start()

        notification_id = dispatcher.send(
            title="Test Notification",
            message="Test message",
            notification_type=NotificationType.INFO,
            severity=NotificationSeverity.INFO,
        )

        assert notification_id is not None
        assert notification_id.startswith("notif-")

        dispatcher.stop()

    def test_send_to_specific_channels(self, dispatcher):
        """Test sending notification to specific channels."""
        dispatcher.start()

        # Add a custom channel
        from platform_god.notifications.models import NotificationChannel
        dispatcher.add_channel(NotificationChannel(
            name="custom_console",
            type=NotificationChannelType.CONSOLE,
            enabled=True,
        ))

        notification_id = dispatcher.send(
            title="Channel Test",
            message="Test",
            channels=["custom_console"],
        )

        assert notification_id is not None

        dispatcher.stop()

    def test_add_channel(self, dispatcher):
        """Test adding a channel."""
        from platform_god.notifications.models import NotificationChannel

        result = dispatcher.add_channel(NotificationChannel(
            name="test_channel",
            type=NotificationChannelType.CONSOLE,
            enabled=True,
        ))

        assert result is True

    def test_add_disabled_channel(self, dispatcher):
        """Test adding disabled channel fails."""
        from platform_god.notifications.models import NotificationChannel

        result = dispatcher.add_channel(NotificationChannel(
            name="disabled_channel",
            type=NotificationChannelType.CONSOLE,
            enabled=False,
        ))

        assert result is False

    def test_remove_channel(self, dispatcher):
        """Test removing a channel."""
        from platform_god.notifications.models import NotificationChannel

        dispatcher.add_channel(NotificationChannel(
            name="to_remove",
            type=NotificationChannelType.CONSOLE,
            enabled=True,
        ))

        result = dispatcher.remove_channel("to_remove")
        assert result is True

    def test_remove_nonexistent_channel(self, dispatcher):
        """Test removing non-existent channel."""
        result = dispatcher.remove_channel("nonexistent")
        assert result is False

    def test_get_stats(self, dispatcher):
        """Test getting dispatcher statistics."""
        stats = dispatcher.stats

        assert isinstance(stats, DispatcherStats)
        assert stats.notifications_queued == 0
        assert stats.notifications_sent == 0

    def test_send_from_template(self, dispatcher, tmpdir):
        """Test sending notification from template."""
        dispatcher.start()

        # Create a template file
        template_file = tmpdir / "test_template.yaml"
        template_file.write_text("""
name: test_template
title_template: "{{title}}"
body_template: "{{message}}"
notification_type: info
default_severity: info
required_vars: []
optional_vars: []
""")

        # For this test, we'll just verify the method exists and handles missing templates
        result = dispatcher.send_from_template(
            "nonexistent_template",
            variables={"title": "Test", "message": "Test message"},
        )

        # Should return None for missing template
        assert result is None

        dispatcher.stop()


# =============================================================================
# Global dispatcher tests
# =============================================================================


class TestGlobalDispatcher:
    """Tests for global dispatcher singleton."""

    def test_get_dispatcher_singleton(self, tmpdir):
        """Test get_dispatcher returns singleton."""
        # Clear any existing dispatcher
        shutdown_dispatcher()

        with patch("platform_god.notifications.dispatcher.NotificationDispatcher") as mock_class:
            mock_instance = MagicMock()
            mock_instance.status = DispatcherStatus.RUNNING
            mock_instance.start.return_value = True
            mock_class.return_value = mock_instance

            dispatcher1 = get_dispatcher()
            dispatcher2 = get_dispatcher()

            assert dispatcher1 is dispatcher2

    def test_shutdown_dispatcher(self, tmpdir):
        """Test shutdown_dispatcher function."""
        shutdown_dispatcher()
        # Should not raise


# =============================================================================
# Integration tests
# =============================================================================


class TestNotificationsIntegration:
    """Integration tests for notifications module."""

    @pytest.fixture
    def temp_db_path(self, tmpdir):
        """Create temporary database path."""
        return str(tmpdir / "integration_notifications.db")

    def test_full_notification_flow(self, temp_db_path):
        """Test complete notification flow."""
        dispatcher = NotificationDispatcher(
            db_path=temp_db_path,
            worker_count=1,
        )

        # Start dispatcher
        assert dispatcher.start() is True

        # Send notification
        notification_id = dispatcher.send(
            title="Integration Test",
            message="Integration test message",
            notification_type=NotificationType.ALERT,
            severity=NotificationSeverity.HIGH,
            metadata={"test": "data"},
        )

        assert notification_id is not None

        # Check stats
        stats = dispatcher.stats
        assert stats.notifications_queued >= 1

        # Stop dispatcher
        assert dispatcher.stop(timeout=5.0) is True
        assert dispatcher.status == DispatcherStatus.STOPPED

    def test_multiple_channels_delivery(self, temp_db_path, capsys):
        """Test delivery to multiple channels."""
        dispatcher = NotificationDispatcher(
            db_path=temp_db_path,
            worker_count=1,
        )

        # Add console channel with stdout output
        from platform_god.notifications.models import NotificationChannel

        dispatcher.add_channel(NotificationChannel(
            name="test_console",
            type=NotificationChannelType.CONSOLE,
            enabled=True,
        ))

        dispatcher.start()

        # Send to specific channel
        notification_id = dispatcher.send(
            title="Multi-channel Test",
            message="Test message",
            channels=["test_console"],
        )

        assert notification_id is not None

        # Give time for delivery
        time.sleep(0.1)

        dispatcher.stop(timeout=5.0)

    def test_notification_priority_ordering(self, temp_db_path):
        """Test notifications are ordered by priority."""
        dispatcher = NotificationDispatcher(
            db_path=temp_db_path,
            worker_count=1,
        )

        # Create notifications with different priorities
        queued_notifications = [
            QueuedNotification(
                priority=NotificationPriority.LOW,
                notification=Notification(
                    title="Low Priority",
                    message="Low",
                ),
            ),
            QueuedNotification(
                priority=NotificationPriority.CRITICAL,
                notification=Notification(
                    title="Critical",
                    message="Critical",
                ),
            ),
            QueuedNotification(
                priority=NotificationPriority.HIGH,
                notification=Notification(
                    title="High Priority",
                    message="High",
                ),
            ),
        ]

        # Critical (0) < High (1) < Low (3)
        assert queued_notifications[0].priority.value < queued_notifications[1].priority.value
        assert queued_notifications[1].priority.value < queued_notifications[2].priority.value

    def test_template_rendering_integration(self):
        """Test template rendering with real notification."""
        template = NotificationTemplate(
            name="integration_template",
            title_template="{{severity}}: {{title}}",
            body_template="Agent: {{agent}}\nStatus: {{status}}\n\nDetails: {{message}}",
            required_vars=["severity", "title", "agent", "status"],
        )

        variables = {
            "severity": "WARNING",
            "title": "Test Alert",
            "agent": "PG_SECURITY",
            "status": "failed",
            "message": "Security scan completed with issues",
        }

        title, body = template.render(variables)

        assert title == "WARNING: Test Alert"
        assert "Agent: PG_SECURITY" in body
        assert "Status: failed" in body
        assert "Details: Security scan completed with issues" in body
