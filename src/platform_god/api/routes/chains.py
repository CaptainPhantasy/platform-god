"""
Chain endpoints.

Endpoints for executing agent chains and managing chain definitions.
"""

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, status

from platform_god.api.schemas.exceptions import NotFoundError, ValidationError
from platform_god.api.schemas.requests import ChainCancelRequest, ChainExecuteRequest, ChainType
from platform_god.api.schemas.responses import (
    AgentStatus,
    ChainExecuteResponse,
    ChainListResponse,
    ChainStepResponse,
    ChainStopReason,
    ChainTypeInfo,
)
from platform_god.agents.executor import ExecutionMode
from platform_god.orchestrator.core import (
    ChainDefinition,
    ChainResult,
    Orchestrator,
)

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store for running chains (in production, use Redis or a database)
_running_chains: dict[str, Any] = {}


@router.get("", response_model=ChainListResponse)
async def list_chains() -> ChainListResponse:
    """
    List all available predefined chain types.

    Returns:
        ChainListResponse with available chain types
    """
    chains = [
        ChainTypeInfo(
            name="discovery",
            description="Scan repository and generate initial report",
            step_count=4,
            steps=["PG_DISCOVERY", "PG_STACKMAP", "PG_HEALTH_SCORE", "PG_REPORT_WRITER"],
        ),
        ChainTypeInfo(
            name="security_scan",
            description="Scan for secrets and security risks",
            step_count=3,
            steps=["PG_DISCOVERY", "PG_SECRETS_AND_RISK", "PG_NEXT_STEPS"],
        ),
        ChainTypeInfo(
            name="dependency_audit",
            description="Analyze dependencies for vulnerabilities",
            step_count=4,
            steps=["PG_DISCOVERY", "PG_DEPENDENCY", "PG_SECRETS_AND_RISK", "PG_REPORT_WRITER"],
        ),
        ChainTypeInfo(
            name="doc_generation",
            description="Generate documentation from code analysis",
            step_count=5,
            steps=[
                "PG_DISCOVERY",
                "PG_STACKMAP",
                "PG_ENGINEERING_PRINCIPLES",
                "PG_DOC_AUDIT",
                "PG_DOC_MANAGER",
            ],
        ),
        ChainTypeInfo(
            name="tech_debt",
            description="Analyze technical debt and generate remediation plan",
            step_count=5,
            steps=[
                "PG_DISCOVERY",
                "PG_STACKMAP",
                "PG_HEALTH_SCORE",
                "PG_REFACTOR_PLANNER",
                "PG_NEXT_STEPS",
            ],
        ),
        ChainTypeInfo(
            name="full_analysis",
            description="Complete repository analysis with all metrics",
            step_count=8,
            steps=[
                "PG_DISCOVERY",
                "PG_STACKMAP",
                "PG_HEALTH_SCORE",
                "PG_DEPENDENCY",
                "PG_SECRETS_AND_RISK",
                "PG_DOC_AUDIT",
                "PG_RELEASE_READINESS",
                "PG_REPORT_WRITER",
            ],
        ),
    ]

    return ChainListResponse(chains=chains)


def _get_chain_definition(chain_type: ChainType, steps: list[dict[str, Any]] | None) -> ChainDefinition:
    """
    Get a chain definition by type.

    Args:
        chain_type: Type of chain
        steps: Custom steps for custom chains

    Returns:
        ChainDefinition instance

    Raises:
        ValidationError: If chain type is invalid
    """
    if chain_type == ChainType.DISCOVERY:
        return ChainDefinition.discovery_chain()
    elif chain_type == ChainType.SECURITY_SCAN:
        return ChainDefinition.security_scan_chain()
    elif chain_type == ChainType.DEPENDENCY_AUDIT:
        return ChainDefinition.dependency_audit_chain()
    elif chain_type == ChainType.DOC_GENERATION:
        return ChainDefinition.doc_generation_chain()
    elif chain_type == ChainType.TECH_DEBT:
        return ChainDefinition.tech_debt_chain()
    elif chain_type == ChainType.FULL_ANALYSIS:
        return ChainDefinition.full_analysis_chain()
    elif chain_type == ChainType.CUSTOM:
        if not steps:
            raise ValidationError(
                fields={"steps": "steps required for custom chains"}
            )
        # Build custom chain from steps
        from platform_god.orchestrator.core import AgentStep

        return ChainDefinition(
            name="custom",
            description="Custom chain",
            steps=[
                AgentStep(
                    agent_name=step["agent_name"],
                    input_mapping=step.get("input_mapping"),
                    output_key=step.get("output_key"),
                    continue_on_failure=step.get("continue_on_failure", False),
                )
                for step in steps
            ],
        )
    else:
        raise ValidationError(
            fields={"chain_type": f"Unknown chain type: {chain_type}"}
        )


