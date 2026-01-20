"""
API route handlers.

This package contains all route definitions for the Platform God API.
"""

from platform_god.api.routes import agents, auth, chains, health, metrics, registry, runs

__all__ = [
    "agents",
    "auth",
    "chains",
    "health",
    "metrics",
    "registry",
    "runs",
]
