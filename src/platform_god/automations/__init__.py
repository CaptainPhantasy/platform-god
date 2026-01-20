"""
Platform God Automations Module

Provides automation trigger and execution capabilities for the Platform God system.

Components:
- TriggerEngine: Evaluates event, time, and condition-based triggers
- ActionExecutor: Executes automation actions (agents, chains, notifications, etc.)
- AutomationScheduler: Background scheduler for recurring automations
- AutomationRegistry: Manages automation definitions loaded from YAML configs

Usage:
    from platform_god.automations import (
        get_automation_registry,
        get_trigger_engine,
        get_scheduler,
        execute_automation,
    )

    # Load automations from config
    registry = get_automation_registry()
    registry.load_all()

    # Start the trigger engine and scheduler
    trigger_engine = get_trigger_engine()
    trigger_engine.start()

    scheduler = get_scheduler()
    scheduler.start()

    # Manually execute an automation
    automation = registry.get_by_name("my_automation")
    if automation:
        execute_automation(automation, context={"key": "value"})

Automations are defined in YAML files under configs/automations/:

Example automation:
```yaml
name: health_check_alert
description: Send alert when health score drops below threshold
version: "1.0"
status: enabled

trigger:
  type: condition
  condition:
    metric_path: $.metrics.health_score
    operator: lt
    threshold: 50
  cooldown_seconds: 3600

actions:
  - type: execute_chain
    name: analyze_health
    parameters:
      chain: health_analysis
      repository_root: /path/to/repo

  - type: send_notification
    name: alert_team
    parameters:
      message: "Health score dropped to {metrics.health_score}"
      level: warning
      channels: [log, registry]
```
"""

from platform_god.automations.actions import (
    ActionExecutionError,
    ActionExecutor,
    ActionResult,
    IdempotencyError,
)
from platform_god.automations.models import (
    ActionConfig,
    ActionExecution,
    ActionType,
    ActionStatus,
    AutomationDefinition,
    AutomationRun,
    AutomationStatus,
    ConditionTrigger,
    CooldownTracker,
    Event,
    EventTrigger,
    EventType,
    ScheduledTask,
    TimeTrigger,
    TriggerConfig,
    TriggerType,
)
from platform_god.automations.registry import (
    AutomationRegistry,
    AutomationRegistryEntry,
    RegistryError,
    ValidationError,
    get_automation_registry,
)
from platform_god.automations.scheduler import (
    AutomationScheduler as Scheduler,
    ScheduleInfo,
    SchedulerPersistence,
    SchedulerStatus,
    get_scheduler,
)
from platform_god.automations.triggers import (
    ConditionEvaluator,
    EventListener,
    TriggerEngine,
    TriggerEvaluationResult,
    TriggerFired,
    get_trigger_engine,
)

# High-level API functions


def execute_automation(
    automation: AutomationDefinition,
    context: dict[str, Any] | None = None,
    executor: ActionExecutor | None = None,
) -> AutomationRun:
    """
    Execute an automation with all its actions.

    Args:
        automation: The automation to execute
        context: Optional context to pass to actions
        executor: Optional action executor (uses default if not provided)

    Returns:
        AutomationRun with execution results
    """
    from platform_god.automations.models import AutomationRun, ActionExecution, TriggerType, ActionStatus

    context = context or {}
    executor = executor or ActionExecutor()

    run = AutomationRun(
        automation_id=automation.id,
        automation_name=automation.name,
        trigger_type=TriggerType.EVENT,  # Default to event for manual execution
        context=context,
    )

    # Execute each action in sequence
    for action in automation.actions:
        execution = ActionExecution(
            automation_id=automation.id,
            automation_run_id=run.run_id,
            action_name=action.name,
            action_type=action.type,
            input_parameters=action.parameters.copy(),
        )

        run.add_action_execution(execution)

        # Execute the action
        result = executor.execute(action, automation, context, execution)

        # Check if action failed
        if result.status == ActionStatus.FAILED and not action.continue_on_failure:
            run.mark_failed(result.error or "Action failed")
            return run

    # All actions completed
    run.mark_completed()
    return run


