"""
Audit data models for Platform God.

Defines the core types for audit events, queries, and reports.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AuditLevel(str, Enum):
    """Audit log severity levels."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditEventType(str, Enum):
    """Standard audit event types."""

    # System events
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    SYSTEM_ERROR = "system_error"

    # Agent events
    AGENT_START = "agent_start"
    AGENT_COMPLETE = "agent_complete"
    AGENT_FAIL = "agent_fail"
    AGENT_SKIP = "agent_skip"

    # Registry events
    ENTITY_REGISTER = "entity_register"
    ENTITY_UPDATE = "entity_update"
    ENTITY_DEREGISTER = "entity_deregister"
    ENTITY_READ = "entity_read"

    # Governance events
    GOVERNANCE_RUN_START = "governance_run_start"
    GOVERNANCE_RUN_COMPLETE = "governance_run_complete"
    POLICY_CHECK = "policy_check"
    POLICY_VIOLATION = "policy_violation"
    POLICY_EXCEPTION = "policy_exception"

    # Security events
    AUTH_ATTEMPT = "auth_attempt"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    PERMISSION_DENIED = "permission_denied"
    UNAUTHORIZED_ACCESS = "unauthorized_access"

    # Write events
    WRITE_REQUEST = "write_request"
    WRITE_APPROVED = "write_approved"
    WRITE_DENIED = "write_denied"
    WRITE_EXECUTED = "write_executed"

    # Notification events
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_FAILED = "notification_failed"

    # Custom events
    CUSTOM = "custom"


class AuditResult(str, Enum):
    """Result status of audited operations."""

    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"


