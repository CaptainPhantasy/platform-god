"""
Platform God Notifications Module.

Provides notification delivery, routing, and tracking for
Platform God agent system.

Usage:
    from platform_god.notifications import (
        send,
        send_from_template,
        get_dispatcher,
        NotificationType,
        NotificationSeverity,
    )

    # Send a simple notification
    send(
        title="Agent Completed",
        message="Analysis agent finished successfully",
        severity=NotificationSeverity.INFO,
    )

    # Send from template
    send_from_template(
        "agent_completion_success",
        variables={
            "agent_name": "security_scanner",
            "run_id": "run-123",
            "status": "completed",
        }
    )
"""

from platform_god.notifications.models import (
    # Core models
    Notification,
    NotificationBatch,
    NotificationChannel,
    NotificationTemplate,
    NotificationFilter,
    DeliveryResult,

    # Enums
    NotificationType,
    NotificationSeverity,
    NotificationChannelType,
    NotificationStatus,
    NotificationPriority,
)

from platform_god.notifications.templates import (
    # Templates
    TEMPLATES,
    get_template,
    render_template,
    list_templates,
    register_template,

    # Named templates
    AGENT_COMPLETION_SUCCESS,
    AGENT_COMPLETION_FAILURE,
    AGENT_TIMEOUT,
    CRITICAL_FAILURE,
    GOVERNANCE_FAILURE,
    VALIDATION_FAILURE,
    RETRY_EXHAUSTED,
    SYSTEM_STARTUP,
    SYSTEM_SHUTDOWN,
    RESOURCE_WARNING,
    QUEUE_BACKLOG,
    NEW_CRITICAL_FINDING,
    FINDING_RESOLVED,
    FINDING_SUPPRESSED,
    RUN_STARTED,
    RUN_COMPLETED,
    RUN_FAILED,
    ARTIFACT_CREATED,
)

from platform_god.notifications.dispatcher import (
    # Dispatcher
    NotificationDispatcher,
    DispatcherStatus,
    DispatcherStats,
    get_dispatcher,
    shutdown_dispatcher,
)

from platform_god.notifications.channels import (
    # Channels
    BaseChannel,
    WebhookChannel,
    ConsoleChannel,
    EmailChannel,
    SlackChannel,
    get_channel,
    register_channel,
)

__all__ = [
    # Core models
    "Notification",
    "NotificationBatch",
    "NotificationChannel",
    "NotificationTemplate",
    "NotificationFilter",
    "DeliveryResult",

    # Enums
    "NotificationType",
    "NotificationSeverity",
    "NotificationChannelType",
    "NotificationStatus",
    "NotificationPriority",

    # Templates
    "TEMPLATES",
    "get_template",
    "render_template",
    "list_templates",
    "register_template",

    # Named templates
    "AGENT_COMPLETION_SUCCESS",
    "AGENT_COMPLETION_FAILURE",
    "AGENT_TIMEOUT",
    "CRITICAL_FAILURE",
    "GOVERNANCE_FAILURE",
    "VALIDATION_FAILURE",
    "RETRY_EXHAUSTED",
    "SYSTEM_STARTUP",
    "SYSTEM_SHUTDOWN",
    "RESOURCE_WARNING",
    "QUEUE_BACKLOG",
    "NEW_CRITICAL_FINDING",
    "FINDING_RESOLVED",
    "FINDING_SUPPRESSED",
    "RUN_STARTED",
    "RUN_COMPLETED",
    "RUN_FAILED",
    "ARTIFACT_CREATED",

    # Dispatcher
    "NotificationDispatcher",
    "DispatcherStatus",
    "DispatcherStats",
    "get_dispatcher",
    "shutdown_dispatcher",

    # Channels
    "BaseChannel",
    "WebhookChannel",
    "ConsoleChannel",
    "EmailChannel",
    "SlackChannel",
    "get_channel",
    "register_channel",
]

