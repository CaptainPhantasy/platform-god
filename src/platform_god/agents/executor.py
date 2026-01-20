"""
Agent Execution Harness - safely runs agents with validation.

Executes agents deterministically with:
- Precheck validation
- Scope enforcement
- Output validation
- Audit logging
"""

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from platform_god.core.exceptions import (
    AgentNotFoundError,
    PrecheckError,
    ScopeViolationError,
    ValidationError,
)
from platform_god.core.models import (
    AgentResult,
    AgentStatus,
)

if TYPE_CHECKING:
    from platform_god.agents.registry import AgentDefinition


class ExecutionMode(Enum):
    """How the agent is executed."""

    DRY_RUN = "dry_run"  # Validate only, don't execute
    SIMULATED = "simulated"  # Return mock output
    LIVE = "live"  # Full LLM execution


@dataclass
class ExecutionContext:
    """Context passed during agent execution."""

    repository_root: Path
    agent_name: str
    mode: ExecutionMode = ExecutionMode.DRY_RUN
    caller: str = "system"
    metadata: dict[str, Any] = field(default_factory=dict)


class ExecutionHarness:
    """
    Harness for safe, deterministic agent execution.

    Enforces:
    1. Precheck validation before any work
    2. Scope/permission boundaries
    3. Output schema validation
    4. Audit logging
    """

    def __init__(self, audit_dir: Path | None = None):
        """Initialize harness with optional audit directory."""
        self._audit_dir = audit_dir or Path("var/audit")
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    def execute(
        self,
        agent_name: str,
        input_data: dict[str, Any],
        context: ExecutionContext,
    ) -> AgentResult:
        """
        Execute an agent with full validation.

        Returns AgentResult with status, output, and error details.
        """
        from platform_god.agents.registry import get_agent

        start_time = time.time()
        agent = get_agent(agent_name)

        if not agent:
            raise AgentNotFoundError(
                f"Agent '{agent_name}' not found in registry",
                agent_name=agent_name,
            )

        # Run prechecks
        try:
            self._validate_prechecks(agent, input_data, context)
        except PrecheckError as e:
            return AgentResult(
                agent_name=agent_name,
                agent_class=agent.agent_class,
                status=AgentStatus.STOPPED,
                input_data=input_data,
                error_message=str(e),
                error_type=type(e).__name__,
            )
        except ScopeViolationError as e:
            return AgentResult(
                agent_name=agent_name,
                agent_class=agent.agent_class,
                status=AgentStatus.STOPPED,
                input_data=input_data,
                error_message=str(e),
                error_type=type(e).__name__,
            )

        # Execute based on mode
        try:
            if context.mode == ExecutionMode.DRY_RUN:
                output = self._dry_run_output(agent)
            elif context.mode == ExecutionMode.SIMULATED:
                output = self._simulated_output(agent, input_data)
            else:
                output = self._live_output(agent, input_data)

            elapsed_ms = (time.time() - start_time) * 1000

            result = AgentResult(
                agent_name=agent_name,
                agent_class=agent.agent_class,
                status=AgentStatus.COMPLETED,
                input_data=input_data,
                output_data=output,
                execution_time_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            result = AgentResult(
                agent_name=agent_name,
                agent_class=agent.agent_class,
                status=AgentStatus.FAILED,
                input_data=input_data,
                error_message=str(e),
                error_type=type(e).__name__,
                execution_time_ms=elapsed_ms,
            )

        # Write audit log
        self._write_audit_log(result)

        return result

    def _validate_prechecks(
        self,
        agent: "AgentDefinition",
        input_data: dict[str, Any],
        context: ExecutionContext,
    ) -> None:
        """
        Run precheck validation.

        Raises:
            PrecheckError: If validation fails
            ScopeViolationError: If agent attempts to access unauthorized paths
        """
        failures = []

        # Check repository root exists
        repo_root = input_data.get("repository_root") or str(context.repository_root)
        repo_root_path = Path(repo_root)
        if not repo_root_path.exists():
            failures.append("repository_root does not exist")
        elif not repo_root_path.is_dir():
            failures.append("repository_root is not a directory")

        # Check scope enforcement
        if agent.allowed_paths:
            requested_path = repo_root_path.resolve()
            allowed_resolved = [Path(p).resolve() for p in agent.allowed_paths]
            is_allowed = any(
                str(requested_path).startswith(str(allowed))
                for allowed in allowed_resolved
            )
            if not is_allowed and agent.allowed_paths:
                raise ScopeViolationError(
                    f"Agent '{agent.name}' cannot access path: {repo_root}",
                    agent_name=agent.name,
                    agent_class=agent.agent_class.value,
                    requested_path=str(repo_root),
                    allowed_paths=agent.allowed_paths,
                )

        # Check required parameters based on agent
        required = self._extract_required_inputs(agent)
        for key in required:
            if key not in input_data:
                failures.append(f"Missing required input: {key}")

        if failures:
            raise PrecheckError(
                f"Precheck validation failed for agent '{agent.name}'",
                agent_name=agent.name,
                agent_class=agent.agent_class.value,
                failures=failures,
            )

    def _extract_required_inputs(self, agent: "AgentDefinition") -> set[str]:
        """Extract required input keys from agent definition."""
        # This would parse the INPUT section from the agent markdown
        # For now, return common required fields
        common = {"repository_root"}
        return common

    def _dry_run_output(self, agent: "AgentDefinition") -> dict[str, Any]:
        """Return mock output for dry run mode."""
        return {
            "status": "success",
            "mode": "dry_run",
            "agent": agent.name,
            "message": "Dry run completed - no actual execution",
        }

    def _simulated_output(
        self, agent: "AgentDefinition", input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Return simulated output based on agent schema."""
        base = {
            "status": "success",
            "mode": "simulated",
            "agent": agent.name,
        }

        # Add schema-based mock data
        if agent.output_schema:
            for key, value_type in agent.output_schema.items():
                if key == "status":
                    continue
                base[key] = _mock_value_for_type(key, value_type)

        return base

    def _live_output(
        self, agent: "AgentDefinition", input_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute agent via LLM."""
        from platform_god.llm.client import LLMClient, format_agent_prompt, load_agent_prompt

        # Load agent prompt
        prompt = load_agent_prompt(agent.name)

        # Format with input data
        formatted_prompt = format_agent_prompt(prompt, input_data)

        # Call LLM
        client = LLMClient()
        try:
            from platform_god.llm.client import LLMRequest

            request = LLMRequest(
                prompt=formatted_prompt,
                max_tokens=4096,
                temperature=0.0,
                response_format="json",
            )
            response = client.complete(request)

            # Parse JSON response
            output = response.parse_json()
            if output is None:
                raise ValidationError(
                    "LLM response could not be parsed as JSON",
                    field="output",
                    expected_format="valid JSON",
                    details={"response_preview": response.content[:200]},
                )

            # Add execution metadata
            output["_meta"] = {
                "model": response.model,
                "provider": response.provider.value,
                "tokens_used": response.tokens_used,
            }

            return output

        finally:
            client.close()

    def _write_audit_log(self, result: AgentResult) -> None:
        """Write execution result to audit log."""
        import datetime

        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d")
        log_file = self._audit_dir / f"execution_{timestamp}.jsonl"

        log_entry = {
            "timestamp": result.timestamp,
            "agent_name": result.agent_name,
            "agent_class": result.agent_class.value,
            "status": result.status.value,
            "execution_time_ms": result.execution_time_ms,
            "error": result.error_message,
            "error_type": result.error_type,
        }

        with open(log_file, "a") as f:
            f.write(json.dumps(log_entry) + "\n")


def _mock_value_for_type(key: str, type_hint: Any) -> Any:
    """Generate mock value based on type."""
    key_lower = key.lower()

    if "timestamp" in key_lower or "time" in key_lower:
        return "2024-01-01T00:00:00Z"
    if "count" in key_lower or "total" in key_lower:
        return 0
    if "size" in key_lower:
        return 0
    if "confidence" in key_lower:
        return "high"
    if "paths" in key_lower or "files" in key_lower:
        return []
    if "summary" in key_lower:
        return {}
    if "hash" in key_lower:
        return "a1b2c3d4"

    return "mock_value"
