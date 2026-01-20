"""
Notification templates for Platform God.

Predefined templates for common notification types including
agent completion, failure alerts, and system status updates.
"""

from platform_god.notifications.models import (
    NotificationTemplate,
    NotificationType,
    NotificationSeverity,
)


# ============================================================================
# AGENT COMPLETION TEMPLATES
# ============================================================================

AGENT_COMPLETION_SUCCESS = NotificationTemplate(
    name="agent_completion_success",
    title_template="Agent Completed: {{agent_name}}",
    body_template="""Agent {{agent_name}} completed successfully.

Run ID: {{run_id}}
Status: {{status}}
Execution Time: {{execution_time_ms}}ms

Output:
{{output_summary}}

Started: {{started_at}}
Completed: {{completed_at}}""",
    notification_type=NotificationType.SUCCESS,
    default_severity=NotificationSeverity.INFO,
    required_vars=["agent_name", "run_id", "status"],
    optional_vars=["execution_time_ms", "output_summary", "started_at", "completed_at"],
)

AGENT_COMPLETION_FAILURE = NotificationTemplate(
    name="agent_completion_failure",
    title_template="Agent Failed: {{agent_name}}",
    body_template="""Agent {{agent_name}} failed during execution.

Run ID: {{run_id}}
Error: {{error_message}}

Started: {{started_at}}
Failed at: {{failed_at}}""",
    notification_type=NotificationType.ERROR,
    default_severity=NotificationSeverity.HIGH,
    required_vars=["agent_name", "run_id", "error_message"],
    optional_vars=["started_at", "failed_at", "stack_trace"],
)

AGENT_TIMEOUT = NotificationTemplate(
    name="agent_timeout",
    title_template="Agent Timeout: {{agent_name}}",
    body_template="""Agent {{agent_name}} exceeded execution timeout.

Run ID: {{run_id}}
Timeout: {{timeout_seconds}}s
Last Activity: {{last_activity_at}}""",
    notification_type=NotificationType.WARNING,
    default_severity=NotificationSeverity.MEDIUM,
    required_vars=["agent_name", "run_id", "timeout_seconds"],
    optional_vars=["last_activity_at"],
)


# ============================================================================
# FAILURE ALERT TEMPLATES
# ============================================================================

CRITICAL_FAILURE = NotificationTemplate(
    name="critical_failure",
    title_template="CRITICAL FAILURE: {{component}}",
    body_template="""A critical failure occurred in {{component}}.

{{description}}

Impact: {{impact}}
Affected Runs: {{affected_runs}}

Action Required: Yes
Severity: CRITICAL""",
    notification_type=NotificationType.ALERT,
    default_severity=NotificationSeverity.CRITICAL,
    required_vars=["component", "description", "impact"],
    optional_vars=["affected_runs", "error_code", "traceback"],
)

GOVERNANCE_FAILURE = NotificationTemplate(
    name="governance_failure",
    title_template="Governance Check Failed: {{rule_id}}",
    body_template="""Governance rule violation detected.

Rule: {{rule_id}}
Project: {{project_name}}
Severity: {{severity}}

Description:
{{description}}

Location: {{location_path}}:{{location_line}}

Finding ID: {{finding_id}}""",
    notification_type=NotificationType.WARNING,
    default_severity=NotificationSeverity.HIGH,
    required_vars=["rule_id", "project_name", "description"],
    optional_vars=["severity", "location_path", "location_line", "finding_id", "cwe_id"],
)

VALIDATION_FAILURE = NotificationTemplate(
    name="validation_failure",
    title_template="Output Validation Failed: {{agent_name}}",
    body_template="""Agent output validation failed.

Agent: {{agent_name}}
Run ID: {{run_id}}
Schema: {{schema_name}}

Validation Errors:
{{validation_errors}}

The output did not conform to the expected schema and was rejected.""",
    notification_type=NotificationType.ERROR,
    default_severity=NotificationSeverity.MEDIUM,
    required_vars=["agent_name", "run_id", "schema_name", "validation_errors"],
    optional_vars=["expected_schema", "actual_output"],
)

RETRY_EXHAUSTED = NotificationTemplate(
    name="retry_exhausted",
    title_template="Retry Exhausted: {{agent_name}} (Run {{run_id}})",
    body_template="""Agent execution failed after {{max_retries}} retry attempts.

Agent: {{agent_name}}
Run ID: {{run_id}}
Final Error: {{final_error}}

Total Attempts: {{total_attempts}}
Total Time: {{total_time_ms}}ms

The operation has been marked as failed and requires manual intervention.""",
    notification_type=NotificationType.ERROR,
    default_severity=NotificationSeverity.HIGH,
    required_vars=["agent_name", "run_id", "max_retries", "final_error"],
    optional_vars=["total_attempts", "total_time_ms"],
)


