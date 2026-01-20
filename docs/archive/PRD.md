# PLATFORM GOD - Product Requirements Document

## System Purpose

PLATFORM GOD is a deterministic, agent-driven repository governance system. It scans, analyzes, and generates artifacts for software repositories using a multi-agent orchestration model with strict permission boundaries and comprehensive audit trails.

### Core Mission

Provide automated repository governance through:
- Deterministic agent execution with no discretion
- Complete auditability of all operations
- Permission-based safety boundaries
- Multi-agent chain coordination
- State persistence for incremental analysis
- Human-in-the-loop decision support

### Target Users

1. **Software Engineers**: Analyze codebase health, identify technical debt, and plan refactoring
2. **Security Engineers**: Scan for secrets, credentials, and security vulnerabilities
3. **DevOps Engineers**: Audit dependencies, assess release readiness, and generate documentation
4. **Engineering Managers**: Track repository metrics, review accumulated findings, and monitor system health
5. **Compliance Officers**: Review audit trails, verify governance policies, and access decision records

## Non-Goals

PLATFORM GOD explicitly does NOT:

1. **Modify production code** - Write-gated agents may only modify specific designated paths (prompts/, var/)

2. **Execute arbitrary commands** - Agents have no shell or process execution capabilities

3. **Make autonomous decisions** - All agents follow strict prompt contracts with no discretion

4. **Access external networks** - Except for LLM API calls, all operations are local

5. **Implement user interfaces** - UI is a separate read-only Node.js/Ink component

6. **Serve as a general-purpose AI assistant** - Agents are task-specific, not conversational

7. **Replace human review** - All write operations require explicit approval and audit trails

---

## Product Requirements

### Overview

PLATFORM GOD consists of 6 core modules. This section defines functional requirements for each module, including API requirements, dashboard requirements, and configuration requirements.

### Module 1: Agent Registry and Execution

#### Status: COMPLETE (100%)

The Agent Registry is fully implemented and operational. This module manages agent discovery, loading, and execution.

**Functional Requirements:**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| AGENT-001 | Auto-discover agents from `prompts/agents/*.md` at runtime | P0 | Complete |
| AGENT-002 | Parse agent contracts (ROLE, GOAL, SCOPE, INPUT, OUTPUT) | P0 | Complete |
| AGENT-003 | Classify agents into 5 permission classes | P0 | Complete |
| AGENT-004 | Execute agents via LLM API with timeout and retry | P0 | Complete |
| AGENT-005 | Validate agent outputs against OUTPUT schema | P0 | Complete |
| AGENT-006 | Support DRY_RUN, SIMULATED, and LIVE execution modes | P0 | Complete |
| AGENT-007 | Write audit logs for all executions | P0 | Complete |
| AGENT-008 | Precheck validation before execution | P0 | Complete |

**API Requirements:**

```python
# Agent Registry API
class AgentRegistry:
    def get(self, name: str) -> AgentDefinition | None
    def list_all(self) -> list[AgentDefinition]
    def list_class(self, agent_class: AgentClass) -> list[AgentDefinition]
    def names(self) -> list[str]

# Execution Harness API
class ExecutionHarness:
    def execute(self, agent_name: str, input_data: dict, context: ExecutionContext) -> AgentResult
```

**Configuration Requirements:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `agents_dir` | Path | `prompts/agents/` | Directory containing agent definitions |
| `audit_dir` | Path | `var/audit/` | Directory for audit logs |
| `timeout_seconds` | int | 120 | LLM request timeout |
| `max_retries` | int | 3 | Retry attempts for transient failures |

**Remaining Work:** None

---

### Module 2: Chain Orchestration

#### Status: COMPLETE (100%)

The Chain Orchestrator is fully implemented with all predefined chains operational.

