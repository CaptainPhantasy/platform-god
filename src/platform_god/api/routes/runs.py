"""
Run endpoints.

Endpoints for querying chain execution history and run status.
"""

import logging
from pathlib import Path

from fastapi import APIRouter, Query, status

from platform_god.api.schemas.exceptions import NotFoundError
from platform_god.api.schemas.responses import (
    AgentStatus,
    RunDetail,
    RunListResponse,
    RunStatus,
    RunSummary,
)
from platform_god.state.manager import StateManager

router = APIRouter()
logger = logging.getLogger(__name__)


def _convert_run_status(status: str) -> RunStatus:
    """Convert state manager run status to API RunStatus."""
    status_map = {
        "pending": RunStatus.PENDING,
        "running": RunStatus.RUNNING,
        "completed": RunStatus.COMPLETED,
        "failed": RunStatus.FAILED,
        "cancelled": RunStatus.CANCELLED,
    }
    return status_map.get(status.lower(), RunStatus.PENDING)


@router.get("", response_model=RunListResponse)
async def list_runs(
    repository_root: str | None = Query(None, description="Filter by repository root"),
    chain_name: str | None = Query(None, description="Filter by chain name"),
    status_filter: str | None = Query(None, alias="status", description="Filter by run status"),
    limit: int = Query(50, ge=1, le=500, description="Maximum results"),
    offset: int = Query(0, ge=0, description="Results to skip"),
) -> RunListResponse:
    """
    List chain execution runs.

    Supports filtering by repository, chain name, and status.

    Query Parameters:
        repository_root: Filter by repository root path
        chain_name: Filter by chain name
        status: Filter by run status (pending, running, completed, failed, cancelled)
        limit: Maximum results (default: 50, max: 500)
        offset: Number of results to skip (default: 0)

    Returns:
        RunListResponse with matching runs
    """
    state_mgr = StateManager()

    # Get runs from state manager
    repo_path = Path(repository_root) if repository_root else None
    runs = state_mgr.list_runs(repository_root=repo_path, limit=limit + offset)

    # Apply additional filters
    filtered_runs = []
    for run in runs:
        # Chain name filter
        if chain_name and run.chain_name != chain_name:
            continue

        # Status filter
        if status_filter and run.status.value != status_filter:
            continue

        filtered_runs.append(run)

    # Apply pagination
    total = len(filtered_runs)
    paginated_runs = filtered_runs[offset : offset + limit]

    # Convert to response format
    summaries = [
        RunSummary(
            run_id=run.run_id,
            chain_name=run.chain_name,
            repository=Path(run.repository_root).name,
            status=_convert_run_status(run.status.value),
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_ms=run.execution_time_ms,
        )
        for run in paginated_runs
    ]

    return RunListResponse(
        runs=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/recent", response_model=RunListResponse)
async def list_recent_runs(
    limit: int = Query(10, ge=1, le=100, description="Number of recent runs"),
) -> RunListResponse:
    """
    List recent chain runs across all repositories.

    Args:
        limit: Number of recent runs to return (default: 10, max: 100)

    Returns:
        RunListResponse with recent runs
    """
    return await list_runs(
        repository_root=None,
        chain_name=None,
        status_filter=None,
        limit=limit,
        offset=0,
    )


@router.get("/{run_id}", response_model=RunDetail)
async def get_run(run_id: str) -> RunDetail:
    """
    Get detailed information about a specific run.

    Args:
        run_id: Unique run identifier

    Returns:
        RunDetail with full run information

    Raises:
        NotFoundError: If run doesn't exist
    """
    state_mgr = StateManager()
    run = state_mgr.get_chain_run(run_id)

    if not run:
        raise NotFoundError(
            message=f"Run '{run_id}' not found",
            detail="The run may have been cleaned up or never existed",
        )

    # Convert agent results status
    agent_results = []
    for ar in run.agent_results:
        result = dict(ar)
        # Convert status string to enum
        if "status" in result:
            try:
                result["status"] = AgentStatus(result["status"]).value
            except (ValueError, KeyError):
                pass
        agent_results.append(result)

    return RunDetail(
        run_id=run.run_id,
        chain_name=run.chain_name,
        repository_root=run.repository_root,
        status=_convert_run_status(run.status.value),
        started_at=run.started_at,
        completed_at=run.completed_at,
        execution_time_ms=run.execution_time_ms,
        agent_results=agent_results,
        final_state=run.final_state,
        error=run.error,
    )


@router.get("/repository/{repository_name:path}", response_model=RunListResponse)
async def list_runs_by_repository(
    repository_name: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> RunListResponse:
    """
    List runs for a specific repository by name.

    Args:
        repository_name: Repository name (path component)
        limit: Maximum results
        offset: Results to skip

    Returns:
        RunListResponse with matching runs

    Raises:
        NotFoundError: If repository not found in any runs
    """
    state_mgr = StateManager()
    all_runs = state_mgr.list_runs(limit=1000)

    # Filter by repository name
    matching_runs = []
    for run in all_runs:
        if Path(run.repository_root).name == repository_name:
            matching_runs.append(run)

    if not matching_runs:
        raise NotFoundError(
            message=f"No runs found for repository: {repository_name}",
            detail="Check the repository name or view all runs without filtering",
        )

    # Apply pagination
    total = len(matching_runs)
    paginated_runs = matching_runs[offset : offset + limit]

    summaries = [
        RunSummary(
            run_id=run.run_id,
            chain_name=run.chain_name,
            repository=Path(run.repository_root).name,
            status=_convert_run_status(run.status.value),
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_ms=run.execution_time_ms,
        )
        for run in paginated_runs
    ]

    return RunListResponse(
        runs=summaries,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/chain/{chain_name}/latest", response_model=RunDetail)
async def get_latest_run_for_chain(
    chain_name: str,
    repository_root: str = Query(..., description="Repository root path"),
) -> RunDetail:
    """
    Get the latest run for a specific chain and repository.

    Args:
        chain_name: Name of the chain
        repository_root: Repository root path

    Returns:
        RunDetail with latest run information

    Raises:
        NotFoundError: If no run found
    """
    state_mgr = StateManager()
    run = state_mgr.get_last_run(Path(repository_root), chain_name)

    if not run:
        raise NotFoundError(
            message=f"No runs found for chain '{chain_name}' in repository",
            detail=f"Chain: {chain_name}, Repository: {repository_root}",
        )

    return RunDetail(
        run_id=run.run_id,
        chain_name=run.chain_name,
        repository_root=run.repository_root,
        status=_convert_run_status(run.status.value),
        started_at=run.started_at,
        completed_at=run.completed_at,
        execution_time_ms=run.execution_time_ms,
        agent_results=run.agent_results,
        final_state=run.final_state,
        error=run.error,
    )


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: str) -> None:
    """
    Delete a specific run record.

    Useful for cleaning up old run data.

    Args:
        run_id: Unique run identifier

    Raises:
        NotFoundError: If run doesn't exist
    """
    state_mgr = StateManager()
    run = state_mgr.get_chain_run(run_id)

    if not run:
        raise NotFoundError(
            message=f"Run '{run_id}' not found",
        )

    # Delete the run file
    run_file = state_mgr._runs_dir / f"{run_id}.json"
    if run_file.exists():
        run_file.unlink()

    # Update index
    if run_id in state_mgr._index.get("runs", []):
        state_mgr._index["runs"].remove(run_id)
        state_mgr._save_index()
