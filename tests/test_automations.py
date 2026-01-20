"""Tests for automations module (scheduler, triggers, actions, models)."""

import json
import queue
import tempfile
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from platform_god.automations.models import (
    TriggerType,
    EventType,
    ActionType,
    ActionStatus,
    AutomationStatus,
    EventTrigger,
    TimeTrigger,
    ConditionTrigger,
    TriggerConfig,
    ActionConfig,
    AutomationDefinition,
    ScheduledTask,
    AutomationRun,
    Event,
    CooldownTracker,
)
from platform_god.automations.scheduler import (
    SchedulerStatus,
    ScheduleInfo,
    AutomationScheduler,
    SchedulerPersistence,
    get_scheduler,
)
from platform_god.automations.triggers import (
    TriggerEvaluationResult,
    TriggerFired,
    TriggerContext,
    EventListener,
    ConditionEvaluator,
    TriggerEngine,
    get_trigger_engine,
)
from platform_god.automations.actions import (
    ActionExecutionError,
    ActionResult,
    ActionExecutor,
)
from platform_god.core.models import AgentStatus, AgentResult


# =============================================================================
# Model tests
# =============================================================================


class TestAutomationModels:
    """Tests for automation model classes."""

    def test_event_trigger_matches(self):
        """Test EventTrigger.matches method."""
        trigger = EventTrigger(
            event_type=EventType.AGENT_COMPLETE,
            agent_name="PG_DISCOVERY",
        )

        # Matching event
        event = Event(
            event_type=EventType.AGENT_COMPLETE,
            agent_name="PG_DISCOVERY",
        )
        assert trigger.matches(event) is True

        # Different event type
        event2 = Event(
            event_type=EventType.AGENT_FAILED,
            agent_name="PG_DISCOVERY",
        )
        assert trigger.matches(event2) is False

        # Different agent name
        event3 = Event(
            event_type=EventType.AGENT_COMPLETE,
            agent_name="PG_SECURITY",
        )
        assert trigger.matches(event3) is False

    def test_event_trigger_no_filter(self):
        """Test EventTrigger without agent filter matches all agents."""
        trigger = EventTrigger(event_type=EventType.AGENT_COMPLETE)

        event1 = Event(
            event_type=EventType.AGENT_COMPLETE,
            agent_name="AnyAgent",
        )
        assert trigger.matches(event1) is True

    def test_event_trigger_with_filter_criteria(self):
        """Test EventTrigger with filter criteria."""
        trigger = EventTrigger(
            event_type=EventType.AGENT_COMPLETE,
            filter_criteria={"status": "completed"},
        )

        event = Event(
            event_type=EventType.AGENT_COMPLETE,
            metadata={"status": "completed"},
        )
        assert trigger.matches(event) is True

        event2 = Event(
            event_type=EventType.AGENT_COMPLETE,
            metadata={"status": "failed"},
        )
        assert trigger.matches(event2) is False

    def test_time_trigger_validates_format(self):
        """Test TimeTrigger validates cron format."""
        # Valid 5-part cron
        trigger = TimeTrigger(cron_expression="0 0 * * *")
        assert trigger.cron_expression == "0 0 * * *"

        # Valid 6-part cron
        trigger2 = TimeTrigger(cron_expression="0 0 * * * 2024")
        assert trigger2.cron_expression == "0 0 * * * 2024"

        # Invalid cron raises error
        with pytest.raises(ValueError):
            TimeTrigger(cron_expression="invalid")

    def test_trigger_config_validation(self):
        """Test TriggerConfig.is_valid method."""
        # Valid event trigger
        config = TriggerConfig(
            type=TriggerType.EVENT,
            event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
        )
        assert config.is_valid() is True

        # Missing event for event trigger
        config2 = TriggerConfig(type=TriggerType.EVENT)
        assert config2.is_valid() is False

        # Valid time trigger
        config3 = TriggerConfig(
            type=TriggerType.TIME,
            time=TimeTrigger(cron_expression="0 0 * * *"),
        )
        assert config3.is_valid() is True

        # Valid condition trigger
        config4 = TriggerConfig(
            type=TriggerType.CONDITION,
            condition=ConditionTrigger(
                metric_path="$.health_score",
                operator="gt",
                threshold=80,
            ),
        )
        assert config4.is_valid() is True

    def test_action_config_idempotency_key(self):
        """Test ActionConfig.get_idempotency_key method."""
        action = ActionConfig(
            type=ActionType.SEND_NOTIFICATION,
            name="test_action",
            parameters={"channel": "slack"},
        )

        key = action.get_idempotency_key()
        assert isinstance(key, str)
        assert len(key) == 16  # SHA256 truncated to 16 chars

        # Same action produces same key
        key2 = action.get_idempotency_key()
        assert key == key2

        # Different action produces different key
        action2 = ActionConfig(
            type=ActionType.SEND_NOTIFICATION,
            name="test_action",
            parameters={"channel": "email"},
        )
        key3 = action2.get_idempotency_key()
        assert key != key3

    def test_automation_definition_validation(self):
        """Test AutomationDefinition.is_valid method."""
        # Valid automation
        automation = AutomationDefinition(
            name="Test Automation",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[
                ActionConfig(type=ActionType.LOG_MESSAGE)
            ],
        )
        assert automation.is_valid() is True

        # Missing name
        automation2 = AutomationDefinition(
            name="",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )
        assert automation2.is_valid() is False

        # No actions
        automation3 = AutomationDefinition(
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[],
        )
        assert automation3.is_valid() is False


