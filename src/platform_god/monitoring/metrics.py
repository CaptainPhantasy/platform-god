"""
Metrics collection for Platform God.

Provides:
- Agent execution metrics
- Success/failure rate tracking
- Execution time aggregation
- Registry statistics
- Prometheus-style export
"""

import atexit
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class MetricType(str, Enum):
    """Types of metrics."""

    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


@dataclass
class AgentMetrics:
    """Metrics for a single agent."""

    agent_name: str
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_execution_time_ms: float = 0
    min_execution_time_ms: float | None = None
    max_execution_time_ms: float | None = None
    last_execution_at: str | None = None
    last_status: str | None = None
    average_execution_time_ms: float = 0

    def record_execution(
        self,
        execution_time_ms: float,
        success: bool,
        timestamp: str | None = None,
    ) -> None:
        """Record an agent execution."""
        self.execution_count += 1
        self.total_execution_time_ms += execution_time_ms
        self.average_execution_time_ms = self.total_execution_time_ms / self.execution_count

        if success:
            self.success_count += 1
            self.last_status = "success"
        else:
            self.failure_count += 1
            self.last_status = "failure"

        if self.min_execution_time_ms is None or execution_time_ms < self.min_execution_time_ms:
            self.min_execution_time_ms = execution_time_ms

        if self.max_execution_time_ms is None or execution_time_ms > self.max_execution_time_ms:
            self.max_execution_time_ms = execution_time_ms

        self.last_execution_at = timestamp or datetime.now(timezone.utc).isoformat()

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "agent_name": self.agent_name,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 2),
            "total_execution_time_ms": round(self.total_execution_time_ms, 2),
            "average_execution_time_ms": round(self.average_execution_time_ms, 2),
            "min_execution_time_ms": self.min_execution_time_ms,
            "max_execution_time_ms": self.max_execution_time_ms,
            "last_execution_at": self.last_execution_at,
            "last_status": self.last_status,
        }


@dataclass
class ChainMetrics:
    """Metrics for chain executions."""

    chain_name: str
    execution_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_execution_time_ms: float = 0
    average_execution_time_ms: float = 0
    last_execution_at: str | None = None
    last_status: str | None = None
    last_repository: str | None = None

    def record_execution(
        self,
        execution_time_ms: float,
        success: bool,
        repository: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """Record a chain execution."""
        self.execution_count += 1
        self.total_execution_time_ms += execution_time_ms
        self.average_execution_time_ms = self.total_execution_time_ms / self.execution_count

        if success:
            self.success_count += 1
            self.last_status = "completed"
        else:
            self.failure_count += 1
            self.last_status = "failed"

        self.last_execution_at = timestamp or datetime.now(timezone.utc).isoformat()
        self.last_repository = repository

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.execution_count == 0:
            return 0.0
        return (self.success_count / self.execution_count) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "chain_name": self.chain_name,
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": round(self.success_rate, 2),
            "total_execution_time_ms": round(self.total_execution_time_ms, 2),
            "average_execution_time_ms": round(self.average_execution_time_ms, 2),
            "last_execution_at": self.last_execution_at,
            "last_status": self.last_status,
            "last_repository": self.last_repository,
        }


@dataclass
class SystemMetrics:
    """System-level metrics."""

    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_agent_executions: int = 0
    total_chain_executions: int = 0
    total_errors: int = 0
    active_repositories: int = 0
    registry_entities: int = 0
    last_updated: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "start_time": self.start_time,
            "total_agent_executions": self.total_agent_executions,
            "total_chain_executions": self.total_chain_executions,
            "total_errors": self.total_errors,
            "active_repositories": self.active_repositories,
            "registry_entities": self.registry_entities,
            "last_updated": self.last_updated,
        }