**Functional Requirements:**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| CHAIN-001 | Define chains as ordered sequences of agent steps | P0 | Complete |
| CHAIN-002 | Support state passing between steps via JSONPath | P0 | Complete |
| CHAIN-003 | Implement discovery_analysis chain | P0 | Complete |
| CHAIN-004 | Implement security_scan chain | P0 | Complete |
| CHAIN-005 | Implement dependency_audit chain | P0 | Complete |
| CHAIN-006 | Implement doc_generation chain | P0 | Complete |
| CHAIN-007 | Implement tech_debt chain | P0 | Complete |
| CHAIN-008 | Implement full_analysis chain | P0 | Complete |
| CHAIN-009 | Support continue_on_failure per step | P1 | Complete |
| CHAIN-010 | Generate chain execution summaries | P0 | Complete |

**Predefined Chains:**

| Chain | Steps | Output Keys |
|-------|-------|-------------|
| discovery_analysis | PG_DISCOVERY -> PG_STACKMAP -> PG_HEALTH_SCORE -> PG_REPORT_WRITER | discovery, stackmap, health, report |
| security_scan | PG_DISCOVERY -> PG_SECRETS_AND_RISK -> PG_NEXT_STEPS | discovery, security, recommendations |
| dependency_audit | PG_DISCOVERY -> PG_DEPENDENCY -> PG_SECRETS_AND_RISK -> PG_REPORT_WRITER | discovery, dependencies, risk, report |
| doc_generation | PG_DISCOVERY -> PG_STACKMAP -> PG_ENGINEERING_PRINCIPLES -> PG_DOC_AUDIT -> PG_DOC_MANAGER | discovery, stackmap, principles, doc_audit, documentation |
| tech_debt | PG_DISCOVERY -> PG_STACKMAP -> PG_HEALTH_SCORE -> PG_REFACTOR_PLANNER -> PG_NEXT_STEPS | discovery, stackmap, health, refactor_plan, next_steps |
| full_analysis | All agents combined | All keys above + readiness |

**API Requirements:**

```python
class ChainDefinition:
    @classmethod
    def discovery_chain(cls) -> ChainDefinition
    @classmethod
    def security_scan_chain(cls) -> ChainDefinition
    @classmethod
    def dependency_audit_chain(cls) -> ChainDefinition
    @classmethod
    def doc_generation_chain(cls) -> ChainDefinition
    @classmethod
    def tech_debt_chain(cls) -> ChainDefinition
    @classmethod
    def full_analysis_chain(cls) -> ChainDefinition

class Orchestrator:
    def execute_chain(self, chain: ChainDefinition, repository_root: Path, mode: ExecutionMode) -> ChainResult
    def chain_summary(self, result: ChainResult) -> str
    def persist_chain_result(self, result: ChainResult, output_dir: Path) -> Path
```

**Remaining Work:** None

---

### Module 3: Registry and State Storage

#### Status: COMPLETE (100%)

The Registry and State Storage modules are fully implemented.

**Functional Requirements:**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| REG-001 | File-based JSON storage for entities in `var/registry/` | P0 | Complete |
| REG-002 | Root index with entity type catalog and checksums | P0 | Complete |
| REG-003 | CRUD operations for registry entities | P0 | Complete |
| REG-004 | Registry operation audit logging | P0 | Complete |
| REG-005 | State storage for chain runs in `var/state/` | P0 | Complete |
| REG-006 | Repository fingerprinting for change detection | P0 | Complete |
| REG-007 | Accumulated findings across runs | P0 | Complete |
| REG-008 | State integrity verification via checksums | P1 | Complete |

**Registry Schema:**

```
var/registry/
├── _INDEX.json              # Root index: {version, last_updated, entities, checksums}
└── {entity_type}/
    └── {entity_id}.json     # EntityRecord: {entity_id, entity_type, data, created_at, updated_at, checksum, metadata}
```

**State Schema:**

```
var/state/
├── index.json               # Global index: {runs: [], repositories: []}
├── runs/
│   └── {run_id}.json       # ChainRun: {run_id, chain_name, repository_root, status, started_at, ...}
└── repositories/
    └── {repo_hash}.json    # RepositoryState: {repository_root, fingerprint, last_chain_runs, accumulated_findings, metrics}
```

**API Requirements:**

