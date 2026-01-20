"""
Registry endpoints.

Endpoints for querying and managing the registry storage.
"""

import logging
from typing import Any

from fastapi import APIRouter, Query, status

from platform_god.api.schemas.exceptions import ConflictError, NotFoundError, ValidationError
from platform_god.api.schemas.requests import (
    RegistryEntityRequest,
    RegistryUpdateRequest,
)
from platform_god.api.schemas.responses import (
    RegistryEntityResponse,
    RegistryListResponse,
    RegistryOperationResponse,
)
from platform_god.registry.storage import Registry

router = APIRouter()
logger = logging.getLogger(__name__)


def _entity_to_response(entity_type: str, entity_id: str, entity: Any) -> RegistryEntityResponse:
    """Convert internal entity record to API response."""
    return RegistryEntityResponse(
        entity_id=entity.entity_id,
        entity_type=entity_type,
        data=entity.data,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
        checksum=entity.checksum,
        metadata=entity.metadata,
    )


@router.get("", response_model=RegistryListResponse)
async def list_entities(
    entity_type: str | None = Query(None, description="Filter by entity type"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results to skip"),
) -> RegistryListResponse:
    """
    List registry entities.

    Supports filtering by entity type.

    Query Parameters:
        entity_type: Filter by entity type (e.g., 'repository', 'agent', 'finding')
        limit: Maximum results (default: 100, max: 1000)
        offset: Number of results to skip (default: 0)

    Returns:
        RegistryListResponse with matching entities
    """
    registry = Registry()

    if entity_type:
        # List entities of specific type
        entities = registry.list_by_type(entity_type)
        total = len(entities)
        paginated = entities[offset : offset + limit]
    else:
        # List all entities from index
        all_entities = []
        for etype, entity_ids in registry.index.entities.items():
            for eid in entity_ids:
                entity = registry._load_entity(etype, eid)
                if entity:
                    all_entities.append((etype, entity))
        total = len(all_entities)
        paginated = all_entities[offset : offset + limit]

    # Convert to response
    response_entities = []
    for item in paginated:
        if entity_type:
            etype, entity = entity_type, item
        else:
            etype, entity = item

        response_entities.append(
            _entity_to_response(etype, entity.entity_id, entity)
        )

    return RegistryListResponse(
        entities=response_entities,
        entity_type=entity_type,
        total=total,
        limit=limit,
        offset=offset,
    )


# Specific routes must be defined before parameterized routes
@router.get("/types/list", response_model=list[str])
async def list_entity_types() -> list[str]:
    """
    List all entity types currently in the registry.

    Returns:
        List of entity type names
    """
    registry = Registry()
    return list(registry.index.entities.keys())


@router.get("/index", response_model=dict[str, Any])
async def get_registry_index() -> dict[str, Any]:
    """
    Get the registry index with all entity types and counts.

    Returns:
        Dictionary with registry index information
    """
    registry = Registry()

    index_data = {
        "version": registry.index.version,
        "last_updated": registry.index.last_updated,
        "entity_types": {
            etype: len(eids)
            for etype, eids in registry.index.entities.items()
        },
        "total_entities": sum(len(eids) for eids in registry.index.entities.values()),
    }

    return index_data


# Parameterized routes (defined after specific routes)
@router.get("/{entity_type}/{entity_id}", response_model=RegistryEntityResponse)
async def get_entity(entity_type: str, entity_id: str) -> RegistryEntityResponse:
    """
    Get a specific entity from the registry.

    Args:
        entity_type: Type of entity
        entity_id: Unique entity identifier

    Returns:
        RegistryEntityResponse with entity data

    Raises:
        NotFoundError: If entity doesn't exist
    """
    registry = Registry()
    result = registry.read(entity_type, entity_id)

    if result.status != "success":
        raise NotFoundError(
            message=f"Entity '{entity_id}' of type '{entity_type}' not found",
            detail=result.error,
        )

    entity = registry._load_entity(entity_type, entity_id)
    if not entity:
        raise NotFoundError(
            message=f"Entity '{entity_id}' of type '{entity_type}' not found",
        )

    return _entity_to_response(entity_type, entity_id, entity)


@router.post("", response_model=RegistryOperationResponse, status_code=status.HTTP_201_CREATED)
async def register_entity(request: RegistryEntityRequest) -> RegistryOperationResponse:
    """
    Register a new entity in the registry.

    Args:
        request: Entity registration request

    Returns:
        RegistryOperationResponse with operation result

    Raises:
        ConflictError: If entity already exists
    """
    registry = Registry()

    result = registry.register(
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        entity_data=request.data,
    )

    if result.status == "failure":
        if "already exists" in result.error:
            raise ConflictError(
                message=f"Entity '{request.entity_id}' already exists",
                detail=result.error,
            )
        raise ValidationError(
            fields={"entity_id": result.error}
        )

    # Add metadata if provided
    if request.metadata:
        entity = registry._load_entity(request.entity_type, request.entity_id)
        if entity:
            entity.metadata = request.metadata
            registry._save_entity(entity, request.entity_type)

    return RegistryOperationResponse(
        status=result.status,
        operation=result.operation,
        entity_type=request.entity_type,
        entity_id=request.entity_id,
        audit_ref=result.audit_ref,
        checksum=result.after_state and registry.index.checksums.get(request.entity_id),
    )


@router.put("/{entity_type}/{entity_id}", response_model=RegistryOperationResponse)
async def update_entity(
    entity_type: str,
    entity_id: str,
    request: RegistryUpdateRequest,
) -> RegistryOperationResponse:
    """
    Update an existing entity in the registry.

    Args:
        entity_type: Type of entity
        entity_id: Unique entity identifier
        request: Update request with new data

    Returns:
        RegistryOperationResponse with operation result

    Raises:
        NotFoundError: If entity doesn't exist
    """
    registry = Registry()

    # Get existing entity
    existing = registry._load_entity(entity_type, entity_id)
    if not existing:
        raise NotFoundError(
            message=f"Entity '{entity_id}' of type '{entity_type}' not found",
        )

    # Merge or replace data
    if request.merge:
        update_data = {**existing.data, **request.data}
    else:
        update_data = request.data

    result = registry.update(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_data=update_data,
    )

    if result.status == "failure":
        raise ValidationError(
            fields={"entity_id": result.error}
        )

    return RegistryOperationResponse(
        status=result.status,
        operation=result.operation,
        entity_type=entity_type,
        entity_id=entity_id,
        audit_ref=result.audit_ref,
        checksum=registry.index.checksums.get(entity_id),
    )


@router.delete("/{entity_type}/{entity_id}", response_model=RegistryOperationResponse)
async def deregister_entity(entity_type: str, entity_id: str) -> RegistryOperationResponse:
    """
    Remove an entity from the registry.

    Args:
        entity_type: Type of entity
        entity_id: Unique entity identifier

    Returns:
        RegistryOperationResponse with operation result

    Raises:
        NotFoundError: If entity doesn't exist
    """
    registry = Registry()

    result = registry.deregister(
        entity_type=entity_type,
        entity_id=entity_id,
    )

    if result.status == "failure":
        raise NotFoundError(
            message=f"Entity '{entity_id}' of type '{entity_type}' not found",
            detail=result.error,
        )

    return RegistryOperationResponse(
        status=result.status,
        operation=result.operation,
        entity_type=entity_type,
        entity_id=entity_id,
        audit_ref=result.audit_ref,
    )


@router.post("/{entity_type}/{entity_id}/verify", response_model=dict[str, Any])
async def verify_entity_integrity(entity_type: str, entity_id: str) -> dict[str, Any]:
    """
    Verify the integrity of an entity by comparing checksums.

    Args:
        entity_type: Type of entity
        entity_id: Unique entity identifier

    Returns:
        Dictionary with verification result

    Raises:
        NotFoundError: If entity doesn't exist
    """
    registry = Registry()

    entity = registry._load_entity(entity_type, entity_id)
    if not entity:
        raise NotFoundError(
            message=f"Entity '{entity_id}' of type '{entity_type}' not found",
        )

    stored_checksum = registry.index.checksums.get(entity_id)
    computed_checksum = entity.compute_checksum()

    is_valid = stored_checksum == computed_checksum

    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "valid": is_valid,
        "stored_checksum": stored_checksum,
        "computed_checksum": computed_checksum,
    }