# =============================================================================
# ScheduleInfo tests
# =============================================================================


class TestScheduleInfo:
    """Tests for ScheduleInfo class."""

    def test_matches_wildcard(self):
        """Test matching with wildcards."""
        schedule = ScheduleInfo()  # All wildcards
        dt = datetime(2024, 1, 15, 12, 30, 0)
        assert schedule.matches(dt) is True

    def test_matches_specific_minute(self):
        """Test matching specific minute."""
        schedule = ScheduleInfo(minute="30")
        dt = datetime(2024, 1, 15, 12, 30, 0)
        assert schedule.matches(dt) is True

        dt2 = datetime(2024, 1, 15, 12, 31, 0)
        assert schedule.matches(dt2) is False

    def test_matches_specific_hour(self):
        """Test matching specific hour."""
        schedule = ScheduleInfo(hour="14")
        dt = datetime(2024, 1, 15, 14, 0, 0)
        assert schedule.matches(dt) is True

        dt2 = datetime(2024, 1, 15, 13, 0, 0)
        assert schedule.matches(dt2) is False

    def test_matches_list(self):
        """Test matching list of values."""
        schedule = ScheduleInfo(minute="0,15,30,45")
        dt = datetime(2024, 1, 15, 12, 15, 0)
        assert schedule.matches(dt) is True

        dt2 = datetime(2024, 1, 15, 12, 10, 0)
        assert schedule.matches(dt2) is False

    def test_matches_range(self):
        """Test matching range of values."""
        schedule = ScheduleInfo(hour="9-17")
        dt = datetime(2024, 1, 15, 12, 0, 0)
        assert schedule.matches(dt) is True

        dt2 = datetime(2024, 1, 15, 8, 0, 0)
        assert schedule.matches(dt2) is False

        dt3 = datetime(2024, 1, 15, 18, 0, 0)
        assert schedule.matches(dt3) is False

    def test_matches_step(self):
        """Test matching step values."""
        schedule = ScheduleInfo(minute="*/15")
        dt = datetime(2024, 1, 15, 12, 0, 0)
        assert schedule.matches(dt) is True

        dt2 = datetime(2024, 1, 15, 12, 15, 0)
        assert schedule.matches(dt2) is True

        dt3 = datetime(2024, 1, 15, 12, 10, 0)
        assert schedule.matches(dt3) is False

    def test_next_occurrence(self):
        """Test calculating next occurrence."""
        schedule = ScheduleInfo(minute="30")
        now = datetime(2024, 1, 15, 12, 0, 0)
        next_time = schedule.next_occurrence(now)

        assert next_time > now
        assert next_time.minute == 30

    def test_matches_timezone(self):
        """Test matching with timezone."""
        schedule = ScheduleInfo(hour="14", timezone_str="America/New_York")

        # Create datetime in UTC
        dt = datetime(2024, 1, 15, 19, 0, 0, tzinfo=timezone.utc)
        # 19:00 UTC is 14:00 EST
        assert schedule.matches(dt) is True


# =============================================================================
# SchedulerPersistence tests
# =============================================================================


