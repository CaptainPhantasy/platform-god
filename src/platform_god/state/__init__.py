"""
Platform God State Module.

Provides cross-run state persistence for chain results and repository state.
"""

__all__ = ["StateManager", "ChainRun", "RepositoryState", "AgentExecution"]

from platform_god.state.manager import AgentExecution, ChainRun, RepositoryState, StateManager
