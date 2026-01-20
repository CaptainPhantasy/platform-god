"""
Pydantic response schemas for API endpoints.

All API responses conform to these schemas for consistent output.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentPermissionLevel(str, Enum):
    """Permission levels for filesystem access."""

    READ_ONLY = "read_only"
    WRITE_GATED = "write_gated"
    CONTROL_PLANE = "control_plane"


class AgentClass(str, Enum):
    """Canonical agent classes defining permissions and scope."""

    READ_ONLY_SCAN = "READ_ONLY_SCAN"
    PLANNING_SYNTHESIS = "PLANNING_SYNTHESIS"
    REGISTRY_STATE = "REGISTRY_STATE"
    WRITE_GATED = "WRITE_GATED"
    CONTROL_PLANE = "CONTROL_PLANE"


class AgentStatus(str, Enum):
    """Possible states of agent execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunStatus(str, Enum):
    """Status of a chain run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChainStopReason(str, Enum):
    """Reasons why a chain might stop."""

    COMPLETED = "completed"
    AGENT_FAILED = "agent_failed"
    PRECHECK_FAILED = "precheck_failed"
    STOP_CONDITION = "stop_condition"
    MANUAL = "manual"


class AgentResponse(BaseModel):
    """Response model for a single agent."""

    name: str = Field(..., description="Agent name")
    agent_class: AgentClass = Field(..., description="Agent class")
    role: str = Field(..., description="Agent role description")
    goal: str = Field(..., description="Agent goal")
    permissions: AgentPermissionLevel = Field(..., description="Permission level")
    allowed_paths: list[str] = Field(default_factory=list, description="Allowed write paths")
    disallowed_paths: list[str] = Field(default_factory=list, description="Disallowed paths")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="Input schema")
    output_schema: dict[str, Any] = Field(default_factory=dict, description="Output schema")
    stop_conditions: list[str] = Field(default_factory=list, description="Stop conditions")
    source_file: str = Field(..., description="Source file path")
    content_hash: str = Field(..., description="Content hash")

    model_config = {"extra": "forbid"}


class AgentListResponse(BaseModel):
    """Response model for listing agents."""

    agents: list[AgentResponse] = Field(..., description="List of agents")
    total: int = Field(..., description="Total count of agents")
    limit: int = Field(..., description="Response limit")
    offset: int = Field(..., description="Response offset")

    model_config = {"extra": "forbid"}


class AgentExecutionResult(BaseModel):
    """Result of an agent execution."""

    agent_name: str = Field(..., description="Agent name")
    agent_class: AgentClass = Field(..., description="Agent class")
    status: AgentStatus = Field(..., description="Execution status")
    output_data: dict[str, Any] | None = Field(None, description="Agent output")
    error_message: str | None = Field(None, description="Error message if failed")
    execution_time_ms: float | None = Field(None, description="Execution time in milliseconds")
    timestamp: str = Field(..., description="Execution timestamp")

    model_config = {"extra": "forbid"}


class AgentExecuteResponse(BaseModel):
    """Response model for agent execution."""

    result: AgentExecutionResult = Field(..., description="Execution result")
    mode: str = Field(..., description="Execution mode used")

    model_config = {"extra": "forbid"}


class ChainStepResponse(BaseModel):
    """Response model for a single chain step."""

    agent_name: str = Field(..., description="Agent name")
    status: AgentStatus = Field(..., description="Step status")
    output_key: str | None = Field(None, description="Output state key")
    execution_time_ms: float | None = Field(None, description="Execution time")
    error_message: str | None = Field(None, description="Error if failed")

    model_config = {"extra": "forbid"}


class ChainExecuteResponse(BaseModel):
    """Response model for chain execution."""

    chain_name: str = Field(..., description="Chain name")
    status: ChainStopReason = Field(..., description="Chain completion status")
    completed_steps: int = Field(..., description="Number of completed steps")
    total_steps: int = Field(..., description="Total number of steps")
    steps: list[ChainStepResponse] = Field(..., description="Individual step results")
    final_state: dict[str, Any] = Field(default_factory=dict, description="Final chain state")
    execution_time_ms: float | None = Field(None, description="Total execution time")
    run_id: str | None = Field(None, description="Associated run ID")
    error: str | None = Field(None, description="Error if chain failed")

    model_config = {"extra": "forbid"}


class ChainTypeInfo(BaseModel):
    """Information about a predefined chain type."""

    name: str = Field(..., description="Chain name")
    description: str = Field(..., description="Chain description")
    step_count: int = Field(..., description="Number of steps")
    steps: list[str] = Field(..., description="Agent names in sequence")

    model_config = {"extra": "forbid"}


class ChainListResponse(BaseModel):
    """Response model for listing available chains."""

    chains: list[ChainTypeInfo] = Field(..., description="Available chain types")

    model_config = {"extra": "forbid"}


class RunSummary(BaseModel):
    """Summary information for a chain run."""

    run_id: str = Field(..., description="Unique run identifier")
    chain_name: str = Field(..., description="Chain name")
    repository: str = Field(..., description="Repository name")
    status: RunStatus = Field(..., description="Run status")
    started_at: str = Field(..., description="Start timestamp")
    completed_at: str | None = Field(None, description="Completion timestamp")
    duration_ms: float | None = Field(None, description="Duration in milliseconds")

    model_config = {"extra": "forbid"}


class RunDetail(BaseModel):
    """Detailed information for a chain run."""

    run_id: str = Field(..., description="Unique run identifier")
    chain_name: str = Field(..., description="Chain name")
    repository_root: str = Field(..., description="Repository root path")
    status: RunStatus = Field(..., description="Run status")
    started_at: str = Field(..., description="Start timestamp")
    completed_at: str | None = Field(None, description="Completion timestamp")
    execution_time_ms: float | None = Field(None, description="Execution time")
    agent_results: list[dict[str, Any]] = Field(default_factory=list, description="Agent results")
    final_state: dict[str, Any] = Field(default_factory=dict, description="Final state")
    error: str | None = Field(None, description="Error message if failed")

    model_config = {"extra": "forbid"}


class RunListResponse(BaseModel):
    """Response model for listing runs."""

    runs: list[RunSummary] = Field(..., description="List of run summaries")
    total: int = Field(..., description="Total count matching filters")
    limit: int = Field(..., description="Response limit")
    offset: int = Field(..., description="Response offset")

    model_config = {"extra": "forbid"}


class RegistryEntityResponse(BaseModel):
    """Response model for a registry entity."""

    entity_id: str = Field(..., description="Entity identifier")
    entity_type: str = Field(..., description="Entity type")
    data: dict[str, Any] = Field(..., description="Entity data")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str = Field(..., description="Last update timestamp")
    checksum: str = Field(..., description="Data integrity checksum")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Entity metadata")

    model_config = {"extra": "forbid"}


class RegistryListResponse(BaseModel):
    """Response model for listing registry entities."""

    entities: list[RegistryEntityResponse] = Field(..., description="List of entities")
    entity_type: str | None = Field(None, description="Entity type filter")
    total: int = Field(..., description="Total count")
    limit: int = Field(..., description="Response limit")
    offset: int = Field(..., description="Response offset")

    model_config = {"extra": "forbid"}


class RegistryOperationResponse(BaseModel):
    """Response model for registry operations."""

    status: str = Field(..., description="Operation status")
    operation: str = Field(..., description="Operation performed")
    entity_type: str = Field(..., description="Entity type")
    entity_id: str = Field(..., description="Entity ID")
    audit_ref: str = Field(..., description="Audit log reference")
    checksum: str | None = Field(None, description="Entity checksum after operation")
    error: str | None = Field(None, description="Error message if failed")

    model_config = {"extra": "forbid"}


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Health status")
    version: str = Field(..., description="API version")
    timestamp: str = Field(..., description="Check timestamp")
    components: dict[str, str] = Field(default_factory=dict, description="Component statuses")

    model_config = {"extra": "forbid"}


class ErrorResponse(BaseModel):
    """Standard error response format."""

    error: dict[str, Any] = Field(..., description="Error details")

    model_config = {"extra": "forbid"}
