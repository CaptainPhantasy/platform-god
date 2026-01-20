# PLATFORM GOD - Software Design Document

## Architecture Overview

PLATFORM GOD is a Python-based multi-agent system with a separate Node.js UI. The architecture follows a layered design with clear separation between orchestration, execution, and storage.

### Component Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        CLI Layer                            │
│                    (src/platform_god/cli.py)                │
│  - Typer-based command interface                            │
│  - Entry points: pgod, platform-god                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                   Orchestrator Layer                        │
│              (src/platform_god/orchestrator/)              │
│  - Chain definition and execution                           │
│  - State passing between agents                             │
│  - Failure handling                                         │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                    Execution Layer                          │
│               (src/platform_god/agents/)                   │
│  - AgentRegistry: Catalog and loader                        │
│  - ExecutionHarness: Safe execution with validation         │
│  - Precheck validation                                      │
└─────────────────────────────────────────────────────────────┘
                              │
┌──────────────┬──────────────────┬──────────────────────────┐
│ Storage Layer│   LLM Interface   │    State Management      │
│(registry/)   │    (llm/)        │      (state/)            │
│- Entity CRUD │- Anthropic Claude │- Run history             │
│- Audit log   │- OpenAI GPT      │- Repository fingerprints │
│- Index       │- Custom API      │- Findings accumulation   │
└──────────────┴──────────────────┴──────────────────────────┘
```

### Module Structure

```
src/platform_god/
├── __init__.py          # Package initialization
├── cli.py               # CLI entry point
├── version.py           # Version definition
├── core/
│   └── models.py        # Core data models
├── agents/
│   ├── registry.py      # Agent catalog and loader
│   └── executor.py      # Execution harness
├── orchestrator/
│   └── core.py          # Multi-agent coordination
├── llm/
│   └── client.py        # LLM provider abstraction
├── registry/
│   └── storage.py       # Persistent entity storage
└── state/
    └── manager.py       # Cross-run state management
```

## Agent Permission Model

### Agent Classes

Permissions are defined by the `AgentClass` enum in `core/models.py`:

```python
class AgentClass(Enum):
    READ_ONLY_SCAN = "READ_ONLY_SCAN"
    PLANNING_SYNTHESIS = "PLANNING_SYNTHESIS"
    REGISTRY_STATE = "REGISTRY_STATE"
    WRITE_GATED = "WRITE_GATED"
    CONTROL_PLANE = "CONTROL_PLANE"
```

### Permission Boundaries

Each class has specific `AgentPermissions` (immutable dataclass):

| Class | can_read | can_write | can_network | allowed_write_paths | disallowed_paths |
|-------|----------|-----------|-------------|---------------------|------------------|
| READ_ONLY_SCAN | True | False | False | () | () |
| PLANNING_SYNTHESIS | True | False | False | () | () |
| REGISTRY_STATE | True | True | False | var/registry/, var/audit/ | () |
| WRITE_GATED | True | True | False | prompts/, var/artifacts/, var/cache/ | src/, configs/, docs/, tests/, scripts/, assets/ |
| CONTROL_PLANE | True | True | False | var/, prompts/ | () |

### Permission Enforcement

The `ExecutionHarness._run_prechecks()` method validates:
1. Repository root exists and is accessible
2. Required inputs are present
3. Agent is registered
4. Operation is within permission boundaries

Write operations are checked via `AgentDefinition.allows_write_to(path)`.

## Registry and State Design

### Registry Storage (`var/registry/`)

File-based JSON storage for entity tracking:

```
var/registry/
├── _INDEX.json              # Root index with checksums
└── {entity_type}/           # Entity type directories
    └── {entity_id}.json     # Individual entity records
```

**Index Structure** (`RegistryIndex`):
- `version`: Schema version
- `last_updated`: ISO timestamp
- `entities`: Map of entity_type -> [entity_ids]
- `checksums`: Map of entity_id -> SHA256

**Entity Record** (`EntityRecord`):
- `entity_id`: Unique identifier
- `entity_type`: Type categorization
- `data`: JSON payload
- `created_at`, `updated_at`: ISO timestamps
- `checksum`: SHA256 of data

### State Management (`var/state/`)

Cross-run state for incremental analysis:

```
var/state/
├── index.json               # Global run index
├── runs/
│   └── {run_id}.json       # Individual chain runs
└── repositories/
    └── {repo_hash}.json    # Repository state
```

**Repository State** (`RepositoryState`):
- `repository_root`: Absolute path
- `fingerprint`: Repository fingerprint for change detection
- `last_chain_runs`: Map of chain_name -> run_id
- `accumulated_findings`: Findings from all runs
- `metrics`: Accumulated metrics

### Audit Trail (`var/audit/`)

Append-only JSONL logs:

```
var/audit/
├── execution_YYYYMMDD.jsonl    # Agent executions
└── registry_log.jsonl          # Registry operations
```

## Chain Execution Model

### Chain Definition

Chains are defined as `ChainDefinition` dataclasses:

```python
@dataclass
class ChainDefinition:
    name: str
    description: str
    steps: list[AgentStep]
    initial_state: dict[str, Any]
```

Each step specifies:
- `agent_name`: Agent to execute
- `input_mapping`: JSONPath expression for input (e.g., "$.discovery")
- `output_key`: Key to store output for subsequent steps
- `continue_on_failure`: Whether to continue if this step fails

### State Passing

The `ChainState` class manages state between agents:

```python
def resolve_input(self, input_mapping: str | None, initial_state: dict) -> dict:
    """
    Supports:
    - null -> use initial_state
    - "$.key" -> extract single key
    - "$.a,$.b" -> merge multiple keys
    """
