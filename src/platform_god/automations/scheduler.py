"""
Automation Scheduler - scheduled and recurring automation execution.

Handles:
- Cron expression parsing and scheduling
- Background task execution
- Task persistence across restarts
- Graceful shutdown
- Missed schedule handling

The scheduler runs as a background thread, waking periodically to:
1. Check for due tasks
2. Schedule next occurrences of recurring tasks
3. Execute pending tasks
4. Persist state changes
"""

import fcntl
import json
import os
import signal
import threading
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Callable

from platform_god.automations.models import (
    AutomationDefinition,
    ScheduledTask,
    TimeTrigger,
    TriggerType,
)
from platform_god.automations.triggers import TriggerFired, TriggerFiredCallback


class SchedulerStatus(Enum):
    """Status of the scheduler."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class TaskLockError(Exception):
    """Raised when a task cannot be locked."""


@dataclass
class ScheduleInfo:
    """Parsed schedule information from a cron expression."""

    minute: str = "*"
    hour: str = "*"
    day: str = "*"
    month: str = "*"
    weekday: str = "*"
    timezone_str: str = "UTC"

    def matches(self, dt: datetime) -> bool:
        """Check if a datetime matches this schedule."""
        # Convert to schedule timezone
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(self.timezone_str)
        local_dt = dt.astimezone(tz)

        return (
            self._matches_field(local_dt.minute, self.minute, 0, 59)
            and self._matches_field(local_dt.hour, self.hour, 0, 23)
            and self._matches_field(local_dt.day, self.day, 1, 31)
            and self._matches_field(local_dt.month, self.month, 1, 12)
            and self._matches_field(local_dt.weekday() + 1, self.weekday, 1, 7)  # Cron uses 1-7 for Mon-Sun
        )

    def _matches_field(self, value: int, pattern: str, min_val: int, max_val: int) -> bool:
        """Check if a value matches a cron pattern field."""
        if pattern == "*":
            return True

        # Handle lists: "1,3,5"
        if "," in pattern:
            return any(self._matches_field(value, p.strip(), min_val, max_val) for p in pattern.split(","))

        # Handle ranges: "1-5"
        if "-" in pattern:
            start, end = pattern.split("-")
            try:
                start_val = int(start)
                end_val = int(end)
                return start_val <= value <= end_val
            except ValueError:
                return False

        # Handle steps: "*/5" or "1-10/2"
        if "/" in pattern:
            base, step = pattern.split("/")
            try:
                step_val = int(step)
                if base == "*":
                    return (value - min_val) % step_val == 0
                else:
                    return self._matches_field(value, base, min_val, max_val) and (
                        (value - self._min_of(base, min_val)) % step_val == 0
                    )
            except ValueError:
                return False

        # Simple value match
        try:
            return value == int(pattern)
        except ValueError:
            return False

    def _min_of(self, pattern: str, default: int) -> int:
        """Get the minimum value from a pattern."""
        if "-" in pattern:
            return int(pattern.split("-")[0])
        if "," in pattern:
            return min(int(p.strip()) for p in pattern.split(",") if p.strip().isdigit())
        return default

    def next_occurrence(self, after: datetime | None = None) -> datetime:
        """Calculate the next occurrence after a given time."""
        check_time = after or datetime.now(timezone.utc)

        # Check forward minute by minute (simple but inefficient)
        # For production, a more sophisticated algorithm would be better
        for i in range(60 * 24 * 365 * 2):  # Check up to 2 years ahead
            candidate = check_time + timedelta(minutes=i)
            # Round to minute boundary
            candidate = candidate.replace(second=0, microsecond=0)

            if self.matches(candidate):
                return candidate

        # Should never get here, but return a far future date as fallback
        return check_time + timedelta(days=365)


@dataclass
class TaskExecution:
    """A task execution record."""

    task_id: str
    automation_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"
    run_id: str | None = None
    error: str | None = None


class SchedulerPersistence:
    """Handles persistence of scheduled tasks."""

    def __init__(self, state_dir: Path | None = None):
        """Initialize persistence layer."""
        self._state_dir = state_dir or Path("var/automations/scheduler")
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._tasks_file = self._state_dir / "scheduled_tasks.json"
        self._executions_file = self._state_dir / "executions.json"
        self._lock_file = self._state_dir / "scheduler.lock"

    def load_tasks(self) -> dict[str, ScheduledTask]:
        """Load all scheduled tasks."""
        if not self._tasks_file.exists():
            return {}

        try:
            data = json.loads(self._tasks_file.read_text())
            return {
                task_id: ScheduledTask(**task_data)
                for task_id, task_data in data.items()
            }
        except (json.JSONDecodeError, ValueError):
            return {}

    def save_tasks(self, tasks: dict[str, ScheduledTask]) -> None:
        """Save all scheduled tasks."""
        data = {
            task_id: task.model_dump()
            for task_id, task in tasks.items()
        }
        self._tasks_file.write_text(json.dumps(data, indent=2))

    def load_executions(self) -> list[TaskExecution]:
        """Load task execution records."""
        if not self._executions_file.exists():
            return []

        try:
            data = json.loads(self._executions_file.read_text())
            return [TaskExecution(**item) for item in data]
        except (json.JSONDecodeError, ValueError):
            return []

    def save_executions(self, executions: list[TaskExecution]) -> None:
        """Save task execution records."""
        data = [
            {
                "task_id": e.task_id,
                "automation_id": e.automation_id,
                "started_at": e.started_at.isoformat(),
                "completed_at": e.completed_at.isoformat() if e.completed_at else None,
                "status": e.status,
                "run_id": e.run_id,
                "error": e.error,
            }
            for e in executions
        ]
        self._executions_file.write_text(json.dumps(data, indent=2))

    def acquire_lock(self, timeout: float = 30.0) -> bool:
        """Acquire exclusive scheduler lock."""
        try:
            self._lock_file.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._lock_file, os.O_CREAT | os.O_WRONLY)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # Write our PID
                os.write(fd, str(os.getpid()).encode())
                return True
            except (IOError, OSError):
                os.close(fd)
                return False
        except (FileNotFoundError, PermissionError):
            return False

    def release_lock(self) -> None:
        """Release the scheduler lock."""
        if self._lock_file.exists():
            try:
                self._lock_file.unlink()
            except OSError:
                pass


# Type alias for callback
TriggerFiredCallback = Callable[[TriggerFired], None]


class AutomationScheduler:
    """
    Background scheduler for time-based automations.

    Features:
    - Cron-like scheduling
    - Persistent task storage
    - Graceful shutdown
    - Lock-based single-instance guarantee
    - Missed schedule recovery
    """

    # Default tick interval - how often to check for due tasks
    TICK_INTERVAL_SECONDS = 30

    def __init__(
        self,
        state_dir: Path | None = None,
        tick_interval: float = TICK_INTERVAL_SECONDS,
    ):
        """Initialize scheduler."""
        self._state_dir = state_dir or Path("var/automations/scheduler")
        self._tick_interval = tick_interval

        self._persistence = SchedulerPersistence(self._state_dir)

        self._status = SchedulerStatus.STOPPED
        self._thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

        # State
        self._tasks: dict[str, ScheduledTask] = {}
        self._executions: list[TaskExecution] = []
        self._schedule_cache: dict[str, ScheduleInfo] = {}

        # Callbacks
        self._on_task_due: list[Callable[[ScheduledTask], None]] = []

    @property
    def status(self) -> SchedulerStatus:
        """Get current scheduler status."""
        return self._status

    def add_task_callback(self, callback: Callable[[ScheduledTask], None]) -> None:
        """Add a callback for when a task becomes due."""
        self._on_task_due.append(callback)

    def start(self) -> bool:
        """
        Start the scheduler.

        Returns:
            True if started successfully, False if couldn't acquire lock
        """
        if self._status != SchedulerStatus.STOPPED:
            return True  # Already running or starting

        self._status = SchedulerStatus.STARTING

        # Try to acquire exclusive lock
        if not self._persistence.acquire_lock():
            self._status = SchedulerStatus.ERROR
            return False

        # Load persisted state
        self._tasks = self._persistence.load_tasks()
        self._executions = self._persistence.load_executions()

        # Reset status of any running tasks from previous run
        for task in self._tasks.values():
            if task.status == "running":
                task.status = "pending"
                task.last_run = None

        # Start scheduler thread
        self._shutdown_event.clear()
        self._thread = threading.Thread(
            target=self._scheduler_loop,
            name="AutomationScheduler",
            daemon=True,
        )
        self._thread.start()

        self._status = SchedulerStatus.RUNNING
        return True

    def stop(self, graceful: bool = True, timeout: float = 30.0) -> None:
        """Stop the scheduler."""
        if self._status == SchedulerStatus.STOPPED:
            return

        self._status = SchedulerStatus.STOPPING

        if graceful:
            # Wait for current tick to complete
            self._shutdown_event.wait(timeout)

        # Signal shutdown
        self._shutdown_event.set()

        # Wait for thread
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        # Save state and release lock
        self._save_state()
        self._persistence.release_lock()

        self._status = SchedulerStatus.STOPPED

    def schedule_automation(
        self,
        automation: AutomationDefinition,
        first_run_at: datetime | None = None,
    ) -> ScheduledTask:
        """
        Schedule an automation for time-based execution.

        Args:
            automation: The automation to schedule
            first_run_at: Optional first run time (defaults to next cron occurrence)

        Returns:
            The created ScheduledTask
        """
        if automation.trigger.type != TriggerType.TIME or not automation.trigger.time:
            raise ValueError("Automation must have a time trigger to be scheduled")

        trigger = automation.trigger.time

        # Parse schedule
        schedule_info = self._parse_schedule(trigger)
        self._schedule_cache[automation.id] = schedule_info

        # Calculate first run
        if first_run_at:
            scheduled_at = first_run_at
        else:
            scheduled_at = schedule_info.next_occurrence()

        # Create task
        task = ScheduledTask(
            task_id=f"task_{automation.id}",
            automation_id=automation.id,
            automation_name=automation.name,
            scheduled_at=scheduled_at.isoformat(),
            trigger_type=TriggerType.TIME,
            execution_context={"cron_expression": trigger.cron_expression},
        )

        self._tasks[task.task_id] = task
        self._save_state()

        return task

    def unschedule_automation(self, automation_id: str) -> bool:
        """Remove an automation from the schedule."""
        task_id = f"task_{automation_id}"
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._schedule_cache.pop(automation_id, None)
            self._save_state()
            return True
        return False

    def update_task_status(
        self,
        task_id: str,
        status: str,
        run_id: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update the status of a scheduled task."""
        task = self._tasks.get(task_id)
        if not task:
            return

        task.status = status

        if status == "running":
            execution = TaskExecution(
                task_id=task_id,
                automation_id=task.automation_id,
                started_at=datetime.now(timezone.utc),
                status="running",
                run_id=run_id,
            )
            self._executions.append(execution)
            task.last_run = execution.started_at.isoformat()

        elif status in ("completed", "failed", "cancelled"):
            # Find the running execution and update it
            for execution in reversed(self._executions):
                if execution.task_id == task_id and execution.status == "running":
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.status = status
                    execution.error = error
                    break

            # Schedule next run
            if status == "completed":
                schedule_info = self._schedule_cache.get(task.automation_id)
                if schedule_info:
                    next_run = schedule_info.next_occurrence()
                    task.next_run = next_run.isoformat()
                    task.scheduled_at = next_run.isoformat()
                    task.status = "pending"

        self._save_state()

    def get_scheduled_tasks(self) -> list[ScheduledTask]:
        """Get all scheduled tasks."""
        return list(self._tasks.values())

    def get_task_executions(self, task_id: str | None = None) -> list[TaskExecution]:
        """Get execution history, optionally filtered by task."""
        if task_id:
            return [e for e in self._executions if e.task_id == task_id]
        return self._executions.copy()

    def reschedule_missed(self, max_age: timedelta = timedelta(hours=24)) -> int:
        """
        Reschedule tasks that were missed during downtime.

        Args:
            max_age: Maximum age of missed tasks to reschedule

        Returns:
            Number of tasks rescheduled
        """
        now = datetime.now(timezone.utc)
        rescheduled = 0

        for task in self._tasks.values():
            if task.status == "pending":
                scheduled_time = datetime.fromisoformat(task.scheduled_at)

                # Check if it was missed (past time and not too old)
                if scheduled_time < now and (now - scheduled_time) <= max_age:
                    # Reschedule for next occurrence
                    schedule_info = self._schedule_cache.get(task.automation_id)
                    if schedule_info:
                        next_run = schedule_info.next_occurrence(now + timedelta(minutes=1))
                        task.scheduled_at = next_run.isoformat()
                        task.next_run = next_run.isoformat()
                        rescheduled += 1

        if rescheduled > 0:
            self._save_state()

        return rescheduled

    def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while not self._shutdown_event.is_set():
            try:
                self._tick()
            except Exception as e:
                # Log error but continue
                self._log_error(f"Scheduler tick error: {e}")

            # Wait for next tick or shutdown
            self._shutdown_event.wait(self._tick_interval)

    def _tick(self) -> None:
        """Single scheduler tick - check for due tasks."""
        now = datetime.now(timezone.utc)

        for task in self._tasks.values():
            if task.status != "pending":
                continue

            # Check if task is due
            if task.is_due(now):
                # Mark as running
                task.status = "running"

                # Notify callbacks
                for callback in self._on_task_due:
                    try:
                        callback(task)
                    except Exception:
                        pass

    def _parse_schedule(self, trigger: TimeTrigger) -> ScheduleInfo:
        """Parse a cron expression into a ScheduleInfo."""
        parts = trigger.cron_expression.split()

        if len(parts) < 5:
            raise ValueError(f"Invalid cron expression: {trigger.cron_expression}")

        return ScheduleInfo(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            weekday=parts[4],
            timezone_str=trigger.timezone_str,
        )

    def _save_state(self) -> None:
        """Persist scheduler state."""
        self._persistence.save_tasks(self._tasks)
        self._persistence.save_executions(self._executions)

    def _log_error(self, message: str) -> None:
        """Log an error message."""
        log_file = self._state_dir / "scheduler.log"
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(log_file, "a") as f:
            f.write(f"{timestamp} [ERROR] {message}\n")


@lru_cache(maxsize=1)
def get_scheduler() -> AutomationScheduler:
    """Get the global automation scheduler."""
    return AutomationScheduler()


# Signal handlers for graceful shutdown
def _setup_signal_handlers(scheduler: AutomationScheduler) -> None:
    """Setup signal handlers for graceful shutdown."""
    def handler(signum, frame):
        scheduler.stop(graceful=True)

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)
