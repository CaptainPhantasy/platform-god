# PLATFORM GOD - Agent Reference

## Agent Classes and Permissions

### AgentClass Enum

```python
class AgentClass(Enum):
    READ_ONLY_SCAN = "READ_ONLY_SCAN"        # Repository scanning only
    PLANNING_SYNTHESIS = "PLANNING_SYNTHESIS"  # Analysis and planning
    REGISTRY_STATE = "REGISTRY_STATE"        # Registry operations
    WRITE_GATED = "WRITE_GATED"              # Artifact generation
    CONTROL_PLANE = "CONTROL_PLANE"          # System operations
```

### Permission Levels

```python
class PermissionLevel(Enum):
    READ_ONLY = "read_only"      # No write access
    WRITE_GATED = "write_gated"  # Controlled write access
    CONTROL_PLANE = "control_plane"  # Full system access
```

## Agent Lifecycle

### 1. Registration

Agents are auto-discovered from `prompts/agents/*.md` at runtime:

```python
# agents/registry.py
class AgentRegistry:
    def _load(self) -> None:
        for md_file in self._agents_dir.glob("*.md"):
            agent = load_agent_from_file(md_file)
            if agent:
                self._agents[agent.name] = agent
```

### 2. Execution Flow

```
┌─────────────────────────────────────────────────────────────┐
│  1. Chain requests agent execution                          │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  2. ExecutionHarness.run_prechecks()                        │
│     - Agent exists in registry                              │
│     - Repository root is accessible                         │
│     - Required inputs present                               │
│     - Permission boundaries satisfied                       │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  3. Load agent prompt from prompts/agents/{NAME}_AGENT.md   │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  4. Format prompt with input data                           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  5. Call LLM API (if LIVE mode)                             │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  6. Validate output against schema                           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│  7. Write audit log to var/audit/                           │
└─────────────────────────────────────────────────────────────┘
```

### 3. Result States

```python
class AgentStatus(Enum):
    PENDING = "pending"        # Not yet started
    RUNNING = "running"        # Currently executing
    COMPLETED = "completed"    # Finished successfully
    FAILED = "failed"          # Execution failed
    STOPPED = "stopped"        # Precheck failed
```

## Prompt Contract Format

Every agent prompt file (`prompts/agents/{NAME}_AGENT.md`) follows this structure:

```
# AUTO-GENERATED: OVERWRITE OK
```text
You are PG_{NAME}_AGENT.

ROLE
{What the agent does}

GOAL
{The specific objective}

NON-GOALS (EXPLICIT)
{Explicit exclusions - what NOT to do}

SCOPE / PERMISSIONS (HARD)
Allowed:
{Allowed operations}
Disallowed:
{Disallowed operations}

OPERATING RULES (MANDATORY)
{Rules that must be obeyed}

INPUT
{Required input schema}

PRECHECKS (MUST PASS BEFORE DOING ANY WORK)
{Validation before execution}

TASKS (EXECUTE IN ORDER — NO REORDERING)
{Ordered list of tasks}

VALIDATION (MUST PASS AT THE END)
{Output verification}

OUTPUT (STRICT — NO EXTRA TEXT)
{JSON schema}

FAILURE HANDLING
{Failure behavior}

STOP CONDITIONS (HARD)
{Conditions that halt execution}
```
```

## Rules Agents Must Obey

### 1. Deterministic Execution

- No discretion or strategy changes
- Execute tasks in specified order only
- No assumptions beyond provided input

### 2. Permission Boundaries

| Class | Write Paths | Disallowed Paths |
|-------|-------------|------------------|
| READ_ONLY_SCAN | None | All writes |
| PLANNING_SYNTHESIS | None | All writes |
| REGISTRY_STATE | var/registry/, var/audit/ | None |
| WRITE_GATED | prompts/, var/artifacts/, var/cache/ | src/, configs/, docs/, tests/, scripts/, assets/ |
| CONTROL_PLANE | var/, prompts/ | None |

### 3. Output Format

All agents MUST return valid JSON matching the OUTPUT schema:
- No extra text outside JSON
- No markdown formatting unless specified
- ISO8601 timestamps for date fields
- Boolean values as true/false, not strings

### 4. Failure Handling

On any failure:
- STOP immediately
- Return failure output with error details
- Do not attempt recovery

### 5. No Network Access

Unless explicitly permitted:
- No HTTP requests
- No external API calls
- No package downloads

LLM API calls are made by the ExecutionHarness, not by agents.

## Registered Agents (34 Total)

