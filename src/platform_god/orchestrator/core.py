"""
Orchestrator Core - multi-agent coordination.

Runs chains of agents with state passing between them.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from platform_god.agents.executor import (
    ExecutionContext,
    ExecutionHarness,
    ExecutionMode,
)
from platform_god.core.exceptions import ChainExecutionError
from platform_god.core.models import AgentClass, AgentResult, AgentStatus
from platform_god.registry.storage import Registry


class ChainStopReason(Enum):
    """Reasons why a chain might stop."""

    COMPLETED = "completed"
    AGENT_FAILED = "agent_failed"
    PRECHECK_FAILED = "precheck_failed"
    STOP_CONDITION = "stop_condition"
    MANUAL = "manual"


@dataclass
class AgentStep:
    """A single step in an agent chain."""

    agent_name: str
    input_mapping: str | None = None
    # JSONPath expression like "$.previous_agent.files"
    output_key: str | None = None
    # Key to store output under for next steps
    continue_on_failure: bool = False


@dataclass
class ChainDefinition:
    """Definition of an agent execution chain."""

    name: str
    description: str
    steps: list[AgentStep]
    initial_state: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def discovery_chain(cls) -> "ChainDefinition":
        """Create a standard discovery analysis chain."""
        return cls(
            name="discovery_analysis",
            description="Scan repository and generate initial report",
            steps=[
                AgentStep(
                    agent_name="PG_DISCOVERY",
                    output_key="discovery",
                ),
                AgentStep(
                    agent_name="PG_STACKMAP",
                    input_mapping="$.discovery",
                    output_key="stackmap",
                ),
                AgentStep(
                    agent_name="PG_HEALTH_SCORE",
                    input_mapping="$.stackmap",
                    output_key="health",
                ),
                AgentStep(
                    agent_name="PG_REPORT_WRITER",
                    input_mapping="$.discovery,$.stackmap,$.health",
                    output_key="report",
                ),
            ],
        )

    @classmethod
    def security_scan_chain(cls) -> "ChainDefinition":
        """Create a security scanning chain."""
        return cls(
            name="security_scan",
            description="Scan for secrets and security risks",
            steps=[
                AgentStep(
                    agent_name="PG_DISCOVERY",
                    output_key="discovery",
                ),
                AgentStep(
                    agent_name="PG_SECRETS_AND_RISK",
                    input_mapping="$.discovery",
                    output_key="security",
                ),
                AgentStep(
                    agent_name="PG_NEXT_STEPS",
                    input_mapping="$.security",
                    output_key="recommendations",
                ),
            ],
        )

    @classmethod
    def dependency_audit_chain(cls) -> "ChainDefinition":
        """Create a dependency audit chain."""
        return cls(
            name="dependency_audit",
            description="Analyze dependencies for vulnerabilities and issues",
            steps=[
                AgentStep(
                    agent_name="PG_DISCOVERY",
                    output_key="discovery",
                ),
                AgentStep(
                    agent_name="PG_DEPENDENCY",
                    input_mapping="$.discovery",
                    output_key="dependencies",
                ),
                AgentStep(
                    agent_name="PG_SECRETS_AND_RISK",
                    input_mapping="$.dependencies",
                    output_key="risk",
                ),
                AgentStep(
                    agent_name="PG_REPORT_WRITER",
                    input_mapping="$.dependencies,$.risk",
                    output_key="report",
                ),
            ],
        )

    @classmethod
    def doc_generation_chain(cls) -> "ChainDefinition":
        """Create a documentation generation chain."""
        return cls(
            name="doc_generation",
            description="Generate documentation from code analysis",
            steps=[
                AgentStep(
                    agent_name="PG_DISCOVERY",
                    output_key="discovery",
                ),
                AgentStep(
                    agent_name="PG_STACKMAP",
                    input_mapping="$.discovery",
                    output_key="stackmap",
                ),
                AgentStep(
                    agent_name="PG_ENGINEERING_PRINCIPLES",
                    input_mapping="$.stackmap",
                    output_key="principles",
                ),
                AgentStep(
                    agent_name="PG_DOC_AUDIT",
                    input_mapping="$.discovery,$.principles",
                    output_key="doc_audit",
                ),
                AgentStep(
                    agent_name="PG_DOC_MANAGER",
                    input_mapping="$.doc_audit",
                    output_key="documentation",
                ),
            ],
        )

    @classmethod
    def tech_debt_chain(cls) -> "ChainDefinition":
        """Create a technical debt analysis chain."""
        return cls(
            name="tech_debt",
            description="Analyze technical debt and generate remediation plan",
            steps=[
                AgentStep(
                    agent_name="PG_DISCOVERY",
                    output_key="discovery",
                ),
                AgentStep(
                    agent_name="PG_STACKMAP",
                    input_mapping="$.discovery",
                    output_key="stackmap",
                ),
                AgentStep(
                    agent_name="PG_HEALTH_SCORE",
                    input_mapping="$.stackmap",
                    output_key="health",
                ),
                AgentStep(
                    agent_name="PG_REFACTOR_PLANNER",
                    input_mapping="$.health",
                    output_key="refactor_plan",
                ),
                AgentStep(
                    agent_name="PG_NEXT_STEPS",
                    input_mapping="$.refactor_plan",
                    output_key="next_steps",
                ),
            ],
        )

    @classmethod
    def full_analysis_chain(cls) -> "ChainDefinition":
        """Create a comprehensive full-repository analysis chain."""
        return cls(
            name="full_analysis",
            description="Complete repository analysis with all metrics",
            steps=[
                AgentStep(
                    agent_name="PG_DISCOVERY",
                    output_key="discovery",
                ),
                AgentStep(
                    agent_name="PG_STACKMAP",
                    input_mapping="$.discovery",
                    output_key="stackmap",
                ),
                AgentStep(
                    agent_name="PG_HEALTH_SCORE",
                    input_mapping="$.stackmap",
                    output_key="health",
                ),
                AgentStep(
                    agent_name="PG_DEPENDENCY",
                    input_mapping="$.discovery",
                    output_key="dependencies",
                ),
                AgentStep(
                    agent_name="PG_SECRETS_AND_RISK",
                    input_mapping="$.discovery",
                    output_key="security",
                ),
                AgentStep(
                    agent_name="PG_DOC_AUDIT",
                    input_mapping="$.discovery",
                    output_key="docs",
                ),
                AgentStep(
                    agent_name="PG_RELEASE_READINESS",
                    input_mapping="$.health,$.security",
                    output_key="readiness",
                ),
                AgentStep(
                    agent_name="PG_REPORT_WRITER",
                    input_mapping="$.discovery,$.stackmap,$.health,$.dependencies,$.security,$.docs,$.readiness",
                    output_key="report",
                ),
            ],
        )


@dataclass
class ChainResult:
    """Result of executing an agent chain."""

    chain_name: str
    status: ChainStopReason
    completed_steps: int
    total_steps: int
    results: list[AgentResult] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class ChainState:
    """Mutable state passed between agents in a chain."""

    data: dict[str, Any] = field(default_factory=dict)
    step_index: int = 0

    def set_output(self, key: str, value: Any) -> None:
        """Store output from an agent."""
        self.data[key] = value

    def get_output(self, key: str) -> Any:
        """Get stored output."""
        return self.data.get(key)

    def resolve_input(
        self, input_mapping: str | None, initial_state: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Resolve input mapping to actual input dict.

        Supports:
        - null -> use initial_state
        - "$.key" -> extract single key
        - "$.a,$.b" -> merge multiple keys
        """
        if not input_mapping:
            return initial_state.copy()

        result = {}
        for part in input_mapping.split(","):
            part = part.strip()
            if part.startswith("$."):
                key = part[2:]
                if key in self.data:
                    result[key] = self.data[key]
                elif key in initial_state:
                    result[key] = initial_state[key]
            else:
                result["input"] = part

        return result


