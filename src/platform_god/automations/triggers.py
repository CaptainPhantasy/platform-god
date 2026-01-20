"""
Automation Trigger Engine - evaluates and fires automation triggers.

Supports:
- Event-based triggers (agent completion, failures, registry updates)
- Time-based triggers (cron-like scheduling)
- Condition-based triggers (thresholds, metrics)

The trigger engine maintains the event bus, evaluates conditions,
and coordinates with the scheduler for time-based triggers.
"""

import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from platform_god.automations.models import (
    AutomationDefinition,
    AutomationRun,
    AutomationStatus,
    ConditionTrigger,
    CooldownTracker,
    Event,
    EventType,
    ScheduledTask,
    TriggerType,
)
from platform_god.core.models import AgentResult


# Type alias for trigger fired callback
TriggerFiredCallback = Callable[["TriggerFired"], None]


class TriggerEvaluationResult(Enum):
    """Result of trigger evaluation."""

    FIRED = "fired"  # Trigger conditions met, should execute
    WAITING = "waiting"  # Not yet time or conditions not met
    COOLDOWN = "cooldown"  # In cooldown period
    DISABLED = "disabled"  # Automation is disabled
    MAX_REACHED = "max_reached"  # Maximum executions reached


@dataclass
class TriggerFired:
    """Notification that a trigger has fired."""

    automation_id: str
    automation_name: str
    trigger_type: TriggerType
    triggered_at: datetime
    context: dict[str, Any] = field(default_factory=dict)
    event_id: str | None = None


@dataclass
class TriggerContext:
    """Context passed to trigger handlers."""

    automation: AutomationDefinition
    event: Event | None = None
    scheduled_task: ScheduledTask | None = None
    previous_runs: list[AutomationRun] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