@router.post("/execute", response_model=ChainExecuteResponse, status_code=status.HTTP_202_ACCEPTED)
async def execute_chain(
    request: ChainExecuteRequest,
    background_tasks: BackgroundTasks,
) -> ChainExecuteResponse:
    """
    Execute an agent chain.

    Chains execute synchronously. For long-running chains,
    consider implementing async execution with status polling.

    Args:
        request: Chain execution request
        background_tasks: FastAPI background tasks

    Returns:
        ChainExecuteResponse with execution results

    Raises:
        ValidationError: If request validation fails
        NotFoundError: If referenced agents don't exist
    """
    # Get chain definition
    chain = _get_chain_definition(request.chain_type, request.steps)

    # Set initial state if provided
    if request.initial_state:
        chain.initial_state = request.initial_state

    # Create orchestrator
    orchestrator = Orchestrator()

    # Execute chain
    execution_mode = ExecutionMode(request.mode.value)
    result: ChainResult = orchestrator.execute_chain(
        chain=chain,
        repository_root=Path(request.repository_root),
        mode=execution_mode,
    )

    # Record the run in state manager
    from platform_god.state.manager import StateManager

    state_mgr = StateManager()
    chain_run = state_mgr.record_chain_run(
        chain_name=result.chain_name,
        repository_root=Path(request.repository_root),
        result=result,
    )

    # Convert steps to response format
    steps_response = [
        ChainStepResponse(
            agent_name=step.agent_name,
            status=AgentStatus(step.status.value),
            output_key=None,  # Would need to track this in ChainResult
            execution_time_ms=step.execution_time_ms,
            error_message=step.error_message,
        )
        for step in result.results
    ]

    # Calculate total execution time
    execution_time_ms = sum(r.execution_time_ms or 0 for r in result.results)

    return ChainExecuteResponse(
        chain_name=result.chain_name,
        status=ChainStopReason(result.status.value),
        completed_steps=result.completed_steps,
        total_steps=result.total_steps,
        steps=steps_response,
        final_state=result.final_state,
        execution_time_ms=execution_time_ms,
        run_id=chain_run.run_id,
        error=result.error,
    )


@router.post("/{chain_name}/cancel", status_code=status.HTTP_200_OK)
async def cancel_chain(
    chain_name: str,
    request: ChainCancelRequest | None = None,
) -> dict[str, str]:
    """
    Cancel a running chain.

    Note: Current implementation doesn't support true cancellation
    of running chains. This endpoint is provided for API completeness
    and future implementation.

    Args:
        chain_name: Name of the chain to cancel
        request: Optional cancellation reason

    Returns:
        Cancellation confirmation

    Raises:
        NotFoundError: If no running chain found
    """
    # Check if chain is running
    if chain_name not in _running_chains:
        raise NotFoundError(
            message=f"No running chain found: {chain_name}",
            detail="Chain may have already completed or never started",
        )

    # Remove from running chains
    del _running_chains[chain_name]

    reason = request.reason if request and request.reason else "Cancelled via API"

    logger.info(f"Chain '{chain_name}' cancelled: {reason}")

    return {
        "status": "cancelled",
        "chain_name": chain_name,
        "reason": reason,
    }


@router.get("/{chain_name}", response_model=ChainTypeInfo)
async def get_chain_info(chain_name: str) -> ChainTypeInfo:
    """
    Get information about a specific chain type.

    Args:
        chain_name: Name of the chain

    Returns:
        ChainTypeInfo with chain details

    Raises:
        NotFoundError: If chain type doesn't exist
    """
    chains = await list_chains()
    for chain in chains.chains:
        if chain.name == chain_name:
            return chain

    available = [c.name for c in chains.chains]
    raise NotFoundError(
        message=f"Chain '{chain_name}' not found",
        detail=f"Available chains: {', '.join(available)}",
    )
