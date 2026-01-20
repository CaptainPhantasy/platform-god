"""
Artifact query and retrieval module.

Provides flexible querying capabilities for artifacts stored in the
artifacts backend with pagination and filtering.
"""

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .models import (
    Artifact,
    ArtifactListResult,
    ArtifactMetadata,
    ArtifactQuery,
    ArtifactStatus,
    ArtifactType,
)
from .storage import ArtifactStorage


class ArtifactRetriever:
    """
    Artifact query and retrieval interface.

    Provides methods to query, list, and retrieve artifacts with
    flexible filtering and pagination support.
    """

    def __init__(self, storage: ArtifactStorage | None = None):
        """
        Initialize retriever with storage backend.

        Args:
            storage: ArtifactStorage instance (creates default if None)
        """
        self._storage = storage or ArtifactStorage()
        self._lock = threading.RLock()
        self._local = threading.local()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local SQLite connection for queries."""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            registry_path = self._storage._registry_path
            self._local.conn = sqlite3.connect(
                str(registry_path),
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _build_where_clause(self, query: ArtifactQuery) -> tuple[str, list[Any]]:
        """
        Build SQL WHERE clause from query parameters.

        Returns:
            Tuple of (where_clause, parameters)
        """
        conditions = []
        params = []

        # Exact ID match
        if query.artifact_id:
            conditions.append("artifact_id = ?")
            params.append(query.artifact_id)

        # Type filter (single or list)
        if query.artifact_type:
            if isinstance(query.artifact_type, list):
                placeholders = ",".join("?" * len(query.artifact_type))
                conditions.append(f"artifact_type IN ({placeholders})")
                params.extend([t.value for t in query.artifact_type])
            else:
                conditions.append("artifact_type = ?")
                params.append(query.artifact_type.value)

        # Source filter
        if query.source:
            conditions.append("source = ?")
            params.append(query.source)

        # Agent run ID filter
        if query.agent_run_id:
            conditions.append("agent_run_id = ?")
            params.append(query.agent_run_id)

        # Run ID filter
        if query.run_id:
            conditions.append("run_id = ?")
            params.append(query.run_id)

        # Project ID filter
        if query.project_id is not None:
            conditions.append("project_id = ?")
            params.append(query.project_id)

        # Status filter (single or list)
        if query.status:
            if isinstance(query.status, list):
                placeholders = ",".join("?" * len(query.status))
                conditions.append(f"status IN ({placeholders})")
                params.extend([s.value for s in query.status])
            else:
                conditions.append("status = ?")
                params.append(query.status.value)

        # Content hash filter
        if query.content_hash:
            conditions.append("content_hash = ?")
            params.append(query.content_hash)

        # Date range filters
        if query.created_after:
            conditions.append("created_at >= ?")
            params.append(query.created_after)

        if query.created_before:
            conditions.append("created_at <= ?")
            params.append(query.created_before)

        # Substring filters
        if query.title_contains:
            conditions.append("title LIKE ?")
            params.append(f"%{query.title_contains}%")

        if query.description_contains:
            conditions.append("description LIKE ?")
            params.append(f"%{query.description_contains}%")

        # Persistence filter
        if query.is_persistent is not None:
            conditions.append("is_persistent = ?")
            params.append(1 if query.is_persistent else 0)

        # Size filters
        if query.min_size_bytes is not None:
            conditions.append("size_bytes >= ?")
            params.append(query.min_size_bytes)

        if query.max_size_bytes is not None:
            conditions.append("size_bytes <= ?")
            params.append(query.max_size_bytes)

        # Tags filter (all must match - JSON contains)
        if query.tags:
            for tag in query.tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        return where_clause, params

    def _build_order_clause(self, query: ArtifactQuery) -> str:
        """Build SQL ORDER BY clause from query parameters."""
        valid_columns = {
            "created_at": "created_at",
            "updated_at": "updated_at",
            "size_bytes": "size_bytes",
            "title": "title",
            "artifact_type": "artifact_type",
            "status": "status",
        }

        column = valid_columns.get(query.sort_by, "created_at")
        order = "DESC" if query.sort_order == "desc" else "ASC"

        return f"ORDER BY {column} {order}"

    def _row_to_metadata(self, row: sqlite3.Row) -> ArtifactMetadata:
        """Convert database row to ArtifactMetadata."""
        return ArtifactMetadata(
            artifact_id=row["artifact_id"],
            artifact_type=ArtifactType(row["artifact_type"]),
            title=row["title"],
            description=row["description"],
            source=row["source"],
            agent_run_id=row["agent_run_id"],
            run_id=row["run_id"],
            project_id=row["project_id"],
            file_path=Path(row["file_path"]) if row["file_path"] else None,
            storage_path=Path(row["storage_path"]) if row["storage_path"] else None,
            content_hash=row["content_hash"],
            size_bytes=row["size_bytes"],
            mime_type=row["mime_type"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            version=row["version"],
            parent_artifact_id=row["parent_artifact_id"],
            status=ArtifactStatus(row["status"]),
            is_persistent=bool(row["is_persistent"]),
            tags=json.loads(row["tags"]) if row["tags"] else [],
            custom_metadata=json.loads(row["custom_metadata"]) if row["custom_metadata"] else {},
        )

    def query(self, query: ArtifactQuery) -> ArtifactListResult:
        """
        Query artifacts with filtering and pagination.

        Args:
            query: ArtifactQuery with filters and pagination

        Returns:
            ArtifactListResult with matching artifacts
        """
        with self._lock:
            try:
                conn = self._get_connection()

                where_clause, params = self._build_where_clause(query)
                order_clause = self._build_order_clause(query)

                # Get total count
                count_sql = f"SELECT COUNT(*) as count FROM artifact_index {where_clause}"
                count_result = conn.execute(count_sql, params).fetchone()
                total_count = count_result["count"] if count_result else 0

                # Get paginated results
                sql = f"""
                SELECT * FROM artifact_index
                {where_clause}
                {order_clause}
                LIMIT ? OFFSET ?
                """
                params.extend([query.limit, query.offset])

                rows = conn.execute(sql, params).fetchall()

                artifacts = []
                for row in rows:
                    try:
                        metadata = self._row_to_metadata(row)
                        artifacts.append(metadata)
                    except (ValidationError, ValueError):
                        # Skip invalid records
                        continue

                return ArtifactListResult(
                    artifacts=artifacts,
                    total_count=total_count,
                    returned_count=len(artifacts),
                    offset=query.offset,
                    limit=query.limit,
                    has_more=query.offset + len(artifacts) < total_count,
                )

            except sqlite3.Error:
                return ArtifactListResult(
                    artifacts=[],
                    total_count=0,
                    returned_count=0,
                    offset=query.offset,
                    limit=query.limit,
                    has_more=False,
                )

    def get_by_id(self, artifact_id: str) -> ArtifactMetadata | None:
        """
        Get artifact metadata by ID.

        Args:
            artifact_id: Unique artifact identifier

        Returns:
            ArtifactMetadata if found, None otherwise
        """
        with self._lock:
            try:
                conn = self._get_connection()
                row = conn.execute(
                    "SELECT * FROM artifact_index WHERE artifact_id = ?",
                    (artifact_id,),
                ).fetchone()

                if row is None:
                    return None

                return self._row_to_metadata(row)

            except (sqlite3.Error, ValidationError):
                return None

    def get_content(self, artifact_id: str) -> Artifact | None:
        """
        Get artifact with content.

        Args:
            artifact_id: Unique artifact identifier

        Returns:
            Artifact with content if found, None otherwise
        """
        with self._lock:
            content_bytes, metadata = self._storage.load_content(artifact_id)

            if metadata is None:
                return None

            if content_bytes is None:
                # Content not on disk (may be archived)
                return Artifact(metadata=metadata, content=None)

            # Return with content
            return Artifact(metadata=metadata, content=content_bytes)

    def get_content_as_text(self, artifact_id: str) -> Artifact | None:
        """
        Get artifact with text content.

        Args:
            artifact_id: Unique artifact identifier

        Returns:
            Artifact with text content if found, None otherwise
        """
        with self._lock:
            content_text, metadata = self._storage.load_content_as_text(artifact_id)

            if metadata is None:
                return None

            if content_text is None:
                return Artifact(metadata=metadata, content=None)

            return Artifact(metadata=metadata, content=content_text)

    def list_by_type(
        self,
        artifact_type: ArtifactType,
        offset: int = 0,
        limit: int = 100,
    ) -> ArtifactListResult:
        """
        List all artifacts of a specific type.

        Args:
            artifact_type: Type to filter by
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        query = ArtifactQuery(
            artifact_type=artifact_type,
            status=ArtifactStatus.ACTIVE,
            offset=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return self.query(query)

    def list_by_source(
        self,
        source: str,
        offset: int = 0,
        limit: int = 100,
    ) -> ArtifactListResult:
        """
        List all artifacts from a specific source.

        Args:
            source: Source identifier
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        query = ArtifactQuery(
            source=source,
            status=ArtifactStatus.ACTIVE,
            offset=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return self.query(query)

    def list_by_run(
        self,
        run_id: str,
        offset: int = 0,
        limit: int = 100,
    ) -> ArtifactListResult:
        """
        List all artifacts from a specific run.

        Args:
            run_id: Run identifier
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        query = ArtifactQuery(
            run_id=run_id,
            status=ArtifactStatus.ACTIVE,
            offset=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return self.query(query)

    def list_by_project(
        self,
        project_id: int,
        offset: int = 0,
        limit: int = 100,
    ) -> ArtifactListResult:
        """
        List all artifacts for a specific project.

        Args:
            project_id: Project ID
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        query = ArtifactQuery(
            project_id=project_id,
            status=ArtifactStatus.ACTIVE,
            offset=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return self.query(query)

    def list_by_tags(
        self,
        tags: list[str],
        offset: int = 0,
        limit: int = 100,
    ) -> ArtifactListResult:
        """
        List all artifacts with all specified tags.

        Args:
            tags: Tags to filter by (all must match)
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        query = ArtifactQuery(
            tags=tags,
            status=ArtifactStatus.ACTIVE,
            offset=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return self.query(query)

    def list_by_date_range(
        self,
        start_date: str,
        end_date: str,
        offset: int = 0,
        limit: int = 100,
    ) -> ArtifactListResult:
        """
        List artifacts created within a date range.

        Args:
            start_date: ISO timestamp start (inclusive)
            end_date: ISO timestamp end (inclusive)
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        query = ArtifactQuery(
            created_after=start_date,
            created_before=end_date,
            status=ArtifactStatus.ACTIVE,
            offset=offset,
            limit=limit,
            sort_by="created_at",
            sort_order="desc",
        )
        return self.query(query)

    def find_duplicates(self) -> dict[str, list[str]]:
        """
        Find artifacts with duplicate content (same hash).

        Returns:
            Dict mapping content_hash to list of artifact_ids
        """
        with self._lock:
            try:
                conn = self._get_connection()

                rows = conn.execute(
                    """
                    SELECT content_hash, GROUP_CONCAT(artifact_id) as artifact_ids
                    FROM artifact_index
                    WHERE status = 'active' AND content_hash IS NOT NULL
                    GROUP BY content_hash
                    HAVING COUNT(*) > 1
                    """
                ).fetchall()

                duplicates = {}
                for row in rows:
                    hashes = row["artifact_ids"].split(",") if row["artifact_ids"] else []
                    duplicates[row["content_hash"]] = hashes

                return duplicates

            except sqlite3.Error:
                return {}

    def get_version_history(self, artifact_id: str) -> list[ArtifactMetadata]:
        """
        Get version history for an artifact.

        Args:
            artifact_id: Base artifact ID (looks for all versions)

        Returns:
            List of ArtifactMetadata ordered by version
        """
        with self._lock:
            try:
                conn = self._get_connection()

                # Find the root artifact (no parent) or use the given ID
                rows = conn.execute(
                    """
                    SELECT * FROM artifact_index
                    WHERE artifact_id = ?
                        OR parent_artifact_id = ?
                        OR artifact_id IN (
                            SELECT parent_artifact_id FROM artifact_index WHERE artifact_id = ?
                        )
                    ORDER BY version ASC
                    """,
                    (artifact_id, artifact_id, artifact_id),
                ).fetchall()

                versions = []
                for row in rows:
                    try:
                        metadata = self._row_to_metadata(row)
                        versions.append(metadata)
                    except (ValidationError, ValueError):
                        continue

                return versions

            except sqlite3.Error:
                return []

    def search(self, search_term: str, offset: int = 0, limit: int = 100) -> ArtifactListResult:
        """
        Full-text search across artifact titles and descriptions.

        Args:
            search_term: Term to search for
            offset: Pagination offset
            limit: Maximum results

        Returns:
            ArtifactListResult with matching artifacts
        """
        with self._lock:
            try:
                conn = self._get_connection()

                pattern = f"%{search_term}%"

                # Get total count
                count_result = conn.execute(
                    """
                    SELECT COUNT(*) as count FROM artifact_index
                    WHERE status = 'active'
                        AND (title LIKE ? OR description LIKE ?)
                    """,
                    (pattern, pattern),
                ).fetchone()
                total_count = count_result["count"] if count_result else 0

                # Get paginated results
                rows = conn.execute(
                    """
                    SELECT * FROM artifact_index
                    WHERE status = 'active'
                        AND (title LIKE ? OR description LIKE ?)
                    ORDER BY created_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (pattern, pattern, limit, offset),
                ).fetchall()

                artifacts = []
                for row in rows:
                    try:
                        metadata = self._row_to_metadata(row)
                        artifacts.append(metadata)
                    except (ValidationError, ValueError):
                        continue

                return ArtifactListResult(
                    artifacts=artifacts,
                    total_count=total_count,
                    returned_count=len(artifacts),
                    offset=offset,
                    limit=limit,
                    has_more=offset + len(artifacts) < total_count,
                )

            except sqlite3.Error:
                return ArtifactListResult(
                    artifacts=[],
                    total_count=0,
                    returned_count=0,
                    offset=offset,
                    limit=limit,
                    has_more=False,
                )

    def close(self) -> None:
        """Close database connections."""
        if hasattr(self._local, "conn") and self._local.conn:
            self._local.conn.close()
            self._local.conn = None
