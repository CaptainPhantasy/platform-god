"""
Platform God Orchestrator Module.

Provides multi-agent coordination and execution chains.
"""

__all__ = ["Orchestrator", "ChainDefinition", "ChainResult"]

from platform_god.orchestrator.core import (
    ChainDefinition,
    ChainResult,
    Orchestrator,
)
