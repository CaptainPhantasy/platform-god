"""
Automation Actions - executable action implementations.

Provides actions for:
- Executing agents and chains
- Sending notifications
- Creating artifacts
- Updating registry entries
- HTTP requests
- Custom actions

All actions are:
- Idempotent when possible
- Timeout-aware
- Retry-capable
- Audit-logged
"""

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from platform_god.agents.executor import ExecutionContext, ExecutionHarness, ExecutionMode
from platform_god.agents.registry import get_agent
from platform_god.automations.models import (
    ActionConfig,
    ActionExecution,
    ActionStatus,
    ActionType,
    AutomationDefinition,
)
from platform_god.core.models import AgentStatus
from platform_god.orchestrator.core import (
    ChainDefinition,
    Orchestrator,
)
from platform_god.registry.storage import Registry


class ActionExecutionError(Exception):
    """Base exception for action execution errors."""

    def __init__(self, message: str, recoverable: bool = False):
        self.message = message
        self.recoverable = recoverable
        super().__init__(message)


class IdempotencyError(Exception):
    """Raised when an idempotent action was already executed."""


@dataclass
class ActionResult:
    """Result of an action execution."""

    status: ActionStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    execution_time_ms: float | None = None
    should_retry: bool = False
    idempotency_key: str | None = None


