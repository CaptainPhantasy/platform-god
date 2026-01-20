"""
Core data models for Platform God.

All agent inputs/outputs use these deterministic, type-safe schemas.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class AgentClass(Enum):
    """Canonical agent classes defining permissions and scope."""

    READ_ONLY_SCAN = "READ_ONLY_SCAN"
    PLANNING_SYNTHESIS = "PLANNING_SYNTHESIS"
    REGISTRY_STATE = "REGISTRY_STATE"
    WRITE_GATED = "WRITE_GATED"
    CONTROL_PLANE = "CONTROL_PLANE"


class AgentStatus(Enum):
    """Possible states of agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass(frozen=True)
class AgentPermissions:
    """Immutable permissions granted to an agent."""

    can_read: bool = True
    can_write: bool = False
    can_network: bool = False
    allowed_write_paths: tuple[str, ...] = ()
    disallowed_paths: tuple[str, ...] = ()

    @staticmethod
    def for_class(agent_class: AgentClass) -> "AgentPermissions":
        """Return permissions for a given agent class."""
        match agent_class:
            case AgentClass.READ_ONLY_SCAN:
                return AgentPermissions(
                    can_read=True,
                    can_write=False,
                    can_network=False,
                )
            case AgentClass.PLANNING_SYNTHESIS:
                return AgentPermissions(
                    can_read=True,
                    can_write=False,
                    can_network=False,
                )
            case AgentClass.REGISTRY_STATE:
                return AgentPermissions(
                    can_read=True,
                    can_write=True,
                    can_network=False,
                    allowed_write_paths=("var/registry/", "var/audit/"),
                )
            case AgentClass.WRITE_GATED:
                return AgentPermissions(
                    can_read=True,
                    can_write=True,
                    can_network=False,
                    allowed_write_paths=(
                        "prompts/agents/",
                        "var/artifacts/",
                        "var/cache/",
                    ),
                    disallowed_paths=(
                        "src/",
                        "configs/",
                        "docs/",
                        "tests/",
                        "scripts/",
                        "assets/",
                    ),
                )
            case AgentClass.CONTROL_PLANE:
                return AgentPermissions(
                    can_read=True,
                    can_write=True,
                    can_network=False,
                    allowed_write_paths=(
                        "var/",
                        "prompts/agents/",
                    ),
                    disallowed_paths=(),
                )
            case _:
                return AgentPermissions()


class AgentInput(BaseModel):
    """Input contract for agent execution."""

    repository_root: Path
    parameters: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


class AgentOutput(BaseModel):
    """Output contract from agent execution - must be valid JSON."""

    status: str = Field(description="Either 'success' or 'failure'")
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    timestamp: str = Field(default_factory=lambda: _iso_timestamp())

    model_config = {"extra": "allow"}


class AgentResult(BaseModel):
    """Result of an agent execution attempt."""

    agent_name: str
    agent_class: AgentClass
    status: AgentStatus
    input_data: dict[str, Any]
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    error_type: str | None = None
    execution_time_ms: float | None = None
    timestamp: str = Field(default_factory=lambda: _iso_timestamp())

    def is_success(self) -> bool:
        """Return True if execution succeeded."""
        return self.status == AgentStatus.COMPLETED and self.error_message is None


class WriteRequest(BaseModel):
    """Request for write operation validation."""

    operation: str  # "create", "update", "delete"
    target_path: str
    content: str | None = None
    actor: str


class WriteDecision(BaseModel):
    """Decision from write gate validation."""

    decision: str  # "allow" or "deny"
    operation: str
    target_path: str
    actor: str
    violated_rule_id: str | None = None
    reasoning: str


class GuardrailRequest(BaseModel):
    """Request for guardrail validation."""

    operation_type: str
    target_path: str
    operation_context: dict[str, Any] = Field(default_factory=dict)


class GuardrailDecision(BaseModel):
    """Decision from guardrail validation."""

    decision: str  # "allow" or "deny"
    violated_rule_id: str | None = None
    explanation: str


class VerificationRequest(BaseModel):
    """Request for verification of completed work."""

    work_description: str
    acceptance_criteria: list[str]
    deliverable_paths: list[str]


class VerificationResult(BaseModel):
    """Result from verification."""

    result: str  # "pass" or "fail"
    work_description: str
    criteria_evaluations: list[dict[str, Any]]
    failed_criteria: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)


def _iso_timestamp() -> str:
    """Return current ISO8601 timestamp in UTC."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
