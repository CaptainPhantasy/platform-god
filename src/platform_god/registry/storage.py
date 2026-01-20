"""
Registry Storage - persistent entity tracking with audit.

Implements the var/registry/ storage layer for tracked entities.
"""

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from platform_god.core.exceptions import (
    ChecksumMismatchError,
    EntityExistsError,
    EntityNotFoundError,
)
from pydantic import BaseModel, Field


class EntityOperation(Enum):
    """Operations on registry entities."""

    READ = "read"
    REGISTER = "register"
    UPDATE = "update"
    DEREGISTER = "deregister"


class RegistryIndex(BaseModel):
    """Root index of the registry."""

    version: str = "1.0"
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    entities: dict[str, list[str]] = Field(
        default_factory=dict, description="entity_type -> [entity_ids]"
    )
    checksums: dict[str, str] = Field(
        default_factory=dict, description="entity_id -> sha256"
    )

    def add_entity(self, entity_type: str, entity_id: str) -> None:
        """Add an entity to the index."""
        if entity_type not in self.entities:
            self.entities[entity_type] = []
        if entity_id not in self.entities[entity_type]:
            self.entities[entity_type].append(entity_id)
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def remove_entity(self, entity_type: str, entity_id: str) -> None:
        """Remove an entity from the index."""
        if entity_type in self.entities and entity_id in self.entities[entity_type]:
            self.entities[entity_type].remove(entity_id)
        self.checksums.pop(entity_id, None)
        self.last_updated = datetime.now(timezone.utc).isoformat()

    def update_checksum(self, entity_id: str, checksum: str) -> None:
        """Update integrity checksum for an entity."""
        self.checksums[entity_id] = checksum
        self.last_updated = datetime.now(timezone.utc).isoformat()


class EntityRecord(BaseModel):
    """A single registry entity record."""

    entity_id: str
    entity_type: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checksum: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    def compute_checksum(self) -> str:
        """Compute SHA256 checksum of entity data."""
        data_str = json.dumps(self.data, sort_keys=True)
        return hashlib.sha256(data_str.encode()).hexdigest()

    def update_data(self, new_data: dict[str, Any]) -> None:
        """Update entity data and refresh checksum."""
        self.data = {**self.data, **new_data}
        self.updated_at = datetime.now(timezone.utc).isoformat()
        self.checksum = self.compute_checksum()


@dataclass
class RegistryResult:
    """Result of a registry operation."""

    status: str  # "success" or "failure"
    operation: str
    entity_type: str
    entity_id: str
    before_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    audit_ref: str = ""
    error: str = ""