class TestSchedulerPersistence:
    """Tests for SchedulerPersistence class."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def persistence(self, temp_state_dir):
        """Create persistence instance."""
        return SchedulerPersistence(state_dir=temp_state_dir)

    def test_load_tasks_empty(self, persistence):
        """Test loading tasks from empty state."""
        tasks = persistence.load_tasks()
        assert tasks == {}

    def test_save_and_load_tasks(self, persistence):
        """Test saving and loading tasks."""
        from platform_god.automations.models import ScheduledTask

        task = ScheduledTask(
            task_id="task_123",
            automation_id="automation_456",
            automation_name="Test Automation",
            scheduled_at=datetime.now(timezone.utc).isoformat(),
            trigger_type=TriggerType.TIME,
            status="pending",
        )

        persistence.save_tasks({"task_123": task})
        loaded = persistence.load_tasks()

        assert "task_123" in loaded
        assert loaded["task_123"].automation_id == "automation_456"

    def test_load_executions_empty(self, persistence):
        """Test loading executions from empty state."""
        executions = persistence.load_executions()
        assert executions == []

    def test_acquire_lock(self, persistence):
        """Test acquiring scheduler lock."""
        # Note: fcntl may not work on all systems
        # This test is basic
        try:
            result = persistence.acquire_lock(timeout=1.0)
            assert isinstance(result, bool)
        except (OSError, AttributeError):
            # fcntl not available on this platform
            pass

    def test_release_lock(self, persistence):
        """Test releasing scheduler lock."""
        persistence.release_lock()
        # Should not raise


# =============================================================================
# AutomationScheduler tests
# =============================================================================


class TestAutomationScheduler:
    """Tests for AutomationScheduler class."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def scheduler(self, temp_state_dir):
        """Create scheduler instance."""
        scheduler = AutomationScheduler(state_dir=temp_state_dir, tick_interval=0.1)
        yield scheduler
        if scheduler.status != SchedulerStatus.STOPPED:
            scheduler.stop(timeout=5.0)

    def test_initial_status(self, scheduler):
        """Test initial scheduler status."""
        assert scheduler.status == SchedulerStatus.STOPPED

    def test_start_scheduler(self, scheduler):
        """Test starting scheduler."""
        result = scheduler.start()
        assert result is True
        assert scheduler.status == SchedulerStatus.RUNNING

    def test_stop_scheduler(self, scheduler):
        """Test stopping scheduler."""
        scheduler.start()
        scheduler.stop(timeout=5.0)
        assert scheduler.status == SchedulerStatus.STOPPED

    def test_schedule_automation(self, scheduler):
        """Test scheduling an automation."""
        automation = AutomationDefinition(
            name="Scheduled Test",
            trigger=TriggerConfig(
                type=TriggerType.TIME,
                time=TimeTrigger(cron_expression="0 * * * *"),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        task = scheduler.schedule_automation(automation)

        assert task.automation_id == automation.id
        assert task.status == "pending"
        assert task.trigger_type == TriggerType.TIME

    def test_unschedule_automation(self, scheduler):
        """Test unscheduling an automation."""
        automation = AutomationDefinition(
            id="auto_123",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.TIME,
                time=TimeTrigger(cron_expression="0 * * * *"),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        scheduler.schedule_automation(automation)
        result = scheduler.unschedule_automation("auto_123")

        assert result is True

    def test_get_scheduled_tasks(self, scheduler):
        """Test getting scheduled tasks."""
        tasks = scheduler.get_scheduled_tasks()
        assert isinstance(tasks, list)

    def test_update_task_status(self, scheduler):
        """Test updating task status."""
        automation = AutomationDefinition(
            id="auto_456",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.TIME,
                time=TimeTrigger(cron_expression="0 * * * *"),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        task = scheduler.schedule_automation(automation)

        # Update to running
        scheduler.update_task_status(task.task_id, "running", run_id="run_123")

        # Update to completed
        scheduler.update_task_status(task.task_id, "completed", run_id="run_123")

        # Should schedule next run
        updated_tasks = scheduler.get_scheduled_tasks()
        assert any(t.task_id == task.task_id for t in updated_tasks)


# =============================================================================
# EventListener tests
# =============================================================================


class TestEventListener:
    """Tests for EventListener class."""

    @pytest.fixture
    def event_queue(self):
        """Create event queue."""
        return queue.Queue()

    @pytest.fixture
    def listener(self, event_queue):
        """Create event listener."""
        return EventListener(event_queue)

    def test_publish_agent_complete(self, listener, event_queue):
        """Test publishing agent complete event."""
        result = AgentResult(
            agent_name="PG_DISCOVERY",
            agent_class="read_only_scan",
            status=AgentStatus.COMPLETED,
            input_data={},
            output_data={"findings": []},
            execution_time_ms=100,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        event = listener.publish_agent_complete(result)

        assert event.event_type == EventType.AGENT_COMPLETE
        assert event.agent_name == "PG_DISCOVERY"
        assert not event_queue.empty()

    def test_publish_agent_failed(self, listener, event_queue):
        """Test publishing agent failed event."""
        result = AgentResult(
            agent_name="PG_SECURITY",
            agent_class="security_scan",
            status=AgentStatus.FAILED,
            input_data={},
            output_data=None,
            execution_time_ms=50,
            error_message="Scan failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        event = listener.publish_agent_failed(result)

        assert event.event_type == EventType.AGENT_FAILED
        assert event.metadata["error"] == "Scan failed"

    def test_publish_chain_complete(self, listener, event_queue):
        """Test publishing chain complete event."""
        event = listener.publish_chain_complete(
            chain_name="discovery",
            status="completed",
            completed_steps=5,
            total_steps=5,
            execution_time_ms=1000,
        )

        assert event.event_type == EventType.CHAIN_COMPLETE
        assert event.chain_name == "discovery"

    def test_publish_custom_event(self, listener, event_queue):
        """Test publishing custom event."""
        event = listener.publish_custom(
            custom_type="my_event",
            metadata={"key": "value"},
        )

        assert event.event_type == EventType.CUSTOM
        assert event.metadata["custom_type"] == "my_event"

    def test_start_stop_listener(self, listener):
        """Test starting and stopping listener."""
        assert listener.is_running() is False

        listener.start()
        assert listener.is_running() is True

        listener.stop()
        assert listener.is_running() is False


# =============================================================================
# ConditionEvaluator tests
# =============================================================================


class TestConditionEvaluator:
    """Tests for ConditionEvaluator class."""

    @pytest.fixture
    def evaluator(self):
        """Create condition evaluator."""
        return ConditionEvaluator()

    def test_evaluate_gt_operator(self, evaluator):
        """Test greater than operator."""
        trigger = ConditionTrigger(
            metric_path="score",
            operator="gt",
            threshold=80,
        )
        context = {"score": 85}

        assert evaluator.evaluate(trigger, context) is True

        context2 = {"score": 75}
        assert evaluator.evaluate(trigger, context2) is False

    def test_evaluate_lt_operator(self, evaluator):
        """Test less than operator."""
        trigger = ConditionTrigger(
            metric_path="temperature",
            operator="lt",
            threshold=30,
        )
        context = {"temperature": 25}

        assert evaluator.evaluate(trigger, context) is True

    def test_evaluate_gte_operator(self, evaluator):
        """Test greater than or equal operator."""
        trigger = ConditionTrigger(
            metric_path="count",
            operator="gte",
            threshold=100,
        )
        context = {"count": 100}

        assert evaluator.evaluate(trigger, context) is True

    def test_evaluate_lte_operator(self, evaluator):
        """Test less than or equal operator."""
        trigger = ConditionTrigger(
            metric_path="value",
            operator="lte",
            threshold=50,
        )
        context = {"value": 50}

        assert evaluator.evaluate(trigger, context) is True

    def test_evaluate_eq_operator(self, evaluator):
        """Test equality operator."""
        trigger = ConditionTrigger(
            metric_path="status",
            operator="eq",
            threshold="ready",
        )
        context = {"status": "ready"}

        assert evaluator.evaluate(trigger, context) is True

    def test_evaluate_ne_operator(self, evaluator):
        """Test not equal operator."""
        trigger = ConditionTrigger(
            metric_path="state",
            operator="ne",
            threshold="error",
        )
        context = {"state": "running"}

        assert evaluator.evaluate(trigger, context) is True

    def test_evaluate_contains_operator(self, evaluator):
        """Test contains operator."""
        trigger = ConditionTrigger(
            metric_path="message",
            operator="contains",
            threshold="error",
        )
        context = {"message": "An error occurred"}

        assert evaluator.evaluate(trigger, context) is True

    def test_evaluate_exists_operator(self, evaluator):
        """Test exists operator."""
        trigger = ConditionTrigger(
            metric_path="data",
            operator="exists",
            threshold=None,
        )
        context = {"data": "value"}

        assert evaluator.evaluate(trigger, context) is True

        context2 = {}
        assert evaluator.evaluate(trigger, context2) is False

    def test_resolve_nested_path(self, evaluator):
        """Test resolving nested metric paths."""
        trigger = ConditionTrigger(
            metric_path="metrics.health_score",
            operator="gt",
            threshold=80,
        )
        context = {"metrics": {"health_score": 90}}

        assert evaluator.evaluate(trigger, context) is True

    def test_resolve_dollar_notation(self, evaluator):
        """Test resolving $ notation paths."""
        trigger = ConditionTrigger(
            metric_path="$.data.value",
            operator="gt",
            threshold=50,
        )
        context = {"data": {"value": 75}}

        assert evaluator.evaluate(trigger, context) is True


# =============================================================================
# TriggerEngine tests
# =============================================================================


class TestTriggerEngine:
    """Tests for TriggerEngine class."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def engine(self, temp_state_dir):
        """Create trigger engine."""
        return TriggerEngine(state_dir=temp_state_dir)

    def test_initial_status(self, engine):
        """Test initial engine status."""
        assert engine.is_running() is False

    def test_start_stop_engine(self, engine):
        """Test starting and stopping engine."""
        engine.start()
        assert engine.is_running() is True

        engine.stop()
        assert engine.is_running() is False

    def test_register_automation(self, engine):
        """Test registering automation."""
        automation = AutomationDefinition(
            id="auto_123",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        engine.register_automation(automation)

        tracker = engine.get_cooldown_tracker("auto_123")
        assert tracker is not None

    def test_unregister_automation(self, engine):
        """Test unregistering automation."""
        automation = AutomationDefinition(
            id="auto_456",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        engine.register_automation(automation)
        engine.unregister_automation("auto_456")

        tracker = engine.get_cooldown_tracker("auto_456")
        assert tracker is None

    def test_evaluate_event_trigger_fired(self, engine):
        """Test evaluating event trigger that fires."""
        automation = AutomationDefinition(
            id="auto_789",
            name="Test",
            status=AutomationStatus.ENABLED,
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
                cooldown_seconds=0,
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        event = Event(
            event_type=EventType.AGENT_COMPLETE,
            agent_name="PG_DISCOVERY",
        )

        result = engine.evaluate_event_trigger(automation, event)
        assert result == TriggerEvaluationResult.FIRED

    def test_evaluate_event_trigger_disabled(self, engine):
        """Test evaluating disabled automation."""
        automation = AutomationDefinition(
            id="auto_disabled",
            name="Test",
            status=AutomationStatus.DISABLED,
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        event = Event(event_type=EventType.AGENT_COMPLETE)

        result = engine.evaluate_event_trigger(automation, event)
        assert result == TriggerEvaluationResult.DISABLED

    def test_fire_trigger(self, engine):
        """Test firing a trigger."""
        automation = AutomationDefinition(
            id="auto_fire",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        callback_called = []

        def callback(fired):
            callback_called.append(fired)

        engine.add_trigger_callback(callback)
        engine.register_automation(automation)

        fired = engine.fire_trigger(
            automation,
            TriggerType.EVENT,
            context={"test": "data"},
        )

        assert fired.automation_id == "auto_fire"
        assert len(callback_called) == 1


# =============================================================================
# ActionExecutor tests
# =============================================================================


class TestActionExecutor:
    """Tests for ActionExecutor class."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def executor(self, temp_dir):
        """Create action executor."""
        with patch("platform_god.automations.actions.Registry"), \
             patch("platform_god.automations.actions.Orchestrator"), \
             patch("platform_god.automations.actions.ExecutionHarness"):
            return ActionExecutor(idempotency_dir=temp_dir / "idempotency")

    def test_log_message_action(self, executor):
        """Test executing log message action."""
        automation = AutomationDefinition(
            id="auto_log",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[],
        )

        action = ActionConfig(
            type=ActionType.LOG_MESSAGE,
            parameters={"message": "Test log", "level": "info"},
        )

        from platform_god.automations.models import ActionExecution

        execution = ActionExecution(
            action_id="exec_1",
            action_name="log_test",
            action_type=ActionType.LOG_MESSAGE,
        )

        result = executor.execute(
            action,
            automation,
            {"var": "value"},
            execution,
        )

        assert result.status == ActionStatus.COMPLETED
        assert result.output["message"] == "Test log"

    def test_create_artifact_action(self, executor):
        """Test executing create artifact action."""
        automation = AutomationDefinition(
            id="auto_artifact",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[],
        )

        action = ActionConfig(
            type=ActionType.CREATE_ARTIFACT,
            parameters={
                "content": "Test artifact content",
                "filename": "test_artifact.json",
            },
        )

        from platform_god.automations.models import ActionExecution

        execution = ActionExecution(
            action_id="exec_2",
            action_name="create_artifact",
            action_type=ActionType.CREATE_ARTIFACT,
        )

        result = executor.execute(
            action,
            automation,
            {},
            execution,
        )

        assert result.status == ActionStatus.COMPLETED
        assert "artifact_path" in result.output

    def test_register_custom_action(self, executor):
        """Test registering custom action."""
        custom_called = []

        def custom_handler(action, context):
            custom_called.append((action, context))
            return ActionResult(status=ActionStatus.COMPLETED)

        executor.register_custom_action("custom_test", custom_handler)

        action = ActionConfig(
            type=ActionType.CUSTOM,
            parameters={"action_name": "custom_test"},
        )

        automation = AutomationDefinition(
            id="auto_custom",
            name="Test",
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
            ),
            actions=[],
        )

        from platform_god.automations.models import ActionExecution

        execution = ActionExecution(
            action_id="exec_3",
            action_name="custom_action",
            action_type=ActionType.CUSTOM,
        )

        result = executor.execute(
            action,
            automation,
            {},
            execution,
        )

        assert result.status == ActionStatus.COMPLETED
        assert len(custom_called) == 1


# =============================================================================
# Global singleton tests
# =============================================================================


class TestGlobalSingletons:
    """Tests for global singleton functions."""

    def test_get_scheduler_singleton(self):
        """Test get_scheduler returns singleton."""
        with patch("platform_god.automations.scheduler.AutomationScheduler") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance

            scheduler1 = get_scheduler()
            scheduler2 = get_scheduler()

            assert scheduler1 is scheduler2

    def test_get_trigger_engine_singleton(self):
        """Test get_trigger_engine returns singleton."""
        with patch("platform_god.automations.triggers.TriggerEngine") as mock_class:
            mock_instance = MagicMock()
            mock_class.return_value = mock_instance

            engine1 = get_trigger_engine()
            engine2 = get_trigger_engine()

            assert engine1 is engine2


# =============================================================================
# Integration tests
# =============================================================================


class TestAutomationsIntegration:
    """Integration tests for automations module."""

    @pytest.fixture
    def temp_state_dir(self):
        """Create temporary state directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_full_event_trigger_flow(self, temp_state_dir):
        """Test complete event trigger flow."""
        # Create automation
        automation = AutomationDefinition(
            id="integration_auto",
            name="Integration Test",
            status=AutomationStatus.ENABLED,
            trigger=TriggerConfig(
                type=TriggerType.EVENT,
                event=EventTrigger(event_type=EventType.AGENT_COMPLETE),
                cooldown_seconds=0,
            ),
            actions=[
                ActionConfig(type=ActionType.LOG_MESSAGE, parameters={"message": "Triggered"})
            ],
        )

        # Create trigger engine
        engine = TriggerEngine(state_dir=temp_state_dir)
        engine.start()

        # Register automation
        engine.register_automation(automation)

        # Create event
        event = Event(
            event_type=EventType.AGENT_COMPLETE,
            agent_name="PG_TEST",
        )

        # Evaluate trigger
        result = engine.evaluate_event_trigger(automation, event)
        assert result == TriggerEvaluationResult.FIRED

        # Fire trigger
        fired_triggers = []

        def callback(fired):
            fired_triggers.append(fired)

        engine.add_trigger_callback(callback)
        engine.fire_trigger(automation, TriggerType.EVENT, event=event)

        assert len(fired_triggers) == 1
        assert fired_triggers[0].automation_id == "integration_auto"

        engine.stop()

    def test_scheduler_task_lifecycle(self, temp_state_dir):
        """Test scheduler task lifecycle."""
        scheduler = AutomationScheduler(state_dir=temp_state_dir)

        automation = AutomationDefinition(
            id="scheduled_auto",
            name="Scheduled Test",
            trigger=TriggerConfig(
                type=TriggerType.TIME,
                time=TimeTrigger(cron_expression="0 * * * *"),
            ),
            actions=[ActionConfig(type=ActionType.LOG_MESSAGE)],
        )

        # Schedule automation
        task = scheduler.schedule_automation(automation)
        assert task.status == "pending"

        # Update task status through lifecycle
        scheduler.update_task_status(task.task_id, "running", run_id="run_1")
        scheduler.update_task_status(task.task_id, "completed", run_id="run_1")

        # Check it rescheduled
        tasks = scheduler.get_scheduled_tasks()
        assert any(t.task_id == task.task_id for t in tasks)

        scheduler.unschedule_automation("scheduled_auto")
        scheduler.stop()
