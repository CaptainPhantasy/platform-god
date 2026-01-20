"""Tests for agent registry loading and management."""

from pathlib import Path

import pytest

from platform_god.agents.registry import (
    AgentDefinition,
    AgentRegistry,
    PermissionLevel,
    get_agent,
    get_global_registry,
)
from platform_god.core.models import AgentClass


class TestAgentRegistry:
    """Tests for AgentRegistry class."""

    def test_registry_loads_agents(self, agents_dir: Path) -> None:
        """Registry loads agents from the agents directory."""
        registry = AgentRegistry(agents_dir)
        agents = registry.list_all()
        # Should have at least the standard agents
        assert len(agents) > 0

    def test_registry_get_agent(self, agents_dir: Path) -> None:
        """Registry can retrieve specific agent by name."""
        registry = AgentRegistry(agents_dir)
        agent = registry.get("PG_DISCOVERY")
        assert agent is not None
        assert agent.name == "PG_DISCOVERY"

    def test_registry_get_nonexistent_agent(self, agents_dir: Path) -> None:
        """Registry returns None for non-existent agent."""
        registry = AgentRegistry(agents_dir)
        agent = registry.get("PG_NONEXISTENT")
        assert agent is None

    def test_registry_list_class(self, agents_dir: Path) -> None:
        """Registry can filter agents by class."""
        registry = AgentRegistry(agents_dir)
        read_only_agents = registry.list_class(AgentClass.READ_ONLY_SCAN)
        assert all(a.agent_class == AgentClass.READ_ONLY_SCAN for a in read_only_agents)

    def test_registry_names(self, agents_dir: Path) -> None:
        """Registry can return all agent names."""
        registry = AgentRegistry(agents_dir)
        names = registry.names()
        assert isinstance(names, list)
        assert "PG_DISCOVERY" in names

    def test_global_registry_cached(self) -> None:
        """Global registry is cached (same instance on repeated calls)."""
        r1 = get_global_registry()
        r2 = get_global_registry()
        assert r1 is r2

    def test_get_agent_global(self) -> None:
        """get_agent retrieves from global registry."""
        agent = get_agent("PG_DISCOVERY")
        assert agent is not None
        assert agent.name == "PG_DISCOVERY"


class TestAgentDefinition:
    """Tests for AgentDefinition dataclass."""

    def test_agent_definition_structure(self, agents_dir: Path) -> None:
        """AgentDefinition has expected structure."""
        registry = AgentRegistry(agents_dir)
        agent = registry.get("PG_DISCOVERY")

        assert agent is not None
        assert agent.name == "PG_DISCOVERY"
        assert agent.role  # Should have a role
        assert agent.goal  # Should have a goal
        assert agent.permissions in PermissionLevel

    def test_allows_write_to(self, agents_dir: Path) -> None:
        """allows_write_to correctly validates write permissions."""
        registry = AgentRegistry(agents_dir)

        # READ_ONLY_SCAN agent should not allow any writes
        discovery = registry.get("PG_DISCOVERY")
        assert discovery is not None
        assert discovery.allows_write_to("var/registry/test.json") is False
        assert discovery.allows_write_to("any/path") is False


class TestPermissionLevel:
    """Tests for PermissionLevel enum."""

    def test_all_levels_defined(self) -> None:
        """All expected permission levels are defined."""
        expected = {"read_only", "write_gated", "control_plane"}
        actual = {pl.value for pl in PermissionLevel}
        assert actual == expected
