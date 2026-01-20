"""
Agent endpoints.

Endpoints for listing, querying, and executing agents.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Request, status

from platform_god.api.schemas.exceptions import NotFoundError, ValidationError
from platform_god.api.schemas.requests import AgentExecuteRequest
from platform_god.api.schemas.responses import (
    AgentClass,
    AgentExecuteResponse,
    AgentExecutionResult,
    AgentListResponse,
    AgentPermissionLevel,
    AgentResponse,
    AgentStatus,
)
from platform_god.agents.executor import ExecutionContext, ExecutionHarness, ExecutionMode
from platform_god.agents.registry import get_global_registry
from platform_god.state.manager import get_state_manager

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=AgentListResponse)
async def list_agents(request: Request) -> AgentListResponse:
    """
    List all available agents.

    Can be filtered by agent_class or permissions via query parameters.

    Query Parameters:
        agent_class: Filter by agent class (e.g., "READ_ONLY_SCAN")
        permissions: Filter by permission level (e.g., "read_only")
        limit: Maximum results (default: 100, max: 1000)
        offset: Number of results to skip (default: 0)

    Returns:
        AgentListResponse with filtered agent list
    """
    # Parse query parameters
    params = request.query_params
    agent_class_filter = params.get("agent_class")
    permissions_filter = params.get("permissions")
    limit = int(params.get("limit", 100))
    offset = int(params.get("offset", 0))

    # Clamp limit
    limit = min(max(1, limit), 1000)

    # Get agents from registry
    registry = get_global_registry()
    all_agents = registry.list_all()

    # Apply filters
    filtered_agents = []
    for agent in all_agents:
        if agent_class_filter:
            if agent.agent_class.value != agent_class_filter:
                continue
        if permissions_filter:
            if agent.permissions.value != permissions_filter:
                continue
        filtered_agents.append(agent)

    # Apply pagination
    total = len(filtered_agents)
    paginated_agents = filtered_agents[offset : offset + limit]

    # Convert to response models
    agent_responses = [
        AgentResponse(
            name=agent.name,
            agent_class=AgentClass(agent.agent_class.value),
            role=agent.role,
            goal=agent.goal,
            permissions=AgentPermissionLevel(agent.permissions.value),
            allowed_paths=list(agent.allowed_paths),
            disallowed_paths=list(agent.disallowed_paths),
            input_schema=agent.input_schema,
            output_schema=agent.output_schema,
            stop_conditions=list(agent.stop_conditions),
            source_file=agent.source_file,
            content_hash=agent.content_hash,
        )
        for agent in paginated_agents
    ]

    return AgentListResponse(
        agents=agent_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{agent_name}", response_model=AgentResponse)
async def get_agent(agent_name: str) -> AgentResponse:
    """
    Get detailed information about a specific agent.

    Args:
        agent_name: Name of the agent to retrieve

    Returns:
        AgentResponse with detailed agent information

    Raises:
        NotFoundError: If agent does not exist
    """
    registry = get_global_registry()
    agent = registry.get(agent_name)

    if not agent:
        raise NotFoundError(
            message=f"Agent '{agent_name}' not found",
            detail=f"Available agents: {', '.join(registry.names())}",
        )

    return AgentResponse(
        name=agent.name,
        agent_class=AgentClass(agent.agent_class.value),
        role=agent.role,
        goal=agent.goal,
        permissions=AgentPermissionLevel(agent.permissions.value),
        allowed_paths=list(agent.allowed_paths),
        disallowed_paths=list(agent.disallowed_paths),
        input_schema=agent.input_schema,
        output_schema=agent.output_schema,
        stop_conditions=list(agent.stop_conditions),
        source_file=agent.source_file,
        content_hash=agent.content_hash,
    )


@router.post("/execute", response_model=AgentExecuteResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_agent(
    request: AgentExecuteRequest,
    background_tasks: BackgroundTasks,
) -> AgentExecuteResponse:
    """
    Execute a single agent.

    Execution happens synchronously for now. For long-running agents,
    consider using the chains endpoint or implement async execution.

    Args:
        request: Agent execution request
        background_tasks: FastAPI background tasks

    Returns:
        AgentExecuteResponse with execution result

    Raises:
        ValidationError: If request validation fails
        NotFoundError: If specified agent doesn't exist
    """
    # Get agent name from input data or use a default
    agent_name = request.input_data.get("agent_name")
    if not agent_name:
        raise ValidationError(
            fields={"agent_name": "agent_name must be provided in input_data"}
        )

    # Verify agent exists
    registry = get_global_registry()
    agent_def = registry.get(agent_name)
    if not agent_def:
        raise NotFoundError(
            message=f"Agent '{agent_name}' not found",
            detail=f"Available agents: {', '.join(registry.names())}",
        )

    # Get state manager and start tracking execution
    state_manager = get_state_manager()
    repository_root = Path(request.repository_root)

    # Start tracking the execution
    execution = state_manager.start_agent_execution(
        agent_name=agent_name,
        repository_root=repository_root,
        mode=request.mode.value,
        caller="api",
    )

    try:
        # Build execution context
        execution_mode = ExecutionMode(request.mode.value)
        context = ExecutionContext(
            repository_root=repository_root,
            agent_name=agent_name,
            mode=execution_mode,
            caller="api",
        )

        # Build input data
        input_data = {"repository_root": request.repository_root}
        input_data.update(request.input_data)

        # Execute agent
        harness = ExecutionHarness()
        result = harness.execute(agent_name, input_data, context)

        # Mark execution as completed
        state_manager.complete_agent_execution(
            execution_id=execution.execution_id,
            output_data=result.output_data,
            error=result.error_message,
            execution_time_ms=result.execution_time_ms,
        )

        # Convert to response
        return AgentExecuteResponse(
            result=AgentExecutionResult(
                agent_name=result.agent_name,
                agent_class=AgentClass(result.agent_class.value),
                status=AgentStatus(result.status.value),
                output_data=result.output_data,
                error_message=result.error_message,
                execution_time_ms=result.execution_time_ms,
                timestamp=result.timestamp,
            ),
            mode=request.mode.value,
        )
    except Exception as e:
        # Mark execution as failed on any exception
        state_manager.complete_agent_execution(
            execution_id=execution.execution_id,
            error=str(e),
        )
        raise


@router.get("/classes/list", response_model=dict[str, str])
async def list_agent_classes() -> dict[str, str]:
    """
    List all available agent classes with descriptions.

    Returns:
        Dictionary mapping agent class names to descriptions
    """
    return {
        "READ_ONLY_SCAN": "Read-only repository scanning agents",
        "PLANNING_SYNTHESIS": "Planning and synthesis agents",
        "REGISTRY_STATE": "Registry and state modification agents",
        "WRITE_GATED": "Write-gated agents with scoped write permissions",
        "CONTROL_PLANE": "Control plane agents with full permissions",
    }


@router.get("/permissions/list", response_model=dict[str, str])
async def list_permission_levels() -> dict[str, str]:
    """
    List all permission levels with descriptions.

    Returns:
        Dictionary mapping permission levels to descriptions
    """
    return {
        "read_only": "Can only read files, no write access",
        "write_gated": "Can write to specific allowed paths",
        "control_plane": "Full control plane access",
    }