class Orchestrator:
    """
    Multi-agent orchestration engine.

    Executes chains of agents with:
    - State passing between steps
    - Failure handling
    - Guardrail enforcement
    - Registry integration
    """

    def __init__(
        self,
        harness: ExecutionHarness | None = None,
        registry: Registry | None = None,
    ):
        """Initialize orchestrator with execution harness and registry."""
        self._harness = harness or ExecutionHarness()
        self._registry = registry or Registry()

    def execute_chain(
        self,
        chain: ChainDefinition,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
        on_step_complete: Callable[[AgentResult], None] | None = None,
    ) -> ChainResult:
        """
        Execute an agent chain.

        Args:
            chain: Chain definition to execute
            repository_root: Root of repository to analyze
            mode: Execution mode (dry_run, simulated, live)
            on_step_complete: Optional callback after each step

        Returns:
            ChainResult with status and all step outputs

        Raises:
            ChainExecutionError: If chain setup fails critically
        """
        if not chain.steps:
            raise ChainExecutionError(
                f"Chain '{chain.name}' has no steps defined",
                chain_name=chain.name,
            )

        if not repository_root.exists():
            raise ChainExecutionError(
                f"Repository root does not exist: {repository_root}",
                chain_name=chain.name,
                details={"repository_root": str(repository_root)},
            )

        state = ChainState(data=chain.initial_state.copy())
        results = []

        for step_index, step in enumerate(chain.steps):
            state.step_index = step_index

            # Build input for this step
            step_input = state.resolve_input(step.input_mapping, chain.initial_state)
            step_input.setdefault("repository_root", str(repository_root))

            # Execute agent
            context = ExecutionContext(
                repository_root=repository_root,
                agent_name=step.agent_name,
                mode=mode,
                caller=f"chain:{chain.name}",
            )

            try:
                result = self._harness.execute(step.agent_name, step_input, context)
            except Exception as e:
                # Wrap unexpected exceptions
                result = AgentResult(
                    agent_name=step.agent_name,
                    agent_class=AgentClass.READ_ONLY_SCAN,
                    status=AgentStatus.FAILED,
                    input_data=step_input,
                    error_message=f"Unexpected error: {e}",
                    error_type=type(e).__name__,
                )

            results.append(result)

            # Store output for next steps
            if step.output_key and result.output_data:
                state.set_output(step.output_key, result.output_data)

            # Callback
            if on_step_complete:
                on_step_complete(result)

            # Check for failure
            if result.status != AgentStatus.COMPLETED:
                if not step.continue_on_failure:
                    return ChainResult(
                        chain_name=chain.name,
                        status=ChainStopReason.AGENT_FAILED,
                        completed_steps=step_index + 1,
                        total_steps=len(chain.steps),
                        results=results,
                        final_state=state.data,
                        error=result.error_message,
                    )

        return ChainResult(
            chain_name=chain.name,
            status=ChainStopReason.COMPLETED,
            completed_steps=len(chain.steps),
            total_steps=len(chain.steps),
            results=results,
            final_state=state.data,
        )

    def execute_discovery_chain(
        self,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
    ) -> ChainResult:
        """Execute the standard discovery analysis chain."""
        chain = ChainDefinition.discovery_chain()
        return self.execute_chain(chain, repository_root, mode)

    def execute_security_chain(
        self,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
    ) -> ChainResult:
        """Execute the security scanning chain."""
        chain = ChainDefinition.security_scan_chain()
        return self.execute_chain(chain, repository_root, mode)

    def execute_dependency_audit_chain(
        self,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
    ) -> ChainResult:
        """Execute the dependency audit chain."""
        chain = ChainDefinition.dependency_audit_chain()
        return self.execute_chain(chain, repository_root, mode)

    def execute_doc_generation_chain(
        self,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
    ) -> ChainResult:
        """Execute the documentation generation chain."""
        chain = ChainDefinition.doc_generation_chain()
        return self.execute_chain(chain, repository_root, mode)

    def execute_tech_debt_chain(
        self,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
    ) -> ChainResult:
        """Execute the technical debt analysis chain."""
        chain = ChainDefinition.tech_debt_chain()
        return self.execute_chain(chain, repository_root, mode)

    def execute_full_analysis_chain(
        self,
        repository_root: Path,
        mode: ExecutionMode = ExecutionMode.DRY_RUN,
    ) -> ChainResult:
        """Execute the comprehensive full-repository analysis chain."""
        chain = ChainDefinition.full_analysis_chain()
        return self.execute_chain(chain, repository_root, mode)

    def chain_summary(self, result: ChainResult) -> str:
        """Generate a human-readable summary of chain execution."""
        lines = [
            f"Chain: {result.chain_name}",
            f"Status: {result.status.value}",
            f"Steps: {result.completed_steps}/{result.total_steps}",
        ]

        for i, step_result in enumerate(result.results):
            status_symbol = "✓" if step_result.is_success() else "✗"
            lines.append(
                f"  [{i+1}] {status_symbol} {step_result.agent_name}: "
                f"{step_result.status.value}"
            )
            if step_result.execution_time_ms:
                lines.append(f"      Time: {step_result.execution_time_ms:.0f}ms")
            if step_result.error_message:
                lines.append(f"      Error: {step_result.error_message}")
            if step_result.error_type:
                lines.append(f"      Error Type: {step_result.error_type}")

        return "\n".join(lines)

    def persist_chain_result(self, result: ChainResult, output_dir: Path) -> Path:
        """Persist chain result to disk."""
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = result.results[0].timestamp if result.results else "unknown"
        timestamp_safe = timestamp.replace(":", "-").replace("Z", "")

        filename = f"{result.chain_name}_{timestamp_safe}.json"
        output_path = output_dir / filename

        output_data = {
            "chain_name": result.chain_name,
            "status": result.status.value,
            "completed_steps": result.completed_steps,
            "total_steps": result.total_steps,
            "final_state": result.final_state,
            "results": [
                {
                    "agent_name": r.agent_name,
                    "status": r.status.value,
                    "output": r.output_data,
                    "error": r.error_message,
                    "error_type": r.error_type,
                    "execution_time_ms": r.execution_time_ms,
                }
                for r in result.results
            ],
        }

        output_path.write_text(json.dumps(output_data, indent=2))
        return output_path

    def record_chain_run(
        self, result: ChainResult, repository_root: Path
    ) -> "ChainRun":
        """Record chain run in state manager."""
        from platform_god.state.manager import StateManager

        state_mgr = StateManager()
        return state_mgr.record_chain_run(result.chain_name, repository_root, result)