# ============================================================================
# SYSTEM STATUS TEMPLATES
# ============================================================================

SYSTEM_STARTUP = NotificationTemplate(
    name="system_startup",
    title_template="Platform God System Started",
    body_template="""Platform God system has been initialized.

Version: {{version}}
Environment: {{environment}}
Started at: {{timestamp}}

Registry: {{registry_path}}
Active Projects: {{active_projects}}
Registered Agents: {{registered_agents}}""",
    notification_type=NotificationType.INFO,
    default_severity=NotificationSeverity.INFO,
    required_vars=["version"],
    optional_vars=["environment", "registry_path", "active_projects", "registered_agents", "timestamp"],
)

SYSTEM_SHUTDOWN = NotificationTemplate(
    name="system_shutdown",
    title_template="Platform God System Shutting Down",
    body_template="""Platform God system is shutting down.

Reason: {{reason}}
Uptime: {{uptime_seconds}}s

Runs Completed: {{runs_completed}}
Runs Failed: {{runs_failed}}
Notifications Sent: {{notifications_sent}}""",
    notification_type=NotificationType.INFO,
    default_severity=NotificationSeverity.INFO,
    required_vars=["reason"],
    optional_vars=["uptime_seconds", "runs_completed", "runs_failed", "notifications_sent"],
)

RESOURCE_WARNING = NotificationTemplate(
    name="resource_warning",
    title_template="Resource Warning: {{resource_type}}",
    body_template="""System resource threshold exceeded.

Resource: {{resource_type}}
Current: {{current_value}}%
Threshold: {{threshold_value}}%

{{recommendation}}""",
    notification_type=NotificationType.WARNING,
    default_severity=NotificationSeverity.MEDIUM,
    required_vars=["resource_type", "current_value", "threshold_value"],
    optional_vars=["recommendation", "peak_value", "average_value"],
)

QUEUE_BACKLOG = NotificationTemplate(
    name="queue_backlog",
    title_template="Notification Queue Backlog Warning",
    body_template="""The notification queue has exceeded the warning threshold.

Queue Size: {{queue_size}}
Threshold: {{threshold}}
Oldest Pending: {{oldest_pending_age}}

Consider scaling up notification workers or investigating delivery failures.""",
    notification_type=NotificationType.WARNING,
    default_severity=NotificationSeverity.LOW,
    required_vars=["queue_size", "threshold"],
    optional_vars=["oldest_pending_age", "failed_deliveries"],
)


# ============================================================================
# FINDING TEMPLATES
# ============================================================================

NEW_CRITICAL_FINDING = NotificationTemplate(
    name="new_critical_finding",
    title_template="CRITICAL Finding: {{title}}",
    body_template="""A new critical security finding has been detected.

Project: {{project_name}}
Category: {{category}}
Title: {{title}}

Description:
{{description}}

Location: {{location_path}}:{{location_line}}
Finding ID: {{finding_id}}
Confidence: {{confidence}}

IMMEDIATE ACTION REQUIRED""",
    notification_type=NotificationType.ALERT,
    default_severity=NotificationSeverity.CRITICAL,
    required_vars=["project_name", "category", "title", "description"],
    optional_vars=["location_path", "location_line", "finding_id", "confidence", "cwe_id", "rule_id"],
)

FINDING_RESOLVED = NotificationTemplate(
    name="finding_resolved",
    title_template="Finding Resolved: {{title}}",
    body_template="""A security finding has been marked as resolved.

Finding ID: {{finding_id}}
Title: {{title}}
Status: {{status}}

Resolution:
{{mitigation}}

Resolved by: {{resolved_by}}
Resolved at: {{resolved_at}}""",
    notification_type=NotificationType.SUCCESS,
    default_severity=NotificationSeverity.INFO,
    required_vars=["finding_id", "title", "status"],
    optional_vars=["mitigation", "resolved_by", "resolved_at"],
)

FINDING_SUPPRESSED = NotificationTemplate(
    name="finding_suppressed",
    title_template="Finding Suppressed: {{title}}",
    body_template="""A security finding has been suppressed.

Finding ID: {{finding_id}}
Title: {{title}}
Reason: {{suppress_reason}}

Suppressed by: {{suppressed_by}}
Suppressed at: {{suppressed_at}}""",
    notification_type=NotificationType.INFO,
    default_severity=NotificationSeverity.INFO,
    required_vars=["finding_id", "title", "suppress_reason"],
    optional_vars=["suppressed_by", "suppressed_at"],
)


# ============================================================================
# RUN TEMPLATES
# ============================================================================

