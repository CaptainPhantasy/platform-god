"""
Agent Registry - catalogs all available agents and their metadata.

Agents are defined in prompts/agents/*.md and loaded at runtime.
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

from platform_god.core.exceptions import ValidationError
from platform_god.core.models import AgentClass


class PermissionLevel(Enum):
    """Permission levels for filesystem access."""

    READ_ONLY = "read_only"
    WRITE_GATED = "write_gated"
    CONTROL_PLANE = "control_plane"


@dataclass(frozen=True)
class AgentDefinition:
    """Metadata and contract definition for an agent."""

    name: str
    agent_class: AgentClass
    role: str
    goal: str
    permissions: PermissionLevel
    allowed_paths: tuple[str, ...] = ()
    disallowed_paths: tuple[str, ...] = ()
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    stop_conditions: tuple[str, ...] = ()
    source_file: str = ""
    content_hash: str = ""

    def allows_write_to(self, path: str) -> bool:
        """Check if this agent is allowed to write to a given path."""
        if self.permissions == PermissionLevel.READ_ONLY:
            return False

        # Check disallowed paths first
        for disallowed in self.disallowed_paths:
            if path.startswith(disallowed):
                return False

        # If no explicit allowed paths, deny
        if not self.allowed_paths:
            return False

        # Check allowed paths
        for allowed in self.allowed_paths:
            if path.startswith(allowed):
                return True

        return False


def _extract_section(content: str, section: str) -> str:
    """Extract a section from agent markdown content.

    The section name may have optional suffixes like (HARD), (MANDATORY), etc.
    e.g., "SCOPE / PERMISSIONS (HARD)" will match when looking for "SCOPE / PERMISSIONS".

    Returns empty string if section is not found or is empty.
    """
    pattern = rf"^{re.escape(section)}(?:\s*\(.*?\))?\s*\n+(.*?)(?=^[A-Z]{{3,}}|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def _extract_code_block(content: str) -> str:
    """Extract JSON schema from markdown code block."""
    match = re.search(r"```json\s*(\{.+?\})\s*```", content, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"```\s*(\{.+?\})\s*```", content, re.DOTALL)
    if match:
        return match.group(1)
    return "{}"


def _parse_agent_class(content: str) -> AgentClass:
    """Infer agent class from permissions section."""
    scope = _extract_section(content, "SCOPE / PERMISSIONS")

    if "write" not in scope.lower():
        return AgentClass.READ_ONLY_SCAN
    if "control" in scope.lower() or "orchestrat" in content.lower():
        return AgentClass.CONTROL_PLANE
    if "var/registry" in scope:
        return AgentClass.REGISTRY_STATE
    return AgentClass.WRITE_GATED


def _parse_allowed_paths(content: str) -> tuple[str, ...]:
    """Parse allowed write paths from permissions section."""
    scope = _extract_section(content, "SCOPE / PERMISSIONS")
    paths = []

    # Look for "Write to" patterns
    for match in re.finditer(r'(?:Write to|writes?\s+to)\s+([^\n]+)', scope, re.IGNORECASE):
        path_spec = match.group(1).strip()
        # Extract paths from patterns like 'var/registry/**' or 'prompts/agents/**'
        for path in re.finditer(r"([\w/]+/\*\*|[\w/]+/)", path_spec):
            p = path.group(1).replace("**", "")
            if p not in paths:
                paths.append(p)

    return tuple(paths)


def _parse_disallowed_paths(content: str) -> tuple[str, ...]:
    """Parse disallowed paths from permissions section."""
    scope = _extract_section(content, "SCOPE / PERMISSIONS")
    paths = []

    # Look for "Disallowed:" section
    disallowed_match = re.search(r"Disallowed:\s*\n(.+?)\n\n", scope, re.DOTALL)
    if disallowed_match:
        disallowed_text = disallowed_match.group(1)
        # Extract paths from patterns like "Any writes to src/, configs/"
        for match in re.finditer(r'(?:writes?\s+to|writes?)\s+([^\n]+)', disallowed_text, re.IGNORECASE):
            path_spec = match.group(1).strip()
            for part in path_spec.split(","):
                p = part.strip().strip('"\'').rstrip("/")
                if p and p not in paths:
                    paths.append(p)

    return tuple(paths)


def _parse_output_schema(content: str) -> dict:
    """Parse OUTPUT section JSON schema."""
    output_section = _extract_section(content, "OUTPUT")
    json_match = re.search(r"\{[\s\S]+?\}", output_section)
    if json_match:
        try:
            import json

            return json.loads(json_match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


def _parse_stop_conditions(content: str) -> tuple[str, ...]:
    """Parse STOP_CONDITIONS from agent definition."""
    stop_section = _extract_section(content, "STOP CONDITIONS")
    conditions = []

    for line in stop_section.split("\n"):
        line = line.lstrip("-*").strip()
        if line and not line.startswith("STOP"):
            conditions.append(line)

    return tuple(conditions)


# Required sections that must be present and non-empty in agent prompts
_REQUIRED_SECTIONS = ("ROLE", "GOAL", "SCOPE / PERMISSIONS")


def _validate_agent_sections(content: str, path: Path) -> None:
    """Validate that all required sections exist and are non-empty.

    Args:
        content: The agent prompt file content
        path: Path to the agent file (for error reporting)

    Raises:
        ValidationError: If any required section is missing or empty
    """
    missing_sections = []
    empty_sections = []

    for section in _REQUIRED_SECTIONS:
        section_content = _extract_section(content, section)
        if not section_content:
            # Check if the section header exists at all
            section_pattern = rf"^{section}\s*\n"
            if re.search(section_pattern, content, re.MULTILINE):
                # Section exists but is empty
                empty_sections.append(section)
            else:
                # Section doesn't exist at all
                missing_sections.append(section)

    errors = []
    if missing_sections:
        errors.append(f"Missing required sections: {', '.join(missing_sections)}")
    if empty_sections:
        errors.append(f"Empty required sections: {', '.join(empty_sections)}")

    if errors:
        raise ValidationError(
            f"Agent prompt validation failed for {path.name}",
            field="agent_prompt_sections",
            validation_errors=errors,
            details={"file": str(path), "required_sections": list(_REQUIRED_SECTIONS)},
        )


def load_agent_from_file(path: Path) -> AgentDefinition | None:
    """Load an agent definition from a markdown file."""
    content = path.read_text()
    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]

    # Validate required sections exist and are non-empty
    _validate_agent_sections(content, path)

    # Extract name from filename
    name = path.stem.removesuffix("_AGENT")

    # Parse sections
    role = _extract_section(content, "ROLE")
    goal = _extract_section(content, "GOAL")
    agent_class = _parse_agent_class(content)

    # Determine permission level
    permissions = PermissionLevel.READ_ONLY
    scope = _extract_section(content, "SCOPE / PERMISSIONS")
    if "write" in scope.lower():
        if "var/registry" in scope:
            permissions = PermissionLevel.WRITE_GATED
        else:
            permissions = PermissionLevel.WRITE_GATED

    allowed_paths = _parse_allowed_paths(content)
    disallowed_paths = _parse_disallowed_paths(content)
    output_schema = _parse_output_schema(content)
    stop_conditions = _parse_stop_conditions(content)

    return AgentDefinition(
        name=name,
        agent_class=agent_class,
        role=role,
        goal=goal,
        permissions=permissions,
        allowed_paths=allowed_paths,
        disallowed_paths=disallowed_paths,
        output_schema=output_schema,
        stop_conditions=stop_conditions,
        source_file=str(path),
        content_hash=content_hash,
    )


class AgentRegistry:
    """Registry of all available agents."""

    def __init__(self, agents_dir: Path | None = None):
        """Initialize registry by scanning agents directory."""
        self._agents_dir = agents_dir or self._find_agents_dir()
        self._agents: dict[str, AgentDefinition] = {}
        self._by_class: dict[AgentClass, list[str]] = {
            cls: [] for cls in AgentClass
        }
        self._load()

    @staticmethod
    def _find_agents_dir() -> Path:
        """Find the agents directory relative to this file."""
        # Go up from src/platform_god/agents/ to project root
        here = Path(__file__).parent
        root = here.parent.parent.parent
        return root / "prompts" / "agents"

    def _load(self) -> None:
        """Load all agent definitions from disk."""
        if not self._agents_dir.exists():
            return

        for md_file in self._agents_dir.glob("*.md"):
            agent = load_agent_from_file(md_file)
            if agent:
                self._agents[agent.name] = agent
                self._by_class[agent.agent_class].append(agent.name)

    def get(self, name: str) -> AgentDefinition | None:
        """Get an agent by name."""
        return self._agents.get(name)

    def list_class(self, agent_class: AgentClass) -> list[AgentDefinition]:
        """List all agents of a given class."""
        return [
            self._agents[name]
            for name in self._by_class.get(agent_class, [])
        ]

    def list_all(self) -> list[AgentDefinition]:
        """List all registered agents."""
        return list(self._agents.values())

    def names(self) -> list[str]:
        """Return all agent names."""
        return list(self._agents.keys())


@lru_cache(maxsize=1)
def get_global_registry() -> AgentRegistry:
    """Get the global agent registry (cached)."""
    return AgentRegistry()


def get_agent(name: str) -> AgentDefinition | None:
    """Get an agent by name from the global registry."""
    return get_global_registry().get(name)
