"""
Artifact lifecycle management.

Handles artifact archiving, deletion with retention policies, and
versioning operations.
"""

import shutil
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

from pydantic import ValidationError

from .models import (
    ArchiveResult,
    ArtifactMetadata,
    ArtifactStatus,
    ArtifactType,
    RetentionPolicy,
)
from .storage import ArtifactStorage
from .retrieval import ArtifactRetriever


class ArtifactLifecycle:
    """
    Artifact lifecycle management.

    Manages artifact lifecycle operations including:
    - Archiving old artifacts
    - Applying retention policies
    - Cleanup of deleted artifacts
    - Version management
    """

    DEFAULT_ARCHIVE_DIR = Path("var/artifacts/.archive")

    def __init__(
        self,
        storage: ArtifactStorage | None = None,
        retriever: ArtifactRetriever | None = None,
    ):
        """
        Initialize lifecycle manager.

        Args:
            storage: ArtifactStorage instance
            retriever: ArtifactRetriever instance
        """
        self._storage = storage or ArtifactStorage()
        self._retriever = retriever or ArtifactRetriever(self._storage)
        self._lock = threading.RLock()
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local SQLite connection."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            registry_path = self._storage._registry_path
            self._local.conn = sqlite3.connect(
                str(registry_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _get_archive_dir(self, custom_path: Path | None = None) -> Path:
        """Get or create archive directory."""
        archive_dir = custom_path or self.DEFAULT_ARCHIVE_DIR
        archive_dir.mkdir(parents=True, exist_ok=True)
        return archive_dir

    def _archive_to_directory(
        self,
        metadata: ArtifactMetadata,
        archive_dir: Path,
    ) -> bool:
        """Move artifact to archive directory."""
        try:
            if metadata.storage_path is None:
                return False

            source_dir = metadata.storage_path.parent
            if not source_dir.exists():
                return False

            # Create archive subdirectory by type
            type_archive = archive_dir / metadata.artifact_type.value
            type_archive.mkdir(parents=True, exist_ok=True)

            # Move to archive
            target_dir = type_archive / metadata.artifact_id
            if target_dir.exists():
                shutil.rmtree(target_dir)

            shutil.move(str(source_dir), str(target_dir))

            # Update metadata to reflect archive location
            new_storage_path = target_dir / metadata.storage_path.name
            from .models import ArtifactMetadata as AM
            updated_metadata = AM(
                **metadata.model_dump(),
                storage_path=new_storage_path,
                status=ArtifactStatus.ARCHIVED,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

            # Update in database
            conn = self._get_connection()
            conn.execute(
                """
                UPDATE artifact_index SET
                    storage_path = ?, status = ?, updated_at = ?
                WHERE artifact_id = ?
                """,
                (
                    str(new_storage_path),
                    ArtifactStatus.ARCHIVED.value,
                    updated_metadata.updated_at,
                    metadata.artifact_id,
                ),
            )
            conn.commit()

            return True

        except (OSError, shutil.Error):
            return False

    def archive_by_age(
        self,
        days: int,
        keep_persistent: bool = True,
        archive_path: Path | None = None,
        dry_run: bool = False,
    ) -> ArchiveResult:
        """
        Archive artifacts older than specified days.

        Args:
            days: Age threshold in days
            keep_persistent: Whether to skip persistent artifacts
            archive_path: Custom archive directory
            dry_run: If True, don't actually move files

        Returns:
            ArchiveResult with operation details
        """
        with self._lock:
            result = ArchiveResult(success=True)

            try:
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

                query = f"""
                SELECT * FROM artifact_index
                WHERE status = 'active'
                    AND created_at < ?
                    AND (is_persistent = 0 OR ? = 0)
                """

                conn = self._get_connection()
                rows = conn.execute(query, (cutoff_date, int(keep_persistent))).fetchall()

                archive_dir = self._get_archive_dir(archive_path) if not dry_run else None

                for row in rows:
                    try:
                        metadata = self._retriever._row_to_metadata(row)

                        if dry_run:
                            result.archived_count += 1
                            if metadata.size_bytes:
                                result.freed_bytes += metadata.size_bytes
                        else:
                            if self._archive_to_directory(metadata, archive_dir):  # type: ignore
                                result.archived_count += 1
                                if metadata.size_bytes:
                                    result.freed_bytes += metadata.size_bytes
                            else:
                                result.errors.append(f"Failed to archive {metadata.artifact_id}")

                    except (ValidationError, ValueError):
                        result.errors.append(f"Invalid artifact data for {row['artifact_id']}")

            except sqlite3.Error as e:
                result.success = False
                result.errors.append(f"Database error: {e}")

            return result

    def archive_by_type(
        self,
        artifact_type: ArtifactType,
        days: int = 30,
        keep_persistent: bool = True,
        archive_path: Path | None = None,
        dry_run: bool = False,
    ) -> ArchiveResult:
        """
        Archive artifacts of a specific type older than specified days.

        Args:
            artifact_type: Type of artifacts to archive
            days: Age threshold in days
            keep_persistent: Whether to skip persistent artifacts
            archive_path: Custom archive directory
            dry_run: If True, don't actually move files

        Returns:
            ArchiveResult with operation details
        """
        with self._lock:
            result = ArchiveResult(success=True)

            try:
                cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

                query = """
                SELECT * FROM artifact_index
                WHERE artifact_type = ?
                    AND status = 'active'
                    AND created_at < ?
                    AND (is_persistent = 0 OR ? = 0)
                """

                conn = self._get_connection()
                rows = conn.execute(
                    query,
                    (artifact_type.value, cutoff_date, int(keep_persistent)),
                ).fetchall()

                archive_dir = self._get_archive_dir(archive_path) if not dry_run else None

                for row in rows:
                    try:
                        metadata = self._retriever._row_to_metadata(row)

                        if dry_run:
                            result.archived_count += 1
                            if metadata.size_bytes:
                                result.freed_bytes += metadata.size_bytes
                        else:
                            if self._archive_to_directory(metadata, archive_dir):  # type: ignore
                                result.archived_count += 1
                                if metadata.size_bytes:
                                    result.freed_bytes += metadata.size_bytes
                            else:
                                result.errors.append(f"Failed to archive {metadata.artifact_id}")

                    except (ValidationError, ValueError):
                        result.errors.append(f"Invalid artifact data for {row['artifact_id']}")

            except sqlite3.Error as e:
                result.success = False
                result.errors.append(f"Database error: {e}")

            return result

    def apply_retention_policy(
        self,
        policy: RetentionPolicy,
        dry_run: bool = False,
    ) -> ArchiveResult:
        """
        Apply a retention policy to artifacts.

        This is the main method for lifecycle management that:
        1. Archives artifacts older than max_age_days
        2. Limits versions per artifact to max_versions
        3. Cleans up if storage exceeds max_total_size_mb

        Args:
            policy: RetentionPolicy defining rules
            dry_run: If True, don't actually move/delete files

        Returns:
            ArchiveResult with operation details
        """
        with self._lock:
            result = ArchiveResult(success=True)
            archive_dir = self._get_archive_dir(policy.archive_path) if not dry_run else None

            try:
                conn = self._get_connection()

                # Phase 1: Archive by age
                if policy.max_age_days:
                    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=policy.max_age_days)).isoformat()

                    # Build exclusion for persistent and protected types
                    protected_types = [t.value for t in policy.keep_types]
                    type_exclusion = ""
                    params = [cutoff_date, int(policy.keep_persistent)]

                    if protected_types:
                        placeholders = ",".join("?" * len(protected_types))
                        type_exclusion = f"AND artifact_type NOT IN ({placeholders})"
                        params.extend(protected_types)

                    query = f"""
                    SELECT * FROM artifact_index
                    WHERE status = 'active'
                        AND created_at < ?
                        AND (is_persistent = 0 OR ? = 0)
                        {type_exclusion}
                    """

                    rows = conn.execute(query, params).fetchall()

                    for row in rows:
                        try:
                            metadata = self._retriever._row_to_metadata(row)

                            if dry_run:
                                if policy.archive_before_delete:
                                    result.archived_count += 1
                                else:
                                    result.deleted_count += 1
                                if metadata.size_bytes:
                                    result.freed_bytes += metadata.size_bytes
                            else:
                                if policy.archive_before_delete:
                                    if self._archive_to_directory(metadata, archive_dir):  # type: ignore
                                        result.archived_count += 1
                                        if metadata.size_bytes:
                                            result.freed_bytes += metadata.size_bytes
                                    else:
                                        result.errors.append(f"Failed to archive {metadata.artifact_id}")
                                else:
                                    # Direct deletion
                                    if self._delete_artifact_files(metadata):
                                        self._mark_deleted(metadata.artifact_id)
                                        result.deleted_count += 1
                                        if metadata.size_bytes:
                                            result.freed_bytes += metadata.size_bytes
                                    else:
                                        result.errors.append(f"Failed to delete {metadata.artifact_id}")

                        except (ValidationError, ValueError):
                            result.errors.append(f"Invalid artifact data for {row['artifact_id']}")

                # Phase 2: Limit versions per artifact
                if policy.max_versions:
                    rows = conn.execute(
                        """
                        SELECT parent_artifact_id, COUNT(*) as version_count
                        FROM artifact_index
                        WHERE status = 'active' AND parent_artifact_id IS NOT NULL
                        GROUP BY parent_artifact_id
                        HAVING version_count > ?
                        """,
                        (policy.max_versions,),
                    ).fetchall()

                    for row in rows:
                        parent_id = row["parent_artifact_id"]
                        excess_count = row["version_count"] - policy.max_versions

                        # Get oldest excess versions
                        excess_rows = conn.execute(
                            """
                            SELECT * FROM artifact_index
                            WHERE parent_artifact_id = ?
                                AND status = 'active'
                            ORDER BY created_at ASC
                            LIMIT ?
                            """,
                            (parent_id, excess_count),
                        ).fetchall()

                        for excess_row in excess_rows:
                            try:
                                metadata = self._retriever._row_to_metadata(excess_row)

                                if dry_run:
                                    if policy.archive_before_delete:
                                        result.archived_count += 1
                                    else:
                                        result.deleted_count += 1
                                    if metadata.size_bytes:
                                        result.freed_bytes += metadata.size_bytes
                                else:
                                    if policy.archive_before_delete:
                                        if self._archive_to_directory(metadata, archive_dir):  # type: ignore
                                            result.archived_count += 1
                                            if metadata.size_bytes:
                                                result.freed_bytes += metadata.size_bytes
                                        else:
                                            result.errors.append(f"Failed to archive {metadata.artifact_id}")
                                    else:
                                        if self._delete_artifact_files(metadata):
                                            self._mark_deleted(metadata.artifact_id)
                                            result.deleted_count += 1
                                            if metadata.size_bytes:
                                                result.freed_bytes += metadata.size_bytes
                                        else:
                                            result.errors.append(f"Failed to delete {metadata.artifact_id}")

                            except (ValidationError, ValueError):
                                result.errors.append(f"Invalid artifact data for {excess_row['artifact_id']}")

                # Phase 3: Check total storage size
                if policy.max_total_size_mb:
                    max_bytes = policy.max_total_size_mb * 1024 * 1024

                    # Get current total size
                    size_row = conn.execute(
                        """
                        SELECT COALESCE(SUM(size_bytes), 0) as total_size
                        FROM artifact_index
                        WHERE status = 'active'
                            AND (is_persistent = 0 OR ? = 0)
                        """,
                        (int(policy.keep_persistent),),
                    ).fetchone()

                    current_size = size_row["total_size"] if size_row else 0

                    if current_size > max_bytes:
                        excess_bytes = current_size - max_bytes

                        # Get oldest artifacts to delete
                        rows = conn.execute(
                            """
                            SELECT * FROM artifact_index
                            WHERE status = 'active'
                                AND (is_persistent = 0 OR ? = 0)
                            ORDER BY created_at ASC
                            """,
                            (int(policy.keep_persistent),),
                        ).fetchall()

                        freed_so_far = 0

                        for row in rows:
                            if freed_so_far >= excess_bytes:
                                break

                            try:
                                metadata = self._retriever._row_to_metadata(row)
                                artifact_size = metadata.size_bytes or 0

                                if dry_run:
                                    if policy.archive_before_delete:
                                        result.archived_count += 1
                                    else:
                                        result.deleted_count += 1
                                    result.freed_bytes += artifact_size
                                    freed_so_far += artifact_size
                                else:
                                    if policy.archive_before_delete:
                                        if self._archive_to_directory(metadata, archive_dir):  # type: ignore
                                            result.archived_count += 1
                                            result.freed_bytes += artifact_size
                                            freed_so_far += artifact_size
                                        else:
                                            result.errors.append(f"Failed to archive {metadata.artifact_id}")
                                    else:
                                        if self._delete_artifact_files(metadata):
                                            self._mark_deleted(metadata.artifact_id)
                                            result.deleted_count += 1
                                            result.freed_bytes += artifact_size
                                            freed_so_far += artifact_size
                                        else:
                                            result.errors.append(f"Failed to delete {metadata.artifact_id}")

                            except (ValidationError, ValueError):
                                result.errors.append(f"Invalid artifact data for {row['artifact_id']}")

            except sqlite3.Error as e:
                result.success = False
                result.errors.append(f"Database error: {e}")

            return result

    def _delete_artifact_files(self, metadata: ArtifactMetadata) -> bool:
        """Delete artifact files from disk."""
        try:
            if metadata.storage_path:
                artifact_dir = metadata.storage_path.parent
                if artifact_dir.exists():
                    shutil.rmtree(artifact_dir)
            return True
        except (OSError, shutil.Error):
            return False

    def _mark_deleted(self, artifact_id: str) -> bool:
        """Mark artifact as deleted in database."""
        try:
            conn = self._get_connection()
            conn.execute(
                "UPDATE artifact_index SET status = 'deleted', updated_at = ? WHERE artifact_id = ?",
                (datetime.now(timezone.utc).isoformat(), artifact_id),
            )
            conn.commit()
            return True
        except sqlite3.Error:
            return False

    def cleanup_deleted(self, older_than_days: int = 7, dry_run: bool = False) -> ArchiveResult:
        """
        Permanently delete artifacts marked as deleted.

        Args:
            older_than_days: Only delete artifacts marked deleted more than this many days ago
            dry_run: If True, don't actually delete files

        Returns:
            ArchiveResult with operation details
        """
        with self._lock:
            result = ArchiveResult(success=True)

            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

                conn = self._get_connection()

                # Get deleted artifacts
                rows = conn.execute(
                    """
                    SELECT * FROM artifact_index
                    WHERE status = 'deleted'
                    LIMIT 1000
                    """
                ).fetchall()

                for row in rows:
                    try:
                        # Parse updated_at to check if old enough
                        updated_at = datetime.fromisoformat(row["updated_at"])
                        if updated_at > cutoff_date:
                            continue

                        metadata = self._retriever._row_to_metadata(row)

                        if dry_run:
                            result.deleted_count += 1
                            if metadata.size_bytes:
                                result.freed_bytes += metadata.size_bytes
                        else:
                            # Delete files
                            if self._delete_artifact_files(metadata):
                                # Remove from database
                                conn.execute(
                                    "DELETE FROM artifact_index WHERE artifact_id = ?",
                                    (metadata.artifact_id,),
                                )
                                conn.commit()
                                result.deleted_count += 1
                                if metadata.size_bytes:
                                    result.freed_bytes += metadata.size_bytes
                            else:
                                result.errors.append(f"Failed to delete files for {metadata.artifact_id}")

                    except (ValidationError, ValueError):
                        result.errors.append(f"Invalid artifact data for {row['artifact_id']}")

            except sqlite3.Error as e:
                result.success = False
                result.errors.append(f"Database error: {e}")

            return result

    def create_version(
        self,
        parent_artifact_id: str,
        new_content: str | bytes | None = None,
        title: str | None = None,
        description: str | None = None,
    ) -> ArtifactMetadata | None:
        """
        Create a new version of an existing artifact.

        Args:
            parent_artifact_id: ID of the parent artifact
            new_content: New content (uses parent content if None)
            title: New title (uses parent title if None)
            description: New description

        Returns:
            New ArtifactMetadata if successful, None otherwise
        """
        with self._lock:
            try:
                # Get parent metadata
                parent = self._retriever.get_by_id(parent_artifact_id)
                if parent is None:
                    return None

                # Get parent content if not provided
                if new_content is None:
                    content_bytes, _ = self._storage.load_content(parent_artifact_id)
                    if content_bytes is None:
                        return None
                    # Try to decode as text for JSON/text artifacts
                    try:
                        new_content = content_bytes.decode("utf-8")
                    except UnicodeDecodeError:
                        new_content = content_bytes
                elif isinstance(new_content, str):
                    new_content = new_content.encode("utf-8")

                # Calculate new version number
                conn = self._get_connection()
                version_row = conn.execute(
                    """
                    SELECT COALESCE(MAX(version), 0) as max_version
                    FROM artifact_index
                    WHERE artifact_id = ? OR parent_artifact_id = ?
                    """,
                    (parent_artifact_id, parent_artifact_id),
                ).fetchone()
                new_version = (version_row["max_version"] if version_row else 0) + 1

                # Store new version
                from .models import ArtifactType
                result = self._storage.store(
                    content=new_content,
                    artifact_type=ArtifactType(parent.artifact_type.value),
                    title=title or parent.title,
                    description=description,
                    source=parent.source,
                    agent_run_id=parent.agent_run_id,
                    run_id=parent.run_id,
                    project_id=parent.project_id,
                    mime_type=parent.mime_type,
                    is_persistent=parent.is_persistent,
                    tags=parent.tags.copy(),
                    custom_metadata=parent.custom_metadata.copy(),
                    parent_artifact_id=parent_artifact_id,
                )

                if result.success and result.artifact_id:
                    # Update version number in metadata
                    conn.execute(
                        "UPDATE artifact_index SET version = ? WHERE artifact_id = ?",
                        (new_version, result.artifact_id),
                    )
                    conn.commit()

                    return self._retriever.get_by_id(result.artifact_id)

                return None

            except (sqlite3.Error, ValidationError, OSError):
                return None

    def restore_from_archive(self, artifact_id: str) -> ArtifactMetadata | None:
        """
        Restore an archived artifact to active status.

        Args:
            artifact_id: ID of artifact to restore

        Returns:
            Updated ArtifactMetadata if successful, None otherwise
        """
        with self._lock:
            try:
                # Get current metadata
                metadata = self._retriever.get_by_id(artifact_id)
                if metadata is None or metadata.status != ArtifactStatus.ARCHIVED:
                    return None

                if metadata.storage_path is None:
                    return None

                # Move back from archive to active storage
                archive_path = metadata.storage_path
                type_dir = self._storage._artifacts_dir / metadata.artifact_type.value
                target_dir = type_dir / artifact_id
                target_dir.mkdir(parents=True, exist_ok=True)

                # Move directory contents
                for item in archive_path.parent.iterdir():
                    if item.is_dir() and item.name == artifact_id:
                        for file in item.iterdir():
                            shutil.copy2(file, target_dir / file.name)
                        break

                # Update status
                from .models import ArtifactMetadata as AM
                updated_metadata = AM(
                    **metadata.model_dump(),
                    storage_path=target_dir / archive_path.name,
                    status=ArtifactStatus.ACTIVE,
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )

                conn = self._get_connection()
                conn.execute(
                    """
                    UPDATE artifact_index SET
                        storage_path = ?, status = ?, updated_at = ?
                    WHERE artifact_id = ?
                    """,
                    (
                        str(updated_metadata.storage_path),
                        ArtifactStatus.ACTIVE.value,
                        updated_metadata.updated_at,
                        artifact_id,
                    ),
                )
                conn.commit()

                return self._retriever.get_by_id(artifact_id)

            except (sqlite3.Error, ValidationError, OSError, shutil.Error):
                return None

    def close(self) -> None:
        """Close database connections."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
