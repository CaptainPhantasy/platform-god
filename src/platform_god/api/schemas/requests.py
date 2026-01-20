"""
Pydantic request schemas for API endpoints.

All incoming API requests are validated against these schemas.
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ExecutionMode(str, Enum):
    """Execution mode for agents and chains."""

    DRY_RUN = "dry_run"
    """Validate only, don't execute."""

    SIMULATED = "simulated"
    """Return mock output."""

    LIVE = "live"
    """Full LLM execution."""


class ChainType(str, Enum):
    """Predefined chain types."""

    DISCOVERY = "discovery"
    SECURITY_SCAN = "security_scan"
    DEPENDENCY_AUDIT = "dependency_audit"
    DOC_GENERATION = "doc_generation"
    TECH_DEBT = "tech_debt"
    FULL_ANALYSIS = "full_analysis"
    CUSTOM = "custom"


class AgentListRequest(BaseModel):
    """Request parameters for listing agents."""

    agent_class: str | None = Field(
        None,
        description="Filter by agent class",
        examples=["READ_ONLY_SCAN"],
    )
    permissions: str | None = Field(
        None,
        description="Filter by permission level",
        examples=["read_only"],
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results to return",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip",
    )

    model_config = {"extra": "forbid"}


class AgentExecuteRequest(BaseModel):
    """Request to execute a single agent."""

    repository_root: str = Field(
        ...,
        description="Absolute path to the repository root",
        examples=["/path/to/repository"],
    )
    mode: ExecutionMode = Field(
        default=ExecutionMode.DRY_RUN,
        description="Execution mode",
    )
    input_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional input data for the agent",
    )
    timeout_seconds: int | None = Field(
        default=300,
        ge=1,
        le=3600,
        description="Maximum execution time in seconds",
    )

    @field_validator("repository_root")
    @classmethod
    def validate_repository_root(cls, v: str) -> str:
        """Validate repository root path."""
        path = Path(v).resolve()
        if not path.exists():
            raise ValueError(f"Repository root does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Repository root is not a directory: {v}")
        return str(path)

    model_config = {"extra": "forbid"}


class ChainExecuteRequest(BaseModel):
    """Request to execute a chain."""

    chain_type: ChainType = Field(
        ...,
        description="Type of chain to execute",
    )
    repository_root: str = Field(
        ...,
        description="Absolute path to the repository root",
    )
    mode: ExecutionMode = Field(
        default=ExecutionMode.DRY_RUN,
        description="Execution mode",
    )
    initial_state: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial state for the chain",
    )
    steps: list[dict[str, Any]] | None = Field(
        None,
        description="Custom chain steps (required for custom chains)",
    )
    timeout_seconds: int | None = Field(
        default=600,
        ge=1,
        le=3600,
        description="Maximum execution time in seconds",
    )

    @field_validator("repository_root")
    @classmethod
    def validate_repository_root(cls, v: str) -> str:
        """Validate repository root path."""
        path = Path(v).resolve()
        if not path.exists():
            raise ValueError(f"Repository root does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Repository root is not a directory: {v}")
        return str(path)

    @field_validator("steps")
    @classmethod
    def validate_custom_chain(cls, v: list[dict[str, Any]] | None, info: dict[str, Any]) -> list[dict[str, Any]] | None:
        """Validate that custom chains have steps defined."""
        if info.data.get("chain_type") == ChainType.CUSTOM and not v:
            raise ValueError("steps must be provided for custom chains")
        return v

    model_config = {"extra": "forbid"}


class ChainCancelRequest(BaseModel):
    """Request to cancel a running chain."""

    reason: str | None = Field(
        None,
        description="Optional reason for cancellation",
    )

    model_config = {"extra": "forbid"}


class RunListRequest(BaseModel):
    """Request parameters for listing runs."""

    repository_root: str | None = Field(
        None,
        description="Filter by repository root path",
    )
    chain_name: str | None = Field(
        None,
        description="Filter by chain name",
    )
    status: str | None = Field(
        None,
        description="Filter by run status",
        examples=["completed", "failed"],
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum number of results to return",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip",
    )
    started_after: datetime | None = Field(
        None,
        description="Filter runs started after this timestamp",
    )
    started_before: datetime | None = Field(
        None,
        description="Filter runs started before this timestamp",
    )

    model_config = {"extra": "forbid"}


class RegistryEntityRequest(BaseModel):
    """Request to create or update a registry entity."""

    entity_type: str = Field(
        ...,
        description="Type of entity (e.g., 'repository', 'agent', 'finding')",
        examples=["repository"],
    )
    entity_id: str = Field(
        ...,
        description="Unique identifier for the entity",
        examples=["repo_abc123"],
    )
    data: dict[str, Any] = Field(
        ...,
        description="Entity data",
    )
    metadata: dict[str, Any] | None = Field(
        None,
        description="Optional metadata",
    )

    model_config = {"extra": "forbid"}


class RegistryQueryRequest(BaseModel):
    """Request to query registry entities."""

    entity_type: str | None = Field(
        None,
        description="Filter by entity type",
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip",
    )

    model_config = {"extra": "forbid"}


class RegistryUpdateRequest(BaseModel):
    """Request to update a registry entity."""

    data: dict[str, Any] = Field(
        ...,
        description="Updated entity data",
    )
    merge: bool = Field(
        default=True,
        description="Merge with existing data (true) or replace (false)",
    )

    model_config = {"extra": "forbid"}
