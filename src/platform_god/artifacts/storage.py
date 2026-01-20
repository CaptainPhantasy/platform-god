"""
Artifact storage backend.

Handles saving artifacts to var/artifacts/ with support for JSON, text,
and binary content. Generates unique IDs, tracks metadata, and manages
SQLite registry integration.
"""

import hashlib
import json
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import (
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    StorageResult,
)


class StorageError(Enum):
    """Types of storage errors."""

    INVALID_PATH = "invalid_path"
    ALREADY_EXISTS = "already_exists"
    NOT_FOUND = "not_found"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    DATABASE_ERROR = "database_error"
    IO_ERROR = "io_error"
    VALIDATION_ERROR = "validation_error"


class ArtifactStorage:
    """
    Artifact storage backend.

    Manages var/artifacts/ directory structure:
    - var/artifacts/{artifact_type}/{artifact_id}/
    - var/artifacts/{artifact_type}/{artifact_id}/content.{ext}
    - var/artifacts/{artifact_type}/{artifact_id}/metadata.json
    - var/artifacts/.index.db (SQLite registry)

    Thread-safe operations with file-level locking.
    """

    def __init__(
        self,
        artifacts_dir: Path | None = None,
        registry_path: Path | None = None,
    ):
        """
        Initialize artifact storage.

        Args:
            artifacts_dir: Base directory for artifact storage (default: var/artifacts/)
            registry_path: Path to SQLite registry (default: var/artifacts/.index.db)
        """
        self._artifacts_dir = artifacts_dir or Path("var/artifacts")
        self._registry_path = registry_path or self._artifacts_dir / ".index.db"
        self._lock = threading.RLock()
        self._local = threading.local()

        # Ensure directories exist
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Initialize registry database
        self._init_registry()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self._registry_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._executepragma()
        return self._local.conn

    def _executepragma(self) -> None:
        """Configure SQLite pragmas for optimal operation."""
        conn = self._get_connection()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

    def _init_registry(self) -> None:
        """Initialize the SQLite registry schema."""
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS artifact_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artifact_id TEXT NOT NULL UNIQUE,
                artifact_type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                source TEXT,
                agent_run_id TEXT,
                run_id TEXT,
                project_id INTEGER,
                file_path TEXT,
                storage_path TEXT,
                content_hash TEXT,
                size_bytes INTEGER,
                mime_type TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                version INTEGER DEFAULT 1,
                parent_artifact_id TEXT,
                status TEXT DEFAULT 'active',
                is_persistent INTEGER DEFAULT 1,
                tags TEXT,
                custom_metadata TEXT,
                FOREIGN KEY (parent_artifact_id) REFERENCES artifact_index(artifact_id)
            )
        """
        )

        # Create indexes for common queries
        indexes = [
            ("idx_artifact_id", "artifact_id"),
            ("idx_artifact_type", "artifact_type"),
            ("idx_source", "source"),
            ("idx_agent_run_id", "agent_run_id"),
            ("idx_run_id", "run_id"),
            ("idx_project_id", "project_id"),
            ("idx_content_hash", "content_hash"),
            ("idx_status", "status"),
            ("idx_created_at", "created_at"),
        ]

        for idx_name, col in indexes:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {idx_name} ON artifact_index({col})"
            )

        conn.commit()

    def _artifact_dir(self, artifact_id: str, artifact_type: ArtifactType) -> Path:
        """Get the storage directory for an artifact."""
        type_dir = self._artifacts_dir / artifact_type.value
        type_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir = type_dir / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        return artifact_dir

    def _compute_hash(self, data: bytes) -> str:
        """Compute SHA256 hash of data."""
        return hashlib.sha256(data).hexdigest()

    def _compute_hash_streaming(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file with streaming."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def _file_extension(self, artifact_type: ArtifactType, mime_type: str | None = None) -> str:
        """Get appropriate file extension for artifact type."""
        extension_map = {
            ArtifactType.REPORT: ".json",
            ArtifactType.PATCH: ".diff",
            ArtifactType.DOCUMENTATION: ".md",
            ArtifactType.TEST: ".py",
            ArtifactType.CONFIG: ".yaml",
            ArtifactType.BINARY: ".bin",
            ArtifactType.SCAN_RESULT: ".json",
            ArtifactType.CUSTOM: ".dat",
        }

        # Check MIME type for more specific extensions
        if mime_type:
            mime_to_ext = {
                "application/json": ".json",
                "text/plain": ".txt",
                "text/markdown": ".md",
                "text/html": ".html",
                "application/xml": ".xml",
                "application/yaml": ".yaml",
                "application/pdf": ".pdf",
                "application/zip": ".zip",
                "image/png": ".png",
                "image/jpeg": ".jpg",
            }
            if mime_type in mime_to_ext:
                return mime_to_ext[mime_type]

        return extension_map.get(artifact_type, ".dat")

    def _register_in_database(self, metadata: ArtifactMetadata) -> bool:
        """Register artifact metadata in SQLite registry."""
        try:
            conn = self._get_connection()
            conn.execute(
                """
                INSERT INTO artifact_index (
                    artifact_id, artifact_type, title, description, source,
                    agent_run_id, run_id, project_id, file_path, storage_path,
                    content_hash, size_bytes, mime_type, created_at, updated_at,
                    version, parent_artifact_id, status, is_persistent, tags,
                    custom_metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    metadata.artifact_id,
                    metadata.artifact_type.value,
                    metadata.title,
                    metadata.description,
                    metadata.source,
                    metadata.agent_run_id,
                    metadata.run_id,
                    metadata.project_id,
                    str(metadata.file_path) if metadata.file_path else None,
                    str(metadata.storage_path) if metadata.storage_path else None,
                    metadata.content_hash,
                    metadata.size_bytes,
                    metadata.mime_type,
                    metadata.created_at,
                    metadata.updated_at,
                    metadata.version,
                    metadata.parent_artifact_id,
                    metadata.status.value,
                    1 if metadata.is_persistent else 0,
                    json.dumps(metadata.tags) if metadata.tags else None,
                    json.dumps(metadata.custom_metadata) if metadata.custom_metadata else None,
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def _update_in_database(self, metadata: ArtifactMetadata) -> bool:
        """Update artifact metadata in SQLite registry."""
        try:
            conn = self._get_connection()
            conn.execute(
                """
                UPDATE artifact_index SET
                    title = ?, description = ?, source = ?, agent_run_id = ?,
                    run_id = ?, project_id = ?, file_path = ?, storage_path = ?,
                    content_hash = ?, size_bytes = ?, mime_type = ?, updated_at = ?,
                    version = ?, parent_artifact_id = ?, status = ?,
                    is_persistent = ?, tags = ?, custom_metadata = ?
                WHERE artifact_id = ?
                """,
                (
                    metadata.title,
                    metadata.description,
                    metadata.source,
                    metadata.agent_run_id,
                    metadata.run_id,
                    metadata.project_id,
                    str(metadata.file_path) if metadata.file_path else None,
                    str(metadata.storage_path) if metadata.storage_path else None,
                    metadata.content_hash,
                    metadata.size_bytes,
                    metadata.mime_type,
                    metadata.updated_at,
                    metadata.version,
                    metadata.parent_artifact_id,
                    metadata.status.value,
                    1 if metadata.is_persistent else 0,
                    json.dumps(metadata.tags) if metadata.tags else None,
                    json.dumps(metadata.custom_metadata) if metadata.custom_metadata else None,
                    metadata.artifact_id,
                ),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def _delete_from_database(self, artifact_id: str) -> bool:
        """Delete artifact from SQLite registry."""
        try:
            conn = self._get_connection()
            conn.execute(
                "DELETE FROM artifact_index WHERE artifact_id = ?",
                (artifact_id,),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def generate_artifact_id(self) -> str:
        """Generate a unique artifact ID."""
        return str(uuid.uuid4())

    def store(
        self,
        content: str | bytes,
        artifact_type: ArtifactType,
        title: str,
        description: str | None = None,
        source: str | None = None,
        agent_run_id: str | None = None,
        run_id: str | None = None,
        project_id: int | None = None,
        artifact_id: str | None = None,
        mime_type: str | None = None,
        is_persistent: bool = True,
        tags: list[str] | None = None,
        custom_metadata: dict[str, Any] | None = None,
        parent_artifact_id: str | None = None,
    ) -> StorageResult:
        """
        Store an artifact.

        Args:
            content: Artifact content (string or bytes)
            artifact_type: Type of artifact
            title: Human-readable title
            description: Optional description
            source: Source agent or system
            agent_run_id: Associated agent run ID
            run_id: Associated run ID
            project_id: Associated project ID
            artifact_id: Custom artifact ID (auto-generated if None)
            mime_type: MIME type of content
            is_persistent: Whether artifact persists across cleanups
            tags: Searchable tags
            custom_metadata: Additional metadata
            parent_artifact_id: Parent artifact for versioning

        Returns:
            StorageResult with operation outcome
        """
        with self._lock:
            try:
                # Generate ID if not provided
                if artifact_id is None:
                    artifact_id = self.generate_artifact_id()

                # Convert content to bytes
                if isinstance(content, str):
                    content_bytes = content.encode("utf-8")
                else:
                    content_bytes = content

                # Compute checksum
                content_hash = self._compute_hash(content_bytes)
                size_bytes = len(content_bytes)

                # Create artifact directory
                artifact_dir = self._artifact_dir(artifact_id, artifact_type)
                extension = self._file_extension(artifact_type, mime_type)
                content_path = artifact_dir / f"content{extension}"
                metadata_path = artifact_dir / "metadata.json"

                # Write content
                with open(content_path, "wb") as f:
                    f.write(content_bytes)

                # Create metadata
                metadata = ArtifactMetadata(
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    title=title,
                    description=description,
                    source=source,
                    agent_run_id=agent_run_id,
                    run_id=run_id,
                    project_id=project_id,
                    storage_path=content_path,
                    content_hash=content_hash,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    is_persistent=is_persistent,
                    tags=tags or [],
                    custom_metadata=custom_metadata or {},
                    parent_artifact_id=parent_artifact_id,
                )

                # Write metadata file
                metadata_path.write_text(metadata.model_dump_json(indent=2))

                # Register in database
                if not self._register_in_database(metadata):
                    return StorageResult(
                        success=False,
                        error="Failed to register in database",
                    )

                return StorageResult(
                    success=True,
                    artifact_id=artifact_id,
                    storage_path=content_path,
                    checksum=content_hash,
                )

            except (OSError, IOError) as e:
                return StorageResult(
                    success=False,
                    error=f"I/O error: {e}",
                )
            except Exception as e:
                return StorageResult(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

    def store_streaming(
        self,
        source_path: Path,
        artifact_type: ArtifactType,
        title: str,
        description: str | None = None,
        source: str | None = None,
        agent_run_id: str | None = None,
        run_id: str | None = None,
        project_id: int | None = None,
        artifact_id: str | None = None,
        mime_type: str | None = None,
        is_persistent: bool = True,
        tags: list[str] | None = None,
        custom_metadata: dict[str, Any] | None = None,
        chunk_size: int = 8192,
    ) -> StorageResult:
        """
        Store a large file as an artifact with streaming.

        Args:
            source_path: Path to source file
            artifact_type: Type of artifact
            title: Human-readable title
            description: Optional description
            source: Source agent or system
            agent_run_id: Associated agent run ID
            run_id: Associated run ID
            project_id: Associated project ID
            artifact_id: Custom artifact ID (auto-generated if None)
            mime_type: MIME type of content
            is_persistent: Whether artifact persists across cleanups
            tags: Searchable tags
            custom_metadata: Additional metadata
            chunk_size: Chunk size for streaming

        Returns:
            StorageResult with operation outcome
        """
        with self._lock:
            try:
                # Validate source
                if not source_path.exists():
                    return StorageResult(
                        success=False,
                        error=f"Source file not found: {source_path}",
                    )

                # Generate ID if not provided
                if artifact_id is None:
                    artifact_id = self.generate_artifact_id()

                # Get file size
                size_bytes = source_path.stat().st_size

                # Create artifact directory
                artifact_dir = self._artifact_dir(artifact_id, artifact_type)
                extension = self._file_extension(artifact_type, mime_type)
                content_path = artifact_dir / f"content{extension}"
                metadata_path = artifact_dir / "metadata.json"

                # Stream copy with hashing
                hasher = hashlib.sha256()
                with open(source_path, "rb") as src, open(content_path, "wb") as dst:
                    while True:
                        chunk = src.read(chunk_size)
                        if not chunk:
                            break
                        dst.write(chunk)
                        hasher.update(chunk)

                content_hash = hasher.hexdigest()

                # Create metadata
                metadata = ArtifactMetadata(
                    artifact_id=artifact_id,
                    artifact_type=artifact_type,
                    title=title,
                    description=description,
                    source=source,
                    agent_run_id=agent_run_id,
                    run_id=run_id,
                    project_id=project_id,
                    file_path=source_path,
                    storage_path=content_path,
                    content_hash=content_hash,
                    size_bytes=size_bytes,
                    mime_type=mime_type,
                    is_persistent=is_persistent,
                    tags=tags or [],
                    custom_metadata=custom_metadata or {},
                )

                # Write metadata file
                metadata_path.write_text(metadata.model_dump_json(indent=2))

                # Register in database
                if not self._register_in_database(metadata):
                    return StorageResult(
                        success=False,
                        error="Failed to register in database",
                    )

                return StorageResult(
                    success=True,
                    artifact_id=artifact_id,
                    storage_path=content_path,
                    checksum=content_hash,
                )

            except (OSError, IOError) as e:
                return StorageResult(
                    success=False,
                    error=f"I/O error: {e}",
                )
            except Exception as e:
                return StorageResult(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

    def update_metadata(
        self,
        artifact_id: str,
        title: str | None = None,
        description: str | None = None,
        status: ArtifactStatus | None = None,
        tags: list[str] | None = None,
        custom_metadata: dict[str, Any] | None = None,
    ) -> StorageResult:
        """
        Update artifact metadata.

        Args:
            artifact_id: ID of artifact to update
            title: New title
            description: New description
            status: New status
            tags: New tags (replaces existing)
            custom_metadata: New custom metadata (merged with existing)

        Returns:
            StorageResult with operation outcome
        """
        with self._lock:
            try:
                # Load existing metadata
                metadata = self._load_metadata_from_disk(artifact_id)
                if metadata is None:
                    return StorageResult(
                        success=False,
                        error="Artifact not found",
                    )

                # Update fields
                if title is not None:
                    metadata.title = title
                if description is not None:
                    metadata.description = description
                if status is not None:
                    metadata.status = status
                if tags is not None:
                    metadata.tags = tags
                if custom_metadata is not None:
                    metadata.custom_metadata = {
                        **metadata.custom_metadata,
                        **custom_metadata,
                    }

                metadata.updated_at = datetime.now(timezone.utc).isoformat()

                # Write metadata file
                if metadata.storage_path:
                    metadata_path = metadata.storage_path.parent / "metadata.json"
                    metadata_path.write_text(metadata.model_dump_json(indent=2))

                # Update database
                if not self._update_in_database(metadata):
                    return StorageResult(
                        success=False,
                        error="Failed to update in database",
                    )

                return StorageResult(
                    success=True,
                    artifact_id=artifact_id,
                )

            except Exception as e:
                return StorageResult(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

    def _load_metadata_from_disk(self, artifact_id: str) -> ArtifactMetadata | None:
        """Load metadata from disk by scanning artifact directories."""
        for artifact_type in ArtifactType:
            type_dir = self._artifacts_dir / artifact_type.value
            artifact_dir = type_dir / artifact_id
            metadata_path = artifact_dir / "metadata.json"

            if metadata_path.exists():
                try:
                    data = json.loads(metadata_path.read_text())
                    return ArtifactMetadata(**data)
                except (json.JSONDecodeError, ValidationError):
                    continue
        return None

    def load_content(self, artifact_id: str) -> tuple[bytes | None, ArtifactMetadata | None]:
        """
        Load artifact content.

        Args:
            artifact_id: ID of artifact to load

        Returns:
            Tuple of (content_bytes, metadata)
        """
        with self._lock:
            try:
                metadata = self._load_metadata_from_disk(artifact_id)
                if metadata is None or metadata.storage_path is None:
                    return None, None

                content_path = metadata.storage_path
                if not content_path.exists():
                    return None, metadata

                content = content_path.read_bytes()
                return content, metadata

            except (OSError, IOError):
                return None, None

    def load_content_as_text(self, artifact_id: str) -> tuple[str | None, ArtifactMetadata | None]:
        """
        Load artifact content as text.

        Args:
            artifact_id: ID of artifact to load

        Returns:
            Tuple of (content_text, metadata)
        """
        content_bytes, metadata = self.load_content(artifact_id)
        if content_bytes is None:
            return None, metadata

        try:
            return content_bytes.decode("utf-8"), metadata
        except UnicodeDecodeError:
            return None, metadata

    def verify_integrity(self, artifact_id: str) -> bool:
        """
        Verify artifact checksum matches stored value.

        Args:
            artifact_id: ID of artifact to verify

        Returns:
            True if checksum is valid
        """
        with self._lock:
            try:
                metadata = self._load_metadata_from_disk(artifact_id)
                if metadata is None or metadata.storage_path is None:
                    return False

                if not metadata.storage_path.exists():
                    return False

                computed_hash = self._compute_hash_streaming(metadata.storage_path)
                return computed_hash == metadata.content_hash

            except (OSError, IOError):
                return False

    def delete_artifact(
        self,
        artifact_id: str,
        delete_from_disk: bool = False,
    ) -> StorageResult:
        """
        Delete an artifact.

        Args:
            artifact_id: ID of artifact to delete
            delete_from_disk: Whether to delete from disk (default: marks as deleted)

        Returns:
            StorageResult with operation outcome
        """
        with self._lock:
            try:
                metadata = self._load_metadata_from_disk(artifact_id)
                if metadata is None:
                    return StorageResult(
                        success=False,
                        error="Artifact not found",
                    )

                if delete_from_disk:
                    # Delete from disk
                    if metadata.storage_path:
                        artifact_dir = metadata.storage_path.parent
                        shutil.rmtree(artifact_dir, ignore_errors=True)

                    # Delete from database
                    self._delete_from_database(artifact_id)
                else:
                    # Mark as deleted
                    metadata.status = ArtifactStatus.DELETED
                    metadata.updated_at = datetime.now(timezone.utc).isoformat()

                    if metadata.storage_path:
                        metadata_path = metadata.storage_path.parent / "metadata.json"
                        metadata_path.write_text(metadata.model_dump_json(indent=2))

                    self._update_in_database(metadata)

                return StorageResult(
                    success=True,
                    artifact_id=artifact_id,
                )

            except Exception as e:
                return StorageResult(
                    success=False,
                    error=f"Unexpected error: {e}",
                )

    def get_storage_stats(self) -> dict[str, Any]:
        """Get statistics about artifact storage."""
        with self._lock:
            try:
                conn = self._get_connection()
                cursor = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_count,
                        SUM(size_bytes) as total_size,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,
                        COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived_count,
                        COUNT(CASE WHEN status = 'deleted' THEN 1 END) as deleted_count
                    FROM artifact_index
                    """
                )
                row = cursor.fetchone()

                # Count by type
                cursor = conn.execute(
                    """
                    SELECT artifact_type, COUNT(*) as count
                    FROM artifact_index
                    WHERE status = 'active'
                    GROUP BY artifact_type
                """
                )
                by_type = {r["artifact_type"]: r["count"] for r in cursor.fetchall()}

                return {
                    "total_count": row["total_count"] or 0,
                    "total_size_bytes": row["total_size"] or 0,
                    "active_count": row["active_count"] or 0,
                    "archived_count": row["archived_count"] or 0,
                    "deleted_count": row["deleted_count"] or 0,
                    "by_type": by_type,
                    "storage_path": str(self._artifacts_dir),
                }

            except sqlite3.Error:
                return {}

    def close(self) -> None:
        """Close database connections (call on shutdown)."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