class Registry:
    """
    Registry storage backend.

    Manages var/registry/ with:
    - _INDEX.json (root index)
    - {entity_type}/{entity_id}.json (entity records)
    - Audit logging to var/audit/registry_log.jsonl
    """

    INDEX_FILE = "_INDEX.json"

    def __init__(self, registry_dir: Path | None = None, audit_dir: Path | None = None):
        """Initialize registry with storage directories."""
        self._registry_dir = registry_dir or Path("var/registry")
        self._audit_dir = audit_dir or Path("var/audit")
        self._registry_dir.mkdir(parents=True, exist_ok=True)
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._index: RegistryIndex | None = None

    @property
    def index(self) -> RegistryIndex:
        """Get or create the registry index."""
        if self._index is None:
            self._index = self._load_index()
        return self._index

    def _load_index(self) -> RegistryIndex:
        """Load index from disk or create new."""
        index_path = self._registry_dir / self.INDEX_FILE
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text())
                return RegistryIndex(**data)
            except (json.JSONDecodeError, ValueError):
                pass
        return RegistryIndex()

    def _save_index(self) -> None:
        """Persist index to disk atomically using write-replace pattern."""
        index_path = self._registry_dir / self.INDEX_FILE
        temp_path = self._registry_dir / f"{self.INDEX_FILE}.tmp"

        try:
            # Write to temporary file in same directory
            temp_path.write_text(self.index.model_dump_json(indent=2))
            # Atomic replace operation
            os.replace(temp_path, index_path)
        except Exception:
            # Clean up temp file on any exception
            temp_path.unlink(missing_ok=True)
            raise

    def _entity_path(self, entity_type: str, entity_id: str) -> Path:
        """Get file path for an entity record."""
        type_dir = self._registry_dir / entity_type
        type_dir.mkdir(parents=True, exist_ok=True)
        return type_dir / f"{entity_id}.json"

    def _load_entity(self, entity_type: str, entity_id: str) -> EntityRecord | None:
        """Load entity record from disk."""
        path = self._entity_path(entity_type, entity_id)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return EntityRecord(**data)
            except (json.JSONDecodeError, ValueError):
                pass
        return None

    def _save_entity(self, entity: EntityRecord, entity_type: str) -> None:
        """Save entity record to disk."""
        path = self._entity_path(entity_type, entity.entity_id)
        entity.checksum = entity.compute_checksum()
        path.write_text(entity.model_dump_json(indent=2))

    def _write_audit_log(self, result: RegistryResult) -> str:
        """Write audit log entry and return reference."""
        audit_ref = str(uuid.uuid4())[:8]
        log_path = self._audit_dir / "registry_log.jsonl"

        entry = {
            "audit_ref": audit_ref,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": result.operation,
            "entity_type": result.entity_type,
            "entity_id": result.entity_id,
            "status": result.status,
            "error": result.error,
        }

        with open(log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return audit_ref

    def register(
        self, entity_type: str, entity_id: str, entity_data: dict[str, Any]
    ) -> RegistryResult:
        """
        Register a new entity.

        Raises:
            EntityExistsError: If entity already exists
        """
        # Check for collision
        existing = self._load_entity(entity_type, entity_id)
        if existing:
            raise EntityExistsError(
                f"Entity '{entity_id}' of type '{entity_type}' already exists",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        # Create entity record
        entity = EntityRecord(
            entity_id=entity_id,
            entity_type=entity_type,
            data=entity_data,
        )
        entity.checksum = entity.compute_checksum()

        # Save and update index
        self._save_entity(entity, entity_type)
        self.index.add_entity(entity_type, entity_id)
        self.index.update_checksum(entity_id, entity.checksum)
        self._save_index()

        # Audit
        result = RegistryResult(
            status="success",
            operation="register",
            entity_type=entity_type,
            entity_id=entity_id,
            after_state=entity.data,
        )
        result.audit_ref = self._write_audit_log(result)

        return result

    def update(
        self, entity_type: str, entity_id: str, entity_data: dict[str, Any]
    ) -> RegistryResult:
        """
        Update an existing entity.

        Raises:
            EntityNotFoundError: If entity does not exist
        """
        entity = self._load_entity(entity_type, entity_id)
        if not entity:
            raise EntityNotFoundError(
                f"Entity '{entity_id}' of type '{entity_type}' not found",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        before_state = entity.data.copy()
        entity.update_data(entity_data)

        self._save_entity(entity, entity_type)
        self.index.update_checksum(entity_id, entity.checksum)
        self._save_index()

        result = RegistryResult(
            status="success",
            operation="update",
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
            after_state=entity.data,
        )
        result.audit_ref = self._write_audit_log(result)

        return result

    def deregister(self, entity_type: str, entity_id: str) -> RegistryResult:
        """
        Remove an entity from the registry.

        Raises:
            EntityNotFoundError: If entity does not exist
        """
        entity = self._load_entity(entity_type, entity_id)
        if not entity:
            raise EntityNotFoundError(
                f"Entity '{entity_id}' of type '{entity_type}' not found",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        before_state = entity.data.copy()

        # Remove files
        path = self._entity_path(entity_type, entity_id)
        path.unlink(missing_ok=True)

        # Update index
        self.index.remove_entity(entity_type, entity_id)
        self._save_index()

        result = RegistryResult(
            status="success",
            operation="deregister",
            entity_type=entity_type,
            entity_id=entity_id,
            before_state=before_state,
        )
        result.audit_ref = self._write_audit_log(result)

        return result

    def read(self, entity_type: str, entity_id: str) -> RegistryResult:
        """
        Read an entity from the registry.

        Raises:
            EntityNotFoundError: If entity does not exist
        """
        entity = self._load_entity(entity_type, entity_id)
        if not entity:
            raise EntityNotFoundError(
                f"Entity '{entity_id}' of type '{entity_type}' not found",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        return RegistryResult(
            status="success",
            operation="read",
            entity_type=entity_type,
            entity_id=entity_id,
            after_state=entity.data,
        )

    def list_by_type(self, entity_type: str) -> list[EntityRecord]:
        """List all entities of a given type."""
        entity_ids = self.index.entities.get(entity_type, [])
        records = []
        for eid in entity_ids:
            entity = self._load_entity(entity_type, eid)
            if entity:
                records.append(entity)
        return records

    def verify_integrity(self, entity_type: str, entity_id: str) -> bool:
        """
        Verify entity checksum matches index.

        Raises:
            EntityNotFoundError: If entity does not exist
            ChecksumMismatchError: If checksums do not match
        """
        entity = self._load_entity(entity_type, entity_id)
        if not entity:
            raise EntityNotFoundError(
                f"Entity '{entity_id}' of type '{entity_type}' not found",
                entity_type=entity_type,
                entity_id=entity_id,
            )

        stored_checksum = self.index.checksums.get(entity_id)
        computed_checksum = entity.compute_checksum()

        if stored_checksum != computed_checksum:
            raise ChecksumMismatchError(
                f"Checksum mismatch for entity '{entity_id}'",
                entity_type=entity_type,
                entity_id=entity_id,
                expected=stored_checksum,
                actual=computed_checksum,
            )

        return True
