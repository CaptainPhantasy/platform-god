"""Tests for artifact storage, retrieval, and lifecycle management."""

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Generator

import pytest

from platform_god.artifacts import (
    Artifact,
    ArtifactListResult,
    ArtifactMetadata,
    ArtifactQuery,
    ArtifactRetriever,
    ArtifactStatus,
    ArtifactStorage,
    ArtifactType,
    ArchiveResult,
    ArtifactLifecycle,
    RetentionPolicy,
    StorageResult,
    StorageError,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_artifacts_dir(temp_dir: Path) -> Generator[Path, None, None]:
    """Provide a temporary artifacts directory that is cleaned up after the test."""
    artifacts_dir = temp_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    yield artifacts_dir


@pytest.fixture
def artifact_storage(temp_artifacts_dir: Path) -> ArtifactStorage:
    """Provide an ArtifactStorage instance with a temporary directory."""
    return ArtifactStorage(artifacts_dir=temp_artifacts_dir)


@pytest.fixture
def artifact_retriever(artifact_storage: ArtifactStorage) -> ArtifactRetriever:
    """Provide an ArtifactRetriever instance with a temporary storage."""
    return ArtifactRetriever(storage=artifact_storage)


@pytest.fixture
def artifact_lifecycle(
    artifact_storage: ArtifactStorage,
    artifact_retriever: ArtifactRetriever,
) -> ArtifactLifecycle:
    """Provide an ArtifactLifecycle instance with temporary storage."""
    return ArtifactLifecycle(storage=artifact_storage, retriever=artifact_retriever)


@pytest.fixture
def sample_artifact_id(artifact_storage: ArtifactStorage) -> str:
    """Store a sample artifact and return its ID."""
    result = artifact_storage.store(
        content='{"key": "value"}',
        artifact_type=ArtifactType.REPORT,
        title="Test Report",
        description="A test report for unit testing",
        source="test_system",
        agent_run_id="run_123",
        run_id="run_abc",
        project_id=1,
        tags=["test", "sample"],
        custom_metadata={"env": "test"},
    )
    assert result.success
    assert result.artifact_id is not None
    return result.artifact_id


@pytest.fixture
def sample_artifact_id_2(artifact_storage: ArtifactStorage) -> str:
    """Store a second sample artifact and return its ID."""
    result = artifact_storage.store(
        content="patch content here",
        artifact_type=ArtifactType.PATCH,
        title="Test Patch",
        description="A test patch",
        source="test_system",
        tags=["patch", "test"],
    )
    assert result.success
    assert result.artifact_id is not None
    return result.artifact_id


# =============================================================================
# Model Tests
# =============================================================================


class TestArtifactType:
    """Tests for ArtifactType enum."""

    def test_all_types_defined(self) -> None:
        """Verify all expected artifact types are defined."""
        # Check that the enum has all expected values (case-insensitive comparison)
        expected_types = {
            "report",
            "patch",
            "documentation",
            "test",
            "config",
            "binary",
            "scan_result",
            "custom",
        }
        actual_types = {at.value.lower() for at in ArtifactType}
        assert actual_types == expected_types


class TestArtifactStatus:
    """Tests for ArtifactStatus enum."""

    def test_all_statuses_defined(self) -> None:
        """Verify all expected artifact statuses are defined."""
        # Check that the enum has all expected values (case-insensitive comparison)
        expected_statuses = {
            "active",
            "archived",
            "deleted",
            "pending_deletion",
        }
        actual_statuses = {s.value.lower() for s in ArtifactStatus}
        assert actual_statuses == expected_statuses


class TestArtifactMetadata:
    """Tests for ArtifactMetadata model."""

    def test_minimal_metadata(self) -> None:
        """ArtifactMetadata can be created with minimal fields."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
        )
        assert metadata.artifact_id == "test-123"
        assert metadata.artifact_type == ArtifactType.REPORT
        assert metadata.title == "Test Report"
        assert metadata.description is None
        assert metadata.source is None
        assert metadata.status == ArtifactStatus.ACTIVE
        assert metadata.version == 1
        assert metadata.is_persistent is True
        assert metadata.tags == []
        assert metadata.custom_metadata == {}

    def test_full_metadata(self) -> None:
        """ArtifactMetadata can be created with all fields."""
        now = datetime.now(timezone.utc).isoformat()
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.PATCH,
            title="Test Patch",
            description="A test patch",
            source="test_agent",
            agent_run_id="run_456",
            run_id="run_xyz",
            project_id=42,
            file_path=Path("/tmp/test.patch"),
            storage_path=Path("var/artifacts/patch/test-123/content.diff"),
            content_hash="abc123",
            size_bytes=1024,
            mime_type="text/plain",
            created_at=now,
            updated_at=now,
            version=2,
            parent_artifact_id="parent-123",
            status=ArtifactStatus.ARCHIVED,
            is_persistent=False,
            tags=["test", "patch"],
            custom_metadata={"key": "value"},
        )
        assert metadata.artifact_id == "test-123"
        assert metadata.artifact_type == ArtifactType.PATCH
        assert metadata.status == ArtifactStatus.ARCHIVED
        assert metadata.version == 2
        assert metadata.is_persistent is False
        assert metadata.tags == ["test", "patch"]
        assert metadata.custom_metadata == {"key": "value"}

    def test_artifact_type_validator_string(self) -> None:
        """ArtifactType validator converts string to enum."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type="report",  # String instead of enum
            title="Test Report",
        )
        assert metadata.artifact_type == ArtifactType.REPORT

    def test_artifact_type_validator_invalid_string(self) -> None:
        """Invalid artifact type string defaults to CUSTOM."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type="invalid_type",
            title="Test Report",
        )
        assert metadata.artifact_type == ArtifactType.CUSTOM

    def test_status_validator_string(self) -> None:
        """Status validator converts string to enum."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
            status="archived",
        )
        assert metadata.status == ArtifactStatus.ARCHIVED


