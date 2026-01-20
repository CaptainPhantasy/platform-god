"""
Metrics endpoints for Platform God.

Provides metrics in JSON and Prometheus formats.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from platform_god.monitoring.metrics import get_metrics_collector

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("", response_model=dict[str, Any])
@router.get("/", response_model=dict[str, Any])
async def get_metrics(
    format: str = Query("json", description="Response format: 'json' or 'prometheus'"),
) -> dict[str, Any] | PlainTextResponse:
    """
    Get system and application metrics.

    Returns metrics for:
    - Agent executions (counts, success rates, timings)
    - Chain executions (counts, success rates, timings)
    - System statistics (total runs, active repositories, etc.)

    Args:
        format: Response format - "json" (default) or "prometheus"

    Returns:
        Metrics in requested format
    """
    collector = get_metrics_collector()

    if format.lower() == "prometheus":
        prometheus_text = collector.to_prometheus()
        return PlainTextResponse(
            content=prometheus_text,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return collector.get_all_metrics()


@router.get("/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics() -> PlainTextResponse:
    """
    Get metrics in Prometheus text format.

    Returns metrics in Prometheus exposition format for scraping by
    Prometheus or compatible monitoring systems.

    Metrics include:
    - platform_god_agent_executions_total
    - platform_god_chain_executions_total
    - platform_god_errors_total
    - platform_god_agent_success_rate
    - platform_god_chain_success_rate
    - And more...

    Returns:
        Prometheus-formatted metrics as plain text
    """
    collector = get_metrics_collector()
    prometheus_text = collector.to_prometheus()

    return PlainTextResponse(
        content=prometheus_text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/agents")
async def get_agent_metrics(
    agent_name: str | None = Query(None, description="Specific agent name"),
) -> dict[str, Any]:
    """
    Get metrics for agent executions.

    Args:
        agent_name: Optional specific agent name

    Returns:
        Agent metrics dictionary
    """
    collector = get_metrics_collector()
    return {"metrics": collector.get_agent_metrics(agent_name)}


@router.get("/chains")
async def get_chain_metrics(
    chain_name: str | None = Query(None, description="Specific chain name"),
) -> dict[str, Any]:
    """
    Get metrics for chain executions.

    Args:
        chain_name: Optional specific chain name

    Returns:
        Chain metrics dictionary
    """
    collector = get_metrics_collector()
    return {"metrics": collector.get_chain_metrics(chain_name)}


@router.get("/system")
async def get_system_metrics() -> dict[str, Any]:
    """
    Get system-level metrics.

    Returns statistics including:
    - Total executions (agents and chains)
    - Error counts
    - Active repositories
    - Registry entity count
    - Uptime information

    Returns:
        System metrics dictionary
    """
    collector = get_metrics_collector()
    return collector.get_system_metrics()


@router.post("/reset")
async def reset_metrics(
    agent_name: str | None = Query(None, description="Reset metrics for specific agent"),
    chain_name: str | None = Query(None, description="Reset metrics for specific chain"),
) -> dict[str, Any]:
    """
    Reset metrics.

    Use with caution - this will clear collected metrics.

    Args:
        agent_name: Reset only this agent's metrics
        chain_name: Reset only this chain's metrics

    Returns:
        Confirmation of reset operation
    """
    collector = get_metrics_collector()

    if agent_name:
        collector.reset_agent_metrics(agent_name)
        return {
            "status": "reset",
            "target": f"agent:{agent_name}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    elif chain_name:
        collector.reset_chain_metrics(chain_name)
        return {
            "status": "reset",
            "target": f"chain:{chain_name}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    else:
        collector.reset_all_metrics()
        return {
            "status": "reset",
            "target": "all",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/save")
async def save_metrics() -> dict[str, Any]:
    """
    Persist metrics to disk.

    Manually trigger metrics persistence. Metrics are also
    automatically saved periodically.

    Returns:
        Confirmation of save operation
    """
    collector = get_metrics_collector()
    collector.save()

    return {
        "status": "saved",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
