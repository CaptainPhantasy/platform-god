"""
Health check functions for Platform God components.

Provides comprehensive health monitoring for:
- SQLite/registry storage
- Disk space availability
- LLM API connectivity (optional)
- Registry integrity validation

WARNING: LLM Health Check and API Quota
----------------------------------------
The `check_llm_connection` function makes REAL API calls to LLM providers.
These calls count against your API quota and may incur costs.

Rate Limiting:
- Results are cached for 5 minutes to avoid draining quota
- Default health checks DO NOT include LLM (include_llm=False)
- For Kubernetes liveness/readiness probes, NEVER enable include_llm

Recommendations:
- Only enable LLM checks for manual diagnostics or infrequent monitoring
- Use longer cache TTLs (5+ minutes) when calling check_llm_connection
- Consider separate monitoring for LLM connectivity vs. general health
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# LLM health check cache TTL in seconds (5 minutes)
# This prevents excessive API calls that drain quota
_LLM_CACHE_TTL = 300
_llm_last_check_time: float = 0
_llm_cached_result: HealthCheckResult | None = None
_llm_cache_lock = threading.Lock()


class HealthStatus(str, Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
        }


def check_database(db_path: Path | None = None, timeout: float = 5.0) -> HealthCheckResult:
    """
    Check SQLite database connectivity and integrity.

    Args:
        db_path: Path to SQLite database (defaults to var/state/index.json for registry check)
        timeout: Connection timeout in seconds

    Returns:
        HealthCheckResult with database status
    """
    import time

    start_time = time.time()
    db_path = db_path or Path("var/state/index.json")

    try:
        # Check if state directory exists and is accessible
        state_dir = Path("var/state")
        if not state_dir.exists():
            state_dir.mkdir(parents=True, exist_ok=True)

        # Verify directory is writable
        test_file = state_dir / ".health_check_test"
        test_file.touch()
        test_file.unlink()

        duration_ms = (time.time() - start_time) * 1000

        # Check state index file
        index_file = state_dir / "index.json"
        index_exists = index_file.exists()
        index_readable = False
        if index_exists:
            try:
                _ = index_file.read_text()
                index_readable = True
            except Exception:
                pass

        return HealthCheckResult(
            name="database",
            status=HealthStatus.HEALTHY,
            message="State storage is accessible",
            details={
                "path": str(state_dir.absolute()),
                "writable": True,
                "index_exists": index_exists,
                "index_readable": index_readable,
            },
            duration_ms=duration_ms,
        )

    except PermissionError as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"Permission denied accessing state storage",
            details={"error": str(e), "path": str(db_path)},
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="database",
            status=HealthStatus.UNHEALTHY,
            message=f"State storage check failed: {e}",
            details={"error": str(e), "path": str(db_path)},
            duration_ms=duration_ms,
        )


def check_registry(registry_dir: Path | None = None) -> HealthCheckResult:
    """
    Check registry storage integrity.

    Verifies:
    - Registry directory exists and is accessible
    - Index file can be loaded
    - Entity checksums are valid (sample check)

    Args:
        registry_dir: Path to registry directory (defaults to var/registry/)

    Returns:
        HealthCheckResult with registry status
    """
    import time

    start_time = time.time()
    registry_dir = registry_dir or Path("var/registry")

    try:
        from platform_god.registry.storage import Registry

        registry = Registry(registry_dir=registry_dir)

        # Access index to verify it loads
        index = registry.index

        # Count entities by type
        entity_counts = {
            entity_type: len(entity_ids)
            for entity_type, entity_ids in index.entities.items()
        }
        total_entities = sum(entity_counts.values())

        # Sample integrity check - verify up to 5 entities
        verified = 0
        failed = 0
        checked = 0

        for entity_type, entity_ids in index.entities.items():
            for entity_id in entity_ids[:5]:  # Check first 5 per type
                checked += 1
                if registry.verify_integrity(entity_type, entity_id):
                    verified += 1
                else:
                    failed += 1

            if checked >= 20:  # Limit total checks
                break

        duration_ms = (time.time() - start_time) * 1000

        status = HealthStatus.HEALTHY
        message = f"Registry is healthy ({total_entities} entities)"

        if failed > 0:
            status = HealthStatus.DEGRADED
            message = f"Registry has {failed} corrupted entities out of {checked} checked"
        elif not list(index.entities.keys()):
            status = HealthStatus.HEALTHY
            message = "Registry is empty (no entities)"

        return HealthCheckResult(
            name="registry",
            status=status,
            message=message,
            details={
                "path": str(registry_dir.absolute()),
                "entity_counts": entity_counts,
                "total_entities": total_entities,
                "integrity_checked": checked,
                "integrity_verified": verified,
                "integrity_failed": failed,
                "index_version": index.version,
                "last_updated": index.last_updated,
            },
            duration_ms=duration_ms,
        )

    except ImportError as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="registry",
            status=HealthStatus.UNHEALTHY,
            message="Registry module not available",
            details={"error": str(e)},
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="registry",
            status=HealthStatus.UNHEALTHY,
            message=f"Registry check failed: {e}",
            details={"error": str(e), "path": str(registry_dir)},
            duration_ms=duration_ms,
        )


def check_disk_space(
    path: Path | None = None,
    warning_threshold_gb: float = 10.0,
    critical_threshold_gb: float = 5.0,
) -> HealthCheckResult:
    """
    Check available disk space.

    Args:
        path: Path to check disk space for (defaults to current working directory)
        warning_threshold_gb: Warning threshold in GB
        critical_threshold_gb: Critical threshold in GB

    Returns:
        HealthCheckResult with disk space status
    """
    import time

    start_time = time.time()
    path = path or Path.cwd()

    try:
        import shutil

        usage = shutil.disk_usage(path)

        total_gb = usage.total / (1024**3)
        used_gb = usage.used / (1024**3)
        free_gb = usage.free / (1024**3)
        used_percent = (used_gb / total_gb) * 100

        duration_ms = (time.time() - start_time) * 1000

        status = HealthStatus.HEALTHY
        message = f"Disk space OK ({free_gb:.1f} GB free)"

        if free_gb < critical_threshold_gb:
            status = HealthStatus.UNHEALTHY
            message = f"Critical: Only {free_gb:.1f} GB free (threshold: {critical_threshold_gb} GB)"
        elif free_gb < warning_threshold_gb:
            status = HealthStatus.DEGRADED
            message = f"Warning: Only {free_gb:.1f} GB free (threshold: {warning_threshold_gb} GB)"

        return HealthCheckResult(
            name="disk_space",
            status=status,
            message=message,
            details={
                "path": str(path.absolute()),
                "total_gb": round(total_gb, 2),
                "used_gb": round(used_gb, 2),
                "free_gb": round(free_gb, 2),
                "used_percent": round(used_percent, 2),
                "warning_threshold_gb": warning_threshold_gb,
                "critical_threshold_gb": critical_threshold_gb,
            },
            duration_ms=duration_ms,
        )

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="disk_space",
            status=HealthStatus.UNKNOWN,
            message=f"Could not determine disk space: {e}",
            details={"error": str(e), "path": str(path)},
            duration_ms=duration_ms,
        )


def check_llm_connection(
    api_key: str | None = None,
    provider: str | None = None,
    timeout: float = 5.0,
    force_refresh: bool = False,
) -> HealthCheckResult:
    """
    Check LLM API reachability (optional check).

    .. warning::
        **QUOTA IMPACT**: This function makes REAL API calls to LLM providers.
        Each call consumes API quota and may incur costs. Results are cached
        for 5 minutes to prevent excessive consumption.

    This check is optional and returns DEGRADED if not configured
    rather than UNHEALTHY, since LLM connectivity is not required
    for basic Platform God operation.

    Rate Limiting:
        - Results are cached for 5 minutes by default
        - Use force_refresh=True to bypass the cache
        - A warning is logged when an actual API call is made

    Args:
        api_key: API key to use (defaults to environment variables)
        provider: LLM provider to check (anthropic, openai, etc.)
        timeout: Request timeout in seconds
        force_refresh: Bypass cache and force a new API call

    Returns:
        HealthCheckResult with LLM connectivity status

    Example:
        DO NOT use this in Kubernetes liveness/readiness probes::

            # BAD: Will drain API quota
            while True:
                check_llm_connection()  # Called every check

        GOOD: Use for manual diagnostics only::

            # Only when debugging LLM issues
            result = check_llm_connection()
    """
    global _llm_last_check_time, _llm_cached_result

    import os

    start_time = time.time()
    current_time = time.time()

    # Check cache first (unless force_refresh is True)
    if not force_refresh:
        with _llm_cache_lock:
            if _llm_cached_result is not None:
                cache_age = current_time - _llm_last_check_time
                if cache_age < _LLM_CACHE_TTL:
                    logger.debug(
                        f"LLM health check: using cached result "
                        f"(age: {cache_age:.1f}s, TTL: {_LLM_CACHE_TTL}s)"
                    )
                    return _llm_cached_result

    # Log a warning that we're making a real API call
    logger.warning(
        "LLM health check: Making REAL API call to %s - this consumes API quota. "
        "Result will be cached for %d seconds.",
        provider or os.getenv("PG_LLM_PROVIDER", "anthropic"),
        _LLM_CACHE_TTL,
    )

    # Check if API key is configured
    provider = provider or os.getenv("PG_LLM_PROVIDER", "anthropic").lower()

    env_key = None
    if provider == "anthropic":
        env_key = "ANTHROPIC_API_KEY"
    elif provider in ("openai", "azure_openai"):
        env_key = "OPENAI_API_KEY"
    else:
        env_key = "PG_LLM_API_KEY"

    api_key = api_key or os.getenv(env_key, "")

    if not api_key:
        duration_ms = (time.time() - start_time) * 1000
        result = HealthCheckResult(
            name="llm_connection",
            status=HealthStatus.DEGRADED,
            message=f"LLM API key not configured (set {env_key})",
            details={
                "provider": provider,
                "configured": False,
                "env_var": env_key,
            },
            duration_ms=duration_ms,
        )
        # Cache the result even when API key is not configured
        with _llm_cache_lock:
            _llm_cached_result = result
            _llm_last_check_time = current_time
        return result

    # Perform actual API check
    result = _perform_llm_api_check(provider, api_key, timeout, start_time)

    # Cache the result
    with _llm_cache_lock:
        _llm_cached_result = result
        _llm_last_check_time = current_time

    return result


def _perform_llm_api_check(
    provider: str,
    api_key: str,
    timeout: float,
    start_time: float,
) -> HealthCheckResult:
    """
    Perform the actual LLM API connectivity check.

    This is separated from check_llm_connection to allow caching
    of the result without duplicating the API call logic.

    Args:
        provider: LLM provider name
        api_key: API key to use
        timeout: Request timeout in seconds
        start_time: Check start time for duration calculation

    Returns:
        HealthCheckResult with LLM connectivity status
    """
    import os

    try:
        # Try a minimal API call
        with httpx.Client(timeout=timeout) as client:
            if provider == "anthropic":
                # Check Anthropic API
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                }
                # Use a minimal request to check connectivity
                response = client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json={
                        "model": "claude-3-5-haiku-20241022",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )

                if response.status_code in (200, 400):  # 400 might be auth, but API is reachable
                    duration_ms = (time.time() - start_time) * 1000
                    return HealthCheckResult(
                        name="llm_connection",
                        status=HealthStatus.HEALTHY,
                        message="LLM API is reachable",
                        details={
                            "provider": provider,
                            "configured": True,
                            "status_code": response.status_code,
                        },
                        duration_ms=duration_ms,
                    )
                else:
                    duration_ms = (time.time() - start_time) * 1000
                    return HealthCheckResult(
                        name="llm_connection",
                        status=HealthStatus.UNHEALTHY,
                        message=f"LLM API returned error: {response.status_code}",
                        details={
                            "provider": provider,
                            "configured": True,
                            "status_code": response.status_code,
                        },
                        duration_ms=duration_ms,
                    )

            elif provider in ("openai", "azure_openai"):
                # Check OpenAI API
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "content-type": "application/json",
                }
                base_url = os.getenv("PG_LLM_BASE_URL", "https://api.openai.com/v1")

                response = client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json={
                        "model": "gpt-3.5-turbo",
                        "max_tokens": 1,
                        "messages": [{"role": "user", "content": "ping"}],
                    },
                )

                if response.status_code in (200, 400, 401):  # API reachable, even if auth fails
                    duration_ms = (time.time() - start_time) * 1000
                    return HealthCheckResult(
                        name="llm_connection",
                        status=HealthStatus.HEALTHY,
                        message="LLM API is reachable",
                        details={
                            "provider": provider,
                            "configured": True,
                            "status_code": response.status_code,
                        },
                        duration_ms=duration_ms,
                    )
                else:
                    duration_ms = (time.time() - start_time) * 1000
                    return HealthCheckResult(
                        name="llm_connection",
                        status=HealthStatus.UNHEALTHY,
                        message=f"LLM API returned error: {response.status_code}",
                        details={
                            "provider": provider,
                            "configured": True,
                            "status_code": response.status_code,
                        },
                        duration_ms=duration_ms,
                    )
            else:
                # Unsupported provider - return degraded
                duration_ms = (time.time() - start_time) * 1000
                return HealthCheckResult(
                    name="llm_connection",
                    status=HealthStatus.DEGRADED,
                    message=f"Unsupported LLM provider: {provider}",
                    details={
                        "provider": provider,
                        "configured": True,
                        "supported_providers": ["anthropic", "openai", "azure_openai"],
                    },
                    duration_ms=duration_ms,
                )

    except httpx.TimeoutException:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="llm_connection",
            status=HealthStatus.UNHEALTHY,
            message="LLM API request timed out",
            details={"provider": provider, "configured": True, "error": "timeout"},
            duration_ms=duration_ms,
        )
    except httpx.HTTPError as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="llm_connection",
            status=HealthStatus.UNHEALTHY,
            message=f"LLM API connection failed: {e}",
            details={"provider": provider, "configured": True, "error": str(e)},
            duration_ms=duration_ms,
        )
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return HealthCheckResult(
            name="llm_connection",
            status=HealthStatus.UNKNOWN,
            message=f"LLM check failed: {e}",
            details={"provider": provider, "configured": True, "error": str(e)},
            duration_ms=duration_ms,
        )


def run_all_health_checks(
    include_llm: bool = False,
    registry_dir: Path | None = None,
    db_path: Path | None = None,
    force_llm_refresh: bool = False,
) -> dict[str, HealthCheckResult]:
    """
    Run all health checks and return results.

    .. warning::
        Setting include_llm=True will make REAL API calls to LLM providers.
        These calls consume API quota and may incur costs. Only enable for
        manual diagnostics - NEVER use in Kubernetes liveness/readiness probes.

    Args:
        include_llm: Whether to include LLM connectivity check (default: False)
        registry_dir: Path to registry directory
        db_path: Path to database/state directory
        force_llm_refresh: Force a fresh LLM check, bypassing cache

    Returns:
        Dictionary mapping check names to results
    """
    results = {}

    # Always run these core checks
    results["database"] = check_database(db_path)
    results["registry"] = check_registry(registry_dir)
    results["disk_space"] = check_disk_space()

    # Optional checks
    if include_llm:
        results["llm_connection"] = check_llm_connection(force_refresh=force_llm_refresh)

    return results


def get_overall_health(results: dict[str, HealthCheckResult]) -> HealthStatus:
    """
    Determine overall health status from individual check results.

    Args:
        results: Dictionary of health check results

    Returns:
        Overall HealthStatus
    """
    if not results:
        return HealthStatus.UNKNOWN

    has_unhealthy = any(r.status == HealthStatus.UNHEALTHY for r in results.values())
    has_degraded = any(r.status == HealthStatus.DEGRADED for r in results.values())

    if has_unhealthy:
        return HealthStatus.UNHEALTHY
    if has_degraded:
        return HealthStatus.DEGRADED
    return HealthStatus.HEALTHY


@lru_cache(maxsize=1)
def get_cached_health_results() -> dict[str, HealthCheckResult]:
    """
    Get cached health results (refreshed on process restart).

    This is useful for API endpoints that need fast responses
    and can tolerate slightly stale data.

    Returns:
        Cached health check results
    """
    return run_all_health_checks(include_llm=False)


def clear_health_cache() -> None:
    """Clear the cached health results."""
    get_cached_health_results.cache_clear()


def clear_llm_cache() -> None:
    """
    Clear the LLM health check cache.

    This forces the next call to check_llm_connection() to make
    a fresh API call. Use sparingly to avoid consuming quota.
    """
    global _llm_last_check_time, _llm_cached_result
    with _llm_cache_lock:
        _llm_last_check_time = 0
        _llm_cached_result = None
    logger.debug("LLM health check cache cleared")


class HealthCheckRunner:
    """
    Thread-safe health check runner with caching.

    Provides:
    - Cached results with TTL
    - Thread-safe access
    - Async support
    """

    def __init__(self, cache_ttl_seconds: float = 30.0):
        """Initialize health check runner."""
        self._cache_ttl = cache_ttl_seconds
        self._last_check: float = 0
        self._cached_results: dict[str, HealthCheckResult] | None = None
        self._lock = threading.Lock()

    def run(
        self,
        force_refresh: bool = False,
        include_llm: bool = False,
        force_llm_refresh: bool = False,
    ) -> dict[str, HealthCheckResult]:
        """
        Run health checks, using cache if within TTL.

        Args:
            force_refresh: Force a fresh check regardless of cache
            include_llm: Include LLM connectivity check (WARNING: consumes API quota)
            force_llm_refresh: Force fresh LLM check, bypassing LLM cache

        Returns:
            Dictionary of health check results
        """
        import time

        if include_llm:
            logger.warning(
                "Health check with LLM enabled - this will make API calls and consume quota. "
                "Consider disabling include_llm for frequent health checks."
            )

        with self._lock:
            current_time = time.time()
            should_refresh = force_refresh or (
                self._cached_results is None
                or (current_time - self._last_check) > self._cache_ttl
            )

            if should_refresh:
                self._cached_results = run_all_health_checks(
                    include_llm=include_llm,
                    force_llm_refresh=force_llm_refresh,
                )
                self._last_check = current_time

            return self._cached_results.copy() if self._cached_results else {}

    async def run_async(
        self,
        force_refresh: bool = False,
        include_llm: bool = False,
        force_llm_refresh: bool = False,
    ) -> dict[str, HealthCheckResult]:
        """
        Async version of run health checks.

        Args:
            force_refresh: Force a fresh check regardless of cache
            include_llm: Include LLM connectivity check (WARNING: consumes API quota)
            force_llm_refresh: Force fresh LLM check, bypassing LLM cache

        Returns:
            Dictionary of health check results
        """
        # Run blocking checks in thread pool
        import asyncio

        return await asyncio.to_thread(
            self.run,
            force_refresh=force_refresh,
            include_llm=include_llm,
            force_llm_refresh=force_llm_refresh,
        )


# Global health check runner instance
_global_runner: HealthCheckRunner | None = None
_runner_lock = threading.Lock()


def get_health_runner() -> HealthCheckRunner:
    """Get the global health check runner instance."""
    global _global_runner

    if _global_runner is None:
        with _runner_lock:
            if _global_runner is None:
                _global_runner = HealthCheckRunner()

    return _global_runner