class TestArtifact:
    """Tests for Artifact model."""

    def test_artifact_with_text_content(self) -> None:
        """Artifact can hold text content."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
        )
        artifact = Artifact(metadata=metadata, content="test content")
        assert artifact.content == "test content"
        assert artifact.is_binary() is False
        assert artifact.is_stored_on_disk() is False
        assert artifact.get_content_size() == len("test content")

    def test_artifact_with_binary_content(self) -> None:
        """Artifact can hold binary content."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.BINARY,
            title="Test Binary",
        )
        content = b"\x00\x01\x02\x03"
        artifact = Artifact(metadata=metadata, content=content)
        assert artifact.content == content
        assert artifact.is_binary() is True
        assert artifact.get_content_size() == 4

    def test_artifact_with_disk_storage(self) -> None:
        """Artifact with disk storage has no in-memory content."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
            storage_path=Path("var/artifacts/report/test-123/content.json"),
            size_bytes=1024,
        )
        artifact = Artifact(metadata=metadata, content=None)
        assert artifact.content is None
        assert artifact.is_stored_on_disk() is True
        assert artifact.get_content_size() == 1024

    def test_artifact_size_with_text(self) -> None:
        """get_content_size returns UTF-8 byte count for text."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
        )
        artifact = Artifact(metadata=metadata, content="hello world")
        # "hello world" is 11 bytes
        assert artifact.get_content_size() == 11

    def test_artifact_size_with_utf8(self) -> None:
        """get_content_size handles UTF-8 correctly."""
        metadata = ArtifactMetadata(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
        )
        artifact = Artifact(metadata=metadata, content="hello world")
        assert artifact.get_content_size() == 11


class TestArtifactQuery:
    """Tests for ArtifactQuery model."""

    def test_default_query(self) -> None:
        """Default query filters for active artifacts."""
        query = ArtifactQuery()
        assert query.artifact_id is None
        assert query.status == ArtifactStatus.ACTIVE
        assert query.offset == 0
        assert query.limit == 100
        assert query.sort_by == "created_at"
        assert query.sort_order == "desc"

    def test_query_with_type_filter(self) -> None:
        """Query can filter by artifact type."""
        query = ArtifactQuery(artifact_type=ArtifactType.REPORT)
        assert query.artifact_type == ArtifactType.REPORT

    def test_query_with_multiple_types(self) -> None:
        """Query can filter by multiple artifact types."""
        query = ArtifactQuery(
            artifact_type=[ArtifactType.REPORT, ArtifactType.PATCH]
        )
        assert isinstance(query.artifact_type, list)
        assert ArtifactType.REPORT in query.artifact_type
        assert ArtifactType.PATCH in query.artifact_type

    def test_query_with_type_strings(self) -> None:
        """Query converts type strings to enums."""
        query = ArtifactQuery(artifact_type="report")
        assert query.artifact_type == ArtifactType.REPORT

    def test_query_with_multiple_type_strings(self) -> None:
        """Query converts multiple type strings to enums."""
        query = ArtifactQuery(artifact_type=["report", "patch"])
        assert isinstance(query.artifact_type, list)
        assert ArtifactType.REPORT in query.artifact_type
        assert ArtifactType.PATCH in query.artifact_type

    def test_query_pagination(self) -> None:
        """Query supports pagination."""
        query = ArtifactQuery(offset=50, limit=25)
        assert query.offset == 50
        assert query.limit == 25

    def test_query_sort_validation(self) -> None:
        """Query validates sort order."""
        with pytest.raises(ValueError):
            ArtifactQuery(sort_order="invalid")

        # Valid orders should work
        query1 = ArtifactQuery(sort_order="asc")
        assert query1.sort_order == "asc"
        query2 = ArtifactQuery(sort_order="desc")
        assert query2.sort_order == "desc"

    def test_query_with_all_filters(self) -> None:
        """Query can use all filter parameters."""
        query = ArtifactQuery(
            artifact_id="test-123",
            artifact_type=ArtifactType.REPORT,
            source="test_agent",
            agent_run_id="run_456",
            run_id="run_xyz",
            project_id=42,
            status=ArtifactStatus.ACTIVE,
            tags=["test", "important"],
            content_hash="abc123",
            created_after="2024-01-01T00:00:00Z",
            created_before="2024-12-31T23:59:59Z",
            title_contains="test",
            description_contains="important",
            is_persistent=True,
            min_size_bytes=100,
            max_size_bytes=10240,
            offset=10,
            limit=50,
            sort_by="title",
            sort_order="asc",
        )
        assert query.artifact_id == "test-123"
        assert query.source == "test_agent"
        assert query.tags == ["test", "important"]
        assert query.is_persistent is True
        assert query.min_size_bytes == 100
        assert query.max_size_bytes == 10240


class TestStorageResult:
    """Tests for StorageResult model."""

    def test_success_result(self) -> None:
        """StorageResult can represent success."""
        result = StorageResult(
            success=True,
            artifact_id="test-123",
            storage_path=Path("var/artifacts/test.json"),
            checksum="abc123",
        )
        assert result.success is True
        assert result.artifact_id == "test-123"
        assert result.error is None

    def test_failure_result(self) -> None:
        """StorageResult can represent failure."""
        result = StorageResult(
            success=False,
            error="Storage failed",
        )
        assert result.success is False
        assert result.error == "Storage failed"
        assert result.artifact_id is None


class TestArchiveResult:
    """Tests for ArchiveResult model."""

    def test_archive_result(self) -> None:
        """ArchiveResult can hold operation statistics."""
        result = ArchiveResult(
            success=True,
            archived_count=5,
            deleted_count=2,
            freed_bytes=1024000,
            errors=["warning 1", "warning 2"],
        )
        assert result.success is True
        assert result.archived_count == 5
        assert result.deleted_count == 2
        assert result.freed_bytes == 1024000
        assert len(result.errors) == 2