```python
# Registry API
class Registry:
    def register(self, entity_type: str, entity_id: str, entity_data: dict) -> RegistryResult
    def update(self, entity_type: str, entity_id: str, entity_data: dict) -> RegistryResult
    def deregister(self, entity_type: str, entity_id: str) -> RegistryResult
    def read(self, entity_type: str, entity_id: str) -> RegistryResult
    def list_by_type(self, entity_type: str) -> list[EntityRecord]
    def verify_integrity(self, entity_type: str, entity_id: str) -> bool

# State Manager API
class StateManager:
    def get_repository_state(self, repository_root: Path) -> RepositoryState
    def save_repository_state(self, state: RepositoryState) -> None
    def record_chain_run(self, chain_name: str, repository_root: Path, result: ChainResult) -> ChainRun
    def get_chain_run(self, run_id: str) -> ChainRun | None
    def list_runs(self, repository_root: Path | None, limit: int) -> list[ChainRun]
    def has_repository_changed(self, repository_root: Path) -> bool
```

**Remaining Work:** None

---

### Module 4: CLI Interface

#### Status: COMPLETE (100%)

The CLI is fully implemented with all primary commands.

**Functional Requirements:**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| CLI-001 | List all available agents | P0 | Complete |
| CLI-002 | List all available chains | P0 | Complete |
| CLI-003 | Execute chains with mode selection | P0 | Complete |
| CLI-004 | Quick repository inspection | P1 | Complete |
| CLI-005 | View execution history | P0 | Complete |
| CLI-006 | Launch UI (CLI mode) | P0 | Complete |
| CLI-007 | Launch UI (Dashboard mode) | P1 | Complete |
| CLI-008 | Display version information | P2 | Complete |

**Command Reference:**

| Command | Description | Status |
|---------|-------------|--------|
| `pgod agents [-c CLASS] [-v]` | List agents, optional class filter | Complete |
| `pgod chains` | List all execution chains | Complete |
| `pgod run <chain> <repo> [-m MODE] [-o FILE] [-r]` | Execute a chain | Complete |
| `pgod inspect <repo>` | Quick repository inspection | Complete |
| `pgod history <repo> [-n N]` | Show execution history | Complete |
| `pgod ui <repo> [-d]` | Launch UI (optional dashboard mode) | Complete |
| `pgod version` | Show version | Complete |

**Configuration Requirements:**

| Environment Variable | Type | Default | Description |
|---------------------|------|---------|-------------|
| `PG_LLM_PROVIDER` | string | `anthropic` | LLM provider |
| `PG_LLM_MODEL` | string | `claude-3-5-sonnet-20241022` | Model name |
| `PG_LLM_BASE_URL` | string | (provider default) | API endpoint |
| `ANTHROPIC_API_KEY` | string | (required) | Anthropic API key |
| `OPENAI_API_KEY` | string | (required for OpenAI) | OpenAI API key |

**Remaining Work:** None

---

### Module 5: Dashboard (Read-Only UI)

#### Status: COMPLETE (100%)

The Dashboard is implemented as a read-only Node.js/Ink application.

**Functional Requirements:**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| UI-001 | CLI mode with text output | P0 | Complete |
| UI-002 | Dashboard mode with interactive TUI | P0 | Complete |
| UI-003 | Display latest run summary | P0 | Complete |
| UI-004 | Display recent runs list | P0 | Complete |
| UI-005 | Display findings grouped by severity | P0 | Complete |
| UI-006 | Display artifact index | P1 | Complete |
| UI-007 | Display repository state | P0 | Complete |
| UI-008 | Keyboard navigation in dashboard mode | P0 | Complete |
| UI-009 | Tab-based navigation (Runs, Findings, Artifacts) | P0 | Complete |
| UI-010 | Strictly read-only - no writes or mutations | P0 | Complete |

**UI Components:**

| Component | Description | Technology |
|-----------|-------------|------------|
| CLI Output Renderer | Text-based output for terminal | Node.js |
| Ink Dashboard | Interactive TUI with tabs | React + Ink |
| Data Readers | Read-only access to state/registry | Node.js |

**Navigation:**

| Screen | Navigation |
|--------|------------|
| Main | Tab to switch views |
| Runs | Up/Down to navigate, Enter for details, ESC to back |
| Findings | Tab to filter by severity, Up/Down to navigate |
| Artifacts | Tab to filter by type, Up/Down to navigate |
| Global | Ctrl+C to quit |

