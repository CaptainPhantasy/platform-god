"""
Platform God Artifacts Module.

Provides artifact storage, retrieval, and lifecycle management for
generated outputs, reports, patches, and other artifacts.
"""

from .models import (
    ArchiveResult,
    Artifact,
    ArtifactListResult,
    ArtifactMetadata,
    ArtifactQuery,
    ArtifactStatus,
    ArtifactType,
    RetentionPolicy,
    StorageResult,
)
from .storage import ArtifactStorage, StorageError
from .retrieval import ArtifactRetriever
from .lifecycle import ArtifactLifecycle

__all__ = [
    # Models
    "Artifact",
    "ArtifactMetadata",
    "ArtifactQuery",
    "ArtifactListResult",
    "ArtifactType",
    "ArtifactStatus",
    "StorageResult",
    "RetentionPolicy",
    "ArchiveResult",
    # Storage
    "ArtifactStorage",
    "StorageError",
    # Retrieval
    "ArtifactRetriever",
    # Lifecycle
    "ArtifactLifecycle",
]
