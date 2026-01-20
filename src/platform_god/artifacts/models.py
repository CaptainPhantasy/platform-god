"""
Pydantic models for artifact storage and retrieval.

Defines schemas for artifacts, metadata, and queries used throughout
the artifacts module.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ArtifactType(Enum):
    """Types of artifacts that can be stored."""

    REPORT = "report"
    PATCH = "patch"
    DOCUMENTATION = "documentation"
    TEST = "test"
    CONFIG = "config"
    BINARY = "binary"
    SCAN_RESULT = "scan_result"
    CUSTOM = "custom"


class ArtifactStatus(Enum):
    """Lifecycle status of an artifact."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"
    PENDING_DELETION = "pending_deletion"


class ArtifactMetadata(BaseModel):
    """Metadata associated with an artifact."""

    artifact_id: str = Field(description="Unique UUID for the artifact")
    artifact_type: ArtifactType = Field(description="Type of artifact")
    title: str = Field(description="Human-readable title")
    description: str | None = Field(default=None, description="Optional description")
    source: str | None = Field(
        default=None, description="Source agent or system that created the artifact"
    )
    agent_run_id: str | None = Field(default=None, description="Associated agent run ID")
    run_id: str | None = Field(default=None, description="Associated run ID")
    project_id: int | None = Field(default=None, description="Associated project ID")
    file_path: Path | None = Field(default=None, description="Local filesystem path")
    storage_path: Path | None = Field(
        default=None, description="Storage path within var/artifacts/"
    )
    content_hash: str | None = Field(
        default=None, description="SHA256 hash of content"
    )
    size_bytes: int | None = Field(default=None, description="Size in bytes")
    mime_type: str | None = Field(default=None, description="MIME type if applicable")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp of creation",
    )
    updated_at: str | None = Field(
        default=None, description="ISO timestamp of last update"
    )
    version: int = Field(default=1, description="Artifact version number")
    parent_artifact_id: str | None = Field(
        default=None, description="Parent artifact if this is a version"
    )
    status: ArtifactStatus = Field(
        default=ArtifactStatus.ACTIVE, description="Current status"
    )
    is_persistent: bool = Field(
        default=True, description="Whether artifact should persist across cleanups"
    )
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    custom_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional custom metadata"
    )

    @field_validator("artifact_type", mode="before")
    @classmethod
    def validate_artifact_type(cls, v):
        """Convert string to ArtifactType enum."""
        if isinstance(v, str):
            try:
                return ArtifactType(v)
            except ValueError:
                return ArtifactType.CUSTOM
        return v

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        """Convert string to ArtifactStatus enum."""
        if isinstance(v, str):
            try:
                return ArtifactStatus(v)
            except ValueError:
                return ArtifactStatus.ACTIVE
        return v


class Artifact(BaseModel):
    """Complete artifact record with content."""

    metadata: ArtifactMetadata = Field(description="Artifact metadata")
    content: str | bytes | None = Field(
        default=None, description="Artifact content (None if stored on disk)"
    )

    def is_binary(self) -> bool:
        """Return True if content is binary."""
        return isinstance(self.content, bytes)

    def is_stored_on_disk(self) -> bool:
        """Return True if artifact is stored on disk rather than in memory."""
        return self.content is None and self.metadata.storage_path is not None

    def get_content_size(self) -> int:
        """Return size of content in bytes."""
        if self.content is None:
            return self.metadata.size_bytes or 0
        if isinstance(self.content, bytes):
            return len(self.content)
        return len(self.content.encode("utf-8"))