class MetricsCollector:
    """
    Thread-safe metrics collector for Platform God.

    Collects and aggregates metrics from:
    - Agent executions
    - Chain runs
    - Registry operations
    - System statistics

    Metrics can be exported as JSON or Prometheus format.
    """

    def __init__(self, state_dir: Path | None = None):
        """Initialize metrics collector."""
        self._state_dir = state_dir or Path("var/state")
        self._metrics_file = self._state_dir / "metrics.json"

        # Thread-safe storage
        self._lock = threading.Lock()

        # Agent metrics: agent_name -> AgentMetrics
        self._agent_metrics: dict[str, AgentMetrics] = {}

        # Chain metrics: chain_name -> ChainMetrics
        self._chain_metrics: dict[str, ChainMetrics] = {}

        # System metrics
        self._system_metrics = SystemMetrics()

        # Load persisted metrics if available
        self._load()

        # Register atexit handler to auto-save metrics on shutdown
        atexit.register(self._atexit_handler)

    def _atexit_handler(self) -> None:
        """Save metrics on process shutdown (registered with atexit)."""
        try:
            self.save()
        except Exception as e:
            # Log but don't raise - atexit handlers should not raise exceptions
            logger.warning(f"Failed to save metrics during shutdown: {e}")

    def record_agent_execution(
        self,
        agent_name: str,
        execution_time_ms: float,
        success: bool,
        timestamp: str | None = None,
    ) -> None:
        """
        Record an agent execution.

        Args:
            agent_name: Name of the agent
            execution_time_ms: Execution time in milliseconds
            success: Whether execution succeeded
            timestamp: Execution timestamp (ISO format)
        """
        with self._lock:
            if agent_name not in self._agent_metrics:
                self._agent_metrics[agent_name] = AgentMetrics(agent_name=agent_name)

            self._agent_metrics[agent_name].record_execution(
                execution_time_ms=execution_time_ms,
                success=success,
                timestamp=timestamp,
            )

            self._system_metrics.total_agent_executions += 1
            if not success:
                self._system_metrics.total_errors += 1

            self._system_metrics.last_updated = datetime.now(timezone.utc).isoformat()

    def record_chain_execution(
        self,
        chain_name: str,
        execution_time_ms: float,
        success: bool,
        repository: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        """
        Record a chain execution.

        Args:
            chain_name: Name of the chain
            execution_time_ms: Execution time in milliseconds
            success: Whether execution succeeded
            repository: Repository path
            timestamp: Execution timestamp (ISO format)
        """
        with self._lock:
            if chain_name not in self._chain_metrics:
                self._chain_metrics[chain_name] = ChainMetrics(chain_name=chain_name)

            self._chain_metrics[chain_name].record_execution(
                execution_time_ms=execution_time_ms,
                success=success,
                repository=repository,
                timestamp=timestamp,
            )

            self._system_metrics.total_chain_executions += 1
            if not success:
                self._system_metrics.total_errors += 1

            self._system_metrics.last_updated = datetime.now(timezone.utc).isoformat()

    def get_agent_metrics(self, agent_name: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Get metrics for agents.

        Args:
            agent_name: Specific agent name, or None for all agents

        Returns:
            Metrics dict for single agent, or list of dicts for all agents
        """
        with self._lock:
            if agent_name:
                if agent_name in self._agent_metrics:
                    return self._agent_metrics[agent_name].to_dict()
                return {}

            return [m.to_dict() for m in self._agent_metrics.values()]

    def get_chain_metrics(self, chain_name: str | None = None) -> dict[str, Any] | list[dict[str, Any]]:
        """
        Get metrics for chains.

        Args:
            chain_name: Specific chain name, or None for all chains

        Returns:
            Metrics dict for single chain, or list of dicts for all chains
        """
        with self._lock:
            if chain_name:
                if chain_name in self._chain_metrics:
                    return self._chain_metrics[chain_name].to_dict()
                return {}

            return [m.to_dict() for m in self._chain_metrics.values()]

    def get_system_metrics(self) -> dict[str, Any]:
        """Get system-level metrics."""
        with self._lock:
            # Update dynamic values
            self._update_registry_stats()
            return self._system_metrics.to_dict()

    def get_all_metrics(self) -> dict[str, Any]:
        """Get all metrics as a single dictionary."""
        with self._lock:
            self._update_registry_stats()

            return {
                "system": self._system_metrics.to_dict(),
                "agents": self.get_agent_metrics(),
                "chains": self.get_chain_metrics(),
            }

    def to_prometheus(self) -> str:
        """
        Export metrics in Prometheus text format.

        Returns:
            Prometheus-formatted metrics string
        """
        with self._lock:
            lines = []

            # System metrics
            sys = self._system_metrics
            lines.append(f'# HELP platform_god_agent_executions_total Total agent executions')
            lines.append(f'# TYPE platform_god_agent_executions_total counter')
            lines.append(f'platform_god_agent_executions_total {sys.total_agent_executions}')

            lines.append(f'# HELP platform_god_chain_executions_total Total chain executions')
            lines.append(f'# TYPE platform_god_chain_executions_total counter')
            lines.append(f'platform_god_chain_executions_total {sys.total_chain_executions}')

            lines.append(f'# HELP platform_god_errors_total Total errors')
            lines.append(f'# TYPE platform_god_errors_total counter')
            lines.append(f'platform_god_errors_total {sys.total_errors}')

            lines.append(f'# HELP platform_god_active_repositories Number of active repositories')
            lines.append(f'# TYPE platform_god_active_repositories gauge')
            lines.append(f'platform_god_active_repositories {sys.active_repositories}')

            lines.append(f'# HELP platform_god_registry_entities Number of registry entities')
            lines.append(f'# TYPE platform_god_registry_entities gauge')
            lines.append(f'platform_god_registry_entities {sys.registry_entities}')

            # Agent metrics
            for agent_name, metrics in self._agent_metrics.items():
                # safe_name = agent_name.replace("-", "_").replace(".", "_")  # Reserved for Prometheus label compatibility
                lines.append(f'\n# Agent: {agent_name}')
                lines.append(f'platform_god_agent_executions{{agent="{agent_name}"}} {metrics.execution_count}')
                lines.append(f'platform_god_agent_successes{{agent="{agent_name}"}} {metrics.success_count}')
                lines.append(f'platform_god_agent_failures{{agent="{agent_name}"}} {metrics.failure_count}')
                lines.append(f'platform_god_agent_success_rate{{agent="{agent_name}"}} {metrics.success_rate:.2f}')
                lines.append(f'platform_god_agent_avg_duration_ms{{agent="{agent_name}"}} {metrics.average_execution_time_ms:.2f}')

            # Chain metrics
            for chain_name, metrics in self._chain_metrics.items():
                # safe_name = chain_name.replace("-", "_").replace(".", "_")  # Reserved for Prometheus label compatibility
                lines.append(f'\n# Chain: {chain_name}')
                lines.append(f'platform_god_chain_executions{{chain="{chain_name}"}} {metrics.execution_count}')
                lines.append(f'platform_god_chain_successes{{chain="{chain_name}"}} {metrics.success_count}')
                lines.append(f'platform_god_chain_failures{{chain="{chain_name}"}} {metrics.failure_count}')
                lines.append(f'platform_god_chain_success_rate{{chain="{chain_name}"}} {metrics.success_rate:.2f}')
                lines.append(f'platform_god_chain_avg_duration_ms{{chain="{chain_name}"}} {metrics.average_execution_time_ms:.2f}')

            return "\n".join(lines)

    def reset_agent_metrics(self, agent_name: str | None = None) -> None:
        """
        Reset agent metrics.

        Args:
            agent_name: Specific agent to reset, or None for all agents
        """
        with self._lock:
            if agent_name:
                if agent_name in self._agent_metrics:
                    self._agent_metrics[agent_name] = AgentMetrics(agent_name=agent_name)
            else:
                self._agent_metrics.clear()

    def reset_chain_metrics(self, chain_name: str | None = None) -> None:
        """
        Reset chain metrics.

        Args:
            chain_name: Specific chain to reset, or None for all chains
        """
        with self._lock:
            if chain_name:
                if chain_name in self._chain_metrics:
                    self._chain_metrics[chain_name] = ChainMetrics(chain_name=chain_name)
            else:
                self._chain_metrics.clear()

    def reset_all_metrics(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._agent_metrics.clear()
            self._chain_metrics.clear()
            self._system_metrics = SystemMetrics()

    def save(self) -> None:
        """Persist metrics to disk."""
        with self._lock:
            self._metrics_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "system": self._system_metrics.to_dict(),
                "agents": {
                    name: m.to_dict()
                    for name, m in self._agent_metrics.items()
                },
                "chains": {
                    name: m.to_dict()
                    for name, m in self._chain_metrics.items()
                },
            }

            self._metrics_file.write_text(json.dumps(data, indent=2))

    def _load(self) -> None:
        """Load metrics from disk if available."""
        if not self._metrics_file.exists():
            return

        try:
            data = json.loads(self._metrics_file.read_text())

            # Load system metrics
            if "system" in data:
                sys_data = data["system"]
                self._system_metrics = SystemMetrics(
                    start_time=sys_data.get("start_time", datetime.now(timezone.utc).isoformat()),
                    total_agent_executions=sys_data.get("total_agent_executions", 0),
                    total_chain_executions=sys_data.get("total_chain_executions", 0),
                    total_errors=sys_data.get("total_errors", 0),
                    active_repositories=sys_data.get("active_repositories", 0),
                    registry_entities=sys_data.get("registry_entities", 0),
                )

            # Load agent metrics
            if "agents" in data:
                for name, agent_data in data["agents"].items():
                    metrics = AgentMetrics(agent_name=name)
                    metrics.execution_count = agent_data.get("execution_count", 0)
                    metrics.success_count = agent_data.get("success_count", 0)
                    metrics.failure_count = agent_data.get("failure_count", 0)
                    metrics.total_execution_time_ms = agent_data.get("total_execution_time_ms", 0)
                    metrics.average_execution_time_ms = agent_data.get("average_execution_time_ms", 0)
                    metrics.min_execution_time_ms = agent_data.get("min_execution_time_ms")
                    metrics.max_execution_time_ms = agent_data.get("max_execution_time_ms")
                    metrics.last_execution_at = agent_data.get("last_execution_at")
                    metrics.last_status = agent_data.get("last_status")
                    self._agent_metrics[name] = metrics

            # Load chain metrics
            if "chains" in data:
                for name, chain_data in data["chains"].items():
                    metrics = ChainMetrics(chain_name=name)
                    metrics.execution_count = chain_data.get("execution_count", 0)
                    metrics.success_count = chain_data.get("success_count", 0)
                    metrics.failure_count = chain_data.get("failure_count", 0)
                    metrics.total_execution_time_ms = chain_data.get("total_execution_time_ms", 0)
                    metrics.average_execution_time_ms = chain_data.get("average_execution_time_ms", 0)
                    metrics.last_execution_at = chain_data.get("last_execution_at")
                    metrics.last_status = chain_data.get("last_status")
                    metrics.last_repository = chain_data.get("last_repository")
                    self._chain_metrics[name] = metrics

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to load metrics from disk: {e}")

    def _update_registry_stats(self) -> None:
        """Update registry statistics in system metrics."""
        try:
            from platform_god.registry.storage import Registry

            registry = Registry()
            # Count total entities
            total = sum(len(ids) for ids in registry.index.entities.values())
            self._system_metrics.registry_entities = total

        except Exception:
            pass

        # Update active repositories count from state manager
        try:
            from platform_god.state.manager import StateManager

            state_mgr = StateManager()
            self._system_metrics.active_repositories = len(state_mgr._index.get("repositories", []))

        except Exception:
            pass


# Global metrics collector instance
_global_collector: MetricsCollector | None = None
_collector_lock = threading.Lock()


def get_metrics_collector(state_dir: Path | None = None) -> MetricsCollector:
    """
    Get the global metrics collector instance.

    Args:
        state_dir: Optional state directory path

    Returns:
        MetricsCollector instance
    """
    global _global_collector

    if _global_collector is None:
        with _collector_lock:
            if _global_collector is None:
                _global_collector = MetricsCollector(state_dir=state_dir)

    return _global_collector


@lru_cache(maxsize=1)
def get_cached_metrics() -> dict[str, Any]:
    """
    Get cached metrics (refreshed on explicit call).

    Returns:
        All metrics as dictionary
    """
    collector = get_metrics_collector()
    return collector.get_all_metrics()


def clear_metrics_cache() -> None:
    """Clear the cached metrics."""
    get_cached_metrics.cache_clear()


def format_prometheus_metric(
    name: str,
    value: float | int,
    metric_type: MetricType = MetricType.GAUGE,
    help_text: str = "",
    labels: dict[str, str] | None = None,
) -> str:
    """
    Format a single metric in Prometheus format.

    Args:
        name: Metric name
        value: Metric value
        metric_type: Type of metric
        help_text: Help text for the metric
        labels: Optional label dict

    Returns:
        Prometheus-formatted metric string
    """
    lines = []

    if help_text:
        lines.append(f"# HELP {name} {help_text}")
    lines.append(f"# TYPE {name} {metric_type.value}")

    label_str = ""
    if labels:
        label_pairs = [f'{k}="{v}"' for k, v in labels.items()]
        label_str = "{" + ",".join(label_pairs) + "}"

    lines.append(f"{name}{label_str} {value}")

    return "\n".join(lines)