def create_automation(
    name: str,
    trigger_type: TriggerType,
    trigger_config: dict[str, Any],
    actions: list[dict[str, Any]],
    description: str = "",
    status: AutomationStatus = AutomationStatus.ENABLED,
) -> AutomationDefinition:
    """
    Create a new automation definition.

    Args:
        name: Unique name for the automation
        trigger_type: Type of trigger (event, time, condition)
        trigger_config: Configuration for the trigger
        actions: List of action configurations
        description: Optional description
        status: Initial status (default: enabled)

    Returns:
        AutomationDefinition ready to be registered
    """
    from platform_god.automations.models import ActionConfig

    # Build trigger
    trigger_data = {"type": trigger_type.value, **trigger_config}
    trigger = _build_trigger_from_dict(trigger_data)

    # Build actions
    action_configs = []
    for action_data in actions:
        action_configs.append(
            ActionConfig(
                type=ActionType(action_data["type"]),
                name=action_data.get("name", f"{name}_action_{len(action_configs)}"),
                parameters=action_data.get("parameters", {}),
                continue_on_failure=action_data.get("continue_on_failure", False),
                retry_count=action_data.get("retry_count", 0),
                retry_delay_seconds=action_data.get("retry_delay_seconds", 5),
                timeout_seconds=action_data.get("timeout_seconds"),
            )
        )

    return AutomationDefinition(
        name=name,
        description=description,
        status=status,
        trigger=trigger,
        actions=action_configs,
    )


def _build_trigger_from_dict(data: dict[str, Any]) -> TriggerConfig:
    """Build a TriggerConfig from a dictionary."""
    trigger_type = TriggerType(data.get("type", "event"))
    trigger = TriggerConfig(type=trigger_type)

    if trigger_type == TriggerType.EVENT:
        from platform_god.automations.models import EventTrigger, EventType

        event_data = data.get("event", {})
        trigger.event = EventTrigger(
            event_type=EventType(event_data.get("event_type", "custom")),
            agent_name=event_data.get("agent_name"),
            chain_name=event_data.get("chain_name"),
            filter_criteria=event_data.get("filter_criteria", {}),
        )

    elif trigger_type == TriggerType.TIME:
        from platform_god.automations.models import TimeTrigger

        time_data = data.get("time", {})
        trigger.time = TimeTrigger(
            cron_expression=time_data.get("cron_expression", "0 * * * *"),
            timezone_str=time_data.get("timezone", "UTC"),
        )

    elif trigger_type == TriggerType.CONDITION:
        from platform_god.automations.models import ConditionTrigger

        condition_data = data.get("condition", {})
        trigger.condition = ConditionTrigger(
            metric_path=condition_data.get("metric_path", ""),
            operator=condition_data.get("operator", "eq"),
            threshold=condition_data.get("threshold", 0),
            check_interval_seconds=condition_data.get("check_interval_seconds", 60),
        )

    trigger.cooldown_seconds = data.get("cooldown_seconds", 0)
    trigger.max_executions = data.get("max_executions")

    return trigger


__all__ = [
    # Models
    "ActionConfig",
    "ActionExecution",
    "ActionType",
    "ActionStatus",
    "AutomationDefinition",
    "AutomationRun",
    "AutomationStatus",
    "ConditionTrigger",
    "CooldownTracker",
    "Event",
    "EventTrigger",
    "EventType",
    "ScheduledTask",
    "TimeTrigger",
    "TriggerConfig",
    "TriggerType",
    # Actions
    "ActionExecutionError",
    "ActionExecutor",
    "ActionResult",
    "IdempotencyError",
    # Registry
    "AutomationRegistry",
    "AutomationRegistryEntry",
    "RegistryError",
    "ValidationError",
    "get_automation_registry",
    # Scheduler
    "Scheduler",
    "ScheduleInfo",
    "SchedulerPersistence",
    "SchedulerStatus",
    "get_scheduler",
    # Triggers
    "ConditionEvaluator",
    "EventListener",
    "TriggerEngine",
    "TriggerEvaluationResult",
    "TriggerFired",
    "get_trigger_engine",
    # High-level API
    "execute_automation",
    "create_automation",
]