RUN_STARTED = NotificationTemplate(
    name="run_started",
    title_template="Run Started: {{run_id}}",
    body_template="""A new {{run_type}} run has been initiated.

Run ID: {{run_id}}
Type: {{run_type}}
Initiated by: {{initiated_by}}

Targets: {{target_count}}
Agents: {{agent_count}}

Started at: {{started_at}}""",
    notification_type=NotificationType.INFO,
    default_severity=NotificationSeverity.INFO,
    required_vars=["run_id", "run_type"],
    optional_vars=["initiated_by", "target_count", "agent_count", "started_at", "parameters"],
)

RUN_COMPLETED = NotificationTemplate(
    name="run_completed",
    title_template="Run Completed: {{run_id}}",
    body_template="""Run completed successfully.

Run ID: {{run_id}}
Type: {{run_type}}
Status: {{status}}

Duration: {{duration_seconds}}s
Agents Run: {{agents_completed}}/{{agents_total}}
Findings: {{finding_count}}
Artifacts: {{artifact_count}}

Completed at: {{completed_at}}""",
    notification_type=NotificationType.SUCCESS,
    default_severity=NotificationSeverity.INFO,
    required_vars=["run_id", "run_type", "status"],
    optional_vars=["duration_seconds", "agents_completed", "agents_total", "finding_count", "artifact_count", "completed_at"],
)

RUN_FAILED = NotificationTemplate(
    name="run_failed",
    title_template="Run Failed: {{run_id}}",
    body_template="""Run execution failed.

Run ID: {{run_id}}
Type: {{run_type}}
Error: {{error_message}}

Agents Completed: {{agents_completed}}/{{agents_total}}
Failed at: {{failed_at}}""",
    notification_type=NotificationType.ERROR,
    default_severity=NotificationSeverity.HIGH,
    required_vars=["run_id", "run_type", "error_message"],
    optional_vars=["agents_completed", "agents_total", "failed_at", "stack_trace"],
)


# ============================================================================
# ARTIFACT TEMPLATES
# ============================================================================

ARTIFACT_CREATED = NotificationTemplate(
    name="artifact_created",
    title_template="Artifact Created: {{title}}",
    body_template="""A new artifact has been generated.

Artifact ID: {{artifact_id}}
Title: {{title}}
Type: {{artifact_type}}

Size: {{size_bytes}} bytes
Storage: {{storage_path}}

Run: {{run_id}}
Agent: {{agent_name}}""",
    notification_type=NotificationType.INFO,
    default_severity=NotificationSeverity.INFO,
    required_vars=["artifact_id", "title", "artifact_type"],
    optional_vars=["size_bytes", "storage_path", "run_id", "agent_name", "mime_type"],
)


# ============================================================================
# TEMPLATE REGISTRY
# ============================================================================

TEMPLATES: dict[str, NotificationTemplate] = {
    # Agent completion templates
    "agent_completion_success": AGENT_COMPLETION_SUCCESS,
    "agent_completion_failure": AGENT_COMPLETION_FAILURE,
    "agent_timeout": AGENT_TIMEOUT,
    # Failure alert templates
    "critical_failure": CRITICAL_FAILURE,
    "governance_failure": GOVERNANCE_FAILURE,
    "validation_failure": VALIDATION_FAILURE,
    "retry_exhausted": RETRY_EXHAUSTED,
    # System status templates
    "system_startup": SYSTEM_STARTUP,
    "system_shutdown": SYSTEM_SHUTDOWN,
    "resource_warning": RESOURCE_WARNING,
    "queue_backlog": QUEUE_BACKLOG,
    # Finding templates
    "new_critical_finding": NEW_CRITICAL_FINDING,
    "finding_resolved": FINDING_RESOLVED,
    "finding_suppressed": FINDING_SUPPRESSED,
    # Run templates
    "run_started": RUN_STARTED,
    "run_completed": RUN_COMPLETED,
    "run_failed": RUN_FAILED,
    # Artifact templates
    "artifact_created": ARTIFACT_CREATED,
}


def get_template(name: str) -> NotificationTemplate | None:
    """Get a template by name."""
    return TEMPLATES.get(name)


def render_template(name: str, variables: dict[str, Any]) -> tuple[str, str] | None:
    """
    Render a template by name with provided variables.

    Returns:
        Tuple of (rendered_title, rendered_body) or None if template not found.
    """
    template = get_template(name)
    if template is None:
        return None
    return template.render(variables)


def list_templates() -> list[str]:
    """List all available template names."""
    return list(TEMPLATES.keys())


def register_template(template: NotificationTemplate) -> None:
    """Register a custom template."""
    TEMPLATES[template.name] = template


# Type hints for module