class ActionExecutor:
    """
    Executes automation actions with proper error handling and idempotency.

    Each action type has a corresponding execute_* method that:
    1. Validates parameters
    2. Checks idempotency
    3. Executes with timeout
    4. Handles retries
    5. Returns ActionResult
    """

    def __init__(
        self,
        registry: Registry | None = None,
        orchestrator: Orchestrator | None = None,
        execution_harness: ExecutionHarness | None = None,
        idempotency_dir: Path | None = None,
    ):
        """Initialize action executor."""
        self._registry = registry or Registry()
        self._orchestrator = orchestrator or Orchestrator()
        self._harness = execution_harness or ExecutionHarness()

        self._idempotency_dir = idempotency_dir or Path("var/automations/idempotency")
        self._idempotency_dir.mkdir(parents=True, exist_ok=True)

        # Custom action handlers
        self._custom_actions: dict[str, Callable[[ActionConfig, dict[str, Any]], ActionResult]] = {}

    def register_custom_action(
        self,
        name: str,
        handler: Callable[[ActionConfig, dict[str, Any]], ActionResult],
    ) -> None:
        """Register a custom action handler."""
        self._custom_actions[name] = handler

    def execute(
        self,
        action: ActionConfig,
        automation: AutomationDefinition,
        run_context: dict[str, Any],
        execution: ActionExecution,
    ) -> ActionResult:
        """
        Execute an action with full error handling and retries.

        Args:
            action: The action configuration to execute
            automation: The automation definition
            run_context: Context from the current automation run
            execution: The ActionExecution record to update

        Returns:
            ActionResult with status, output, and error info
        """
        execution.mark_started()

        # Check idempotency
        idempotency_key = action.get_idempotency_key()
        execution.idempotency_key = idempotency_key

        if self._was_already_executed(idempotency_key, run_context):
            # Check if previous execution succeeded
            previous_result = self._get_previous_execution_result(idempotency_key)
            if previous_result and previous_result["status"] == "completed":
                execution.mark_completed(previous_result.get("output"))
                return ActionResult(
                    status=ActionStatus.COMPLETED,
                    output=previous_result.get("output"),
                    idempotency_key=idempotency_key,
                )
            execution.mark_skipped()
            return ActionResult(
                status=ActionStatus.SKIPPED,
                error="Already executed (idempotency)",
                idempotency_key=idempotency_key,
            )

        # Execute with retries
        last_result: ActionResult | None = None
        for attempt in range(action.retry_count + 1):
            if attempt > 0:
                # Wait before retry
                time.sleep(action.retry_delay_seconds)

            try:
                result = self._execute_action(
                    action,
                    automation,
                    run_context,
                )

                # Check if should retry
                if result.should_retry and attempt < action.retry_count:
                    execution.retry_count = attempt + 1
                    last_result = result
                    continue

                # Update execution record
                if result.status == ActionStatus.COMPLETED:
                    execution.mark_completed(result.output)
                    self._record_execution(idempotency_key, execution, run_context)
                elif result.status == ActionStatus.FAILED:
                    execution.mark_failed(result.error or "Unknown error")
                    if result.should_retry:
                        # Will be handled by retry loop
                        continue

                return result

            except TimeoutError as e:
                if attempt < action.retry_count:
                    execution.retry_count = attempt + 1
                    continue
                execution.mark_failed(f"Timeout: {e}")
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=f"Timeout: {e}",
                    should_retry=False,
                )

            except Exception as e:
                if attempt < action.retry_count:
                    execution.retry_count = attempt + 1
                    continue
                execution.mark_failed(str(e))
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=str(e),
                    should_retry=False,
                )

        # All retries exhausted
        execution.mark_failed(last_result.error if last_result else "Max retries exceeded")
        return ActionResult(
            status=ActionStatus.FAILED,
            error=last_result.error if last_result else "Max retries exceeded",
            should_retry=False,
        )

    def _execute_action(
        self,
        action: ActionConfig,
        automation: AutomationDefinition,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Execute a single action (no retries)."""
        match action.type:
            case ActionType.EXECUTE_AGENT:
                return self._execute_agent_action(action, run_context)
            case ActionType.EXECUTE_CHAIN:
                return self._execute_chain_action(action, run_context)
            case ActionType.SEND_NOTIFICATION:
                return self._execute_notification_action(action, run_context)
            case ActionType.CREATE_ARTIFACT:
                return self._execute_create_artifact_action(action, run_context)
            case ActionType.UPDATE_REGISTRY:
                return self._execute_update_registry_action(action, run_context)
            case ActionType.HTTP_REQUEST:
                return self._execute_http_request_action(action, run_context)
            case ActionType.LOG_MESSAGE:
                return self._execute_log_message_action(action, run_context)
            case ActionType.CUSTOM:
                return self._execute_custom_action(action, run_context)
            case _:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=f"Unknown action type: {action.type}",
                )

    def _execute_agent_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Execute an agent as an action."""
        agent_name = action.parameters.get("agent_name")
        if not agent_name:
            return ActionResult(
                status=ActionStatus.FAILED,
                error="Missing required parameter: agent_name",
            )

        # Verify agent exists
        agent_def = get_agent(agent_name)
        if not agent_def:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Agent '{agent_name}' not found in registry",
            )

        # Build input from parameters and context
        input_data = action.parameters.get("input", {})
        if isinstance(input_data, dict):
            # Merge with run context
            merged_input = {**run_context, **input_data}
        else:
            merged_input = {**run_context, "input": input_data}

        # Determine execution mode
        mode_str = action.parameters.get("mode", "dry_run")
        try:
            mode = ExecutionMode(mode_str)
        except ValueError:
            mode = ExecutionMode.DRY_RUN

        # Get repository root
        repository_root = action.parameters.get("repository_root") or run_context.get("repository_root")
        if not repository_root:
            return ActionResult(
                status=ActionStatus.FAILED,
                error="Missing required parameter: repository_root",
            )

        repository_path = Path(repository_root)
        if not repository_path.exists():
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Repository root does not exist: {repository_root}",
            )

        # Execute agent
        context = ExecutionContext(
            repository_root=repository_path,
            agent_name=agent_name,
            mode=mode,
            caller=f"automation:{action.name}",
            metadata={"automation_action": action.name},
        )

        start_time = time.time()
        result = self._harness.execute(agent_name, merged_input, context)
        elapsed_ms = (time.time() - start_time) * 1000

        if result.status == AgentStatus.COMPLETED:
            return ActionResult(
                status=ActionStatus.COMPLETED,
                output={
                    "agent_name": agent_name,
                    "mode": mode.value,
                    "output_data": result.output_data,
                    "execution_time_ms": result.execution_time_ms,
                },
                execution_time_ms=elapsed_ms,
            )
        else:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=result.error_message or f"Agent execution failed with status: {result.status.value}",
                should_retry=result.status == AgentStatus.FAILED,
            )

    def _execute_chain_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Execute an agent chain as an action."""
        chain_name = action.parameters.get("chain_name")
        if not chain_name:
            # Try to get chain from predefined chains
            predefined_chains = {
                "discovery": ChainDefinition.discovery_chain,
                "security": ChainDefinition.security_scan_chain,
                "dependency_audit": ChainDefinition.dependency_audit_chain,
                "doc_generation": ChainDefinition.doc_generation_chain,
                "tech_debt": ChainDefinition.tech_debt_chain,
                "full_analysis": ChainDefinition.full_analysis_chain,
            }
            chain_key = action.parameters.get("chain")
            if chain_key in predefined_chains:
                chain = predefined_chains[chain_key]()
            else:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error="Missing required parameter: chain_name or valid chain key",
                )
        else:
            # For custom chain names, we'd need to load from config
            # For now, use predefined chains
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Custom chain '{chain_name}' not yet supported",
            )

        # Get repository root
        repository_root = action.parameters.get("repository_root") or run_context.get("repository_root")
        if not repository_root:
            return ActionResult(
                status=ActionStatus.FAILED,
                error="Missing required parameter: repository_root",
            )

        repository_path = Path(repository_root)
        if not repository_path.exists():
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Repository root does not exist: {repository_root}",
            )

        # Determine execution mode
        mode_str = action.parameters.get("mode", "dry_run")
        try:
            mode = ExecutionMode(mode_str)
        except ValueError:
            mode = ExecutionMode.DRY_RUN

        # Execute chain
        start_time = time.time()
        result = self._orchestrator.execute_chain(chain, repository_path, mode)
        elapsed_ms = (time.time() - start_time) * 1000

        if result.status.value == "completed":
            return ActionResult(
                status=ActionStatus.COMPLETED,
                output={
                    "chain_name": chain.name,
                    "completed_steps": result.completed_steps,
                    "total_steps": result.total_steps,
                    "final_state": result.final_state,
                    "execution_time_ms": elapsed_ms,
                },
                execution_time_ms=elapsed_ms,
            )
        else:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=result.error or f"Chain execution failed with status: {result.status.value}",
            )

    def _execute_notification_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Send a notification as an action."""
        message = action.parameters.get("message", "")
        level = action.parameters.get("level", "info")
        channels = action.parameters.get("channels", ["log"])

        # Format message with context
        try:
            formatted_message = message.format(**run_context)
        except (KeyError, AttributeError):
            formatted_message = message

        output = {
            "level": level,
            "channels": channels,
            "message": formatted_message,
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }

        # Send to each channel
        for channel in channels:
            match channel:
                case "log":
                    self._log_notification(level, formatted_message)
                case "registry":
                    self._registry_notification(level, formatted_message)
                case _:
                    output[f"{channel}_status"] = "unknown_channel"

        return ActionResult(
            status=ActionStatus.COMPLETED,
            output=output,
        )

    def _execute_create_artifact_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Create an artifact as an action."""
        artifact_type = action.parameters.get("artifact_type", "general")
        content = action.parameters.get("content", "")
        filename = action.parameters.get("filename")

        if not filename:
            filename = f"artifact_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

        # Create artifacts directory
        artifacts_dir = Path("var/artifacts/automations")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = artifacts_dir / filename

        # Format content with context
        try:
            formatted_content = content.format(**run_context)
        except (KeyError, AttributeError):
            formatted_content = str(content)

        # Write artifact
        artifact_path.write_text(formatted_content)

        # Optionally register in registry
        if action.parameters.get("register_in_registry", False):
            self._registry.register(
                entity_type="artifact",
                entity_id=artifact_path.stem,
                entity_data={
                    "path": str(artifact_path),
                    "type": artifact_type,
                    "created_by": "automation",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        return ActionResult(
            status=ActionStatus.COMPLETED,
            output={
                "artifact_path": str(artifact_path),
                "artifact_type": artifact_type,
                "size_bytes": len(formatted_content),
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _execute_update_registry_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Update registry as an action."""
        entity_type = action.parameters.get("entity_type")
        entity_id = action.parameters.get("entity_id")
        operation = action.parameters.get("operation", "update")

        if not entity_type or not entity_id:
            return ActionResult(
                status=ActionStatus.FAILED,
                error="Missing required parameters: entity_type, entity_id",
            )

        entity_data = action.parameters.get("data", {})

        # Format data with context
        try:
            formatted_data = {
                k: v.format(**run_context) if isinstance(v, str) else v
                for k, v in entity_data.items()
            }
        except (KeyError, AttributeError):
            formatted_data = entity_data

        # Execute registry operation
        match operation:
            case "register":
                result = self._registry.register(entity_type, entity_id, formatted_data)
            case "update":
                result = self._registry.update(entity_type, entity_id, formatted_data)
            case "deregister":
                result = self._registry.deregister(entity_type, entity_id)
            case _:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=f"Unknown registry operation: {operation}",
                )

        if result.status == "success":
            return ActionResult(
                status=ActionStatus.COMPLETED,
                output={
                    "operation": operation,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "audit_ref": result.audit_ref,
                },
            )
        else:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=result.error or "Registry operation failed",
            )

    def _execute_http_request_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Execute an HTTP request as an action."""
        url = action.parameters.get("url")
        method = action.parameters.get("method", "GET").upper()
        headers = action.parameters.get("headers", {})
        body = action.parameters.get("body")
        timeout = action.parameters.get("timeout", 30)

        if not url:
            return ActionResult(
                status=ActionStatus.FAILED,
                error="Missing required parameter: url",
            )

        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=f"Invalid URL: {url}",
                )
        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Invalid URL: {e}",
            )

        # Format URL with context
        try:
            formatted_url = url.format(**run_context)
        except (KeyError, AttributeError):
            formatted_url = url

        # Prepare request
        request_kwargs = {
            "method": method,
            "url": formatted_url,
            "headers": headers,
            "timeout": timeout,
        }

        if body and method in ("POST", "PUT", "PATCH"):
            request_kwargs["content"] = json.dumps(body) if isinstance(body, dict) else body

        # Execute request
        try:
            with httpx.Client() as client:
                response = client.request(**request_kwargs)

            output = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "success": 200 <= response.status_code < 300,
            }

            # Try to parse JSON response
            try:
                output["response_body"] = response.json()
            except:
                output["response_body"] = response.text[:1000]  # Truncate large responses

            if response.status_code >= 500:
                # Server error - might be retryable
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=f"HTTP {response.status_code}: Server error",
                    output=output,
                    should_retry=True,
                )
            elif response.status_code >= 400:
                # Client error - not retryable
                return ActionResult(
                    status=ActionStatus.FAILED,
                    error=f"HTTP {response.status_code}: Client error",
                    output=output,
                    should_retry=False,
                )
            else:
                return ActionResult(
                    status=ActionStatus.COMPLETED,
                    output=output,
                )

        except httpx.TimeoutException:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"HTTP request timeout after {timeout}s",
                should_retry=True,
            )
        except httpx.NetworkError as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Network error: {e}",
                should_retry=True,
            )
        except Exception as e:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"HTTP request failed: {e}",
                should_retry=False,
            )

    def _execute_log_message_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Log a message as an action."""
        message = action.parameters.get("message", "")
        level = action.parameters.get("level", "info").lower()

        # Format message
        try:
            formatted_message = message.format(**run_context)
        except (KeyError, AttributeError):
            formatted_message = str(message)

        # Log at appropriate level
        log_message = f"[Automation] {formatted_message}"

        match level:
            case "debug":
                # Would use logger.debug in real implementation
                pass
            case "info":
                # Would use logger.info
                pass
            case "warning" | "warn":
                # Would use logger.warning
                pass
            case "error":
                # Would use logger.error
                pass
            case _:
                pass

        # Write to automation log
        log_file = self._idempotency_dir.parent / "automation.log"
        with open(log_file, "a") as f:
            timestamp = datetime.now(timezone.utc).isoformat()
            f.write(f"{timestamp} [{level.upper()}] {log_message}\n")

        return ActionResult(
            status=ActionStatus.COMPLETED,
            output={
                "message": formatted_message,
                "level": level,
                "logged_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _execute_custom_action(
        self,
        action: ActionConfig,
        run_context: dict[str, Any],
    ) -> ActionResult:
        """Execute a custom action."""
        custom_name = action.parameters.get("action_name") or action.name

        if custom_name not in self._custom_actions:
            return ActionResult(
                status=ActionStatus.FAILED,
                error=f"Unknown custom action: {custom_name}",
            )

        handler = self._custom_actions[custom_name]
        return handler(action, run_context)

    def _log_notification(self, level: str, message: str) -> None:
        """Log a notification message."""
        log_file = self._idempotency_dir.parent / "notifications.log"
        with open(log_file, "a") as f:
            timestamp = datetime.now(timezone.utc).isoformat()
            f.write(f"{timestamp} [{level.upper()}] {message}\n")

    def _registry_notification(self, level: str, message: str) -> None:
        """Store notification in registry."""
        notification_id = f"notif_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        self._registry.register(
            entity_type="notification",
            entity_id=notification_id,
            entity_data={
                "level": level,
                "message": message,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _was_already_executed(
        self,
        idempotency_key: str,
        run_context: dict[str, Any],
    ) -> bool:
        """Check if an action with this idempotency key was already executed."""
        idempotency_file = self._idempotency_dir / f"{idempotency_key}.json"
        return idempotency_file.exists()

    def _get_previous_execution_result(self, idempotency_key: str) -> dict[str, Any] | None:
        """Get the result of a previous execution."""
        idempotency_file = self._idempotency_dir / f"{idempotency_key}.json"
        if idempotency_file.exists():
            try:
                return json.loads(idempotency_file.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return None

    def _record_execution(
        self,
        idempotency_key: str,
        execution: ActionExecution,
        run_context: dict[str, Any],
    ) -> None:
        """Record a successful execution for idempotency."""
        idempotency_file = self._idempotency_dir / f"{idempotency_key}.json"

        record = {
            "idempotency_key": idempotency_key,
            "action_name": execution.action_name,
            "action_type": execution.action_type.value,
            "status": execution.status.value,
            "completed_at": execution.completed_at,
            "output": execution.output,
        }

        idempotency_file.write_text(json.dumps(record, indent=2))
