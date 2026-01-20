"""
Automation Registry - load, store, and manage automation definitions.

Handles:
- Loading automations from YAML files
- Validation of automation definitions
- Runtime registration and management
- Automation execution history tracking
- Import/export of automation configurations
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from platform_god.automations.models import (
    ActionConfig,
    ActionType,
    AutomationDefinition,
    AutomationRun,
    AutomationStatus,
    TriggerConfig,
    TriggerType,
)
from platform_god.automations.scheduler import AutomationScheduler, get_scheduler
from platform_god.automations.triggers import TriggerEngine, get_trigger_engine


class RegistryError(Exception):
    """Base exception for registry errors."""


class ValidationError(RegistryError):
    """Raised when automation validation fails."""


@dataclass
class AutomationSource:
    """Source information for an automation."""

    source_path: Path | None = None
    content_hash: str = ""
    loaded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    format: str = "yaml"  # yaml, json, or dict


@dataclass
class AutomationRegistryEntry:
    """A registered automation with metadata."""

    automation: AutomationDefinition
    source: AutomationSource
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_modified: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AutomationRegistry:
    """
    Registry for automation definitions.

    Manages:
    - Loading automations from YAML/JSON files
    - Runtime registration and validation
    - Scheduling time-based automations
    - Integration with trigger engine
    """

    DEFAULT_AUTOMATIONS_DIR = Path("configs/automations")
    STATE_DIR = Path("var/automations/registry")

    def __init__(
        self,
        automations_dir: Path | None = None,
        state_dir: Path | None = None,
        trigger_engine: TriggerEngine | None = None,
        scheduler: AutomationScheduler | None = None,
    ):
        """Initialize the automation registry."""
        self._automations_dir = automations_dir or self.DEFAULT_AUTOMATIONS_DIR
        self._state_dir = state_dir or self.STATE_DIR
        self._state_dir.mkdir(parents=True, exist_ok=True)

        self._trigger_engine = trigger_engine or get_trigger_engine()
        self._scheduler = scheduler or get_scheduler()

        # Storage
        self._automations: dict[str, AutomationRegistryEntry] = {}
        self._index: dict[str, list[str]] = {
            "by_name": {},
            "by_trigger_type": {},
            "by_status": {},
        }

        # History
        self._runs: dict[str, AutomationRun] = {}
        self._runs_by_automation: dict[str, list[str]] = {}

        # Load persisted state
        self._load_state()

    def load_all(self) -> int:
        """
        Load all automations from the automations directory.

        Returns:
            Number of automations loaded
        """
        if not self._automations_dir.exists():
            return 0

        count = 0

        # Load YAML files
        for yaml_file in self._automations_dir.glob("*.yaml"):
            try:
                automations = self.load_from_yaml(yaml_file)
                for automation in automations:
                    self.register(automation, source_path=yaml_file)
                    count += 1
            except Exception:
                pass  # Skip invalid files

        # Load JSON files
        for json_file in self._automations_dir.glob("*.json"):
            try:
                automations = self.load_from_json(json_file)
                for automation in automations:
                    self.register(automation, source_path=json_file)
                    count += 1
            except Exception:
                pass

        return count

    def load_from_yaml(self, path: Path) -> list[AutomationDefinition]:
        """Load automations from a YAML file."""
        content = path.read_text()
        # content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]  # Reserved for future use

        data = yaml.safe_load(content)

        if isinstance(data, dict):
            # Single automation
            return [self._parse_automation(data)]
        elif isinstance(data, list):
            # Multiple automations
            return [self._parse_automation(item) for item in data]
        else:
            raise ValidationError(f"Invalid YAML structure in {path}")

    def load_from_json(self, path: Path) -> list[AutomationDefinition]:
        """Load automations from a JSON file."""
        content = path.read_text()
        # content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]  # Reserved for future use

        data = json.loads(content)

        if isinstance(data, dict):
            return [self._parse_automation(data)]
        elif isinstance(data, list):
            return [self._parse_automation(item) for item in data]
        else:
            raise ValidationError(f"Invalid JSON structure in {path}")

    def load_from_dict(self, data: dict[str, Any]) -> AutomationDefinition:
        """Load an automation from a dictionary."""
        return self._parse_automation(data)

    def register(
        self,
        automation: AutomationDefinition,
        source_path: Path | None = None,
        update_if_exists: bool = True,
    ) -> AutomationRegistryEntry:
        """
        Register an automation.

        Args:
            automation: The automation to register
            source_path: Optional source file path
            update_if_exists: Whether to update if already registered

        Returns:
            The registry entry

        Raises:
            ValidationError: If automation is invalid
        """
        # Validate
        if not automation.is_valid():
            raise ValidationError(f"Invalid automation: {automation.name}")

        # Generate ID if not set
        if not automation.id or automation.id.startswith("automation_"):
            # Create stable ID from name
            name_hash = hashlib.sha256(automation.name.encode()).hexdigest()[:12]
            automation.id = f"automation_{name_hash}"

        # Check if already exists
        existing = self._automations.get(automation.id)

        if existing:
            if not update_if_exists:
                return existing

            # Update existing
            content = source_path.read_text() if source_path else ""
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:16] if content else ""

            existing.automation = automation
            existing.source.content_hash = content_hash
            existing.source.source_path = source_path
            existing.last_modified = datetime.now(timezone.utc).isoformat()

            # Re-register with trigger engine and scheduler
            self._reregister_automation(automation)
            return existing

        # Create new entry
        content = source_path.read_text() if source_path else ""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16] if content else ""

        source = AutomationSource(
            source_path=source_path,
            content_hash=content_hash,
        )

        entry = AutomationRegistryEntry(
            automation=automation,
            source=source,
        )

        self._automations[automation.id] = entry
        self._update_index(automation, entry)

        # Register with trigger engine and scheduler
        self._register_automation(automation)

        # Save state
        self._save_state()

        return entry

    def unregister(self, automation_id: str) -> bool:
        """Unregister an automation."""
        entry = self._automations.pop(automation_id, None)
        if not entry:
            return False

        # Remove from index
        self._remove_from_index(automation_id, entry.automation)

        # Unregister from trigger engine and scheduler
        self._unregister_automation(automation_id)

        # Save state
        self._save_state()

        return True

    def get(self, automation_id: str) -> AutomationDefinition | None:
        """Get an automation by ID."""
        entry = self._automations.get(automation_id)
        return entry.automation if entry else None

    def get_by_name(self, name: str) -> AutomationDefinition | None:
        """Get an automation by name."""
        for entry in self._automations.values():
            if entry.automation.name == name:
                return entry.automation
        return None

    def list_all(
        self,
        status: AutomationStatus | None = None,
        trigger_type: TriggerType | None = None,
    ) -> list[AutomationDefinition]:
        """List all registered automations, optionally filtered."""
        automations = list(self._automations.values())

        if status:
            automations = [e for e in automations if e.automation.status == status]

        if trigger_type:
            automations = [e for e in automations if e.automation.trigger.type == trigger_type]

        return [e.automation for e in automations]

    def list_enabled(self) -> list[AutomationDefinition]:
        """List all enabled automations."""
        return [
            entry.automation
            for entry in self._automations.values()
            if entry.automation.status == AutomationStatus.ENABLED
        ]

    def enable(self, automation_id: str) -> bool:
        """Enable an automation."""
        entry = self._automations.get(automation_id)
        if not entry:
            return False

        entry.automation.status = AutomationStatus.ENABLED
        self._register_automation(entry.automation)
        self._save_state()

        return True

    def disable(self, automation_id: str) -> bool:
        """Disable an automation."""
        entry = self._automations.get(automation_id)
        if not entry:
            return False

        entry.automation.status = AutomationStatus.DISABLED
        self._unregister_automation(automation_id)
        self._save_state()

        return True

    def record_run(self, run: AutomationRun) -> None:
        """Record an automation run."""
        self._runs[run.run_id] = run

        # Index by automation
        automation_id = run.automation_id
        if automation_id not in self._runs_by_automation:
            self._runs_by_automation[automation_id] = []
        self._runs_by_automation[automation_id].append(run.run_id)

        # Prune old runs (keep last 1000)
        if len(self._runs) > 1000:
            # Sort by started_at
            sorted_runs = sorted(
                self._runs.items(),
                key=lambda x: x[1].started_at,
            )
            # Remove oldest
            for run_id, _ in sorted_runs[:100]:
                del self._runs[run_id]
                # Remove from index
                for automation_runs in self._runs_by_automation.values():
                    if run_id in automation_runs:
                        automation_runs.remove(run_id)

        self._save_state()

    def get_run(self, run_id: str) -> AutomationRun | None:
        """Get an automation run by ID."""
        return self._runs.get(run_id)

    def get_runs(
        self,
        automation_id: str | None = None,
        limit: int = 50,
    ) -> list[AutomationRun]:
        """Get automation runs, optionally filtered."""
        runs = []

        if automation_id:
            run_ids = self._runs_by_automation.get(automation_id, [])
            for run_id in run_ids[-limit:]:
                run = self._runs.get(run_id)
                if run:
                    runs.append(run)
        else:
            # Get most recent runs
            sorted_runs = sorted(
                self._runs.values(),
                key=lambda r: r.started_at,
                reverse=True,
            )
            runs = sorted_runs[:limit]

        return runs

    def export_automation(self, automation_id: str, output_path: Path, format: str = "yaml") -> None:
        """Export an automation to a file."""
        automation = self.get(automation_id)
        if not automation:
            raise RegistryError(f"Automation not found: {automation_id}")

        data = automation.model_dump()

        if format == "yaml":
            content = yaml.dump(data, default_flow_style=False, sort_keys=False)
        elif format == "json":
            content = json.dumps(data, indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)

    def export_all(self, output_dir: Path, format: str = "yaml") -> int:
        """Export all automations to a directory."""
        output_dir.mkdir(parents=True, exist_ok=True)

        count = 0
        for entry in self._automations.values():
            automation = entry.automation
            filename = f"{automation.name}.{format}"
            output_path = output_dir / filename

            self.export_automation(automation.id, output_path, format)
            count += 1

        return count

    def reload(self, automation_id: str) -> bool:
        """Reload an automation from its source file."""
        entry = self._automations.get(automation_id)
        if not entry or not entry.source.source_path:
            return False

        source_path = entry.source.source_path

        # Remove existing
        self.unregister(automation_id)

        # Reload from source
        try:
            if source_path.suffix in (".yaml", ".yml"):
                automations = self.load_from_yaml(source_path)
            elif source_path.suffix == ".json":
                automations = self.load_from_json(source_path)
            else:
                return False

            for automation in automations:
                # Preserve the original ID
                automation.id = automation_id
                self.register(automation, source_path=source_path)

            return True
        except Exception:
            return False

    def _parse_automation(self, data: dict[str, Any]) -> AutomationDefinition:
        """Parse automation definition from dict."""
        # Parse trigger
        trigger_data = data.get("trigger", {})
        trigger = self._parse_trigger(trigger_data)

        # Parse actions
        actions_data = data.get("actions", [])
        actions = [self._parse_action(ad) for ad in actions_data]

        # Create automation
        return AutomationDefinition(
            id=data.get("id", ""),
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0"),
            status=AutomationStatus(data.get("status", "enabled")),
            trigger=trigger,
            actions=actions,
            metadata=data.get("metadata", {}),
        )

    def _parse_trigger(self, data: dict[str, Any]) -> TriggerConfig:
        """Parse trigger configuration."""
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
                cron_expression=time_data["cron_expression"],
                timezone_str=time_data.get("timezone", "UTC"),
            )

        elif trigger_type == TriggerType.CONDITION:
            from platform_god.automations.models import ConditionTrigger

            condition_data = data.get("condition", {})
            trigger.condition = ConditionTrigger(
                metric_path=condition_data["metric_path"],
                operator=condition_data["operator"],
                threshold=condition_data["threshold"],
                check_interval_seconds=condition_data.get("check_interval_seconds", 60),
            )

        trigger.cooldown_seconds = data.get("cooldown_seconds", 0)
        trigger.max_executions = data.get("max_executions")

        return trigger

    def _parse_action(self, data: dict[str, Any]) -> ActionConfig:
        """Parse action configuration."""
        return ActionConfig(
            type=ActionType(data["type"]),
            name=data.get("name", ""),
            parameters=data.get("parameters", {}),
            continue_on_failure=data.get("continue_on_failure", False),
            retry_count=data.get("retry_count", 0),
            retry_delay_seconds=data.get("retry_delay_seconds", 5),
            timeout_seconds=data.get("timeout_seconds"),
        )

    def _update_index(
        self,
        automation: AutomationDefinition,
        entry: AutomationRegistryEntry,
    ) -> None:
        """Update the search index."""
        automation_id = automation.id

        # Name index
        if automation.name not in self._index["by_name"]:
            self._index["by_name"][automation.name] = []
        self._index["by_name"][automation.name].append(automation_id)

        # Trigger type index
        trigger_key = automation.trigger.type.value
        if trigger_key not in self._index["by_trigger_type"]:
            self._index["by_trigger_type"][trigger_key] = []
        self._index["by_trigger_type"][trigger_key].append(automation_id)

        # Status index
        status_key = automation.status.value
        if status_key not in self._index["by_status"]:
            self._index["by_status"][status_key] = []
        self._index["by_status"][status_key].append(automation_id)

    def _remove_from_index(self, automation_id: str, automation: AutomationDefinition) -> None:
        """Remove an automation from the index."""
        # Name index
        if automation.name in self._index["by_name"]:
            self._index["by_name"][automation.name] = [
                aid for aid in self._index["by_name"][automation.name] if aid != automation_id
            ]

        # Trigger type index
        trigger_key = automation.trigger.type.value
        if trigger_key in self._index["by_trigger_type"]:
            self._index["by_trigger_type"][trigger_key] = [
                aid for aid in self._index["by_trigger_type"][trigger_key] if aid != automation_id
            ]

        # Status index
        status_key = automation.status.value
        if status_key in self._index["by_status"]:
            self._index["by_status"][status_key] = [
                aid for aid in self._index["by_status"][status_key] if aid != automation_id
            ]

    def _register_automation(self, automation: AutomationDefinition) -> None:
        """Register automation with trigger engine and scheduler."""
        if automation.status != AutomationStatus.ENABLED:
            return

        # Register with trigger engine
        self._trigger_engine.register_automation(automation)

        # Register with scheduler if time-based
        if automation.trigger.type == TriggerType.TIME:
            try:
                self._scheduler.schedule_automation(automation)
            except Exception:
                pass  # Scheduler may not be running

    def _reregister_automation(self, automation: AutomationDefinition) -> None:
        """Re-register an automation (update)."""
        self._unregister_automation(automation.id)
        self._register_automation(automation)

    def _unregister_automation(self, automation_id: str) -> None:
        """Unregister automation from trigger engine and scheduler."""
        self._trigger_engine.unregister_automation(automation_id)
        self._scheduler.unschedule_automation(automation_id)

    def _load_state(self) -> None:
        """Load persisted state."""
        index_file = self._state_dir / "index.json"

        if index_file.exists():
            try:
                data = json.loads(index_file.read_text())
                self._index = data.get("index", self._index)
            except (json.JSONDecodeError, ValueError):
                pass

    def _save_state(self) -> None:
        """Persist state to disk."""
        index_file = self._state_dir / "index.json"

        data = {
            "index": self._index,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        index_file.write_text(json.dumps(data, indent=2))


@lru_cache(maxsize=1)
def get_automation_registry() -> AutomationRegistry:
    """Get the global automation registry."""
    return AutomationRegistry()