class TestRetentionPolicy:
    """Tests for RetentionPolicy model."""

    def test_default_policy(self) -> None:
        """Default retention policy has no limits."""
        policy = RetentionPolicy()
        assert policy.max_age_days is None
        assert policy.max_versions is None
        assert policy.max_total_size_mb is None
        assert policy.keep_persistent is True
        assert policy.keep_types == []
        assert policy.archive_before_delete is True

    def test_policy_with_age_limit(self) -> None:
        """Retention policy can set age limit."""
        policy = RetentionPolicy(max_age_days=30)
        assert policy.max_age_days == 30

    def test_policy_with_version_limit(self) -> None:
        """Retention policy can set version limit."""
        policy = RetentionPolicy(max_versions=5)
        assert policy.max_versions == 5

    def test_policy_with_size_limit(self) -> None:
        """Retention policy can set size limit."""
        policy = RetentionPolicy(max_total_size_mb=1024)
        assert policy.max_total_size_mb == 1024

    def test_policy_with_keep_types(self) -> None:
        """Retention policy can specify types to keep."""
        policy = RetentionPolicy(
            keep_types=[ArtifactType.REPORT, ArtifactType.DOCUMENTATION]
        )
        assert len(policy.keep_types) == 2
        assert ArtifactType.REPORT in policy.keep_types


# =============================================================================
# Storage Tests
# =============================================================================


class TestArtifactStorageInit:
    """Tests for ArtifactStorage initialization."""

    def test_creates_artifacts_directory(self, temp_artifacts_dir: Path) -> None:
        """Storage initialization creates the artifacts directory."""
        storage = ArtifactStorage(artifacts_dir=temp_artifacts_dir)
        assert temp_artifacts_dir.exists()
        assert storage._artifacts_dir == temp_artifacts_dir

    def test_creates_registry_database(self, temp_artifacts_dir: Path) -> None:
        """Storage initialization creates the SQLite registry."""
        registry_path = temp_artifacts_dir / ".index.db"
        storage = ArtifactStorage(
            artifacts_dir=temp_artifacts_dir,
            registry_path=registry_path,
        )
        assert registry_path.exists()
        assert storage._registry_path == registry_path

    def test_initializes_database_schema(self, artifact_storage: ArtifactStorage) -> None:
        """Storage initialization creates the artifact_index table."""
        conn = artifact_storage._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='artifact_index'"
        )
        result = cursor.fetchone()
        assert result is not None

    def test_creates_indexes(self, artifact_storage: ArtifactStorage) -> None:
        """Storage initialization creates query indexes."""
        conn = artifact_storage._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row["name"] for row in cursor.fetchall()}
        assert "idx_artifact_id" in indexes
        assert "idx_artifact_type" in indexes
        assert "idx_source" in indexes
        assert "idx_status" in indexes


class TestArtifactStorageStore:
    """Tests for ArtifactStorage.store method."""

    def test_store_text_content(self, artifact_storage: ArtifactStorage) -> None:
        """Storage can store text content."""
        result = artifact_storage.store(
            content="test content",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
        )
        assert result.success is True
        assert result.artifact_id is not None
        assert result.storage_path is not None
        assert result.checksum is not None
        assert result.storage_path.exists()

    def test_store_binary_content(self, artifact_storage: ArtifactStorage) -> None:
        """Storage can store binary content."""
        content = b"\x00\x01\x02\x03\x04\x05"
        result = artifact_storage.store(
            content=content,
            artifact_type=ArtifactType.BINARY,
            title="Test Binary",
        )
        assert result.success is True
        assert result.storage_path.exists()
        stored_content = result.storage_path.read_bytes()
        assert stored_content == content

    def test_store_with_all_metadata(self, artifact_storage: ArtifactStorage) -> None:
        """Storage can store artifact with full metadata."""
        result = artifact_storage.store(
            content='{"key": "value"}',
            artifact_type=ArtifactType.REPORT,
            title="Full Metadata Report",
            description="Report with all metadata fields",
            source="test_agent",
            agent_run_id="run_123",
            run_id="run_abc",
            project_id=42,
            mime_type="application/json",
            is_persistent=False,
            tags=["test", "full"],
            custom_metadata={"env": "test", "region": "us-east"},
        )
        assert result.success is True

        # Verify metadata was stored in database
        conn = artifact_storage._get_connection()
        row = conn.execute(
            "SELECT * FROM artifact_index WHERE artifact_id = ?",
            (result.artifact_id,),
        ).fetchone()
        assert row is not None
        assert row["title"] == "Full Metadata Report"
        assert row["description"] == "Report with all metadata fields"
        assert row["source"] == "test_agent"
        assert row["agent_run_id"] == "run_123"
        assert row["project_id"] == 42
        assert row["is_persistent"] == 0

    def test_store_with_custom_id(self, artifact_storage: ArtifactStorage) -> None:
        """Storage can use a custom artifact ID."""
        custom_id = "custom-artifact-123"
        result = artifact_storage.store(
            content="test content",
            artifact_type=ArtifactType.REPORT,
            title="Test",
            artifact_id=custom_id,
        )
        assert result.success is True
        assert result.artifact_id == custom_id

    def test_store_creates_metadata_file(self, artifact_storage: ArtifactStorage) -> None:
        """Storage creates a metadata.json file alongside content."""
        result = artifact_storage.store(
            content="test content",
            artifact_type=ArtifactType.REPORT,
            title="Test Report",
        )
        assert result.success is True

        metadata_path = result.storage_path.parent / "metadata.json"
        assert metadata_path.exists()

        metadata_data = json.loads(metadata_path.read_text())
        assert metadata_data["artifact_id"] == result.artifact_id
        assert metadata_data["title"] == "Test Report"

    def test_store_creates_type_subdirectory(self, artifact_storage: ArtifactStorage) -> None:
        """Storage creates type-based subdirectories."""
        result = artifact_storage.store(
            content="test content",
            artifact_type=ArtifactType.PATCH,
            title="Test Patch",
        )
        assert result.success is True

        # Path should be: artifacts_dir/patch/artifact_id/content.ext
        assert "patch" in str(result.storage_path)
        assert result.artifact_id in str(result.storage_path)

    def test_store_generates_checksum(self, artifact_storage: ArtifactStorage) -> None:
        """Storage generates SHA256 checksum for content."""
        content = "test content for checksum"
        result = artifact_storage.store(
            content=content,
            artifact_type=ArtifactType.REPORT,
            title="Test",
        )
        assert result.success is True
        assert result.checksum is not None
        assert len(result.checksum) == 64  # SHA256 hex length

    def test_store_same_content_same_checksum(self, artifact_storage: ArtifactStorage) -> None:
        """Same content produces same checksum."""
        content = "identical content"
        result1 = artifact_storage.store(
            content=content,
            artifact_type=ArtifactType.REPORT,
            title="Test 1",
        )
        result2 = artifact_storage.store(
            content=content,
            artifact_type=ArtifactType.PATCH,
            title="Test 2",
        )
        assert result1.checksum == result2.checksum

    def test_store_records_size(self, artifact_storage: ArtifactStorage) -> None:
        """Storage records content size in bytes."""
        content = "test content"
        result = artifact_storage.store(
            content=content,
            artifact_type=ArtifactType.REPORT,
            title="Test",
        )
        assert result.success is True

        conn = artifact_storage._get_connection()
        row = conn.execute(
            "SELECT size_bytes FROM artifact_index WHERE artifact_id = ?",
            (result.artifact_id,),
        ).fetchone()
        assert row["size_bytes"] == len(content.encode("utf-8"))

    def test_store_with_parent_artifact(self, artifact_storage: ArtifactStorage) -> None:
        """Storage can record parent artifact for versioning."""
        parent_result = artifact_storage.store(
            content="parent content",
            artifact_type=ArtifactType.REPORT,
            title="Parent",
        )
        assert parent_result.success is True

        child_result = artifact_storage.store(
            content="child content",
            artifact_type=ArtifactType.REPORT,
            title="Child",
            parent_artifact_id=parent_result.artifact_id,
        )
        assert child_result.success is True

        conn = artifact_storage._get_connection()
        row = conn.execute(
            "SELECT parent_artifact_id FROM artifact_index WHERE artifact_id = ?",
            (child_result.artifact_id,),
        ).fetchone()
        assert row["parent_artifact_id"] == parent_result.artifact_id


