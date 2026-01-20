# Platform God Automations Module

Automation triggers and execution system for Platform God.

## Overview

The automations module provides a complete system for defining, scheduling, and executing automation workflows. Automations can be triggered by events, scheduled with cron expressions, or activated based on conditions.

## Architecture

```
platform_god/automations/
|- __init__.py       # Package exports and high-level API
|- models.py         # Core data models (Automation, Trigger, Action, etc.)
|- triggers.py       # Trigger engine (event, time, condition evaluation)
|- actions.py        # Action executor (agents, chains, notifications, etc.)
|- scheduler.py      # Background task scheduler with cron support
|- registry.py       # Automation loader and runtime registry
```

## Components

### Models (`models.py`)

Core data structures for the automations system:

- **`AutomationDefinition`**: Complete automation with trigger and actions
- **`TriggerConfig`**: Event, time, or condition trigger configuration
- **`ActionConfig`**: Single action with parameters and retry policy
- **`AutomationRun`**: Record of an automation execution
- **`ActionExecution`**: Record of a single action execution
- **`ScheduledTask`**: Persistent scheduled task for the scheduler
- **`Event`**: System event that can trigger automations
- **`CooldownTracker`**: Tracks cooldown periods between executions

### Triggers (`triggers.py`)

Trigger evaluation and event dispatch:

- **`TriggerEngine`**: Main engine for evaluating all trigger types
- **`EventListener`**: Publishes system events (agent complete, chain complete, etc.)
- **`ConditionEvaluator`**: Evaluates condition-based triggers
- **`EventTrigger`**: Match events to automations
- **`TimeTrigger`**: Cron-based time triggers
- **`ConditionTrigger`**: Metric threshold triggers

### Actions (`actions.py`)

Executable automation actions:

- **`ActionExecutor`**: Executes actions with retry and idempotency
- **`execute_agent`**: Run a single agent
- **`execute_chain`**: Run an agent chain
- **`send_notification`**: Send notifications (log, registry, custom)
- **`create_artifact`**: Create and register artifacts
- **`update_registry`**: Update registry entries
- **`http_request`**: Make HTTP requests
- **`log_message`**: Log messages
- **`custom`**: Execute custom registered actions

### Scheduler (`scheduler.py`)

Background scheduler for time-based automations:

- **`AutomationScheduler`**: Main scheduler with cron support
- **`ScheduleInfo`**: Parsed cron expression with matching logic
- **`SchedulerPersistence`**: Task persistence across restarts
- **`TaskExecution`**: Execution history for scheduled tasks
- Graceful shutdown handling
- Missed schedule recovery
- Single-instance lock guarantee

### Registry (`registry.py`)

Automation definition management:

- **`AutomationRegistry`**: Load, store, and manage automations
- **`load_from_yaml()` / `load_from_json()`**: Load automations from files
- **`register()`**: Register an automation for execution
- **`record_run()`**: Record automation execution history
- **`export_automation()` / `export_all()``: Export automations

## Usage

### Basic Usage

```python
from platform_god.automations import (
    get_automation_registry,
    get_trigger_engine,
    get_scheduler,
    execute_automation,
)

# Load automations from config directory
registry = get_automation_registry()
count = registry.load_all()
print(f"Loaded {count} automations")

# Start the trigger engine and scheduler
trigger_engine = get_trigger_engine()
trigger_engine.start()

scheduler = get_scheduler()
scheduler.start()

# Manually execute an automation
automation = registry.get_by_name("daily_security_scan")
if automation:
    run = execute_automation(
        automation,
        context={"repository_root": "/path/to/repo"}
    )
    print(f"Execution status: {run.status.value}")
```

### Defining Automations (YAML)

Automations are defined in YAML files under `configs/automations/`:

```yaml
name: my_automation
description: Automation description
version: "1.0"
status: enabled

# Event-based trigger
trigger:
  type: event
  event:
    event_type: chain_complete
    chain_name: full_analysis
  cooldown_seconds: 3600

# Time-based trigger (cron)
# trigger:
#   type: time
#   time:
#     cron_expression: "0 2 * * *"  # 2 AM daily
#     timezone_str: "UTC"
#   cooldown_seconds: 82800

# Condition-based trigger
# trigger:
#   type: condition
#   condition:
#     metric_path: $.metrics.health_score
#     operator: lt
#     threshold: 50
#     check_interval_seconds: 300
#   cooldown_seconds: 3600

