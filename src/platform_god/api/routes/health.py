"""
Health check endpoints.

Provides health status and version information for the API.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query

from platform_god.api.schemas.responses import HealthResponse
from platform_god.monitoring.health import (
    HealthCheckRunner,
    HealthStatus,
    get_overall_health,
    run_all_health_checks,
)
from platform_god.registry.storage import Registry
from platform_god.version import __version__

router = APIRouter()
logger = logging.getLogger(__name__)

# Global health check runner with 30-second cache
_health_runner = HealthCheckRunner(cache_ttl_seconds=30.0)


@router.get("", response_model=HealthResponse)
@router.get("/", response_model=HealthResponse)
async def health_check(
    include_llm: bool = Query(False, description="Include LLM connectivity check"),
    detailed: bool = Query(False, description="Return detailed health information"),
    force_refresh: bool = Query(False, description="Force fresh health checks"),
) -> HealthResponse:
    """
    Perform health check on API and dependencies.

    Returns status of:
    - Database/State storage (var/state/)
    - Registry storage (var/registry/)
    - Disk space availability
    - LLM API connectivity (optional, with include_llm=true)
    - Agents registry

    The endpoint uses cached results (30-second TTL) for fast responses.
    Use force_refresh=true to bypass cache.

    Args:
        include_llm: Whether to check LLM API connectivity
        detailed: Return detailed health information
        force_refresh: Force fresh health checks bypassing cache

    Returns:
        HealthResponse with status and component information
    """
    # Run health checks
    if force_refresh:
        results = run_all_health_checks(include_llm=include_llm)
    else:
        runner = _health_runner
        results = await runner.run_async(force_refresh=force_refresh, include_llm=include_llm)

    # Determine overall status
    overall_status = get_overall_health(results).value

    # Build components dict for response
    components: dict[str, str] = {}
    for name, result in results.items():
        if detailed:
            components[name] = f"{result.status.value}: {result.message}"
        else:
            components[name] = f"{result.status.value}: {result.message}"

    # Check agents registry (always included)
    try:
        from platform_god.agents.registry import get_global_registry

        agent_registry = get_global_registry()
        agent_count = len(agent_registry.list_all())
        components["agents"] = f"healthy ({agent_count} agents)"
    except Exception as e:
        components["agents"] = f"unhealthy: {e}"
        if overall_status == "healthy":
            overall_status = "degraded"
        logger.warning(f"Agent registry health check failed: {e}")

    return HealthResponse(
        status=overall_status,
        version=__version__,
        timestamp=datetime.now(timezone.utc).isoformat(),
        components=components,
    )


@router.get("/ping")
async def ping() -> dict[str, str]:
    """
    Simple ping endpoint for load balancer checks.

    This endpoint always succeeds and returns immediately.
    Use for quick liveness checks.

    Returns:
        {"pong": "timestamp"}
    """
    return {"pong": datetime.now(timezone.utc).isoformat()}


@router.get("/detailed")
async def health_detailed(
    include_llm: bool = Query(False, description="Include LLM connectivity check"),
) -> dict[str, Any]:
    """
    Detailed health check with full component information.

    Returns comprehensive health status including:
    - Individual check results with timings
    - Disk space details
    - Registry integrity information
    - System resource status

    Args:
        include_llm: Whether to check LLM API connectivity

    Returns:
        Detailed health information dictionary
    """
    results = run_all_health_checks(include_llm=include_llm)

    # Get agent count
    agent_count = 0
    try:
        from platform_god.agents.registry import get_global_registry
        agent_registry = get_global_registry()
        agent_count = len(agent_registry.list_all())
    except Exception:
        pass

    return {
        "status": get_overall_health(results).value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": __version__,
        "checks": {name: result.to_dict() for name, result in results.items()},
        "summary": {
            "total_checks": len(results),
            "healthy": sum(1 for r in results.values() if r.status == HealthStatus.HEALTHY),
            "degraded": sum(1 for r in results.values() if r.status == HealthStatus.DEGRADED),
            "unhealthy": sum(1 for r in results.values() if r.status == HealthStatus.UNHEALTHY),
            "unknown": sum(1 for r in results.values() if r.status == HealthStatus.UNKNOWN),
        },
        "agents": {"count": agent_count},
    }


@router.get("/ready")
async def readiness() -> dict[str, Any]:
    """
    Readiness check for Kubernetes/container orchestration.

    Returns 200 when the service is ready to handle requests.
    This checks that core dependencies are accessible.

    Returns:
        Readiness status with details
    """
    checks: dict[str, dict[str, bool | str]] = {}
    ready = True

    # Check registry
    try:
        registry = Registry()
        _ = registry.index
        checks["registry"] = {"ready": True}
    except Exception as e:
        checks["registry"] = {"ready": False, "error": str(e)}
        ready = False

    # Check state storage
    try:
        from platform_god.state.manager import StateManager
        state_mgr = StateManager()
        _ = state_mgr._index
        checks["state"] = {"ready": True}
    except Exception as e:
        checks["state"] = {"ready": False, "error": str(e)}
        ready = False

    return {
        "ready": ready,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.get("/live")
async def liveness() -> dict[str, str]:
    """
    Liveness check for Kubernetes/container orchestration.

    Returns 200 if the service is running.
    This is a lightweight check that always succeeds if the process is alive.

    Returns:
        Liveness status
    """
    return {
        "alive": "true",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