def _utc_now() -> str:
    """Return current UTC timestamp as ISO8601 string."""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class AuditEvent(BaseModel):
    """
    A single audit log entry.

    Immutable record of a system event for compliance and forensics.
    """

    # Core identification
    event_id: str = Field(default_factory=lambda: f"evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}")
    timestamp: str = Field(default_factory=_utc_now)
    event_type: AuditEventType = Field(description="Type of event being logged")

    # Who and what
    actor: str = Field(default="system", description="User, agent, or system that performed the action")
    action: str = Field(description="Human-readable description of the action")
    target: str | None = Field(default=None, description="Object or resource affected")

    # Outcome
    result: AuditResult = Field(default=AuditResult.UNKNOWN, description="Operation result")
    severity: AuditLevel = Field(default=AuditLevel.INFO, description="Log severity level")

    # Additional context
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional event context")
    error_message: str | None = Field(default=None, description="Error details if operation failed")

    # Traceability
    correlation_id: str | None = Field(default=None, description="Correlates related events")
    parent_event_id: str | None = Field(default=None, description="Parent event for nested operations")
    run_id: str | None = Field(default=None, description="Associated run identifier")

    # Integrity
    checksum: str | None = Field(default=None, description="SHA256 hash for integrity verification")

    model_config = {"frozen": True}  # Immutable

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of event data for integrity verification."""
        import hashlib
        import json

        # Create canonical representation
        data = {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "action": self.action,
            "target": self.target,
            "result": self.result.value,
            "metadata": self.metadata,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def with_checksum(self) -> "AuditEvent":
        """Return a new event with checksum computed."""
        return self.model_copy(update={"checksum": self.compute_checksum()})

    def to_log_line(self) -> str:
        """Convert to JSONL string for file storage."""

        event = self.with_checksum()
        return event.model_dump_json(exclude_none=True)


class AuditQuery(BaseModel):
    """Query parameters for searching audit logs."""

    # Time range
    start_time: str | None = Field(default=None, description="ISO8601 start timestamp")
    end_time: str | None = Field(default=None, description="ISO8601 end timestamp")

    # Filters
    event_types: list[AuditEventType] | None = Field(default=None, description="Filter by event types")
    actors: list[str] | None = Field(default=None, description="Filter by actors")
    targets: list[str] | None = Field(default=None, description="Filter by targets")
    severities: list[AuditLevel] | None = Field(default=None, description="Filter by severity levels")
    results: list[AuditResult] | None = Field(default=None, description="Filter by result status")

    # Text search
    search_query: str | None = Field(default=None, description="Full-text search in action and metadata")

    # Traceability
    correlation_id: str | None = Field(default=None, description="Filter by correlation ID")
    run_id: str | None = Field(default=None, description="Filter by run ID")

    # Pagination
    limit: int = Field(default=1000, ge=1, le=100000, description="Maximum results")
    offset: int = Field(default=0, ge=0, description="Results to skip")

    # Sorting
    sort_by: str = Field(default="timestamp", description="Field to sort by")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort direction")

    def has_filters(self) -> bool:
        """Check if query has any active filters."""
        return bool(
            self.start_time
            or self.end_time
            or self.event_types
            or self.actors
            or self.targets
            or self.severities
            or self.results
            or self.search_query
            or self.correlation_id
            or self.run_id
        )


@dataclass
class AuditStats:
    """Statistical summary of audit events."""

    total_events: int = 0
    by_event_type: dict[str, int] = field(default_factory=dict)
    by_severity: dict[str, int] = field(default_factory=dict)
    by_actor: dict[str, int] = field(default_factory=dict)
    by_result: dict[str, int] = field(default_factory=dict)
    unique_targets: int = 0
    time_range: tuple[str, str] | None = None  # (earliest, latest)

    def add_event(self, event: AuditEvent) -> None:
        """Update stats with a new event."""
        self.total_events += 1

        # Count by type
        evt_type = event.event_type.value
        self.by_event_type[evt_type] = self.by_event_type.get(evt_type, 0) + 1

        # Count by severity
        sev = event.severity.value
        self.by_severity[sev] = self.by_severity.get(sev, 0) + 1

        # Count by actor
        self.by_actor[event.actor] = self.by_actor.get(event.actor, 0) + 1

        # Count by result
        res = event.result.value
        self.by_result[res] = self.by_result.get(res, 0) + 1

        # Update time range
        if self.time_range is None:
            self.time_range = (event.timestamp, event.timestamp)
        else:
            start, end = self.time_range
            if event.timestamp < start:
                self.time_range = (event.timestamp, end)
            if event.timestamp > end:
                self.time_range = (start, event.timestamp)


class AuditReport(BaseModel):
    """Generated audit report with statistics and filtered events."""

    report_id: str = Field(description="Unique report identifier")
    generated_at: str = Field(default_factory=_utc_now, description="Report generation timestamp")
    query: AuditQuery = Field(description="Query used to generate this report")

    # Statistics
    stats: AuditStats = Field(description="Statistical summary of matched events")
    total_matching: int = Field(description="Total events matching the query")

    # Events
    events: list[AuditEvent] = Field(default_factory=list, description="Matched audit events")

    # Report metadata
    title: str = Field(default="Audit Report", description="Report title")
    description: str | None = Field(default=None, description="Report description")
    duration_ms: float | None = Field(default=None, description="Report generation time")

    def add_event(self, event: AuditEvent) -> None:
        """Add an event to the report and update stats."""
        self.events.append(event)
        self.stats.add_event(event)
        self.total_matching = len(self.events)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for export."""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at,
            "query": self.query.model_dump(exclude_none=True),
            "stats": {
                "total_events": self.stats.total_events,
                "by_event_type": self.stats.by_event_type,
                "by_severity": self.stats.by_severity,
                "by_actor": self.stats.by_actor,
                "by_result": self.stats.by_result,
                "unique_targets": self.stats.unique_targets,
                "time_range": list(self.stats.time_range) if self.stats.time_range else None,
            },
            "total_matching": self.total_matching,
            "events": [e.model_dump(exclude_none=True) for e in self.events],
        }


class ExportFormat(str, Enum):
    """Supported export formats for audit reports."""

    JSON = "json"
    CSV = "csv"
    """Export format for audit reports."""