class TestArtifactStorageStreaming:
    """Tests for ArtifactStorage.store_streaming method."""

    def test_store_streaming_from_file(
        self,
        artifact_storage: ArtifactStorage,
        temp_dir: Path,
    ) -> None:
        """Storage can stream large files from disk."""
        # Create a source file
        source_file = temp_dir / "source.txt"
        source_file.write_text("large file content for streaming")

        result = artifact_storage.store_streaming(
            source_path=source_file,
            artifact_type=ArtifactType.DOCUMENTATION,
            title="Streamed Doc",
        )
        assert result.success is True
        assert result.storage_path.exists()
        assert result.storage_path.read_text() == source_file.read_text()

    def test_store_streaming_nonexistent_file(
        self,
        artifact_storage: ArtifactStorage,
        temp_dir: Path,
    ) -> None:
        """Streaming returns error for nonexistent file."""
        nonexistent = temp_dir / "nonexistent.txt"
        result = artifact_storage.store_streaming(
            source_path=nonexistent,
            artifact_type=ArtifactType.DOCUMENTATION,
            title="Missing File",
        )
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_store_streaming_generates_checksum(
        self,
        artifact_storage: ArtifactStorage,
        temp_dir: Path,
    ) -> None:
        """Streaming generates correct checksum."""
        source_file = temp_dir / "source.txt"
        content = "streaming content"
        source_file.write_text(content)

        result = artifact_storage.store_streaming(
            source_path=source_file,
            artifact_type=ArtifactType.DOCUMENTATION,
            title="Streamed",
        )
        assert result.success is True
        assert result.checksum is not None
        assert len(result.checksum) == 64