class ArtifactQuery(BaseModel):
    """Query parameters for searching artifacts."""

    artifact_id: str | None = Field(default=None, description="Exact artifact ID match")
    artifact_type: ArtifactType | list[ArtifactType] | None = Field(
        default=None, description="Filter by artifact type(s)"
    )
    source: str | None = Field(default=None, description="Filter by source")
    agent_run_id: str | None = Field(default=None, description="Filter by agent run ID")
    run_id: str | None = Field(default=None, description="Filter by run ID")
    project_id: int | None = Field(default=None, description="Filter by project ID")
    status: ArtifactStatus | list[ArtifactStatus] | None = Field(
        default=ArtifactStatus.ACTIVE, description="Filter by status"
    )
    tags: list[str] | None = Field(
        default=None, description="Filter by tags (all must match)"
    )
    content_hash: str | None = Field(
        default=None, description="Filter by content hash (deduplication)"
    )
    created_after: str | None = Field(
        default=None, description="ISO timestamp filter - created after"
    )
    created_before: str | None = Field(
        default=None, description="ISO timestamp filter - created before"
    )
    title_contains: str | None = Field(
        default=None, description="Filter by title substring"
    )
    description_contains: str | None = Field(
        default=None, description="Filter by description substring"
    )
    is_persistent: bool | None = Field(
        default=None, description="Filter by persistence flag"
    )
    min_size_bytes: int | None = Field(
        default=None, description="Minimum size filter"
    )
    max_size_bytes: int | None = Field(
        default=None, description="Maximum size filter"
    )

    # Pagination
    offset: int = Field(default=0, ge=0, description="Pagination offset")
    limit: int = Field(default=100, ge=1, le=1000, description="Max results to return")

    # Sorting
    sort_by: str = Field(
        default="created_at",
        description="Field to sort by (created_at, updated_at, size_bytes, title)",
    )
    sort_order: str = Field(
        default="desc", description="Sort order: 'asc' or 'desc'"
    )

    @field_validator("artifact_type", mode="before")
    @classmethod
    def validate_artifact_type(cls, v):
        """Convert string to ArtifactType enum."""
        if isinstance(v, str):
            try:
                return ArtifactType(v)
            except ValueError:
                return ArtifactType.CUSTOM
        if isinstance(v, list) and v and isinstance(v[0], str):
            return [ArtifactType(x) if x in [at.value for at in ArtifactType] else ArtifactType.CUSTOM for x in v]
        return v

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, v):
        """Convert string to ArtifactStatus enum."""
        if isinstance(v, str):
            return ArtifactStatus(v)
        if isinstance(v, list) and v:
            return [ArtifactStatus(x) for x in v]
        return v

    @field_validator("sort_order")
    @classmethod
    def validate_sort_order(cls, v):
        """Ensure sort_order is valid."""
        if v not in ("asc", "desc"):
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


class ArtifactListResult(BaseModel):
    """Result of an artifact list query."""

    artifacts: list[ArtifactMetadata] = Field(
        description="List of artifact metadata matching query"
    )
    total_count: int = Field(description="Total count matching query (before pagination)")
    returned_count: int = Field(description="Number of artifacts in this page")
    offset: int = Field(description="Current offset")
    limit: int = Field(description="Current limit")
    has_more: bool = Field(description="Whether more results exist")


class StorageResult(BaseModel):
    """Result of an artifact storage operation."""

    success: bool = Field(description="Whether operation succeeded")
    artifact_id: str | None = Field(default=None, description="Artifact ID if created")
    storage_path: Path | None = Field(default=None, description="Path where stored")
    error: str | None = Field(default=None, description="Error message if failed")
    checksum: str | None = Field(default=None, description="SHA256 checksum if stored")


class RetentionPolicy(BaseModel):
    """Retention policy for artifact lifecycle management."""

    max_age_days: int | None = Field(
        default=None, description="Maximum age in days before cleanup"
    )
    max_versions: int | None = Field(
        default=None, description="Maximum versions to keep per artifact"
    )
    max_total_size_mb: int | None = Field(
        default=None, description="Maximum total storage before cleanup"
    )
    keep_persistent: bool = Field(
        default=True, description="Never delete persistent artifacts"
    )
    keep_types: list[ArtifactType] = Field(
        default_factory=list, description="Artifact types to never delete"
    )
    archive_before_delete: bool = Field(
        default=True, description="Archive before permanent deletion"
    )
    archive_path: Path | None = Field(
        default=None, description="Custom archive path"
    )


class ArchiveResult(BaseModel):
    """Result of an archive operation."""

    success: bool = Field(description="Whether operation succeeded")
    archived_count: int = Field(default=0, description="Number of artifacts archived")
    deleted_count: int = Field(default=0, description="Number of artifacts deleted")
    freed_bytes: int = Field(default=0, description="Bytes of storage freed")
    errors: list[str] = Field(default_factory=list, description="Any errors encountered")