```

### Execution Flow

1. Initialize `ChainState` with `initial_state`
2. For each step:
   - Resolve input from state using `input_mapping`
   - Create `ExecutionContext` with mode and metadata
   - Execute agent via `ExecutionHarness`
   - Store output under `output_key`
   - Call `on_step_complete` callback if provided
   - On failure (if not `continue_on_failure`): halt and return

### Available Chains

| Chain Name | Description | Steps |
|------------|-------------|-------|
| discovery_analysis | Scan repository and generate report | PG_DISCOVERY → PG_STACKMAP → PG_HEALTH_SCORE → PG_REPORT_WRITER |
| security_scan | Scan for secrets and risks | PG_DISCOVERY → PG_SECRETS_AND_RISK → PG_NEXT_STEPS |
| dependency_audit | Analyze dependencies | PG_DISCOVERY → PG_DEPENDENCY → PG_SECRETS_AND_RISK → PG_REPORT_WRITER |
| doc_generation | Generate documentation | PG_DISCOVERY → PG_STACKMAP → PG_ENGINEERING_PRINCIPLES → PG_DOC_AUDIT → PG_DOC_MANAGER |
| tech_debt | Analyze technical debt | PG_DISCOVERY → PG_STACKMAP → PG_HEALTH_SCORE → PG_REFACTOR_PLANNER → PG_NEXT_STEPS |
| full_analysis | Complete repository analysis | All agents combined |

## Failure Handling and Rollback

### Failure Modes

1. **Precheck Failure**: Execution stops before agent runs
   - Logged to audit trail
   - Returns `AgentStatus.STOPPED`

2. **Agent Failure**: Agent returns failure status
   - Chain stops (unless `continue_on_failure=True`)
   - Error message recorded
   - Partial results preserved

3. **Validation Failure**: Output doesn't match schema
   - Treated as agent failure
   - Raw output logged for debugging

### Rollback Mechanism

The `PG_ROLLBACK_AGENT` provides:
- Restoration from registry snapshots
- Integrity validation
- Audit logging of rollback operations

Rollback is NOT automatic - it must be explicitly invoked.

## LLM Provider Abstraction

### Supported Providers

The `LLMProvider` enum defines supported providers:

```python
class LLMProvider(Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    CUSTOM = "custom"
```

### Configuration

Environment-based configuration:

```bash
# Provider selection
PG_LLM_PROVIDER=anthropic|openai|azure_openai|custom

# API keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
PG_LLM_API_KEY=...  # For custom provider

# Model override
PG_LLM_MODEL=claude-3-5-sonnet-20241022

# Custom endpoint
PG_LLM_BASE_URL=https://...
```

### Request/Response Model

```python
@dataclass
class LLMRequest:
    prompt: str
    system_prompt: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.0
    response_format: str | None = None  # "json" for strict JSON

@dataclass
class LLMResponse:
    content: str
    model: str
    provider: LLMProvider
    tokens_used: int | None = None
    finish_reason: str | None = None
    raw_response: dict[str, Any]
```

### Retry Logic

The client implements automatic retry for:
- HTTP 429 (rate limiting)
- HTTP 502, 503, 504 (server errors)
- Network failures

Default: 3 retries with exponential backoff.

## Database Schema

The `schemas/registry.sql` defines a SQLite schema with 16 tables:

### Core Tables

- `projects`: Tracked repositories
- `agents`: Available agent definitions
- `runs`: Top-level execution runs
- `agent_runs`: Individual agent executions

### Governance Tables

- `findings`: Issues and observations
- `decisions`: Governance decisions
- `baselines`: Snapshots for comparison

### Supporting Tables

- `tags`, `project_tags`: Categorization
- `project_relationships`: Dependencies between projects
- `artifacts`: Generated outputs
- `prompt_versions`: Prompt change tracking
- `notifications`: Event logging
- `agent_output_schemas`: Output validation
- `run_targets`: Run scope specification

### Triggers

Automatic timestamp updates on:
- `projects.updated_at`
- `findings.updated_at`
- `agents.updated_at`

## Concurrency and Isolation

### File Locking

Not implemented. The system assumes single-process operation.

### State Consistency

- Registry operations are atomic (write-then-rename)
- Audit logs are append-only
- State updates are serialized within a run

### Multi-Process Safety

Not currently supported. Future versions may add:
- File-based locking for registry
- Database-backed state
- Distributed coordination

## Error Handling Strategy

### Exception Categories

1. **Recoverable**: Retry with different parameters
2. **Non-recoverable**: Log and fail
3. **Catastrophic**: System halt

### Error Propagation

```
Agent Execution → ExecutionHarness → Orchestrator → CLI → Exit Code
```

Exit codes:
- 0: Success
- 1: Failure (agent or chain)

## Security Considerations

### Input Validation

- All file paths are validated against permission boundaries
- JSON inputs are parsed with Pydantic validation
- Repository roots must exist and be readable

### Secret Scanning

The `PG_SECRETS_AND_RISK_AGENT` scans for:
- API keys
- Credentials
- Sensitive tokens
- Certificate files

### Audit Trail

All operations are logged with:
- Timestamp
- Actor
- Operation type
- Target
- Result

This enables forensic analysis and compliance auditing.