class EventListener:
    """Listens for system events and dispatches to automations."""

    def __init__(self, event_queue: queue.Queue):
        """Initialize event listener with output queue."""
        self._event_queue = event_queue
        self._running = False
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start the event listener."""
        with self._lock:
            self._running = True

    def stop(self) -> None:
        """Stop the event listener."""
        with self._lock:
            self._running = False

    def is_running(self) -> bool:
        """Check if listener is running."""
        with self._lock:
            return self._running

    def publish_agent_complete(self, result: AgentResult) -> Event:
        """Publish an agent completion event."""
        event = Event(
            event_type=EventType.AGENT_COMPLETE,
            agent_name=result.agent_name,
            metadata={
                "agent_class": result.agent_class.value,
                "status": result.status.value,
                "execution_time_ms": result.execution_time_ms,
                "has_error": result.error_message is not None,
                "output_size": len(str(result.output_data)) if result.output_data else 0,
            },
        )
        self._event_queue.put(event)
        return event

    def publish_agent_failed(self, result: AgentResult) -> Event:
        """Publish an agent failure event."""
        event = Event(
            event_type=EventType.AGENT_FAILED,
            agent_name=result.agent_name,
            metadata={
                "agent_class": result.agent_class.value,
                "error": result.error_message,
                "execution_time_ms": result.execution_time_ms,
            },
        )
        self._event_queue.put(event)
        return event

    def publish_chain_complete(
        self,
        chain_name: str,
        status: str,
        completed_steps: int,
        total_steps: int,
        execution_time_ms: float,
    ) -> Event:
        """Publish a chain completion event."""
        event = Event(
            event_type=EventType.CHAIN_COMPLETE,
            chain_name=chain_name,
            metadata={
                "status": status,
                "completed_steps": completed_steps,
                "total_steps": total_steps,
                "execution_time_ms": execution_time_ms,
            },
        )
        self._event_queue.put(event)
        return event

    def publish_chain_failed(
        self,
        chain_name: str,
        error: str | None = None,
    ) -> Event:
        """Publish a chain failure event."""
        event = Event(
            event_type=EventType.CHAIN_FAILED,
            chain_name=chain_name,
            metadata={"error": error},
        )
        self._event_queue.put(event)
        return event

    def publish_registry_update(
        self,
        entity_type: str,
        entity_id: str,
        operation: str,
    ) -> Event:
        """Publish a registry update event."""
        event = Event(
            event_type=EventType.REGISTRY_UPDATE,
            metadata={
                "entity_type": entity_type,
                "entity_id": entity_id,
                "operation": operation,
            },
        )
        self._event_queue.put(event)
        return event

    def publish_artifact_created(
        self,
        artifact_path: str,
        artifact_type: str,
    ) -> Event:
        """Publish an artifact creation event."""
        event = Event(
            event_type=EventType.ARTIFACT_CREATED,
            metadata={
                "artifact_path": artifact_path,
                "artifact_type": artifact_type,
            },
        )
        self._event_queue.put(event)
        return event

    def publish_custom(
        self,
        custom_type: str,
        metadata: dict[str, Any],
    ) -> Event:
        """Publish a custom event."""
        event = Event(
            event_type=EventType.CUSTOM,
            metadata={
                "custom_type": custom_type,
                **metadata,
            },
        )
        self._event_queue.put(event)
        return event


class ConditionEvaluator:
    """Evaluates condition-based triggers."""

    def __init__(self, metrics_provider: Callable[[], dict[str, Any]] | None = None):
        """Initialize with optional metrics provider."""
        self._metrics_provider = metrics_provider

    def get_current_metrics(self) -> dict[str, Any]:
        """Get current metrics values."""
        if self._metrics_provider:
            return self._metrics_provider()
        return {}

    def evaluate(self, trigger: ConditionTrigger, context: dict[str, Any]) -> bool:
        """
        Evaluate a condition trigger.

        Args:
            trigger: The condition trigger to evaluate
            context: Current execution context with metric values

        Returns:
            True if condition is met (should trigger)
        """
        # Resolve metric value using JSONPath-like syntax
        value = self._resolve_value(trigger.metric_path, context)

        # Apply operator
        match trigger.operator:
            case "gt":
                return self._compare(value, trigger.threshold, lambda a, b: a > b)
            case "lt":
                return self._compare(value, trigger.threshold, lambda a, b: a < b)
            case "gte":
                return self._compare(value, trigger.threshold, lambda a, b: a >= b)
            case "lte":
                return self._compare(value, trigger.threshold, lambda a, b: a <= b)
            case "eq":
                return value == trigger.threshold
            case "ne":
                return value != trigger.threshold
            case "contains":
                return trigger.threshold in str(value) if value else False
            case "exists":
                return value is not None
            case _:
                return False

    def _resolve_value(self, path: str, context: dict[str, Any]) -> Any:
        """Resolve a JSONPath-like expression to a value."""
        # Support simple dot notation: "metrics.health_score"
        # or dollar notation: "$.metrics.health_score"
        path = path.lstrip("$.")

        parts = path.split(".")
        value = context

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            elif isinstance(value, list) and part.isdigit():
                index = int(part)
                value = value[index] if 0 <= index < len(value) else None
            else:
                return None

        return value

    def _compare(self, a: Any, b: Any, op: Callable[[Any, Any], bool]) -> bool:
        """Safely compare two values."""
        try:
            return op(a, b)
        except (TypeError, ValueError):
            return False


class TriggerEngine:
    """
    Main trigger evaluation and firing engine.

    Coordinates:
    - Event listening and matching to event triggers
    - Time-based trigger evaluation
    - Condition evaluation
    - Cooldown tracking
    - Trigger fire notification
    """

    def __init__(
        self,
        automations_dir: Path | None = None,
        state_dir: Path | None = None,
    ):
        """Initialize trigger engine."""
        self._automations_dir = automations_dir or Path("var/automations")
        self._state_dir = state_dir or Path("var/automations/state")
        self._state_dir.mkdir(parents=True, exist_ok=True)

        # Event processing
        self._event_queue: queue.Queue[Event] = queue.Queue()
        self._event_listener = EventListener(self._event_queue)
        self._condition_evaluator = ConditionEvaluator()

        # State
        self._cooldown_trackers: dict[str, CooldownTracker] = {}
        self._trigger_counts: dict[str, int] = {}
        self._running = False
        self._lock = threading.Lock()
        self._shutdown_event = threading.Event()

        # Callbacks
        self._on_trigger_fired: list[Callable[[TriggerFired], None]] = []

    @property
    def event_listener(self) -> EventListener:
        """Get the event listener for publishing events."""
        return self._event_listener

    def add_trigger_callback(self, callback: Callable[[TriggerFired], None]) -> None:
        """Add a callback for when a trigger fires."""
        self._on_trigger_fired.append(callback)

    def start(self) -> None:
        """Start the trigger engine."""
        with self._lock:
            self._running = True
            self._event_listener.start()
            self._shutdown_event.clear()

    def stop(self, graceful: bool = True) -> None:
        """Stop the trigger engine."""
        with self._lock:
            self._running = False
            self._event_listener.stop()

        if graceful:
            # Drain remaining events
            self._drain_events()

        self._shutdown_event.set()

    def is_running(self) -> bool:
        """Check if engine is running."""
        with self._lock:
            return self._running

    def register_automation(self, automation: AutomationDefinition) -> None:
        """Register an automation for trigger evaluation."""
        automation_id = automation.id

        # Initialize cooldown tracker
        if automation_id not in self._cooldown_trackers:
            self._cooldown_trackers[automation_id] = CooldownTracker(
                automation_id=automation_id
            )

    def unregister_automation(self, automation_id: str) -> None:
        """Unregister an automation."""
        self._cooldown_trackers.pop(automation_id, None)
        self._trigger_counts.pop(automation_id, None)

    def evaluate_event_trigger(
        self,
        automation: AutomationDefinition,
        event: Event,
    ) -> TriggerEvaluationResult:
        """Evaluate if an event trigger should fire."""
        if automation.status != AutomationStatus.ENABLED:
            return TriggerEvaluationResult.DISABLED

        trigger = automation.trigger
        if trigger.type != TriggerType.EVENT or not trigger.event:
            return TriggerEvaluationResult.WAITING

        # Check cooldown
        cooldown_tracker = self._cooldown_trackers.get(automation.id)
        if not cooldown_tracker:
            cooldown_tracker = CooldownTracker(automation_id=automation.id)
            self._cooldown_trackers[automation.id] = cooldown_tracker

        if not cooldown_tracker.can_trigger(trigger.cooldown_seconds):
            return TriggerEvaluationResult.COOLDOWN

        # Check max executions
        if trigger.max_executions is not None:
            trigger_count = cooldown_tracker.trigger_count
            if trigger_count >= trigger.max_executions:
                return TriggerEvaluationResult.MAX_REACHED

        # Check if event matches trigger
        if trigger.event.matches(event):
            # Check if already processed by this automation
            if automation.id in event.processed_by:
                return TriggerEvaluationResult.WAITING

            return TriggerEvaluationResult.FIRED

        return TriggerEvaluationResult.WAITING

    def evaluate_time_trigger(
        self,
        automation: AutomationDefinition,
        now: datetime | None = None,
    ) -> TriggerEvaluationResult:
        """Evaluate if a time trigger should fire."""
        if automation.status != AutomationStatus.ENABLED:
            return TriggerEvaluationResult.DISABLED

        trigger = automation.trigger
        if trigger.type != TriggerType.TIME or not trigger.time:
            return TriggerEvaluationResult.WAITING

        # Check cooldown
        cooldown_tracker = self._cooldown_trackers.get(automation.id)
        if not cooldown_tracker:
            cooldown_tracker = CooldownTracker(automation_id=automation.id)
            self._cooldown_trackers[automation.id] = cooldown_tracker

        if not cooldown_tracker.can_trigger(trigger.cooldown_seconds, now):
            return TriggerEvaluationResult.COOLDOWN

        # Check max executions
        if trigger.max_executions is not None:
            trigger_count = cooldown_tracker.trigger_count
            if trigger_count >= trigger.max_executions:
                return TriggerEvaluationResult.MAX_REACHED

        # Time triggers are evaluated by the scheduler
        # This just checks if we're in cooldown
        return TriggerEvaluationResult.WAITING

    def evaluate_condition_trigger(
        self,
        automation: AutomationDefinition,
        metrics: dict[str, Any],
    ) -> TriggerEvaluationResult:
        """Evaluate if a condition trigger should fire."""
        if automation.status != AutomationStatus.ENABLED:
            return TriggerEvaluationResult.DISABLED

        trigger = automation.trigger
        if trigger.type != TriggerType.CONDITION or not trigger.condition:
            return TriggerEvaluationResult.WAITING

        # Check cooldown
        cooldown_tracker = self._cooldown_trackers.get(automation.id)
        if not cooldown_tracker:
            cooldown_tracker = CooldownTracker(automation_id=automation.id)
            self._cooldown_trackers[automation.id] = cooldown_tracker

        if not cooldown_tracker.can_trigger(trigger.cooldown_seconds):
            return TriggerEvaluationResult.COOLDOWN

        # Check max executions
        if trigger.max_executions is not None:
            trigger_count = cooldown_tracker.trigger_count
            if trigger_count >= trigger.max_executions:
                return TriggerEvaluationResult.MAX_REACHED

        # Evaluate condition
        context = {"metrics": metrics, "context": {}}
        if self._condition_evaluator.evaluate(trigger.condition, context):
            return TriggerEvaluationResult.FIRED

        return TriggerEvaluationResult.WAITING

    def fire_trigger(
        self,
        automation: AutomationDefinition,
        trigger_type: TriggerType,
        event: Event | None = None,
        context: dict[str, Any] | None = None,
    ) -> TriggerFired:
        """Fire a trigger and notify callbacks."""
        trigger = automation.trigger

        # Record the trigger
        cooldown_tracker = self._cooldown_trackers.get(automation.id)
        if cooldown_tracker:
            cooldown_tracker.record_trigger(trigger.cooldown_seconds)

        # Create fired notification
        fired = TriggerFired(
            automation_id=automation.id,
            automation_name=automation.name,
            trigger_type=trigger_type,
            triggered_at=datetime.now(timezone.utc),
            context=context or {},
            event_id=event.event_id if event else None,
        )

        # Mark event as processed
        if event and automation.id not in event.processed_by:
            event.processed_by.append(automation.id)

        # Notify callbacks
        for callback in self._on_trigger_fired:
            try:
                callback(fired)
            except Exception:
                pass  # Don't let one bad callback break everything

        return fired

    def process_pending_events(
        self,
        automations: list[AutomationDefinition],
    ) -> list[TriggerFired]:
        """
        Process all pending events and return fired triggers.

        This should be called periodically to check for new events.
        """
        if not self._event_listener.is_running():
            return []

        fired_triggers = []

        # Process all available events
        events_processed = 0
        max_events_per_batch = 100

        while events_processed < max_events_per_batch:
            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break

            events_processed += 1

            # Find matching automations
            for automation in automations:
                if automation.trigger.type == TriggerType.EVENT:
                    result = self.evaluate_event_trigger(automation, event)

                    if result == TriggerEvaluationResult.FIRED:
                        fired = self.fire_trigger(
                            automation,
                            TriggerType.EVENT,
                            event,
                            {"event": event.model_dump()},
                        )
                        fired_triggers.append(fired)

        return fired_triggers

    def get_cooldown_tracker(self, automation_id: str) -> CooldownTracker | None:
        """Get the cooldown tracker for an automation."""
        return self._cooldown_trackers.get(automation_id)

    def reset_cooldown(self, automation_id: str) -> None:
        """Reset cooldown for an automation."""
        tracker = self._cooldown_trackers.get(automation_id)
        if tracker:
            tracker.cooldown_until = None

    def _drain_events(self, timeout: float = 1.0) -> int:
        """Drain remaining events from the queue."""
        count = 0
        start = time.time()

        while time.time() - start < timeout:
            try:
                self._event_queue.get_nowait()
                count += 1
            except queue.Empty:
                break

        return count


@lru_cache(maxsize=1)
def get_trigger_engine() -> TriggerEngine:
    """Get the global trigger engine."""
    return TriggerEngine()