**Configuration Requirements:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--repo` | Path | `.` | Repository path |
| `--dashboard` | flag | false | Enable TUI mode |
| `--mode` | string | `cli` | Output mode (cli/dashboard) |

**Remaining Work:** None

---

### Module 6: REST API

#### Status: COMPLETE (100%)

The REST API module is fully implemented with 37 endpoints across 6 API modules.

**Functional Requirements:**

| ID | Requirement | Priority | Status |
|----|-------------|----------|--------|
| API-001 | HTTP server for REST endpoints | P0 | Complete |
| API-002 | Agent listing endpoint | P0 | Complete |
| API-003 | Chain listing endpoint | P0 | Complete |
| API-004 | Chain execution endpoint | P0 | Complete |
| API-005 | Run history endpoint | P0 | Complete |
| API-006 | Repository state endpoint | P0 | Complete |
| API-007 | Registry query endpoint | P1 | Complete |
| API-008 | Health check endpoint | P0 | Complete |
| API-009 | Authentication middleware | P1 | Complete |
| API-010 | Rate limiting middleware | P2 | Complete |

**Implemented Endpoints:**

| Method | Path | Description | Response |
|--------|------|-------------|----------|
| GET | `/api/v1/health` | Health check | 200 OK |
| GET | `/api/v1/agents` | List all agents | Agent list |
| GET | `/api/v1/agents/{name}` | Get agent details | Agent definition |
| GET | `/api/v1/chains` | List all chains | Chain list |
| GET | `/api/v1/chains/{name}` | Get chain details | Chain definition |
| POST | `/api/v1/chains/{name}/execute` | Execute chain | Chain result |
| GET | `/api/v1/runs` | List chain runs | Run list |
| GET | `/api/v1/runs/{id}` | Get run details | Run details |
| GET | `/api/v1/repositories` | List repositories | Repository list |
| GET | `/api/v1/repositories/{id}` | Get repository state | Repository state |
| GET | `/api/v1/registry/{type}/{id}` | Get registry entity | Entity record |
| POST | `/api/v1/registry/{type}` | Create registry entity | Create result |
| PUT | `/api/v1/registry/{type}/{id}` | Update registry entity | Update result |
| DELETE | `/api/v1/registry/{type}/{id}` | Delete registry entity | Delete result |

**Configuration Requirements:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `host` | string | `127.0.0.1` | Bind address |
| `port` | int | `8000` | Server port |
| `api_key_required` | bool | `true` | Require API key |
| `rate_limit` | int | `100` | Requests per minute |
| `cors_enabled` | bool | `false` | Enable CORS |

**Acceptance Criteria:**

- All endpoints return JSON responses
- Error responses include error code and message
- Authentication via Bearer token or API key
- Rate limiting per API key
- Request logging to audit trail
- OpenAPI/Swagger documentation

**Remaining Work:** None

---

## User Stories

### Story 1: Developer Using CLI

**As a** software engineer
**I want to** scan my repository for security issues
**So that** I can identify and remediate vulnerabilities before deployment

**Acceptance Criteria:**

1. Given a repository path, I can execute `pgod run security_scan /path/to/repo --mode live`
2. The system executes the security_scan chain (PG_DISCOVERY -> PG_SECRETS_AND_RISK -> PG_NEXT_STEPS)
3. Results are displayed in the terminal with findings grouped by severity
4. I can optionally save results to a file with `--output results.json`
5. I can record the run for future reference with `--record`
6. Execution is logged to the audit trail
7. Exit code is 0 on success, 1 on failure

---

### Story 2: Developer Using API

**As a** developer integrating PLATFORM GOD into CI/CD
**I want to** trigger repository analysis via HTTP API
**So that** I can automate governance checks in my pipeline

**Acceptance Criteria:**

1. I can send a POST request to `/api/v1/chains/security_scan/execute` with repository path
2. The API returns a run ID for tracking
3. I can poll `/api/v1/runs/{id}` for status updates
4. When complete, I can fetch results including findings and recommendations
5. The API returns appropriate HTTP status codes (200, 400, 500)
6. Failed authentication returns 401 with error message
7. Rate limiting returns 429 with retry-after header

---

### Story 3: Admin Monitoring System

**As an** engineering manager
**I want to** view accumulated findings across all repositories
**So that** I can track technical debt and prioritize remediation

**Acceptance Criteria:**

1. I can launch the dashboard with `pgod ui /path/to/repo --dashboard`
2. The Runs tab shows execution history with status and duration
3. The Findings tab displays issues grouped by severity (critical, high, medium, low)
4. I can filter findings by severity using Tab key
5. The Artifacts tab shows generated reports and documentation
6. I can navigate between tabs using keyboard shortcuts
7. The UI is strictly read-only - no accidental modifications
8. Data refreshes when I re-enter the screen

---

## Acceptance Criteria

### By Module

#### Agent Registry and Execution

| Criterion | Description | Verification |
|-----------|-------------|--------------|
| AGENT-AC-001 | All 34 agents are discovered and loaded | `pgod agents` lists 34 agents |
| AGENT-AC-002 | Agents are correctly classified | `pgod agents -v` shows correct classes |
| AGENT-AC-003 | Execution times out after configured duration | Agent with infinite loop terminates |
| AGENT-AC-004 | Failed executions are logged | Audit log contains failure entries |
| AGENT-AC-005 | DRY_RUN mode makes no LLM calls | No API key required for dry_run |

#### Chain Orchestration

| Criterion | Description | Verification |
|-----------|-------------|--------------|
| CHAIN-AC-001 | All 6 predefined chains execute successfully | `pgod run <chain> . --mode simulated` completes |
| CHAIN-AC-002 | State passes correctly between steps | Later steps can access earlier outputs |
| CHAIN-AC-003 | Failed steps halt chain execution | Chain stops on first failure |
| CHAIN-AC-004 | continue_on_failure allows proceeding | Chain continues to next step |
| CHAIN-AC-005 | Chain results are persisted | Output file contains all step outputs |

#### Registry and State Storage

| Criterion | Description | Verification |
|-----------|-------------|--------------|
| REG-AC-001 | Entities can be registered, updated, and read | CRUD operations succeed |
| REG-AC-002 | Index tracks all entities | _INDEX.json contains all entities |
| REG-AC-003 | Checksums detect data corruption | Modified entity fails verification |
| REG-AC-004 | Repository fingerprints detect changes | Modified file triggers change detection |
| REG-AC-005 | Accumulated findings persist across runs | Findings from previous runs are retained |

#### CLI Interface

| Criterion | Description | Verification |
|-----------|-------------|--------------|
| CLI-AC-001 | All commands execute without error | No unhandled exceptions |
| CLI-AC-002 | Help text is available | `pgod --help` displays usage |
| CLI-AC-003 | Exit codes indicate success/failure | Success = 0, Failure = 1 |
| CLI-AC-004 | Output is formatted correctly | Tables render in terminal |
| CLI-AC-005 | Version is displayed | `pgod version` shows version |

#### Dashboard

| Criterion | Description | Verification |
|-----------|-------------|--------------|
| UI-AC-001 | CLI mode displays text output | Text renders to terminal |
| UI-AC-002 | Dashboard mode launches TUI | Ink interface renders |
| UI-AC-003 | Navigation works correctly | Tabs and arrow keys function |
| UI-AC-004 | No writes occur | File system is unchanged |
| UI-AC-005 | Data loads from state files | Runs and findings are displayed |

#### REST API

| Criterion | Description | Verification |
|-----------|-------------|--------------|
| API-AC-001 | Server starts on configured port | HTTP requests succeed |
| API-AC-002 | Health endpoint returns 200 | GET /api/v1/health returns OK |
| API-AC-003 | Agent listing returns JSON | GET /api/v1/agents returns array |
| API-AC-004 | Chain execution starts async | POST returns run ID immediately |
| API-AC-005 | Authentication rejects invalid tokens | 401 returned without auth |
| API-AC-006 | Rate limiting enforces limits | 429 returned after limit |

---

## Non-Functional Requirements

### Performance

| ID | Requirement | Target | Measurement |
|----|-------------|--------|-------------|
| PERF-001 | Agent execution time | < 30 seconds | Time from request to result |
| PERF-002 | Chain execution time | < 5 minutes (full_analysis) | Time from start to completion |
| PERF-003 | CLI startup time | < 1 second | Time to help text |
| PERF-004 | API response time | < 500ms (p95) | HTTP request latency |
| PERF-005 | State load time | < 2 seconds | Time to load repository state |
| PERF-006 | Memory usage | < 512 MB | Resident set size |
| PERF-007 | File I/O efficiency | < 100ms | Single file read/write |

### Security

| ID | Requirement | Implementation |
|----|-------------|----------------|
| SEC-001 | No unauthorized file writes | Permission boundary enforcement |
| SEC-002 | API key protection | Environment variables only |
| SEC-003 | Audit trail immutability | Append-only log files |
| SEC-004 | Input validation | Pydantic schema validation |
| SEC-005 | Path traversal prevention | Absolute path resolution |
| SEC-006 | LLM API communication only | No other network access |
| SEC-007 | Secret redaction | Credentials masked in logs |

### Reliability

| ID | Requirement | Target |
|----|-------------|--------|
| REL-001 | Agent execution success rate | > 99% |
| REL-002 | Chain completion rate | > 95% |
| REL-003 | Data integrity | SHA256 checksums |
| REL-004 | Recovery from transient failures | 3 automatic retries |
| REL-005 | Graceful degradation | Failed step halts chain cleanly |
| REL-006 | No data loss | Atomic write operations |

### Maintainability

| ID | Requirement | Target |
|----|-------------|--------|
| MAINT-001 | Code coverage | > 80% |
| MAINT-002 | Type annotation coverage | 100% |
| MAINT-003 | Documentation coverage | All public APIs documented |
| MAINT-004 | Agent contract format | Standardized Markdown |
| MAINT-005 | Error messages | Actionable and descriptive |

### Scalability

| ID | Requirement | Target |
|----|-------------|--------|
| SCALE-001 | Repository size | Up to 100K files |
| SCALE-002 | Concurrent chains | Single process (no concurrency) |
| SCALE-003 | State retention | Up to 1000 runs |
| SCALE-004 | Registry entities | Up to 10K entities |
| SCALE-005 | Audit log retention | Daily rotation |

---

## Success Metrics

### Development Progress

| Module | Status | Completion |
|--------|--------|------------|
| Agent Registry and Execution | Complete | 100% |
| Chain Orchestration | Complete | 100% |
| Registry and State Storage | Complete | 100% |
| CLI Interface | Complete | 100% |
| Dashboard (Read-Only UI) | Complete | 100% |
| REST API | Complete | 100% |

**Overall Completion: 100% (6 of 6 modules)**

### Quality Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Agents Registered | 34 | 34 |
| Chains Defined | 6 | 6+ |
| Test Coverage | TBD | > 80% |
| API Endpoints | 42 | 14+ |
| Documentation Pages | 9 | 15 |

### Adoption Metrics

| Metric | Target | Timeframe |
|--------|--------|-----------|
| Active repositories | 10 | v0.2.0 |
| Chains executed per week | 50 | v0.2.0 |
| Average execution time | < 5 min | v0.1.0 |
| API requests per day | 1000 | v0.3.0 |

---

## Deterministic Agent Model

### Agent Contract

Every agent is defined by a Markdown contract file in `prompts/agents/` containing:

```
ROLE       - What the agent does
GOAL       - The specific objective
NON-GOALS  - Explicit exclusions
SCOPE/PERMISSIONS - Read/write boundaries
OPERATING RULES - Mandatory execution constraints
INPUT      - Required input schema
PRECHECKS  - Validation before execution
TASKS      - Ordered steps to execute
VALIDATION - Output verification requirements
OUTPUT     - Strict JSON schema
```

### Execution Guarantees

- **No discretion**: Agents cannot deviate from defined tasks
- **No recovery**: Failures halt execution immediately
- **No assumptions**: Only provided input may be used
- **Full audit**: Every execution is logged to `var/audit/`

### Output Format

All agents return strict JSON matching the OUTPUT schema. Any deviation fails validation and is recorded as a failure.

---

## Safety & Governance Principles

### Permission Model

Five agent classes with graduated permissions:

| Class | Description | Write Access | Network Access |
|-------|-------------|--------------|----------------|
| READ_ONLY_SCAN | Repository scanning | None | None |
| PLANNING_SYNTHESIS | Analysis and planning | None | None |
| REGISTRY_STATE | Registry operations | var/registry/, var/audit/ | None |
| WRITE_GATED | Artifact generation | prompts/, var/ | None |
| CONTROL_PLANE | System operations | var/, prompts/ | None |

### Precheck Validation

Before any agent executes:
1. Repository root exists and is readable
2. Required inputs are present
3. Agent is registered in the catalog
4. Permission boundaries are satisfied

### Audit Trail

Every execution writes to `var/audit/execution_YYYYMMDD.jsonl`:
- Timestamp
- Agent name and class
- Execution status
- Duration in milliseconds
- Error messages (if any)

### State Persistence

Repository state is tracked in `var/state/`:
- Run history with chain results
- Repository fingerprints for change detection
- Accumulated findings across runs

---

## Supported Execution Modes

### DRY_RUN

Validate prechecks only. No agent execution.
- Use: Verify chain will execute successfully
- Output: Validation results only

### SIMULATED

Execute agents with mock outputs based on schemas.
- Use: Test chain logic without LLM calls
- Output: Schema-compliant mock data

### LIVE

Full agent execution via LLM API.
- Use: Production analysis
- Output: Real agent results

---

## What PLATFORM GOD Explicitly Does NOT Do

### Code Modification

PLATFORM GOD does NOT modify source code in:
- `src/`
- `configs/`
- `tests/`
- `scripts/`
- `assets/`

These paths are explicitly disallowed for all WRITE_GATED agents.

### Network Operations

PLATFORM GOD does NOT:
- Make HTTP requests except to configured LLM APIs
- Fetch external resources
- Send notifications (infrastructure exists but is not implemented)
- Access package repositories

### Decision Making

PLATFORM GOD does NOT:
- Choose strategies based on analysis
- Prioritize findings autonomously
- Select remediation approaches
- Make policy decisions

It produces structured outputs for human decision-making.

### Deployment

PLATFORM GOD does NOT:
- Deploy applications
- Manage infrastructure
- Execute CI/CD pipelines
- Restart services

---

## System Boundaries

### Inputs

- Local repository path
- Chain selection
- Execution mode
- Optional output file path

### Outputs

- JSON-formatted agent results
- Chain execution summaries
- Audit logs
- State records

### External Dependencies

- LLM API (Anthropic, OpenAI, or compatible)
- Python 3.11+
- Node.js 18+ (for UI only)

---

## Governance Model

### Write Gating

The `PG_WRITE_GATE_AGENT` validates all write operations:
- Target path permissions
- Actor authorization
- Rule compliance
- Provides allow/deny decision with reasoning

### Rollback

The `PG_ROLLBACK_AGENT` can reverse changes:
- Restores previous state from registry
- Validates rollback integrity
- Logs all rollback operations

### Baselines

Baselines track repository state for comparison:
- Security posture snapshots
- Performance metrics
- Compliance status
- Quality indicators

---

## Version Information

- **Current Version**: 0.1.0
- **Python Requirement**: >=3.11
- **Node.js Requirement**: >=18 (for UI only)
- **License**: See LICENSE file

---

## Architecture Constraints

1. No breaking changes to agent contracts
2. All state must be serializable to JSON
3. No circular dependencies between agents
4. Registry operations must be atomic
5. Audit logs must be append-only
6. UI must be strictly read-only
7. No parallel execution within chains
8. Single-process operation only

---

## Roadmap

### v0.1.0 (Current)

- Complete agent registry and execution
- Complete chain orchestration
- Complete registry and state storage
- Complete CLI interface
- Complete read-only dashboard
- Complete REST API

### v0.2.0 (Planned)

- Expand test coverage
- Add shell completion
- Performance optimizations
- Additional chain definitions

### v0.3.0 (Future)

- WebSocket support for real-time updates
- Multi-process chain execution
- Distributed state backend
- Advanced filtering and search
- Custom chain builder UI
