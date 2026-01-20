"""
Automation Models - core data structures for automations.

Defines the domain models for:
- Automation definitions (loaded from YAML)
- Triggers (event, time, condition-based)
- Actions (executable operations)
- Scheduled tasks (persistent scheduler state)
- Execution history (audit trail)
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TriggerType(Enum):
    """Types of automation triggers."""

    EVENT = "event"  # Triggered by system events
    TIME = "time"  # Scheduled by cron expression
    CONDITION = "condition"  # Triggered when condition is met


class EventType(Enum):
    """System events that can trigger automations."""

    AGENT_COMPLETE = "agent_complete"
    AGENT_FAILED = "agent_failed"
    CHAIN_COMPLETE = "chain_complete"
    CHAIN_FAILED = "chain_failed"
    REGISTRY_UPDATE = "registry_update"
    ARTIFACT_CREATED = "artifact_created"
    CUSTOM = "custom"


class ActionType(Enum):
    """Types of actions an automation can execute."""

    EXECUTE_AGENT = "execute_agent"
    EXECUTE_CHAIN = "execute_chain"
    SEND_NOTIFICATION = "send_notification"
    CREATE_ARTIFACT = "create_artifact"
    UPDATE_REGISTRY = "update_registry"
    HTTP_REQUEST = "http_request"
    LOG_MESSAGE = "log_message"
    CUSTOM = "custom"


class ActionStatus(Enum):
    """Status of an action execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AutomationStatus(Enum):
    """Status of an automation."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"


@dataclass(frozen=True)
class EventTrigger:
    """Event-based trigger configuration."""

    event_type: EventType
    agent_name: str | None = None  # Filter by specific agent
    chain_name: str | None = None  # Filter by specific chain
    filter_criteria: dict[str, Any] = field(default_factory=dict)

    def matches(self, event: "Event") -> bool:
        """Check if this trigger matches the given event."""
        if self.event_type != event.event_type:
            return False
        if self.agent_name and event.agent_name != self.agent_name:
            return False
        if self.chain_name and event.chain_name != self.chain_name:
            return False
        if self.filter_criteria:
            for key, value in self.filter_criteria.items():
                if event.metadata.get(key) != value:
                    return False
        return True


@dataclass(frozen=True)
class TimeTrigger:
    """Time-based trigger configuration (cron-like)."""

    cron_expression: str
    timezone_str: str = "UTC"

    def __post_init__(self):
        """Validate cron expression format."""
        parts = self.cron_expression.split()
        if len(parts) not in (5, 6):
            raise ValueError(
                f"Invalid cron expression: {self.cron_expression}. "
                "Expected 5 or 6 parts (min hour day month weekday [year])"
            )


@dataclass(frozen=True)
class ConditionTrigger:
    """Condition-based trigger configuration."""

    metric_path: str  # JSONPath to metric value
    operator: str  # "gt", "lt", "gte", "lte", "eq", "ne"
    threshold: float | int | str
    check_interval_seconds: int = 60


class TriggerConfig(BaseModel):
    """Configuration for an automation trigger."""

    type: TriggerType
    event: EventTrigger | None = None
    time: TimeTrigger | None = None
    condition: ConditionTrigger | None = None
    cooldown_seconds: int = Field(default=0, description="Minimum time between triggers")
    max_executions: int | None = Field(default=None, description="Max times to trigger (None = unlimited)")

    model_config = {"extra": "allow"}

    def is_valid(self) -> bool:
        """Validate trigger configuration."""
        match self.type:
            case TriggerType.EVENT:
                return self.event is not None
            case TriggerType.TIME:
                return self.time is not None
            case TriggerType.CONDITION:
                return self.condition is not None
            case _:
                return False


class ActionConfig(BaseModel):
    """Configuration for a single action."""

    type: ActionType
    name: str = Field(default_factory=lambda: f"action_{uuid.uuid4().hex[:8]}")
    parameters: dict[str, Any] = Field(default_factory=dict)
    continue_on_failure: bool = False
    retry_count: int = 0
    retry_delay_seconds: int = 5
    timeout_seconds: int | None = None

    model_config = {"extra": "allow"}

    def get_idempotency_key(self) -> str:
        """Generate a key for idempotency tracking."""
        import hashlib
        import json

        key_data = {
            "type": self.type.value,
            "name": self.name,
            "parameters": self.parameters,
        }
        return hashlib.sha256(json.dumps(key_data, sort_keys=True).encode()).hexdigest()[:16]


class AutomationDefinition(BaseModel):
    """Full definition of an automation."""

    id: str = Field(default_factory=lambda: f"automation_{uuid.uuid4().hex[:12]}")
    name: str
    description: str = ""
    version: str = "1.0"
    status: AutomationStatus = AutomationStatus.ENABLED
    trigger: TriggerConfig
    actions: list[ActionConfig] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    model_config = {"extra": "allow"}

    def is_valid(self) -> bool:
        """Validate automation definition."""
        if not self.name:
            return False
        if not self.trigger.is_valid():
            return False
        if not self.actions:
            return False
        return True


class ScheduledTask(BaseModel):
    """A scheduled automation task."""

    task_id: str = Field(default_factory=lambda: f"task_{uuid.uuid4().hex[:12]}")
    automation_id: str
    automation_name: str
    scheduled_at: str  # ISO timestamp when task should run
    trigger_type: TriggerType
    execution_context: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = Field(default="pending")  # pending, running, completed, failed, cancelled
    last_run: str | None = None
    next_run: str | None = None

    model_config = {"extra": "allow"}

    def is_due(self, now: datetime | None = None) -> bool:
        """Check if this task is due for execution."""
        if self.status != "pending":
            return False

        check_time = now or datetime.now(timezone.utc)
        scheduled_time = datetime.fromisoformat(self.scheduled_at)

        return check_time >= scheduled_time


class Event(BaseModel):
    """A system event that can trigger automations."""

    event_id: str = Field(default_factory=lambda: f"event_{uuid.uuid4().hex[:12]}")
    event_type: EventType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    agent_name: str | None = None
    chain_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    processed_by: list[str] = Field(default_factory=list)  # List of automation IDs that processed this

    model_config = {"extra": "allow"}


class ActionExecution(BaseModel):
    """Record of a single action execution."""

    execution_id: str = Field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    automation_id: str
    automation_run_id: str
    action_name: str
    action_type: ActionType
    status: ActionStatus = ActionStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    execution_time_ms: float | None = None
    input_parameters: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] | None = None
    error_message: str | None = None
    retry_count: int = 0
    idempotency_key: str | None = None

    model_config = {"extra": "allow"}

    def mark_started(self) -> None:
        """Mark action as started."""
        self.status = ActionStatus.RUNNING
        self.started_at = datetime.now(timezone.utc).isoformat()

    def mark_completed(self, output: dict[str, Any] | None = None) -> None:
        """Mark action as completed."""
        self.status = ActionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.output = output or {}

        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.execution_time_ms = (end - start).total_seconds() * 1000

    def mark_failed(self, error: str) -> None:
        """Mark action as failed."""
        self.status = ActionStatus.FAILED
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.error_message = error

        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.execution_time_ms = (end - start).total_seconds() * 1000

    def mark_skipped(self) -> None:
        """Mark action as skipped."""
        self.status = ActionStatus.SKIPPED
        self.completed_at = datetime.now(timezone.utc).isoformat()


class AutomationRun(BaseModel):
    """Record of an automation execution."""

    run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    automation_id: str
    automation_name: str
    trigger_type: TriggerType
    triggered_by: str | None = None  # event_id, schedule, or manual
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    execution_time_ms: float | None = None
    status: ActionStatus = ActionStatus.PENDING
    action_executions: list[ActionExecution] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None

    model_config = {"extra": "allow"}

    def add_action_execution(self, execution: ActionExecution) -> None:
        """Add an action execution record."""
        self.action_executions.append(execution)

    def mark_completed(self) -> None:
        """Mark run as completed."""
        self.status = ActionStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc).isoformat()

        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.execution_time_ms = (end - start).total_seconds() * 1000

    def mark_failed(self, error: str) -> None:
        """Mark run as failed."""
        self.status = ActionStatus.FAILED
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.error_message = error

        if self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.completed_at)
            self.execution_time_ms = (end - start).total_seconds() * 1000

    def to_summary(self) -> dict[str, Any]:
        """Convert to summary for display."""
        return {
            "run_id": self.run_id,
            "automation_name": self.automation_name,
            "trigger_type": self.trigger_type.value,
            "status": self.status.value,
            "started_at": self.started_at,
            "duration_ms": self.execution_time_ms,
            "actions_completed": sum(
                1 for a in self.action_executions if a.status == ActionStatus.COMPLETED
            ),
            "actions_total": len(self.action_executions),
        }


class CooldownTracker(BaseModel):
    """Tracks cooldown periods for automation triggers."""

    automation_id: str
    last_triggered: str | None = None
    trigger_count: int = 0
    cooldown_until: str | None = None

    model_config = {"extra": "allow"}

    def can_trigger(self, cooldown_seconds: int, now: datetime | None = None) -> bool:
        """Check if automation can trigger based on cooldown."""
        check_time = now or datetime.now(timezone.utc)

        if self.cooldown_until:
            cooldown_time = datetime.fromisoformat(self.cooldown_until)
            if check_time < cooldown_time:
                return False

        return True

    def record_trigger(self, cooldown_seconds: int) -> str:
        """Record a trigger and set next cooldown."""
        now = datetime.now(timezone.utc)
        self.last_triggered = now.isoformat()
        self.trigger_count += 1

        if cooldown_seconds > 0:
            from datetime import timedelta
            self.cooldown_until = (now + timedelta(seconds=cooldown_seconds)).isoformat()
        else:
            self.cooldown_until = None

        return self.last_triggered