# Convenience functions
def send(
    title: str,
    message: str,
    notification_type: NotificationType = NotificationType.INFO,
    severity: NotificationSeverity = NotificationSeverity.INFO,
    channels: list[str] | None = None,
    **kwargs
) -> str:
    """
    Send a notification through the global dispatcher.

    Args:
        title: Notification title
        message: Notification message body
        notification_type: Type of notification
        severity: Severity level
        channels: List of channel names (default: all enabled)
        **kwargs: Additional notification fields (run_id, project_id, etc.)

    Returns:
        Notification ID
    """
    dispatcher = get_dispatcher()
    return dispatcher.send(
        title=title,
        message=message,
        notification_type=notification_type,
        severity=severity,
        channels=channels,
        **kwargs
    )


def send_from_template(
    template_name: str,
    variables: dict,
    channels: list[str] | None = None,
    **kwargs
) -> str | None:
    """
    Send a notification from a registered template.

    Args:
        template_name: Name of the template to use
        variables: Dictionary of template variables
        channels: List of channel names (default: all enabled)
        **kwargs: Additional notification fields

    Returns:
        Notification ID or None if template not found/error
    """
    dispatcher = get_dispatcher()
    return dispatcher.send_from_template(
        template_name=template_name,
        variables=variables,
        channels=channels,
        **kwargs
    )


def notify_agent_completion(
    agent_name: str,
    run_id: str,
    status: str,
    execution_time_ms: int | None = None,
    output_summary: str | None = None,
    error_message: str | None = None,
) -> str | None:
    """
    Send a notification for agent completion.

    Args:
        agent_name: Name of the agent
        run_id: Run identifier
        status: Completion status (completed, failed, etc.)
        execution_time_ms: Execution time in milliseconds
        output_summary: Summary of agent output
        error_message: Error message if failed

    Returns:
        Notification ID or None
    """
    if status == "completed" or status == "success":
        template_name = "agent_completion_success"
        variables = {
            "agent_name": agent_name,
            "run_id": run_id,
            "status": status,
            "execution_time_ms": execution_time_ms,
            "output_summary": output_summary,
        }
    else:
        template_name = "agent_completion_failure"
        variables = {
            "agent_name": agent_name,
            "run_id": run_id,
            "error_message": error_message or "Unknown error",
        }

    return send_from_template(
        template_name=template_name,
        variables=variables,
        agent_name=agent_name,
        run_id=run_id,
    )


def notify_finding(
    project_name: str,
    category: str,
    title: str,
    description: str,
    severity: str = "high",
    location_path: str | None = None,
    location_line: int | None = None,
    finding_id: str | None = None,
) -> str:
    """
    Send a notification for a new security finding.

    Args:
        project_name: Name of the project
        category: Finding category
        title: Finding title
        description: Finding description
        severity: Severity level (critical, high, medium, low)
        location_path: File path of finding
        location_line: Line number of finding
        finding_id: Finding identifier

    Returns:
        Notification ID
    """
    if severity.lower() == "critical":
        template_name = "new_critical_finding"
        from platform_god.notifications.models import NotificationSeverity
        notif_severity = NotificationSeverity.CRITICAL
    else:
        template_name = "governance_failure"
        from platform_god.notifications.models import NotificationSeverity
        severity_map = {
            "high": NotificationSeverity.HIGH,
            "medium": NotificationSeverity.MEDIUM,
            "low": NotificationSeverity.LOW,
        }
        notif_severity = severity_map.get(severity.lower(), NotificationSeverity.MEDIUM)

    variables = {
        "project_name": project_name,
        "category": category,
        "title": title,
        "description": description,
        "severity": severity,
        "location_path": location_path,
        "location_line": location_line,
        "finding_id": finding_id,
    }

    return send_from_template(
        template_name=template_name,
        variables=variables,
    ) or send(
        title=f"{severity.upper()} Finding: {title}",
        message=description,
        severity=notif_severity,
    )


def get_stats() -> DispatcherStats:
    """Get current dispatcher statistics."""
    dispatcher = get_dispatcher()
    return dispatcher.stats