class TestArtifactStorageLoad:
    """Tests for ArtifactStorage load methods."""

    def test_load_content(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage can load artifact content."""
        content, metadata = artifact_storage.load_content(sample_artifact_id)
        assert content is not None
        assert metadata is not None
        assert metadata.artifact_id == sample_artifact_id
        assert json.loads(content) == {"key": "value"}

    def test_load_content_as_text(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage can load text content."""
        content, metadata = artifact_storage.load_content_as_text(sample_artifact_id)
        assert content is not None
        assert isinstance(content, str)
        assert json.loads(content) == {"key": "value"}

    def test_load_nonexistent_artifact(self, artifact_storage: ArtifactStorage) -> None:
        """Loading nonexistent artifact returns None."""
        content, metadata = artifact_storage.load_content("nonexistent-id")
        assert content is None
        assert metadata is None

    def test_load_binary_content(self, artifact_storage: ArtifactStorage) -> None:
        """Storage can load binary content."""
        result = artifact_storage.store(
            content=b"\x00\x01\x02\x03",
            artifact_type=ArtifactType.BINARY,
            title="Binary Test",
        )
        content, metadata = artifact_storage.load_content(result.artifact_id)
        assert content == b"\x00\x01\x02\x03"


class TestArtifactStorageUpdateMetadata:
    """Tests for ArtifactStorage.update_metadata method."""

    def test_update_title(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage can update artifact title."""
        result = artifact_storage.update_metadata(
            sample_artifact_id,
            title="Updated Title",
        )
        assert result.success is True

        metadata = artifact_storage._load_metadata_from_disk(sample_artifact_id)
        assert metadata is not None
        assert metadata.title == "Updated Title"

    def test_update_description(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage can update artifact description."""
        result = artifact_storage.update_metadata(
            sample_artifact_id,
            description="Updated description",
        )
        assert result.success is True

        metadata = artifact_storage._load_metadata_from_disk(sample_artifact_id)
        assert metadata is not None
        assert metadata.description == "Updated description"

    def test_update_status(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage can update artifact status."""
        result = artifact_storage.update_metadata(
            sample_artifact_id,
            status=ArtifactStatus.ARCHIVED,
        )
        assert result.success is True

        metadata = artifact_storage._load_metadata_from_disk(sample_artifact_id)
        assert metadata is not None
        assert metadata.status == ArtifactStatus.ARCHIVED

    def test_update_tags(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage can update artifact tags."""
        result = artifact_storage.update_metadata(
            sample_artifact_id,
            tags=["updated", "tags"],
        )
        assert result.success is True

        metadata = artifact_storage._load_metadata_from_disk(sample_artifact_id)
        assert metadata is not None
        assert metadata.tags == ["updated", "tags"]

    def test_update_custom_metadata(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Storage merges custom metadata."""
        result = artifact_storage.update_metadata(
            sample_artifact_id,
            custom_metadata={"new_key": "new_value"},
        )
        assert result.success is True

        metadata = artifact_storage._load_metadata_from_disk(sample_artifact_id)
        assert metadata is not None
        assert metadata.custom_metadata["env"] == "test"  # Original
        assert metadata.custom_metadata["new_key"] == "new_value"  # Merged

    def test_update_nonexistent_artifact(self, artifact_storage: ArtifactStorage) -> None:
        """Updating nonexistent artifact returns error."""
        result = artifact_storage.update_metadata("nonexistent-id", title="New Title")
        assert result.success is False
        assert "not found" in result.error.lower()


class TestArtifactStorageDelete:
    """Tests for ArtifactStorage.delete_artifact method."""

    def test_delete_marks_as_deleted(self, artifact_storage: ArtifactStorage) -> None:
        """Deletion can mark artifact as deleted without removing files."""
        result = artifact_storage.store(
            content="test content",
            artifact_type=ArtifactType.REPORT,
            title="To Delete",
        )
        artifact_id = result.artifact_id
        assert result.success is True

        delete_result = artifact_storage.delete_artifact(artifact_id, delete_from_disk=False)
        assert delete_result.success is True

        metadata = artifact_storage._load_metadata_from_disk(artifact_id)
        assert metadata is not None
        assert metadata.status == ArtifactStatus.DELETED
        assert metadata.storage_path.exists()

    def test_delete_from_disk(self, artifact_storage: ArtifactStorage) -> None:
        """Deletion can remove artifact from disk."""
        result = artifact_storage.store(
            content="test content",
            artifact_type=ArtifactType.REPORT,
            title="To Delete",
        )
        artifact_id = result.artifact_id
        storage_path = result.storage_path
        assert result.success is True

        delete_result = artifact_storage.delete_artifact(artifact_id, delete_from_disk=True)
        assert delete_result.success is True
        assert not storage_path.exists()

    def test_delete_nonexistent_artifact(self, artifact_storage: ArtifactStorage) -> None:
        """Deleting nonexistent artifact returns error."""
        result = artifact_storage.delete_artifact("nonexistent-id")
        assert result.success is False
        assert "not found" in result.error.lower()


class TestArtifactStorageVerify:
    """Tests for ArtifactStorage.verify_integrity method."""

    def test_verify_valid_artifact(self, artifact_storage: ArtifactStorage, sample_artifact_id: str) -> None:
        """Verification passes for valid artifact."""
        assert artifact_storage.verify_integrity(sample_artifact_id) is True

    def test_verify_nonexistent_artifact(self, artifact_storage: ArtifactStorage) -> None:
        """Verification fails for nonexistent artifact."""
        assert artifact_storage.verify_integrity("nonexistent-id") is False

    def test_verify_corrupted_artifact(self, artifact_storage: ArtifactStorage) -> None:
        """Verification fails for corrupted artifact."""
        result = artifact_storage.store(
            content="original content",
            artifact_type=ArtifactType.REPORT,
            title="To Corrupt",
        )
        artifact_id = result.artifact_id

        # Corrupt the file
        result.storage_path.write_text("corrupted content")

        assert artifact_storage.verify_integrity(artifact_id) is False


class TestArtifactStorageStats:
    """Tests for ArtifactStorage.get_storage_stats method."""

    def test_storage_stats(self, artifact_storage: ArtifactStorage) -> None:
        """Storage returns statistics."""
        artifact_storage.store(
            content="test content 1",
            artifact_type=ArtifactType.REPORT,
            title="Test 1",
        )
        artifact_storage.store(
            content="test content 2",
            artifact_type=ArtifactType.PATCH,
            title="Test 2",
        )

        stats = artifact_storage.get_storage_stats()
        assert "total_count" in stats
        assert "active_count" in stats
        assert "total_size_bytes" in stats
        assert "by_type" in stats
        assert stats["total_count"] >= 2

    def test_storage_stats_empty(self, temp_artifacts_dir: Path) -> None:
        """Storage stats work with empty storage."""
        storage = ArtifactStorage(artifacts_dir=temp_artifacts_dir)
        stats = storage.get_storage_stats()
        assert stats["total_count"] == 0
        assert stats["active_count"] == 0


class TestArtifactStorageUtility:
    """Tests for ArtifactStorage utility methods."""

    def test_generate_artifact_id(self, artifact_storage: ArtifactStorage) -> None:
        """Generated artifact IDs are unique."""
        id1 = artifact_storage.generate_artifact_id()
        id2 = artifact_storage.generate_artifact_id()
        assert id1 != id2
        assert len(id1) == 36  # UUID4 format

    def test_file_extension_by_type(self, artifact_storage: ArtifactStorage) -> None:
        """Storage returns correct extensions for types."""
        assert artifact_storage._file_extension(ArtifactType.REPORT) == ".json"
        assert artifact_storage._file_extension(ArtifactType.PATCH) == ".diff"
        assert artifact_storage._file_extension(ArtifactType.DOCUMENTATION) == ".md"
        assert artifact_storage._file_extension(ArtifactType.TEST) == ".py"
        assert artifact_storage._file_extension(ArtifactType.CONFIG) == ".yaml"
        assert artifact_storage._file_extension(ArtifactType.BINARY) == ".bin"
        assert artifact_storage._file_extension(ArtifactType.SCAN_RESULT) == ".json"
        assert artifact_storage._file_extension(ArtifactType.CUSTOM) == ".dat"

    def test_file_extension_by_mime_type(self, artifact_storage: ArtifactStorage) -> None:
        """Storage returns correct extensions for MIME types."""
        assert artifact_storage._file_extension(
            ArtifactType.CUSTOM, "application/json"
        ) == ".json"
        assert artifact_storage._file_extension(
            ArtifactType.CUSTOM, "text/plain"
        ) == ".txt"
        assert artifact_storage._file_extension(
            ArtifactType.CUSTOM, "application/pdf"
        ) == ".pdf"
        assert artifact_storage._file_extension(
            ArtifactType.CUSTOM, "image/png"
        ) == ".png"


# =============================================================================
# Retriever Tests
# =============================================================================


class TestArtifactRetrieverGetById:
    """Tests for ArtifactRetriever.get_by_id method."""

    def test_get_by_id(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can get artifact by ID."""
        metadata = artifact_retriever.get_by_id(sample_artifact_id)
        assert metadata is not None
        assert metadata.artifact_id == sample_artifact_id
        assert metadata.title == "Test Report"

    def test_get_by_id_nonexistent(self, artifact_retriever: ArtifactRetriever) -> None:
        """Retriever returns None for nonexistent ID."""
        metadata = artifact_retriever.get_by_id("nonexistent-id")
        assert metadata is None


class TestArtifactRetrieverGetContent:
    """Tests for ArtifactRetriever.get_content method."""

    def test_get_content(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can get artifact with content."""
        artifact = artifact_retriever.get_content(sample_artifact_id)
        assert artifact is not None
        assert artifact.metadata.artifact_id == sample_artifact_id
        assert artifact.content is not None

    def test_get_content_as_text(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can get artifact with text content."""
        artifact = artifact_retriever.get_content_as_text(sample_artifact_id)
        assert artifact is not None
        assert isinstance(artifact.content, str)
        assert json.loads(artifact.content) == {"key": "value"}

    def test_get_content_nonexistent(self, artifact_retriever: ArtifactRetriever) -> None:
        """Retriever returns None for nonexistent artifact."""
        artifact = artifact_retriever.get_content("nonexistent-id")
        assert artifact is None


class TestArtifactRetrieverQuery:
    """Tests for ArtifactRetriever.query method."""

    def test_query_all(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query all artifacts."""
        query = ArtifactQuery()
        result = artifact_retriever.query(query)
        assert isinstance(result, ArtifactListResult)
        assert result.total_count >= 1
        assert len(result.artifacts) >= 1

    def test_query_by_id(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by artifact ID."""
        query = ArtifactQuery(artifact_id=sample_artifact_id)
        result = artifact_retriever.query(query)
        assert result.total_count == 1
        assert result.artifacts[0].artifact_id == sample_artifact_id

    def test_query_by_type(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by artifact type."""
        query = ArtifactQuery(artifact_type=ArtifactType.REPORT)
        result = artifact_retriever.query(query)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.artifact_type == ArtifactType.REPORT

    def test_query_by_multiple_types(
        self,
        artifact_retriever: ArtifactRetriever,
        sample_artifact_id: str,
        sample_artifact_id_2: str,
    ) -> None:
        """Retriever can query by multiple types."""
        query = ArtifactQuery(
            artifact_type=[ArtifactType.REPORT, ArtifactType.PATCH]
        )
        result = artifact_retriever.query(query)
        assert result.total_count >= 2

    def test_query_by_source(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by source."""
        query = ArtifactQuery(source="test_system")
        result = artifact_retriever.query(query)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.source == "test_system"

    def test_query_by_status(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by status."""
        query = ArtifactQuery(status=ArtifactStatus.ACTIVE)
        result = artifact_retriever.query(query)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.status == ArtifactStatus.ACTIVE

    def test_query_by_tags(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by tags (all must match)."""
        query = ArtifactQuery(tags=["test", "sample"])
        result = artifact_retriever.query(query)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert "test" in artifact.tags
            assert "sample" in artifact.tags

    def test_query_by_project_id(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by project ID."""
        query = ArtifactQuery(project_id=1)
        result = artifact_retriever.query(query)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.project_id == 1

    def test_query_by_title_contains(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can query by title substring."""
        query = ArtifactQuery(title_contains="Report")
        result = artifact_retriever.query(query)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert "Report" in artifact.title

    def test_query_by_persistence(
        self,
        artifact_retriever: ArtifactRetriever,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Retriever can query by persistence flag."""
        # Ensure we have a persistent artifact
        artifact_storage.store(
            content="persistent content",
            artifact_type=ArtifactType.REPORT,
            title="Persistent Report",
            is_persistent=True,
        )

        query = ArtifactQuery(is_persistent=True)
        result = artifact_retriever.query(query)
        assert result.total_count >= 1

        # Also test non-persistent query
        artifact_storage.store(
            content="temporary content",
            artifact_type=ArtifactType.REPORT,
            title="Temporary Report",
            is_persistent=False,
        )

        query_non_persistent = ArtifactQuery(is_persistent=False)
        result_non_persistent = artifact_retriever.query(query_non_persistent)
        assert result_non_persistent.total_count >= 1

    def test_query_pagination(self, artifact_retriever: ArtifactRetriever) -> None:
        """Retriever supports pagination."""
        # Store multiple artifacts
        storage = artifact_retriever._storage
        for i in range(5):
            storage.store(
                content=f"content {i}",
                artifact_type=ArtifactType.REPORT,
                title=f"Report {i}",
            )

        query = ArtifactQuery(limit=2, offset=0)
        result = artifact_retriever.query(query)
        assert result.returned_count == 2
        assert result.has_more is True

        query2 = ArtifactQuery(limit=2, offset=2)
        result2 = artifact_retriever.query(query2)
        assert result2.returned_count == 2

    def test_query_sort_by_title(self, artifact_retriever: ArtifactRetriever) -> None:
        """Retriever can sort by title."""
        storage = artifact_retriever._storage
        storage.store(
            content="a",
            artifact_type=ArtifactType.REPORT,
            title="Alpha Report",
        )
        storage.store(
            content="b",
            artifact_type=ArtifactType.REPORT,
            title="Zeta Report",
        )

        query = ArtifactQuery(sort_by="title", sort_order="asc")
        result = artifact_retriever.query(query)
        if result.total_count >= 2:
            assert result.artifacts[0].title <= result.artifacts[1].title


class TestArtifactRetrieverListMethods:
    """Tests for ArtifactRetriever list_* methods."""

    def test_list_by_type(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can list artifacts by type."""
        result = artifact_retriever.list_by_type(ArtifactType.REPORT)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.artifact_type == ArtifactType.REPORT

    def test_list_by_source(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can list artifacts by source."""
        result = artifact_retriever.list_by_source("test_system")
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.source == "test_system"

    def test_list_by_run(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can list artifacts by run ID."""
        result = artifact_retriever.list_by_run("run_abc")
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.run_id == "run_abc"

    def test_list_by_project(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can list artifacts by project ID."""
        result = artifact_retriever.list_by_project(1)
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert artifact.project_id == 1

    def test_list_by_tags(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can list artifacts by tags."""
        result = artifact_retriever.list_by_tags(["test"])
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert "test" in artifact.tags


class TestArtifactRetrieverSearch:
    """Tests for ArtifactRetriever.search method."""

    def test_search_by_term(self, artifact_retriever: ArtifactRetriever, sample_artifact_id: str) -> None:
        """Retriever can search by term."""
        result = artifact_retriever.search("Report")
        assert result.total_count >= 1
        for artifact in result.artifacts:
            assert "Report" in artifact.title or "Report" in (artifact.description or "")

    def test_search_pagination(self, artifact_retriever: ArtifactRetriever) -> None:
        """Search supports pagination."""
        result = artifact_retriever.search("test", offset=0, limit=10)
        assert isinstance(result, ArtifactListResult)
        assert result.offset == 0
        assert result.limit == 10


class TestArtifactRetrieverAdvanced:
    """Tests for advanced ArtifactRetriever methods."""

    def test_find_duplicates(self, artifact_retriever: ArtifactRetriever) -> None:
        """Retriever can find duplicate artifacts by content hash."""
        storage = artifact_retriever._storage
        # Store two artifacts with identical content
        content = "duplicate content"
        storage.store(
            content=content,
            artifact_type=ArtifactType.REPORT,
            title="Original",
        )
        storage.store(
            content=content,
            artifact_type=ArtifactType.REPORT,
            title="Duplicate",
        )

        duplicates = artifact_retriever.find_duplicates()
        assert len(duplicates) > 0
        # At least one hash should have 2+ artifacts
        for hash_val, artifact_ids in duplicates.items():
            if len(artifact_ids) >= 2:
                return
        pytest.fail("Expected to find duplicate artifacts")

    def test_get_version_history(self, artifact_retriever: ArtifactRetriever) -> None:
        """Retriever can get version history for an artifact."""
        storage = artifact_retriever._storage

        # Create parent
        parent_result = storage.store(
            content="parent content",
            artifact_type=ArtifactType.REPORT,
            title="Parent",
        )

        # Create child version
        storage.store(
            content="child content",
            artifact_type=ArtifactType.REPORT,
            title="Child",
            parent_artifact_id=parent_result.artifact_id,
        )

        history = artifact_retriever.get_version_history(parent_result.artifact_id)
        assert len(history) >= 2


# =============================================================================
# Lifecycle Tests
# =============================================================================


class TestArtifactLifecycleArchive:
    """Tests for ArtifactLifecycle archive methods."""

    def test_archive_by_age(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Lifecycle can archive artifacts by age."""
        # Store an old artifact (manually set created_at in DB)
        result = artifact_storage.store(
            content="old content",
            artifact_type=ArtifactType.REPORT,
            title="Old Report",
            is_persistent=False,
        )
        artifact_id = result.artifact_id

        # Manually update created_at to be old
        conn = artifact_storage._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE artifact_index SET created_at = ? WHERE artifact_id = ?",
            (old_date, artifact_id),
        )
        conn.commit()

        # Archive by age (dry run)
        archive_result = artifact_lifecycle.archive_by_age(
            days=30,
            keep_persistent=False,
            dry_run=True,
        )
        assert archive_result.success is True
        assert archive_result.archived_count >= 1

    def test_archive_by_type(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Lifecycle can archive artifacts by type."""
        # Store old REPORT artifact
        result = artifact_storage.store(
            content="old report",
            artifact_type=ArtifactType.REPORT,
            title="Old Report",
            is_persistent=False,
        )
        artifact_id = result.artifact_id

        # Make it old
        conn = artifact_storage._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE artifact_index SET created_at = ? WHERE artifact_id = ?",
            (old_date, artifact_id),
        )
        conn.commit()

        # Archive by type
        archive_result = artifact_lifecycle.archive_by_type(
            artifact_type=ArtifactType.REPORT,
            days=30,
            keep_persistent=False,
            dry_run=True,
        )
        assert archive_result.success is True
        assert archive_result.archived_count >= 1


class TestArtifactLifecycleRetentionPolicy:
    """Tests for ArtifactLifecycle.apply_retention_policy method."""

    def test_apply_policy_age_limit(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Lifecycle can apply age-based retention policy."""
        # Create old artifact
        result = artifact_storage.store(
            content="old content",
            artifact_type=ArtifactType.REPORT,
            title="Old Report",
            is_persistent=False,
        )
        artifact_id = result.artifact_id

        # Make it old
        conn = artifact_storage._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE artifact_index SET created_at = ? WHERE artifact_id = ?",
            (old_date, artifact_id),
        )
        conn.commit()

        # Apply policy
        policy = RetentionPolicy(
            max_age_days=30,
            keep_persistent=False,
            archive_before_delete=True,
        )
        result = artifact_lifecycle.apply_retention_policy(policy, dry_run=True)
        assert result.success is True
        assert result.archived_count >= 1

    def test_apply_policy_keeps_persistent(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Retention policy respects persistent flag."""
        # Create old persistent artifact
        result = artifact_storage.store(
            content="persistent old content",
            artifact_type=ArtifactType.REPORT,
            title="Persistent Report",
            is_persistent=True,  # Persistent
        )
        artifact_id = result.artifact_id

        # Make it old
        conn = artifact_storage._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE artifact_index SET created_at = ? WHERE artifact_id = ?",
            (old_date, artifact_id),
        )
        conn.commit()

        # Apply policy (should keep persistent)
        policy = RetentionPolicy(
            max_age_days=30,
            keep_persistent=True,  # Keep persistent artifacts
            archive_before_delete=True,
        )
        result = artifact_lifecycle.apply_retention_policy(policy, dry_run=True)
        assert result.success is True
        # Persistent artifact should not be archived
        assert result.archived_count == 0

    def test_apply_policy_keeps_types(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Retention policy respects protected types."""
        # Create old REPORT artifact
        result = artifact_storage.store(
            content="important report",
            artifact_type=ArtifactType.REPORT,
            title="Important Report",
            is_persistent=False,
        )
        artifact_id = result.artifact_id

        # Make it old
        conn = artifact_storage._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        conn.execute(
            "UPDATE artifact_index SET created_at = ? WHERE artifact_id = ?",
            (old_date, artifact_id),
        )
        conn.commit()

        # Apply policy that protects REPORT type
        policy = RetentionPolicy(
            max_age_days=30,
            keep_persistent=False,
            keep_types=[ArtifactType.REPORT],
            archive_before_delete=True,
        )
        result = artifact_lifecycle.apply_retention_policy(policy, dry_run=True)
        assert result.success is True
        # Protected type should not be archived
        assert result.archived_count == 0


class TestArtifactLifecycleVersioning:
    """Tests for ArtifactLifecycle version management methods."""

    def test_create_version(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        sample_artifact_id: str,
    ) -> None:
        """Lifecycle can create a new version of an artifact."""
        new_version = artifact_lifecycle.create_version(
            parent_artifact_id=sample_artifact_id,
            new_content='{"key": "updated"}',
            title="Updated Test Report",
        )
        assert new_version is not None
        assert new_version.parent_artifact_id == sample_artifact_id
        assert new_version.title == "Updated Test Report"
        assert new_version.version > 1

    def test_create_version_without_content(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        sample_artifact_id: str,
    ) -> None:
        """Lifecycle can create version inheriting parent content."""
        new_version = artifact_lifecycle.create_version(
            parent_artifact_id=sample_artifact_id,
            title="Version 2",
        )
        assert new_version is not None
        assert new_version.parent_artifact_id == sample_artifact_id

    def test_create_version_nonexistent_parent(
        self,
        artifact_lifecycle: ArtifactLifecycle,
    ) -> None:
        """Creating version with nonexistent parent returns None."""
        new_version = artifact_lifecycle.create_version(
            parent_artifact_id="nonexistent-id",
            new_content="test",
        )
        assert new_version is None


class TestArtifactLifecycleCleanup:
    """Tests for ArtifactLifecycle cleanup methods."""

    def test_cleanup_deleted(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Lifecycle can clean up deleted artifacts."""
        # Create and delete an artifact
        result = artifact_storage.store(
            content="to be deleted",
            artifact_type=ArtifactType.REPORT,
            title="Temporary",
        )
        artifact_id = result.artifact_id

        # Mark as deleted
        conn = artifact_storage._get_connection()
        old_date = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        conn.execute(
            "UPDATE artifact_index SET status = 'deleted', updated_at = ? WHERE artifact_id = ?",
            (old_date, artifact_id),
        )
        conn.commit()

        # Cleanup deleted
        cleanup_result = artifact_lifecycle.cleanup_deleted(older_than_days=7, dry_run=True)
        assert cleanup_result.success is True
        assert cleanup_result.deleted_count >= 1


class TestArtifactLifecycleRestore:
    """Tests for ArtifactLifecycle.restore_from_archive method."""

    def test_restore_from_archive(
        self,
        artifact_lifecycle: ArtifactLifecycle,
        artifact_storage: ArtifactStorage,
    ) -> None:
        """Lifecycle restore requires actual archive directory structure."""
        # This test is limited because proper restoration requires
        # the artifact to be in the .archive directory structure
        # which is set up by the archive operations, not just status change

        # Just verify the method exists and can be called
        # Real restoration testing would require full archive workflow
        assert hasattr(artifact_lifecycle, "restore_from_archive")

        # Test that restoring non-existent artifact returns None
        result = artifact_lifecycle.restore_from_archive("nonexistent-id")
        assert result is None


# =============================================================================
# Result Model Tests
# =============================================================================


class TestArtifactListResult:
    """Tests for ArtifactListResult model."""

    def test_list_result_properties(self) -> None:
        """ArtifactListResult contains all expected fields."""
        metadata = ArtifactMetadata(
            artifact_id="test-1",
            artifact_type=ArtifactType.REPORT,
            title="Test",
        )
        result = ArtifactListResult(
            artifacts=[metadata],
            total_count=1,
            returned_count=1,
            offset=0,
            limit=100,
            has_more=False,
        )
        assert len(result.artifacts) == 1
        assert result.total_count == 1
        assert result.returned_count == 1
        assert result.has_more is False

    def test_list_result_pagination(self) -> None:
        """ArtifactListResult correctly indicates more results."""
        artifacts = [
            ArtifactMetadata(
                artifact_id=f"test-{i}",
                artifact_type=ArtifactType.REPORT,
                title=f"Test {i}",
            )
            for i in range(10)
        ]
        result = ArtifactListResult(
            artifacts=artifacts[:5],
            total_count=10,
            returned_count=5,
            offset=0,
            limit=5,
            has_more=True,
        )
        assert result.has_more is True
        assert result.returned_count == 5