actions:
  - type: execute_agent
    name: run_discovery
    parameters:
      agent_name: PG_DISCOVERY
      repository_root: "{repository_root}"
      mode: dry_run
    continue_on_failure: false
    retry_count: 1
    timeout_seconds: 300

  - type: send_notification
    name: notify_team
    parameters:
      message: "Discovery completed for {repository_root}"
      level: info
      channels: [log, registry]
    continue_on_failure: true

  - type: create_artifact
    name: save_report
    parameters:
      artifact_type: discovery_report
      filename: "discovery_{timestamp}.json"
      register_in_registry: true
    continue_on_failure: true
```

### Trigger Types

#### Event Triggers

Triggered by system events:
- `agent_complete`: When an agent finishes execution
- `agent_failed`: When an agent fails
- `chain_complete`: When a chain finishes
- `chain_failed`: When a chain fails
- `registry_update`: When registry is updated
- `artifact_created`: When an artifact is created
- `custom`: Custom events

#### Time Triggers

Scheduled with cron expressions:
```
0 2 * * *     # 2 AM every day
0 */6 * * *   # Every 6 hours
0 0 * * 1     # Midnight every Monday
*/30 9-17 * * *  # Every 30 minutes during business hours
```

#### Condition Triggers

Triggered when metrics cross thresholds:
```yaml
trigger:
  type: condition
  condition:
    metric_path: $.metrics.health_score
    operator: lt  # gt, lt, gte, lte, eq, ne, contains, exists
    threshold: 50
    check_interval_seconds: 300
```

### Action Types

| Action | Description | Parameters |
|--------|-------------|------------|
| `execute_agent` | Run a single agent | `agent_name`, `repository_root`, `mode` |
| `execute_chain` | Run an agent chain | `chain` or `chain_name`, `repository_root`, `mode` |
| `send_notification` | Send a notification | `message`, `level`, `channels` |
| `create_artifact` | Create an artifact file | `artifact_type`, `filename`, `content` |
| `update_registry` | Update registry entry | `entity_type`, `entity_id`, `operation`, `data` |
| `http_request` | Make an HTTP request | `url`, `method`, `headers`, `body` |
| `log_message` | Log a message | `message`, `level` |
| `custom` | Execute custom action | `action_name` |

### Event Publishing

```python
from platform_god.automations import get_trigger_engine

engine = get_trigger_engine()
engine.start()

# Publish events
listener = engine.event_listener

# Agent completion
event = listener.publish_agent_complete(agent_result)

# Agent failure
event = listener.publish_agent_failed(agent_result)

# Chain completion
event = listener.publish_chain_complete(
    chain_name="full_analysis",
    status="completed",
    completed_steps=8,
    total_steps=8,
    execution_time_ms=15000,
)

# Custom event
event = listener.publish_custom(
    custom_type="deployment_complete",
    metadata={"service": "api", "version": "1.2.3"},
)
```

## Features

### Idempotency

Actions track idempotency keys to avoid duplicate executions:

```python
# Each action generates an idempotency key from its config
# If an action was already executed with the same key,
# it returns the previous result instead of re-executing
```

### Chained Actions

Actions execute in sequence. Configure behavior on failure:

```yaml
actions:
  - type: execute_chain
    continue_on_failure: false  # Stop automation if this fails
    # ...

  - type: send_notification
    continue_on_failure: true  # Continue even if this fails
    # ...
```

### Retry Logic

Configure retry behavior per action:

```yaml
actions:
  - type: http_request
    retry_count: 3
    retry_delay_seconds: 10
    timeout_seconds: 30
```

### Audit Trail

All executions are tracked:

```python
# Get execution history
runs = registry.get_runs(automation_id="automation_xxx", limit=10)

for run in runs:
    print(f"{run.run_id}: {run.status.value}")
    for execution in run.action_executions:
        print(f"  - {execution.action_name}: {execution.status.value}")
```

### Graceful Shutdown

The scheduler handles graceful shutdown:

```python
scheduler.stop(graceful=True, timeout=30.0)
```

## Configuration

Automations are loaded from `configs/automations/` by default.

Directory structure:
```
configs/automations/
|- health_alert.yaml
|- daily_security_scan.yaml
|- chain_completion_notification.yaml
```

State is stored in `var/automations/`:
```
var/automations/
|- scheduler/
|   |- scheduled_tasks.json
|   |- executions.json
|   |- scheduler.lock
|- registry/
|   |- index.json
|- idempotency/
|   |- {idempotency_key}.json
|- state/
```

## Example Automations

See the example configurations in `configs/automations/`:
- `health_alert.yaml`: Alert on low health score
- `daily_security_scan.yaml`: Daily scheduled security scan
- `chain_completion_notification.yaml`: Notify on chain completion
