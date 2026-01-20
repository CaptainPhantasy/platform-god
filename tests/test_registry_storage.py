"""Tests for registry storage CRUD operations."""

from pathlib import Path

import pytest

from platform_god.core.exceptions import EntityExistsError, EntityNotFoundError
from platform_god.registry.storage import (
    EntityOperation,
    EntityRecord,
    Registry,
    RegistryIndex,
)


class TestEntityOperation:
    """Tests for EntityOperation enum."""

    def test_all_operations_defined(self) -> None:
        """All expected operations are defined."""
        expected = {"read", "register", "update", "deregister"}
        actual = {eo.value for eo in EntityOperation}
        assert actual == expected


class TestRegistryIndex:
    """Tests for RegistryIndex model."""

    def test_index_creation(self) -> None:
        """RegistryIndex can be created."""
        idx = RegistryIndex()
        assert idx.version == "1.0"
        assert idx.entities == {}
        assert idx.checksums == {}

    def test_add_entity(self) -> None:
        """RegistryIndex can add entities."""
        idx = RegistryIndex()
        idx.add_entity("test_type", "test_id")

        assert "test_type" in idx.entities
        assert "test_id" in idx.entities["test_type"]

    def test_remove_entity(self) -> None:
        """RegistryIndex can remove entities."""
        idx = RegistryIndex()
        idx.add_entity("test_type", "test_id")
        idx.remove_entity("test_type", "test_id")

        assert "test_id" not in idx.entities.get("test_type", [])

    def test_update_checksum(self) -> None:
        """RegistryIndex can update checksums."""
        idx = RegistryIndex()
        idx.update_checksum("test_id", "abc123")

        assert idx.checksums["test_id"] == "abc123"


class TestEntityRecord:
    """Tests for EntityRecord model."""

    def test_record_creation(self) -> None:
        """EntityRecord can be created."""
        record = EntityRecord(
            entity_id="test_001",
            entity_type="test_type",
            data={"key": "value"},
        )
        assert record.entity_id == "test_001"
        assert record.entity_type == "test_type"
        assert record.data["key"] == "value"

    def test_compute_checksum(self) -> None:
        """EntityRecord can compute checksum from data."""
        record = EntityRecord(
            entity_id="test_001",
            entity_type="test_type",
            data={"key": "value"},
        )
        checksum = record.compute_checksum()

        assert checksum is not None
        assert len(checksum) == 64  # SHA256 hex length

    def test_update_data(self) -> None:
        """EntityRecord can update data and refresh checksum."""
        record = EntityRecord(
            entity_id="test_001",
            entity_type="test_type",
            data={"key": "value"},
        )
        old_checksum = record.compute_checksum()

        record.update_data({"new_key": "new_value"})
        new_checksum = record.checksum

        assert "new_key" in record.data
        assert new_checksum != old_checksum


class TestRegistry:
    """Tests for Registry class."""

    def test_registry_initialization(self, temp_dir: Path) -> None:
        """Registry initializes with storage directories."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        assert registry_dir.exists()
        assert audit_dir.exists()

    def test_register_entity(self, temp_dir: Path) -> None:
        """Registry can register new entities."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        result = registry.register(
            "test_type",
            "test_001",
            {"key": "value"},
        )

        assert result.status == "success"
        assert result.entity_id == "test_001"

    def test_register_duplicate_fails(self, temp_dir: Path) -> None:
        """Registry rejects duplicate entity registration."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        # First registration
        registry.register("test_type", "test_001", {"key": "value"})

        # Duplicate registration raises EntityExistsError
        with pytest.raises(EntityExistsError, match="already exists"):
            registry.register("test_type", "test_001", {"key": "value2"})

    def test_read_entity(self, temp_dir: Path) -> None:
        """Registry can read registered entities."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        registry.register("test_type", "test_001", {"key": "value"})
        result = registry.read("test_type", "test_001")

        assert result.status == "success"
        assert result.after_state["key"] == "value"

    def test_read_nonexistent_fails(self, temp_dir: Path) -> None:
        """Registry raises EntityNotFoundError for non-existent entity."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        with pytest.raises(EntityNotFoundError, match="not found"):
            registry.read("test_type", "nonexistent")

    def test_update_entity(self, temp_dir: Path) -> None:
        """Registry can update existing entities."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        registry.register("test_type", "test_001", {"key": "value"})
        result = registry.update("test_type", "test_001", {"key": "new_value"})

        assert result.status == "success"
        assert result.after_state["key"] == "new_value"

    def test_update_nonexistent_fails(self, temp_dir: Path) -> None:
        """Registry cannot update non-existent entities."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        with pytest.raises(EntityNotFoundError, match="not found"):
            registry.update("test_type", "nonexistent", {"key": "value"})

    def test_deregister_entity(self, temp_dir: Path) -> None:
        """Registry can deregister entities."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        registry.register("test_type", "test_001", {"key": "value"})
        result = registry.deregister("test_type", "test_001")

        assert result.status == "success"

        # Verify entity is gone - should raise EntityNotFoundError
        with pytest.raises(EntityNotFoundError):
            registry.read("test_type", "test_001")

    def test_deregister_nonexistent_fails(self, temp_dir: Path) -> None:
        """Registry cannot deregister non-existent entities."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        with pytest.raises(EntityNotFoundError, match="not found"):
            registry.deregister("test_type", "nonexistent")

    def test_list_by_type(self, temp_dir: Path) -> None:
        """Registry can list entities by type."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        registry.register("test_type", "test_001", {"key": "value1"})
        registry.register("test_type", "test_002", {"key": "value2"})
        registry.register("other_type", "test_003", {"key": "value3"})

        entities = registry.list_by_type("test_type")

        assert len(entities) == 2
        assert all(e.entity_type == "test_type" for e in entities)

    def test_verify_integrity(self, temp_dir: Path) -> None:
        """Registry can verify entity integrity."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"
        registry = Registry(registry_dir=registry_dir, audit_dir=audit_dir)

        registry.register("test_type", "test_001", {"key": "value"})

        # Integrity should pass
        assert registry.verify_integrity("test_type", "test_001") is True

    def test_index_persistence(self, temp_dir: Path) -> None:
        """Registry persists and reloads index."""
        registry_dir = temp_dir / "registry"
        audit_dir = temp_dir / "audit"

        # Create registry and add entity
        registry1 = Registry(registry_dir=registry_dir, audit_dir=audit_dir)
        registry1.register("test_type", "test_001", {"key": "value"})

        # Create new registry instance (should reload index)
        registry2 = Registry(registry_dir=registry_dir, audit_dir=audit_dir)
        result = registry2.read("test_type", "test_001")

        assert result.status == "success"