### Discovery & Analysis Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_DISCOVERY | READ_ONLY_SCAN | Scans and catalogs repository files and directories |
| PG_STACKMAP | READ_ONLY_SCAN | Maps technology stack from file analysis |
| PG_HEALTH_SCORE | READ_ONLY_SCAN | Assesses repository health metrics |
| PG_FINGERPRINT | READ_ONLY_SCAN | Creates file fingerprints for change detection |

### Security & Risk Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_SECRETS_AND_RISK | READ_ONLY_SCAN | Scans for secrets, credentials, and security risks |
| PG_GUARDRAILS_AGENT | PLANNING_SYNTHESIS | Validates compliance with policy guardrails |
| PG_AUDIT_INDEX_AGENT | READ_ONLY_SCAN | Creates compliance audit index |

### Dependency Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_DEPENDENCY | READ_ONLY_SCAN | Analyzes project dependencies |
| PG_DEPENDENCY_MANAGER | WRITE_GATED | Manages dependency updates |

### Documentation Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_DOC_AUDIT | READ_ONLY_SCAN | Audits documentation coverage and quality |
| PG_DOC_MANAGER | WRITE_GATED | Generates and updates documentation |
| PG_REPORT_WRITER | WRITE_GATED | Creates analysis reports |
| PG_FAQ | WRITE_GATED | Generates FAQ content |
| PG_USER_STORY | WRITE_GATED | Creates user stories from requirements |

### Planning & Refactoring Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_REFACTOR_PLANNER | PLANNING_SYNTHESIS | Plans code refactoring approaches |
| PG_CONSOLIDATION_PLANNER | PLANNING_SYNTHESIS | Plans resource consolidation |
| PG_ENGINEERING_PRINCIPLES | READ_ONLY_SCAN | Extracts engineering principles from codebase |
| PG_NEXT_STEPS | PLANNING_SYNTHESIS | Generates action recommendations |

### Governance Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_WRITE_GATE | CONTROL_PLANE | Validates write operations before execution |
| PG_REGISTRY | REGISTRY_STATE | Manages registry operations |
| PG_ROLLBACK | REGISTRY_STATE | Handles rollback of changes |
| PG_GUARDRAILS | CONTROL_PLANE | Enforces policy compliance |
| PG_VERIFY | PLANNING_SYNTHESIS | Verifies work completion against criteria |

### Automation Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_AUTOMATION | WRITE_GATED | Plans automation workflows |
| PG_ASSET_COLLECTOR | WRITE_GATED | Collects and catalogs assets |

### Specialized Agents

| Agent | Class | Description |
|-------|-------|-------------|
| PG_DASHBOARD | WRITE_GATED | Creates dashboard configurations |
| PG_RELEASE_READINESS | READ_ONLY_SCAN | Assesses release readiness |
| PG_ROADMAP_GENERATOR | WRITE_GATED | Generates project roadmaps |
| PG_GIT_INIT | CONTROL_PLANE | Initializes git repositories |
| PG_REPO_SCAFFOLD | WRITE_GATED | Scaffolds new repository structure |
| PG_RESOURCE_CALCULATOR | READ_ONLY_SCAN | Calculates resource requirements |
| PG_DEDUP | PLANNING_SYNTHESIS | Deduplicates findings and artifacts |
| PG_AUDIT_LOG | REGISTRY_STATE | Reads audit logs |
| PG_AD_COPY | WRITE_GATED | Generates marketing copy |
| PG_CUSTOMER_RESEARCH | READ_ONLY_SCAN | Analyzes customer research data |

## Agent Input Schema

Standard input fields:

```json
{
  "repository_root": "/absolute/path/to/repo",
  "...": "additional fields vary by agent"
}
```

## Agent Output Schema

All agents return:

```json
{
  "status": "success|failure",
  "timestamp": "2024-01-01T00:00:00Z",
  "...": "additional fields vary by agent"
}
```

## Querying Agents

### Via CLI

```bash
# List all agents
pgod agents

# Filter by class
pgod agents --class READ_ONLY_SCAN

# Show detailed permissions
pgod agents --verbose
```

### Via Python API

```python
from platform_god.agents.registry import get_global_registry, AgentClass

registry = get_global_registry()

# List all agents
all_agents = registry.list_all()

# Filter by class
read_only_agents = registry.list_class(AgentClass.READ_ONLY_SCAN)

# Get specific agent
agent = registry.get("PG_DISCOVERY")

# Check permissions
can_write = agent.allows_write_to("var/artifacts/output.json")
```

## Adding New Agents

1. Create prompt file: `prompts/agents/PG_{NAME}_AGENT.md`
2. Follow the prompt contract format
3. Specify agent class in SCOPE/PERMISSIONS
4. Define OUTPUT schema
5. Agent will be auto-discovered on next run

No code changes required - agents are fully defined by their prompt contracts.
